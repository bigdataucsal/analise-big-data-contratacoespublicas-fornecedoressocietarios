"""
Tratamento dos contratos brutos do PNCP -> camada analitica + carga no Aiven.
=============================================================================
Le os JSONL brutos, achata o aninhado, tipa, normaliza, deduplica e grava:

  1. dados/parquet/contratos/ano_mes=AAAA-MM/*.parquet  (camada analitica)
  2. dados/saida_postgres/contratos/ano_mes=AAAA-MM/*.csv  (carga no Aiven)

NAO escreve em dados/raw/. Os arquivos do extrator original
(contratos_2025.jsonl e contratos_2025.checkpoint) sao lidos e nunca alterados.

Por que DuckDB e nao pandas
---------------------------
O bruto completo e ~2 milhoes de contratos em JSON aninhado (~3,5 GB). Com
pandas isso exige carregar tudo em memoria e achatar linha a linha em Python.
O DuckDB le o glob de JSONL em paralelo, achata em SQL, processa fora da
memoria (nao precisa de RAM maior que o dado) e escreve Parquet particionado
num unico comando. Sem cluster, sem JVM, uma dependencia so -- que e o ponto
certo para este volume numa maquina. PySpark resolveria, mas num no unico
paga JVM e shuffle sem ganho.

Deduplicacao
------------
Obrigatoria, nao opcional: o bruto atual ja tem 400 duplicatas (18.900 linhas
para 18.500 chaves unicas), porque o resume do extrator original regravou
paginas ja baixadas. A chave natural e numeroControlePNCP; quando ela repete,
fica a versao com dataAtualizacaoGlobal mais recente.

Uso (rodar de dentro de etl/):
    python tratar_contratos.py                    # parquet + csv
    python tratar_contratos.py --formato parquet  # so a camada analitica
    python tratar_contratos.py --resumo           # nao grava, so perfila
    python tratar_contratos.py --threads 8
"""

import argparse
import shutil
import sys
import time
from decimal import Decimal
from pathlib import Path

import duckdb

import config

# Schema explicito de proposito. Com inferencia automatica, um shard em que
# orgaoSubRogado e sempre nulo infere VARCHAR enquanto outro infere STRUCT, e
# a leitura do glob quebra. Declarar resolve e documenta o contrato do dado.
STRUCT_ORGAO = "STRUCT(cnpj VARCHAR, razaoSocial VARCHAR, poderId VARCHAR, esferaId VARCHAR)"
STRUCT_UNIDADE = ("STRUCT(ufNome VARCHAR, codigoUnidade VARCHAR, nomeUnidade VARCHAR, "
                  "ufSigla VARCHAR, municipioNome VARCHAR, codigoIbge VARCHAR)")
STRUCT_DOMINIO = "STRUCT(id INTEGER, nome VARCHAR)"

COLUNAS_BRUTO = {
    "numeroControlePNCP": "VARCHAR",
    "numeroControlePncpCompra": "VARCHAR",
    "numeroControlePncpAta": "VARCHAR",
    "anoContrato": "INTEGER",
    "sequencialContrato": "INTEGER",
    "numeroContratoEmpenho": "VARCHAR",
    "numeroParcelas": "INTEGER",
    "numeroRetificacao": "INTEGER",
    "processo": "VARCHAR",
    "objetoContrato": "VARCHAR",
    "informacaoComplementar": "VARCHAR",
    # Datas entram como texto e sao convertidas com TRY_CAST mais adiante:
    # uma linha com data torta vira NULL em vez de derrubar a carga inteira.
    "dataAssinatura": "VARCHAR",
    "dataVigenciaInicio": "VARCHAR",
    "dataVigenciaFim": "VARCHAR",
    "dataPublicacaoPncp": "VARCHAR",
    "dataAtualizacao": "VARCHAR",
    "dataAtualizacaoGlobal": "VARCHAR",
    "niFornecedor": "VARCHAR",
    "tipoPessoa": "VARCHAR",
    "nomeRazaoSocialFornecedor": "VARCHAR",
    "codigoPaisFornecedor": "VARCHAR",
    "niFornecedorSubContratado": "VARCHAR",
    "nomeFornecedorSubContratado": "VARCHAR",
    "tipoPessoaSubContratada": "VARCHAR",
    "valorInicial": "DOUBLE",
    "valorParcela": "DOUBLE",
    "valorGlobal": "DOUBLE",
    "valorAcumulado": "DOUBLE",
    "receita": "BOOLEAN",
    "emendaParlamentar": "BOOLEAN",
    "frutoAdesao": "BOOLEAN",
    "temRemanejamento": "BOOLEAN",
    "identificadorCipi": "VARCHAR",
    "urlCipi": "VARCHAR",
    "usuarioNome": "VARCHAR",
    "tipoContrato": STRUCT_DOMINIO,
    "categoriaProcesso": STRUCT_DOMINIO,
    "orgaoEntidade": STRUCT_ORGAO,
    "orgaoSubRogado": STRUCT_ORGAO,
    "unidadeOrgao": STRUCT_UNIDADE,
    "unidadeSubRogada": STRUCT_UNIDADE,
}

