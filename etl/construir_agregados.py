"""
Constroi os agregados materializados do painel (T2, semana 3):

    agg_kpi_genero_setor    contratos e valor por ano, CNAE, UF, faixa racial do
                            territorio e classificacao de controle da empresa
                            (RN-05). Alimenta o KPI 1 e a camada interseccional.
    agg_concentracao_socio  por socio pessoa fisica ligado a 2 ou mais empresas
                            com contrato (RN-07): empresas, contratos e valor.

Por que tabelas montadas aqui, e nao MATERIALIZED VIEW: o REFRESH de uma view e
uma consulta unica sobre a fato inteira, sem fatiar e sem retomar, e e o tipo
de consulta que derrubou o no gratuito no benchmark. Aqui cada agregado e:
  * montado dentro de UMA transacao: se a conexao cair, o agregado antigo
    continua intacto e o painel nao le dado pela metade;
  * calculado em FATIAS (hash do contrato) somadas ao agregado, de modo que
    cada passada agrega so 1/N da fato;
  * calculado contra tabelas auxiliares pequenas (empresas e municipios), sem
    mediana e sem ordenacao;
  * precedido de uma guarda de tamanho do banco.
Nada aqui foi medido contra o no gratuito: a primeira execucao deve ser
acompanhada pelo painel de uso da Aiven.

Uso (de dentro de etl/):
    python construir_agregados.py --simular
    python construir_agregados.py --orcamento        # so mede o disco
    python construir_agregados.py                    # constroi os dois
    python construir_agregados.py --so kpi           # ou: --so concentracao
    python construir_agregados.py --fatias 16 --limite-mb 550
"""
import argparse
import os
import sys
import time

import config   # tambem carrega o etl/.env

TETO_DISCO_MB = 1000
LIMITE_PADRAO_MB = 600
FATIAS_PADRAO = 8

TABELAS_ESPERADAS = ("fato_contrato", "dim_fornecedor", "dim_municipio", "dim_socio",
                     "ponte_empresa_socio", "agg_kpi_genero_setor", "agg_concentracao_socio")
AGREGADOS = ("agg_kpi_genero_setor", "agg_concentracao_socio")


def fatia(coluna: str, n: int, b: int) -> str:
    """Condicao da fatia b de n, por hash do texto (sem operador de resto)."""
    return f"mod(mod(hashtext({coluna}), {n}) + {n}, {n}) = {b}"


# Quadro societario de cada empresa: so a ponte e o dim_socio, que sao pequenos.
SQL_QUADRO = """
CREATE TEMP TABLE t_quadro ON COMMIT DROP AS
SELECT v.id_fornecedor,
       coalesce(bool_or(s.identificador_tipo = 1), false) AS tem_pj,
       count(*) FILTER (WHERE s.identificador_tipo = 2 AND v.elegivel) AS n,
       count(*) FILTER (WHERE s.identificador_tipo = 2 AND v.elegivel
                          AND s.genero = 'feminino') AS n_fem,
       count(*) FILTER (WHERE s.identificador_tipo = 2 AND v.elegivel
                          AND s.genero = 'masculino') AS n_masc,
       count(*) FILTER (WHERE s.identificador_tipo = 2 AND v.elegivel
                          AND s.genero = 'indeterminado') AS n_ind,
       count(*) FILTER (WHERE s.identificador_tipo = 2 AND v.elegivel
                          AND s.genero IS NULL) AS n_nulo
FROM (
    SELECT p.id_fornecedor, p.id_socio,
           bool_or(p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')) AS elegivel
    FROM ponte_empresa_socio p
    GROUP BY p.id_fornecedor, p.id_socio
) v
JOIN dim_socio s ON s.id_socio = v.id_socio
GROUP BY v.id_fornecedor
"""

# Classificacao de controle da empresa (RN-05), uma linha por fornecedor.
SQL_CONTROLE = """
CREATE TEMP TABLE t_empresa_controle ON COMMIT DROP AS
SELECT fo.cnpj_raiz,
       coalesce(fo.cnae_principal, 'sem cnae') AS cnae_principal,
       CASE
           WHEN q.id_fornecedor IS NULL THEN 'sem socio na base'
           WHEN q.n_nulo > 0            THEN 'nao classificado'
           WHEN q.tem_pj                THEN 'misto ou indeterminado'
           WHEN q.n = 0                 THEN 'indeterminado'
           WHEN q.n_ind  > q.n / 3.0    THEN 'misto ou indeterminado'
           WHEN q.n_fem  > q.n / 2.0    THEN 'feminino'
           WHEN q.n_masc > q.n / 2.0    THEN 'masculino'
           ELSE 'misto ou indeterminado'
       END AS genero_controle
FROM dim_fornecedor fo
LEFT JOIN t_quadro q ON q.id_fornecedor = fo.id_fornecedor
"""

