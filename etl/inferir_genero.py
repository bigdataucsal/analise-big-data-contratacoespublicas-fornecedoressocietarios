"""
Inferencia de genero pelo primeiro nome (RN-04), com o Censo 2022 do IBGE.
=====================================================================
Entrega da T3. Classifica um nome como feminino ou masculino quando a
frequencia da categoria dominante na base de nomes do IBGE (Censo 2022)
atinge o limiar definido, e como indeterminado caso contrario.

A taxa de indeterminados NAO e falha do metodo: e o resultado que torna
o erro mensuravel. Reportar essa taxa e o que separa inferencia honesta
de chute, e ela precisa aparecer no README e no pitch.

Como funciona
-------------
Para cada primeiro nome DISTINTO, normaliza (maiusculas, sem acento) e faz
uma unica chamada, que ja devolve os dois sexos:

    GET https://servicodados.ibge.gov.br/api/v3/nomes/2022/nome/vanessa
        ?tipo=nome&localidade=0        (localidade 0 = Brasil)

    campos usados: "mulheres" e "homens"

A proporcao dominante decide a classificacao. Exemplo capturado em
29/09/2026 (o "frequencia" da resposta e a soma dos dois sexos):

    VANESSA  396.406 F contra 1.468 M  -> 99,6% F  -> feminino

Origem do endereco
------------------
O endereco v3 foi capturado pelo DevTools do navegador no site Nomes no
Brasil (censo2022.ibge.gov.br/nomes), em 29/09/2026. NAO confirmei que ele
conste da documentacao publica da API. Por isso: (1) cada resposta fica em
cache em disco, que e o dado bruto do projeto e nao vai para o git; (2)
registrem no README a data de acesso e o endereco usado.

Limites da fonte, que precisam estar declarados no trabalho
-----------------------------------------------------------
1. So o primeiro nome. Segundo a nota tecnica 01/2025 do IBGE, do campo
   "nome" so o primeiro nome informado e divulgado. Por isso so o primeiro
   token e consultado.
2. Nome raro e suprimido: so aparecem nomes com 20 ou mais ocorrencias no
   Brasil (15 por UF, 10 por municipio). Nomes estrangeiros e grafias raras
   caem em indeterminado.
3. Variantes de grafia contam separadas (ANA e ANNA, LUIS e LUIZ). Cada
   variante tem a sua propria proporcao entre os sexos, e e ela que se usa.
4. Acentos nao existem na base; normalizamos antes de consultar.
5. O sexo e o informado no momento da coleta do Censo, em 1 de agosto de 2022.

Privacidade (RN-09)
-------------------
O nome completo de socio nunca e gravado. O cache guarda so o primeiro nome
com as duas frequencias, e o CSV de saida e agregado por primeiro nome
(sem sobrenome e sem documento).

Cache
-----
Muitas pessoas compartilham o primeiro nome, entao a consulta e feita por
nome DISTINTO e guardada em disco (dados/cache/nomes_ibge_2022.json). Rodar
de novo nao repete requisicao, o que importa porque e uma API publica.

Uso (rodar de dentro de etl/):
    python inferir_genero.py                       # 1.000 socios PF de Socios1.zip
    python inferir_genero.py --limite 200          # teste rapido
    python inferir_genero.py --limite 0            # todos os PF das linhas lidas
    python inferir_genero.py --limiar 0.95         # limiar mais exigente
    python inferir_genero.py --fonte pncp          # fornecedores PF do PNCP
    python inferir_genero.py --arquivo nomes.txt   # um nome por linha
"""

import argparse
import csv
import io
import json
import random
import sys
import threading
import time
import unicodedata
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import requests

import config

API = "https://servicodados.ibge.gov.br/api/v3/nomes/2022/nome/"
LIMIAR_PADRAO = 0.90          # 90%, conforme a RN-04
# O IBGE so publica nomes com 20 ou mais ocorrencias no Brasil (15 na UF, 10
# no municipio). Abaixo desse piso a proporcao e ruido: 3 registros femininos
# e nenhum masculino dariam 100% e nao significam nada.
MINIMO_OCORRENCIAS = 20
INTERVALO_PADRAO = 0.25       # segundos entre requisicoes, para nao abusar
TIMEOUT = 30
MAX_TENTATIVAS = 4
BASE = Path(__file__).resolve().parent                # .../etl
LINHAS_SOCIOS = 200_000                               # como no medir_pendencias.py

