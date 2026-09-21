# Recorte congelado

Gerado por `recorte_cnpjs.py` a partir de `contratos_2025_completo.jsonl`.

## Criterios

1. Periodo: 20250101 a 20251231 (definido em `config.py`).
2. Contratos com valor global maior que zero.
3. Contratos com valor global ate R$ 1.000.000.000,00. Acima disso sao erros de digitacao na origem, nao contratos: na base medida, 26 registros concentravam 98.7% do valor somado, com os maiores passando de R$ 500 bilhoes em um unico contrato.
4. Os 50 orgaos com maior valor contratado apos os criterios acima (lista em `orgaos_recorte.csv`).

## Resultado

- 58.769 contratos na base de origem
- 58.333 apos os criterios de valor
- 6.405 apos o recorte de orgao
- 3.478 raizes de CNPJ distintas, que formam o filtro aplicado aos arquivos da Receita Federal

## Observacao

A lista e preliminar enquanto o download do PNCP nao terminar. Ela serve para desenvolver e testar o parser da Receita; basta rodar este script de novo ao fim da coleta para gerar a definitiva.
