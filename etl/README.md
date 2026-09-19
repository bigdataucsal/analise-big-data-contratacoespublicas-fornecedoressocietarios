# Pipeline ETL — PNCP → Parquet → Aiven for PostgreSQL

Documenta os scripts de extração e tratamento. Os números aqui foram medidos
contra a API do PNCP em 19/09/2026, não estimados.

```
    API do PNCP
         │
         │  baixar_pncp_rapido.py        (janela diária + paralelismo)
         ▼
    dados/raw/pncp/diario/contratos_AAAA-MM-DD.jsonl
         │
         │  tratar_contratos.py          (DuckDB: achata, tipa, deduplica)
         ▼
    dados/parquet/contratos/ano_mes=AAAA-MM/*.parquet      ← camada analítica
    dados/saida_postgres/contratos/ano_mes=AAAA-MM/*.csv   ← insumo da carga
         │
         │  carregar_aiven.py            (COPY + índices)
         ▼
    Aiven for PostgreSQL — tabela `contratos`
```

---

## 1. Extração — `baixar_pncp_rapido.py`

### O problema

O recorte de 2025 tem **2.023.236 contratos**. O `baixar_pncp.py` pagina o ano
inteiro de uma vez, 100 por página: 20.233 requisições. E a API do PNCP pagina
por deslocamento, então o custo cresce com o número da página:

| requisição | tempo medido |
|---|---|
| página 1 (`tamanhoPagina=500`) | 12 s |
| página 4000 (`tamanhoPagina=500`) | **52 s** |

Quanto mais o download avança, mais lento fica. Nesse ritmo a varredura
completa não termina em tempo útil.

### A saída

Quebrar o período em **janelas de 1 dia**. Cada dia tem ~5.500 contratos, ou
seja no máximo ~18 páginas — então toda requisição é rasa (~2 s) e o custo por
página para de crescer. Somando: `tamanhoPagina=500` (o máximo aceito; 1000
responde 400), conexão reaproveitada e alguns dias em paralelo.

| abordagem | vazão medida |
|---|---|
| original (paginação profunda, sequencial) | ~7 registros/s |
| este (janela diária, 3 em paralelo) | **~780 registros/s** |

### Limite de taxa

A API devolve 429 sob concorrência e não manda `Retry-After`. Medido:

| workers | resultado |
|---|---|
| 3 | nenhum 429 |
| 4 | 6 respostas 429 |
| 12 | metade das requisições perdidas (429 + 504) |

Daí o padrão de **3 workers**. O script ainda regula o ritmo sozinho: cada 429
aumenta a pausa global (1,8×, teto de 5 s) e sequências de sucesso a reduzem.

### Retomada

Um arquivo por dia, escrito em `.parcial` e renomeado só no fim — shard com
nome final é shard completo. Cair no meio e rodar de novo pula os dias prontos.
Não há arquivo de checkpoint: os próprios shards são o checkpoint.

```bash
python baixar_pncp_rapido.py                            # período do config.py
python baixar_pncp_rapido.py --de 20250101 --ate 20250107   # teste curto
python baixar_pncp_rapido.py --verificar                # dias faltando, duplicatas
```

> O `baixar_pncp.py` original continua no repositório e seus arquivos
> (`contratos_2025.jsonl`, `contratos_2025.checkpoint`) não são tocados por
> nenhum script novo — são lidos no tratamento e nunca escritos.

---

## 2. Tratamento — `tratar_contratos.py`

Motor: **DuckDB**. Lê o glob de JSONL em paralelo, achata em SQL, processa fora
da memória (não exige RAM maior que o dado) e escreve Parquet particionado num
único comando. PySpark resolveria, mas num nó único paga JVM e shuffle sem
ganho; pandas exigiria carregar ~3,5 GB de JSON aninhado na memória.

O que o tratamento faz:

- **Achata** os aninhados (`orgaoEntidade`, `unidadeOrgao`, `tipoContrato`,
  `categoriaProcesso`, e os sub-rogados) em colunas planas.