# Particulas que nunca sao o primeiro nome de fato.
PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DEL", "VAN", "VON"}


def normalizar(texto: str) -> str:
    """Maiusculas, sem acento, so letras. A base nao tem sinais diacriticos."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.upper() if c.isalpha() or c.isspace()).strip()


def primeiro_nome(nome_completo: str) -> str:
    """O primeiro token utilizavel.

    Pula particulas e iniciais abreviadas: "J. C. SILVA" nao tem primeiro
    nome consultavel, e "DE SOUZA MARIA" comeca numa particula.
    """
    for token in normalizar(nome_completo).split():
        if token in PARTICULAS:
            continue
        # Primeiro token que nao e particula: se for so uma inicial, nao ha
        # primeiro nome consultavel (pegar o token seguinte seria pegar o
        # sobrenome e classificar "J C SANTOS" como se SANTOS fosse um nome).
        return token if len(token) >= 3 else ""
    return ""


class Cache:
    """Resultados por nome distinto, persistidos em disco."""

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self._lock = threading.Lock()
        self._dados = {}
        if caminho.exists():
            try:
                self._dados = json.loads(caminho.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                print(f"AVISO: {caminho.name} ilegivel, recomecando o cache")

    def get(self, nome):
        return self._dados.get(nome)

    def put(self, nome, valor):
        with self._lock:
            self._dados[nome] = valor

    def salvar(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.caminho.write_text(
                json.dumps(self._dados, ensure_ascii=False, indent=1), encoding="utf-8")

    def __len__(self):
        return len(self._dados)


def frequencia(sessao, nome: str):
    """(feminino, masculino) do Censo 2022 para um primeiro nome. (0, 0) se ausente."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = sessao.get(API + nome, params={"tipo": "nome", "localidade": 0},
                              timeout=TIMEOUT)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError):
            time.sleep(2 ** tentativa)
            continue
        if resp.status_code == 404:                  # nome ausente da base
            return 0, 0
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** tentativa)
            continue
        resp.raise_for_status()
        try:
            dados = resp.json()
        except ValueError:
            # Se algum WAF responder HTML com status 200, tratar como nome
            # ausente esconderia o defeito. Falha alto.
            raise RuntimeError(
                f"nome {nome}: resposta nao e JSON (provavel bloqueio; confira "
                f"a normalizacao de acentos). Trecho: {resp.text[:80]!r}")
        if isinstance(dados, list):
            dados = dados[0] if dados else {}
        if not isinstance(dados, dict):
            return 0, 0
        return int(dados.get("mulheres") or 0), int(dados.get("homens") or 0)
    raise RuntimeError(f"nome {nome}: falhou apos {MAX_TENTATIVAS} tentativas")


def classificar(freq_f: int, freq_m: int, limiar: float, minimo: int = MINIMO_OCORRENCIAS):
    """Devolve (classe, confianca, motivo).

    Tres caminhos para indeterminado, e vale distingui-los no relatorio
    porque tem causas diferentes:

    ausente  -- o nome nao aparece na base. O IBGE suprime nomes com menos
                de 20 ocorrencias no Brasil, entao "ausente" nao quer dizer
                que ninguem se chama assim, e sim que sao poucos. Nomes
                estrangeiros e grafias raras caem aqui.
    instavel -- o nome aparece, mas com frequencia total baixa demais para
                a proporcao significar alguma coisa. Um nome com 3 registros
                femininos e nenhum masculino da 100%, e isso e ruido.
    ambiguo  -- o nome aparece com frequencia boa, mas a proporcao dominante
                nao alcanca o limiar. E o caso genuinamente ambiguo.

    O denominador e sempre M+F, e nao o "frequencia" total da resposta: a
    supressao do IBGE e aplicada por celula, entao usar so a soma dos sexos
    mantem a proporcao coerente.
    """
    total = freq_f + freq_m
    if total == 0:
        return "indeterminado", 0.0, "ausente"
    if total < minimo:
        return "indeterminado", max(freq_f, freq_m) / total, "instavel"
    p_f = freq_f / total
    if p_f >= limiar:
        return "feminino", p_f, "classificado"
    if (1 - p_f) >= limiar:
        return "masculino", 1 - p_f, "classificado"
    return "indeterminado", max(p_f, 1 - p_f), "ambiguo"


