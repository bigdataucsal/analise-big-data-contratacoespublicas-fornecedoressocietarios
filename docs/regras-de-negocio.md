# Regras de negócio

Entrega da Trilha 3. Cada regra traz o enunciado, a justificativa e, quando já
existe, o número medido que a sustenta. É a justificativa que importa: dizer
que tratamos os dados não é regra de negócio, dizer o que fizemos e por que é.

Onde a regra mudou em relação ao esboço inicial do projeto, a mudança está
marcada e explicada, porque quase todas vieram de coisa que só apareceu ao
olhar o dado real.

Revisado em 02/10/2026. Os números agora vêm da coleta completa de 2025
(2.023.134 contratos) e da Receita filtrada (239.600 empresas, 339.385 sócios).
A primeira versão deste documento foi escrita sobre a amostra de 1 a 20 de
janeiro, e vários números dela não valiam para o ano. Onde um número de janeiro
foi mantido como histórico, ele está marcado `[AMOSTRA JAN]`; onde depende de
medição ainda não feita, `[PENDENTE]`. As decisões citadas como D1 a D9 estão em
`docs/decisoes-do-grupo.md`.

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

Medido no ano inteiro: 3,76% dos contratos têm fornecedor com identificador de
onze dígitos, que são CPF e portanto não possuem quadro societário, 0,17% têm
identificador com tamanho diferente de onze e de catorze, e o restante, cerca de
96,1%, tem catorze dígitos. Os de tamanho irregular são todos do tipo PE,
fornecedor estrangeiro, cujo documento não segue o formato brasileiro; não são
erro de digitação, como a amostra de janeiro dava a entender (lá eram 97,40%,
2,42% e 0,16% `[AMOSTRA JAN]`). Dois contratos do ano vêm sem identificador
nenhum.

Acréscimo de 02/10/2026: quem tem raiz de CNPJ, e o que acontece com quem não
tem. Só recebe raiz o fornecedor com `tipoPessoa` igual a PJ e identificador de
catorze dígitos. É o mesmo critério no `recorte_cnpjs.py` e no tratamento. O
campo do dado real se chama `tipoPessoa`; o roteiro fala em
`tipoPessoaFornecedor`, que não existe em nenhum dos 41 campos de topo do
contrato. Ficam sem raiz os fornecedores pessoa física, os estrangeiros e os PJ
com identificador irregular, e também os 1.979 contratos em que tipo e tamanho
se contradizem (1.472 marcados como PJ com onze dígitos e 507 marcados como PF
com catorze). No ano são 82.784 contratos. Depois do filtro de valor da RN-02
sobram 78.795 na fato, 3,9% dos contratos, que somam R$ 16,9 bilhões, 2,2% do
valor depois do corte de sanidade.

Esses contratos formam um universo declarado à parte. Continuam na contagem de
contratos e no valor total do universo, mas não entram em nenhum indicador de
controle societário, porque não há quadro societário a cruzar. Na tabela de
fatos eles ficam com fornecedor nulo, e as visões dos KPIs os deixam de fora
pela própria junção com a dimensão de fornecedor. Todo resultado de gênero do
controle vale, portanto, para os contratos com raiz de CNPJ, e deve vir
acompanhado do tamanho deste universo. Não confundir com os empresários
individuais da RN-05: esses têm raiz de CNPJ, mas não têm sócio na base.

## RN-02. Elegibilidade do contrato

Um contrato entra nos indicadores de valor e nos KPIs quando cumpre quatro
condições: foi publicado no PNCP dentro do período; tem valor global maior que
zero, contado em centavos; tem valor global de até um bilhão de reais; e não é
contrato de receita. Quem falha na terceira ou na quarta condição não é apagado:
fica marcado e continua na descrição do universo. Uma quinta condição do
esboço, tirar os contratos anulados ou cancelados, não está implementada, e o
motivo está no fim desta regra.

Alteração de 02/10/2026: entrou a condição de receita (decisão D9), o teto de um
bilhão passou de exclusão para marcação (D3), o valor maior que zero passou a
ser contado em centavos, e os números foram refeitos com o ano inteiro.

Por quê, condição a condição.

O período segue a data de publicação, porque é por ela que a API do PNCP
consulta e foi por ela que a coleta foi feita (D7). No ano, a diferença para a
data de assinatura é pequena; ver a seção Recorte.