# SELECT do tratamento. Nomes em snake_case porque o Postgres rebaixa
# identificador nao aspeado para minusculo -- manter camelCase obrigaria a
# aspear cada coluna em toda consulta no Aiven.
SQL_TRATAMENTO = """
WITH bruto AS (
    SELECT * FROM read_json([{fontes}], format='newline_delimited',
                            columns={{{colunas}}}, union_by_name=true)
),
tipado AS (
    SELECT
        numeroControlePNCP                                   AS numero_controle_pncp,
        numeroControlePncpCompra                             AS numero_controle_compra,
        numeroControlePncpAta                                AS numero_controle_ata,
        anoContrato                                          AS ano_contrato,
        sequencialContrato                                   AS sequencial_contrato,
        numeroContratoEmpenho                                AS numero_contrato_empenho,
        processo                                             AS processo,

        TRY_CAST(dataPublicacaoPncp    AS TIMESTAMP)         AS data_publicacao,
        TRY_CAST(dataAtualizacao       AS TIMESTAMP)         AS data_atualizacao,
        TRY_CAST(dataAtualizacaoGlobal AS TIMESTAMP)         AS data_atualizacao_global,
        TRY_CAST(dataAssinatura        AS DATE)              AS data_assinatura,
        TRY_CAST(dataVigenciaInicio    AS DATE)              AS data_vigencia_inicio,
        TRY_CAST(dataVigenciaFim       AS DATE)              AS data_vigencia_fim,

        -- Dinheiro em DECIMAL, nunca em float: somatorio de 2 milhoes de
        -- contratos em DOUBLE acumula erro de arredondamento visivel.
        TRY_CAST(valorInicial   AS DECIMAL(18,2))            AS valor_inicial,
        TRY_CAST(valorGlobal    AS DECIMAL(18,2))            AS valor_global,
        TRY_CAST(valorParcela   AS DECIMAL(18,2))            AS valor_parcela,
        TRY_CAST(valorAcumulado AS DECIMAL(18,2))            AS valor_acumulado,
        numeroParcelas                                       AS numero_parcelas,
        numeroRetificacao                                    AS numero_retificacao,

        -- Identificador do fornecedor: sempre texto. Virar numero comeria o
        -- zero a esquerda de CNPJ como 00394429000102.
        nullif(trim(niFornecedor), '')                       AS ni_fornecedor,
        upper(nullif(trim(tipoPessoa), ''))                  AS tipo_pessoa,
        regexp_replace(trim(nomeRazaoSocialFornecedor), '\\s+', ' ', 'g')
                                                             AS nome_fornecedor,
        nullif(trim(codigoPaisFornecedor), '')               AS codigo_pais_fornecedor,
        -- Raiz do CNPJ (8 primeiros digitos): identifica a empresa por tras de
        -- matriz e filiais. E por ela que o cruzamento societario com a Receita
        -- se sustenta -- o CNPJ completo separaria filiais do mesmo grupo.
        CASE WHEN upper(trim(tipoPessoa)) = 'PJ'
                  AND length(regexp_replace(niFornecedor, '[^0-9]', '', 'g')) = 14
             THEN left(regexp_replace(niFornecedor, '[^0-9]', '', 'g'), 8)
        END                                                  AS cnpj_raiz_fornecedor,

        nullif(trim(niFornecedorSubContratado), '')          AS ni_subcontratado,
        nullif(trim(nomeFornecedorSubContratado), '')        AS nome_subcontratado,

        orgaoEntidade.cnpj                                   AS orgao_cnpj,
        regexp_replace(trim(orgaoEntidade.razaoSocial), '\\s+', ' ', 'g')
                                                             AS orgao_razao_social,
        orgaoEntidade.poderId                                AS orgao_poder,
        orgaoEntidade.esferaId                               AS orgao_esfera,

        upper(nullif(trim(unidadeOrgao.ufSigla), ''))        AS uf_sigla,
        unidadeOrgao.ufNome                                  AS uf_nome,
        unidadeOrgao.municipioNome                           AS municipio_nome,
        unidadeOrgao.codigoIbge                              AS codigo_ibge,
        unidadeOrgao.codigoUnidade                           AS codigo_unidade,
        regexp_replace(trim(unidadeOrgao.nomeUnidade), '\\s+', ' ', 'g')
                                                             AS nome_unidade,

        orgaoSubRogado.cnpj                                  AS orgao_subrogado_cnpj,
        unidadeSubRogada.codigoUnidade                       AS unidade_subrogada_codigo,

        tipoContrato.id                                      AS tipo_contrato_id,
        tipoContrato.nome                                    AS tipo_contrato_nome,
        categoriaProcesso.id                                 AS categoria_processo_id,
        categoriaProcesso.nome                               AS categoria_processo_nome,

        -- No bruto esses booleanos vem nulos quando sao falsos (98% de nulo).
        -- Normalizar evita que "IS NOT TRUE" e "= FALSE" deem respostas
        -- diferentes na filtragem la no Aiven.
        coalesce(receita, FALSE)                             AS receita,
        coalesce(emendaParlamentar, FALSE)                   AS emenda_parlamentar,
        coalesce(frutoAdesao, FALSE)                         AS fruto_adesao,
        coalesce(temRemanejamento, FALSE)                    AS tem_remanejamento,

        regexp_replace(trim(objetoContrato), '\\s+', ' ', 'g')
                                                             AS objeto_contrato,
        regexp_replace(trim(informacaoComplementar), '\\s+', ' ', 'g')
                                                             AS informacao_complementar,
        nullif(trim(identificadorCipi), '')                  AS identificador_cipi
    FROM bruto
),
deduplicado AS (
    SELECT *
    FROM tipado
    WHERE numero_controle_pncp IS NOT NULL
    QUALIFY row_number() OVER (
        PARTITION BY numero_controle_pncp
        ORDER BY data_atualizacao_global DESC NULLS LAST
    ) = 1
)
SELECT
    *,
    strftime(data_publicacao, '%Y-%m') AS ano_mes   -- chave de particao
FROM deduplicado
"""


