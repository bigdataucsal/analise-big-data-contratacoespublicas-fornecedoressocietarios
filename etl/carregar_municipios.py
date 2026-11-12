"""
Carga de dim_municipio no Aiven, a partir do CSV que o baixar_proxy_racial.py
ja gera (etl/dados/proxy/cor_raca_municipio_2022.csv). Este script NAO baixa
o Censo: a coleta e o baixar_proxy_racial.py, que e a fonte unica.

O que faz: le o CSV, ajusta os nomes das colunas para o dim_municipio, deriva a
UF dos dois primeiros digitos do codigo IBGE e carrega com COPY + upsert. Pode
ser rodado de novo sem duplicar. O dado descreve o TERRITORIO, nunca uma pessoa
(RN-06 e RN-09).

Uso (de dentro de etl/):
    python carregar_municipios.py --simular
    python carregar_municipios.py
    python carregar_municipios.py --completar-localidades
    python carregar_municipios.py --csv outro_caminho.csv
"""
import argparse
import io
import os
import sys
import time
from pathlib import Path

import pandas as pd

import config   # tambem carrega o etl/.env

CSV_PADRAO = Path(config.DIR_DADOS_PARQUET).parent / "proxy" / "cor_raca_municipio_2022.csv"
URL_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"

ORIGEM_PARA_DIM = {"total": "pop_total", "branca": "pop_branca", "preta": "pop_preta",
                   "parda": "pop_parda", "amarela": "pop_amarela", "indigena": "pop_indigena"}
COLS_POP = list(ORIGEM_PARA_DIM.values())
COLUNAS = ["codigo_ibge", "nome", "uf_sigla"] + COLS_POP + ["pct_negra"]

UF_POR_CODIGO = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}


def ler(csv: Path) -> pd.DataFrame:
    if not csv.is_file():
        raise SystemExit(f"ERRO: {csv} nao existe. Rodem antes: python baixar_proxy_racial.py")
    bruto = pd.read_csv(csv, dtype={"codigo_ibge": str})
    esperadas = ["codigo_ibge", "municipio", "pct_negra"] + list(ORIGEM_PARA_DIM)
    faltam = [c for c in esperadas if c not in bruto.columns]
    if faltam:
        raise SystemExit(f"ERRO: faltam colunas no CSV: {faltam}\n"
                         f"       Colunas encontradas: {list(bruto.columns)}")

    codigo = bruto["codigo_ibge"].astype(str).str.strip()
    nome_bruto = bruto["municipio"].astype(str)
    uf = codigo.str[:2].map(UF_POR_CODIGO)
    if uf.isna().any():
        raise SystemExit("ERRO: codigo IBGE com UF desconhecida: "
                         + ", ".join(codigo[uf.isna()].head(5)))
    if codigo.duplicated().any():
        raise SystemExit("ERRO: ha codigo_ibge repetido no CSV.")
    sufixo = nome_bruto.str.extract(r"\s-\s([A-Z]{2})\s*$")[0]
    divergentes = int((sufixo.notna() & (sufixo != uf)).sum())
    if divergentes:
        print(f"   AVISO: {divergentes} municipio(s) com UF do nome diferente da UF do codigo.")

    df = pd.DataFrame({
        "codigo_ibge": codigo,
        "nome": nome_bruto.str.replace(r"\s-\s[A-Z]{2}\s*$", "", regex=True).str.strip(),
        "uf_sigla": uf,
    })
    for origem, destino in ORIGEM_PARA_DIM.items():
        df[destino] = pd.to_numeric(bruto[origem], errors="coerce").astype("Int64")
    df["pct_negra"] = pd.to_numeric(bruto["pct_negra"], errors="coerce").round(3)
    fora = df["pct_negra"].dropna()
    if ((fora < 0) | (fora > 100)).any():
        raise SystemExit("ERRO: pct_negra fora do intervalo 0 a 100.")
    return df[COLUNAS]


