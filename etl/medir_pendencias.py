import zipfile, pathlib
import pandas as pd

import config

RAW = pathlib.Path(config.DIR_DADOS_RAW) / "receita"

# ---------- 1. Descompactado real ----------
print("== 1. Descompactado real ==")
total, por_tipo = 0, {}
for z in sorted(RAW.glob("*.zip")):
    with zipfile.ZipFile(z) as zf:
        t = sum(i.file_size for i in zf.infolist())
    tipo = "".join(ch for ch in z.stem if not ch.isdigit())
    por_tipo[tipo] = por_tipo.get(tipo, 0) + t
    total += t
for k, v in por_tipo.items():
    print(f"  {k:18} {v/1e9:8.2f} GB")
print(f"  TOTAL              {total/1e9:8.2f} GB decimais | {total/2**30:.2f} GiB")

# ---------- leitura de amostra direto do ZIP (primeiras 200 mil linhas) ----------
def amostra(zip_path, cols, usecols=None, n=200_000):
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(zf.namelist()[0]) as f:
            return pd.read_csv(f, sep=";", header=None, names=cols, usecols=usecols,
                               dtype=str, encoding="latin-1", nrows=n,
                               keep_default_na=False, na_values=[""])

# ---------- 2a. Sócios ----------
print("\n== 2a. Sócios (Socios1.zip, 200 mil primeiras linhas) ==")
COLS_SOC = ["cnpj_basico", "identificador_de_socio", "nome_do_socio", "cnpj_cpf_do_socio",
            "qualificacao_do_socio", "data_entrada_sociedade", "pais", "cpf_representante",
            "nome_representante", "qualificacao_representante", "faixa_etaria"]
s = amostra(RAW / "Socios1.zip", COLS_SOC)
print("linhas:", len(s))
print(pd.DataFrame({"pct_nulos": (s.isna().mean() * 100).round(2), "distintos": s.nunique()}))
print("\nidentificador_de_socio (1=PJ, 2=PF, 3=estrangeiro):")
print(s.identificador_de_socio.value_counts(normalize=True).round(4).to_dict())
print("data_entrada = 00000000:", round((s.data_entrada_sociedade == "00000000").mean() * 100, 2), "%")
pj = s[s.identificador_de_socio == "1"]
pf = s[s.identificador_de_socio == "2"]
print("tamanho do documento, sócio PJ:", pj.cnpj_cpf_do_socio.str.len().value_counts().to_dict())
print("tamanho do documento, sócio PF:", pf.cnpj_cpf_do_socio.str.len().value_counts().to_dict())
print("linhas duplicadas:", s.duplicated().sum())
print("PF distintos por máscara:", pf.cnpj_cpf_do_socio.nunique(),
      "| por máscara + nome:", pf[["cnpj_cpf_do_socio", "nome_do_socio"]].drop_duplicates().shape[0])

# ---------- 2b. Estabelecimentos ----------
print("\n== 2b. Estabelecimentos (Estabelecimentos1.zip, 200 mil primeiras linhas) ==")
COLS_EST = ["cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial", "nome_fantasia",
            "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao_cadastral",
            "nome_cidade_exterior", "pais", "data_inicio_atividade", "cnae_fiscal_principal",
            "cnae_fiscal_secundaria", "tipo_logradouro", "logradouro", "numero", "complemento",
            "bairro", "cep", "uf", "municipio", "ddd_1", "telefone_1", "ddd_2", "telefone_2",
            "ddd_fax", "fax", "correio_eletronico", "situacao_especial", "data_situacao_especial"]
USO = ["cnpj_basico", "identificador_matriz_filial", "situacao_cadastral",
       "data_inicio_atividade", "cnae_fiscal_principal", "uf", "municipio"]
e = amostra(RAW / "Estabelecimentos1.zip", COLS_EST, usecols=USO)
print("linhas:", len(e))
print(pd.DataFrame({"pct_nulos": (e.isna().mean() * 100).round(2), "distintos": e.nunique()}))
print("matriz/filial:", e.identificador_matriz_filial.value_counts().to_dict())
print("situacao_cadastral:", e.situacao_cadastral.value_counts(normalize=True).round(4).to_dict())
print("tamanho do CNAE:", e.cnae_fiscal_principal.str.len().value_counts().to_dict())
print("tamanho do código de município:", e.municipio.str.len().value_counts().to_dict())
print("data_inicio_atividade = 00000000:", round((e.data_inicio_atividade == "00000000").mean() * 100, 2), "%")

# ---------- 3. Universos de fornecedor e valores fora da faixa (contratos tratados) ----------
import duckdb
P = "dados/parquet/contratos/*/*.parquet"
con = duckdb.connect()
print("\n== 3a. Universos de fornecedor ==")
print(con.sql(f"""
    SELECT tipo_pessoa,
           count(*) AS contratos,
           count(*) FILTER (WHERE cnpj_raiz_fornecedor IS NULL) AS sem_raiz,
           round(sum(valor_global)) AS valor_global
    FROM read_parquet('{P}', hive_partitioning=true)
    GROUP BY 1 ORDER BY 2 DESC""").df())
print("\n== 3b. Valores fora da faixa (RN-02 e teto de R$ 1 bi) ==")
print(con.sql(f"""
    SELECT count(*) AS total,
           count(*) FILTER (WHERE valor_global IS NULL)  AS nulos,
           count(*) FILTER (WHERE valor_global <= 0)     AS zero_ou_negativo,
           count(*) FILTER (WHERE valor_global > 1e9)    AS acima_de_1_bi
    FROM read_parquet('{P}', hive_partitioning=true)""").df())