-- Modelo estrela no Aiven for PostgreSQL.
-- =====================================================================
-- Substitui o schema_postgres.sql, que era uma tabela unica. Aquele
-- desenho nao cabia: medido, daria cerca de 1,9 GB entre dados e indices
-- para os 2 milhoes de contratos, contra um orcamento utilizavel de 500 a
-- 700 MB. O limite de 1 GB da Aiven e o DISCO do servico, nao a soma das
-- tabelas -- contam indices, WAL, arquivos temporarios de consulta e
-- bloat; so os backups ficam de fora.
--
-- A normalizacao e o que resolve. Nome de orgao, de unidade, de municipio
-- e de fornecedor se repetem milhoes de vezes na tabela unica; trocados
-- por chave estrangeira de 4 bytes, os dados caem de cerca de 1,2 GB para
-- cerca de 560 MB. Com o recorte dos 50 maiores orgaos, para a ordem de
-- 135 MB.
--
-- Duas decisoes de modelagem valem defesa na apresentacao:
--
-- 1. A relacao entre empresa e socio e de MUITOS PARA MUITOS. Um socio
--    participa de varias empresas e uma empresa tem varios socios. Isso
--    nao cabe numa dimensao comum e exige a tabela ponte. E ela que
--    sustenta tanto o agregado de genero por empresa quanto a analise de
--    concentracao societaria.
-- 2. O texto livre do objeto do contrato NAO entra aqui. Medido, ele
--    custaria 313 MB de dados mais 400 a 465 MB de indice de busca
--    textual, mais do que todo o orcamento utilizavel numa coluna so.
--    Fica na camada Parquet.


-- =====================================================================
-- 1. Dimensoes
-- =====================================================================

-- Ordem das colunas nao e estetica: agrupar os tipos de largura fixa
-- antes dos de texto elimina o preenchimento de alinhamento que o
-- Postgres insere entre colunas de tamanhos diferentes. Medido na tabela
-- unica: 9,74 bytes por linha de padding, que em 2 milhoes de linhas sao
-- cerca de 20 MB jogados fora. De graca, so pela ordem.

CREATE TABLE IF NOT EXISTS dim_tempo (
    id_tempo        INTEGER PRIMARY KEY,   -- AAAAMMDD, chave natural legivel
    data            DATE NOT NULL,
    ano             SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    dia_da_semana   SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_municipio (
    id_municipio    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Populacao do Censo 2022, para o proxy territorial de cor ou raca.
    -- Descreve o TERRITORIO, nunca uma pessoa.
    pop_total       INTEGER,
    pop_branca      INTEGER,
    pop_preta       INTEGER,
    pop_parda       INTEGER,
    pop_amarela     INTEGER,
    pop_indigena    INTEGER,
    pct_negra       NUMERIC(6,3),          -- (preta + parda) / total
    codigo_ibge     TEXT NOT NULL UNIQUE,  -- 7 digitos; e o codigo do PNCP e do SIDRA
    nome            TEXT NOT NULL,
    uf_sigla        TEXT NOT NULL
);

COMMENT ON COLUMN dim_municipio.codigo_ibge IS
  'Codigo do IBGE. A base da Receita usa codificacao PROPRIA de municipio; '
  'ligar por ela exige a tabela de traducao distribuida no conjunto do CNPJ.';

CREATE TABLE IF NOT EXISTS dim_orgao (
    id_orgao        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnpj            TEXT NOT NULL UNIQUE,
    razao_social    TEXT NOT NULL,
    poder           TEXT,                  -- E executivo, L legislativo, J judiciario
    esfera          TEXT                   -- F federal, E estadual, M municipal, D distrital, N nacional
);

CREATE TABLE IF NOT EXISTS dim_unidade (
    id_unidade      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_municipio    INTEGER REFERENCES dim_municipio(id_municipio),
    codigo_unidade  TEXT NOT NULL,
    nome_unidade    TEXT,
    UNIQUE (codigo_unidade, id_municipio)
);

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
    tipo_pessoa        TEXT,               -- PJ, PF, PE
    natureza_juridica  TEXT,               -- vem da Receita; 1XXX = ente publico
    porte              TEXT,               -- 00 nao informado, 01 micro, 03 pequeno, 05 demais
    cnae_principal     TEXT                -- 7 digitos, para o proxy setorial
);

CREATE TABLE IF NOT EXISTS dim_socio (
    id_socio           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confianca_genero   NUMERIC(5,4),       -- proporcao dominante do primeiro nome
    faixa_etaria       SMALLINT,           -- codigo 1 a 9 da Receita; 0 = nao se aplica
    identificador_tipo SMALLINT,           -- 1 PJ, 2 PF, 3 estrangeiro
    -- CPF mascarado da Receita, no formato 000***718468**. Preserva os seis
    -- digitos do meio, o que basta para agrupar o mesmo socio entre
    -- empresas -- que e o que a analise de rede precisa -- sem identificar
    -- a pessoa. Pela RN-09 ele e chave interna e nunca vai a apresentacao.
    cpf_mascarado      TEXT UNIQUE,
    identificador_pub  TEXT NOT NULL UNIQUE,  -- derivado, e este que aparece no painel
    genero             TEXT                -- feminino, masculino, indeterminado
        CHECK (genero IN ('feminino', 'masculino', 'indeterminado'))
);

