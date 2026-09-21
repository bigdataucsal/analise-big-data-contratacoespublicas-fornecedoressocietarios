# Regras de negócio

Entrega da Trilha 3. Cada regra traz o enunciado, a justificativa e, quando já
existe, o número medido que a sustenta. É a justificativa que importa: dizer
que tratamos os dados não é regra de negócio, dizer o que fizemos e por que é.

Onde a regra mudou em relação ao esboço inicial do projeto, a mudança está
marcada e explicada, porque quase todas vieram de coisa que só apareceu ao
olhar o dado real.

## RN-01. Normalização de identificadores

Todo CNPJ é tratado como texto de catorze caracteres com zeros à esquerda
preservados. A chave de junção com o quadro societário é a raiz de oito
caracteres, obtida pelos oito primeiros dígitos.

Por quê: o quadro societário é atributo da empresa e não do estabelecimento. A
tabela de sócios da Receita Federal é chaveada pela raiz de oito dígitos, e o
PDF oficial a descreve como número base de inscrição. Uma junção direta do CNPJ
de catorze dígitos do contrato com essa coluna retorna zero linhas, sem erro
nenhum, o que é o tipo de falha que custa um dia de trabalho até alguém
perceber.

A conversão para tipo numérico é proibida porque destrói zeros à esquerda:
00394429000102 viraria 394429000102 e deixaria de casar com qualquer base.

Medido: 97,40% dos fornecedores têm identificador de catorze dígitos, 2,42%
têm onze, que são CPF e portanto não possuem quadro societário, e 0,16% têm
identificadores irregulares, com sete, nove, três ou nenhum dígito.

## RN-02. Elegibilidade do contrato

Entram na análise contratos com valor global maior que zero e menor ou igual a
um bilhão de reais, com data de publicação dentro do recorte.

Por quê: o limite inferior é óbvio, contrato sem valor não representa
transferência de recurso. O limite superior é a mudança em relação ao esboço
inicial, e é a mais importante deste documento.

Medimos que vinte e seis contratos, que são 0,04% da base, concentram 98,7% do
valor somado. Os quatro maiores são de 640 bilhões, 640 bilhões, 562,5 bilhões
e 250 bilhões de reais, todos do mesmo órgão. O somatório de vinte dias de
contratações chegava a 2,6 trilhões de reais, aproximadamente metade do
orçamento federal anual. Não são contratos, são erros de digitação na origem,
muito provavelmente valores registrados sem o separador decimal.

Sem esse corte, a mediana de 4.153,50 reais convive com uma média de
45.013.038,24, que é 10.837 vezes maior, e qualquer agregação por valor passa a
descrever os erros em vez dos contratos. Com o corte, o somatório de vinte dias
cai para 33,3 bilhões, que é plausível.

O limite de um bilhão é uma escolha e precisa ser declarado como tal. É uma
ordem de grandeza acima do maior contrato federal plausível para um objeto
único. Ele exclui 0,04% dos registros, e esse percentual deve ser reportado
sempre que o valor agregado for apresentado.

## RN-03. Definição de sócio com poder de controle

Entram no cálculo de gênero os sócios pessoa física, identificados pelo código
2 na coluna de identificador de sócio, cuja qualificação pertença a um dos três
grupos abaixo. Representante legal e procurador ficam de fora.

O grupo de participação societária reúne os códigos 22, 23, 24, 25, 26, 28, 29,
30, 31, 37, 38, 47, 48, 49, 52, 55, 56, 57, 58 e 74.

O grupo de titularidade de empresa individual, EIRELI e sociedade limitada
unipessoal reúne os códigos 34, 50, 65, 66, 67, 68, 78 e 79.

O grupo de administração e controle reúne os códigos 05, 08, 10, 16, 64, 70,
71, 72 e 73.

Por quê: o esboço inicial dizia apenas que entram os sócios cuja qualificação
indique participação societária ou administração. Uma leitura literal disso
filtraria pelo código 22, de sócio, e perderia uma faixa inteira de
fornecedores. Muitos fornecedores pequenos do setor público são MEI, empresário
individual ou sociedade unipessoal, e nesses casos o dono aparece com o código
50 ou 65, não com o 22. Nomear os três grupos explicitamente resolve isso.

A distinção entre sócio pessoa física e pessoa jurídica é feita pelo
identificador de sócio, nunca pelo formato do documento. O CPF vem mascarado e
preenchido com zeros até catorze caracteres, e desde agosto de 2026 o CNPJ do
sócio pessoa jurídica passou a vir com oito dígitos em vez de catorze, de modo
que o comprimento do campo não separa os casos de forma confiável.

Dois casos exigem decisão explícita do grupo. O código 53, de sócio sem
capital, é formalmente sócio mas não participa do capital. O código 63, de
cotas em tesouraria, não é uma pessoa: são quotas da própria empresa, e aparece
com nome e documento vazios. A decisão atual é excluir os dois, e a exclusão
deve ser reportada.