O limite inferior parece óbvio, contrato sem valor não representa transferência
de recurso, mas ele esconde um detalhe. No ano, 17.823 contratos (0,88%) têm
valor zero em centavos, e nenhum tem valor negativo ou nulo. O JSON bruto, lido
antes do tratamento, tem 245 contratos a menos com valor zero, porque traz 245
valores positivos menores que meio centavo, que o tratamento arredonda para
R$ 0,00 ao gravar o valor com duas casas decimais (contagem feita pela T2 no
JSON bruto do ano, em 02/10/2026). Nos 20 dias de janeiro que
reproduzimos, os casos desse tipo são todos de R$ 0,0001, valor simbólico que
não representa pagamento `[AMOSTRA JAN]`. Por isso a regra vale para o valor em
centavos, que é o que vai para o Parquet e para o banco.

O limite superior foi a mudança mais importante em relação ao esboço. No ano, o
valor global somado dos 2.023.134 contratos é de R$ 18,25 trilhões, e 95,77%
desse total está em 243 contratos (0,012% da base) acima de um bilhão; sem eles,
sobram R$ 771,2 bilhões. Os quatro maiores têm R$ 6,03 trilhões, R$ 1,96
trilhão, R$ 1,12 trilhão e R$ 1,03 trilhão, de quatro órgãos diferentes. A
auditoria mostra dois padrões. Um é erro de escala: no maior contrato do ano o
valor global é mil vezes o da parcela. O outro é concentração em poucas origens,
com credenciamentos de serviços de saúde de valores redondos e repetidos, em que
o valor parece ser um teto estimado do credenciamento, e não o preço
contratado. Essa segunda leitura é hipótese, a confirmar no CSV de auditoria.
Nos dois casos, o número não descreve dinheiro que mudou de mão.

Sem o corte, a mediana de R$ 3.486,00 convive com uma média de R$ 9.101.366,39,
cerca de 2.611 vezes maior, e qualquer agregação por valor passa a descrever os
erros em vez dos contratos. Com o corte, a média cai para R$ 384.638,09 e a
mediana quase não se move (R$ 3.484,00). Na amostra de janeiro a distorção
parecia ainda maior: 26 contratos concentravam 98,7% do valor e a média passava
de 10 mil vezes a mediana `[AMOSTRA JAN]`. A primeira versão desta regra citava
a mediana de janeiro como R$ 4.153,50, calculada com os contratos de valor zero;
só com valor maior que zero, que é a base usada para o ano, ela era R$ 4.260,00.

O limite de um bilhão é uma escolha e precisa ser declarado como tal. Ele atinge
0,012% dos registros no ano, e esse percentual deve acompanhar todo valor
agregado que for apresentado. Os contratos acima dele não são apagados:
continuam no Parquet e no CSV de auditoria e só saem dos indicadores de valor
(D3). A escolha foi testada contra os vizinhos. Acima de R$ 100 milhões são
1.432 contratos e sobram R$ 444 bilhões; acima de R$ 10 bilhões são 78 e sobram
R$ 1.178 bilhões. Os 1.189 contratos entre R$ 100 milhões e um bilhão somam
R$ 327 bilhões, 42% do que sobra depois do corte, e podem ter o mesmo tipo de
erro. Por isso o KPI 1 roda também com o corte de R$ 100 milhões, como
sensibilidade, na Fase 2.

A condição de receita é nova. O campo `receita` do PNCP separa o contrato de
receita (verdadeiro) do contrato de despesa (falso). No contrato de receita o
dinheiro anda ao contrário: é o fornecedor quem paga o órgão, como na alienação
de mercadorias apreendidas ou na cessão onerosa de um espaço público. Somar esse
contrato aos de despesa infla o total e mistura dois fenômenos opostos, e nenhum
deles é recurso público recebido por fornecedor. No ano, depois do corte de
sanidade, são 20.439 contratos (1,02%) e R$ 12,2 bilhões (1,6% do valor); sem
eles, a despesa soma R$ 759,0 bilhões em 1.984.629 contratos. Eles ficam
marcados e saem dos indicadores de valor e dos KPIs, aparecendo só na descrição
do universo (D9).

