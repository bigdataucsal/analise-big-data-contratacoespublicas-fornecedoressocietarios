# Folha de números — defesa

Entrega da Trilha 3 para a avaliação de 26/11. Todos os números são medidos no
repositório, não estimados, e cada bloco diz onde conferir. Serve para responder
de cabeça; o raciocínio completo está em `docs/5-vs.md`,
`docs/regras-de-negocio.md`, `docs/escolha-do-banco.md` e
`docs/achados-e-limitacoes.md`.

## Volume e redução

| número | o que é |
|---|---|
| **2.023.134** | contratos do PNCP em 2025, ano inteiro, cobertura nacional |
| **3,62 GB → 254,1 MB** | JSONL bruto → Parquet ZSTD, cerca de **14×** |
| **28,67 GB** | Receita Federal descompactada (7,76 GB em ZIP) |
| **0,59%** | o que sobra de 222,2 milhões de linhas da Receita → 69,05 MB, cerca de **400×** |
| **334,6 MB** | só o campo `objeto_contrato`, mais 430 a 500 MB de índice trigram |
| **58.769** | contratos da amostra local de janeiro (20 primeiros dias) |

## O banco: por que 1 GB bastou

| número | o que é |
|---|---|
| **1 GB** | é o **disco do serviço**, não a soma das tabelas: heap, índices, WAL, temporários e bloat dividem a mesma cota |
| **500–700 MB** | orçamento realmente utilizável |
| **177 MB** | fato de 5 colunas, 2.005.068 linhas, sem índices |
| **213–223 MB** | a mesma fato com índices; 241–251 MB somando as dimensões |
| **1.164,1 MB** | temporários acumulados numa agregação de 1 milhão de linhas |
| **conexão caiu** | agregação sobre a fato completa, com 1 CPU e 1 GB de RAM |

A estratégia em uma frase: **o DuckDB faz o peso localmente e o PostgreSQL
recebe só o resultado**, em modelagem estrela com tabela-ponte, tipagem
enxuta (`DECIMAL` para dinheiro, `DATE` para data, CNPJ como texto) e KPIs em
visão materializada em vez de recálculo. O `objeto_contrato` não vai ao banco
por decisão D2.

## Veracidade e valores

| número | o que é |
|---|---|
| **R$ 18,25 tri** | valor somado dos 2.023.134 contratos — mais de 1,5× o PIB, logo impossível |
| **243 = 0,012%** | contratos acima de R$ 1 bi, com **95,77%** de todo o valor |
| **R$ 771,2 bi** | o que sobra depois do corte de sanidade |
| **9.101.366 / 3.486** | média vs mediana **sem** corte = **2.611×** |
| **384.638 / 3.484** | média vs mediana **com** corte = 110× — a mediana quase não se move |
| **0 duplicatas** | 2.023.134 linhas para 2.023.134 chaves |
| **20.439 = 1,02%** | contratos de receita, R$ 12,2 bi (1,6% do valor) |

Na amostra de janeiro, conferido em 10/11/2026 pelo `auditar_kpis.py`: 26
contratos com **98,74%** do valor e mediana de **R$ 4.260,00** com valor maior
que zero — os mesmos números que o documento já registrava.

## Gênero e controle

| número | o que é |
|---|---|
| **90%** | limiar da inferência; abaixo disso, **indeterminado** |
| **327.180** | sócios PF elegíveis, de 28.048 primeiros nomes distintos |
| **34,3 / 61,8 / 4,0** | % feminino / masculino / **indeterminado** entre sócios |
| **131.423 = 54,9%** | empresas com controle definido |
| **39.904 = 30,4%** | controle feminino entre elas — **conta empresas, não valor** |
| **65.001 = 27,1%** | empresas sem sócio na base, das quais 62.880 empresários individuais |
| **25.375 = 7,8%** | linhas de diretor, presidente e conselheiro (decisão D4) |

## Chaves, fontes e dispersão

| número | o que é |
|---|---|
| **raiz de 8 dígitos** | chave de junção PNCP × Receita: o quadro societário é da empresa, não do estabelecimento. **239.605** raízes. Converter para número destrói o zero à esquerda |
| **nome + máscara** | chave do sócio; a máscara sozinha colide (169.762 vs 195.748 em 200 mil linhas) |
| **41 campos** | de topo no JSON do PNCP, com 4 objetos aninhados |
| **11.813 órgãos** | 27 UFs, 4.196 municípios, **69,89% municipal** — a análise não é federal |
| **20–40 req/min** | limite da API do PNCP, **por tempo e não por concorrência** |
| **5.570 municípios** | Censo 2022 via SIDRA (tabela 9605); % negra de 2,5% a 97,2%, mediana 60,8% |
| **78.795 = 3,9%** | contratos sem raiz de CNPJ (R$ 16,9 bi), universo declarado à parte |