def nomes_socios_pf(limite, semente):
    """Socios pessoa fisica de Socios1.zip (as primeiras linhas), sorteados.

    Este e o universo certo da RN-04. As colunas da Receita, por posicao:
    0 cnpj_basico, 1 identificador_de_socio (2 = PF), 2 nome_do_socio.
    E amostra sequencial, nao aleatoria: o relatorio precisa dizer isso.
    """
    zip_path = Path(config.DIR_DADOS_RAW) / "receita" / "Socios1.zip"
    if not zip_path.is_file():
        raise SystemExit(f"ERRO: {zip_path} nao existe. Confira o DIR_DADOS_RAW no .env.")
    nomes = []
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(zf.namelist()[0]) as bruto:
            texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
            for i, linha in enumerate(csv.reader(texto, delimiter=";", quotechar='"')):
                if i >= LINHAS_SOCIOS:
                    break
                if len(linha) > 2 and linha[1] == "2" and linha[2].strip():
                    nomes.append(linha[2])
    if limite:
        nomes = random.Random(semente).sample(nomes, min(limite, len(nomes)))
    return nomes, (f"socios PF de Socios1.zip (ate {LINHAS_SOCIOS:,} primeiras linhas"
                   f"{f', sorteio de {limite} com semente {semente}' if limite else ''})")


def nomes_do_pncp(limite):
    """Fornecedores pessoa fisica do PNCP (alternativa ao universo de socios)."""
    import duckdb
    caminho = (Path(config.DIR_DADOS_RAW) / "pncp" /
               f"contratos_{config.ANO_REFERENCIA}_completo.jsonl")
    if not caminho.is_file() or caminho.stat().st_size == 0:
        raise SystemExit("ERRO: nenhum JSONL do PNCP encontrado. "
                         "Rode antes: python baixar_pncp_rapido.py")
    con = duckdb.connect()
    sql = f"""
        SELECT DISTINCT nomeRazaoSocialFornecedor
        FROM read_json('{str(caminho).replace(chr(92), '/')}',
                       format='newline_delimited', union_by_name=true, sample_size=-1)
        WHERE tipoPessoa = 'PF' AND trim(nomeRazaoSocialFornecedor) <> ''
        ORDER BY 1
    """
    if limite:
        sql += f" LIMIT {limite}"
    return [r[0] for r in con.sql(sql).fetchall()], f"fornecedores PF do PNCP ({caminho.name})"


