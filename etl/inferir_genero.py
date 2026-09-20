"""
Piloto de inferencia de genero pelo primeiro nome (RN-04).
=====================================================================
Entrega da T3. Classifica um nome como feminino ou masculino quando a
frequencia da categoria dominante na base de nomes do IBGE (Censo 2010)
atinge o limiar definido, e como indeterminado caso contrario.

A taxa de indeterminados NAO e falha do metodo: e o resultado que torna
o erro mensuravel. Reportar essa taxa e o que separa inferencia honesta
de chute, e ela precisa aparecer no README e no pitch.

Como funciona
-------------
Para cada nome, pega o primeiro nome utilizavel, normaliza (maiusculas,
sem acento), e consulta a API do IBGE duas vezes, uma por sexo:

    GET servicodados.ibge.gov.br/api/v2/censos/nomes/MARIA?sexo=F
    GET servicodados.ibge.gov.br/api/v2/censos/nomes/MARIA?sexo=M

Cada resposta traz a serie por decada; somando as frequencias chega-se ao
total por sexo. A proporcao dominante decide a classificacao.

Exemplos medidos em 20/09/2026:

    MARIA  11.694.738 F contra     39.391 M  -> 99,7% F  -> feminino
    JOSE       22.021 F contra  5.732.508 M  -> 99,6% M  -> masculino
    ARIEL       2.715 F contra     27.111 M  -> 90,9% M  -> no limite

Limites da fonte, que precisam estar declarados no trabalho
-----------------------------------------------------------
1. Nome composto nao funciona: "MARIA LUIZA" devolve lista vazia. So o
   primeiro nome isolado retorna dados. Por isso so o primeiro token e
   consultado.
2. Nome raro e suprimido. Abaixo de um minimo de ocorrencias o IBGE nao
   publica, e a resposta vem vazia -- indistinguivel de nome inexistente.
   Nomes estrangeiros e grafias raras caem em indeterminado.
3. A base e do Censo 2010, ou seja, retrata nomes de uma populacao nascida
   majoritariamente antes disso. Para socios de empresa, que sao adultos,
   isso e mais ajuda do que problema.
4. A acentuacao e ignorada pela API, entao normalizamos antes de consultar.

Para rodar em escala (quando a T2 entregar os socios)
-----------------------------------------------------
Bater na API nome a nome serve para o piloto, nao para centenas de milhares
de socios. Para isso existe base consolidada derivada desta mesma API:

    Brasil.IO, dataset "Genero dos Nomes"
    https://brasil.io/dataset/genero-nomes/
    https://data.brasil.io/dataset/genero-nomes/nomes.csv.gz  (~1,8 MB)

Sao cerca de 100 mil nomes com as colunas first_name, classification,
frequency_female, frequency_male, frequency_total e ratio, esta ultima ja
sendo a proporcao dominante -- basta filtrar ratio >= 0,90. A base ainda
agrupa variantes ortograficas (ANA e ANNA, LUIS e LUIZ), que a API conta
como nomes diferentes.

Licenca CC BY-SA 4.0, que e share-alike: redistribuindo a base ou derivada,
mantenham a mesma licenca. A atribuicao exigida e literal:

    "Fonte: IBGE/Censo 2010, dados tratados por Alvaro Justen/Brasil.IO"

A base e uma captura de 2018 feita sobre uma lista de nomes que eles tinham,
nao um indice completo (o IBGE nao publica indice de todos os nomes). Vai
haver nome do recorte que nao esta la. A estrategia certa e casar contra o
CSV primeiro e mandar so os que nao casaram para a API, deduplicados.

Cache
-----
Muitas pessoas compartilham o primeiro nome, entao a consulta e feita por
nome DISTINTO e guardada em disco. Rodar de novo nao repete requisicao, o
que importa porque e uma API publica e gratuita.

Uso (rodar de dentro de etl/):
    python inferir_genero.py                      # piloto sobre os fornecedores PF do PNCP
    python inferir_genero.py --limite 1000        # so os primeiros 1000 nomes
    python inferir_genero.py --limiar 0.95        # limiar mais exigente
    python inferir_genero.py --arquivo nomes.txt  # um nome por linha (socios da Receita)
"""

import argparse
import json
import sys
import threading
import time
import unicodedata
from pathlib import Path

import requests

import config

