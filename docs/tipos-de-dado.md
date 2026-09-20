# Classificação dos tipos de dado

O barema pede a identificação explícita das três variedades, com um trecho real
de cada uma. Todos os exemplos abaixo foram extraídos dos arquivos do projeto,
não construídos para ilustrar, e o caminho de origem está indicado em cada um.

Uma observação de atribuição: no cronograma este documento estava com as
Trilhas 2 e 4. Ele foi escrito pela Trilha 3 porque a semana correspondente
passou sem que fosse produzido, e porque os três exemplos já existiam em disco.
Quem for consolidar o README deve tratá lo como material disponível, não como
disputa de escopo.

## Semiestruturado: JSON aninhado das APIs

Origem: `etl/dados/raw/pncp/contratos_2025_completo.jsonl`, uma linha por
contrato, como veio da API do PNCP.

```json
{
  "numeroControlePNCP": "00394460005887-2-007096/2024",
  "orgaoEntidade": {
    "cnpj": "00394460005887",
    "razaoSocial": "MINISTERIO DA ECONOMIA",
    "poderId": "E",
    "esferaId": "F"
  },
  "unidadeOrgao": {
    "ufNome": "Paraná",
    "codigoUnidade": "900100",
    "nomeUnidade": "Superintendência Regional da Receita Federal do Brasil da 9ª Região Fiscal",
    "ufSigla": "PR",
    "municipioNome": "Curitiba",
    "codigoIbge": "4106902"
  },
  "tipoContrato": { "id": 1, "nome": "Contrato (termo inicial)" },
  "valorGlobal": 7000.0,
  "niFornecedor": "06121879000106",
  "orgaoSubRogado": null,
  "objetoContrato": "Alienação de mercadorias apreendidas pela Receita Federal"
}
```

O que faz deste dado semiestruturado, e não estruturado, são três
características visíveis no trecho.

Há aninhamento. Os campos `orgaoEntidade`, `unidadeOrgao` e `tipoContrato` são
objetos com estrutura própria, e não valores escalares. Uma tabela relacional
não os aceita nessa forma, e é por isso que o tratamento os achata em colunas
planas.

Há campos opcionais. O `orgaoSubRogado` aparece aqui como nulo, e em outros
registros vem como objeto completo. Medimos que ele está presente em menos de
1% dos contratos. Um esquema fixo teria essa coluna sempre, com valor ausente
na maioria das linhas; no JSON o campo pode simplesmente não existir.

Há o padrão de código mais descrição. O `tipoContrato` traz um identificador e
um nome juntos, o que é exatamente a forma de uma tabela de dimensão embutida
no registro. Foi essa observação que levou `tipoContrato` e `categoriaProcesso`
a virarem dimensões próprias no modelo estrela.

A mesma classificação vale para as respostas do Portal da Transparência e do
IBGE, que também são JSON.

## Estruturado: tabela de esquema fixo

Origem: `etl/dados/saida_postgres/contratos/ano_mes=2025-01/`, o CSV que o
tratamento gera a partir do JSON acima, pronto para a carga no PostgreSQL.

```
numero_controle_pncp     | 08916501000124-2-000001/2023
numero_controle_compra   | 08916501000124-1-000002/2023
numero_controle_ata      |
ano_contrato             | 2023
sequencial_contrato      | 1
numero_contrato_empenho  | 093
processo                 | 002/2023
data_publicacao          | 2025-01-20 11:33:52
data_atualizacao         | 2026-01-28 10:35:03
```

Aqui há 49 colunas fixas, na mesma ordem em toda linha, cada uma com um tipo
declarado. O ausente é ausente de verdade, como o `numero_controle_ata` vazio
acima, e não um campo que deixou de existir.

Vale notar que este exemplo é dado estruturado que nós produzimos a partir do
semiestruturado. Ele mostra o resultado do achatamento, e é útil justamente por
isso.

O dado estruturado que vem de fora são os arquivos da Receita Federal, que têm
esquema fixo mas em condições bem menos confortáveis: sem linha de cabeçalho,
separados por ponto e vírgula, em codificação latina, com data no formato
AAAAMMDD e ausência representada por oito zeros. O layout completo está em
`docs/mapa-colunas-receita.md`. Um trecho real deles será acrescentado aqui
assim que a Trilha 2 concluir o download, e essa é a única lacuna deste
documento.

