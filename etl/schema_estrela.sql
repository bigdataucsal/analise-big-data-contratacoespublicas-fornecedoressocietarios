-- Modelo estrela no Aiven for PostgreSQL (versao consolidada, T2).
-- =====================================================================
-- Substitui o schema_postgres.sql, que era uma tabela unica. Aquele
-- desenho nao cabia: estimado a partir da amostra de janeiro, daria cerca
-- de 1,9 GB entre dados e indices para os 2 milhoes de contratos, contra um
-- orcamento utilizavel de 500 a 700 MB. O limite de 1 GB da Aiven e o
-- DISCO do servico, nao a soma das tabelas -- contam indices, WAL, arquivos
-- temporarios de consulta e bloat, so os backups ficam de fora.
--
-- A normalizacao e o que resolve. Nome de orgao, de unidade, de municipio
-- e de fornecedor se repetem milhoes de vezes na tabela unica. O que existe
-- medido e uma fato de 5 colunas com os 2.005.068 contratos: 177 MB sem
-- indices na Aiven (docs/escolha-do-banco.md). Esta versao adota exatamente
-- essas 5 colunas. A fato final da Fase 2 podera ter mais colunas, e o
-- tamanho dela sera medido na carga.
--
-- Saem do banco: dim_tempo, dim_orgao, dim_unidade, dim_tipo_contrato e
-- dim_categoria_processo. Os atributos delas continuam como colunas do
-- Parquet de contratos.
--
-- Duas decisoes de modelagem valem defesa na apresentacao:
--
-- 1. A relacao entre empresa e socio e de MUITOS PARA MUITOS. Um socio
--    participa de varias empresas e uma empresa tem varios socios. Isso
--    nao cabe numa dimensao comum e exige a tabela ponte. E ela que
--    sustenta tanto o agregado de genero por empresa quanto a analise de
--    concentracao societaria.
-- 2. O texto livre do objeto do contrato NAO entra aqui. No ano inteiro
--    ele soma 334,6 MB de dados, e um indice de busca textual custaria
--    algo entre 430 e 500 MB (estimativa pela razao medida em janeiro):
--    mais do que todo o orcamento utilizavel numa coluna so. Fica na
--    camada Parquet.
--
-- Este arquivo so tem comandos IF NOT EXISTS, entao pode rodar varias
-- vezes. A migracao do desenho antigo (DROP) fica em aplicar_schema.py,
-- nunca aqui, porque carregar_receita_aiven.py executa as primeiras
-- secoes a cada carga. Os titulos de secao abaixo sao lidos por esse
-- carregador e por aplicar_schema.py. Nao renomeiem.


-- =====================================================================
-- 1. Dimensoes
-- =====================================================================
-- Colunas de largura fixa antes das de texto: evita o preenchimento de
-- alinhamento que o Postgres insere entre tipos de tamanhos diferentes.

CREATE TABLE IF NOT EXISTS dim_municipio (
    id_municipio    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pop_total       INTEGER,
    pop_branca      INTEGER,
    pop_preta       INTEGER,
    pop_parda       INTEGER,
    pop_amarela     INTEGER,
    pop_indigena    INTEGER,
    pct_negra       NUMERIC(6,3),
    codigo_ibge     TEXT NOT NULL UNIQUE,
    nome            TEXT NOT NULL,
    uf_sigla        TEXT NOT NULL
);

COMMENT ON TABLE dim_municipio IS
  'Granularidade: 1 linha por municipio (codigo IBGE de 7 digitos). '
  'Populacao por cor ou raca do Censo 2022: descreve o TERRITORIO, nunca uma pessoa (RN-06 e RN-09).';
COMMENT ON COLUMN dim_municipio.pop_total IS
  'Soma das cinco categorias de cor ou raca (como calcula o baixar_proxy_racial.py), e nao a '
  'categoria Total do SIDRA. Soma nacional: 203.069.637, contra 203.080.756 da categoria Total.';
