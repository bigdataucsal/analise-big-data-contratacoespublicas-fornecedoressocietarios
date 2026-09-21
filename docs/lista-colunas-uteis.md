# Lista de colunas úteis, com a fonte de cada uma

Entrega da Trilha 3, semana 1.

Tarefa: ler o PDF de metadados do CNPJ e mapear quais colunas servem a quais
perguntas; localizar o agregado de cor e raça por município no SIDRA e a base
de nomes por sexo.

Este documento é a lista consolidada. Cada linha traz a coluna, o arquivo de
origem, a fonte que documenta esse arquivo, e a pergunta analítica que ela
atende. O detalhamento de cada fonte, com armadilhas e formato, está em
`docs/mapa-colunas-receita.md` e `docs/fontes-genero-e-cor-raca.md`.

## As três perguntas, para referência

Q1. Qual proporção do valor contratado vai para empresas de controle
feminino, e qual proporção do número de contratos.

Q2. Camada interseccional: cruzar gênero do controle societário com
composição de cor ou raça obtida por proxy territorial e setorial.

Q3. Concentração societária: quantos sócios controlam que parcela do valor
contratado, e quais aparecem em múltiplas empresas fornecedoras.

---

## 1. Dados Abertos do CNPJ, da Receita Federal

Fonte: PDF de metadados do CNPJ, publicado pela Receita Federal em
`gov.br/receitafederal/dados/cnpj-metadados.pdf`. Arquivos em
`arquivos.receitafederal.gov.br/dados/cnpj/`.

Os arquivos não têm linha de cabeçalho, então a coluna é identificada pela
ordem posicional. A numeração abaixo é a do PDF oficial.

### Arquivo SOCIOS

| ordem | coluna | serve a | por quê |
|---|---|---|---|
| 1 | CNPJ_BASICO | Q1, Q2, Q3 | chave de junção com a empresa contratada. É a raiz de 8 dígitos, não o CNPJ de 14 |
| 2 | IDENTIFICADOR_DE_SOCIO | Q1, Q3 | separa sócio pessoa física de jurídica. 1 = PJ, 2 = PF, 3 = estrangeiro |
| 3 | NOME_DO_SOCIO_OU_RAZAO_SOCIAL | Q1, Q2 | entrada da inferência de gênero |
| 4 | CNPJ_CPF_DO_SOCIO | Q3 | CPF mascarado; identifica a mesma pessoa entre empresas |
| 5 | QUALIFICACAO_DO_SOCIO | Q1, Q3 | define quem tem poder de controle |
| 6 | DATA_DE_ENTRADA_SOCIEDADE | Q3 | quando o vínculo começou |
| 11 | FAIXA_ETARIA | Q2 | dimensão demográfica; o painel exige filtro por faixa etária |

Não usamos: PAIS (7), REPRESENTANTE_LEGAL (8), NOME_DO_REPRESENTANTE (9) e
QUALIFICACAO_DO_REPRESENTANTE_LEGAL (10). O representante legal representa o
sócio, não é sócio.

### Arquivo EMPRESAS

| ordem | coluna | serve a | por quê |
|---|---|---|---|
| 1 | CNPJ_BASICO | Q1, Q2, Q3 | chave |
| 2 | RAZAO_SOCIAL_NOME_EMPRESARIAL | Q1 | identificação da empresa |
| 3 | NATUREZA_JURIDICA | Q1 | separa fornecedor privado de ente público (grupo 1XXX) |
| 5 | CAPITAL_SOCIAL_DA_EMPRESA | Q1 | porte econômico; único campo decimal do conjunto |
| 6 | PORTE_DA_EMPRESA | Q1 | 00 não informado, 01 micro, 03 pequeno, 05 demais |

Não usamos: QUALIFICACAO_DO_RESPONSAVEL (4), que é o responsável perante a
Receita e não a lista de sócios, e ENTE_FEDERATIVO_RESPONSAVEL (7), vazio na
maioria das linhas.

### Arquivo ESTABELECIMENTOS

| ordem | coluna | serve a | por quê |
|---|---|---|---|
| 1, 2, 3 | CNPJ_BASICO, CNPJ_ORDEM, CNPJ_DV | Q1 | concatenadas formam o CNPJ de 14, que é o que o contrato traz |
| 4 | IDENTIFICADOR_MATRIZ_FILIAL | Q1 | 1 matriz, 2 filial |
| 6 | SITUACAO_CADASTRAL | Q1 | 02 ativa, 08 baixada, entre outras |
| 11 | DATA_DE_INICIO_ATIVIDADE | Q1 | idade da empresa |
| 12 | CNAE_FISCAL_PRINCIPAL | Q2 | setor, base do proxy setorial |
| 20 | UF | Q2 | recorte geográfico e desambiguação do município |
| 21 | MUNICIPIO | Q2 | sede da empresa, base do proxy territorial |

Não usamos as colunas 13 a 19 e 22 a 30, que são endereço detalhado,
telefone, fax e correio eletrônico. As três últimas são dado pessoal de
contato e ficam fora por aplicação da RN-09.

### Tabelas de domínio

| arquivo | serve a | por quê |
|---|---|---|
| QUALSCSV | Q1, Q3 | traduz o código de qualificação do sócio |
| CNAECSV | Q2 | traduz o código de CNAE |
| NATJUCSV | Q1 | traduz a natureza jurídica |
| MUNICCSV | Q2 | traduz o código de município da Receita |

