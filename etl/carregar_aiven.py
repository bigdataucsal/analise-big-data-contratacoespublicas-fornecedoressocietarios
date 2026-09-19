"""
Carga dos contratos tratados no Aiven for PostgreSQL.
=====================================================================
Le os CSV gerados pelo tratar_contratos.py e carrega via COPY, que e a
via rapida do Postgres para volume -- um INSERT por linha levaria horas
onde o COPY leva minutos.

Pre-requisitos:
    pip install "psycopg[binary]" python-dotenv
    python tratar_contratos.py          # gera os CSV

Credencial no .env (ja coberto pelo .gitignore, nao committem):
    AIVEN_PG_URI=postgres://usuario:senha@host.aivencloud.com:12345/defaultdb?sslmode=require

Uso (rodar de dentro de etl/):
    python carregar_aiven.py --simular      # nao conecta, so confere os CSV
    python carregar_aiven.py                # carga completa (substitui)
    python carregar_aiven.py --modo incremental   # upsert, preserva o resto

Modos
-----
substituir  : TRUNCATE + COPY. Mais rapido. Use na carga completa.
incremental : COPY numa staging UNLOGGED e depois INSERT ... ON CONFLICT
              DO UPDATE. Mais lento, porem idempotente -- reprocessar um
              mes atualiza as linhas em vez de estourar a chave primaria.

Ordem da carga
--------------
Tabela -> COPY -> indices -> ANALYZE. Os indices ficam por ultimo de
proposito: criar tudo de uma vez no fim e bem mais rapido do que manter
as arvores atualizadas durante o COPY.
"""

import argparse
import os
import sys
import time
from pathlib import Path

DIR_CSV_PADRAO = Path("dados/saida_postgres/contratos")
TABELA = "contratos"

# Precisa bater, em ordem, com o cabecalho do CSV e com as colunas 1-49 do
# schema_postgres.sql. ano_mes fica de fora: e coluna gerada no Postgres.
COLUNAS = [
    "numero_controle_pncp", "numero_controle_compra", "numero_controle_ata",
    "ano_contrato", "sequencial_contrato", "numero_contrato_empenho", "processo",
    "data_publicacao", "data_atualizacao", "data_atualizacao_global",
    "data_assinatura", "data_vigencia_inicio", "data_vigencia_fim",
    "valor_inicial", "valor_global", "valor_parcela", "valor_acumulado",
    "numero_parcelas", "numero_retificacao",
    "ni_fornecedor", "tipo_pessoa", "nome_fornecedor", "codigo_pais_fornecedor",
    "cnpj_raiz_fornecedor", "ni_subcontratado", "nome_subcontratado",
    "orgao_cnpj", "orgao_razao_social", "orgao_poder", "orgao_esfera",
    "uf_sigla", "uf_nome", "municipio_nome", "codigo_ibge", "codigo_unidade",
    "nome_unidade", "orgao_subrogado_cnpj", "unidade_subrogada_codigo",
    "tipo_contrato_id", "tipo_contrato_nome", "categoria_processo_id",
    "categoria_processo_nome", "receita", "emenda_parlamentar", "fruto_adesao",
    "tem_remanejamento", "objeto_contrato", "informacao_complementar",
    "identificador_cipi",
]