COMMENT ON COLUMN dim_municipio.pct_negra IS
  'PERCENTUAL de 0 a 100: (preta + parda) / pop_total * 100, entre as pessoas com cor ou raca '
  'declarada. Proxy ecologico do recorte racial. Nulo se o municipio nao tiver dado no Censo 2022.';
COMMENT ON COLUMN dim_municipio.codigo_ibge IS
  'Codigo IBGE de 7 digitos. E o codigo usado pelo PNCP e pelo SIDRA. A Receita usa codificacao '
  'propria de municipio e precisa de traducao antes de ligar aqui.';

CREATE TABLE IF NOT EXISTS dim_fornecedor (
    id_fornecedor      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_municipio_sede  INTEGER REFERENCES dim_municipio(id_municipio),
    data_inicio_ativ   DATE,
    capital_social     NUMERIC(18,2),
    -- Raiz de 8 digitos: e o grao da dimensao, porque o quadro societario
    -- pertence a EMPRESA e nao ao estabelecimento. Juntar pelo CNPJ de 14
    -- com a tabela de socios da Receita devolve zero linhas, em silencio.
    cnpj_raiz          TEXT NOT NULL UNIQUE,
    razao_social       TEXT,
    tipo_pessoa        TEXT,
    natureza_juridica  TEXT,
    porte              TEXT,
    cnae_principal     TEXT
);

COMMENT ON TABLE dim_fornecedor IS
  'Granularidade: 1 linha por RAIZ de CNPJ (8 digitos), RN-01. So existe para fornecedor pessoa '
  'juridica com CNPJ de 14 digitos.';
COMMENT ON COLUMN dim_fornecedor.id_municipio_sede IS
  'Nulo enquanto o codigo de municipio da Receita nao for traduzido para o codigo IBGE.';
COMMENT ON COLUMN dim_fornecedor.natureza_juridica IS 'Codigo da Receita. 1XXX = ente publico.';
COMMENT ON COLUMN dim_fornecedor.porte IS '00 nao informado, 01 micro, 03 pequeno, 05 demais.';

CREATE TABLE IF NOT EXISTS dim_socio (
    id_socio           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confianca_genero   NUMERIC(5,4),
    faixa_etaria       SMALLINT,
    identificador_tipo SMALLINT,
    -- Mascara do CPF da Receita (formato 000***718468**). NAO e unica: pessoas
    -- diferentes colidem na mesma mascara. A chave de negocio e identificador_pub,
    -- que a RN-09 define como a unica coisa exibivel.
    cpf_mascarado      TEXT,
    identificador_pub  TEXT NOT NULL UNIQUE,
    genero             TEXT
        CHECK (genero IN ('feminino', 'masculino', 'indeterminado'))
);

COMMENT ON TABLE dim_socio IS
  'Granularidade: 1 linha por socio distinto, identificado por hash de mascara + nome + sal (RN-09).';
COMMENT ON COLUMN dim_socio.genero IS
  'RN-04: classificado quando a proporcao dominante do primeiro nome na base '
  'de nomes do Censo 2022 (API v3 do IBGE) alcanca 90%. A categoria '
  'indeterminado nao e falha, e a medida explicita do que o metodo nao '
  'decide: 4,0% dos 327.180 socios PF do recorte nacional. O piloto de 5,7% '
  'usou o Censo 2010 e outra populacao. Nulo = ainda nao classificado.';


-- =====================================================================
-- 2. Tabela ponte: empresa para socio
-- =====================================================================

