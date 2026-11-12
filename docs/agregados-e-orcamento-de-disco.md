# Agregados materializados e orçamento de disco

Entrega da T2, semana 3. O benchmark mostrou que uma consulta de agregação sobre a fato completa (2.005.068 linhas) derruba a conexão do nó gratuito da Aiven (1 CPU, 1 GB de memória, 1 GB de disco): com metade da fato a consulta levou 6,0 s no servidor com índices, e com a fato inteira o servidor encerrou a conexão, por causa não confirmada (`docs/escolha-do-banco.md`). Por isso o painel lê só duas tabelas de agregado, e a fato nunca é consultada diretamente por ele.

## Os agregados

| Tabela | Grão | Serve a |
|---|---|---|
| `agg_kpi_genero_setor` | ano do contrato, CNAE, UF, faixa de `pct_negra` e controle da empresa (RN-05) | KPI 1 e camada interseccional |
| `agg_concentracao_socio` | sócio pessoa física ligado a duas ou mais empresas com contrato (RN-07) | KPI 4 |

As colunas, os tipos e as chaves estão em `docs/dicionario-de-dados.md`.

## Por que tabelas montadas por script, e não `MATERIALIZED VIEW`

O `REFRESH` de uma view é uma consulta única sobre a fato inteira, sem fatiar e sem retomar, que é o tipo de consulta que derrubou o nó. `etl/construir_agregados.py` monta cada agregado de outra forma:

- **Uma transação por agregado.** Se a conexão cair, o servidor desfaz tudo e o agregado anterior continua intacto.
- **Fatias.** A fato é lida em 8 passadas, cada uma agregando só os contratos de um bucket de hash, e o resultado é somado ao agregado. Cada passada guarda poucos grupos na memória.
- **Tabelas auxiliares pequenas.** Antes de tocar na fato, o script calcula o controle de cada empresa (240 mil linhas) e a faixa racial de cada município (5,6 mil). A fato só passa por junções com essas tabelas.
- **Sem ordenação.** A mediana de valor saiu dos agregados: não é aditiva e exigiria ordenar todos os valores, o que gera arquivos temporários. Os KPIs precisam só de contagem e soma.
- **Guarda de tamanho.** O script para se o banco passar de 600 MB.

O que não foi medido: se essa montagem cabe no nó gratuito. O desenho é uma hipótese até a primeira execução com o painel de uso da Aiven aberto.

## Orçamento de disco

O limite de 1 GB é do disco do serviço, e não da soma das tabelas: contam também o log de transações, os arquivos temporários e o sistema. No benchmark, o console mostrou 62,8% de armazenamento com o banco em 204 MB. Por isso o teto de segurança do banco é menor que 1.000 MB, e o script usa 600 MB.

| Componente | MB | Base |
|---|---|---|
| Banco com `dim_fornecedor` (239.600) e `dim_socio` (315.402) carregadas, ponte e fato vazias | 139,9 | medido em 11/11/2026 |
| `fato_contrato`, 5 colunas, com os índices `ix_fato_cnpj` e `ix_fato_ibge` | 213 a 223 | benchmark de 02/10/2026 (177 MB sem índices, mais índices estimados) |
| Índice da chave primária da fato (texto de 28 caracteres) | 95 | estimativa herdada do schema anterior |
| `ponte_empresa_socio` (339.385 linhas, chave primária e 2 índices) | 60 | estimativa, sem medição |
| `dim_municipio` | 1 | benchmark (0,8 MB) |
| Agregados | até 15 | estimativa |
| **Total estimado** | **cerca de 525 a 535** | soma dos itens |

A estimativa fica no limite inferior do orçamento utilizável do grupo (500 a 700 MB), com pouca folga contra o teto de 600 MB do script. Não está provado que o volume respeite o 1 GB: o que está provado é o que foi medido, e o resto vem da carga da fato e da ponte.

Se a medição ficar acima do teto, as alavancas são, da mais barata para a mais cara:

1. `VACUUM (ANALYZE)` nas tabelas carregadas. Não usar `VACUUM FULL`, que precisa de espaço para uma cópia.
2. Remover `ix_fato_cnpj` e `ix_fato_ibge` (de 36 a 46 MB). Os agregados são montados por varredura e não usam esses índices. O custo é a consulta seletiva de detalhe sobre a fato.
3. Trocar a chave primária de texto da fato por carga com `TRUNCATE` e `COPY` (cerca de 95 MB). O custo é perder a idempotência por `ON CONFLICT`.

## Como medir e registrar

```
python construir_agregados.py --orcamento | Tee-Object ..\docs\evidencias\orcamento-disco.txt
```

Guardar também o print do painel da Aiven com o percentual de armazenamento, porque é o número que decide.

## Resultado da execução

`[PENDENTE]` Linhas e MB de cada agregado, tempo de montagem, temporários gerados, tamanho do banco (`pg_database_size`) e percentual de armazenamento do console depois da carga completa.

## Limites

- O controle de empresa só é útil depois de `dim_socio.genero` ser carregado. Até lá, as empresas com sócio aparecem como `nao classificado`.
- A fato não tem a flag `receita`: os contratos de receita (cerca de 1,02% dos contratos e 1,6% do valor) entram nos totais (RN-02, D9).
- O único eixo de tempo é `ano_contrato`, e não há agregado por mês.
- Os contratos sem raiz de CNPJ (3,9% da fato) não entram nos KPIs (RN-01).