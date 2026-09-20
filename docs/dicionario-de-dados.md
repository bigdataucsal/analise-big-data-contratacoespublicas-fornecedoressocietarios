# Dicionário de dados

Descreve as dez tabelas do modelo estrela, com origem, tipo e domínio de cada
coluna. É um dos itens obrigatórios do README segundo o guia do projeto.

As estatísticas de cardinalidade e domínio foram medidas sobre os 58.769
contratos já coletados, de 1 a 20 de janeiro de 2025, e não estimadas. Quando a
coleta do ano completo terminar elas mudam de magnitude, mas não de natureza.

As colunas que virão da Receita Federal estão descritas pelo layout oficial,
porque o download ainda não terminou. Elas estão marcadas como pendentes.

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
| id_orgao | INTEGER | FK para dim_orgao | 3.495 órgãos distintos, nenhum nulo |
| id_unidade | INTEGER | FK para dim_unidade | 4.215 unidades distintas |
| id_fornecedor | INTEGER | FK para dim_fornecedor | nulo quando o fornecedor é pessoa física |
| id_tipo_contrato | INTEGER | FK para dim_tipo_contrato | 8 valores distintos |
| id_categoria | INTEGER | FK para dim_categoria_processo | 11 valores distintos |
| valor_global | NUMERIC(18,2) | PNCP `valorGlobal` | mediana R$ 4.153,50; ver RN-02 |
| valor_inicial | NUMERIC(18,2) | PNCP `valorInicial` | mediana R$ 4.000,00; difere do global em 2,09% dos casos, indicando aditivo |
| prazo_dias | INTEGER | derivada das datas de vigência | fim menos início |
| ano_contrato | SMALLINT | PNCP `anoContrato` | varia de 2021 a 2025 |
| numero_parcelas | SMALLINT | PNCP `numeroParcelas` | ver a nota de qualidade abaixo |
| receita | BOOLEAN | PNCP `receita` | |
| emenda_parlamentar | BOOLEAN | PNCP `emendaParlamentar` | normalizado: vem nulo quando falso em 99,8% dos casos |
| fruto_adesao | BOOLEAN | PNCP `frutoAdesao` | mesma normalização |

Duas notas de qualidade sobre esta tabela.

A primeira, sobre valor. O máximo bruto de `valor_global` é de 640 bilhões de
reais, e vinte e seis contratos acima de um bilhão concentram 98,7% do valor
somado. São erros de digitação na origem, e a RN-02 os exclui. O dicionário
registra o valor bruto para que ninguém se surpreenda ao consultar o dado antes
do filtro.

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
| cnpj | TEXT | `orgaoEntidade.cnpj` | 3.495 distintos, único |
| razao_social | TEXT | `orgaoEntidade.razaoSocial` | espaços normalizados |
| poder | TEXT | `orgaoEntidade.poderId` | E 30.863, N 24.917, L 1.985, J 1.004 |
| esfera | TEXT | `orgaoEntidade.esferaId` | M 33.091, F 17.023, E 7.730, N 862, D 63 |

A distribuição por esfera merece atenção analítica: a base é predominantemente
municipal, com 56,3% dos contratos, e não federal. Isso tem consequência direta
sobre heterogeneidade de preenchimento.

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
| cnpj_raiz | TEXT | derivada de `niFornecedor` | 20.436 distintos. Nulo para pessoa física |
| razao_social | TEXT | PNCP `nomeRazaoSocialFornecedor` | disponível |
| tipo_pessoa | TEXT | PNCP `tipoPessoa` | PJ 57.142, PF 1.400, PE 227 |
| natureza_juridica | TEXT | Receita, EMPRESAS coluna 3 | pendente. Grupo 1XXX identifica ente público |
| porte | TEXT | Receita, EMPRESAS coluna 6 | pendente. 00 não informado, 01 micro, 03 pequeno, 05 demais |
| capital_social | NUMERIC(18,2) | Receita, EMPRESAS coluna 5 | pendente. Vem com vírgula decimal |
| cnae_principal | TEXT | Receita, ESTABELECIMENTOS coluna 12 | pendente. 7 dígitos sem pontuação |
| id_municipio_sede | INTEGER | Receita, ESTABELECIMENTOS coluna 21 | pendente. Exige tradução de código |
| data_inicio_ativ | DATE | Receita, ESTABELECIMENTOS coluna 11 | pendente. Formato AAAAMMDD, ausente como 00000000 |

O grão é a raiz e não o CNPJ completo porque o quadro societário pertence à
empresa, não ao estabelecimento. Ver RN-01.

Os 1.650 registros sem `cnpj_raiz` são os fornecedores pessoa física e os de
identificador irregular, que por definição não têm quadro societário.

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
O piloto mediu 5,7% de indeterminados, e essa taxa é resultado, não falha.

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
erro clássico desse arquivo: usar apenas o código 22, de sócio, perderia MEI,
empresário individual e sociedade unipessoal, onde o dono aparece como 50 ou 65.
Os grupos estão enumerados na RN-03.

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

Os campos `orgaoSubRogado` e `unidadeSubRogada` estão presentes em menos de 1%
dos contratos e não são consumidos por nenhuma pergunta analítica.

O campo `valorAcumulado` é nulo em 55,99% dos registros, o que o inviabiliza
como métrica principal.

Os campos de telefone, fax e correio eletrônico dos estabelecimentos da Receita
são dados pessoais de contato e não entram no modelo, por aplicação da RN-09.
