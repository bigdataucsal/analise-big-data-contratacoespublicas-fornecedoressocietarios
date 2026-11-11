# Achados analíticos e limitações metodológicas

Entrega da Trilha 3. Os achados vêm das medições registradas em
`docs/5-vs.md`, `docs/regras-de-negocio.md` e `docs/escolha-do-banco.md`, e
cada um aponta para onde foi medido. As limitações não são ressalva de rodapé:
duas delas mudam o que as conclusões podem afirmar, e estão escritas antes dos
números por isso.

Recorte de tudo o que segue: contratos publicados no PNCP em 2025, cobertura
nacional, 2.023.134 registros; quadro societário da Receita Federal na
competência de 14/09/2026, filtrado pelas 239.605 raízes de CNPJ do recorte.

## O que limita a leitura, antes dos números

**O controle é contado por cabeça, não por capital.** O percentual de
participação de cada sócio não existe nos dados abertos da Receita Federal.
Uma empresa com uma sócia de 1% e um sócio de 99% é classificada como empate,
não como controle masculino. Essa é a principal limitação metodológica do
trabalho e não tem contorno com as fontes públicas disponíveis.

**Gênero é inferido, não observado.** Não há declaração de gênero no registro
societário. A inferência vem do primeiro nome contra a base de nomes do Censo
2022, com limiar de 90%, e produz 4,0% de indeterminados que são publicados
como categoria própria em vez de distribuídos entre as outras duas. O limiar é
escolha: a 80% os indeterminados cairiam para cerca de 4,8% e a 99% subiriam
para cerca de 10,0% (medido no piloto, com o Censo 2010).

**Cor e raça são do território, nunca da pessoa.** O indicador é a composição
do município da sede, do Censo 2022. A falácia ecológica se aplica
integralmente: um município com 80% de população negra não autoriza nenhuma
afirmação sobre os sócios das empresas de lá. O caminho de inferir no nível
individual, cruzando nome com bases de raça autodeclarada, foi avaliado e
rejeitado como reidentificação de dado sensível (art. 5 da LGPD), e a rejeição
faz parte do parecer em `docs/parecer-lgpd.md`.

**O vínculo societário não é datado.** O arquivo de sócios é um retrato de uma
competência e não traz data de saída da sociedade. O que se pode afirmar é quem
é sócio hoje de uma empresa que foi contratada naquela data, e não quem era
sócio na data do contrato. A sanção, por ter data, recebe tratamento temporal
correto (RN-08); o vínculo não pode receber o mesmo.

## Achados

### 1. O achado mais consequente é sobre a qualidade do dado, não sobre diversidade

O valor somado dos 2.023.134 contratos de 2025 é de R$ 18,25 trilhões, o que
equivale a mais de uma vez e meia o PIB brasileiro em contratos publicados num
único ano. O número é impossível, e descobrir por que ele é impossível foi a
parte mais produtiva da análise. Vale como teste de sanidade de graça: quando
um agregado de contratações supera o produto do país, o problema está no dado,
não na economia.

**243 contratos, 0,012% da base, concentram 95,77% de todo o valor.** Sem eles
sobram R$ 771,2 bilhões. Os quatro maiores, de quatro órgãos diferentes, valem
R$ 6,03 trilhões, R$ 1,96 trilhão, R$ 1,12 trilhão e R$ 1,03 trilhão. A
auditoria em `docs/evidencias/` mostra dois padrões: erro de escala, com o
maior contrato do ano tendo valor global mil vezes o da parcela, e
credenciamentos de serviços de saúde com valores redondos e repetidos, em que o
campo parece guardar um teto estimado e não o preço contratado.

A medida que mostra isso de forma mais direta é a razão entre média e mediana.
Sem corte, a mediana de R$ 3.486,00 convive com uma média de R$ 9.101.366,39,
**2.611 vezes maior**. Com o corte de R$ 1 bilhão, a média cai para
R$ 384.638,09 e a mediana praticamente não se move, indo a R$ 3.484,00. Uma
mediana estável sob um corte que derruba a média em 23 vezes é a assinatura de
um punhado de outliers, não de uma cauda longa.