## As cinco viradas de premissa

São as perguntas em que a resposta intuitiva está errada.

1. **Amostragem estatística: NÃO.** Filtros e agregações, sim. Motivo na RN-07:
   análise de rede precisa de *todos* os contratos de cada sócio, e amostrar
   faria um sócio de 8 empresas virar um de 2, **subestimando o próprio
   fenômeno medido**. Recortar preserva a rede; amostrar a fragmenta.
2. **Imputação: NÃO existe.** Nada preenchido com média ou mediana. Três coisas
   distintas: normalização semântica de booleano (nulo *significa* falso); nulo
   preservado e declarado; registro sem chave vira universo à parte.
3. **Parquet não é formato de origem.** Nenhuma fonte o entrega; é o destino do
   tratamento. Origem é JSON (PNCP, Transparência, IBGE, SIDRA) e CSV em ZIP
   (Receita).
4. **`sensitive = true` não criptografa.** Controla só a exibição; o `tfstate`
   guarda senha e URI em texto claro.
5. **Os 30,4% contam empresas, não valor.** O cruzamento com valor contratado
   é pendência, não resultado.

## As nove regras em uma linha cada

| RN | regra |
|---|---|
| RN-01 | CNPJ é texto de 14; a junção é pela raiz de 8. Só PJ com 14 dígitos recebe raiz |
| RN-02 | entra no valor quem foi publicado no período, tem valor > 0 em centavos, até R$ 1 bi e não é receita. Reprovado é marcado, não apagado |
| RN-03 | entram sócios PF de três grupos de qualificação; 53 e 63 excluídos; procurador e representante fora |
| RN-04 | gênero pelo primeiro nome, limiar de 90% sobre a soma dos dois sexos, senão indeterminado |
| RN-05 | controle feminino com mais de 50% das sócias elegíveis; empate, sócio PJ ou mais de 1/3 de indeterminados → misto |
| RN-06 | cor e raça por composição do município da sede, **nunca** por pessoa |
| RN-07 | sócio multiempresa integra 2+ empresas; valor controlado é soma, marcada como sobreposta quando a empresa tem 2+ sócios multiempresa |
| RN-08 | sanção vale se vigente na **data de assinatura**, não na de consulta |
| RN-09 | CPF nunca na apresentação; nome por pseudônimo; nada exibido com menos de 5 sócios ou 5 empresas |

## Teste-se

Cubra as respostas e responda em voz alta.

1. Quantos contratos, e quanto ocupam em bruto e em Parquet?
2. O 1 GB do Aiven é o quê, exatamente? Quanto sobra na prática?
3. Quantos contratos concentram quanto do valor? Quanto sobra?
4. Média e mediana antes e depois do corte — qual das duas se move?
5. Qual a chave de junção com a Receita, e por que não o CNPJ de 14?
6. Qual o limiar do gênero, e o que acontece abaixo dele?
7. Quantos por cento de indeterminados, e por que esse número é publicado?
8. Por que a amostragem foi descartada?
9. Houve imputação de nulos? O que foi feito então?
10. Quanto da Receita sobrou depois do filtro, e como o filtro funciona?
11. O limite da API é de quê — requisições ou concorrência?
12. O que protege o token do Aiven, e qual risco continua de pé?
13. Os 30,4% são sobre qual denominador, e contam o quê?
14. Por que PostgreSQL e não um banco de documentos?

## O que admitir se perguntarem

Honestidade aqui vale mais que cobertura. As pendências estão em
`docs/rastreabilidade-regras.md` e as limitações em
`docs/achados-e-limitacoes.md`.

- O KPI 1 cruzado com **valor** não está pronto; o que existe conta empresas.
- Controle é contado **por cabeça**, porque o percentual de capital não existe
  nos dados abertos. É a principal limitação do trabalho.
- A `mv_kpi_genero_setor` **não aplica a RN-05 inteira** (ignora sócio PJ e
  junta as empresas sem sócio com as mistas). A diferença está medida em
  `etl/testes/test_divergencia_visao_kpi.py`, e os números publicados vêm do
  script, não da visão.
- A marcação de sanção depende do CEIS e do CNEP, que são da T2.
- Não há campo de situação na coleta, logo contrato cancelado depois de
  publicado pode estar nos indicadores.
