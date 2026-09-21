"""
Extrator dos Dados Abertos de CNPJ (Receita Federal).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("baixar_receita")

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
try:
    import config as cfg
except ImportError:
    log.error("config.py não encontrado — este script precisa estar na mesma pasta que ele (etl/).")
    raise

BASE_DIR = Path(__file__).resolve().parent     # etl/

# Convenção: cada fonte (receita/pncp/transparencia) usa sua própria subpasta dentro dos
# diretórios compartilhados do config.py, pra não um script pisar no dado do outro.
#
# Os caminhos do config.py são absolutos e ancorados em etl/, então não se
# prefixa mais com a raiz do repositório: prefixar funcionaria (o pathlib
# descarta o lado esquerdo quando o direito é absoluto), mas daria a entender
# que a árvore de dados fica na raiz, e era exatamente essa leitura que fazia
# este script e os do PNCP gravarem em pastas diferentes.
RAW_DIR = Path(cfg.DIR_DADOS_RAW) / "receita"
PARQUET_DIR = Path(cfg.DIR_DADOS_PARQUET) / "receita"
INVENTORY_DIR = Path(cfg.DIR_INVENTARIO)

for _dir in (RAW_DIR, INVENTORY_DIR, PARQUET_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# O servidor oficial da Receita derruba conexão vinda de IP de nuvem (confirmado testando Kaggle e
# outros runners); por isso o mirror comunitário atrás da Cloudflare vem primeiro. As pastas de
# competência mudam de formato entre as fontes (YYYY-MM na oficial, YYYY-MM-DD no mirror) — o regex
# de descoberta aceita os dois.
FONTES_PADRAO = [
    ("mirror (casadosdados, atrás da Cloudflare)", "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos"),
    ("oficial (arquivos.receitafederal.gov.br)", "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj"),
    ("oficial alternativa (dadosabertos.rfb.gov.br)", "https://dadosabertos.rfb.gov.br/CNPJ/dados_abertos_cnpj"),
]

# Confiram este layout contra o PDF oficial antes de usar em produção:
# https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf  (é a Armadilha 6 do roteiro do projeto)
LAYOUTS: dict[str, list[tuple[str, str]]] = {
    "EMPRECSV": [
        ("cnpj_basico", "texto"), ("razao_social", "texto"), ("natureza_juridica", "texto"),
        ("qualificacao_responsavel", "texto"), ("capital_social", "moeda"),
        ("porte_empresa", "texto"), ("ente_federativo_responsavel", "texto"),
    ],
    "ESTABELE": [
        ("cnpj_basico", "texto"), ("cnpj_ordem", "texto"), ("cnpj_dv", "texto"),
        ("identificador_matriz_filial", "texto"), ("nome_fantasia", "texto"),
        ("situacao_cadastral", "texto"), ("data_situacao_cadastral", "data"),
        ("motivo_situacao_cadastral", "texto"), ("nome_cidade_exterior", "texto"),
        ("pais", "texto"), ("data_inicio_atividade", "data"), ("cnae_fiscal_principal", "texto"),
        ("cnae_fiscal_secundaria", "texto"), ("tipo_logradouro", "texto"), ("logradouro", "texto"),
        ("numero", "texto"), ("complemento", "texto"), ("bairro", "texto"), ("cep", "texto"),
        ("uf", "texto"), ("municipio", "texto"), ("ddd_1", "texto"), ("telefone_1", "texto"),
        ("ddd_2", "texto"), ("telefone_2", "texto"), ("ddd_fax", "texto"), ("fax", "texto"),
        ("correio_eletronico", "texto"), ("situacao_especial", "texto"), ("data_situacao_especial", "data"),
    ],
    "SOCIOCSV": [
        ("cnpj_basico", "texto"), ("identificador_socio", "texto"), ("nome_socio_razao_social", "texto"),
        ("cnpj_cpf_socio", "texto"), ("qualificacao_socio", "texto"), ("data_entrada_sociedade", "data"),
        ("pais", "texto"), ("representante_legal", "texto"), ("nome_representante", "texto"),
        ("qualificacao_representante_legal", "texto"), ("faixa_etaria", "texto"),
    ],
    "SIMPLES": [
        ("cnpj_basico", "texto"), ("opcao_simples", "texto"), ("data_opcao_simples", "data"),
        ("data_exclusao_simples", "data"), ("opcao_mei", "texto"), ("data_opcao_mei", "data"),
        ("data_exclusao_mei", "data"),
    ],
}
_TABELAS_DOMINIO = {
    "CNAECSV": "cnae", "MOTICSV": "motivo", "MUNICCSV": "municipio",
    "NATJUCSV": "natureza_juridica", "PAISCSV": "pais", "QUALSCSV": "qualificacao_socio",
}
for _chave, _nome in _TABELAS_DOMINIO.items():
    LAYOUTS[_chave] = [("codigo", "texto"), (f"descricao_{_nome}", "texto")]


def adivinhar_layout(nome_arquivo: str) -> str | None:
    up = nome_arquivo.upper()
    for chave in LAYOUTS:
        if chave in up:
            return chave
    return None


# ---------------------------------------------------------------------------
# Sessão HTTP
# ---------------------------------------------------------------------------
def criar_sessao() -> requests.Session:
    sessao = requests.Session()
    retries = Retry(total=4, backoff_factor=4, status_forcelist=[429, 500, 502, 503, 504])
    sessao.mount("http://", HTTPAdapter(max_retries=retries))
    sessao.mount("https://", HTTPAdapter(max_retries=retries))
    sessao.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })
    return sessao


# ---------------------------------------------------------------------------
# Descoberta de fonte e de arquivos
# ---------------------------------------------------------------------------
def escolher_fonte_disponivel(sessao: requests.Session, fontes=FONTES_PADRAO, timeout=15):
    for nome, base in fontes:
        try:
            url = base if base.endswith("/") else base + "/"
            resp = sessao.get(url, timeout=timeout)
            resp.raise_for_status()
            log.info("Fonte escolhida: %s -> %s", nome, base)
            return base, resp
        except Exception as e:  # noqa: BLE001 — queremos seguir pra próxima fonte em qualquer falha
            log.warning("  %s indisponível (%s); tentando próxima...", nome, e)
    raise RuntimeError("Nenhuma fonte de dados da Receita respondeu.")


def listar_zips(sessao: requests.Session, base: str, resp_inicial=None, competencia: str | None = None):
    """Descobre .zip a partir de uma base: se houver pastas YYYY-MM ou YYYY-MM-DD, entra na pedida
    (ou na mais recente, se `competencia` não for informada); senão assume que os .zip já estão
    listados na própria página. Devolve (urls_zip, competencia_usada) — competencia_usada é None
    quando a fonte não usa pastas por competência."""
    url_base = base if base.endswith("/") else base + "/"
    resp = resp_inicial if resp_inicial is not None else sessao.get(url_base, timeout=30)

    pastas = sorted(set(re.findall(r'href="([^"]*?\d{4}-\d{2}(?:-\d{2})?)/?"', resp.text)))
    competencia_usada = None
    if pastas:
        competencia_usada = competencia or pastas[-1].rstrip("/").split("/")[-1]
        if competencia and competencia_usada not in [p.rstrip("/").split("/")[-1] for p in pastas]:
            raise ValueError(f"Competência {competencia!r} não encontrada. Disponíveis: {pastas}")
        url_pasta = urljoin(url_base, competencia_usada + "/")
        log.info("Competência: %s", competencia_usada)
        resp = sessao.get(url_pasta, timeout=30)
        pagina_base = url_pasta
    else:
        log.info("Nenhuma pasta de competência encontrada; assumindo .zip listados na própria página.")
        pagina_base = url_base

    nomes_zip = sorted(set(re.findall(r'href="([^"]+\.zip)"', resp.text, flags=re.IGNORECASE)))
    urls_zip = [urljoin(pagina_base, nome) for nome in nomes_zip]
    return urls_zip, competencia_usada


def get_latest_folder() -> str | None:
    """Descobre a competência mais recente disponível, sem baixar nada — nome alinhado com o
    comentário do config.py (`cnpj-processor.get_latest_folder()`)."""
    sessao = criar_sessao()
    base, resp_inicial = escolher_fonte_disponivel(sessao)
    _, competencia = listar_zips(sessao, base, resp_inicial)
    return competencia


# ---------------------------------------------------------------------------
# Download resumível
# ---------------------------------------------------------------------------
def baixar_arquivo(sessao: requests.Session, url: str, destino: Path, timeout=60) -> Path:
    destino = Path(destino)
    modo, pos_inicial, cabecalhos = "wb", 0, {}
    if destino.exists():
        pos_inicial = destino.stat().st_size
        cabecalhos["Range"] = f"bytes={pos_inicial}-"
        modo = "ab"
    with sessao.get(url, headers=cabecalhos, stream=True, timeout=timeout) as resposta:
        if resposta.status_code == 416:
            return destino  # já estava completo
        resposta.raise_for_status()
        with open(destino, modo) as f:
            for pedaco in resposta.iter_content(chunk_size=1024 * 1024):
                if pedaco:
                    f.write(pedaco)
    return destino


def baixar_lista(sessao: requests.Session, urls: list[str], pasta_destino: Path) -> pd.DataFrame:
    log_linhas = []
    for url in urls:
        nome = url.rstrip("/").split("/")[-1]
        destino = pasta_destino / nome
        try:
            baixar_arquivo(sessao, url, destino)
            log_linhas.append({"arquivo": nome, "status": "ok",
                                "tamanho_mb": round(destino.stat().st_size / 1e6, 1)})
            log.info("Baixado: %s (%.1f MB)", nome, destino.stat().st_size / 1e6)
        except Exception as e:  # noqa: BLE001
            log_linhas.append({"arquivo": nome, "status": f"erro: {e}", "tamanho_mb": None})
            log.error("Falha ao baixar %s: %s", nome, e)
        pd.DataFrame(log_linhas).to_csv(pasta_destino / "log_download_receita.csv", index=False)
    return pd.DataFrame(log_linhas)


# ---------------------------------------------------------------------------
# Leitura direto de dentro do zip (nunca extrai pro disco)
# ---------------------------------------------------------------------------
def listar_membros_zip(pasta_raw: Path) -> list[dict]:
    membros, avisos = [], []
    for z in sorted(pasta_raw.glob("*.zip")):
        try:
            with zipfile.ZipFile(z) as arq:
                for zinfo in arq.infolist():
                    layout_key = adivinhar_layout(zinfo.filename)
                    if layout_key:
                        membros.append({
                            "zip": str(z), "membro": zinfo.filename, "layout": layout_key,
                            "tamanho_comprimido_mb": round(zinfo.compress_size / 1e6, 2),
                            "tamanho_descomprimido_mb": round(zinfo.file_size / 1e6, 2),
                        })
        except zipfile.BadZipFile:
            avisos.append(z.name)
    if avisos:
        log.warning("Corrompidos/incompletos, baixem de novo: %s", avisos)
    return membros


def ler_amostra(caminho_zip: str, nome_membro: str, layout_key: str, nrows: int | None = 200_000) -> pd.DataFrame:
    colunas = [c for c, _ in LAYOUTS[layout_key]]
    with zipfile.ZipFile(caminho_zip) as arq, arq.open(nome_membro) as f:
        return pd.read_csv(
            f, sep=";", header=None, names=colunas, encoding="latin-1",
            dtype=str, nrows=nrows, on_bad_lines="warn", engine="python",
        )


def construir_inventario(membros: list[dict], pasta_destino: Path,
                          nome_arquivo: str = "inventario_receita_amostra.csv") -> pd.DataFrame:
    linhas = []
    for item in membros:
        amostra = ler_amostra(item["zip"], item["membro"], item["layout"])
        for col in amostra.columns:
            linhas.append({
                "arquivo": item["membro"], "layout": item["layout"],
                "tamanho_comprimido_mb": item["tamanho_comprimido_mb"],
                "tamanho_descomprimido_mb": item["tamanho_descomprimido_mb"],
                "linhas_na_amostra": len(amostra), "coluna": col,
                "pct_nulos_amostra": round(amostra[col].isna().mean() * 100, 2),
                "valores_distintos_amostra": int(amostra[col].nunique(dropna=True)),
            })
        dup = int(amostra.duplicated(subset=[amostra.columns[0]]).sum())
        linhas.append({
            "arquivo": item["membro"], "layout": item["layout"],
            "tamanho_comprimido_mb": item["tamanho_comprimido_mb"],
            "tamanho_descomprimido_mb": item["tamanho_descomprimido_mb"],
            "linhas_na_amostra": len(amostra), "coluna": "__duplicatas_pela_1a_coluna__",
            "pct_nulos_amostra": None, "valores_distintos_amostra": dup,
        })
    df = pd.DataFrame(linhas)
    pasta_destino.mkdir(parents=True, exist_ok=True)
    destino = pasta_destino / nome_arquivo
    df.to_csv(destino, index=False)
    tc = sum(i["tamanho_comprimido_mb"] for i in membros) / 1000
    td = sum(i["tamanho_descomprimido_mb"] for i in membros) / 1000
    log.info("Inventário salvo em %s", destino)
    log.info("Volume: %.2f GB comprimido -> %.2f GB descomprimido", tc, td)
    return df


# ---------------------------------------------------------------------------
# Fase 2: filtrar contra uma lista de CNPJs e salvar em parquet (em chunks, sem extrair)
# ---------------------------------------------------------------------------
def carregar_lista_cnpjs(caminho: str | Path) -> set[str]:
    """Lê a lista de raízes de CNPJ produzida pelo recorte_cnpjs.py.

    Aceita os dois formatos que ele grava: CSV com cabeçalho `cnpj_basico`
    (cnpjs_raiz.csv) e texto puro, um por linha (cnpjs_raiz.txt). Antes, só
    o CSV era aceito, e passar o .txt consumia a primeira raiz como nome de
    coluna e estourava com KeyError.

    E valida o comprimento, que é a guarda que importa. O quadro societário
    da Receita é chaveado pela RAIZ de 8 dígitos (RN-01). Se alguém passar
    cnpjs_completos.txt, que tem os CNPJ de 14, o `isin` não casa com nada:
    o resultado é zero linhas, sem erro, sem aviso, e um parquet vazio que
    parece download malsucedido. Falhar alto aqui custa uma mensagem e
    elimina a categoria inteira de erro.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise SystemExit(
            f"ERRO: lista de CNPJs não encontrada: {caminho}\n"
            f"       Gere com:  python recorte_cnpjs.py"
        )

    primeira = caminho.read_text(encoding="utf-8").splitlines()[:1]
    tem_cabecalho = bool(primeira) and not primeira[0].strip().isdigit()

    if tem_cabecalho:
        df = pd.read_csv(caminho, dtype=str)
        if "cnpj_basico" not in df.columns:
            raise SystemExit(
                f"ERRO: {caminho.name} tem cabeçalho mas não a coluna "
                f"`cnpj_basico`.\n       Colunas encontradas: {list(df.columns)}"
            )
        valores = df["cnpj_basico"]
    else:
        valores = pd.Series([l.strip() for l in
                             caminho.read_text(encoding="utf-8").splitlines()])

    lista = {v for v in valores.dropna().astype(str).str.strip() if v}
    if not lista:
        raise SystemExit(f"ERRO: {caminho.name} está vazio.")

    larguras = {len(v) for v in lista}
    if larguras != {8}:
        exemplo = sorted(lista)[0]
        raise SystemExit(
            f"ERRO: a lista de filtro precisa ser de RAÍZES de 8 dígitos, e "
            f"{caminho.name} tem entradas de {sorted(larguras)} dígito(s).\n"
            f"       Exemplo: {exemplo!r}\n"
            f"       O quadro societário da Receita é chaveado pela raiz "
            f"(RN-01); filtrar por CNPJ de 14 devolveria zero linhas sem "
            f"erro nenhum.\n"
            f"       Use dados/recorte/cnpjs_raiz.csv, não cnpjs_completos.txt."
        )
    return lista