CREATE TABLE IF NOT EXISTS ponte_empresa_socio (
    id_fornecedor      INTEGER NOT NULL REFERENCES dim_fornecedor(id_fornecedor),
    id_socio           INTEGER NOT NULL REFERENCES dim_socio(id_socio),
    data_entrada       DATE,
    qualificacao       TEXT NOT NULL,      -- codigo da tabela de dominio da Receita
    -- Agrupamento derivado da qualificacao, porque filtrar por codigo solto
    -- e o erro classico: so o codigo 22 (Socio) perderia o titular que
    -- aparece como 65, como o de EIRELI. Empresario individual e MEI nem
    -- aparecem no arquivo de socios (RN-03 e RN-05).
    grupo_qualificacao TEXT
        CHECK (grupo_qualificacao IN ('participacao', 'titularidade',
                                      'administracao', 'representacao', 'outro')),
    competencia        TEXT NOT NULL,      -- AAAA-MM do arquivo da Receita
    -- A competencia entra na chave. Sem ela, carregar uma segunda
    -- competencia colidiria com a primeira, e o modelo impediria por
    -- construcao o caminho que a RN-08 aponta: comparar competencias
    -- sucessivas para reconstruir entradas e saidas da sociedade.
    PRIMARY KEY (id_fornecedor, id_socio, qualificacao, competencia)
);

COMMENT ON TABLE ponte_empresa_socio IS
  'Granularidade: 1 linha por vinculo (empresa, socio, qualificacao, competencia). A Receita NAO '
  'publica data de saida da sociedade: cada arquivo e um retrato da competencia. Com uma '
  'competencia so, o que se afirma e quem E socio hoje, nao quem ERA socio na data do contrato.';


-- =====================================================================
-- 3. Fato
-- =====================================================================
-- Fato reduzida a 5 colunas, a mesma do benchmark (etl/benchmark_postgres.py).
-- As chaves estrangeiras sao NATURAIS: codigo_ibge e cnpj_raiz_fornecedor.
-- Dinheiro em NUMERIC, nunca em ponto flutuante.
-- A chave natural do PNCP e a chave primaria para o carregador poder rodar
-- de novo sem duplicar. O indice dela nao estava no benchmark e custa cerca
-- de 95 MB em 2 milhoes de linhas (estimativa do desenho anterior).

CREATE TABLE IF NOT EXISTS fato_contrato (
    numero_controle_pncp TEXT PRIMARY KEY,
    codigo_ibge          TEXT REFERENCES dim_municipio(codigo_ibge),
    cnpj_raiz_fornecedor TEXT REFERENCES dim_fornecedor(cnpj_raiz),
    valor_global         NUMERIC(18,2) NOT NULL,
    ano_contrato         INTEGER
);

COMMENT ON TABLE fato_contrato IS
  'Granularidade: 1 linha por contrato (numero_controle_pncp) publicado em 2025, apos deduplicacao '
  'e filtro de valor da RN-02 (maior que zero em centavos e ate R$ 1 bilhao). Fato reduzida de '
  '5 colunas: 2.005.068 linhas, 177 MB sem indices (benchmark de 02/10/2026).';
COMMENT ON COLUMN fato_contrato.codigo_ibge IS
  'Municipio do ORGAO contratante (PNCP unidadeOrgao.codigoIbge). Nulo se ausente no PNCP ou '
  'inexistente em dim_municipio.';
COMMENT ON COLUMN fato_contrato.cnpj_raiz_fornecedor IS
  'Raiz de 8 digitos do fornecedor. NULO quando o fornecedor nao tem raiz de CNPJ (pessoa fisica, '
  'estrangeiro ou identificador irregular): 78.795 contratos, 3,9% da fato (RN-01). As visoes dos '
  'KPIs os deixam de fora pela propria juncao com dim_fornecedor.';
COMMENT ON COLUMN fato_contrato.ano_contrato IS
  'Ano do contrato (PNCP anoContrato), NAO o ano da publicacao. A coleta e por data de publicacao: '
  '7,05% dos contratos publicados em 2025 tem anoContrato 2024. E o unico eixo de tempo desta '
  'fato, que tambem nao traz a flag receita (RN-02, D9).';


-- =====================================================================
-- 4. Indices
-- =====================================================================
-- Criados DEPOIS da carga. Manter indice vivo durante um COPY faz o
-- Postgres reescrever a arvore a cada insercao. Os dois indices da fato
-- sao os mesmos do benchmark.