SQL_MUNICIPIO = """
CREATE TEMP TABLE t_municipio ON COMMIT DROP AS
SELECT codigo_ibge, uf_sigla,
       CASE WHEN pct_negra IS NULL THEN 'sem dado'
            WHEN pct_negra >= 70   THEN 'alta'
            WHEN pct_negra >= 40   THEN 'media'
            ELSE 'baixa' END AS faixa_pct_negra
FROM dim_municipio
"""


def sql_kpi(n: int, b: int) -> str:
    return f"""
INSERT INTO agg_kpi_genero_setor AS a
    (ano_contrato, cnae_principal, uf_sigla, faixa_pct_negra, genero_controle,
     contratos, valor_total)
SELECT coalesce(f.ano_contrato, 0)::smallint,
       c.cnae_principal,
       coalesce(m.uf_sigla, 'sem uf'),
       coalesce(m.faixa_pct_negra, 'sem dado'),
       c.genero_controle,
       count(*),
       sum(f.valor_global)
FROM fato_contrato f
JOIN t_empresa_controle c ON c.cnpj_raiz = f.cnpj_raiz_fornecedor
LEFT JOIN t_municipio m   ON m.codigo_ibge = f.codigo_ibge
WHERE {fatia('f.numero_controle_pncp', n, b)}
GROUP BY 1, 2, 3, 4, 5
ON CONFLICT (ano_contrato, uf_sigla, genero_controle, faixa_pct_negra, cnae_principal)
DO UPDATE SET contratos = a.contratos + EXCLUDED.contratos,
              valor_total = a.valor_total + EXCLUDED.valor_total
"""


def sql_totais_empresa(n: int, b: int) -> str:
    # A fatia e por CNPJ, entao as fatias nao se sobrepoem: INSERT simples.
    return f"""
INSERT INTO t_empresa_contratos
SELECT fo.id_fornecedor, count(*), sum(f.valor_global)
FROM fato_contrato f
JOIN dim_fornecedor fo ON fo.cnpj_raiz = f.cnpj_raiz_fornecedor
WHERE {fatia('f.cnpj_raiz_fornecedor', n, b)}
GROUP BY fo.id_fornecedor
"""


SQL_CONCENTRACAO = """
WITH vinculo AS (
    SELECT DISTINCT p.id_socio, p.id_fornecedor
    FROM ponte_empresa_socio p
    JOIN dim_socio s              ON s.id_socio = p.id_socio AND s.identificador_tipo = 2
    JOIN t_empresa_contratos ce   ON ce.id_fornecedor = p.id_fornecedor
    WHERE p.grupo_qualificacao IN ('participacao', 'titularidade')
),
multiempresa AS (
    SELECT id_socio FROM vinculo GROUP BY id_socio HAVING count(*) >= 2
),
multi_por_empresa AS (
    SELECT v.id_fornecedor, count(*) AS n_multi
    FROM vinculo v
    JOIN multiempresa m ON m.id_socio = v.id_socio
    GROUP BY v.id_fornecedor
)
INSERT INTO agg_concentracao_socio
    (id_socio, identificador_pub, genero, empresas, contratos, valor_controlado, soma_sobreposta)
SELECT s.id_socio, s.identificador_pub, s.genero,
       count(*)::integer,
       sum(ce.contratos)::bigint,
       sum(ce.valor),
       bool_or(mpe.n_multi > 1)
FROM multiempresa m
JOIN dim_socio s              ON s.id_socio = m.id_socio
JOIN vinculo v                ON v.id_socio = m.id_socio
JOIN t_empresa_contratos ce   ON ce.id_fornecedor = v.id_fornecedor
JOIN multi_por_empresa mpe    ON mpe.id_fornecedor = v.id_fornecedor
GROUP BY s.id_socio, s.identificador_pub, s.genero
"""


def preparar(cur) -> None:
    """Ajustes validos so dentro da transacao corrente."""
    cur.execute("SET LOCAL work_mem = '16MB'")
    cur.execute("SET LOCAL max_parallel_workers_per_gather = 0")
    cur.execute("SET LOCAL statement_timeout = '15min'")
    cur.execute("SET LOCAL synchronous_commit = off")


def mb_banco(cur) -> float:
    return float(cur.execute("SELECT pg_database_size(current_database()) / 1e6").fetchone()[0])


def temp_mb(cur) -> float:
    return float(cur.execute("SELECT temp_bytes / 1e6 FROM pg_stat_database "
                             "WHERE datname = current_database()").fetchone()[0])