Consequência prática: **qualquer agregação por valor feita sem corte descreve
os erros de digitação, não as contratações.** O corte de R$ 1 bilhão é uma
escolha declarada, não uma verdade; por isso o pipeline grava também
`acima_sensibilidade`, em R$ 100 milhões, já que os 1.189 contratos entre
R$ 100 milhões e R$ 1 bilhão somam 42% do que sobra depois do corte e podem ter
o mesmo tipo de erro.

### 2. Contratação pública brasileira, no volume, é municipal

Os 2.023.134 contratos vêm de 11.813 órgãos, em 27 unidades da federação e
4.196 municípios, e **69,89% deles são da esfera municipal**. Isso reposiciona
o tema: a imagem de compra pública como fenômeno federal não sobrevive à
contagem. Também explica por que o recorte inicial dos cinquenta maiores órgãos
por valor foi abandonado — além de exigir cobertura nacional para comparar
estados, aquele critério selecionava justamente os órgãos que digitaram valores
errados.

### 3. Controle feminino em 30,4% das empresas com controle definido

Das 239.600 empresas do recorte, 174.599 têm sócio na base e 131.423 têm
controle definido como feminino ou masculino. Entre essas, **39.904 são de
controle feminino, 30,4%**, contra 91.519 de controle masculino.

Três ressalvas que precisam acompanhar o número sempre:

- **Conta empresas, não valor.** O cruzamento com o valor contratado é o que o
  KPI 1 pede de verdade e ainda não foi feito. Nenhum texto deve apresentar os
  30,4% como participação feminina no valor contratado.
- O denominador é 131.423, não 239.600. Apresentar 39.904 sobre o total daria
  16,7% e seria outra pergunta.
- A classificação inclui empresas que só aparecem em contratos de receita.

No nível do sócio, e não da empresa, a composição dos 327.180 sócios pessoa
física elegíveis é de **34,3% feminino, 61,8% masculino e 4,0% indeterminado**.

### 4. Um quarto das empresas não tem controle inferível

**65.001 empresas, 27,1% do recorte, não têm nenhuma linha de sócio na base**, e
62.880 delas são empresários individuais — que, por definição, não têm quadro
societário e não aparecem no arquivo de sócios. As outras 2.121 incluem
municípios, autarquias, sindicatos e consórcios públicos.

Esse grupo é declarado à parte em vez de ser forçado para dentro de uma classe.
Inferir o gênero do titular pela razão social exigiria tratar nome de pessoa
física a partir de outro campo, o que pesa na LGPD, e ficou como extensão
opcional. A decisão está registrada como D5.

### 5. 3,9% dos contratos não admitem análise societária nenhuma

**78.795 contratos da fato, 3,9% do total, somando R$ 16,9 bilhões, não têm raiz
de CNPJ** — são de pessoa física, de fornecedor estrangeiro ou de pessoa
jurídica com identificador irregular. Não há quadro societário a cruzar, e eles
ficam com fornecedor nulo na tabela de fatos.

O número importa porque é o tamanho do universo que todo resultado de gênero
deixa de fora. Um resultado de diversidade societária vale para os contratos
com raiz de CNPJ, e publicá-lo sem esse tamanho ao lado seria omissão.

### 6. O território das empresas é majoritariamente negro, e isso não diz nada sobre os sócios

A composição racial dos 5.570 municípios do Censo 2022 vai de **2,5% a 97,2% de
população preta ou parda, com mediana de 60,8%**. O indicador descreve o
contexto da empresa e entra nas visões como faixa, nunca como atributo de
pessoa. O eixo setorial, pela RAIS, não foi integrado: os microdados públicos
são desidentificados e não trazem o CNPJ do empregador, o que obriga o
cruzamento a ser por CNAE e município, nunca empresa a empresa.