CREATE INDEX IF NOT EXISTS ix_fato_cnpj       ON fato_contrato (cnpj_raiz_fornecedor);
CREATE INDEX IF NOT EXISTS ix_fato_ibge       ON fato_contrato (codigo_ibge);

CREATE INDEX IF NOT EXISTS ix_ponte_socio     ON ponte_empresa_socio (id_socio);
CREATE INDEX IF NOT EXISTS ix_ponte_grupo     ON ponte_empresa_socio (grupo_qualificacao);

CREATE INDEX IF NOT EXISTS ix_fornecedor_cnae ON dim_fornecedor (cnae_principal);
CREATE INDEX IF NOT EXISTS ix_fornecedor_mun  ON dim_fornecedor (id_municipio_sede);
CREATE INDEX IF NOT EXISTS ix_municipio_uf    ON dim_municipio (uf_sigla);
CREATE INDEX IF NOT EXISTS ix_socio_genero    ON dim_socio (genero);


-- =====================================================================
-- 5. Agregados calculados previamente
-- =====================================================================
-- Um no gratuito com 1 GB de memoria nao sustenta consulta analitica
-- pesada a cada clique de filtro no painel. Alem da lentidao, consulta
-- com ordenacao e juncao grande gera arquivo temporario em disco, que
-- consome a MESMA cota de 1 GB -- ou seja, o painel lento tambem enche o
-- disco. Materializar resolve os dois problemas. No benchmark, uma consulta
-- sobre a fato inteira derrubou o no gratuito: o primeiro REFRESH com a
-- fato carregada deve ser feito com o painel de uso do no aberto.
--
-- Estado das regras nestas visoes:
--  * RN-05: aplicada por inteiro (socio pessoa juridica no quadro deixa a
--    empresa como mista, e empresa sem socio na base fica separada).
--  * RN-07: aplicada (so socio pessoa fisica, so empresa com contrato, e a
--    sobreposicao conta apenas socios multiempresa).
--  * RN-02: pendente. A fato nao tem a flag receita, entao os contratos de
--    receita (cerca de 1,02% dos contratos e 1,6% do valor) entram nos
--    totais. A exclusao depende da coluna que a fato da Fase 2 vai trazer.
--  * Tempo: so ha ano_contrato, nao ha mes.
-- Os numeros de genero publicados ate agora vem do classificar_empresas.py.

-- KPI de genero por setor, UF e faixa racial do territorio. O territorio e
-- o municipio do orgao contratante (fato_contrato.codigo_ibge).
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_kpi_genero_setor AS
WITH quadro AS (
    SELECT p.id_fornecedor,
           coalesce(bool_or(s.identificador_tipo = 1), false) AS tem_pj,
           count(DISTINCT p.id_socio) FILTER (WHERE s.identificador_tipo = 2
               AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')) AS n,
           count(DISTINCT p.id_socio) FILTER (WHERE s.identificador_tipo = 2
               AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')
               AND s.genero = 'feminino') AS n_fem,
           count(DISTINCT p.id_socio) FILTER (WHERE s.identificador_tipo = 2
               AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')
               AND s.genero = 'masculino') AS n_masc,
           count(DISTINCT p.id_socio) FILTER (WHERE s.identificador_tipo = 2
               AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')
               AND s.genero = 'indeterminado') AS n_ind,
           count(DISTINCT p.id_socio) FILTER (WHERE s.identificador_tipo = 2
               AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')
               AND s.genero IS NULL) AS n_nulo
    FROM ponte_empresa_socio p
    JOIN dim_socio s ON s.id_socio = p.id_socio
    GROUP BY p.id_fornecedor
)
SELECT
    f.ano_contrato,
    fo.cnae_principal,
    m.uf_sigla,
    CASE
        WHEN m.pct_negra IS NULL THEN 'sem dado'
        WHEN m.pct_negra >= 70   THEN 'alta'
        WHEN m.pct_negra >= 40   THEN 'media'
        ELSE 'baixa'
    END AS faixa_pct_negra,
    CASE
        WHEN q.id_fornecedor IS NULL      THEN 'sem socio na base'
        WHEN q.n_nulo > 0                 THEN 'nao classificado'
        WHEN q.tem_pj                     THEN 'misto ou indeterminado'
        WHEN q.n = 0                      THEN 'indeterminado'
        WHEN q.n_ind  > q.n / 3.0         THEN 'misto ou indeterminado'
        WHEN q.n_fem  > q.n / 2.0         THEN 'feminino'
        WHEN q.n_masc > q.n / 2.0         THEN 'masculino'
        ELSE 'misto ou indeterminado'
    END AS genero_controle,
    count(*)            AS contratos,
    sum(f.valor_global) AS valor_total,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY f.valor_global) AS valor_mediano
