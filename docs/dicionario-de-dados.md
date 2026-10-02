# Dicionário de dados

Descreve as dez tabelas do modelo estrela, com origem, tipo e domínio de cada
coluna. É um dos itens obrigatórios do README segundo o guia do projeto.

As estatísticas de cardinalidade e domínio das tabelas abaixo foram medidas
sobre os 58.769 contratos de 1 a 20 de janeiro de 2025 `[AMOSTRA JAN]`, e não
estimadas. A primeira versão deste documento dizia que, com o ano completo, elas
mudariam de magnitude mas não de natureza. Isso não se confirmou em tudo: a
coleta completa de 2025 (2.023.134 contratos) mudou a composição de alguns
domínios. Os números do ano que importam para as regras estão na tabela a
seguir; os demais valem só como retrato de janeiro.

| estatística | amostra de janeiro | ano inteiro |
|---|---|---|
| órgãos distintos | 3.495 | 11.813 |
| contratos de órgão municipal | 56,3% | 69,89% |
| contratos por tipo de fornecedor (PJ, PF e PE) | 57.142, 1.400 e 227 | 1.941.824, 74.433 e 6.877 |
| contratos sem raiz de CNPJ | 1.650 | 82.784 |
| raízes de CNPJ distintas (contratos PJ com catorze dígitos) | 20.436 | 243.297 |
| `valorAcumulado` nulo | 55,99% | 38,68% |
| valor inicial diferente do global | 2,09% | 2,13% |
| mediana de `valor_global` (valor maior que zero) | R$ 4.260,00 (R$ 4.153,50 contando os zeros, número da primeira versão) | R$ 3.486,00 |
| maior `valor_global` | R$ 640 bilhões | R$ 6,03 trilhões |
| contratos acima de R$ 1 bilhão | 26, com 98,7% do valor | 243, com 95,77% do valor |

As colunas da Receita Federal estão descritas pelo layout oficial. A Receita já
foi baixada e filtrada (239.600 empresas, 529.225 estabelecimentos e 339.385
sócios, competência 2026-09-14), mas ainda não foi carregada no banco, e por isso
essas colunas continuam marcadas como pendentes.

Convenções que valem para todo o modelo. Identificadores como CNPJ, CPF, CEP e
código de município são sempre texto, nunca número, porque zeros à esquerda são
significativos. Valores monetários são sempre `NUMERIC`, nunca ponto flutuante,
porque somar milhões de contratos em float acumula erro visível. Chaves
substitutas são inteiras e as chaves naturais ficam como restrição de
unicidade.

## fato_contrato

Grão: um contrato. É a tabela de fatos do modelo.

| coluna | tipo | origem | observação |
|---|---|---|---|
| id_contrato | BIGINT | gerada | chave substituta; a natural custaria 95 MB de índice contra 40 MB desta |
| numero_controle_pncp | TEXT | PNCP `numeroControlePNCP` | chave natural, única. Formato `00394460005887-2-007096/2024` |
| id_tempo_publicacao | INTEGER | derivada de `dataPublicacaoPncp` | eixo temporal padrão da coleta |
| id_tempo_assinatura | INTEGER | derivada de `dataAssinatura` | pode divergir muito da publicação |
| id_orgao | INTEGER | FK para dim_orgao | 3.495 órgãos distintos em janeiro (11.813 no ano), nenhum nulo |
| id_unidade | INTEGER | FK para dim_unidade | 4.215 unidades distintas em janeiro |
| id_fornecedor | INTEGER | FK para dim_fornecedor | nulo quando o fornecedor não tem raiz de CNPJ (pessoa física, estrangeiro ou identificador irregular); ver RN-01 |
| id_tipo_contrato | INTEGER | FK para dim_tipo_contrato | 8 valores distintos |
| id_categoria | INTEGER | FK para dim_categoria_processo | 11 valores distintos |
| valor_global | NUMERIC(18,2) | PNCP `valorGlobal` | gravado em centavos, e é nesse valor que se aplica a RN-02. Mediana de R$ 3.486,00 no ano |
| valor_inicial | NUMERIC(18,2) | PNCP `valorInicial` | mediana R$ 4.000,00 em janeiro; difere do global em 2,13% dos contratos do ano, indicando aditivo |
| prazo_dias | INTEGER | derivada das datas de vigência | fim menos início |
| ano_contrato | SMALLINT | PNCP `anoContrato` | varia de 2021 a 2025 |
| numero_parcelas | SMALLINT | PNCP `numeroParcelas` | ver a nota de qualidade abaixo |
| receita | BOOLEAN | PNCP `receita` | contrato de receita para o órgão, em que o fornecedor paga. Marcado e fora dos indicadores de valor (RN-02, D9). 1,02% dos contratos da fato no ano; a marca erra nos dois sentidos |
| emenda_parlamentar | BOOLEAN | PNCP `emendaParlamentar` | normalizado: vem nulo quando falso em 99,8% dos casos |
| fruto_adesao | BOOLEAN | PNCP `frutoAdesao` | mesma normalização |

