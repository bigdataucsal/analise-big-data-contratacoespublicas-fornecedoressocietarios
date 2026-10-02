"""
Teste comparativo que sustenta a escolha do banco.
=====================================================================
Entrega da T3, semana 3. Roda a MESMA consulta analitica em duas
abordagens e cronometra as duas, para que a escolha do modelo seja
evidencia e nao preferencia.

A consulta escolhida e a do KPI interseccional, que e a mais pesada do
painel e a que melhor representa a carga real: junta o fato com a
dimensao de fornecedor e com a de municipio, agrupa por faixa de
composicao racial do territorio e por faixa de valor, e calcula soma,
contagem e mediana. Tres juncoes e uma agregacao com mediana -- e
exatamente o formato que o modelo estrela existe para responder.

As duas abordagens comparadas:

    1. Arquivos soltos lidos com pandas. E o que o grupo ja tinha
       instalado no comeco do projeto, e representa "nao usar banco".
    2. Motor analitico colunar (DuckDB) sobre Parquet. Representa a
       camada analitica do projeto.

O que este teste NAO mede
-------------------------
O tempo do PostgreSQL. Nao ha instancia local nem Docker nesta maquina,
e medir contra o Aiven exigiria a credencial. Esse numero e a entrega da
T1, e o lugar dele esta reservado no documento docs/escolha-do-banco.md.

Sem ele, o que este teste sustenta e a parte do argumento sobre formato e
motor de execucao. A parte sobre relacional versus nao relacional se
sustenta no modelo de dados, nao em cronometro -- e isso esta argumentado
no documento.

Uso (rodar de dentro de etl/):
    python benchmark_banco.py
    python benchmark_banco.py --repeticoes 7
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

import duckdb

PARQUET = "dados/parquet/contratos/**/*.parquet"
CSV_MUNICIPIOS = "dados/proxy/cor_raca_municipio_2022.csv"
DIR_BENCH = Path("dados/benchmark")


def preparar(con, escala: int = 1):
    """Materializa fato e dimensoes nos dois formatos, a partir do tratado.

    A mesma informacao vira CSV (para o pandas ler como arquivo solto) e
    Parquet (para o motor colunar). Comparar leitura de CSV com leitura de
    Parquet e parte legitima do teste: o formato E uma das decisoes.
    """
    DIR_BENCH.mkdir(parents=True, exist_ok=True)

    con.execute(f"""
        CREATE OR REPLACE VIEW tratado AS
        SELECT * FROM '{PARQUET}'
    """)
    con.execute(f"""
        CREATE OR REPLACE VIEW municipios AS
        SELECT codigo_ibge, municipio, uf_sigla_ignorado, pct_negra FROM (
            SELECT codigo_ibge, municipio, NULL AS uf_sigla_ignorado, pct_negra
            FROM read_csv('{CSV_MUNICIPIOS}', header=true, sample_size=-1)
        )
    """)

    # Fato enxuto: so as colunas que a consulta usa.
    #
    # A escala replica o fato para aproximar o tamanho real do recorte. Aos
    # 58 mil contratos de janeiro os dois caminhos cabem inteiros na memoria
    # e a diferenca fica pequena -- o que interessa medir e o comportamento
    # quando o volume cresce, porque e esse o cenario do projeto (2.023.236
    # contratos no ano). A replicacao muda a chave para nao colapsar as
    # juncoes, mantendo a cardinalidade do agrupamento.
    con.execute(f"""
        COPY (
            SELECT numero_controle_pncp || '-' || r.i AS numero_controle_pncp,
                   codigo_ibge, cnpj_raiz_fornecedor, valor_global, ano_contrato
            FROM tratado, range({escala}) AS r(i)
            WHERE valor_global > 0 AND valor_global <= 1e9   -- corte de sanidade
        ) TO '{DIR_BENCH}/fato.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.execute(f"""
        COPY (SELECT * FROM '{DIR_BENCH}/fato.parquet')
        TO '{DIR_BENCH}/fato.csv' (FORMAT CSV, HEADER)
    """)
    con.execute(f"""
        COPY (
            SELECT DISTINCT cnpj_raiz_fornecedor, any_value(nome_fornecedor) AS nome,
                   any_value(tipo_pessoa) AS tipo_pessoa
            FROM tratado WHERE cnpj_raiz_fornecedor IS NOT NULL
            GROUP BY cnpj_raiz_fornecedor
        ) TO '{DIR_BENCH}/dim_fornecedor.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.execute(f"""
        COPY (SELECT * FROM '{DIR_BENCH}/dim_fornecedor.parquet')
        TO '{DIR_BENCH}/dim_fornecedor.csv' (FORMAT CSV, HEADER)
    """)
    con.execute(f"""
        COPY (SELECT codigo_ibge, municipio, pct_negra
              FROM read_csv('{CSV_MUNICIPIOS}', header=true, sample_size=-1))
        TO '{DIR_BENCH}/dim_municipio.parquet' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.execute(f"""
        COPY (SELECT * FROM '{DIR_BENCH}/dim_municipio.parquet')
        TO '{DIR_BENCH}/dim_municipio.csv' (FORMAT CSV, HEADER)
    """)

    tamanhos = {}
    for nome in ("fato", "dim_fornecedor", "dim_municipio"):
        tamanhos[nome] = {
            "csv": (DIR_BENCH / f"{nome}.csv").stat().st_size,
            "parquet": (DIR_BENCH / f"{nome}.parquet").stat().st_size,
        }
    return tamanhos