def montar_sql(fontes) -> str:
    lista_fontes = ", ".join(f"'{f}'" for f in fontes)
    colunas = ", ".join(f"'{nome}': '{tipo}'" for nome, tipo in COLUNAS_BRUTO.items())
    return SQL_TRATAMENTO.format(fontes=lista_fontes, colunas=colunas)


def descobrir_fontes(raw_dir: Path) -> list:
    """Todo JSONL bruto do PNCP: os shards diarios do extrator rapido e o
    arquivo do extrator original. Os dois entram; a deduplicacao resolve a
    sobreposicao entre eles."""
    fontes = []
    diario = raw_dir / "pncp" / "diario"
    if diario.is_dir() and any(diario.glob("contratos_*.jsonl")):
        fontes.append(str(diario / "contratos_*.jsonl").replace("\\", "/"))
    legado = raw_dir / "pncp" / f"contratos_{config.ANO_REFERENCIA}.jsonl"
    if legado.is_file() and legado.stat().st_size > 0:
        fontes.append(str(legado).replace("\\", "/"))
    return fontes


def preparar_conexao(threads: int, memoria: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET threads = {threads}")
    con.execute(f"SET memory_limit = '{memoria}'")
    # Sem a ordem de insercao preservada o DuckDB escreve os Parquet em
    # paralelo e usa bem menos memoria. A ordem das linhas nao importa aqui:
    # quem consome filtra e agrega.
    con.execute("SET preserve_insertion_order = false")
    return con


def gravar_parquet(con, sql: str, destino: Path) -> None:
    if destino.exists():
        shutil.rmtree(destino)          # particionamento e reescrito inteiro
    destino.mkdir(parents=True, exist_ok=True)
    caminho = str(destino).replace("\\", "/")
    con.execute(f"""
        COPY ({sql}) TO '{caminho}'
        (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (ano_mes),
         OVERWRITE_OR_IGNORE, FILENAME_PATTERN 'contratos_{{uuid}}')
    """)


def gravar_csv_postgres(con, sql: str, destino: Path) -> None:
    """CSV pronto para COPY no Aiven.

    NULL vai como string vazia, que e o padrao que o COPY ... CSV do Postgres
    entende sem parametro extra. Um CSV por mes: se a carga cair no meio,
    voces refazem so o mes que faltou.
    """
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True, exist_ok=True)
    caminho = str(destino).replace("\\", "/")
    # ano_mes sai do corpo do CSV (vira nome de pasta) para o arquivo bater
    # coluna a coluna com a tabela do schema_postgres.sql.
    con.execute(f"""
        COPY (SELECT * FROM ({sql})) TO '{caminho}'
        (FORMAT CSV, HEADER, DELIMITER ',', QUOTE '"', ESCAPE '"', NULL '',
         PARTITION_BY (ano_mes), OVERWRITE_OR_IGNORE,
         FILENAME_PATTERN 'contratos_{{uuid}}')
    """)


