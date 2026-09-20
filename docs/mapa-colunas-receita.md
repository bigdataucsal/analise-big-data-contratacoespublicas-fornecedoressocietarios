# Mapa de colunas dos Dados Abertos do CNPJ

Entrega da Trilha 3, semana 1. Lista as colunas que servem às perguntas
analíticas do projeto, com a fonte de cada informação e as armadilhas
conhecidas.

A fonte primária é o PDF de metadados publicado pela Receita Federal, e os
arquivos ficam em `arquivos.receitafederal.gov.br/dados/cnpj/`. Onde a
informação não está declarada no PDF oficial e veio de implementações de
parser já existentes, isso está dito explicitamente como fonte secundária,
porque a diferença importa: o que está no PDF é contrato, o que está em
parser de terceiro é observação.

## Formato dos arquivos

Não há linha de cabeçalho. A primeira linha já é dado, e o parser depende
inteiramente da ordem posicional das colunas. Ler com `header=None` e passar
os nomes na ordem correta é obrigatório.

O separador é ponto e vírgula, e essa é a única regra de formato declarada no
PDF oficial. Os campos de texto vêm entre aspas duplas, o que é observação de
fonte secundária, então convém usar um leitor CSV de verdade com
`quotechar` configurado em vez de dividir a linha na mão.

A codificação é latina, ISO 8859-1 ou cp1252 na prática, e não UTF-8. Isso
também é fonte secundária, confirmada por mais de um parser existente que
precisou tratar o cedilha de palavras como PRAÇA. O PDF oficial não declara a
codificação.

Datas vêm no formato AAAAMMDD como texto de oito caracteres, sem separador, e
datas ausentes aparecem como `00000000`, não como campo vazio nem nulo. Isso
precisa ser tratado antes de qualquer conversão.

O único campo decimal do conjunto é o capital social, que usa vírgula como
separador decimal e não tem separador de milhar.

A regra de ouro é ler todas as colunas como texto e converter depois. Zeros à
esquerda são significativos em CNPJ básico, ordem, dígito verificador, CEP,
código de município, CNAE e código de qualificação, e lê los como inteiro
destrói o dado silenciosamente.

Os arquivos grandes vêm particionados em dez partes com o mesmo layout, e é
preciso concatenar todas: uma raiz de CNPJ não está necessariamente na mesma
parte que seus sócios. A publicação é mensal, e cada competência é um retrato
independente.

## SOCIOS, o arquivo central do tema

É o arquivo que dá nome ao trabalho. Onze colunas, das quais cinco interessam
diretamente.

| ordem | coluna | para que serve |
|---|---|---|
| 1 | CNPJ_BASICO | chave de junção com a empresa contratada |
| 2 | IDENTIFICADOR_DE_SOCIO | separa sócio pessoa física de pessoa jurídica |
| 3 | NOME_DO_SOCIO_OU_RAZAO_SOCIAL | entrada da inferência de gênero |
| 5 | QUALIFICACAO_DO_SOCIO | define quem tem poder de controle |
| 11 | FAIXA_ETARIA | dimensão demográfica do sócio |

As outras seis são o CPF mascarado do sócio, a data de entrada na sociedade, o
país do sócio estrangeiro e os três campos do representante legal.

A coluna 1 é a raiz de oito dígitos, e não o CNPJ de catorze. Essa é a
armadilha mais cara do projeto inteiro: o contrato do PNCP traz o CNPJ
completo, e uma junção direta dele com esta coluna retorna zero linhas sem
nenhum erro. É preciso cortar os oito primeiros dígitos. O tratamento já gera
a coluna `cnpj_raiz_fornecedor` exatamente por isso.

A coluna 2 usa os códigos 1 para pessoa jurídica, 2 para pessoa física e 3
para estrangeiro. É por ela que se distingue o tipo de sócio, nunca pelo
formato do documento, e a razão disso aparece logo abaixo.

A coluna 4, do CPF ou CNPJ do sócio, tem três comportamentos distintos. Para
sócio pessoa física, o CPF vem mascarado e preenchido com zeros até catorze
caracteres, no formato `000***718468**`. Para sócio estrangeiro, o PDF oficial
declara que a informação não existe e o campo vem vazio. Para sócio pessoa
jurídica houve mudança em agosto de 2026: o campo passou a trazer apenas a
raiz de oito dígitos em vez do CNPJ completo. Como consequência, o comprimento
do campo não separa os casos de forma confiável, e é por isso que a coluna 2 é
o critério correto. Vale medir o comprimento do campo na competência que
baixarmos para confirmar qual formato está valendo.