Atenção ao MUNICCSV: ele traz código e descrição, mas **não** o código do
IBGE. A Receita usa codificação própria. Como o PNCP e o SIDRA falam código
IBGE, a tradução é necessária e está implementada em
`etl/traduzir_municipios.py`.

---

## 2. Cor e raça por município: agregado 9605 do SIDRA

Fonte: IBGE, Censo Demográfico 2022, pela API de agregados versão 3 do SIDRA.

Agregado 9605, "População residente, por cor ou raça, nos Censos
Demográficos". Variável 93, população residente em pessoas. Classificação 86,
"Cor ou raça". Nível geográfico N6, município.

Foi escolhido em vez do agregado 136 porque o 9605 traz 2010 e 2022 na mesma
tabela, já harmonizados nas mesmas cinco categorias. O 136 não tem 2022.

Chamada usada, testada e funcionando:

```
https://servicodados.ibge.gov.br/api/v3/agregados/9605/periodos/2022/variaveis/93?localidades=N6[all]&classificacao=86[2776,2777,2778,2779,2780]
```

| categoria | código | serve a |
|---|---|---|
| Branca | 2776 | Q2 |
| Preta | 2777 | Q2 |
| Amarela | 2778 | Q2 |
| Parda | 2779 | Q2 |
| Indígena | 2780 | Q2 |
| Total | 95251 | Q2, denominador |

Colunas da tabela que o `etl/baixar_proxy_racial.py` monta a partir disso:

| coluna | serve a | por quê |
|---|---|---|
| codigo_ibge | Q2 | chave de junção com o PNCP e com a sede da empresa |
| municipio, uf | Q2 | identificação e desambiguação |
| branca, preta, amarela, parda, indigena | Q2 | população por categoria |
| total | Q2 | denominador |
| pct_negra | Q2 | (preta + parda) / total, que é o agrupamento que o próprio IBGE usa em análise de desigualdade racial |

Situação: **já baixado**, os 5.570 municípios. O percentual de população negra
varia de 2,51% a 97,20%, com mediana de 60,8%.

Para cruzar cor ou raça com sexo existe o agregado 9606, que acrescenta a
classificação 2 (sexo: 4 homens, 5 mulheres) e a 287 (idade). Ao usá-lo é
obrigatório fixar 287 no código 100362, senão a API devolve as 134 faixas
etárias para cada município.

---

## 3. Base de nomes por sexo

Fonte: IBGE, Censo Demográfico 2010, pela API de nomes versão 2 em
`servicodados.ibge.gov.br/api/v2/censos/nomes/{nome}`. Sem chave, sem
autenticação.

| campo | serve a | por quê |
|---|---|---|
| nome | Q1, Q2 | o primeiro nome normalizado do sócio |
| sexo (parâmetro) | Q1, Q2 | M ou F; são duas chamadas por nome |
| res[].frequencia | Q1, Q2 | somadas dão o total por sexo |

O denominador é sempre masculino mais feminino, nunca o total que a API
devolve sem o parâmetro de sexo. A supressão do IBGE é aplicada célula a
célula, então o total agregado é maior que a soma dos sexos.

Para uso em lote existe base consolidada derivada dessa mesma API, publicada
pela Brasil.IO no conjunto Gênero dos Nomes, com cerca de cem mil nomes e a
proporção dominante já calculada. Licença CC BY-SA 4.0, que é share-alike, e
a atribuição exigida é literal: Fonte IBGE/Censo 2010, dados tratados por
Álvaro Justen/Brasil.IO.

Situação: **implementado e testado** em `etl/inferir_genero.py`. Piloto sobre
mil nomes deu 45,3% feminino, 49,0% masculino, 5,7% indeterminado.

---

## 4. Contratos, para fechar a cadeia

Fonte: PNCP, API pública de consulta. É a base oficial do tema e não estava
no escopo desta tarefa, mas entra na lista porque é o outro lado de toda
junção.

| coluna | serve a | por quê |
|---|---|---|
| niFornecedor | Q1, Q2, Q3 | CNPJ do contratado; os 8 primeiros dígitos ligam ao quadro societário |
| valorGlobal | Q1, Q2, Q3 | a métrica de todas as perguntas |
| orgaoEntidade.cnpj | Q1, Q3 | órgão contratante |
| unidadeOrgao.codigoIbge | Q2 | município, em código IBGE |
| dataPublicacaoPncp, dataAssinatura | Q1, Q2, Q3 | eixo temporal |
| numeroControlePNCP | — | chave natural, para deduplicação |

---

## Resumo por fonte

| fonte | o que entrega | situação |
|---|---|---|
| Receita Federal, CNPJ | quadro societário, CNAE, município da sede, porte | download pendente |
| IBGE, SIDRA agregado 9605 | composição de cor e raça dos 5.570 municípios | baixado |
| IBGE, API de nomes | frequência por sexo, para inferir gênero | implementado |
| PNCP | contratos, valores, órgãos | 58.769 de 2.023.236 baixados |

## Onde está o detalhamento

O formato dos arquivos da Receita, com encoding, separador, tratamento de
data e as armadilhas conhecidas, está em `docs/mapa-colunas-receita.md`.

As limitações de cada fonte de gênero e de cor ou raça, incluindo a supressão
de nomes raros e a natureza ecológica do proxy territorial, estão em
`docs/fontes-genero-e-cor-raca.md`.

A tipagem de cada coluna no modelo dimensional está em
`docs/dicionario-de-dados.md`.
