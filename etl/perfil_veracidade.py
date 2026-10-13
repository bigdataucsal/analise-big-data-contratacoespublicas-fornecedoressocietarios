"""perfil_veracidade.py"""
import argparse

import duckdb
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--parquet", default="dados/parquet/contratos/*/*.parquet")
args = ap.parse_args()

pd.set_option("display.width", 200)
con = duckdb.connect()
src = f"read_parquet('{args.parquet}')"


def pct(cond):
    return f"ROUND(100.0 * SUM(CASE WHEN ({cond}) THEN 1 ELSE 0 END) / COUNT(*), 2)"


def dt(col):
    return f"CAST(TRY_CAST({col} AS TIMESTAMP) AS DATE)"


metricas = {
    "contratos": "COUNT(*)",
    "orgaos distintos (orgao_cnpj)": "COUNT(DISTINCT orgao_cnpj)",
    "UFs": "COUNT(DISTINCT uf_sigla)",
    "municipios distintos (codigo_ibge)": "COUNT(DISTINCT codigo_ibge)",
    "% anoContrato = 2024": pct("TRY_CAST(ano_contrato AS INTEGER) = 2024"),
    "% anoContrato = 2025": pct("TRY_CAST(ano_contrato AS INTEGER) = 2025"),
    "% anoContrato outro ou nulo": pct("COALESCE(TRY_CAST(ano_contrato AS INTEGER) NOT IN (2024, 2025), TRUE)"),
    "% valorAcumulado nulo": pct("valor_acumulado IS NULL"),
    "% identificador com 11 digitos": pct("LENGTH(ni_fornecedor) = 11"),
    "% identificador fora de 11 e 14 digitos (ou ausente)": pct("COALESCE(LENGTH(ni_fornecedor) NOT IN (11, 14), TRUE)"),
    "% valor inicial diferente do global": pct("valor_inicial <> valor_global"),
    "% objeto com menos de 15 caracteres": pct("LENGTH(COALESCE(objeto_contrato, '')) < 15"),
    "% assinatura antes de 2024": pct(f"{dt('data_assinatura')} < DATE '2024-01-01'"),
    "% assinatura depois da publicacao": pct(f"{dt('data_assinatura')} > {dt('data_publicacao')}"),
    "% valor global zero ou negativo": pct("valor_global <= 0"),
    "% nome do fornecedor vazio": pct("nome_fornecedor IS NULL OR TRIM(nome_fornecedor) = ''"),
    "% com orgao subrogado": pct("orgao_subrogado_cnpj IS NOT NULL AND TRIM(CAST(orgao_subrogado_cnpj AS VARCHAR)) <> ''"),
    "% com unidade subrogada": pct("unidade_subrogada_codigo IS NOT NULL AND TRIM(CAST(unidade_subrogada_codigo AS VARCHAR)) <> ''"),
    "objeto: comprimento medio (caracteres)": "ROUND(AVG(LENGTH(objeto_contrato)), 1)",
    "objeto: comprimento maximo": "MAX(LENGTH(objeto_contrato))",
    "objeto: soma dos bytes (MB)": "ROUND(SUM(STRLEN(objeto_contrato)) / 1e6, 1)",
    "valor global: mediana (valor > 0)": "MEDIAN(valor_global) FILTER (WHERE valor_global > 0)",
    "valor global: media (valor > 0)": "AVG(valor_global) FILTER (WHERE valor_global > 0)",
    "valor global: mediana (0 < valor < R$ 1 bi)": "MEDIAN(valor_global) FILTER (WHERE valor_global > 0 AND valor_global < 1e9)",
    "valor global: media (0 < valor < R$ 1 bi)": "AVG(valor_global) FILTER (WHERE valor_global > 0 AND valor_global < 1e9)",
}

nomes = list(metricas)
sql = "SELECT " + ", ".join(f"{e} AS m{i}" for i, e in enumerate(metricas.values())) + f" FROM {src}"
linha = con.sql(sql).fetchone()

print("== Perfil de veracidade (ano inteiro) ==")
for nome, valor in zip(nomes, linha):
    if isinstance(valor, float):
        print(f"  {nome:<52} {valor:,.2f}")
    else:
        print(f"  {nome:<52} {valor:,}" if isinstance(valor, int) else f"  {nome:<52} {valor}")

print("\n== Composicao por esfera (orgao_esfera) ==")
print(con.sql(f"""
    SELECT orgao_esfera, COUNT(*) AS contratos,
           ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM {src} GROUP BY 1 ORDER BY 2 DESC
""").df().to_string())

print("\n== Identificadores fora de 11 e 14 digitos, por tipo_pessoa ==")
print(con.sql(f"""
    SELECT tipo_pessoa, COUNT(*) AS contratos FROM {src}
    WHERE COALESCE(LENGTH(ni_fornecedor) NOT IN (11, 14), TRUE)
    GROUP BY 1 ORDER BY 2 DESC
""").df().to_string())

print("\n== Contratos publicados por dia ==")
print(con.sql(f"""
    WITH d AS (SELECT {dt('data_publicacao')} AS dia, COUNT(*) AS n FROM {src} GROUP BY 1)
    SELECT ROUND(AVG(n)) AS media_dia, MIN(n) AS minimo, MAX(n) AS maximo,
           ROUND(AVG(n) FILTER (WHERE dia BETWEEN DATE '2025-01-01' AND DATE '2025-01-20')) AS media_1_a_20_jan
    FROM d
""").df().to_string())
