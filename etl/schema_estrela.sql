

CREATE TABLE IF NOT EXISTS dim_tempo (
    id_tempo        INTEGER PRIMARY KEY,
    data            DATE NOT NULL,
    ano             SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    dia_da_semana   SMALLINT NOT NULL
);

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

COMMENT ON COLUMN dim_municipio.codigo_ibge IS
  'Codigo do IBGE. A base da Receita usa codificacao PROPRIA de municipio; '
  'ligar por ela exige a tabela de traducao distribuida no conjunto do CNPJ.';

CREATE TABLE IF NOT EXISTS dim_orgao (
    id_orgao        INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cnpj            TEXT NOT NULL UNIQUE,
    razao_social    TEXT NOT NULL,
    poder           TEXT,
    esfera          TEXT
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
    cnpj_raiz          TEXT NOT NULL UNIQUE,
    razao_social       TEXT,
    tipo_pessoa        TEXT,
    natureza_juridica  TEXT,
    porte              TEXT,
    cnae_principal     TEXT
);

CREATE TABLE IF NOT EXISTS dim_socio (
    id_socio           INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    confianca_genero   NUMERIC(5,4),
    faixa_etaria       SMALLINT,
    identificador_tipo SMALLINT,
    cpf_mascarado      TEXT UNIQUE,
    identificador_pub  TEXT NOT NULL UNIQUE,
    genero             TEXT
        CHECK (genero IN ('feminino', 'masculino', 'indeterminado'))
);

COMMENT ON COLUMN dim_socio.genero IS
  'RN-04: classificado quando a proporcao dominante do primeiro nome na base '
  'de nomes do Censo 2022 (API v3 do IBGE) alcanca 90%. A categoria '
  'indeterminado nao e falha, e a medida explicita do que o metodo nao '
  'decide: 4,0% dos 327.180 socios PF do recorte nacional. O piloto de 5,7% '
  'usou o Censo 2010 e outra populacao.';

CREATE TABLE IF NOT EXISTS dim_tipo_contrato (
    id_tipo_contrato   INTEGER PRIMARY KEY,
    nome               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_categoria_processo (
    id_categoria       INTEGER PRIMARY KEY,
    nome               TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS ponte_empresa_socio (
    id_fornecedor      INTEGER NOT NULL REFERENCES dim_fornecedor(id_fornecedor),
    id_socio           INTEGER NOT NULL REFERENCES dim_socio(id_socio),
    data_entrada       DATE,
    qualificacao       TEXT NOT NULL,
    grupo_qualificacao TEXT
        CHECK (grupo_qualificacao IN ('participacao', 'titularidade',
                                      'administracao', 'representacao', 'outro')),
    competencia        TEXT NOT NULL,
    PRIMARY KEY (id_fornecedor, id_socio, qualificacao, competencia)
);

COMMENT ON TABLE ponte_empresa_socio IS
  'A Receita NAO publica data de saida da sociedade: cada arquivo e um '
  'retrato da competencia. Por isso a coluna competencia e obrigatoria e '
  'faz parte da leitura de qualquer resultado. Com uma competencia so, o '
  'que se pode afirmar e quem E socio hoje de uma empresa contratada '
  'naquela data, nao quem ERA socio na data do contrato.';


CREATE TABLE IF NOT EXISTS fato_contrato (
    id_contrato        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_tempo_publicacao  INTEGER NOT NULL REFERENCES dim_tempo(id_tempo),
    id_tempo_assinatura  INTEGER REFERENCES dim_tempo(id_tempo),
    id_orgao           INTEGER NOT NULL REFERENCES dim_orgao(id_orgao),
    id_unidade         INTEGER REFERENCES dim_unidade(id_unidade),
    id_fornecedor      INTEGER REFERENCES dim_fornecedor(id_fornecedor),
    id_tipo_contrato   INTEGER REFERENCES dim_tipo_contrato(id_tipo_contrato),
    id_categoria       INTEGER REFERENCES dim_categoria_processo(id_categoria),
    prazo_dias         INTEGER,
    ano_contrato       SMALLINT,
    numero_parcelas    SMALLINT,
    receita            BOOLEAN NOT NULL DEFAULT FALSE,
    emenda_parlamentar BOOLEAN NOT NULL DEFAULT FALSE,
    fruto_adesao       BOOLEAN NOT NULL DEFAULT FALSE,
    valor_global       NUMERIC(18,2),
    valor_inicial      NUMERIC(18,2),
    numero_controle_pncp TEXT NOT NULL UNIQUE
);

COMMENT ON COLUMN fato_contrato.id_tempo_publicacao IS
  'A coleta e por data de PUBLICACAO. Medido no ano inteiro: 7,05% dos '
  'contratos publicados em 2025 tem anoContrato 2024 (os 62,65% citados '
  'antes eram so de 1 a 20 de janeiro). Declarar qual das duas datas '
  'orienta cada analise continua obrigatorio.';


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
      AND s.identificador_tipo = 2
) controle ON TRUE
GROUP BY 1, 2, 3, 4, 5, 6;

CREATE INDEX IF NOT EXISTS ix_mv_kpi_genero
    ON mv_kpi_genero_setor (ano, uf_sigla, genero_controle);

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
HAVING count(DISTINCT p.id_fornecedor) >= 2;

CREATE INDEX IF NOT EXISTS ix_mv_concentracao
    ON mv_concentracao_socio (valor_controlado DESC);