A coluna 11, de faixa etária, usa os códigos 1 para 0 a 12 anos, 2 para 13 a
20, 3 para 21 a 30, 4 para 31 a 40, 5 para 41 a 50, 6 para 51 a 60, 7 para 61
a 70, 8 para 71 a 80, 9 para maiores de 80, e 0 para não se aplica, que é o
caso típico do sócio pessoa jurídica.

Duas armadilhas de leitura merecem registro. A coluna 10 é a qualificação do
representante legal e não do sócio, e confundi la com a coluna 5 é o erro
clássico desse arquivo. E o representante legal, nas colunas 8 a 10, é quem
representa o sócio menor, incapaz ou estrangeiro, não é um sócio: quando não
há representante, a coluna 8 vem com onze zeros, que não é um CPF válido e
precisa ser filtrado.

### A limitação metodológica mais séria do projeto

Não existe data de saída da sociedade. O arquivo é um retrato do quadro
societário vigente na competência, e sócios que saíram simplesmente
desaparecem na competência seguinte.

A consequência é direta e precisa estar declarada: com uma única competência
não é possível afirmar quem era sócio na data de assinatura de um contrato
passado. O que se pode afirmar é quem é sócio hoje de uma empresa que foi
contratada naquela data. São afirmações diferentes, e a segunda é a única que
os dados sustentam. Guardar competências mensais sucessivas permitiria
reconstruir entradas e saídas, mas isso está fora do escopo do semestre.

Isso afeta diretamente a RN-08 do roteiro, que marca contrato firmado com
fornecedor sancionado comparando a sanção vigente na data de assinatura. O
mesmo raciocínio vale para o vínculo societário, e por coerência a regra
precisa declarar que o quadro societário usado é o da competência baixada, não
o da data do contrato.

### Qualificação do sócio, e um erro que custaria caro

A coluna 5 junta com a tabela de domínio de qualificações. Os códigos não
formam faixa contínua: não existem 01 a 04, 06, 07, 18, 27, 33, 36, 44, 45,
69, 76 e 77, e presumir continuidade quebra qualquer filtro por intervalo.

Para o projeto, os códigos se organizam em três grupos.

O grupo de participação societária de fato, ou seja, quem tem capital, quota
ou ação, reúne os códigos 22, 23, 24, 25, 26, 28, 29, 30, 31, 37, 38, 47, 48,
49, 52, 55, 56, 57, 58 e 74. Quando o interesse for vínculo entre empresas,
somam se 20, de sociedade consorciada, e 21, de sociedade filiada.

O grupo de titularidade de empresa individual, EIRELI e sociedade limitada
unipessoal reúne 50, de empresário, os títulares pessoa física 65, 66, 67 e
68, os titulares pessoa jurídica 78 e 79, e o 34.

O grupo de administração e controle, que é poder de decisão com ou sem
capital, reúne 05 de administrador, 08 de conselheiro, 10 de diretor, 16 de
presidente, 64 de administrador judicial, e 70 a 73 para os residentes no
exterior. Os códigos 28, 31, 49 e 74 pertencem a dois grupos ao mesmo tempo,
porque são sócios que também administram.

A armadilha está no segundo grupo. Muitos fornecedores pequenos do setor
público são MEI, empresário individual ou sociedade unipessoal, e nesses casos
o dono aparece com o código 50 ou 65, e não com o 22 de sócio. A RN-03 do
roteiro, como está escrita, filtra por qualificação que indique participação
societária ou administração, e uma leitura literal disso perderia essa faixa
inteira de fornecedores. A regra precisa nomear os três grupos explicitamente.

Dois casos exigem decisão escrita. O código 53, de sócio sem capital, é
formalmente sócio mas não participa do capital. E o código 63, de cotas em
tesouraria, não é uma pessoa: são quotas da própria empresa, e costuma aparecer
com nome e documento vazios. Precisamos declarar se entram ou não no cálculo.

## EMPRESAS

Sete colunas, no nível da raiz do CNPJ. Interessam a razão social, na coluna 2,
a natureza jurídica, na coluna 3, o capital social, na coluna 5, e o porte, na
coluna 6.

A natureza jurídica junta com a tabela de domínio correspondente, e o grupo
que começa com 1 identifica órgãos e entidades públicas, o que permite separar
fornecedores privados de entes públicos contratando entre si.

O porte usa os códigos 00 para não informado, 01 para microempresa, 03 para
empresa de pequeno porte e 05 para demais. Não existem os códigos 02 e 04, e o
campo pode vir vazio.

A coluna 4 é a qualificação do responsável perante a Receita, e não a lista de
sócios. Usá la como se fosse quadro societário seria um erro grave, porque ela
traz uma única pessoa.