def filtrar_para_parquet(membros: list[dict], lista_cnpjs: set[str], pasta_destino: Path,
                          competencia: str | None = None,
                          chunksize: int = 300_000) -> dict[str, Path]:
    """Filtra cada arquivo (empresas/estabelecimentos/sócios/simples) contra `lista_cnpjs`,
    lendo em chunks direto de dentro do zip, e salva um .parquet por layout. Tabelas de domínio
    (CNAE, município, país...) não têm `cnpj_basico` — são copiadas inteiras, sem filtro, porque
    são pequenas tabelas de referência usadas por qualquer linha, não por CNPJ específico."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    saidas: dict[str, list[pd.DataFrame]] = {}
    descartadas: dict[str, int] = {}

    for item in membros:
        layout_key = item["layout"]
        colunas = [c for c, _ in LAYOUTS[layout_key]]
        tem_cnpj = "cnpj_basico" in colunas
        lidas = 0
        with zipfile.ZipFile(item["zip"]) as arq, arq.open(item["membro"]) as f:
            for pedaco in pd.read_csv(f, sep=";", header=None, names=colunas, encoding="latin-1",
                                       dtype=str, chunksize=chunksize, on_bad_lines="warn", engine="python"):
                # A Receita pode acrescentar coluna numa competência futura. Sem
                # esta checagem, o pandas alinharia errado em silêncio e o dado
                # sairia deslocado -- o pior tipo de falha, porque não avisa.
                if lidas == 0 and len(pedaco.columns) != len(colunas):
                    raise SystemExit(
                        f"ERRO: {item['membro']} tem {len(pedaco.columns)} colunas, "
                        f"e o layout {layout_key} declara {len(colunas)}.\n"
                        f"       A Receita mudou o arquivo. Confira o PDF de "
                        f"metadados e atualize LAYOUTS antes de continuar."
                    )
                lidas += len(pedaco)
                trecho = pedaco[pedaco["cnpj_basico"].isin(lista_cnpjs)] if tem_cnpj else pedaco
                if not trecho.empty:
                    saidas.setdefault(layout_key, []).append(trecho)
        descartadas[layout_key] = descartadas.get(layout_key, 0) + lidas
        log.info("Processado %s (%s): %d linha(s) lida(s)%s", item["membro"], layout_key,
                  lidas, "" if tem_cnpj else " — tabela de domínio, copiada inteira")

    caminhos: dict[str, Path] = {}
    linhas_salvas: dict[str, int] = {}
    for layout_key, partes in saidas.items():
        destino = pasta_destino / f"{layout_key.lower()}.parquet"
        df = pd.concat(partes, ignore_index=True)
        df.to_parquet(destino, index=False)
        caminhos[layout_key] = destino
        linhas_salvas[layout_key] = len(df)
        log.info("Salvo %s (%d linha(s) de %d lidas)",
                 destino, len(df), descartadas.get(layout_key, 0))

    escrever_manifesto(pasta_destino, caminhos, linhas_salvas, descartadas,
                       len(lista_cnpjs), competencia)
    return caminhos


def escrever_manifesto(pasta_destino: Path, caminhos: dict[str, Path],
                       linhas_salvas: dict[str, int], linhas_lidas: dict[str, int],
                       total_cnpjs: int, competencia: str | None) -> Path:
    """Grava o contrato de entrega ao lado dos parquet.

    Existe por dois motivos concretos.

    O primeiro é que os tipos declarados no dicionário LAYOUTS ("data",
    "moeda", "texto") eram escritos e nunca lidos: quem consome o LAYOUTS faz
    `[c for c, _ in ...]` e descarta o tipo. Era uma promessa que o código não
    cumpria, e alguém acabaria confiando nela. O parquet continua saindo com
    tudo em texto, que é o certo -- converter é trabalho do tratamento --, mas
    agora o tratamento recebe por escrito quais colunas são data e quais são
    moeda, em vez de ter que adivinhar ou duplicar a tabela.

    O segundo é a competência. A RN-08 e a tabela ponte do modelo estrela
    exigem declarar de qual competência veio o quadro societário, porque a
    Receita não publica data de saída da sociedade: cada arquivo é um retrato
    do momento. Sem isso registrado junto ao dado, essa informação se perde na
    primeira vez que alguém copiar a pasta.
    """
    manifesto = {
        "competencia": competencia,
        "total_cnpjs_no_filtro": total_cnpjs,
        "observacao": (
            "Colunas gravadas como TEXTO, de propósito: zeros à esquerda são "
            "significativos em CNPJ, CEP, código de município e CNAE. A "
            "conversão de tipo pertence ao tratamento, e os tipos de origem "
            "estão em `colunas` abaixo. Datas vêm como AAAAMMDD com ausência "
            "representada por '00000000'; moeda vem com vírgula decimal."
        ),
        "arquivos": {
            chave: {
                "parquet": caminhos[chave].name,
                "linhas_gravadas": linhas_salvas.get(chave, 0),
                "linhas_lidas_na_origem": linhas_lidas.get(chave, 0),
                "colunas": [{"nome": c, "tipo_origem": t} for c, t in LAYOUTS[chave]],
            }
            for chave in caminhos
        },
    }
    destino = pasta_destino / "_manifesto.json"
    destino.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    log.info("Manifesto escrito em %s", destino)
    return destino


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--filtro", help="regex pra baixar só parte dos arquivos (ex.: 'Socios')")
    parser.add_argument("--competencia", default=cfg.MES_RECEITA,
                         help=f"competência a usar (padrão: config.MES_RECEITA = {cfg.MES_RECEITA!r}; "
                              "se None, pega a mais recente automaticamente)")
    parser.add_argument("--fonte-url", help="força uma fonte específica, pulando a descoberta automática")
    parser.add_argument("--sem-download", action="store_true", help="pula o download, só reconstrói o inventário")
    parser.add_argument("--filtrar-cnpjs", metavar="ARQUIVO", nargs="?",
                         const=str(Path(cfg.DIR_RECORTE) / "cnpjs_raiz.csv"),
                         help="Fase 2: filtra contra a lista de raízes de CNPJ e salva "
                              "em .parquet. Sem valor, usa dados/recorte/cnpjs_raiz.csv, "
                              "gerado por recorte_cnpjs.py. Aceita CSV com coluna "
                              "cnpj_basico ou texto puro, um por linha.")
    args = parser.parse_args(argv)

    sessao = criar_sessao()
    urls_zip: list[str] = []
    competencia_usada = args.competencia

    if not args.sem_download:
        if args.fonte_url:
            base, resp_inicial = args.fonte_url, None
        else:
            base, resp_inicial = escolher_fonte_disponivel(sessao)
        urls_zip, competencia_usada = listar_zips(sessao, base, resp_inicial, competencia=args.competencia)
        if args.filtro:
            padrao = re.compile(args.filtro, re.IGNORECASE)
            urls_zip = [u for u in urls_zip if padrao.search(u)]
        log.info("%d arquivo(s) selecionado(s)", len(urls_zip))
        baixar_lista(sessao, urls_zip, RAW_DIR)

        if competencia_usada and competencia_usada != cfg.MES_RECEITA:
            log.warning(
                "Competência usada (%s) é diferente da registrada em config.py (MES_RECEITA=%r). "
                "Atualizem config.py pra manter reprodutibilidade.",
                competencia_usada, cfg.MES_RECEITA,
            )

    membros = listar_membros_zip(RAW_DIR)
    log.info("%d arquivo(s) interno(s) encontrados (nenhum extraído pro disco)", len(membros))
    construir_inventario(membros, INVENTORY_DIR, nome_arquivo="inventario_receita_amostra.csv")

    if args.filtrar_cnpjs:
        lista_cnpjs = carregar_lista_cnpjs(args.filtrar_cnpjs)
        log.info("Filtrando contra %d raízes de CNPJ de %s",
                 len(lista_cnpjs), args.filtrar_cnpjs)
        filtrar_para_parquet(membros, lista_cnpjs, PARQUET_DIR,
                             competencia=competencia_usada)

    return 0


if __name__ == "__main__":
    sys.exit(main())