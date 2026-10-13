"""diagnostico_valores.py"""
import argparse

import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--parquet", default="dados/parquet/contratos/*/*.parquet")
args = ap.parse_args()

con = duckdb.connect()
src = f"read_parquet('{args.parquet}')"

cols = [r[0] for r in con.sql(f"DESCRIBE SELECT * FROM {src}").fetchall()]
print("== Colunas ==")
print(", ".join(cols))


def achar(*trechos):
    for t in trechos:
        for c in cols:
            if t in c.lower():
                return c
    return None


v = achar("valor_global")
vi = achar("valor_inicial")
ni = achar("ni_fornecedor")
tp = achar("tipo_pessoa")
if not v:
    raise SystemExit("Nao achei a coluna de valor global. Veja a lista acima.")

print(f"\n(usando: valor={v}, valor_inicial={vi}, ni_fornecedor={ni}, tipo_pessoa={tp})")

print("\n== 20 maiores valores ==")
extras = ", ".join(c for c in (ni, tp, vi) if c)
print(con.sql(f"""
    SELECT {v} AS valor_global{', ' + extras if extras else ''}
    FROM {src} ORDER BY {v} DESC LIMIT 20
""").df().to_string())

print("\n== Concentracao do valor ==")
print(con.sql(f"""
    WITH t AS (SELECT {v} AS v FROM {src}),
    tot AS (SELECT SUM(v) AS s, COUNT(*) AS n FROM t)
    SELECT faixa, COUNT(*) AS contratos, SUM(v) AS valor,
           ROUND(100.0 * SUM(v) / (SELECT s FROM tot), 2) AS pct_do_valor
    FROM (
        SELECT v, CASE WHEN v <= 0 THEN '0 - zero/negativo'
                       WHEN v < 1e5 THEN '1 - < 100 mil'
                       WHEN v < 1e6 THEN '2 - 100 mil a 1 mi'
                       WHEN v < 1e7 THEN '3 - 1 a 10 mi'
                       WHEN v < 1e8 THEN '4 - 10 a 100 mi'
                       WHEN v < 1e9 THEN '5 - 100 mi a 1 bi'
                       WHEN v < 1e12 THEN '6 - 1 bi a 1 tri'
                       ELSE '7 - >= 1 tri' END AS faixa
        FROM t) GROUP BY faixa ORDER BY faixa
""").df().to_string())

print("\n== Valores repetidos no topo (possiveis placeholders) ==")
print(con.sql(f"""
    SELECT {v} AS valor, COUNT(*) AS vezes FROM {src}
    WHERE {v} >= 1e9 GROUP BY {v} HAVING COUNT(*) > 1
    ORDER BY vezes DESC, valor DESC LIMIT 10
""").df().to_string())

if vi:
    print("\n== valor_inicial x valor_global nos 20 maiores ==")
    print(con.sql(f"""
        SELECT {v} AS valor_global, {vi} AS valor_inicial
        FROM {src} ORDER BY {v} DESC LIMIT 20
    """).df().to_string())
    print("\nSoma valor_inicial:", con.sql(f"SELECT SUM({vi}) FROM {src}").fetchone()[0])

if ni:
    tipo = tp if tp else f"CASE WHEN LENGTH({ni}) = 14 THEN 'PJ' WHEN LENGTH({ni}) = 11 THEN 'PF' ELSE 'OUTRO' END"
    print("\n== Universos por tipo de fornecedor ==")
    print(con.sql(f"""
        SELECT {tipo} AS tipo, LENGTH({ni}) AS tam_ni, COUNT(*) AS contratos,
               SUM({v}) AS valor, COUNT(DISTINCT {ni}) AS nis_distintos
        FROM {src} GROUP BY 1, 2 ORDER BY contratos DESC
    """).df().to_string())
    print("\n== Raizes de CNPJ (8 digitos) distintas entre fornecedores com 14 digitos ==")
    print(con.sql(f"""
        SELECT COUNT(DISTINCT SUBSTR({ni}, 1, 8)) AS raizes_distintas
        FROM {src} WHERE LENGTH({ni}) = 14
    """).fetchone()[0])