COMMENT ON COLUMN dim_socio.genero IS
  'RN-04: classificado quando a proporcao dominante do primeiro nome na base '
  'do IBGE alcanca 90%. A categoria indeterminado nao e falha, e a medida '
  'explicita do que o metodo nao decide. Piloto mediu 5,7%.';

CREATE TABLE IF NOT EXISTS dim_tipo_contrato (
    id_tipo_contrato   INTEGER PRIMARY KEY,   -- o proprio id do PNCP
    nome               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_categoria_processo (
    id_categoria       INTEGER PRIMARY KEY,   -- o proprio id do PNCP
    nome               TEXT NOT NULL
);


-- =====================================================================
-- 2. Tabela ponte: empresa para socio
-- =====================================================================
-- O coracao do modelo, e o que o barema avalia em modelagem. A cardinalidade
-- e muitos para muitos, entao o vinculo tem que morar numa tabela propria,
-- com seus proprios atributos (a qualificacao e a data de entrada
-- descrevem o VINCULO, nao a empresa nem o socio).

CREATE TABLE IF NOT EXISTS ponte_empresa_socio (
    id_fornecedor      INTEGER NOT NULL REFERENCES dim_fornecedor(id_fornecedor),
    id_socio           INTEGER NOT NULL REFERENCES dim_socio(id_socio),
    data_entrada       DATE,
    qualificacao       TEXT NOT NULL,      -- codigo da tabela de dominio da Receita
    -- Agrupamento derivado da qualificacao, porque filtrar por codigo solto
    -- e o erro classico: so o codigo 22 (Socio) perderia MEI, empresario
    -- individual e sociedade unipessoal, onde o dono aparece como 50 ou 65
    -- -- que e a maior parte dos fornecedores pequenos do setor publico.
    grupo_qualificacao TEXT
        CHECK (grupo_qualificacao IN ('participacao', 'titularidade',
                                      'administracao', 'representacao', 'outro')),
    competencia        TEXT NOT NULL,      -- AAAA-MM do arquivo da Receita
    PRIMARY KEY (id_fornecedor, id_socio, qualificacao)
);

COMMENT ON TABLE ponte_empresa_socio IS
  'A Receita NAO publica data de saida da sociedade: cada arquivo e um '
  'retrato da competencia. Por isso a coluna competencia e obrigatoria e '
  'faz parte da leitura de qualquer resultado. Com uma competencia so, o '
  'que se pode afirmar e quem E socio hoje de uma empresa contratada '
  'naquela data, nao quem ERA socio na data do contrato.';


-- =====================================================================
-- 3. Fato
-- =====================================================================

CREATE TABLE IF NOT EXISTS fato_contrato (
    id_contrato        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Chaves estrangeiras de 4 bytes no lugar do texto repetido. E esta
    -- troca que derruba os dados de ~1,2 GB para ~560 MB.
    id_tempo_publicacao  INTEGER NOT NULL REFERENCES dim_tempo(id_tempo),
    id_tempo_assinatura  INTEGER REFERENCES dim_tempo(id_tempo),
    id_orgao           INTEGER NOT NULL REFERENCES dim_orgao(id_orgao),
    id_unidade         INTEGER REFERENCES dim_unidade(id_unidade),
    id_fornecedor      INTEGER NOT NULL REFERENCES dim_fornecedor(id_fornecedor),
    id_tipo_contrato   INTEGER REFERENCES dim_tipo_contrato(id_tipo_contrato),
    id_categoria       INTEGER REFERENCES dim_categoria_processo(id_categoria),
    prazo_dias         INTEGER,
    ano_contrato       SMALLINT,
    numero_parcelas    SMALLINT,
    receita            BOOLEAN NOT NULL DEFAULT FALSE,
    emenda_parlamentar BOOLEAN NOT NULL DEFAULT FALSE,
    fruto_adesao       BOOLEAN NOT NULL DEFAULT FALSE,
    -- Dinheiro em NUMERIC, nunca em ponto flutuante: somar milhoes de
    -- contratos em float acumula erro visivel no total.
    valor_global       NUMERIC(18,2),
    valor_inicial      NUMERIC(18,2),
    -- Chave natural do PNCP. Fica como UNIQUE e nao como chave primaria
    -- porque uma PK textual de 28 caracteres custaria cerca de 95 MB de
    -- indice contra os ~40 MB de um BIGINT.
    numero_controle_pncp TEXT NOT NULL UNIQUE
);

COMMENT ON COLUMN fato_contrato.id_tempo_publicacao IS
  'A coleta e por data de PUBLICACAO. Medido: 62,65% dos contratos '
  'publicados em 2025 tem anoContrato 2024. Declarar qual das duas datas '
  'orienta cada analise e obrigatorio.';


-- =====================================================================
-- 4. Indices
-- =====================================================================
-- Criados DEPOIS da carga. Manter indice vivo durante um COPY faz o
-- Postgres reescrever a arvore a cada insercao.

CREATE INDEX IF NOT EXISTS ix_fato_fornecedor ON fato_contrato (id_fornecedor);
CREATE INDEX IF NOT EXISTS ix_fato_orgao      ON fato_contrato (id_orgao);
CREATE INDEX IF NOT EXISTS ix_fato_tempo      ON fato_contrato (id_tempo_publicacao);
CREATE INDEX IF NOT EXISTS ix_fato_valor      ON fato_contrato (valor_global);

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
-- disco. Materializar resolve os dois problemas.

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_kpi_genero_setor AS
SELECT
    t.ano,
    t.mes,
    f2.cnae_principal,
    m.uf_sigla,
    CASE
        WHEN m.pct_negra >= 70 THEN 'alta'
        WHEN m.pct_negra >= 40 THEN 'media'
        ELSE 'baixa'
    END                                   AS faixa_pct_negra,
    controle.genero_controle,
    count(*)                              AS contratos,
    sum(f.valor_global)                   AS valor_total,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY f.valor_global) AS valor_mediano