Este arquivo não contém o CNPJ de catorze dígitos em lugar nenhum.

## ESTABELECIMENTOS

Trinta colunas. É aqui que existe o CNPJ completo, que não vem pronto: é a
concatenação das colunas 1, 2 e 3, ou seja, a raiz de oito dígitos, mais a
ordem de quatro, mais o dígito verificador de dois.

Interessam ao projeto a coluna 4, que distingue matriz de filial com 1 e 2, a
coluna 6, de situação cadastral, a coluna 11, com a data de início de
atividade, que permite calcular a idade da empresa, a coluna 12, com o CNAE
fiscal principal, e as colunas 20 e 21, de unidade federativa e município.

A situação cadastral usa 01 para nula, 2 para ativa, 3 para suspensa, 4 para
inapta e 08 para baixada. O próprio PDF oficial mistura a grafia com e sem
zero à esquerda, e nos dados reais vem com dois caracteres, então convém
normalizar antes de comparar.

O CNAE principal tem sete dígitos sem pontuação. Já a coluna 13, do CNAE
secundário, é multivalorada: traz vários códigos separados por vírgula na
mesma célula, podendo ficar muito longa. Como o separador do arquivo é ponto e
vírgula, isso não quebra o parse, mas quebra qualquer conversão numérica e
exige separação em linhas se formos usá la.

### A armadilha do código de município

A coluna 21 traz o código de município da Receita Federal, que não é o código
do IBGE.

Isso importa diretamente para o proxy territorial de cor e raça. O PNCP nos dá
o código IBGE do município, e o Censo, no SIDRA, também é chaveado por código
IBGE. A Receita usa uma codificação própria, distribuída na tabela de domínio
de municípios do próprio conjunto. Para ligar a empresa ao perfil racial do seu
território é preciso passar por essa tabela de tradução, e não assumir que os
códigos são compatíveis.

## Como as colunas atendem às perguntas

A pergunta de assimetria de gênero na captura de recurso público usa o nome do
sócio para a inferência, a qualificação e o identificador de sócio para definir
quem conta como dono, e o CNPJ básico para ligar ao valor contratado que vem do
PNCP.

A pergunta interseccional, que cruza gênero do controle com composição de cor e
raça, usa adicionalmente o CNAE principal, para o proxy setorial, e a unidade
federativa com o município, para o proxy territorial, sempre atribuindo o
indicador ao contexto da empresa e nunca a uma pessoa.

A pergunta de concentração societária usa o CPF mascarado do sócio como
identificador estável de pessoa, o nome do sócio, e o CNPJ básico, montando a
tabela ponte entre empresa e sócio que permite contar em quantas empresas
fornecedoras cada sócio aparece.

O CPF mascarado merece uma observação de privacidade. Ele preserva seis dígitos
do meio, o que é suficiente para agrupar o mesmo sócio entre empresas, que é
exatamente o que a análise de rede precisa, sem identificar a pessoa. Mesmo
assim, pela RN-09, ele não é armazenado nem exibido na camada de apresentação:
serve apenas como chave interna, substituída por identificador derivado.

## O que isso muda nas regras de negócio

Três regras do roteiro precisam de ajuste antes de serem implementadas.

A RN-01, sobre normalização de identificadores, já está correta ao dizer que a
junção com o quadro societário é pela raiz de oito dígitos, e o levantamento
confirma o motivo com a fonte oficial.

A RN-03, sobre definição de sócio com poder de controle, precisa nomear os
códigos de qualificação de forma explícita, incluindo o grupo de titularidade,
sob pena de perder os fornecedores MEI e empresário individual.

A RN-08, e por extensão toda afirmação sobre vínculo societário, precisa
declarar que o quadro usado é o da competência baixada e não o da data do
contrato, porque o arquivo não tem data de saída.

## Fontes

A fonte primária de layout é o PDF de metadados do CNPJ publicado pela Receita
Federal, e a tabela de qualificações foi conferida contra o sistema oficial da
própria Receita. Os arquivos são publicados em
`arquivos.receitafederal.gov.br/dados/cnpj/`, com o conjunto também catalogado
no portal dados.gov.br.

Vieram de fonte secundária, ou seja, de implementações de parser já existentes
e não do PDF oficial: a codificação latina, o uso de aspas duplas nos campos de
texto, o formato de data AAAAMMDD com ausência representada por oito zeros, a
vírgula decimal no capital social, e a mudança de agosto de 2026 no formato do
documento do sócio pessoa jurídica. Todos esses pontos devem ser verificados
contra o arquivo real assim que a Trilha 2 concluir o download, e é exatamente
para isso que serve o inventário da amostra que ela está produzindo em
paralelo.