def verificar(con, limite_mb: float) -> None:
    cur = con.cursor()
    if cur.execute("SHOW default_transaction_read_only").fetchone()[0] == "on":
        raise SystemExit("ERRO: o banco esta em somente leitura (disco cheio?). "
                         "Confiram o painel da Aiven.")
    faltam = [t for t in TABELAS_ESPERADAS
              if cur.execute("SELECT to_regclass(%s)", (t,)).fetchone()[0] is None]
    if faltam:
        raise SystemExit(f"ERRO: tabelas ausentes: {faltam}. Rodem antes: python aplicar_schema.py")
    nova = cur.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name = 'fato_contrato' AND column_name = 'cnpj_raiz_fornecedor'").fetchone()
    if not nova:
        raise SystemExit("ERRO: a fato esta no desenho antigo. Rodem antes: python aplicar_schema.py")

    mb = mb_banco(cur)
    print(f"   banco: {mb:.1f} MB (teto de seguranca deste script: {limite_mb:.0f} MB; "
          f"disco do servico: {TETO_DISCO_MB} MB)")
    if mb > limite_mb:
        raise SystemExit(f"ERRO: o banco ja esta em {mb:.1f} MB, acima do teto de {limite_mb:.0f} MB. "
                         f"Liberem espaco (VACUUM, indices) antes de construir os agregados.")
    n_fato = cur.execute("SELECT count(*) FROM fato_contrato").fetchone()[0]
    print(f"   fato_contrato: {n_fato:,} linhas")
    if n_fato == 0:
        raise SystemExit("ERRO: a fato esta vazia. Carreguem os contratos antes de construir os agregados.")
    n_soc, n_nulo = cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE genero IS NULL) FROM dim_socio "
        "WHERE identificador_tipo = 2").fetchone()
    print(f"   socios pessoa fisica: {n_soc:,}, sem genero classificado: {n_nulo:,}")
    if n_soc and n_nulo == n_soc:
        print("   AVISO: nenhum socio tem genero. As empresas com socio sairao como "
              "'nao classificado' ate o genero ser carregado.")
    con.commit()