## Não estruturado: texto livre

Origem: campo `objetoContrato`, o mesmo arquivo bruto do PNCP.

```
PREGÃO 45/2023 UASG 158141 - ALIMENTOS PARA ANIMAIS - 23360.000234/2024-49 - IE CAMPUS BG 0100157181

ITEM 8 - LÁPIS PRETO, ITEM 11 - PAPEL PARA IMPRESSÃO FORMATADO. - ITEM 16 - RÉGUA COMUM. - 2025NE00103

AQUISIÇÃO DE COLDRE DE PERNA UNIVERSAL PARA DESTRO, MATERIAL EM POLÍMERO, COMPATÍVEL NO MÍNIMO
PISTOLA G2C E TH40, FIVELA COM TRAVA TRIPLA E PARA SAQUE RÁPIDO DESTINADO A USO DA GUARDA
MUNICIPAL. PEDIDO Nº 5755 , PROCESSO DE COMPRA Nº 1983.
```

Os três trechos mostram por que este campo não é estruturado nem
semiestruturado. Não há gramática comum: o primeiro mistura número de pregão,
código de unidade e número de processo; o segundo enumera itens de uma licitação
com numeração interna; o terceiro é descrição técnica de produto com
especificação de material. Nada disso segue um formato que se possa parsear com
regra fixa.

O comprimento também varia sem limite útil. A média é de 149 caracteres, mas o
menor objeto de contrato da base é literalmente o caractere `1`, e o maior tem
5.120 caracteres, sendo uma especificação de produto do tipo:

```
RECIPIENTE ALIMENTOS / MATERIAL: PLÁSTICO / CAPACIDADE: 2L / APLICAÇÃO: COZINHA /
CARACTERÍSTICAS ADICIONAIS: TAMPA. GRADUADO, PRESILHAS PARA FECHAMEN...
```

Medimos que 1,69% dos objetos têm menos de quinze caracteres, ou seja, são
pouco informativos para qualquer análise textual. Esse percentual precisa ser
declarado quando resultados de análise de termos forem apresentados.

É este campo que justifica a camada não relacional do projeto. As perguntas
sobre ele são de busca textual e frequência de termos, que é a carga para a
qual um índice invertido existe. Há também uma razão de custo: medimos que
mantê lo no PostgreSQL consumiria entre 713 e 778 MB somando dados e índice de
busca por trigramas, mais do que todo o orçamento utilizável do plano gratuito
da Aiven. A justificativa completa está em `docs/escolha-do-banco.md`.

## Uma quarta categoria, que não é das três

Os dados do Censo e da RAIS não descrevem contratos nem empresas, e sim
territórios e setores. São tabelas agregadas, estruturadas, mas de natureza
diferente: não são observações do nosso objeto, são o contexto contra o qual ele
é lido.

Origem: `etl/dados/proxy/cor_raca_municipio_2022.csv`, gerado por
`etl/baixar_proxy_racial.py` a partir do SIDRA.

```
codigo_ibge,municipio,ano_censo,branca,preta,amarela,parda,indigena,total,pct_negra
2927408,Salvador - BA,2022,398688,825509,2605,1186416,4395,2417613,83.2195
3550308,São Paulo - SP,2022,6214422,1160073,238603,3820326,17727,11451151,43.4926
```

Vale mencionar essa distinção na apresentação, porque ela é o que sustenta o
proxy ecológico: o indicador é atribuído ao contexto, nunca à pessoa, e é essa
escolha que mantém o projeto dentro da LGPD.

## Resumo

| variedade | fonte | formato | onde no projeto |
|---|---|---|---|
| semiestruturado | PNCP, Portal da Transparência, IBGE | JSON aninhado | `dados/raw/` |
| estruturado | Receita Federal; e o nosso tratado | CSV de esquema fixo | `dados/saida_postgres/`, Receita pendente |
| não estruturado | campo objeto do contrato | texto livre em português | dentro do JSON bruto, preservado em Parquet |
| agregado de contexto | Censo 2022, RAIS | CSV agregado | `dados/proxy/` |

Guardamos sempre o dado bruto antes de tratar, em `dados/raw/`, não
versionado. Quando a API mudar no meio do semestre, é ele que salva o projeto.
