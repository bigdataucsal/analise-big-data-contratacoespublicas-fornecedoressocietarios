"""
Mede a MESMA consulta do benchmark_banco.py no PostgreSQL (servico de teste da Aiven).

Entrega da T2. Complementa o benchmark_banco.py: reaproveita os CSV que ele grava em
dados/benchmark/ (fato.csv, dim_fornecedor.csv, dim_municipio.csv), carrega num schema
isolado ("bench"), roda a consulta e mede tambem o tamanho real das tabelas no banco.

Antes:
    pip install psycopg2-binary
    python benchmark_banco.py                       # gera dados/benchmark/*.csv
    $env:DATABASE_URL = "postgres://..."            # PowerShell; a URI NUNCA vai para chat nem Git

Uso (de dentro de etl/):
    python benchmark_postgres.py                    # ensaio: carrega 200 mil linhas do fato
    python benchmark_postgres.py --linhas 0         # carga completa (so ai os tempos sao comparaveis)
    python benchmark_postgres.py --linhas 0 --manter  # nao apaga o schema no final

Cuidados com o plano gratuito (1 GB de disco para tudo):
  - O script trabalha no schema "bench" e o APAGA no final (use --manter para evitar).
  - Consultas com mediana ordenam muitos dados e podem gerar arquivos temporarios, que
    contam na mesma cota. O script reporta os bytes temporarios gerados.
  - Os tempos incluem a latencia de rede ate o servidor. O tempo de execucao no proprio
    servidor (EXPLAIN ANALYZE) e reportado a parte.
"""

import argparse
import io
import itertools
import json
import os
import statistics
import sys
import time
from pathlib import Path

DIR_BENCH = Path("dados/benchmark")
SCHEMA = "bench"
SAIDA = Path(__file__).resolve().parent.parent / "docs" / "evidencias" / "benchmark_postgres.txt"

DDL = f"""
DROP SCHEMA IF EXISTS {SCHEMA} CASCADE;
CREATE SCHEMA {SCHEMA};
CREATE TABLE {SCHEMA}.fato (
    numero_controle_pncp text,
    codigo_ibge          text,
    cnpj_raiz_fornecedor text,
    valor_global         numeric(18,2),
    ano_contrato         integer
);
CREATE TABLE {SCHEMA}.dim_fornecedor (
    cnpj_raiz_fornecedor text,
    nome                 text,
    tipo_pessoa          text
);
CREATE TABLE {SCHEMA}.dim_municipio (
    codigo_ibge text,
    municipio   text,
    pct_negra   double precision
);
"""

INDICES = f"""
CREATE INDEX ix_fato_cnpj   ON {SCHEMA}.fato (cnpj_raiz_fornecedor);
CREATE INDEX ix_fato_ibge   ON {SCHEMA}.fato (codigo_ibge);
CREATE INDEX ix_dimf_cnpj   ON {SCHEMA}.dim_fornecedor (cnpj_raiz_fornecedor);
CREATE INDEX ix_dimm_ibge   ON {SCHEMA}.dim_municipio (codigo_ibge);
"""

# Mesma consulta do benchmark_banco.py (mesmas faixas, fechadas a esquerda).
CONSULTA = f"""
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
        percentile_cont(0.5) WITHIN GROUP (ORDER BY f.valor_global) AS valor_mediano
    FROM {SCHEMA}.fato f
    JOIN {SCHEMA}.dim_fornecedor d ON d.cnpj_raiz_fornecedor = f.cnpj_raiz_fornecedor
    JOIN {SCHEMA}.dim_municipio  m ON m.codigo_ibge = f.codigo_ibge
    GROUP BY 1, 2, 3
    ORDER BY valor_total DESC
"""

LOG = []


def say(texto=""):
    print(texto)
    LOG.append(texto)


def mb(n):
    return f"{n / 1e6:,.1f} MB".replace(",", "X").replace(".", ",").replace("X", ".")


def conectar(nome_var):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    url = os.environ.get(nome_var)
    if not url:
        sys.exit(f"ERRO: defina a variavel de ambiente {nome_var} com a URI do servico "
                 f"(nao cole a URI em chat nem no Git).")
    try:
        import psycopg2
    except ImportError:
        sys.exit("ERRO: instale o driver com: pip install psycopg2-binary")
    con = psycopg2.connect(url, connect_timeout=30)
    con.autocommit = True
    return con