def construir_kpi(con, n: int) -> None:
    print("\n-- agg_kpi_genero_setor")
    t0 = time.time()
    cur = con.cursor()
    preparar(cur)
    cur.execute(SQL_QUADRO)
    cur.execute(SQL_CONTROLE)
    cur.execute(SQL_MUNICIPIO)
    cur.execute("ANALYZE t_empresa_controle")
    cur.execute("ANALYZE t_municipio")
    dist = cur.execute("SELECT genero_controle, count(*) FROM t_empresa_controle "
                       "GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("   controle das empresas:", ", ".join(f"{g}={c:,}" for g, c in dist))
    cur.execute("TRUNCATE agg_kpi_genero_setor")
    for b in range(n):
        cur.execute(sql_kpi(n, b))
        print(f"   fatia {b + 1}/{n}: {cur.rowcount:,} grupos tocados ({time.time() - t0:.0f}s)")
    con.commit()


def construir_concentracao(con, n: int) -> None:
    print("\n-- agg_concentracao_socio")
    t0 = time.time()
    cur = con.cursor()
    preparar(cur)
    cur.execute("CREATE TEMP TABLE t_empresa_contratos (id_fornecedor INTEGER PRIMARY KEY, "
                "contratos BIGINT NOT NULL, valor NUMERIC(20,2) NOT NULL) ON COMMIT DROP")
    for b in range(n):
        cur.execute(sql_totais_empresa(n, b))
        print(f"   totais por empresa, fatia {b + 1}/{n}: {cur.rowcount:,} empresas "
              f"({time.time() - t0:.0f}s)")
    cur.execute("ANALYZE t_empresa_contratos")
    cur.execute("TRUNCATE agg_concentracao_socio")
    cur.execute(SQL_CONCENTRACAO)
    print(f"   socios multiempresa gravados: {cur.rowcount:,} ({time.time() - t0:.0f}s)")
    con.commit()


def orcamento(con, limite_mb: float) -> None:
    cur = con.cursor()
    print("\n== Orcamento de disco ==")
    linhas = cur.execute(
        "SELECT c.relname, c.reltuples::bigint, pg_relation_size(c.oid), "
        "pg_indexes_size(c.oid), pg_total_relation_size(c.oid) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 5 DESC").fetchall()
    print(f"   {'tabela':<24}{'linhas (est.)':>15}{'dados MB':>11}{'indices MB':>12}{'total MB':>10}")
    for nome, linhas_est, dados, indices, total in linhas:
        est = f"{linhas_est:,}" if linhas_est >= 0 else "n/d"
        print(f"   {nome:<24}{est:>15}{dados / 1e6:>11.1f}{indices / 1e6:>12.1f}{total / 1e6:>10.1f}")
    mb = mb_banco(cur)
    print(f"\n   banco inteiro (pg_database_size): {mb:.1f} MB")
    print(f"   teto de seguranca: {limite_mb:.0f} MB | disco do servico: {TETO_DISCO_MB} MB")
    print(f"   temporarios acumulados (pg_stat_database): {temp_mb(cur):.1f} MB")
    print("   " + ("OK: dentro do teto de seguranca." if mb <= limite_mb
                    else "ALERTA: acima do teto de seguranca."))
    print("   O disco do servico conta tambem o log de transacoes, os temporarios e o sistema, "
          "que pg_database_size nao mostra.")
    print("   Confiram o percentual de armazenamento no painel da Aiven e guardem o print "
          "em docs/evidencias/.")
    con.commit()


def main() -> int:
    p = argparse.ArgumentParser(description="Constroi os agregados materializados do painel")
    p.add_argument("--simular", action="store_true", help="nao conecta; mostra o plano")
    p.add_argument("--orcamento", action="store_true", help="so mede o disco e compara com o teto")
    p.add_argument("--so", choices=["kpi", "concentracao"], help="constroi so um dos agregados")
    p.add_argument("--fatias", type=int, default=FATIAS_PADRAO, help="numero de fatias por agregado")
    p.add_argument("--limite-mb", type=float, default=LIMITE_PADRAO_MB,
                   help="teto de seguranca para pg_database_size")
    p.add_argument("--uri", default=None)
    a = p.parse_args()
    if a.fatias < 1:
        print("ERRO: --fatias precisa ser 1 ou mais.")
        return 1

    if a.simular:
        print("== Simulacao (nao conecta) ==")
        print(f"   fatias por agregado: {a.fatias} | teto de seguranca: {a.limite_mb:.0f} MB")
        print("   1. agg_kpi_genero_setor: quadro societario -> controle por empresa -> "
              f"{a.fatias} passadas sobre a fato, somando ao agregado")
        print("   2. agg_concentracao_socio: totais por empresa em "
              f"{a.fatias} fatias por CNPJ -> uma consulta sobre a ponte")
        print("   Cada agregado roda numa transacao so, e o antigo fica intacto se a conexao cair.")
        return 0

    uri = a.uri or os.environ.get("AIVEN_PG_URI")
    if not uri:
        print("ERRO: defina AIVEN_PG_URI no etl/.env (ou passe --uri).")
        return 1
    if "sslmode=" not in uri:
        uri += ("&" if "?" in uri else "?") + "sslmode=require"

    import psycopg
    inicio = time.time()
    with psycopg.connect(uri, autocommit=False) as con:
        if a.orcamento:
            orcamento(con, a.limite_mb)
            return 0
        print("== Agregados materializados ==")
        verificar(con, a.limite_mb)
        cur = con.cursor()
        antes_mb, antes_tmp = mb_banco(cur), temp_mb(cur)
        con.commit()

        if a.so in (None, "kpi"):
            construir_kpi(con, a.fatias)
        if a.so in (None, "concentracao"):
            construir_concentracao(con, a.fatias)

        for t in AGREGADOS:
            cur.execute(f"ANALYZE {t}")
        con.commit()

        print("\n== Conferencia (para docs/evidencias) ==")
        for t in AGREGADOS:
            n = cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            mb = cur.execute("SELECT pg_total_relation_size(%s::regclass) / 1e6", (t,)).fetchone()[0]
            print(f"   {t}: {n:,} linhas, {float(mb):.2f} MB")
        n_fato, v_fato = cur.execute("SELECT count(*), sum(valor_global) FROM fato_contrato").fetchone()
        c_kpi, v_kpi = cur.execute("SELECT sum(contratos), sum(valor_total) "
                                   "FROM agg_kpi_genero_setor").fetchone()
        print(f"   fato (todas): {n_fato:,} contratos, R$ {float(v_fato):,.2f}")
        print(f"   KPI (so fornecedor com raiz de CNPJ): {int(c_kpi or 0):,} contratos, "
              f"R$ {float(v_kpi or 0):,.2f}")
        print("   A diferenca sao os contratos sem raiz de CNPJ (RN-01), que ficam fora dos KPIs.")
        con.commit()
        print(f"\n   banco: {antes_mb:.1f} MB antes, {mb_banco(cur):.1f} MB depois")
        print(f"   temporarios acumulados: +{temp_mb(cur) - antes_tmp:.1f} MB "
              f"(estatistica acumulada, atualizada ao fim da transacao)")
        con.commit()
        orcamento(con, a.limite_mb)
    print(f"\n== Concluido em {time.time() - inicio:.1f}s ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())