

CREATE TABLE IF NOT EXISTS contratos (
    numero_controle_pncp      TEXT PRIMARY KEY,
    numero_controle_compra    TEXT,
    numero_controle_ata       TEXT,
    ano_contrato              INTEGER,
    sequencial_contrato       INTEGER,
    numero_contrato_empenho   TEXT,
    processo                  TEXT,

    data_publicacao           TIMESTAMP,
    data_atualizacao          TIMESTAMP,
    data_atualizacao_global   TIMESTAMP,
    data_assinatura           DATE,
    data_vigencia_inicio      DATE,
    data_vigencia_fim         DATE,

    valor_inicial             NUMERIC(18,2),
    valor_global              NUMERIC(18,2),
    valor_parcela             NUMERIC(18,2),
    valor_acumulado           NUMERIC(18,2),
    numero_parcelas           INTEGER,
    numero_retificacao        INTEGER,

    ni_fornecedor             TEXT,
    tipo_pessoa               TEXT,
    nome_fornecedor           TEXT,
    codigo_pais_fornecedor    TEXT,
    cnpj_raiz_fornecedor      TEXT,
    ni_subcontratado          TEXT,
    nome_subcontratado        TEXT,

    orgao_cnpj                TEXT,
    orgao_razao_social        TEXT,
    orgao_poder               TEXT,
    orgao_esfera              TEXT,

    uf_sigla                  TEXT,
    uf_nome                   TEXT,
    municipio_nome            TEXT,
    codigo_ibge               TEXT,
    codigo_unidade            TEXT,
    nome_unidade              TEXT,

    orgao_subrogado_cnpj      TEXT,
    unidade_subrogada_codigo  TEXT,

    tipo_contrato_id          INTEGER,
    tipo_contrato_nome        TEXT,
    categoria_processo_id     INTEGER,
    categoria_processo_nome   TEXT,

    receita                   BOOLEAN,
    emenda_parlamentar        BOOLEAN,
    fruto_adesao              BOOLEAN,
    tem_remanejamento         BOOLEAN,

    objeto_contrato           TEXT,
    informacao_complementar   TEXT,
    identificador_cipi        TEXT,

    ano_mes TEXT GENERATED ALWAYS AS (to_char(data_publicacao, 'YYYY-MM')) STORED
);


CREATE INDEX IF NOT EXISTS ix_contratos_ni_fornecedor
    ON contratos (ni_fornecedor);
CREATE INDEX IF NOT EXISTS ix_contratos_cnpj_raiz
    ON contratos (cnpj_raiz_fornecedor);

CREATE INDEX IF NOT EXISTS ix_contratos_orgao_cnpj
    ON contratos (orgao_cnpj);
CREATE INDEX IF NOT EXISTS ix_contratos_uf_data
    ON contratos (uf_sigla, data_publicacao);

CREATE INDEX IF NOT EXISTS ix_contratos_data_publicacao_brin
    ON contratos USING BRIN (data_publicacao);

CREATE INDEX IF NOT EXISTS ix_contratos_valor_global
    ON contratos (valor_global);

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_contratos_objeto_trgm
    ON contratos USING GIN (objeto_contrato gin_trgm_ops);