A marca, porém, não é confiável sozinha, e isso precisa estar escrito. O campo é
preenchido pelo órgão e erra nos dois sentidos. Nos 20 dias de janeiro que
temos localmente, depois do corte, 493 contratos vêm com `receita` verdadeira, e
em 256 deles o objeto só descreve compra, serviço ou obra (separação feita por
palavras do texto do objeto, nesta revisão): aquisição de caminhões, de
material laboratorial, serviços de jardinagem, pavimentação asfáltica
`[AMOSTRA JAN]`. Pelo valor o quadro se inverte, porque os contratos
de receita de verdade são maiores: o maior marcado é a venda de cotas de um
fundo imobiliário estadual, de R$ 470 milhões, e cerca de dois terços do valor
marcado tem objeto de receita. E há alienações de imóveis sem a marca. A
categoria do processo também não resolve, porque aquela venda de cotas está
classificada como serviço. A composição no ano inteiro não foi medida
`[PENDENTE]`.

Daí a forma da regra. A exclusão segue a marca, como decidido, porque é o campo
oficial e o efeito tem teto conhecido: no máximo 1,02% dos contratos e 1,6% do
valor. Mas todo indicador de valor é publicado também com os contratos marcados
incluídos, como sensibilidade, até que a marca seja conferida contra o objeto na
Fase 2.

A regra alcança também o universo de empresas. A lista de raízes do recorte foi
gerada antes desta condição, de modo que as 239.600 empresas e a classificação
de gênero da RN-05 incluem fornecedores que só aparecem em contratos de receita.
Quantos são no ano não foi medido `[PENDENTE]`; na amostra de janeiro eram 267
de 20.240 raízes, 1,3% `[AMOSTRA JAN]`.

Anulados e cancelados não estão implementados. O esboço previa tirá-los da
análise, mas a coleta não traz campo de situação: entre os 41 campos de topo do
contrato, conferidos nos 58.769 registros de janeiro, nenhum indica anulação ou
cancelamento (D6). A exclusão fica pendente e depende de outra fonte, a avaliar
na Fase 2. Até lá, os indicadores podem incluir contratos cancelados depois de
publicados, e isso deve ser dito junto com eles.

Onde cada condição está implementada hoje:

| condição | `recorte_cnpjs.py` (lista de raízes) | tratamento e fato do benchmark | situação |
|---|---|---|---|
| publicação no período | sim, pela coleta | sim, pela coleta | implementada |
| valor maior que zero | sim, no valor bruto do JSON (2.005.313 contratos) | sim, em centavos (2.005.068) | implementada; os 245 de diferença estão explicados acima |
| até um bilhão | sim, como exclusão | sim, como exclusão | a marca no Parquet (D3) entra na Fase 2; hoje os 243 estão no CSV de auditoria |
| não ser receita | não | não; o campo está no Parquet e na fato | Fase 2 (D9) |
| não estar anulado ou cancelado | não | não | sem campo na coleta (D6) |

Como a lista de raízes usou o valor bruto, ela tem 39 raízes a mais do que teria
com a regra em centavos (239.605 contra 239.566, medido pela T2), menos de 0,02%
da lista. O script será alinhado quando a lista for regerada, na Fase 2.

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
filtraria pelo código 22, de sócio, e perderia quem é dono sem ser "sócio" no
cadastro, como o titular de EIRELI, que aparece com o código 65 (1.609 linhas no
recorte nacional). Nomear os três grupos explicitamente resolve isso.

Correção de 02/10/2026: a primeira versão desta regra dizia que o MEI e o
empresário individual aparecem com o código 50 ou 65. Não aparecem. O
empresário individual não tem quadro societário, e por isso não tem linha
nenhuma no arquivo de sócios: das 65.001 empresas do recorte sem sócio na base,
62.880 são empresários individuais. Nenhuma lista de qualificações os alcança, e
eles são tratados como universo à parte na RN-05.

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

Diretor (10), Presidente (16) e Conselheiro de Administração (08) entram no
grupo de administração (decisão D4). O motivo é que são eles que administram a
empresa, que é o que esta regra quer capturar. A escolha pesa: no recorte
nacional eles somam 25.375 das 327.180 linhas de sócio pessoa física, 7,8%
(13.182 de diretor, 10.579 de presidente e 1.614 de conselheiro). A rodada de
sensibilidade sem os três fica para a Fase 2, e até lá todo resultado de gênero
do controle deve ser lido com essa escolha declarada.