### 7. O campo oficial de contrato de receita erra nos dois sentidos

Contratos de receita — em que o dinheiro vai do fornecedor para o órgão — são
20.439 no ano, 1,02% dos contratos e R$ 12,2 bilhões, 1,6% do valor. A regra os
marca e os retira dos indicadores, porque somá-los aos de despesa mistura dois
fenômenos opostos.

Mas a marca não é confiável sozinha, e isso é um achado sobre a fonte. Nos 20
dias de janeiro conferidos, de 493 contratos marcados como receita, **256 têm
objeto que descreve apenas compra, serviço ou obra**: aquisição de caminhões,
material laboratorial, jardinagem, pavimentação. Pelo valor o quadro se
inverte, porque os contratos de receita verdadeiros são maiores — o maior
marcado é a venda de cotas de um fundo imobiliário estadual, de R$ 470 milhões.
E há alienação de imóvel sem a marca. A categoria do processo não resolve: essa
venda de cotas está classificada como serviço. Por isso todo indicador de valor
é publicado também com os marcados incluídos, como sensibilidade.

### 8. A escolha de infraestrutura foi determinada pela pergunta analítica

O limite de 1 GB do plano gratuito admitia três saídas: filtros, agregações ou
amostragem estatística. A amostragem foi descartada, e o motivo é analítico. A
RN-07 mede concentração societária, que depende de enxergar todos os contratos
de cada sócio dentro do recorte; uma amostra aleatória transformaria um sócio
com oito empresas num sócio com duas e faria a métrica **subestimar
sistematicamente o próprio fenômeno que se quer medir**. Recortar reduz o
universo preservando a rede íntegra dentro dele; amostrar reduz fragmentando a
rede. Para uma análise puramente de agregados de valor, a amostragem seria
adequada.

## Limitações restantes, nomeadas

Além das quatro do início:

1. **Sem campo de situação na coleta.** Nenhum dos 41 campos de topo do
   contrato indica anulação ou cancelamento (D6). Os indicadores podem incluir
   contratos cancelados depois de publicados. A exclusão depende de outra fonte.
2. **Diretor, presidente e conselheiro contam como controle.** Decisão D4, com
   peso medido: 25.375 das 327.180 linhas de sócio pessoa física, 7,8%. A
   rodada de sensibilidade sem os três não foi feita.
3. **O código da classificação não usa a lista de qualificações da RN-03.** O
   `classificar_empresas.py`, que produziu os números publicados, filtra por
   palavra na descrição em vez de pela lista de códigos. A diferença tem teto de
   1.608 linhas, 0,49% dos sócios elegíveis, e o efeito real sobre a
   classificação não foi medido. Os dois critérios existem lado a lado em
   `etl/regras/qualificacoes.py` para que a diferença continue mensurável.
4. **A visão materializada do KPI não aplica a RN-05 inteira.** A
   `mv_kpi_genero_setor` não olha o sócio pessoa jurídica e põe as empresas sem
   sócio na base junto com as mistas. Os números publicados vêm do script, não
   da visão.
5. **Eixo temporal.** A coleta é por data de publicação (D7). No ano a
   diferença para a data de assinatura é pequena — 92,69% dos contratos
   publicados têm ano de contrato 2025 —, mas cada análise deve declarar qual
   eixo usa.
6. **Uma única competência societária.** Ver a quarta limitação do início.
   Toda apresentação de resultado societário deve declarar a competência.

## O que um avaliador deveria poder cobrar e hoje não está pronto

- O KPI 1 cruzado com valor contratado, e não só com contagem de empresas.
- A sensibilidade do limiar de gênero nos sócios, com o Censo 2022.
- A concentração da RN-07 rodada sobre a Receita filtrada.
- A marcação de sanção, que depende do CEIS e do CNEP.
- A composição do campo `receita` conferida contra o objeto no ano inteiro.

Essas cinco pendências estão rastreadas em `docs/rastreabilidade-regras.md`,
com responsável e dependência.