## RN-04. Inferência de gênero

O primeiro nome normalizado, em maiúsculas e sem acento, é classificado como
feminino ou masculino quando a frequência da categoria dominante na base de
nomes do IBGE alcança 90% da soma das frequências masculina e feminina. Caso
contrário, ou se o nome não constar da base, a classificação é indeterminado.

Por quê: gênero não é observável no registro societário. O limiar torna o erro
mensurável, e a categoria indeterminado impede que a incerteza seja escondida
dentro de uma das duas classes.

O denominador é sempre a soma de masculino mais feminino, nunca o total que a
API devolve sem o parâmetro de sexo. A supressão de valores pequenos do IBGE é
aplicada célula a célula, então o total agregado é maior que a soma dos sexos:
medimos dezenove ocorrências de diferença no nome ALEX. Usar o total agregado
subestimaria a proporção.

Medido no piloto, sobre mil nomes que são 563 primeiros nomes distintos: 45,3%
feminino, 49,0% masculino e 5,7% indeterminado. Dos indeterminados, 4,1 pontos
percentuais são nomes ausentes da base, suprimidos por terem menos de vinte
ocorrências no país, e 1,6 ponto são nomes genuinamente ambíguos.

A sensibilidade ao limiar foi medida: 4,8% de indeterminados a 80%, 5,7% a 90%,
6,6% a 95% e 10,0% a 99%. A escolha dos 90% fica no ponto em que o ganho de
precisão ainda não custa muita cobertura.

Ressalva: o piloto rodou sobre fornecedores pessoa física do PNCP, porque a
base de sócios ainda não estava disponível. A taxa definitiva sai quando o
piloto rodar sobre os sócios, que é a população à qual a regra se aplica.

## RN-05. Classificação de controle da empresa

Uma empresa é classificada como de controle feminino quando mais de 50% dos
seus sócios elegíveis pela RN-03 são classificados como femininos, e como de
controle masculino no caso simétrico. É classificada como misto ou
indeterminado quando houver empate, quando houver sócio pessoa jurídica no
quadro, ou quando a taxa de indeterminados da própria empresa passar de um
terço.

Por quê: contagem por cabeça é a única opção disponível, porque o percentual de
participação de cada sócio no capital não consta dos dados abertos da Receita
Federal. Declarar isso é obrigatório, e é a principal limitação metodológica do
trabalho.

A regra da empresa com sócio pessoa jurídica no quadro existe porque cadeias
societárias tornam o gênero indefinível sem resolver a cadeia inteira, o que
está fora do escopo do semestre.

## RN-06. Proxy de composição por cor ou raça

Cada empresa recebe um vetor de composição racial derivado do município da sua
sede, a partir do Censo 2022, e do setor CNAE, a partir da RAIS. O indicador é
atribuído ao contexto da empresa, nunca a uma pessoa.

Por quê: não existe base pública que ligue um CPF a uma declaração de cor ou
raça, e é bom que não exista. Cor e raça são dado sensível pelo artigo 5 da
LGPD, e inferir no nível individual por cruzamento de nome com bases que trazem
raça autodeclarada, como a de candidaturas eleitorais, seria reidentificação de
dado sensível. Esse caminho foi avaliado e rejeitado, e a rejeição é parte do
parecer de conformidade.

O que resta é inferência ecológica, com a limitação clássica do método: a
composição do grupo não se transfere para o indivíduo. Um município com 80% de
população negra não autoriza afirmar nada sobre os sócios das empresas de lá.

Os dois eixos não são substitutos. O Censo descreve quem mora no município, a
RAIS descreve quem trabalha formalmente naquele setor naquele município.

Medido: a composição dos 5.570 municípios já está baixada. O percentual de
população negra, somando preta e parda, vai de 2,5% a 97,2%, com mediana de
60,8%.

Uma limitação do lado da RAIS precisa ser declarada: os microdados públicos são
desidentificados e não trazem o CNPJ do empregador, o que obriga o cruzamento a
ser por CNAE e município e nunca empresa a empresa.

## RN-07. Concentração societária

Um sócio é considerado multiempresa quando integra duas ou mais empresas com
contrato dentro do recorte. O valor controlado por sócio é a soma dos valores
contratados dessas empresas, e a soma é marcada como sobreposta quando a mesma
empresa tiver mais de um sócio multiempresa.

Por quê: sem a marcação de sobreposição, o somatório por sócio ultrapassa o
total contratado e a métrica perde sentido, porque o mesmo valor é contado uma
vez para cada sócio da empresa.

