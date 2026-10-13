"""Teste comparativo S2: a mesma junção (empresas x sócios) rodada em Pandas sobre CSV e em"""
from __future__ import annotations

import argparse
import logging
import os
import time
import zipfile
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import config as cfg
from baixar_receita import LAYOUTS, RAW_DIR, listar_membros_zip, ler_amostra

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comparar_pandas_postgres")

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
INVENTORY_DIR = REPO_ROOT / cfg.DIR_INVENTARIO
INVENTORY_DIR.mkdir(parents=True, exist_ok=True)


def montar_conexao() -> str:
    uri = os.getenv("AIVEN_SERVICE_URI")
    if uri:
        return uri if "sslmode=" in uri else uri + ("&" if "?" in uri else "?") + "sslmode=require"

    host = os.getenv("AIVEN_HOST")
    port = os.getenv("AIVEN_PORT")
    dbname = os.getenv("AIVEN_DBNAME", "defaultdb")
    user = os.getenv("AIVEN_USER", "avnadmin")
    password = os.getenv("AIVEN_PASSWORD")
    faltando = [n for n, v in [("AIVEN_HOST", host), ("AIVEN_PORT", port), ("AIVEN_PASSWORD", password)] if not v]
    if faltando:
        raise RuntimeError(
            f"Faltam variáveis no .env: {', '.join(faltando)} "
            "(ou definam AIVEN_SERVICE_URI com a string de conexão completa do Aiven)."
        )
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


def montar_amostra(n_empresas: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    membros = listar_membros_zip(RAW_DIR)
    if not membros:
        raise RuntimeError(f"Nenhum arquivo em {RAW_DIR}, rodem baixar_receita.py primeiro.")

    membros_empresas = [m for m in membros if m["layout"] == "EMPRECSV"]
    membros_socios = [m for m in membros if m["layout"] == "SOCIOCSV"]
    if not membros_empresas or not membros_socios:
        raise RuntimeError("Faltam arquivos de EMPRECSV ou SOCIOCSV em dados/raw/receita, "
                            "rodem baixar_receita.py sem --filtro antes.")

    primeiro = membros_empresas[0]
    empresas = ler_amostra(primeiro["zip"], primeiro["membro"], "EMPRECSV", nrows=n_empresas)
    cnpjs_alvo = set(empresas["cnpj_basico"])
    log.info("%d empresas de teste | %d CNPJs alvo", len(empresas), len(cnpjs_alvo))

    colunas_socios = [c for c, _ in LAYOUTS["SOCIOCSV"]]
    partes = []
    for item in membros_socios:
        with zipfile.ZipFile(item["zip"]) as arq, arq.open(item["membro"]) as f:
            for pedaco in pd.read_csv(f, sep=";", header=None, names=colunas_socios, encoding="latin-1",
                                       dtype=str, chunksize=300_000, on_bad_lines="warn", engine="python"):
                trecho = pedaco[pedaco["cnpj_basico"].isin(cnpjs_alvo)]
                if not trecho.empty:
                    partes.append(trecho)
    socios = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=colunas_socios)
    log.info("%d sócios encontrados pra essas empresas (varrendo todos os shards de sócios)", len(socios))
    return empresas, socios


def rodar_teste(empresas: pd.DataFrame, socios: pd.DataFrame, engine) -> pd.DataFrame:
    t0 = time.perf_counter()
    resultado_pandas = empresas.merge(socios, on="cnpj_basico", how="inner")
    t_pandas = time.perf_counter() - t0
    log.info("Pandas: %.4fs -> %d linhas", t_pandas, len(resultado_pandas))

    t0 = time.perf_counter()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS teste_empresas, teste_socios"))
    empresas.to_sql("teste_empresas", engine, if_exists="replace", index=False, chunksize=10_000, method="multi")
    socios.to_sql("teste_socios", engine, if_exists="append", index=False, chunksize=10_000, method="multi")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE teste_empresas ADD PRIMARY KEY (cnpj_basico)"))
        conn.execute(text("CREATE INDEX idx_teste_socios_cnpj ON teste_socios (cnpj_basico)"))
    t_carga = time.perf_counter() - t0
    log.info("Carga no Aiven (com índice): %.4fs", t_carga)

    consulta = text("""
        SELECT e.cnpj_basico, e.razao_social, e.capital_social,
               s.nome_socio_razao_social, s.qualificacao_socio
        FROM teste_empresas e
        JOIN teste_socios s ON s.cnpj_basico = e.cnpj_basico
    """)
    t0 = time.perf_counter()
    with engine.connect() as conn:
        resultado_sql = pd.read_sql(consulta, conn)
    t_postgres = time.perf_counter() - t0
    log.info("Postgres: %.4fs -> %d linhas", t_postgres, len(resultado_sql))

    if len(resultado_pandas) != len(resultado_sql):
        log.warning("Pandas (%d linhas) e Postgres (%d linhas) discordam, investiguem antes de concluir.",
                    len(resultado_pandas), len(resultado_sql))
    else:
        log.info("OK, os dois métodos concordam no número de linhas do resultado.")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS teste_empresas, teste_socios"))
    log.info("Tabelas de teste removidas do Aiven (plano gratuito tem só ~1GB).")

    return pd.DataFrame([
        {"metodo": "Pandas (dados em memória)", "linhas_empresas": len(empresas),
         "linhas_socios": len(socios), "linhas_resultado": len(resultado_pandas),
         "tempo_segundos": round(t_pandas, 4)},
        {"metodo": "PostgreSQL / Aiven (com índice)", "linhas_empresas": len(empresas),
         "linhas_socios": len(socios), "linhas_resultado": len(resultado_sql),
         "tempo_segundos": round(t_postgres, 4)},
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n-empresas", type=int, default=200_000,
                         help="quantas empresas usar na amostra de teste (padrão: 200000)")
    args = parser.parse_args(argv)

    engine = create_engine(montar_conexao())
    with engine.connect() as conn:
        versao = conn.execute(text("SELECT version()")).scalar()
    log.info("Conectado ao Aiven: %s", versao)

    empresas, socios = montar_amostra(args.n_empresas)
    comparacao = rodar_teste(empresas, socios, engine)

    destino = INVENTORY_DIR / "teste_comparativo_s2.csv"
    comparacao.to_csv(destino, index=False)
    print(comparacao.to_string(index=False))
    log.info("Salvo em %s", destino)

    log.info(
        "Nota pra conclusão: em amostra pequena/média é NORMAL o Pandas ganhar do Postgres numa "
        "junção isolada (overhead de rede/planejamento). Não invalida a escolha do banco, o "
        "argumento real é que a base inteira não cabe em memória, o dashboard repete a mesma "
        "consulta pra usuários diferentes, e só o banco garante integridade referencial e concorrência."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