def fmt_br(valor, casas: int = 0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def listar_csvs(dir_csv: Path) -> list:
    """CSV em ordem de mes, para a tabela ficar quase ordenada por
    data_publicacao -- e o que faz o indice BRIN do schema valer a pena."""
    return sorted(dir_csv.rglob("*.csv"), key=lambda p: (p.parent.name, p.name))


def conferir_cabecalho(caminho: Path) -> None:
    with open(caminho, encoding="utf-8") as f:
        cabecalho = f.readline().strip().split(",")
    if cabecalho != COLUNAS:
        faltando = [c for c in COLUNAS if c not in cabecalho]
        sobrando = [c for c in cabecalho if c not in COLUNAS]
        raise SystemExit(
            f"ERRO: {caminho.name} nao bate com o schema.\n"
            f"  esperado {len(COLUNAS)} colunas, veio {len(cabecalho)}\n"
            f"  faltando: {faltando or '-'}\n"
            f"  sobrando: {sobrando or '-'}\n"
            f"  Se o SELECT do tratar_contratos.py mudou, atualizem COLUNAS "
            f"aqui e o schema_postgres.sql junto."
        )


def sql_copy(tabela: str) -> str:
    colunas = ", ".join(COLUNAS)
    # NULL '' porque o DuckDB grava nulo como campo vazio. HEADER MATCH nao
    # serve: a lista explicita e o que garante a posicao correta.
    return (f"COPY {tabela} ({colunas}) FROM STDIN "
            f"WITH (FORMAT CSV, HEADER, NULL '')")


def carregar(uri: str, dir_csv: Path, modo: str, criar_indices: bool) -> int:
    import psycopg

    arquivos = listar_csvs(dir_csv)
    inicio = time.time()

    with psycopg.connect(uri, autocommit=False) as con:
        with con.cursor() as cur:
            # Numa carga em lote nao ha o que perder esperando o fsync de
            # cada commit: se cair no meio, o remedio e refazer a carga.
            cur.execute("SET synchronous_commit = off")
            cur.execute("SET maintenance_work_mem = '512MB'")  # p/ os indices

            print("-- criando tabela (se nao existir)")
            ddl = Path("schema_postgres.sql").read_text(encoding="utf-8")
            corpo_tabela = ddl.split("-- 2. Indices")[0]
            cur.execute(corpo_tabela)
            con.commit()

            if modo == "substituir":
                # Derruba os indices de uma execucao anterior antes do COPY.
                # Sem isso, a promessa de "indices so no fim" valeria apenas
                # na primeira carga -- da segunda em diante o COPY entraria
                # com as arvores todas montadas.
                print(f"-- removendo indices anteriores")
                cur.execute("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = %s AND indexname LIKE 'ix_%%'
                """, (TABELA,))
                for (nome,) in cur.fetchall():
                    cur.execute(f"DROP INDEX IF EXISTS {nome}")
                con.commit()

                print(f"-- TRUNCATE {TABELA}")
                cur.execute(f"TRUNCATE {TABELA}")
                destino = TABELA
            else:
                destino = f"{TABELA}_stg"
                print(f"-- staging UNLOGGED {destino}")
                cur.execute(f"DROP TABLE IF EXISTS {destino}")
                # UNLOGGED: a staging nao precisa sobreviver a queda do
                # servidor, entao pular o WAL economiza metade da escrita.
                cur.execute(f"CREATE UNLOGGED TABLE {destino} "
                            f"(LIKE {TABELA} INCLUDING DEFAULTS "
                            f" EXCLUDING CONSTRAINTS EXCLUDING INDEXES)")
                cur.execute(f"ALTER TABLE {destino} DROP COLUMN IF EXISTS ano_mes")
                con.commit()

            total = 0
            for i, caminho in enumerate(arquivos, 1):
                conferir_cabecalho(caminho)
                t = time.time()
                with open(caminho, "r", encoding="utf-8", newline="") as f:
                    with cur.copy(sql_copy(destino)) as copia:
                        while bloco := f.read(1 << 20):   # 1 MB por vez
                            copia.write(bloco)
                con.commit()
                linhas = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                total += linhas
                mes = caminho.parent.name.replace("ano_mes=", "")
                print(f"   [{i}/{len(arquivos)}] {mes}: {fmt_br(linhas)} linhas "
                      f"em {time.time()-t:.1f}s")

            if modo == "incremental":
                print(f"-- upsert {destino} -> {TABELA}")
                colunas = ", ".join(COLUNAS)
                atualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUNAS
                                     if c != "numero_controle_pncp")
                t = time.time()
                cur.execute(f"""
                    INSERT INTO {TABELA} ({colunas})
                    SELECT {colunas} FROM {destino}
                    ON CONFLICT (numero_controle_pncp) DO UPDATE SET {atualiza}
                """)
                con.commit()
                print(f"   {fmt_br(cur.rowcount)} linhas inseridas/atualizadas "
                      f"em {time.time()-t:.1f}s")
                cur.execute(f"DROP TABLE {destino}")
                con.commit()

            if criar_indices:
                print("-- criando indices (depois da carga, de proposito)")
                t = time.time()
                corpo_indices = ddl.split("-- 2. Indices")[1].split("-- 3. Exemplos")[0]
                for comando in [c.strip() for c in corpo_indices.split(";") if c.strip()]:
                    if comando.lstrip().startswith("--"):
                        continue
                    try:
                        cur.execute(comando)
                        con.commit()
                    except Exception as e:
                        # O pg_trgm e o indice que depende dele sao os unicos
                        # que exigem permissao de extensao. Se o papel do
                        # Aiven nao tiver, o resto da carga ja esta no lugar
                        # e nao faz sentido derrubar tudo por causa disso.
                        con.rollback()
                        resumo = " ".join(comando.split())[:70]
                        print(f"   AVISO: falhou e foi ignorado -> {resumo}...")
                        print(f"          {type(e).__name__}: {e}")
                print(f"   indices prontos em {time.time()-t:.1f}s")

            print(f"-- ANALYZE {TABELA}")
            cur.execute(f"ANALYZE {TABELA}")
            con.commit()

            final = cur.execute(f"SELECT count(*) FROM {TABELA}").fetchone()[0]

    print(f"\n== Carga concluida em {time.time()-inicio:.1f}s ==")
    print(f"   {fmt_br(total)} linhas enviadas, {fmt_br(final)} na tabela {TABELA}")
    return 0


def simular(dir_csv: Path) -> int:
    arquivos = listar_csvs(dir_csv)
    if not arquivos:
        print(f"ERRO: nenhum CSV em {dir_csv}. Rode antes: python tratar_contratos.py")
        return 1

    print(f"== Simulacao (nao conecta no Aiven) ==")
    print(f"   {len(arquivos)} arquivo(s) em {dir_csv}")
    total_linhas = total_bytes = 0
    for caminho in arquivos:
        conferir_cabecalho(caminho)
        with open(caminho, encoding="utf-8") as f:
            linhas = sum(1 for _ in f) - 1          # menos o cabecalho
        tamanho = caminho.stat().st_size
        total_linhas += linhas
        total_bytes += tamanho
        mes = caminho.parent.name.replace("ano_mes=", "")
        print(f"   {mes}: {fmt_br(linhas):>11} linhas, {tamanho/1e6:7.1f} MB  [cabecalho OK]")

    print(f"\n   total: {fmt_br(total_linhas)} linhas, {total_bytes/1e6:.1f} MB")
    print(f"   destino: tabela {TABELA}, {len(COLUNAS)} colunas via COPY")
    print(f"   ano_mes nao vai no COPY -- e coluna gerada no Postgres")
    print("\n   Tudo certo. Para carregar de verdade:")
    print("     1. AIVEN_PG_URI=... no .env")
    print("     2. python carregar_aiven.py")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Carrega os contratos tratados no Aiven for PostgreSQL")
    p.add_argument("--modo", choices=["substituir", "incremental"],
                   default="substituir",
                   help="substituir: TRUNCATE + COPY (rapido). "
                        "incremental: staging + upsert (idempotente)")
    p.add_argument("--dir-csv", default=str(DIR_CSV_PADRAO),
                   help=f"pasta dos CSV (padrao: {DIR_CSV_PADRAO})")
    p.add_argument("--sem-indices", action="store_true",
                   help="nao criar os indices no fim")
    p.add_argument("--simular", action="store_true",
                   help="nao conecta: so confere os CSV contra o schema")
    p.add_argument("--uri", default=None,
                   help="URI do Postgres (padrao: AIVEN_PG_URI do .env)")
    args = p.parse_args()

    dir_csv = Path(args.dir_csv)
    if not dir_csv.is_dir():
        print(f"ERRO: {dir_csv} nao existe. Rode antes: python tratar_contratos.py")
        return 1

    if args.simular:
        return simular(dir_csv)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    uri = args.uri or os.environ.get("AIVEN_PG_URI")
    if not uri:
        print("ERRO: defina AIVEN_PG_URI no .env (ou passe --uri).")
        print("  Formato: postgres://usuario:senha@host.aivencloud.com:PORTA/"
              "defaultdb?sslmode=require")
        print("  O .gitignore ja cobre o .env -- nao committem a credencial.")
        return 1

    if "sslmode=" not in uri:
        # O Aiven so aceita conexao TLS; sem isso a conexao e recusada e o
        # erro que volta nao diz o motivo.
        uri += ("&" if "?" in uri else "?") + "sslmode=require"

    arquivos = listar_csvs(dir_csv)
    if not arquivos:
        print(f"ERRO: nenhum CSV em {dir_csv}. Rode antes: python tratar_contratos.py")
        return 1

    # Sem host nem usuario no log: a URI carrega a senha.
    print(f"== Carga no Aiven for PostgreSQL ==")
    print(f"   modo   : {args.modo}")
    print(f"   origem : {dir_csv} ({len(arquivos)} arquivo(s))")
    return carregar(uri, dir_csv, args.modo, not args.sem_indices)


if __name__ == "__main__":
    sys.exit(main())
