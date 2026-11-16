"""
Carga da Receita (Parquet ja filtrado pelo baixar_receita.py) no modelo
estrela do Aiven: dim_fornecedor, dim_socio e ponte_empresa_socio.

Ordem: rodem ANTES o aplicar_schema.py, que cria o schema novo. Se o banco
ainda tiver a fato do desenho antigo, este script para com um aviso.

Pode ser rodado de novo sem duplicar (COPY em tabela temporaria + INSERT ...
ON CONFLICT). Se dim_fornecedor e dim_socio ja estiverem carregadas, pula as
duas (use --forcar-dimensoes para recarregar) e carrega so a ponte, em lotes
de 50 mil linhas com commit a cada lote, para o no gratuito nao derrubar a
conexao.

No etl/.env:
    AIVEN_PG_URI=postgres://usuario:senha@host.aivencloud.com:PORTA/defaultdb?sslmode=require
    SALT_SOCIO=<texto fixo; nao mudem depois da carga>

Uso (de dentro de etl/):
    python carregar_receita_aiven.py --simular
    python carregar_receita_aiven.py
    python carregar_receita_aiven.py --forcar-dimensoes
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

import config   # tambem carrega o etl/.env

DIR_RECEITA = Path(config.DIR_DADOS_PARQUET) / "receita"
CSV_RAIZES = Path(config.DIR_RECORTE) / "cnpjs_raiz.csv"
COMPETENCIA = config.MES_RECEITA[:7]          # AAAA-MM do snapshot
LOTE = 200_000                                 # linhas por bloco de COPY
PASSO_PONTE = 50_000                           # linhas da ponte por commit

COLUNAS = {
    "emprecsv": ["cnpj_basico", "razao_social", "natureza_juridica",
                 "capital_social", "porte_empresa"],
    "estabele": ["cnpj_basico", "identificador_matriz_filial",
                 "cnae_fiscal_principal", "data_inicio_atividade"],
    "sociocsv": ["cnpj_basico", "identificador_socio", "nome_socio_razao_social",
                 "cnpj_cpf_socio", "qualificacao_socio",
                 "data_entrada_sociedade", "faixa_etaria"],
    "qualscsv": ["codigo", "descricao_qualificacao_socio"],
}


def sem_acento(txt) -> str:
    t = unicodedata.normalize("NFKD", txt if isinstance(txt, str) else "")
    return "".join(c for c in t if not unicodedata.combining(c))


def normalizar_nome(nome) -> str:
    return re.sub(r"\s+", " ", sem_acento(nome).upper()).strip()


def id_publico(mascara, nome, sal: str = "") -> str:
    """Identificador derivado do socio (RN-09): mascara + nome + sal. Nunca o CPF."""
    m = mascara.strip() if isinstance(mascara, str) else ""
    base = f"{m}|{normalizar_nome(nome)}|{sal}"
    return "S" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def grupo_da_qualificacao(descricao: str) -> str:
    """Agrupa pela DESCRICAO da tabela de dominio da Receita (nao pelo codigo)."""
    d = sem_acento(descricao).upper()
    if "TITULAR" in d or "EMPRESARIO" in d:
        return "titularidade"
    if "SOCIO" in d:
        return "participacao"
    if any(k in d for k in ("ADMINISTRADOR", "DIRETOR", "PRESIDENTE", "CONSELHEIRO")):
        return "administracao"
    if any(k in d for k in ("PROCURADOR", "REPRESENTANTE", "TUTOR", "CURADOR",
                            "INVENTARIANTE")):
        return "representacao"
    return "outro"


def ler(nome: str) -> pd.DataFrame:
    caminho = DIR_RECEITA / f"{nome}.parquet"
    if not caminho.is_file():
        raise SystemExit(f"ERRO: {caminho} nao existe. Rodem: "
                         f"python baixar_receita.py --sem-download --filtrar-cnpjs")
    existentes = pq.read_schema(caminho).names
    faltam = [c for c in COLUNAS[nome] if c not in existentes]
    if faltam:
        raise SystemExit(f"ERRO: {caminho.name} nao tem as colunas {faltam}.\n"
                         f"       Colunas existentes: {existentes}")
    return pd.read_parquet(caminho, columns=COLUNAS[nome])


def data_iso(serie: pd.Series) -> pd.Series:
    # '00000000' e ausencia na Receita: vira nulo
    return pd.to_datetime(serie, format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")


def ler_raizes() -> set:
    df = pd.read_csv(CSV_RAIZES, dtype=str)
    return set(df["cnpj_basico"].dropna().str.strip())


def checar_manifesto(raizes: set) -> None:
    m = DIR_RECEITA / "_manifesto.json"
    if not m.is_file():
        print("   AVISO: _manifesto.json nao encontrado.")
        return
    man = json.loads(m.read_text(encoding="utf-8"))
    print(f"   manifesto: competencia {man.get('competencia')}, "
          f"{man.get('total_cnpjs_no_filtro'):,} raizes no filtro")
    for chave, info in man.get("arquivos", {}).items():
        if chave in ("EMPRECSV", "ESTABELE", "SOCIOCSV"):
            print(f"      {chave}: {info['linhas_lidas_na_origem']:,} lidas -> "
                  f"{info['linhas_gravadas']:,} gravadas")
    if man.get("total_cnpjs_no_filtro") != len(raizes):
        print(f"   AVISO: o Parquet foi gerado com {man.get('total_cnpjs_no_filtro'):,} "
              f"raizes, mas o cnpjs_raiz.csv atual tem {len(raizes):,}. "
              f"Refacam o filtro antes de carregar.")
    if man.get("competencia") and man["competencia"] != config.MES_RECEITA:
        print(f"   AVISO: competencia do Parquet ({man['competencia']}) difere de "
              f"config.MES_RECEITA ({config.MES_RECEITA}).")


def montar(sal: str, raizes: set):
    emp = ler("emprecsv").drop_duplicates("cnpj_basico")
    est = ler("estabele")
    so = ler("sociocsv")
    quals = ler("qualscsv")

    matriz = (est[est["identificador_matriz_filial"] == "1"]
              .drop_duplicates("cnpj_basico")
              [["cnpj_basico", "cnae_fiscal_principal", "data_inicio_atividade"]])
    forn = emp.merge(matriz, on="cnpj_basico", how="left")
    capital = pd.to_numeric(forn["capital_social"].str.replace(",", ".", regex=False),
                            errors="coerce")
    capital = capital.where(capital.abs() < 1e16)       # cabe no NUMERIC(18,2)
    forn = pd.DataFrame({
        "cnpj_raiz": forn["cnpj_basico"],
        "razao_social": forn["razao_social"].str.strip(),
        "natureza_juridica": forn["natureza_juridica"],
        "porte": forn["porte_empresa"],
        "cnae_principal": forn["cnae_fiscal_principal"],
        "capital_social": capital,
        "data_inicio_ativ": data_iso(forn["data_inicio_atividade"]),
    })

    mapa = {str(c).strip(): grupo_da_qualificacao(d)
            for c, d in zip(quals["codigo"], quals["descricao_qualificacao_socio"])}
    desc = {str(c).strip(): d for c, d in
            zip(quals["codigo"], quals["descricao_qualificacao_socio"])}

    so["identificador_pub"] = [id_publico(m, n, sal) for m, n in
                               zip(so["cnpj_cpf_socio"], so["nome_socio_razao_social"])]
    socio = pd.DataFrame({
        "identificador_pub": so["identificador_pub"],
        "cpf_mascarado": so["cnpj_cpf_socio"].str.strip(),
        "identificador_tipo": pd.to_numeric(so["identificador_socio"],
                                            errors="coerce").astype("Int64"),
        "faixa_etaria": pd.to_numeric(so["faixa_etaria"],
                                      errors="coerce").fillna(0).astype(int),
    }).drop_duplicates("identificador_pub")

    qual = so["qualificacao_socio"].fillna("").str.strip().replace("", "00")
    ponte = pd.DataFrame({
        "cnpj_raiz": so["cnpj_basico"],
        "identificador_pub": so["identificador_pub"],
        "data_entrada": data_iso(so["data_entrada_sociedade"]),
        "qualificacao": qual,
        "grupo_qualificacao": qual.map(mapa).fillna("outro"),
        "competencia": COMPETENCIA,
    })
    ponte = (ponte.sort_values("data_entrada", ascending=False, na_position="last")
             .drop_duplicates(["cnpj_raiz", "identificador_pub",
                               "qualificacao", "competencia"]))

    # Painel de conferencia para o grupo decidir a RN-03
    tab = (ponte.assign(descricao=ponte["qualificacao"].map(desc))
           .groupby(["qualificacao", "descricao", "grupo_qualificacao"], dropna=False)
           .size().reset_index(name="vinculos").sort_values("vinculos", ascending=False))
    print("\n-- qualificacoes presentes e grupo atribuido (conferir a RN-03)")
    for _, r in tab.iterrows():
        print(f"   {r['qualificacao']:>3} {sem_acento(r['descricao'])[:48]:<48} "
              f"-> {r['grupo_qualificacao']:<13} {r['vinculos']:>9,}")

    achadas = raizes & set(emp["cnpj_basico"])
    com_socio = raizes & set(so["cnpj_basico"])
    print(f"\n-- cobertura: {len(achadas):,} de {len(raizes):,} raizes na tabela de "
          f"empresas; {len(com_socio):,} com ao menos um socio")
    return forn, socio, ponte


def copiar(cur, tabela: str, df: pd.DataFrame) -> None:
    cols = ", ".join(df.columns)
    with cur.copy(f"COPY {tabela} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '')") as c:
        for ini in range(0, len(df), LOTE):
            buf = io.StringIO()
            df.iloc[ini:ini + LOTE].to_csv(buf, index=False, header=False, na_rep="")
            c.write(buf.getvalue())


def carregar(uri: str, forn, socio, ponte, forcar_dim: bool = False) -> int:
    import psycopg
    inicio = time.time()
    ddl = (Path(__file__).resolve().parent / "schema_estrela.sql").read_text(encoding="utf-8")
    if "-- 4. Indices" not in ddl or "-- 5. Agregados" not in ddl:
        raise SystemExit("ERRO: marcadores de secao nao encontrados no schema_estrela.sql")
    tabelas = ddl.split("-- 4. Indices")[0]
    indices = ddl.split("-- 4. Indices")[1].split("-- 5. Agregados")[0]

    with psycopg.connect(uri, autocommit=False) as con:
        with con.cursor() as cur:
            if cur.execute("SHOW default_transaction_read_only").fetchone()[0] == "on":
                raise SystemExit("ERRO: o banco esta em somente leitura (disco cheio?). "
                                 "Confiram o painel da Aiven antes de carregar.")
            antiga = cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = 'fato_contrato' AND column_name = 'id_tempo_publicacao'"
            ).fetchone()
            if antiga:
                raise SystemExit("ERRO: o banco ainda tem a fato do desenho antigo. "
                                 "Rodem antes: python aplicar_schema.py")
            con.commit()
            cur.execute("SET synchronous_commit = off")

            print("\n-- tabelas (se nao existirem)")
            cur.execute(tabelas)
            # A mascara do CPF colide entre pessoas diferentes; a chave e identificador_pub.
            cur.execute("ALTER TABLE dim_socio DROP CONSTRAINT IF EXISTS "
                        "dim_socio_cpf_mascarado_key")
            con.commit()

            n_f = cur.execute("SELECT count(*) FROM dim_fornecedor").fetchone()[0]
            n_s = cur.execute("SELECT count(*) FROM dim_socio").fetchone()[0]
            con.commit()
            pular = (not forcar_dim) and n_f >= len(forn) and n_s >= len(socio)

            if pular:
                print(f"-- dim_fornecedor ({n_f:,}) e dim_socio ({n_s:,}) ja carregadas: pulando")
            else:
                print(f"-- dim_fornecedor ({len(forn):,} empresas)")
                cur.execute("""CREATE TEMP TABLE stg_fornecedor (
                    cnpj_raiz TEXT, razao_social TEXT, natureza_juridica TEXT, porte TEXT,
                    cnae_principal TEXT, capital_social NUMERIC(18,2), data_inicio_ativ DATE
                ) ON COMMIT DROP""")
                copiar(cur, "stg_fornecedor", forn)
                cur.execute("""
                    INSERT INTO dim_fornecedor (cnpj_raiz, razao_social, tipo_pessoa,
                        natureza_juridica, porte, cnae_principal, capital_social, data_inicio_ativ)
                    SELECT cnpj_raiz, razao_social, 'PJ', natureza_juridica, porte,
                           cnae_principal, capital_social, data_inicio_ativ
                    FROM stg_fornecedor
                    ON CONFLICT (cnpj_raiz) DO UPDATE SET
                        razao_social = EXCLUDED.razao_social,
                        natureza_juridica = EXCLUDED.natureza_juridica,
                        porte = EXCLUDED.porte, cnae_principal = EXCLUDED.cnae_principal,
                        capital_social = EXCLUDED.capital_social,
                        data_inicio_ativ = EXCLUDED.data_inicio_ativ""")
                con.commit()

                print(f"-- dim_socio ({len(socio):,} socios distintos)")
                cur.execute("""CREATE TEMP TABLE stg_socio (
                    identificador_pub TEXT, cpf_mascarado TEXT,
                    identificador_tipo SMALLINT, faixa_etaria SMALLINT
                ) ON COMMIT DROP""")
                copiar(cur, "stg_socio", socio)
                cur.execute("""
                    INSERT INTO dim_socio (identificador_pub, cpf_mascarado,
                                           identificador_tipo, faixa_etaria)
                    SELECT identificador_pub, cpf_mascarado, identificador_tipo, faixa_etaria
                    FROM stg_socio
                    ON CONFLICT (identificador_pub) DO UPDATE SET
                        cpf_mascarado = EXCLUDED.cpf_mascarado,
                        identificador_tipo = EXCLUDED.identificador_tipo,
                        faixa_etaria = EXCLUDED.faixa_etaria""")   # genero nao e tocado
                con.commit()

            print(f"-- ponte_empresa_socio ({len(ponte):,} vinculos, competencia {COMPETENCIA})")
            for ini in range(0, len(ponte), PASSO_PONTE):
                cur.execute("""CREATE TEMP TABLE stg_ponte (
                    cnpj_raiz TEXT, identificador_pub TEXT, data_entrada DATE,
                    qualificacao TEXT, grupo_qualificacao TEXT, competencia TEXT
                ) ON COMMIT DROP""")
                copiar(cur, "stg_ponte", ponte.iloc[ini:ini + PASSO_PONTE])
                cur.execute("""
                    INSERT INTO ponte_empresa_socio (id_fornecedor, id_socio, data_entrada,
                        qualificacao, grupo_qualificacao, competencia)
                    SELECT f.id_fornecedor, s.id_socio, p.data_entrada, p.qualificacao,
                           p.grupo_qualificacao, p.competencia
                    FROM stg_ponte p
                    JOIN dim_fornecedor f ON f.cnpj_raiz = p.cnpj_raiz
                    JOIN dim_socio s ON s.identificador_pub = p.identificador_pub
                    ON CONFLICT (id_fornecedor, id_socio, qualificacao, competencia)
                    DO UPDATE SET data_entrada = EXCLUDED.data_entrada,
                                  grupo_qualificacao = EXCLUDED.grupo_qualificacao""")
                con.commit()
                print(f"   {min(ini + PASSO_PONTE, len(ponte)):,} / {len(ponte):,}")

            print("-- indices (depois da carga)")
            cur.execute(indices)
            con.commit()
            for t in ("dim_fornecedor", "dim_socio", "ponte_empresa_socio"):
                cur.execute(f"ANALYZE {t}")
            con.commit()

            print("\n== Conferencia (para docs/evidencias) ==")
            for t in ("dim_fornecedor", "dim_socio", "ponte_empresa_socio"):
                n = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                mb = cur.execute("SELECT pg_total_relation_size(%s::regclass)/1e6",
                                 (t,)).fetchone()[0]
                print(f"   {t}: {n:,} linhas, {float(mb):.2f} MB")
            sem = cur.execute("""SELECT count(*) FROM dim_fornecedor f WHERE NOT EXISTS
                                 (SELECT 1 FROM ponte_empresa_socio p
                                  WHERE p.id_fornecedor = f.id_fornecedor)""").fetchone()[0]
            print(f"   empresas sem socio na base: {sem:,}")
            gr = cur.execute("""SELECT grupo_qualificacao, count(*) FROM ponte_empresa_socio
                                GROUP BY 1 ORDER BY 2 DESC""").fetchall()
            print("   vinculos por grupo:", ", ".join(f"{g}={n:,}" for g, n in gr))
            tot = cur.execute("SELECT pg_database_size(current_database())/1e6").fetchone()[0]
            print(f"   tamanho total do banco: {float(tot):.1f} MB (limite do Free Tier: ~1000 MB)")
    print(f"\n== Concluido em {time.time()-inicio:.1f}s ==")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Carga da Receita filtrada no Aiven (estrela)")
    p.add_argument("--simular", action="store_true", help="nao conecta; mostra contagens")
    p.add_argument("--uri", default=None)
    p.add_argument("--forcar-dimensoes", action="store_true",
                   help="recarrega dim_fornecedor e dim_socio mesmo se ja estiverem carregadas")
    a = p.parse_args()

    sal = os.environ.get("SALT_SOCIO", "")
    raizes = ler_raizes()
    print("== Receita filtrada (Parquet) ==")
    print(f"   raizes no cnpjs_raiz.csv: {len(raizes):,} | competencia: {COMPETENCIA}")
    checar_manifesto(raizes)
    forn, socio, ponte = montar(sal, raizes)
    print(f"\n   dim_fornecedor: {len(forn):,} | dim_socio: {len(socio):,} | "
          f"ponte: {len(ponte):,}")
    if not sal:
        print("   AVISO: SALT_SOCIO vazio. Definam no etl/.env antes da carga real.")
    if a.simular:
        return 0
    if not sal:
        print("ERRO: carga real exige SALT_SOCIO no etl/.env.")
        return 1

    uri = a.uri or os.environ.get("AIVEN_PG_URI")
    if not uri:
        print("ERRO: defina AIVEN_PG_URI no etl/.env (ou passe --uri).")
        return 1
    if "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"
    return carregar(uri, forn, socio, ponte, a.forcar_dimensoes)


if __name__ == "__main__":
    sys.exit(main())