FROM fato_contrato f
JOIN dim_fornecedor fo    ON fo.cnpj_raiz = f.cnpj_raiz_fornecedor
LEFT JOIN dim_municipio m ON m.codigo_ibge = f.codigo_ibge
LEFT JOIN quadro q        ON q.id_fornecedor = fo.id_fornecedor
GROUP BY 1, 2, 3, 4, 5;

CREATE INDEX IF NOT EXISTS ix_mv_kpi_genero
    ON mv_kpi_genero_setor (ano_contrato, uf_sigla, genero_controle);

-- Concentracao societaria (RN-07): socio pessoa fisica ligado a 2 ou mais
-- empresas COM contrato, pelos grupos participacao e titularidade. A soma e
-- marcada como sobreposta quando alguma empresa do socio tem mais de um
-- socio multiempresa, porque o mesmo valor entra na soma de cada um deles.
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_concentracao_socio AS
WITH contratos_por_empresa AS (
    SELECT fo.id_fornecedor,
           count(*)            AS contratos,
           sum(f.valor_global) AS valor
    FROM fato_contrato f
    JOIN dim_fornecedor fo ON fo.cnpj_raiz = f.cnpj_raiz_fornecedor
    GROUP BY fo.id_fornecedor
),
vinculo AS (
    SELECT DISTINCT p.id_socio, p.id_fornecedor
    FROM ponte_empresa_socio p
    JOIN dim_socio s                ON s.id_socio = p.id_socio AND s.identificador_tipo = 2
    JOIN contratos_por_empresa ce   ON ce.id_fornecedor = p.id_fornecedor
    WHERE p.grupo_qualificacao IN ('participacao', 'titularidade')
),
multiempresa AS (
    SELECT id_socio
    FROM vinculo
    GROUP BY id_socio
    HAVING count(*) >= 2
),
multi_por_empresa AS (
    SELECT v.id_fornecedor, count(*) AS n_multi
    FROM vinculo v
    JOIN multiempresa m ON m.id_socio = v.id_socio
    GROUP BY v.id_fornecedor
)
SELECT
    s.id_socio,
    s.identificador_pub,
    s.genero,
    count(*)                      AS empresas,
    sum(ce.contratos)::bigint     AS contratos,
    sum(ce.valor)                 AS valor_controlado,
    bool_or(mpe.n_multi > 1)      AS soma_sobreposta
FROM multiempresa m
JOIN dim_socio s               ON s.id_socio = m.id_socio
JOIN vinculo v                 ON v.id_socio = m.id_socio
JOIN contratos_por_empresa ce  ON ce.id_fornecedor = v.id_fornecedor
JOIN multi_por_empresa mpe     ON mpe.id_fornecedor = v.id_fornecedor
GROUP BY s.id_socio, s.identificador_pub, s.genero;

CREATE INDEX IF NOT EXISTS ix_mv_concentracao
    ON mv_concentracao_socio (valor_controlado DESC);

-- Minimo de agregacao (RN-09): nenhum recorte do painel deve mostrar
-- resultado baseado em menos de cinco socios ou cinco empresas. O filtro
-- fica na camada de apresentacao, nao nas visoes, porque o mesmo agregado
-- pode ser seguro num recorte e inseguro noutro.