Duas notas de qualidade sobre esta tabela.

A primeira, sobre valor. O máximo bruto de `valor_global` no ano é de R$ 6,03
trilhões, e 243 contratos acima de um bilhão concentram 95,77% do valor somado
(em janeiro eram 26 contratos e 98,7%). Parte é erro de escala, e parte parece
ser teto estimado de credenciamento, hipótese ainda a confirmar. Eles ficam fora
da fato do banco e continuam listados no CSV de auditoria; a coluna que os marca
no Parquet entra na Fase 2 (RN-02, D3). O dicionário registra o valor bruto para
que ninguém se surpreenda ao consultar o dado antes do filtro.

A segunda, sobre parcelas. O máximo de `numero_parcelas` é 54.000, contra uma
mediana de 1. Um contrato com cinquenta e quatro mil parcelas não é plausível, e
esse campo merece um critério de sanidade próprio antes de ser usado em
qualquer métrica. Ainda não há regra de negócio para ele porque nenhuma pergunta
analítica o consome hoje.

## dim_tempo

Grão: um dia. Dimensão de calendário convencional.

| coluna | tipo | observação |
|---|---|---|
| id_tempo | INTEGER | chave no formato AAAAMMDD, legível a olho |
| data | DATE | |
| ano, mes, trimestre | SMALLINT | pré-calculados para evitar função sobre coluna em filtro |
| dia_da_semana | SMALLINT | |

A chave é a própria data no formato numérico em vez de sequencial, porque isso
permite ler a chave estrangeira do fato sem junção durante a depuração.

## dim_orgao

Grão: um órgão contratante. Origem: objeto `orgaoEntidade` do PNCP.

| coluna | tipo | origem | domínio medido |
|---|---|---|---|
| id_orgao | INTEGER | gerada | |
| cnpj | TEXT | `orgaoEntidade.cnpj` | 3.495 distintos em janeiro (11.813 no ano), único |
| razao_social | TEXT | `orgaoEntidade.razaoSocial` | espaços normalizados |
| poder | TEXT | `orgaoEntidade.poderId` | E 30.863, N 24.917, L 1.985, J 1.004 |
| esfera | TEXT | `orgaoEntidade.esferaId` | M 33.091, F 17.023, E 7.730, N 862, D 63 |

A distribuição por esfera merece atenção analítica: a base é predominantemente
municipal, com 69,89% dos contratos do ano (56,3% em janeiro), e não federal.
Isso tem consequência direta sobre heterogeneidade de preenchimento. As
contagens por poder e esfera da tabela acima são de janeiro.

## dim_unidade

Grão: uma unidade administrativa dentro de um órgão. Origem: `unidadeOrgao`.

| coluna | tipo | origem |
|---|---|---|
| id_unidade | INTEGER | gerada |
| id_municipio | INTEGER | FK, derivada de `unidadeOrgao.codigoIbge` |
| codigo_unidade | TEXT | `unidadeOrgao.codigoUnidade`, 4.215 distintos |
| nome_unidade | TEXT | `unidadeOrgao.nomeUnidade` |

## dim_municipio

Grão: um município brasileiro. Origem dupla: identificação do PNCP e do IBGE,
composição racial do Censo 2022 via SIDRA.

| coluna | tipo | origem | observação |
|---|---|---|---|
| id_municipio | INTEGER | gerada | |
| codigo_ibge | TEXT | IBGE, 7 dígitos | único. É a chave que o PNCP e o SIDRA compartilham |
| nome, uf_sigla | TEXT | IBGE | |
| pop_total | INTEGER | Censo 2022, SIDRA agregado 9605 | |
| pop_branca, pop_preta, pop_parda, pop_amarela, pop_indigena | INTEGER | idem | nulo significa não medido, zero significa zero |
| pct_negra | NUMERIC(6,3) | derivada | (preta + parda) / total. Mín 2,51%, mediana 60,8%, máx 97,20% |