FROM fato_contrato f
JOIN dim_tempo t        ON t.id_tempo = f.id_tempo_publicacao
JOIN dim_fornecedor f2  ON f2.id_fornecedor = f.id_fornecedor
LEFT JOIN dim_municipio m ON m.id_municipio = f2.id_municipio_sede
-- Classificacao de controle da empresa pela RN-05: contagem por cabeca
-- entre os socios elegiveis, porque o percentual de participacao de cada
-- socio nao consta dos dados abertos.
LEFT JOIN LATERAL (
    SELECT CASE
        WHEN count(*) FILTER (WHERE s.genero = 'indeterminado')
             > count(*) / 3.0                                   THEN 'misto ou indeterminado'
        WHEN count(*) FILTER (WHERE s.genero = 'feminino')
             > count(*) / 2.0                                   THEN 'feminino'
        WHEN count(*) FILTER (WHERE s.genero = 'masculino')
             > count(*) / 2.0                                   THEN 'masculino'
        ELSE 'misto ou indeterminado'
    END AS genero_controle
    FROM ponte_empresa_socio p
    JOIN dim_socio s ON s.id_socio = p.id_socio
    WHERE p.id_fornecedor = f.id_fornecedor
      AND p.grupo_qualificacao IN ('participacao', 'titularidade', 'administracao')
      AND s.identificador_tipo = 2      -- so socio pessoa fisica
) controle ON TRUE
GROUP BY 1, 2, 3, 4, 5, 6;

CREATE INDEX IF NOT EXISTS ix_mv_kpi_genero
    ON mv_kpi_genero_setor (ano, uf_sigla, genero_controle);

-- Concentracao societaria: por socio, em quantas empresas fornecedoras ele
-- aparece e quanto valor essas empresas capturaram. A marcacao de
-- sobreposicao existe porque, sem ela, a soma por socio ultrapassa o total
-- contratado quando a mesma empresa tem varios socios multiempresa.
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_concentracao_socio AS
SELECT
    s.id_socio,
    s.identificador_pub,
    s.genero,
    count(DISTINCT p.id_fornecedor)   AS empresas,
    count(DISTINCT f.id_contrato)     AS contratos,
    sum(f.valor_global)               AS valor_controlado,
    bool_or(sobreposto.tem)           AS soma_sobreposta
FROM dim_socio s
JOIN ponte_empresa_socio p ON p.id_socio = s.id_socio
JOIN fato_contrato f       ON f.id_fornecedor = p.id_fornecedor
LEFT JOIN LATERAL (
    SELECT count(*) > 1 AS tem
    FROM ponte_empresa_socio p2
    WHERE p2.id_fornecedor = p.id_fornecedor
) sobreposto ON TRUE
WHERE p.grupo_qualificacao IN ('participacao', 'titularidade')
GROUP BY 1, 2, 3
HAVING count(DISTINCT p.id_fornecedor) >= 2;   -- RN-07: socio multiempresa

CREATE INDEX IF NOT EXISTS ix_mv_concentracao
    ON mv_concentracao_socio (valor_controlado DESC);


-- =====================================================================
-- 6. Nota sobre o minimo de agregacao (RN-09)
-- =====================================================================
-- Nenhum recorte do painel deve exibir resultado baseado em menos de cinco
-- socios ou cinco empresas. O filtro nao esta na view de proposito: ele
-- pertence a camada de apresentacao, porque o mesmo agregado pode ser
-- seguro num corte e inseguro noutro. E o mesmo principio que o IBGE
-- aplica ao suprimir nomes com poucas ocorrencias.
