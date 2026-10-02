"""
Teste comparativo que sustenta a escolha do banco.
=====================================================================
Entrega da T3, semana 3 (atualizado pela T2 em 02/10/2026). Roda a MESMA
consulta analitica em duas abordagens e cronometra as duas, para que a
escolha do modelo seja evidencia e nao preferencia.

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
O tempo do PostgreSQL. Ele e medido por benchmark_postgres.py, contra o
servico gratuito da Aiven, com o mesmo fato.csv. Para comparar os tres com
o MESMO volume, use --linhas (veja abaixo). Confira no benchmark_postgres.py
que ele tambem carrega o INICIO do fato.csv; se carregar, as N linhas sao
as mesmas nos tres testes.

Conferencia dos resultados
--------------------------
Alem do tempo, o script compara o RESULTADO das duas abordagens, grupo a
grupo (contratos, soma e mediana do valor). Antes so o numero de linhas do
resultado era comparado; agora o resultado inteiro e.

Uso (rodar de dentro de etl/):
    python benchmark_banco.py                      # prepara os arquivos e roda no volume completo
    python benchmark_banco.py --repeticoes 7
    python benchmark_banco.py --linhas 200000      # usa os arquivos ja preparados; primeiras 200 mil linhas
    python benchmark_banco.py --linhas 1000000     # idem, 1 milhao
    python benchmark_banco.py --linhas 0           # usa os arquivos ja preparados; todas as linhas

Com --linhas, os arquivos de dados NAO sao regerados: o script le o
dados/benchmark/fato.csv que ja existe (o mesmo que o benchmark_postgres.py
usa) e as dimensoes. A saida e gravada em docs/evidencias/.
"""

import argparse
import itertools
import math
import os
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

PARQUET = "dados/parquet/contratos/**/*.parquet"
CSV_MUNICIPIOS = "dados/proxy/cor_raca_municipio_2022.csv"
DIR_BENCH = Path("dados/benchmark")
DIR_EVIDENCIAS = Path("../docs/evidencias")

COLUNAS_CHAVE = ("faixa_pct_negra", "faixa_valor", "tipo_pessoa")

_saida: list[str] = []


def say(texto: str = "") -> None:
    """Imprime e guarda a linha, para gravar a evidencia no fim."""
    print(texto)
    _saida.append(texto)


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


def tamanhos(dir_fato: Path) -> dict:
    """Tamanho em disco dos arquivos usados nesta rodada."""
    arquivos = {
        "fato": dir_fato / "fato",
        "dim_fornecedor": DIR_BENCH / "dim_fornecedor",
        "dim_municipio": DIR_BENCH / "dim_municipio",
    }
    return {nome: {"csv": Path(f"{base}.csv").stat().st_size,
                   "parquet": Path(f"{base}.parquet").stat().st_size}
            for nome, base in arquivos.items()}


