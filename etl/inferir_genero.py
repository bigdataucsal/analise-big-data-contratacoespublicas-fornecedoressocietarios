"""Inferencia de genero pelo primeiro nome (RN-04)."""

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
LIMIAR_PADRAO = 0.90
MINIMO_OCORRENCIAS = 20
INTERVALO_PADRAO = 0.25
TIMEOUT = 30
MAX_TENTATIVAS = 4
BASE = Path(__file__).resolve().parent
LINHAS_SOCIOS = 200_000

PARTICULAS = {"DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DEL", "VAN", "VON"}


def normalizar(texto: str) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.upper() if c.isalpha() or c.isspace()).strip()


def primeiro_nome(nome_completo: str) -> str:
    for token in normalizar(nome_completo).split():
        if token in PARTICULAS:
            continue
        return token if len(token) >= 3 else ""
    return ""


class Cache:

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
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = sessao.get(API + nome, params={"tipo": "nome", "localidade": 0},
                              timeout=TIMEOUT)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError):
            time.sleep(2 ** tentativa)
            continue
        if resp.status_code == 404:
            return 0, 0
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(2 ** tentativa)
            continue
        resp.raise_for_status()
        try:
            dados = resp.json()
        except ValueError:
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
