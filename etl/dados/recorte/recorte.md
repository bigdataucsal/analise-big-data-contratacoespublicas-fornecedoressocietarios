# Recorte congelado

> **PRELIMINAR.** Esta lista NÃO é definitiva e não deve ser tratada
> como tal enquanto a coleta do PNCP não terminar.

## De onde veio

Arquivo de origem: `contratos_2025_completo.jsonl`, saída do `baixar_pncp_rapido.py`.

Cobertura: 20 dia(s), de 2025-01-01 a 2025-01-20 de 365 dias do período definido em `config.py`.

Esse arquivo de origem **não é versionado**, porque é dado bruto e
passa de 100 MB. Quem clonar o repositório recebe esta lista pronta,
mas não consegue regerá-la sem antes rodar a coleta:

```bash
python baixar_pncp_rapido.py    # a coleta completa leva horas
python recorte_cnpjs.py         # aí sim regera a lista definitiva
```

A lista está versionada justamente por isso: sem ela, quem for filtrar
os arquivos da Receita ficaria bloqueado esperando uma coleta de horas.
Ela serve para desenvolver e testar o parser contra dado real. O número
de CNPJs vai crescer quando a coleta fechar o ano.

## Critérios

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