def main() -> int:
    p = argparse.ArgumentParser(description="Inferencia de genero com o Censo 2022 (RN-04)")
    p.add_argument("--fonte", choices=["socios", "pncp"], default="socios",
                   help="de onde vem os nomes (padrao: socios PF da Receita)")
    p.add_argument("--arquivo", default=None, help="um nome por linha; ignora --fonte")
    p.add_argument("--limite", type=int, default=1000,
                   help="quantos nomes usar (padrao: 1000; 0 = todos)")
    p.add_argument("--semente", type=int, default=42, help="semente do sorteio de socios")
    p.add_argument("--limiar", type=float, default=LIMIAR_PADRAO,
                   help=f"proporcao minima para classificar (padrao: {LIMIAR_PADRAO})")
    p.add_argument("--intervalo", type=float, default=INTERVALO_PADRAO,
                   help=f"segundos entre requisicoes (padrao: {INTERVALO_PADRAO})")
    p.add_argument("--saida", default=str(BASE / "dados" / "genero"), help="pasta de saida")
    args = p.parse_args()

    if args.arquivo:
        nomes = [l.strip() for l in Path(args.arquivo).read_text(
            encoding="utf-8").splitlines() if l.strip()]
        if args.limite:
            nomes = nomes[:args.limite]
        origem = args.arquivo
    elif args.fonte == "pncp":
        nomes, origem = nomes_do_pncp(args.limite or None)
    else:
        nomes, origem = nomes_socios_pf(args.limite, args.semente)

    # Um primeiro nome distinto e uma consulta, mesmo que apareca em varias pessoas.
    contagem, sem_primeiro = Counter(), 0
    for nome in nomes:
        pn = primeiro_nome(nome)
        if pn:
            contagem[pn] += 1
        else:
            sem_primeiro += 1
    distintos = sorted(contagem)

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    cache = Cache(BASE / "dados" / "cache" / "nomes_ibge_2022.json")
    a_consultar = [n for n in distintos if cache.get(n) is None]

    print(f"== Inferencia de genero (RN-04, Censo 2022, limiar {args.limiar:.0%}) ==")
    print(f"   origem   : {origem}")
    print(f"   {len(nomes)} nomes, {len(distintos)} primeiros nomes distintos")
    print(f"   {sem_primeiro} sem primeiro nome utilizavel (iniciais ou so particulas)")
    print(f"   cache tem {len(cache)}; {len(a_consultar)} a consultar na API\n")

    sessao = requests.Session()
    inicio = time.time()
    for i, nome in enumerate(a_consultar, 1):
        if i > 1:
            time.sleep(args.intervalo)
        f, m = frequencia(sessao, nome)
        cache.put(nome, {"f": f, "m": m, "consultado_em": date.today().isoformat()})
        if i % 50 == 0 or i == len(a_consultar):
            cache.salvar()
            print(f"   {i}/{len(a_consultar)} consultados "
                  f"({(time.time()-inicio)/60:.1f} min)", flush=True)
    cache.salvar()

    # --- classificacao ---
    total = sum(contagem.values())
    if total == 0:
        print("ERRO: nenhum nome utilizavel.")
        return 1
    classes = {"feminino": 0, "masculino": 0, "indeterminado": 0}
    motivos = {"ausente": 0, "instavel": 0, "ambiguo": 0}
    linhas = []
    for pn in distintos:
        d = cache.get(pn) or {"f": 0, "m": 0}
        classe, conf, motivo = classificar(d["f"], d["m"], args.limiar)
        classes[classe] += contagem[pn]
        if classe == "indeterminado":
            motivos[motivo] += contagem[pn]
        linhas.append((pn, contagem[pn], d["f"], d["m"], classe, round(conf, 4), motivo))

    csv_saida = destino / "genero_por_primeiro_nome.csv"
    with open(csv_saida, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["primeiro_nome", "ocorrencias_na_amostra", "freq_f", "freq_m",
                    "classificacao", "confianca", "motivo"])
        w.writerows(sorted(linhas, key=lambda l: -l[1]))

    print(f"\n== Resultado sobre {total} nomes (AMOSTRA) ==")
    for classe in ("feminino", "masculino", "indeterminado"):
        n = classes[classe]
        print(f"   {classe:15} {n:>6} ({100*n/total:>5.1f}%)")
    ind = classes["indeterminado"]
    if ind:
        print("\n   dos indeterminados, por causa:")
        rotulos = {
            "ausente": "ausente da base (IBGE suprime < 20 no pais)",
            "instavel": f"frequencia total abaixo de {MINIMO_OCORRENCIAS}",
            "ambiguo": "ambiguo de fato (abaixo do limiar)",
        }
        for motivo, rot in rotulos.items():
            n = motivos[motivo]
            print(f"     {rot:44} {n:>5} ({100*n/total:>4.1f}%)")

    print(f"\n   TAXA DE INDETERMINADOS: {100*ind/total:.1f}%")
    print("   (este e o numero que vai no README e no pitch; e de AMOSTRA)")
    print(f"\n   detalhe por primeiro nome em {csv_saida}")
    print("   (sem sobrenome e sem documento)")

    print("\n== Sensibilidade ao limiar ==")
    for lim in (0.80, 0.90, 0.95, 0.99):
        indet = 0
        for pn in distintos:
            d = cache.get(pn) or {"f": 0, "m": 0}
            if classificar(d["f"], d["m"], lim)[0] == "indeterminado":
                indet += contagem[pn]
        marca = "  <- adotado" if abs(lim - args.limiar) < 1e-9 else ""
        print(f"   limiar {lim:.0%}: {100*indet/total:>5.1f}% indeterminados{marca}")

    print(f"\n   custo em escala: {len(distintos)} primeiros nomes distintos nesta amostra; "
          "a base inteira consulta so os distintos que faltarem no cache.")
    return 0


if __name__ == "__main__":
    sys.exit(main())