Quais sócios contam aqui, e por que diferem da RN-05. Para concentração entram
apenas os grupos de participação societária e de titularidade, ficando de fora
o grupo de administração. A razão é que a pergunta da concentração é sobre
controle de capital, ou seja, quem é dono do que recebe recurso público, e um
administrador contratado sem participação no capital não é dono. Já a RN-05,
que classifica o controle da empresa por gênero, inclui a administração, porque
ali a pergunta é sobre quem decide, e administrar é decidir. As duas regras
usam recortes diferentes de propósito, e as visões materializadas do schema
refletem essa diferença.

É esta regra que determina qual estratégia de redução de volume adotamos.

O guia do projeto oferece três caminhos para caber no limite de 1 GB do plano
gratuito: filtros, agregações ou amostragem estatística. Escolhemos os dois
primeiros e descartamos o terceiro, e o motivo está nesta regra.

Análise de rede depende de enxergar todos os contratos de cada sócio dentro do
recorte. Uma amostra aleatória transformaria um sócio com oito empresas num
sócio com duas, e a métrica de concentração passaria a subestimar
sistematicamente o próprio fenômeno que se quer medir. Recortar por órgão
reduz o universo mas preserva a rede íntegra dentro dele; amostrar reduz o
universo fragmentando a rede.

Não se trata portanto de ignorar a amostragem, e sim de escolher, entre as três
opções oferecidas, as duas compatíveis com a pergunta analítica. Para uma
análise que fosse puramente de agregados de valor, a amostragem seria
perfeitamente adequada.

## RN-08. Marcação de sanção e vínculo societário na data

Um contrato é marcado como firmado com fornecedor sancionado quando o CNPJ
constar do CEIS ou do CNEP com sanção vigente na data de assinatura, e não na
data de consulta.

Por quê: comparar contra a lista atual produziria acusação indevida contra
contratos legítimos anteriores à sanção.

Acréscimo que o levantamento tornou necessário: a mesma cautela temporal não
pode ser aplicada ao vínculo societário, porque os dados não permitem. O
arquivo de sócios da Receita não tem data de saída da sociedade, é um retrato
da competência, e sócios que saíram desaparecem na competência seguinte.

Com uma única competência, o que se pode afirmar é quem é sócio hoje de uma
empresa que foi contratada naquela data, e não quem era sócio na data do
contrato. São afirmações diferentes e apenas a primeira se sustenta. Toda
apresentação de resultado societário deve declarar a competência utilizada.

## RN-09. Anonimização e mínimo de agregação

O CPF, ainda que mascarado na origem, nunca é armazenado na camada de
apresentação nem exibido. O nome do sócio é substituído por identificador
derivado. Nenhum recorte do painel exibe resultado baseado em menos de cinco
sócios ou cinco empresas.

Por quê: agregados pequenos permitem reidentificação. É o mesmo princípio que o
IBGE aplica ao suprimir nomes com menos de vinte ocorrências no país, e citar
esse paralelo mostra que a decisão foi consciente e não improvisada.

O CPF mascarado da Receita preserva os seis dígitos do meio, o que basta para
agrupar o mesmo sócio entre empresas, que é exatamente o que a análise de rede
precisa, sem identificar a pessoa.

Vale registrar que essa máscara não é escolha da Receita nem nossa: o PDF de
metadados do CNPJ declara que o CPF é descaracterizado por ocultação dos três
primeiros dígitos e dos dois dígitos verificadores, citando o art. 129 § 2º da
Lei nº 13.473/2017, a LDO de 2018. O dado já chega desidentificado por
exigência legal, e esta regra apenas garante que não o reidentifiquemos ao
longo do pipeline. Ele é usado como chave interna na camada de
dados e substituído por identificador derivado antes de qualquer exibição.

O filtro de agregação mínima fica na camada de apresentação e não nas visões
materializadas, porque o mesmo agregado pode ser seguro num recorte e inseguro
noutro.

## Recorte

O recorte não é uma regra de negócio, mas condiciona todas elas e por isso está
registrado aqui.

O período é o ano de 2025, por data de publicação no PNCP. Vale notar que
62,65% dos contratos publicados no período têm ano de contrato 2024, ou seja, a
coleta por data de publicação captura majoritariamente contratos assinados no
ano anterior. Isso não é erro do dado, é característica da fonte, mas obriga a
declarar em cada análise se o eixo temporal é a publicação ou a assinatura.

O recorte institucional são os cinquenta órgãos com maior valor contratado
depois de aplicada a RN-02. Eles representam 11,0% dos contratos e 71,0% do
valor. A justificativa é que o objeto do trabalho é para onde o dinheiro público
flui, e esses órgãos concentram a maior parte dele.

O recorte é gerado e documentado por `etl/recorte_cnpjs.py`, que produz a lista
de raízes de CNPJ usada para filtrar os arquivos da Receita Federal e um
arquivo com o recorte por escrito.