API = "https://servicodados.ibge.gov.br/api/v2/censos/nomes/"
LIMIAR_PADRAO = 0.90          # 90%, conforme a RN-04
# O IBGE so publica nomes com 20 ou mais ocorrencias no Brasil (15 na UF, 10
# no municipio). Abaixo desse piso a proporcao e ruido: 3 registros femininos
# e nenhum masculino dariam 100% e nao significam nada.
MINIMO_OCORRENCIAS = 20
INTERVALO_PADRAO = 0.25       # segundos entre requisicoes, para nao abusar
TIMEOUT = 30
MAX_TENTATIVAS = 4

# Particulas que nunca sao o primeiro nome de fato.
PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DEL", "VAN", "VON"}


def normalizar(texto: str) -> str:
    """Maiusculas, sem acento, so letras. A API ignora acentuacao."""
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
        if len(token) >= 3 and token not in PARTICULAS:
            return token
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
        self.caminho.write_text(
            json.dumps(self._dados, ensure_ascii=False, indent=1), encoding="utf-8")

    def __len__(self):
        return len(self._dados)


def frequencia(sessao, nome: str, sexo: str) -> int:
    """Soma a serie por decada de um nome num sexo. Zero se nao houver."""
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = sessao.get(API + nome, params={"sexo": sexo}, timeout=TIMEOUT)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError):
            time.sleep(2 ** tentativa)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** tentativa)
            continue
        resp.raise_for_status()
        try:
            dados = resp.json()
        except ValueError:
            # Ha um WAF na frente da API que responde HTML ("Request Rejected")
            # com status 200 quando nao gosta da URL -- acento nao normalizado
            # e o caso classico. Tratar como nome ausente escondeira o defeito.
            raise RuntimeError(
                f"nome {nome}: resposta nao e JSON (provavel bloqueio do WAF; "
                f"confira a normalizacao de acentos). Trecho: {resp.text[:80]!r}")
        if not dados:
            return 0
        return sum(p.get("frequencia", 0) for p in dados[0].get("res", []))
    raise RuntimeError(f"nome {nome} sexo {sexo}: falhou apos {MAX_TENTATIVAS} tentativas")


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
                nao alcanca o limiar. E o caso genuinamente ambiguo, como
                ARIEL (90,9% masculino).

    O denominador e sempre M+F, nunca o total da chamada sem o parametro
    sexo: a supressao do IBGE e aplicada por celula (nome x sexo x decada),
    entao o total agregado e maior que a soma dos sexos e usar ele
    subestimaria a proporcao.
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


