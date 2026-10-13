"""auditar_extremos.py"""
import argparse
import os

import duckdb
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--parquet", default="dados/parquet/contratos/*/*.parquet")
ap.add_argument("--limite", type=float, default=1e9,
                help="contratos com valor_global >= limite vao para o CSV de auditoria")
ap.add_argument("--saida", default="dados/auditoria_valores_extremos.csv")
args = ap.parse_args()

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 70)

con = duckdb.connect()
src = f"read_parquet('{args.parquet}')"

print("== Sensibilidade: o que sai do total conforme o corte ==")
print(con.sql(f"""
    WITH tot AS (SELECT SUM(valor_global) AS s FROM {src} WHERE valor_global > 0)
    SELECT c.corte,
           (SELECT COUNT(*) FROM {src} WHERE valor_global >= c.corte) AS contratos_acima,
           ROUND((SELECT SUM(valor_global) FROM {src} WHERE valor_global >= c.corte) / 1e9, 1) AS valor_acima_bi,
           ROUND(100.0 * (SELECT SUM(valor_global) FROM {src} WHERE valor_global >= c.corte)
                 / (SELECT s FROM tot), 2) AS pct_do_total,
           ROUND((SELECT SUM(valor_global) FROM {src} WHERE valor_global > 0 AND valor_global < c.corte) / 1e9, 1)
                 AS total_restante_bi
    FROM (VALUES (1e8), (1e9), (1e10), (1e11), (1e12)) AS c(corte)
    ORDER BY c.corte
""").df().to_string())

print("\n== 30 maiores contratos, com orgao e objeto ==")
print(con.sql(f"""
    SELECT printf('%.2f', valor_global) AS valor_txt,
           uf_sigla AS uf,
           LEFT(orgao_razao_social, 45) AS orgao,
           LEFT(REPLACE(objeto_contrato, CHR(10), ' '), 90) AS objeto
    FROM {src} ORDER BY valor_global DESC LIMIT 30
""").df().to_string())

print("\n== valor_global x (valor_parcela x numero_parcelas) nos 30 maiores ==")
print(con.sql(f"""
    SELECT printf('%.2f', valor_global) AS valor_txt,
           printf('%.2f', valor_parcela) AS parcela_txt,
           numero_parcelas,
           ROUND(valor_global / NULLIF(valor_parcela * numero_parcelas, 0), 2) AS razao
    FROM {src} ORDER BY valor_global DESC LIMIT 30
""").df().to_string())

print(f"\n== Orgaos com mais contratos >= {args.limite:,.0f} ==")
print(con.sql(f"""
    SELECT LEFT(orgao_razao_social, 50) AS orgao, uf_sigla AS uf, COUNT(*) AS contratos,
           ROUND(SUM(valor_global) / 1e9, 1) AS valor_bi
    FROM {src} WHERE valor_global >= {args.limite}
    GROUP BY 1, 2 ORDER BY contratos DESC, valor_bi DESC LIMIT 12
""").df().to_string())

print(f"\n== Fornecedores (NI) com mais contratos >= {args.limite:,.0f} ==")
print(con.sql(f"""
    SELECT ni_fornecedor, COUNT(*) AS contratos, ROUND(SUM(valor_global) / 1e9, 1) AS valor_bi
    FROM {src} WHERE valor_global >= {args.limite}
    GROUP BY 1 ORDER BY contratos DESC, valor_bi DESC LIMIT 10
""").df().to_string())

os.makedirs(os.path.dirname(args.saida), exist_ok=True)
con.sql(f"""
    COPY (
        SELECT numero_controle_pncp, data_assinatura, data_vigencia_inicio, data_vigencia_fim,
               orgao_cnpj, orgao_razao_social, uf_sigla, ni_fornecedor, tipo_pessoa,
               CASE WHEN tipo_pessoa = 'PJ' THEN nome_fornecedor END AS nome_fornecedor_pj,
               valor_inicial, valor_global, valor_parcela, numero_parcelas, objeto_contrato
        FROM {src} WHERE valor_global >= {args.limite}
        ORDER BY valor_global DESC
    ) TO '{args.saida}' (HEADER, DELIMITER ';')
""")
n = con.sql(f"SELECT COUNT(*) FROM {src} WHERE valor_global >= {args.limite}").fetchone()[0]
print(f"\nCSV de auditoria: {n} contratos com valor >= {args.limite:,.0f} em {args.saida}")