Como a regra está implementada hoje, e onde ela diverge deste texto. O
`classificar_empresas.py`, que produziu os números publicados, não usa a lista
de códigos acima. Ele inclui todo sócio pessoa física cuja descrição de
qualificação não contenha as palavras PROCURADOR ou REPRESENTANTE. No recorte
nacional essa regra não excluiu nenhuma linha (as 327.180 linhas de sócio pessoa
física entraram todas), e com isso entraram qualificações que a lista deixa de
fora: 53, sócio sem capital (1.395 linhas), que esta regra manda excluir; 54,
fundador (92); 59, produtor rural (113); e três qualificações com 8 linhas no
total, que o relatório do script não detalha. São no máximo 1.608 linhas, 0,49%
dos sócios elegíveis, e no máximo 1.608 empresas afetadas, menos de 1% das que
têm sócio. O efeito real sobre a classificação não foi medido. Alinhar o código
à lista entra na Fase 2, junto com a sensibilidade da D4.

## RN-04. Inferência de gênero

O primeiro nome normalizado, em maiúsculas e sem acento, é classificado como
feminino ou masculino quando a frequência da categoria dominante na base de
nomes do IBGE alcança 90% da soma das frequências masculina e feminina. Caso
contrário, ou se o nome não constar da base, a classificação é indeterminado.

A base de nomes é a do Censo Demográfico 2022, consultada pela API v3 do IBGE; o
roteiro cita o Censo 2010, base da API v2, que só foi usada no piloto inicial
(5,7% de indeterminados) e não em nenhum número atual.

Por quê: gênero não é observável no registro societário. O limiar torna o erro
mensurável, e a categoria indeterminado impede que a incerteza seja escondida
dentro de uma das duas classes.

O denominador é sempre a soma de masculino mais feminino, nunca o total que a
API devolve sem o parâmetro de sexo. A supressão de valores pequenos do IBGE é
aplicada célula a célula, então o total agregado é maior que a soma dos sexos:
medimos dezenove ocorrências de diferença no nome ALEX, na API v2. Na v3, que
devolve os dois sexos numa chamada só, o total de ALEX é exatamente a soma dos
sexos, mas a regra continua valendo como proteção. Usar o total agregado
subestimaria a proporção.

Medido nos sócios, que é a população à qual a regra se aplica: dos 327.180
sócios pessoa física elegíveis do recorte nacional, 34,3% ficaram femininos,
61,8% masculinos e 4,0% indeterminados (112.164, 202.077 e 12.939), a partir de
28.048 primeiros nomes distintos. Nas rodadas intermediárias, com a mesma API, a
taxa de indeterminados foi de 3,7% num piloto de mil sócios e de 3,9% no recorte
inicial de 50 órgãos. A evidência da rodada nacional está em
`docs/evidencias/classificacao_genero.txt`.

O piloto que sustentou a escolha do limiar é anterior a tudo isso. Rodou sobre
mil fornecedores pessoa física do PNCP, com 563 primeiros nomes distintos,
porque a base de sócios ainda não estava disponível, e usou a API v2, do Censo
2010. Deu 45,3% feminino, 49,0% masculino e 5,7% indeterminado; dos
indeterminados, 4,1 pontos eram nomes ausentes da base, suprimidos por terem
menos de vinte ocorrências no país, e 1,6 ponto eram nomes genuinamente
ambíguos. A sensibilidade ao limiar foi medida nesse piloto: 4,8% de
indeterminados a 80%, 5,7% a 90%, 6,6% a 95% e 10,0% a 99%. A escolha dos 90%
fica no ponto em que o ganho de precisão ainda não custa muita cobertura.

A queda de 5,7% para 4,0% mistura duas mudanças, a população (de fornecedores
pessoa física para sócios) e a base (de 2010 para 2022), e o que foi medido não
permite separar uma da outra. A sensibilidade ao limiar nos sócios, com o Censo
2022, fica para a Fase 2.

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

Dois casos ficam fora da classificação, e os dois foram decididos depois de ver
o dado. A empresa sem nenhuma linha de sócio na base não tem controle inferível
e forma um universo declarado à parte, sem inferência pelo nome do titular
(decisão D5): são 65.001 empresas, 27,1% do recorte, das quais 62.880 são
empresários individuais, 26,2% do recorte; as outras 2.121 incluem municípios,
autarquias, sindicatos e consórcios públicos. Inferir o gênero do titular pela
razão social exigiria tratar nome de pessoa física a partir de outro campo, o
que pesa na LGPD, e fica como extensão opcional da Fase 2. Já o sócio
estrangeiro, identificador 3, não entra na contagem de gênero nem aciona a
regra do sócio pessoa jurídica, e a empresa que só tem sócio estrangeiro fica
como indeterminada, sem sócio elegível.

Medido no recorte nacional:

| classificação | empresas | % do recorte |
|---|---|---|
| masculino (maioria) | 91.519 | 38,2% |
| feminino (maioria) | 39.904 | 16,7% |
| misto ou indeterminado, sem maioria | 26.817 | 11,2% |
| misto ou indeterminado, mais de um terço de indeterminados | 8.282 | 3,5% |
| misto ou indeterminado, com sócio pessoa jurídica | 8.076 | 3,4% |
| indeterminado, só com sócio estrangeiro | 1 | 0,0% |
| sem sócio na base (62.880 empresários individuais) | 65.001 | 27,1% |
| total | 239.600 | 100% |

As seis primeiras linhas somam as 174.599 empresas com sócio na base. A soma que
circulou antes (131.423 + 26.817 + 8.282 + 8.076 = 174.598) esquecia a empresa
da sexta linha, que o relatório do script mostra como `sem_socio_elegivel`. Que
ela só tem sócio estrangeiro é dedução, e não contagem: como nenhuma linha de
sócio pessoa física foi excluída pela RN-03 no recorte (ver acima), uma empresa
com sócio na base só fica sem sócio elegível se não tiver sócio pessoa física
nem jurídica, e o recorte tem 2 linhas de sócio estrangeiro. Para confirmar,
basta filtrar o `genero_por_empresa.csv` pelo motivo `sem_socio_elegivel` e olhar
a coluna `socios_estrangeiros`; o arquivo está na máquina da T2, não nesta.

O que o KPI 1 mede hoje: os 30,4% de controle feminino contam empresas, não
valor. São 39.904 empresas femininas entre as 131.423 de controle definido. O
cruzamento com o valor dos contratos, que é o que o KPI 1 pede, fica para a
Fase 2, e até lá nenhum texto deve apresentar os 30,4% como participação no
valor contratado. A contagem também inclui empresas que só aparecem em contratos
de receita (ver RN-02).

A visão materializada do KPI em `etl/schema_estrela.sql` ainda não aplica esta
regra por inteiro: ela não olha o sócio pessoa jurídica e põe as empresas sem
sócio na base junto com as mistas. Os números publicados vêm do
`classificar_empresas.py`, e a visão será alinhada na carga da Fase 2.

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
usam recortes diferentes, e as visões materializadas do schema
refletem essa diferença.

É esta regra que determina qual estratégia de redução de volume adotamos.

O guia do projeto oferece três caminhos para caber no limite de 1 GB do plano
gratuito: filtros, agregações ou amostragem estatística. Escolhemos os dois
primeiros e descartamos o terceiro, e o motivo está nesta regra.

Análise de rede depende de enxergar todos os contratos de cada sócio dentro do
recorte. Uma amostra aleatória transformaria um sócio com oito empresas num
sócio com duas, e a métrica de concentração passaria a subestimar
sistematicamente o próprio fenômeno que se quer medir. Recortar, seja por
período, por órgão ou por regra de elegibilidade, reduz o universo mas preserva
a rede íntegra dentro dele; amostrar reduz o universo fragmentando a rede.

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

Essa máscara não é escolha da Receita nem nossa: o PDF de
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

O período é o ano de 2025, por data de publicação no PNCP (D7). No ano inteiro,
7,05% dos contratos publicados têm ano de contrato 2024, 92,69% têm 2025 e 0,25%
têm outro valor ou nenhum, de modo que a coleta por data de publicação pouco
difere de uma coleta por ano do contrato. A primeira versão deste documento
dizia que eram 62,65%, e dizia isso do período inteiro. Era o número de 1 a 20
de janeiro, quando a maior parte do que se publica ainda é do ano anterior, e foi o
caso mais claro de número de amostra que não valia para o ano. Mesmo com a
diferença pequena, cada análise deve declarar se o eixo temporal é a publicação
ou a assinatura.

A cobertura é nacional, sem recorte de órgão. O plano inicial era ficar com os
cinquenta órgãos de maior valor contratado depois da RN-02, que na amostra de
janeiro davam 11,0% dos contratos e 71,0% do valor `[AMOSTRA JAN]`. Ele foi
abandonado por dois motivos: o KPI de comparação entre estados exige cobertura
nacional, e o critério de valor selecionava justamente os órgãos que digitaram
valores errados (ver a Veracidade, em `docs/5-vs.md`).

O recorte é gerado e documentado por `etl/recorte_cnpjs.py`, rodado com
`--todos-orgaos`, que produz a lista de raízes de CNPJ usada para filtrar os
arquivos da Receita Federal (239.605 raízes, de 2.005.313 contratos) e um
arquivo com o recorte por escrito.
