# Recorte congelado

> **PRELIMINAR.** Esta lista NÃO é definitiva e não deve ser tratada
> como tal enquanto a coleta do PNCP não terminar.

## De onde veio

Arquivo de origem: `contratos_2025_completo.jsonl`, saída do `baixar_pncp_rapido.py`.

Cobertura: 365 dia(s), de 2025-01-01 a 2025-12-31 de 365 dias do período definido em `config.py`.

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
3. Contratos com valor global ate R$ 1.000.000.000,00. Acima disso sao erros de digitacao na origem, nao contratos: na base medida, 243 registros concentravam 95.8% do valor somado, com os maiores passando de R$ 500 bilhoes em um unico contrato.

## Resultado

- 2.023.134 contratos na base de origem
- 2.005.313 apos os criterios de valor
- 239.605 raizes de CNPJ distintas, que formam o filtro aplicado aos arquivos da Receita Federal

## Observacao

A lista e preliminar enquanto o download do PNCP nao terminar. Ela serve para desenvolver e testar o parser da Receita; basta rodar este script de novo ao fim da coleta para gerar a definitiva.