Tabela completa com os 5.570 municípios, já baixada.

Duas armadilhas registradas. A primeira: o código de município da Receita
Federal não é o código do IBGE, e ligar a sede da empresa a esta tabela exige
passar pela tabela de tradução distribuída no conjunto do CNPJ. A segunda: o
SIDRA devolve os valores como texto, usando traço para zero e reticências para
dado não disponível, e os dois casos não podem virar o mesmo número.

Sobre o uso desta dimensão, a nota que precisa acompanhar qualquer resultado:
ela descreve o território, nunca a pessoa. Ver RN-06.

## dim_fornecedor

Grão: uma empresa, identificada pela raiz de oito dígitos do CNPJ. Origem
mista: PNCP para identificação, Receita Federal para os atributos cadastrais.

| coluna | tipo | origem | situação |
|---|---|---|---|
| id_fornecedor | INTEGER | gerada | |
| cnpj_raiz | TEXT | derivada de `niFornecedor` | 20.436 distintos em janeiro, 243.297 no ano. Nunca nulo: só existe para PJ com catorze dígitos (RN-01) |
| razao_social | TEXT | PNCP `nomeRazaoSocialFornecedor` | disponível |
| tipo_pessoa | TEXT | PNCP `tipoPessoa` (o roteiro chama de `tipoPessoaFornecedor`) | contratos por tipo em janeiro: PJ 57.142, PF 1.400, PE 227. Na dimensão, só entra PJ |
| natureza_juridica | TEXT | Receita, EMPRESAS coluna 3 | pendente. Grupo 1XXX identifica ente público |
| porte | TEXT | Receita, EMPRESAS coluna 6 | pendente. 00 não informado, 01 micro, 03 pequeno, 05 demais |
| capital_social | NUMERIC(18,2) | Receita, EMPRESAS coluna 5 | pendente. Vem com vírgula decimal |
| cnae_principal | TEXT | Receita, ESTABELECIMENTOS coluna 12 | pendente. 7 dígitos sem pontuação |
| id_municipio_sede | INTEGER | Receita, ESTABELECIMENTOS coluna 21 | pendente. Exige tradução de código |
| data_inicio_ativ | DATE | Receita, ESTABELECIMENTOS coluna 11 | pendente. Formato AAAAMMDD, ausente como 00000000 |

O grão é a raiz e não o CNPJ completo porque o quadro societário pertence à
empresa, não ao estabelecimento. Ver RN-01.

Os contratos sem raiz de CNPJ (1.650 em janeiro, 82.784 no ano) são os de
fornecedor pessoa física, estrangeiro ou com identificador irregular, que por
definição não têm quadro societário. Eles não entram nesta dimensão e ficam com
`id_fornecedor` nulo na fato, formando o universo à parte da RN-01.

## dim_socio

Grão: uma pessoa física ou jurídica que integra o quadro societário de alguma
empresa fornecedora. Origem: Receita Federal, arquivo de sócios. Pendente.

| coluna | tipo | origem | observação |
|---|---|---|---|
| id_socio | INTEGER | gerada | |
| cpf_mascarado | TEXT | SOCIOS coluna 4 | chave interna. Formato `000***718468**`. Nunca exibido, ver RN-09 |
| identificador_pub | TEXT | derivada | identificador substituto, este sim exibível |
| identificador_tipo | SMALLINT | SOCIOS coluna 2 | 1 pessoa jurídica, 2 pessoa física, 3 estrangeiro |
| faixa_etaria | SMALLINT | SOCIOS coluna 11 | 1 a 9 em faixas de dez anos; 0 não se aplica |
| genero | TEXT | inferido | feminino, masculino ou indeterminado. Ver RN-04 |
| confianca_genero | NUMERIC(5,4) | inferido | proporção dominante do primeiro nome |

O nome do sócio existe na origem mas não é coluna desta tabela: ele entra como
insumo da inferência de gênero e é descartado, restando o identificador
derivado. Essa é a aplicação concreta da RN-09.

A coluna `genero` admite indeterminado como valor legítimo, e não como ausência.
Nos 327.180 sócios pessoa física do recorte nacional, 4,0% ficaram
indeterminados, e essa taxa é resultado, não falha. A base de nomes é a do Censo
Demográfico 2022, consultada pela API v3 do IBGE; o roteiro cita o Censo 2010,
base da API v2, que só foi usada no piloto inicial (5,7% de indeterminados) e
não em nenhum número atual.