def abrir_csv(nome, linhas):
    f = open(DIR_BENCH / nome, encoding="utf-8", newline="")
    if linhas:
        corte = io.StringIO("".join(itertools.islice(f, linhas + 1)))  # +1 = cabecalho
        f.close()
        return corte
    return f


def carregar(cur, tabela, csv, linhas=0):
    t = time.perf_counter()
    with abrir_csv(csv, linhas) as f:
        cur.copy_expert(f"COPY {SCHEMA}.{tabela} FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    cur.execute(f"SELECT count(*) FROM {SCHEMA}.{tabela}")
    n = cur.fetchone()[0]
    say(f"   {tabela:16} {n:>10,} linhas  ({time.perf_counter() - t:.1f} s)".replace(",", "."))
    return n


def tamanhos(cur):
    cur.execute(f"""
        SELECT c.relname, pg_total_relation_size(c.oid), pg_relation_size(c.oid), pg_indexes_size(c.oid)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = '{SCHEMA}' AND c.relkind = 'r' ORDER BY c.relname
    """)
    return cur.fetchall()


def temp_bytes(cur):
    cur.execute("SELECT temp_bytes FROM pg_stat_database WHERE datname = current_database()")
    return cur.fetchone()[0] or 0


def medir(cur, repeticoes):
    tempos, linhas = [], []
    for _ in range(repeticoes):
        t = time.perf_counter()
        cur.execute(CONSULTA)
        linhas = cur.fetchall()
        tempos.append(time.perf_counter() - t)
    return tempos, linhas


def tempo_servidor(cur):
    cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + CONSULTA)
    plano = cur.fetchone()[0]
    if isinstance(plano, str):
        plano = json.loads(plano)
    return plano[0]["Execution Time"] / 1000


def relatar(rotulo, tempos, linhas, servidor):
    say(f"   {rotulo}")
    say(f"     1a execucao {tempos[0]:.3f} s | mediana {statistics.median(tempos):.3f} s "
        f"(min {min(tempos):.3f} / max {max(tempos):.3f}) | {len(linhas)} linhas")
    say(f"     tempo de execucao no servidor (EXPLAIN ANALYZE): {servidor:.3f} s")