def completar_localidades(df: pd.DataFrame) -> pd.DataFrame:
    import requests
    resp = requests.get(URL_LOCALIDADES, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    existentes = set(df["codigo_ibge"])
    novos = [{"codigo_ibge": str(m["id"]), "nome": m["nome"].strip(),
              "uf_sigla": UF_POR_CODIGO.get(str(m["id"])[:2])}
             for m in resp.json() if str(m["id"]) not in existentes]
    print(f"-- completando com a lista de localidades do IBGE: {len(novos)} municipio(s) a mais")
    for n in novos:
        print(f"   {n['codigo_ibge']} {n['nome']} ({n['uf_sigla']}) entra com populacao nula")
    if not novos:
        return df
    extra = pd.DataFrame(novos).reindex(columns=COLUNAS)
    df = pd.concat([df, extra], ignore_index=True)
    for c in COLS_POP:
        df[c] = df[c].astype("Int64")
    df["pct_negra"] = pd.to_numeric(df["pct_negra"], errors="coerce")
    return df


def resumo(df: pd.DataFrame) -> None:
    com_censo = int(df["pop_total"].notna().sum())
    pop = float(df["pop_total"].sum())
    negra = float(df["pop_preta"].sum() + df["pop_parda"].sum())
    print("\n== Resumo de dim_municipio ==")
    print("   exemplos:", "; ".join(f"{r.codigo_ibge} {r.nome} ({r.uf_sigla})"
                                    for r in df.head(3).itertuples()))
    print(f"   municipios: {len(df):,} | com dado do Censo: {com_censo:,} | "
          f"sem dado: {len(df) - com_censo:,}")
    print(f"   populacao somada: {pop:,.0f} (o Censo 2022 contou 203.080.756)")
    print(f"   % preta + parda no pais: {negra / pop * 100:.1f}%  (conferir: cerca de 55,5%)")
    print(f"   pct_negra: minimo {df['pct_negra'].min():.1f}, mediana {df['pct_negra'].median():.1f}, "
          f"maximo {df['pct_negra'].max():.1f}")


def carregar(uri: str, df: pd.DataFrame) -> int:
    import psycopg
    inicio = time.time()
    with psycopg.connect(uri, autocommit=False) as con:
        with con.cursor() as cur:
            if cur.execute("SHOW default_transaction_read_only").fetchone()[0] == "on":
                raise SystemExit("ERRO: o banco esta em somente leitura (disco cheio?).")
            if cur.execute("SELECT to_regclass('dim_municipio')").fetchone()[0] is None:
                raise SystemExit("ERRO: dim_municipio nao existe. Rodem antes: python aplicar_schema.py")
            cur.execute("""CREATE TEMP TABLE stg_municipio (
                codigo_ibge TEXT, nome TEXT, uf_sigla TEXT,
                pop_total INTEGER, pop_branca INTEGER, pop_preta INTEGER,
                pop_parda INTEGER, pop_amarela INTEGER, pop_indigena INTEGER,
                pct_negra NUMERIC(6,3)) ON COMMIT DROP""")
            buf = io.StringIO()
            df[COLUNAS].to_csv(buf, index=False, header=False, na_rep="")
            with cur.copy(f"COPY stg_municipio ({', '.join(COLUNAS)}) "
                          f"FROM STDIN WITH (FORMAT CSV, NULL '')") as c:
                c.write(buf.getvalue())
            cur.execute("""
                INSERT INTO dim_municipio (codigo_ibge, nome, uf_sigla, pop_total, pop_branca,
                    pop_preta, pop_parda, pop_amarela, pop_indigena, pct_negra)
                SELECT codigo_ibge, nome, uf_sigla, pop_total, pop_branca,
                       pop_preta, pop_parda, pop_amarela, pop_indigena, pct_negra
                FROM stg_municipio
                ON CONFLICT (codigo_ibge) DO UPDATE SET
                    nome = EXCLUDED.nome, uf_sigla = EXCLUDED.uf_sigla,
                    pop_total = EXCLUDED.pop_total, pop_branca = EXCLUDED.pop_branca,
                    pop_preta = EXCLUDED.pop_preta, pop_parda = EXCLUDED.pop_parda,
                    pop_amarela = EXCLUDED.pop_amarela, pop_indigena = EXCLUDED.pop_indigena,
                    pct_negra = EXCLUDED.pct_negra""")
            con.commit()

            print("\n== Conferencia (para docs/evidencias) ==")
            n, com, soma = cur.execute(
                "SELECT count(*), count(pop_total), sum(pop_total) FROM dim_municipio").fetchone()
            print(f"   dim_municipio: {n:,} linhas, {com:,} com dado do Censo, populacao {soma:,}")
            mb = cur.execute("SELECT pg_total_relation_size('dim_municipio') / 1e6").fetchone()[0]
            print(f"   tamanho: {float(mb):.2f} MB")
    print(f"\n== Concluido em {time.time() - inicio:.1f}s ==")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Carrega dim_municipio a partir do CSV do baixar_proxy_racial.py")
    p.add_argument("--csv", default=str(CSV_PADRAO), help=f"CSV de entrada (padrao: {CSV_PADRAO})")
    p.add_argument("--completar-localidades", action="store_true",
                   help="acrescenta os municipios da lista do IBGE que faltam no CSV, com populacao nula")
    p.add_argument("--simular", action="store_true", help="nao conecta no banco")
    p.add_argument("--uri", default=None)
    a = p.parse_args()

    df = ler(Path(a.csv))
    if a.completar_localidades:
        df = completar_localidades(df)
    resumo(df)
    if a.simular:
        return 0

    uri = a.uri or os.environ.get("AIVEN_PG_URI")
    if not uri:
        print("ERRO: defina AIVEN_PG_URI no etl/.env (ou passe --uri).")
        return 1
    if "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"
    return carregar(uri, df)


if __name__ == "__main__":
    sys.exit(main())