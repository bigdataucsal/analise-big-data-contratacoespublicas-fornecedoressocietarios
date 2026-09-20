-- ATENCAO: ESTE SCHEMA FOI SUPERADO. NAO USE NO RECORTE COMPLETO.
-- =====================================================================
-- Tabela unica, desnormalizada. Medido, ela ocuparia cerca de 1,9 GB
-- entre dados e indices para os 2.023.236 contratos do recorte, contra um
-- orcamento utilizavel de 500 a 700 MB no plano gratuito da Aiven -- e o
-- limite de 1 GB de la e o DISCO do servico, nao a soma das tabelas.
--
-- O substituto e o schema_estrela.sql, que normaliza em modelo estrela e
-- traz a tabela ponte empresa-socio. A justificativa esta em
-- docs/escolha-do-banco.md.
--
-- Este arquivo fica no repositorio por dois motivos: o carregar_aiven.py
-- ainda carrega contra ele (a carga em estrela ainda nao foi escrita), e
-- ele serve de termo de comparacao no documento de escolha do banco. Para
-- uma amostra pequena ele funciona; para o recorte completo, nao cabe.
--
-- Schema dos contratos tratados no Aiven for PostgreSQL.
-- =====================================================================
-- Aplicado pelo carregar_aiven.py, mas roda igual no psql:
--     psql "$AIVEN_PG_URI" -f schema_postgres.sql
--
-- A ordem das colunas de 1 a 49 e exatamente a do CSV gerado pelo
-- tratar_contratos.py. Se mexerem no SELECT de la, mexam aqui tambem --
-- o COPY casa por posicao, nao por nome.


-- =====================================================================
-- 1. Tabela
-- =====================================================================

CREATE TABLE IF NOT EXISTS contratos (
    -- Chave natural do PNCP. E texto, nao numero: tem formato
    -- "00394460005887-1-000067/2024".
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

    -- NUMERIC, nao DOUBLE PRECISION: sao valores de contrato, e soma de
    -- milhao de linhas em ponto flutuante acumula erro que aparece no
    -- total. NUMERIC no Postgres e exato.
    valor_inicial             NUMERIC(18,2),
    valor_global              NUMERIC(18,2),
    valor_parcela             NUMERIC(18,2),
    valor_acumulado           NUMERIC(18,2),
    numero_parcelas           INTEGER,
    numero_retificacao        INTEGER,

    -- CNPJ/CPF sempre TEXT. Em coluna numerica, 00394429000102 viraria
    -- 394429000102 e nao casaria mais com a base da Receita.
    ni_fornecedor             TEXT,
    tipo_pessoa               TEXT,
    nome_fornecedor           TEXT,
    codigo_pais_fornecedor    TEXT,
    -- Raiz do CNPJ: e por ela que se agrupa matriz + filiais no
    -- cruzamento societario.
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

    -- Coluna 50: nao vem no CSV (virou nome de pasta no particionamento).
    -- O Postgres calcula sozinho, entao o COPY continua com 49 colunas.
    ano_mes TEXT GENERATED ALWAYS AS (to_char(data_publicacao, 'YYYY-MM')) STORED
);


-- =====================================================================
-- 2. Indices
-- =====================================================================
-- Criados DEPOIS da carga, de proposito. Manter indice vivo durante um
-- COPY de milhoes de linhas faz o Postgres reescrever a arvore a cada
-- insercao; criar no fim, de uma vez, e varias vezes mais rapido. O
-- carregar_aiven.py respeita essa ordem.

-- Fornecedor: o eixo do trabalho. Filtrar por CNPJ e agrupar por raiz
-- societaria sao as duas consultas mais frequentes.
CREATE INDEX IF NOT EXISTS ix_contratos_ni_fornecedor
    ON contratos (ni_fornecedor);
CREATE INDEX IF NOT EXISTS ix_contratos_cnpj_raiz
    ON contratos (cnpj_raiz_fornecedor);

-- Orgao contratante e recorte geografico.
CREATE INDEX IF NOT EXISTS ix_contratos_orgao_cnpj
    ON contratos (orgao_cnpj);
CREATE INDEX IF NOT EXISTS ix_contratos_uf_data
    ON contratos (uf_sigla, data_publicacao);

-- Recorte temporal. BRIN em vez de btree: a carga vai mes a mes, entao a
-- tabela ja fica quase ordenada por data_publicacao -- e nesse caso o BRIN
-- ocupa alguns KB contra dezenas de MB de um btree, com filtro por periodo
-- igualmente eficiente.
CREATE INDEX IF NOT EXISTS ix_contratos_data_publicacao_brin
    ON contratos USING BRIN (data_publicacao);

-- Faixa de valor.
CREATE INDEX IF NOT EXISTS ix_contratos_valor_global
    ON contratos (valor_global);

-- Busca por palavra no objeto do contrato. Sem trigram, um
-- "objeto_contrato ILIKE '%pavimentacao%'" varre a tabela inteira.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_contratos_objeto_trgm
    ON contratos USING GIN (objeto_contrato gin_trgm_ops);


-- =====================================================================
-- 3. Exemplos da filtragem
-- =====================================================================
-- Deixados aqui como ponto de partida; nada roda automaticamente.
--
-- Fornecedores que mais receberam, por grupo economico:
--   SELECT cnpj_raiz_fornecedor,
--          min(nome_fornecedor)  AS fornecedor,
--          count(*)              AS contratos,
--          sum(valor_global)     AS total
--   FROM contratos
--   WHERE tipo_pessoa = 'PJ'
--   GROUP BY cnpj_raiz_fornecedor
--   ORDER BY total DESC
--   LIMIT 50;
--
-- Mesmo fornecedor atendendo muitos orgaos diferentes (sinal de
-- concentracao que vale investigar):
--   SELECT ni_fornecedor,
--          min(nome_fornecedor)       AS fornecedor,
--          count(DISTINCT orgao_cnpj) AS orgaos,
--          sum(valor_global)          AS total
--   FROM contratos
--   GROUP BY ni_fornecedor
--   HAVING count(DISTINCT orgao_cnpj) > 10
--   ORDER BY orgaos DESC;
--
-- Recorte por UF e periodo:
--   SELECT * FROM contratos
--   WHERE uf_sigla = 'BA'
--     AND data_publicacao >= '2025-01-01'
--     AND data_publicacao <  '2025-04-01';
