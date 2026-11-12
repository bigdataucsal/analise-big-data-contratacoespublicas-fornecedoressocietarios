"""
Aplica o schema_estrela.sql consolidado (T2) no Aiven e confere o dicionario
de dados contra o banco real (information_schema).

O que faz, em ordem:
  1. Descarta as duas views materializadas do desenho antigo, se existirem.
  2. Migra o desenho antigo da fato: se a fato existente nao tiver as 5 colunas
     novas, descarta a fato e as dimensoes que sairam (dim_tempo, dim_orgao,
     dim_unidade, dim_tipo_contrato, dim_categoria_processo). Se a fato antiga
     tiver linhas, so descarta com --forcar.
  3. Cria as tabelas, os indices e as tabelas de agregado (tudo IF NOT EXISTS).
     Os agregados ficam vazios: quem os preenche e o construir_agregados.py.
  4. Compara colunas, tipos e nulidade com o dicionario e lista PK/FK/UNIQUE.

Uso (de dentro de etl/):
    python aplicar_schema.py --simular     # nao conecta
    python aplicar_schema.py
    python aplicar_schema.py --forcar
"""
import argparse
import os
import re
import sys
from pathlib import Path

import config   # tambem carrega o etl/.env

SQL = Path(__file__).resolve().parent / "schema_estrela.sql"
MARC_INDICES = "-- 4. Indices"
MARC_AGREGADOS = "-- 5. Agregados"
MINIMO_INDICES_CI = 10

ANTIGAS = ["dim_unidade", "dim_orgao", "dim_tempo",
           "dim_tipo_contrato", "dim_categoria_processo"]
VIEWS_ANTIGAS = ["mv_kpi_genero_setor", "mv_concentracao_socio"]

# tabela -> {coluna: (data_type do information_schema, is_nullable)}
ESPERADO = {
    "fato_contrato": {
        "numero_controle_pncp": ("text", "NO"),
        "codigo_ibge": ("text", "YES"),
        "cnpj_raiz_fornecedor": ("text", "YES"),
        "valor_global": ("numeric", "NO"),
        "ano_contrato": ("integer", "YES"),
    },
    "dim_fornecedor": {
        "id_fornecedor": ("integer", "NO"),
        "id_municipio_sede": ("integer", "YES"),
        "data_inicio_ativ": ("date", "YES"),
        "capital_social": ("numeric", "YES"),
        "cnpj_raiz": ("text", "NO"),
        "razao_social": ("text", "YES"),
        "tipo_pessoa": ("text", "YES"),
        "natureza_juridica": ("text", "YES"),
        "porte": ("text", "YES"),
        "cnae_principal": ("text", "YES"),
    },
    "dim_municipio": {
        "id_municipio": ("integer", "NO"),
        "pop_total": ("integer", "YES"),
        "pop_branca": ("integer", "YES"),
        "pop_preta": ("integer", "YES"),
        "pop_parda": ("integer", "YES"),
        "pop_amarela": ("integer", "YES"),
        "pop_indigena": ("integer", "YES"),
        "pct_negra": ("numeric", "YES"),
        "codigo_ibge": ("text", "NO"),
        "nome": ("text", "NO"),
        "uf_sigla": ("text", "NO"),
    },
    "dim_socio": {
        "id_socio": ("integer", "NO"),
        "confianca_genero": ("numeric", "YES"),
        "faixa_etaria": ("smallint", "YES"),
        "identificador_tipo": ("smallint", "YES"),
        "cpf_mascarado": ("text", "YES"),
        "identificador_pub": ("text", "NO"),
        "genero": ("text", "YES"),
    },
    "ponte_empresa_socio": {
        "id_fornecedor": ("integer", "NO"),
        "id_socio": ("integer", "NO"),
        "data_entrada": ("date", "YES"),
        "qualificacao": ("text", "NO"),
        "grupo_qualificacao": ("text", "YES"),
        "competencia": ("text", "NO"),
    },
    "agg_kpi_genero_setor": {
        "ano_contrato": ("smallint", "NO"),
        "cnae_principal": ("text", "NO"),
        "uf_sigla": ("text", "NO"),
        "faixa_pct_negra": ("text", "NO"),
        "genero_controle": ("text", "NO"),
        "contratos": ("bigint", "NO"),
        "valor_total": ("numeric", "NO"),
    },
    "agg_concentracao_socio": {
        "id_socio": ("integer", "NO"),
        "empresas": ("integer", "NO"),
        "contratos": ("bigint", "NO"),
        "valor_controlado": ("numeric", "NO"),
        "soma_sobreposta": ("boolean", "NO"),
        "identificador_pub": ("text", "NO"),
        "genero": ("text", "YES"),
    },
}


def secoes():
    ddl = SQL.read_text(encoding="utf-8")
    for marcador in (MARC_INDICES, MARC_AGREGADOS):
        if ddl.count(marcador) != 1:
            raise SystemExit(f"ERRO: o marcador {marcador!r} deve aparecer exatamente "
                             f"uma vez no schema_estrela.sql")
    tabelas, resto = ddl.split(MARC_INDICES)
    indices, agregados = resto.split(MARC_AGREGADOS)
    return tabelas, indices, agregados