def nomes_do_pncp(limite):
    """Fornecedores pessoa fisica do PNCP.

    Substituicao declarada: a RN-04 se aplica a socios, que vem da Receita
    Federal. Enquanto o download da Receita nao termina, o piloto roda sobre
    os fornecedores PF do PNCP, que sao nomes de pessoas reais do mesmo
    universo (contratacao publica brasileira). A taxa de indeterminados
    medida aqui e uma estimativa, nao o numero final -- ele sai quando o
    piloto rodar sobre os socios de verdade.
    """
    import duckdb
    caminho = (Path(config.DIR_DADOS_RAW) / "pncp" /
               f"contratos_{config.ANO_REFERENCIA}_completo.jsonl")
    if not caminho.is_file():
        caminho = (Path(config.DIR_DADOS_RAW) / "pncp" /
                   f"contratos_{config.ANO_REFERENCIA}.jsonl")
    if not caminho.is_file():
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
    p = argparse.ArgumentParser(description="Piloto de inferencia de genero (RN-04)")
    p.add_argument("--arquivo", default=None,
                   help="arquivo com um nome por linha (use quando a T2 entregar os socios)")
    p.add_argument("--limite", type=int, default=1000,
                   help="quantos nomes consultar (padrao: 1000; 0 = todos)")
    p.add_argument("--limiar", type=float, default=LIMIAR_PADRAO,
                   help=f"proporcao minima para classificar (padrao: {LIMIAR_PADRAO})")
    p.add_argument("--intervalo", type=float, default=INTERVALO_PADRAO,
                   help=f"segundos entre requisicoes (padrao: {INTERVALO_PADRAO})")
    p.add_argument("--saida", default="dados/genero", help="pasta de saida")
    args = p.parse_args()

    if args.arquivo:
        nomes = [l.strip() for l in Path(args.arquivo).read_text(
            encoding="utf-8").splitlines() if l.strip()]
        if args.limite:
            nomes = nomes[:args.limite]
        origem = args.arquivo
    else:
        nomes, origem = nomes_do_pncp(args.limite or None)

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    cache = Cache(Path("dados/cache/nomes_ibge.json"))

    # Um nome distinto e uma consulta, mesmo que apareca em varias pessoas.
    mapa = {}
    sem_primeiro = 0
    for nome in nomes:
        pn = primeiro_nome(nome)
        if not pn:
            sem_primeiro += 1
            continue
        mapa.setdefault(pn, []).append(nome)

    distintos = sorted(mapa)
    a_consultar = [n for n in distintos if cache.get(n) is None]

    print(f"== Piloto de genero (RN-04, limiar {args.limiar:.0%}) ==")
    print(f"   origem   : {origem}")
    print(f"   {len(nomes)} nomes, {len(distintos)} primeiros nomes distintos")
    print(f"   {sem_primeiro} sem primeiro nome utilizavel (iniciais ou so particulas)")
    print(f"   cache tem {len(cache)}; {len(a_consultar)} a consultar na API\n")

    sessao = requests.Session()
    inicio = time.time()
    for i, nome in enumerate(a_consultar, 1):
        if i > 1:
            time.sleep(args.intervalo)
        f = frequencia(sessao, nome, "F")
        time.sleep(args.intervalo)
        m = frequencia(sessao, nome, "M")
        cache.put(nome, {"f": f, "m": m})
        if i % 50 == 0 or i == len(a_consultar):
            print(f"   {i}/{len(a_consultar)} consultados "
                  f"({(time.time()-inicio)/60:.1f} min)", flush=True)
    cache.salvar()

    # --- classificacao ---
    linhas = []
    contagem = {"feminino": 0, "masculino": 0, "indeterminado": 0}
    motivos = {"ausente": 0, "instavel": 0, "ambiguo": 0}
    for pn in distintos:
        d = cache.get(pn) or {"f": 0, "m": 0}
        classe, conf, motivo = classificar(d["f"], d["m"], args.limiar)
        contagem[classe] += len(mapa[pn])
        if classe == "indeterminado":
            motivos[motivo] += len(mapa[pn])
        for completo in mapa[pn]:
            linhas.append((completo, pn, d["f"], d["m"], classe, round(conf, 4), motivo))

    total = sum(contagem.values())
    csv = destino / "piloto_genero.csv"
    with open(csv, "w", encoding="utf-8", newline="") as fh:
        fh.write("nome_completo,primeiro_nome,freq_f,freq_m,classificacao,confianca\n")
        for l in linhas:
            nome_escapado = '"' + str(l[0]).replace('"', '""') + '"'
            fh.write(f"{nome_escapado},{l[1]},{l[2]},{l[3]},{l[4]},{l[5]}\n")

    print(f"\n== Resultado sobre {total} nomes ==")
    for classe in ("feminino", "masculino", "indeterminado"):
        n = contagem[classe]
        print(f"   {classe:15} {n:>6} ({100*n/total:>5.1f}%)")
    ind = contagem["indeterminado"]
    if ind:
        print(f"\n   dos indeterminados, por causa:")
        rotulos = {
            "ausente": "ausente da base (IBGE suprime < 20 no pais)",
            "instavel": f"frequencia total abaixo de {MINIMO_OCORRENCIAS}",
            "ambiguo": "ambiguo de fato (abaixo do limiar)",
        }
        for motivo, rot in rotulos.items():
            n = motivos[motivo]
            print(f"     {rot:44} {n:>5} ({100*n/total:>4.1f}%)")

    print(f"\n   TAXA DE INDETERMINADOS: {100*ind/total:.1f}%")
    print(f"   (este e o numero que vai no README e no pitch)")
    print(f"\n   detalhamento em {csv}")

    print(f"\n== Sensibilidade ao limiar ==")
    for lim in (0.80, 0.90, 0.95, 0.99):
        c = {"feminino": 0, "masculino": 0, "indeterminado": 0}
        for pn in distintos:
            d = cache.get(pn) or {"f": 0, "m": 0}
            c[classificar(d["f"], d["m"], lim)[0]] += len(mapa[pn])
        marca = "  <- adotado" if abs(lim - args.limiar) < 1e-9 else ""
        print(f"   limiar {lim:.0%}: {100*c['indeterminado']/total:>5.1f}% "
              f"indeterminados{marca}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