def criar_amostra(n: int) -> Path:
    """Cria uma fato com as PRIMEIRAS n linhas do fato.csv ja existente.

    O recorte e feito linha a linha no proprio arquivo de texto, sem
    reformatar nada. O Parquet da amostra e gerado a partir desse mesmo
    CSV, para que as duas abordagens leiam exatamente o mesmo conteudo.
    """
    dir_amostra = DIR_BENCH / f"amostra_{n}"
    dir_amostra.mkdir(parents=True, exist_ok=True)
    origem = DIR_BENCH / "fato.csv"
    destino = dir_amostra / "fato.csv"
    with open(origem, "r", encoding="utf-8", newline="") as f, \
            open(destino, "w", encoding="utf-8", newline="") as g:
        for linha in itertools.islice(f, n + 1):   # cabecalho + n linhas
            g.write(linha)

    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT numero_controle_pncp::VARCHAR     AS numero_controle_pncp,
                   codigo_ibge::VARCHAR              AS codigo_ibge,
                   cnpj_raiz_fornecedor::VARCHAR     AS cnpj_raiz_fornecedor,
                   CAST(valor_global AS DOUBLE)      AS valor_global,
                   TRY_CAST(ano_contrato AS BIGINT)  AS ano_contrato
            FROM read_csv('{destino.as_posix()}', header=true, all_varchar=true)
        ) TO '{(dir_amostra / "fato.parquet").as_posix()}'
          (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    con.close()
    return dir_amostra


def consulta_sql(dir_fato: Path) -> str:
    return f"""
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
    FROM '{(dir_fato / "fato.parquet").as_posix()}' f
    JOIN '{(DIR_BENCH / "dim_fornecedor.parquet").as_posix()}' d
      ON d.cnpj_raiz_fornecedor = f.cnpj_raiz_fornecedor
    JOIN '{(DIR_BENCH / "dim_municipio.parquet").as_posix()}' m
      ON m.codigo_ibge = f.codigo_ibge
    GROUP BY 1, 2, 3
    ORDER BY valor_total DESC
"""


def rodar_duckdb(con, sql: str):
    t = time.perf_counter()
    linhas = con.sql(sql).fetchall()
    return time.perf_counter() - t, linhas


def rodar_pandas(dir_fato: Path):
    import pandas as pd
    t = time.perf_counter()
    fato = pd.read_csv(dir_fato / "fato.csv", dtype={"codigo_ibge": str,
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
    r = (df.groupby(list(COLUNAS_CHAVE), observed=True)["valor_global"]
           .agg(contratos="count", valor_total="sum", valor_mediano="median")
           .reset_index()
           .sort_values("valor_total", ascending=False))
    return time.perf_counter() - t, r


def normalizar_duckdb(linhas) -> dict:
    return {(str(r[0]), str(r[1]), str(r[2])): (int(r[3]), float(r[4]), float(r[5]))
            for r in linhas}


def normalizar_pandas(df) -> dict:
    return {(str(r.faixa_pct_negra), str(r.faixa_valor), str(r.tipo_pessoa)):
            (int(r.contratos), float(r.valor_total), float(r.valor_mediano))
            for r in df.itertuples()}


def comparar(a: dict, b: dict) -> list[str]:
    """Devolve a lista de divergencias entre os dois resultados (vazia = iguais)."""
    problemas = []
    so_a, so_b = set(a) - set(b), set(b) - set(a)
    if so_a:
        problemas.append(f"grupos so no pandas: {sorted(so_a)}")
    if so_b:
        problemas.append(f"grupos so no DuckDB: {sorted(so_b)}")
    for chave in sorted(set(a) & set(b)):
        ca, va, ma = a[chave]
        cb, vb, mb = b[chave]
        if ca != cb:
            problemas.append(f"{chave}: contratos {ca} x {cb}")
        if not math.isclose(va, vb, rel_tol=1e-9, abs_tol=0.01):
            problemas.append(f"{chave}: valor total {va} x {vb}")
        if not math.isclose(ma, mb, rel_tol=1e-9, abs_tol=0.01):
            problemas.append(f"{chave}: mediana {ma} x {mb}")
    return problemas


def fmt(n, casas=0):
    return f"{n:,.{casas}f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def main() -> int:
    p = argparse.ArgumentParser(description="Teste comparativo para a escolha do banco")
    p.add_argument("--repeticoes", type=int, default=5,
                   help="execucoes de cada abordagem (padrao: 5; reporta a mediana)")
    p.add_argument("--escala", type=int, default=1,
                   help="replica o fato N vezes para simular o volume do ano "
                        "(padrao: 1; so vale quando os arquivos sao preparados)")
    p.add_argument("--linhas", type=int, default=None,
                   help="usa os arquivos ja preparados e as primeiras N linhas do "
                        "fato.csv (0 = todas); sem esta opcao, prepara os arquivos")
    p.add_argument("--saida", default=None,
                   help="arquivo de evidencia (padrao: docs/evidencias/benchmark_banco_<linhas>.txt)")
    args = p.parse_args()

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")

    say(f"== Teste comparativo, {datetime.now():%d/%m/%Y %H:%M} ==")
    import pandas as pd
    say(f"   DuckDB {duckdb.__version__} | pandas {pd.__version__} | "
        f"Python {platform.python_version()} | {os.cpu_count()} processadores logicos | "
        f"{platform.system()} {platform.release()}")

    if args.linhas is None:
        if not Path(CSV_MUNICIPIOS).is_file():
            say(f"ERRO: {CSV_MUNICIPIOS} nao existe. "
                f"Rode antes: python baixar_proxy_racial.py")
            return 1
        say("\n== Preparando os dados nos dois formatos ==")
        preparar(con, args.escala)
        dir_fato, rotulo = DIR_BENCH, "completo"
    else:
        faltando = [f for f in ("fato.csv", "fato.parquet", "dim_fornecedor.csv",
                                "dim_fornecedor.parquet", "dim_municipio.csv",
                                "dim_municipio.parquet") if not (DIR_BENCH / f).is_file()]
        if faltando:
            say(f"ERRO: faltam arquivos em {DIR_BENCH}: {', '.join(faltando)}. "
                f"Rode antes, sem --linhas: python benchmark_banco.py")
            return 1
        if args.linhas > 0:
            say(f"\n== Amostra: primeiras {fmt(args.linhas)} linhas do fato.csv ==")
            dir_fato, rotulo = criar_amostra(args.linhas), str(args.linhas)
        else:
            say("\n== Volume completo, com os arquivos ja preparados ==")
            dir_fato, rotulo = DIR_BENCH, "completo"

    sql = consulta_sql(dir_fato)
    n_fato = con.sql(f"SELECT count(*) FROM "
                     f"'{(dir_fato / 'fato.parquet').as_posix()}'").fetchone()[0]
    say(f"   fato: {fmt(n_fato)} contratos (apos o corte de sanidade"
        + (f", escala {args.escala}x)" if args.linhas is None and args.escala > 1 else ")"))
    say(f"\n   {'tabela':18} {'CSV':>12} {'Parquet':>12}  reducao")
    for nome, t in tamanhos(dir_fato).items():
        say(f"   {nome:18} {t['csv']/1e6:>9.1f} MB {t['parquet']/1e6:>9.1f} MB"
            f"  {t['csv']/t['parquet']:>6.1f}x")

    say(f"\n== Consulta do KPI interseccional, {args.repeticoes} execucoes ==")
    say("   (3 juncoes, agregacao com soma, contagem e mediana)\n")

    resultados, ultimo = {}, {}
    rotinas = (("arquivos soltos com pandas", lambda: rodar_pandas(dir_fato)),
               ("motor colunar sobre Parquet", lambda: rodar_duckdb(con, sql)))
    for rotulo_ab, fn in rotinas:
        tempos, saida = [], None
        for _ in range(args.repeticoes):
            dt, saida = fn()
            tempos.append(dt)
        ultimo[rotulo_ab] = saida
        resultados[rotulo_ab] = (tempos[0], statistics.median(tempos), min(tempos), max(tempos),
                                 len(saida))
        prim, med, mn, mx, n = resultados[rotulo_ab]
        say(f"   {rotulo_ab:30} 1a execucao {prim:>7.3f}s   mediana {med:>7.3f}s   "
            f"(min {mn:.3f} / max {mx:.3f})   {n} linhas")

    a = resultados["arquivos soltos com pandas"][1]
    b = resultados["motor colunar sobre Parquet"][1]
    say(f"\n   O motor colunar foi {a/b:.1f}x mais rapido nesta consulta (mediana).")

    say("\n== Conferencia dos resultados ==")
    res_pandas = normalizar_pandas(ultimo["arquivos soltos com pandas"])
    res_duck = normalizar_duckdb(ultimo["motor colunar sobre Parquet"])
    for nome, res in (("pandas", res_pandas), ("DuckDB", res_duck)):
        say(f"   {nome:8} {len(res)} grupos | {fmt(sum(v[0] for v in res.values()))} contratos"
            f" | valor total R$ {fmt(sum(v[1] for v in res.values()), 2)}")
    problemas = comparar(res_pandas, res_duck)
    if problemas:
        say("   RESULTADOS DIVERGEM:")
        for pr in problemas[:20]:
            say(f"     - {pr}")
    else:
        say("   Os dois resultados sao identicos, grupo a grupo "
            "(contratos exatos; soma e mediana com tolerancia de R$ 0,01).")
    contratos_res = sum(v[0] for v in res_duck.values())
    if contratos_res != n_fato:
        say(f"   Atencao: {fmt(n_fato - contratos_res)} contratos da fato nao entram no resultado "
            f"(fornecedor ou municipio sem correspondencia nas dimensoes, ou sem valor nas chaves).")

    say("\n== O que falta ==")
    say("   O tempo do PostgreSQL e medido por benchmark_postgres.py, no servico gratuito")
    say("   da Aiven, com o mesmo fato.csv (rodar com --linhas igual a esta rodada).")

    destino = Path(args.saida) if args.saida else DIR_EVIDENCIAS / f"benchmark_banco_{rotulo}.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(_saida) + "\n", encoding="utf-8")
    print(f"\nGravado em {destino.resolve()}")
    return 0 if not problemas else 2


if __name__ == "__main__":
    sys.exit(main())