CONSULTA_SQL = f"""
    SELECT
        CASE WHEN m.pct_negra >= 70 THEN 'alta'
             WHEN m.pct_negra >= 40 THEN 'media'
             ELSE 'baixa' END                         AS faixa_pct_negra,
        CASE WHEN f.valor_global >= 1000000 THEN 'acima de 1 mi'
             WHEN f.valor_global >= 100000  THEN '100 mil a 1 mi'
             WHEN f.valor_global >= 10000   THEN '10 mil a 100 mil'
             ELSE 'ate 10 mil' END                    AS faixa_valor,
        d.tipo_pessoa,
        count(*)                                      AS contratos,
        sum(f.valor_global)                           AS valor_total,
        median(f.valor_global)                        AS valor_mediano
    FROM '{DIR_BENCH}/fato.parquet' f
    JOIN '{DIR_BENCH}/dim_fornecedor.parquet' d
      ON d.cnpj_raiz_fornecedor = f.cnpj_raiz_fornecedor
    JOIN '{DIR_BENCH}/dim_municipio.parquet' m
      ON m.codigo_ibge = f.codigo_ibge
    GROUP BY 1, 2, 3
    ORDER BY valor_total DESC
"""


def rodar_duckdb(con):
    t = time.perf_counter()
    linhas = con.sql(CONSULTA_SQL).fetchall()
    return time.perf_counter() - t, len(linhas)


def rodar_pandas():
    import pandas as pd
    t = time.perf_counter()
    fato = pd.read_csv(DIR_BENCH / "fato.csv", dtype={"codigo_ibge": str,
                                                      "cnpj_raiz_fornecedor": str})
    dim_f = pd.read_csv(DIR_BENCH / "dim_fornecedor.csv",
                        dtype={"cnpj_raiz_fornecedor": str})
    dim_m = pd.read_csv(DIR_BENCH / "dim_municipio.csv", dtype={"codigo_ibge": str})

    df = fato.merge(dim_f, on="cnpj_raiz_fornecedor", how="inner")
    df = df.merge(dim_m, on="codigo_ibge", how="inner")

    df["faixa_pct_negra"] = pd.cut(df["pct_negra"], bins=[-1, 40, 70, 101], right=False,
                                   labels=["baixa", "media", "alta"])
    df["faixa_valor"] = pd.cut(df["valor_global"],
                               bins=[-1, 10000, 100000, 1000000, float("inf")], right=False,
                               labels=["ate 10 mil", "10 mil a 100 mil",
                                       "100 mil a 1 mi", "acima de 1 mi"])
    r = (df.groupby(["faixa_pct_negra", "faixa_valor", "tipo_pessoa"],
                    observed=True)["valor_global"]
           .agg(contratos="count", valor_total="sum", valor_mediano="median")
           .reset_index()
           .sort_values("valor_total", ascending=False))
    return time.perf_counter() - t, len(r)


def fmt(n, casas=0):
    return f"{n:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def main() -> int:
    p = argparse.ArgumentParser(description="Teste comparativo para a escolha do banco")
    p.add_argument("--repeticoes", type=int, default=5,
                   help="execucoes de cada abordagem (padrao: 5; reporta a mediana)")
    p.add_argument("--escala", type=int, default=1,
                   help="replica o fato N vezes para simular o volume do ano "
                        "(padrao: 1; use 35 para chegar perto dos 2 milhoes)")
    args = p.parse_args()

    if not Path(CSV_MUNICIPIOS).is_file():
        print(f"ERRO: {CSV_MUNICIPIOS} nao existe. "
              f"Rode antes: python baixar_proxy_racial.py")
        return 1

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")

    print("== Preparando os dados nos dois formatos ==")
    tamanhos = preparar(con, args.escala)
    n_fato = con.sql(f"SELECT count(*) FROM '{DIR_BENCH}/fato.parquet'").fetchone()[0]
    print(f"   fato: {fmt(n_fato)} contratos (apos o corte de sanidade"
          + (f", escala {args.escala}x)" if args.escala > 1 else ")"))
    print(f"\n   {'tabela':18} {'CSV':>12} {'Parquet':>12}  reducao")
    for nome, t in tamanhos.items():
        print(f"   {nome:18} {t['csv']/1e6:>9.1f} MB {t['parquet']/1e6:>9.1f} MB"
              f"  {t['csv']/t['parquet']:>6.1f}x")

    print(f"\n== Consulta do KPI interseccional, {args.repeticoes} execucoes ==")
    print("   (3 juncoes, agregacao com soma, contagem e mediana)\n")

    resultados = {}
    for rotulo, fn in (("arquivos soltos com pandas", rodar_pandas),
                       ("motor colunar sobre Parquet", lambda: rodar_duckdb(con))):
        tempos, linhas = [], None
        for i in range(args.repeticoes):
            dt, linhas = fn()
            tempos.append(dt)
        resultados[rotulo] = (statistics.median(tempos), min(tempos), max(tempos), linhas)
        med, mn, mx, n = resultados[rotulo]
        print(f"   {rotulo:30} mediana {med:>7.3f}s   "
              f"(min {mn:.3f} / max {mx:.3f})   {n} linhas")

    a = resultados["arquivos soltos com pandas"][0]
    b = resultados["motor colunar sobre Parquet"][0]
    print(f"\n   O motor colunar foi {a/b:.1f}x mais rapido nesta consulta.")

    print(f"\n== O que falta ==")
    print("   O tempo do PostgreSQL e a entrega da T1 e nao pode ser medido aqui")
    print("   (sem instancia local nem Docker). O lugar dele esta reservado em")
    print("   docs/escolha-do-banco.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