- **Tipa** com `TRY_CAST`: data torta vira `NULL` em vez de derrubar a carga.
- **Dinheiro em `DECIMAL(18,2)`**, nunca em float — somar milhões de contratos
  em ponto flutuante acumula erro visível no total.
- **CNPJ/CPF como texto**: em coluna numérica, `00394429000102` viraria
  `394429000102` e não casaria mais com a base da Receita.
- **Deriva `cnpj_raiz_fornecedor`** (8 primeiros dígitos): agrupa matriz e
  filiais. É a chave do cruzamento societário — o CNPJ completo separaria
  filiais do mesmo grupo.
- **Normaliza booleanos** que vêm nulos quando falsos (98% de nulo no bruto),
  para `IS NOT TRUE` e `= FALSE` não darem respostas diferentes no Aiven.
- **Deduplica** por `numeroControlePNCP`, mantendo a versão com
  `dataAtualizacaoGlobal` mais recente.

### A deduplicação não é opcional

O bruto atual tem **18.900 linhas para 18.500 chaves únicas — 400 duplicatas**.
O `.checkpoint` marca a página 185, mas o `.jsonl` tem 189 páginas: o resume do
extrator original regravou 4 páginas já baixadas. Como os arquivos não devem ser
alterados, o tratamento absorve isso. O extrator novo não tem essa classe de
falha, porque o shard só ganha nome final depois de completo.

### Compressão

| formato | tamanho (18.500 contratos) |
|---|---|
| JSONL bruto | 33,6 MB |
| CSV tratado | 11,8 MB |
| **Parquet ZSTD** | **2,1 MB** (16×) |

Extrapolando para os 2M de contratos: ~3,5 GB de bruto → ~230 MB de Parquet.

```bash
python tratar_contratos.py --resumo    # perfila sem gravar
python tratar_contratos.py             # parquet + csv
```

---

## 3. Carga — `carregar_aiven.py` + `schema_postgres.sql`

`COPY`, não `INSERT`: um INSERT por linha levaria horas onde o COPY leva
minutos. A ordem é **tabela → COPY → índices → ANALYZE**, com os índices por
último de propósito — mantê-los vivos durante a carga faz o Postgres reescrever
as árvores a cada inserção.

Índices pensados para a filtragem do trabalho: `ni_fornecedor` e
`cnpj_raiz_fornecedor` (o eixo societário), `orgao_cnpj`, `(uf_sigla,
data_publicacao)`, faixa de `valor_global`, BRIN em `data_publicacao` (a carga é
mês a mês, então a tabela já fica quase ordenada — alguns KB contra dezenas de
MB de um btree) e GIN trigram em `objeto_contrato` para busca textual.

Modos:

- `substituir` — `TRUNCATE` + `COPY`. Mais rápido, para carga completa.
- `incremental` — staging `UNLOGGED` + `INSERT ... ON CONFLICT DO UPDATE`.
  Idempotente: reprocessar um mês atualiza as linhas em vez de estourar a PK.

```bash
python carregar_aiven.py --simular          # confere os CSV, não conecta
python carregar_aiven.py                    # carga completa
python carregar_aiven.py --modo incremental # upsert
```

Credencial em `.env` (já coberto pelo `.gitignore`):

```
AIVEN_PG_URI=postgres://usuario:senha@host.aivencloud.com:12345/defaultdb?sslmode=require
```

---

## Dependências

```bash
pip install duckdb "psycopg[binary]" python-dotenv requests
```

## O que ainda não foi verificado

O `COPY` contra um Postgres real **não foi executado** — não havia instância
nem Docker disponível nesta máquina. O que foi verificado: o DDL passa no
parser oficial do Postgres (`libpg_query` via `pglast`), e a ordem das colunas
bate entre `CREATE TABLE`, o cabeçalho do CSV e a lista do carregador. A
primeira carga real no Aiven ainda precisa ser feita e observada.
