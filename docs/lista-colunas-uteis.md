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
`gov.br/receitafederal/dados/cnpj-metadados.pdf`. São 6 páginas. Arquivos em
`arquivos.receitafederal.gov.br/dados/cnpj/`.

A ordem das colunas abaixo foi **conferida diretamente contra esse PDF**, não
tirada de documentação de terceiros. Os arquivos não têm linha de cabeçalho,
então a coluna é identificada pela posição, e errar a ordem desloca o dado
inteiro em silêncio.

O que o PDF declara e o que ele não declara, porque a diferença importa:

Ele declara a ordem e a descrição de cada campo, os códigos de domínio como
os do porte da empresa e os do identificador de sócio, e o separador, que é
ponto e vírgula. Declara também a regra de máscara do CPF, citada adiante.

Ele **não** declara a codificação de caracteres, o delimitador de texto, o
formato de data nem o separador decimal. Esses quatro vieram de implementações
de parser já existentes e estão marcados como fonte secundária em
`docs/mapa-colunas-receita.md`. A leitura completa da competência 2026-09-14,
feita pela T2, confirmou a codificação latina, a data AAAAMMDD com ausência em
oito zeros e a vírgula decimal (`docs/parser-receita.md`), e o trecho real em
`docs/evidencias/exemplos_tipos.txt` mostra as aspas duplas. Essa confirmação
não foi refeita nesta máquina, que não tem a base da Receita.

### Arquivo SOCIOS

| ordem | coluna | serve a | por quê |
|---|---|---|---|
| 1 | CNPJ_BASICO | Q1, Q2, Q3 | chave de junção com a empresa contratada. É a raiz de 8 dígitos, não o CNPJ de 14 |
| 2 | IDENTIFICADOR_DE_SOCIO | Q1, Q3 | separa sócio pessoa física de jurídica. 1 = PJ, 2 = PF, 3 = estrangeiro |
| 3 | NOME_DO_SOCIO_OU_RAZAO_SOCIAL | Q1, Q2 | entrada da inferência de gênero |
| 4 | CNPJ_CPF_DO_SOCIO | Q3 | CPF mascarado por exigência legal; identifica a mesma pessoa entre empresas |
| 5 | QUALIFICACAO_DO_SOCIO | Q1, Q3 | define quem tem poder de controle |
| 6 | DATA_DE_ENTRADA_SOCIEDADE | Q3 | quando o vínculo começou |
| 11 | FAIXA_ETARIA | Q2 | dimensão demográfica; o painel exige filtro por faixa etária |

Não usamos: PAIS (7), REPRESENTANTE_LEGAL (8), NOME_DO_REPRESENTANTE (9) e
QUALIFICACAO_DO_REPRESENTANTE_LEGAL (10). O representante legal representa o
sócio, não é sócio.

Sobre a coluna 4, um ponto que sustenta o parecer de LGPD. O PDF declara que
o CPF vem descaracterizado por ocultação dos três primeiros dígitos e dos
dois dígitos verificadores, e cita a base legal: art. 129 § 2º da Lei nº
13.473/2017, a LDO de 2018. Ou seja, a máscara não é escolha nossa nem
gentileza da Receita, é cumprimento de norma, e o dado já chega
desidentificado na origem. Os seis dígitos do meio que restam bastam para
agrupar o mesmo sócio entre empresas, que é o que a Q3 precisa, sem
identificar a pessoa. A RN-09 se apoia nisso.

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

Fonte: IBGE, Censo Demográfico 2022, pela API de nomes versão 3 em
`servicodados.ibge.gov.br/api/v3/nomes/2022/nome/{nome}?tipo=nome&localidade=0`.
Sem chave, sem autenticação. A base de nomes é a do Censo Demográfico 2022,
consultada pela API v3 do IBGE; o roteiro cita o Censo 2010, base da API v2, que
só foi usada no piloto inicial (5,7% de indeterminados) e não em nenhum número
atual. O endereço da v3 foi capturado no site Nomes no Brasil
(censo2022.ibge.gov.br/nomes) e não foi confirmado na documentação pública da
API, e por isso cada resposta fica guardada em cache.

| campo | serve a | por quê |
|---|---|---|
| nome (no endereço) | Q1, Q2 | o primeiro nome normalizado do sócio |
| mulheres | Q1, Q2 | frequência feminina do nome no Brasil |
| homens | Q1, Q2 | frequência masculina; uma chamada só traz os dois sexos |

O denominador é sempre mulheres mais homens. Na API v2, o total sem o parâmetro
de sexo era maior que a soma dos sexos, porque a supressão do IBGE é aplicada
célula a célula; na v3, o campo `frequencia` já vem como a soma dos dois, mas a
regra continua a mesma.

A base consolidada da Brasil.IO (Gênero dos Nomes) não foi usada: ela deriva do
Censo 2010, e o recorte coube na própria API v3 com cache (18.965 nomes
consultados em 107,7 minutos).

Situação: **aplicado** aos 327.180 sócios pessoa física do recorte nacional, pelo
`etl/classificar_empresas.py`: 34,3% feminino, 61,8% masculino e 4,0%
indeterminado. O piloto inicial, com a API v2 e sobre mil fornecedores pessoa
física do PNCP, tinha dado 45,3%, 49,0% e 5,7%.

---

## 4. Contratos, para fechar a cadeia

Fonte: PNCP, API pública de consulta. É a base oficial do tema e não estava
no escopo desta tarefa, mas entra na lista porque é o outro lado de toda
junção.

| coluna | serve a | por quê |
|---|---|---|
| niFornecedor | Q1, Q2, Q3 | CNPJ do contratado; os 8 primeiros dígitos ligam ao quadro societário |
| tipoPessoa | Q1, Q3 | PJ, PF ou PE; só PJ com catorze dígitos tem raiz de CNPJ (RN-01). O roteiro chama o campo de `tipoPessoaFornecedor`, nome que não existe no dado |
| receita | Q1, Q2, Q3 | separa contrato de receita do de despesa; os de receita saem dos indicadores de valor (RN-02) |
| valorGlobal | Q1, Q2, Q3 | a métrica de todas as perguntas |
| orgaoEntidade.cnpj | Q1, Q3 | órgão contratante |
| unidadeOrgao.codigoIbge | Q2 | município, em código IBGE |
| dataPublicacaoPncp, dataAssinatura | Q1, Q2, Q3 | eixo temporal |
| numeroControlePNCP | (nenhuma) | chave natural, para deduplicação |

---

## Resumo por fonte

| fonte | o que entrega | situação |
|---|---|---|
| Receita Federal, CNPJ | quadro societário, CNAE, município da sede, porte | baixada e filtrada: 239.600 empresas e 339.385 sócios (competência 2026-09-14) |
| IBGE, SIDRA agregado 9605 | composição de cor e raça dos 5.570 municípios | baixado |
| IBGE, API de nomes (Censo 2022) | frequência por sexo, para inferir gênero | aplicada aos sócios do recorte nacional |
| PNCP | contratos, valores, órgãos | 2.023.134 contratos, o ano de 2025 completo, conferido dia a dia contra a API |

## Onde está o detalhamento

O formato dos arquivos da Receita, com encoding, separador, tratamento de
data e as armadilhas conhecidas, está em `docs/mapa-colunas-receita.md`.

As limitações de cada fonte de gênero e de cor ou raça, incluindo a supressão
de nomes raros e a natureza ecológica do proxy territorial, estão em
`docs/fontes-genero-e-cor-raca.md`.

A tipagem de cada coluna no modelo dimensional está em
`docs/dicionario-de-dados.md`.