def fmt_br(valor, casas: int = 0) -> str:
    """Numero no padrao brasileiro: 12.739.091.038,69.

    Um replace(',', '.') sozinho nao serve -- trocaria tambem o separador
    decimal do format(), virando 12.739.091.038.69.
    """
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def imprimir_resumo(con, sql: str) -> None:
    r = con.sql(f"""
        SELECT
            count(*)                                   AS contratos,
            count(DISTINCT ni_fornecedor)              AS fornecedores,
            count(DISTINCT cnpj_raiz_fornecedor)       AS grupos_economicos,
            count(DISTINCT orgao_cnpj)                 AS orgaos,
            count(DISTINCT uf_sigla)                   AS ufs,
            min(data_publicacao)                       AS publicacao_min,
            max(data_publicacao)                       AS publicacao_max,
            sum(valor_global)                          AS valor_global_total,
            count(*) FILTER (WHERE valor_global IS NULL)  AS sem_valor,
            count(*) FILTER (WHERE data_publicacao IS NULL) AS sem_data,
            count(*) FILTER (WHERE ni_fornecedor IS NULL) AS sem_fornecedor
        FROM ({sql})
    """).fetchone()

    rotulos = ["contratos (apos dedup)", "fornecedores distintos",
               "grupos economicos (raiz CNPJ)", "orgaos distintos", "UFs",
               "publicacao min", "publicacao max", "valor global somado",
               "sem valor_global", "sem data_publicacao", "sem ni_fornecedor"]
    print("\n== Resumo do tratado ==")
    for rotulo, valor in zip(rotulos, r):
        if isinstance(valor, int):
            print(f"  {rotulo:32}: {fmt_br(valor)}")
        elif isinstance(valor, Decimal):
            print(f"  {rotulo:32}: R$ {fmt_br(valor, 2)}")
        else:
            print(f"  {rotulo:32}: {valor}")

    print("\n== Contratos por mes de publicacao ==")
    for ano_mes, qtd, valor in con.sql(f"""
        SELECT ano_mes, count(*), sum(valor_global)
        FROM ({sql}) GROUP BY 1 ORDER BY 1
    """).fetchall():
        print(f"  {ano_mes}: {fmt_br(qtd):>11} contratos  "
              f"R$ {fmt_br(valor or 0, 2):>22}")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Trata os contratos brutos do PNCP para Parquet e Aiven/Postgres")
    p.add_argument("--formato", choices=["ambos", "parquet", "csv"], default="ambos",
                   help="o que gravar (padrao: ambos)")
    p.add_argument("--resumo", action="store_true",
                   help="nao grava nada, so perfila o que sairia")
    p.add_argument("--threads", type=int, default=0,
                   help="threads do DuckDB (padrao: todos os nucleos)")
    p.add_argument("--memoria", default="4GB",
                   help="teto de memoria do DuckDB (padrao: 4GB; o resto vai "
                        "para disco, nao quebra)")
    args = p.parse_args()

    raw_dir = Path(config.DIR_DADOS_RAW)
    fontes = descobrir_fontes(raw_dir)
    if not fontes:
        print(f"ERRO: nenhum JSONL bruto encontrado em {raw_dir / 'pncp'}.")
        print("      Rode antes: python baixar_pncp_rapido.py")
        return 1

    threads = args.threads or (duckdb.connect().sql(
        "SELECT current_setting('threads')").fetchone()[0])
    con = preparar_conexao(threads, args.memoria)
    sql = montar_sql(fontes)

    print("== Tratamento de contratos PNCP ==")
    print(f"   fontes  : {len(fontes)}")
    for f in fontes:
        print(f"             {f}")
    print(f"   engine  : DuckDB {duckdb.__version__}, {threads} threads, "
          f"teto {args.memoria}")

    inicio = time.time()
    imprimir_resumo(con, sql)

    if args.resumo:
        print(f"\n== Somente resumo, nada gravado ({time.time()-inicio:.1f}s) ==")
        return 0

    if args.formato in ("ambos", "parquet"):
        destino = Path(config.DIR_DADOS_PARQUET) / "contratos"
        t = time.time()
        gravar_parquet(con, sql, destino)
        arquivos = list(destino.rglob("*.parquet"))
        tamanho = sum(a.stat().st_size for a in arquivos) / 1e6
        print(f"\n== Parquet: {len(arquivos)} arquivo(s), {tamanho:.1f} MB "
              f"em {destino} ({time.time()-t:.1f}s) ==")

    if args.formato in ("ambos", "csv"):
        destino = Path("dados/saida_postgres/contratos")
        t = time.time()
        gravar_csv_postgres(con, sql, destino)
        arquivos = list(destino.rglob("*.csv"))
        tamanho = sum(a.stat().st_size for a in arquivos) / 1e6
        print(f"== CSV p/ Aiven: {len(arquivos)} arquivo(s), {tamanho:.1f} MB "
              f"em {destino} ({time.time()-t:.1f}s) ==")
        print("   proximo passo: python carregar_aiven.py")

    print(f"\n== Concluido em {time.time()-inicio:.1f}s ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