def conferir_com_duckdb(linhas_pg):
    """Compara totais com o DuckDB sobre os mesmos Parquet (so faz sentido na carga completa)."""
    try:
        import duckdb
    except ImportError:
        return None
    r = duckdb.connect().sql(f"""
        SELECT count(*), sum(f.valor_global)
        FROM '{DIR_BENCH}/fato.parquet' f
        JOIN '{DIR_BENCH}/dim_fornecedor.parquet' d ON d.cnpj_raiz_fornecedor = f.cnpj_raiz_fornecedor
        JOIN '{DIR_BENCH}/dim_municipio.parquet'  m ON m.codigo_ibge = f.codigo_ibge
    """).fetchone()
    n_pg = sum(int(l[3]) for l in linhas_pg)
    v_pg = sum(float(l[4]) for l in linhas_pg)
    ok = n_pg == int(r[0]) and abs(v_pg - float(r[1])) <= 1e-6 * max(1.0, abs(float(r[1])))
    return ok, (n_pg, int(r[0])), (v_pg, float(r[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark da consulta no PostgreSQL (Aiven)")
    ap.add_argument("--url-var", default="DATABASE_URL", help="variavel de ambiente com a URI")
    ap.add_argument("--repeticoes", type=int, default=5)
    ap.add_argument("--linhas", type=int, default=200_000,
                    help="linhas do fato a carregar (0 = todas). Padrao: 200 mil (ensaio)")
    ap.add_argument("--manter", action="store_true", help="nao apagar o schema no final")
    args = ap.parse_args()

    for arq in ("fato.csv", "dim_fornecedor.csv", "dim_municipio.csv"):
        if not (DIR_BENCH / arq).is_file():
            sys.exit(f"ERRO: {DIR_BENCH / arq} nao existe. Rode antes: python benchmark_banco.py")

    con = conectar(args.url_var)
    cur = con.cursor()
    cur.execute("SHOW server_version")
    versao = cur.fetchone()[0]
    cur.execute("SELECT pg_database_size(current_database())")
    base_antes = cur.fetchone()[0]
    say(f"== PostgreSQL {versao} | tamanho do banco antes: {mb(base_antes)} ==")
    if base_antes > 400e6:
        say("   AVISO: o banco ja esta grande para um plano de 1 GB. Considere parar (Ctrl+C).")

    amostra = args.linhas > 0
    if amostra:
        say("\n   *** ENSAIO COM AMOSTRA: os tempos NAO sao comparaveis com o DuckDB/pandas. ***")
        say("   *** Use esta rodada para o tamanho das tabelas. Para tempos: --linhas 0. ***")

    try:
        say("\n== Carga ==")
        cur.execute(DDL)
        n_fato = carregar(cur, "fato", "fato.csv", args.linhas)
        carregar(cur, "dim_fornecedor", "dim_fornecedor.csv")
        carregar(cur, "dim_municipio", "dim_municipio.csv")
        cur.execute(f"ANALYZE {SCHEMA}.fato; ANALYZE {SCHEMA}.dim_fornecedor; ANALYZE {SCHEMA}.dim_municipio;")

        say("\n== Consulta sem indices ==")
        t0 = temp_bytes(cur)
        tempos, linhas = medir(cur, args.repeticoes)
        servidor = tempo_servidor(cur)
        relatar("sem indices", tempos, linhas, servidor)
        sem_indice = (tempos, servidor)

        say("\n== Criando indices de juncao ==")
        t = time.perf_counter()
        cur.execute(INDICES)
        cur.execute(f"ANALYZE {SCHEMA}.fato; ANALYZE {SCHEMA}.dim_fornecedor; ANALYZE {SCHEMA}.dim_municipio;")
        say(f"   indices criados em {time.perf_counter() - t:.1f} s")

        say("\n== Consulta com indices ==")
        tempos, linhas = medir(cur, args.repeticoes)
        servidor = tempo_servidor(cur)
        relatar("com indices", tempos, linhas, servidor)
        gerados = temp_bytes(cur) - t0
        say(f"\n   arquivos temporarios gerados pelas consultas: {mb(gerados)} "
            f"(contam na cota de disco; estatistica pode atrasar alguns segundos)")

        say("\n== Tamanho real no PostgreSQL (com indices) ==")
        say(f"   {'tabela':16} {'total':>12} {'dados':>12} {'indices':>12}")
        total = 0
        for nome, tot, heap, idx in tamanhos(cur):
            total += tot
            say(f"   {nome:16} {mb(tot):>12} {mb(heap):>12} {mb(idx):>12}")
        say(f"   {'soma':16} {mb(total):>12}")
        if amostra:
            n_total = sum(1 for _ in open(DIR_BENCH / "fato.csv", encoding="utf-8")) - 1
            cur.execute(f"SELECT pg_total_relation_size('{SCHEMA}.fato')")
            fato_amostra = cur.fetchone()[0]
            proj = fato_amostra * n_total / n_fato
            say(f"\n   fato projetada para {n_total:,} linhas: ~{mb(proj)} (extrapolacao linear, NAO medicao)"
                .replace(",", "."))
            say("   Atencao: esta fato tem so 5 colunas; a fato reduzida final tera mais.")
        else:
            conf = conferir_com_duckdb(linhas)
            if conf:
                ok, (n_pg, n_dk), (v_pg, v_dk) = conf
                say(f"\n   conferencia com o DuckDB: contratos {n_pg:,} x {n_dk:,}; "
                    f"valor {v_pg:,.2f} x {v_dk:,.2f} -> {'IGUAIS' if ok else 'DIFERENTES'}"
                    .replace(",", "X").replace(".", ",").replace("X", "."))

        cur.execute("SELECT pg_database_size(current_database())")
        say(f"\n   tamanho do banco depois da carga: {mb(cur.fetchone()[0])}")
    finally:
        if not args.manter:
            cur.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
            say(f"\n   schema {SCHEMA} apagado.")
        con.close()

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text("\n".join(LOG), encoding="utf-8")
    print(f"\nGravado em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())