def migrar(cur, forcar: bool) -> None:
    cols = {r[0] for r in cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'fato_contrato'").fetchall()}
    if not cols or cols == set(ESPERADO["fato_contrato"]):
        print("-- migracao: fato inexistente ou ja no desenho novo, nada a descartar")
        return
    n = cur.execute("SELECT count(*) FROM fato_contrato").fetchone()[0]
    if n > 0 and not forcar:
        raise SystemExit(f"ERRO: a fato existente tem desenho antigo e {n:,} linhas. Para descartar "
                         f"mesmo assim, rodem com --forcar (os contratos precisarao ser recarregados).")
    print(f"-- migracao: descartando fato de desenho antigo ({n:,} linhas) e dimensoes que sairam")
    cur.execute("DROP TABLE IF EXISTS fato_contrato")
    for t in ANTIGAS:
        cur.execute(f"DROP TABLE IF EXISTS {t}")


def conferir(cur) -> bool:
    print("\n== Conferencia do dicionario contra o banco ==")
    tudo_ok = True
    for tabela, esperado in ESPERADO.items():
        linhas = cur.execute(
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s", (tabela,)).fetchall()
        real = {c: (t, n) for c, t, n in linhas}
        faltam = sorted(set(esperado) - set(real))
        sobram = sorted(set(real) - set(esperado))
        difs = [f"{c}: esperado {esperado[c]}, real {real[c]}"
                for c in esperado if c in real and real[c] != esperado[c]]
        if faltam or sobram or difs:
            tudo_ok = False
            print(f"   DIVERGE  {tabela}")
            for item in faltam:
                print(f"            falta no banco: {item}")
            for item in sobram:
                print(f"            sobra no banco: {item}")
            for item in difs:
                print(f"            {item}")
        else:
            print(f"   OK       {tabela}: {len(esperado)} colunas")

    print("\n-- chaves (PK, FK, UNIQUE)")
    for tabela, tipo, definicao in cur.execute(
            "SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid) "
            "FROM pg_constraint WHERE connamespace = 'public'::regnamespace "
            "AND contype IN ('p', 'f', 'u') ORDER BY 1, 2, 3").fetchall():
        nome = {"p": "PK", "f": "FK", "u": "UNIQUE"}[tipo]
        print(f"   {tabela:<24} {nome:<7} {definicao}")

    n_ix = cur.execute("SELECT count(*) FROM pg_indexes WHERE schemaname = current_schema() "
                       "AND indexname LIKE 'ix_%'").fetchone()[0]
    print(f"\n-- indices ix_*: {n_ix} (o CI exige no minimo {MINIMO_INDICES_CI})")
    if n_ix < MINIMO_INDICES_CI:
        tudo_ok = False

    print("\n-- linhas por tabela")
    for tabela in ESPERADO:
        n = cur.execute(f"SELECT count(*) FROM {tabela}").fetchone()[0]
        print(f"   {tabela:<24} {n:>12,}")
    return tudo_ok


def main() -> int:
    p = argparse.ArgumentParser(description="Aplica o schema estrela consolidado no Aiven")
    p.add_argument("--simular", action="store_true", help="nao conecta; mostra o que seria aplicado")
    p.add_argument("--forcar", action="store_true", help="descarta a fato antiga mesmo com linhas")
    p.add_argument("--uri", default=None)
    a = p.parse_args()

    tabelas, indices, agregados = secoes()

    if a.simular:
        nomes_ix = (re.findall(r"CREATE (?:UNIQUE )?INDEX IF NOT EXISTS (ix_\w+)", indices + agregados)
                    + re.findall(r"CONSTRAINT (ix_\w+)", agregados))
        print("== Simulacao (nao conecta) ==")
        print("   tabelas :", ", ".join(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)",
                                                  tabelas + agregados)))
        print(f"   indices ix_*: {len(nomes_ix)} (o CI exige no minimo {MINIMO_INDICES_CI})")
        return 0

    uri = a.uri or os.environ.get("AIVEN_PG_URI")
    if not uri:
        print("ERRO: defina AIVEN_PG_URI no etl/.env (ou passe --uri).")
        return 1
    if "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"

    import psycopg
    with psycopg.connect(uri, autocommit=False) as con:
        cur = con.cursor()
        if cur.execute("SHOW default_transaction_read_only").fetchone()[0] == "on":
            raise SystemExit("ERRO: o banco esta em somente leitura (disco cheio?). "
                             "Confira o painel da Aiven.")
        for v in VIEWS_ANTIGAS:
            cur.execute(f"DROP MATERIALIZED VIEW IF EXISTS {v}")
        migrar(cur, a.forcar)
        con.commit()

        print("-- tabelas")
        cur.execute(tabelas)
        # A mascara do CPF colide entre pessoas diferentes: nao pode ser UNIQUE.
        cur.execute("ALTER TABLE dim_socio DROP CONSTRAINT IF EXISTS dim_socio_cpf_mascarado_key")
        con.commit()

        print("-- indices")
        cur.execute(indices)
        con.commit()

        print("-- agregados (tabelas vazias)")
        cur.execute(agregados)
        con.commit()

        ok = conferir(cur)
    print("\n== Schema aplicado" + ("" if ok else " COM DIVERGENCIAS") + " ==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())