## ponte_empresa_socio

Grão: um vínculo entre empresa e sócio, numa competência. É a tabela que
resolve a cardinalidade de muitos para muitos, e a decisão de modelagem que o
projeto defende.

| coluna | tipo | origem | observação |
|---|---|---|---|
| id_fornecedor | INTEGER | FK | parte da chave primária |
| id_socio | INTEGER | FK | parte da chave primária |
| qualificacao | TEXT | SOCIOS coluna 5 | parte da chave. Código da tabela de domínio da Receita |
| competencia | TEXT | nome do arquivo | parte da chave. Formato AAAA-MM |
| grupo_qualificacao | TEXT | derivada | participacao, titularidade, administracao, representacao, outro |
| data_entrada | DATE | SOCIOS coluna 6 | não existe data de saída |

A competência faz parte da chave primária de propósito. O arquivo da Receita é
um retrato do momento e não tem data de saída da sociedade, de modo que a única
forma de reconstruir entradas e saídas é comparar competências sucessivas. Se a
competência ficasse fora da chave, o modelo impediria por construção exatamente
esse caminho.

A coluna `grupo_qualificacao` é derivada porque filtrar por código solto é o
erro clássico desse arquivo: usar apenas o código 22, de sócio, perderia o
titular que aparece como 65, como o de EIRELI. O empresário individual e o MEI
não aparecem no arquivo de sócios em código nenhum (ver RN-03 e RN-05). Os
grupos estão enumerados na RN-03.

## Tabelas de domínio

### dim_tipo_contrato

Origem: objeto `tipoContrato` do PNCP, que já vem no padrão código mais
descrição. Oito valores distintos na base medida.

| id | nome | ocorrências |
|---|---|---|
| 7 | Empenho | 27.692 |
| 1 | Contrato (termo inicial) | 19.002 |
| 8 | Outros | 11.888 |
| 5 | Termo de Adesão | 74 |

### dim_categoria_processo

Origem: objeto `categoriaProcesso` do PNCP. Onze valores distintos.

| id | nome | ocorrências |
|---|---|---|
| 2 | Compras | 40.667 |
| 8 | Serviços | 14.713 |
| 10 | Serviços de Saúde | 792 |
| 9 | Serviços de Engenharia | 660 |

## Domínios codificados que vêm da Receita

Estes não viram tabela no nosso modelo porque a Receita já distribui as tabelas
de domínio no próprio conjunto. Ficam registrados aqui para leitura do dado.

Identificador de sócio: 1 pessoa jurídica, 2 pessoa física, 3 estrangeiro.

Porte da empresa: 00 não informado, 01 microempresa, 03 empresa de pequeno
porte, 05 demais. Os códigos 02 e 04 não existem.

Situação cadastral: 01 nula, 02 ativa, 03 suspensa, 04 inapta, 08 baixada. O
PDF oficial mistura a grafia com e sem zero à esquerda, então convém normalizar
para dois caracteres antes de comparar.

Identificador de matriz ou filial: 1 matriz, 2 filial.

Faixa etária do sócio: 1 de 0 a 12 anos, 2 de 13 a 20, 3 de 21 a 30, 4 de 31 a
40, 5 de 41 a 50, 6 de 51 a 60, 7 de 61 a 70, 8 de 71 a 80, 9 maiores de 80, 0
não se aplica, tipicamente sócio pessoa jurídica.

Qualificação do sócio: são sessenta e seis códigos, não contíguos, agrupados
para uso do projeto na RN-03.

## Campos do bruto que não entram no modelo

Registrados para que a ausência seja decisão explícita e não esquecimento.

O campo `objetoContrato`, texto livre, permanece na camada Parquet e não entra
no PostgreSQL. A justificativa de custo está em `docs/escolha-do-banco.md`.

Os campos `orgaoSubRogado` e `unidadeSubRogada` vêm preenchidos em 0,31% dos
contratos do ano (a chave existe em todos, com valor nulo) e não são consumidos
por nenhuma pergunta analítica.

O campo `valorAcumulado` é nulo em 38,68% dos contratos do ano (55,99% em
janeiro), o que ainda o inviabiliza como métrica principal.

Os campos de telefone, fax e correio eletrônico dos estabelecimentos da Receita
são dados pessoais de contato e não entram no modelo, por aplicação da RN-09.
