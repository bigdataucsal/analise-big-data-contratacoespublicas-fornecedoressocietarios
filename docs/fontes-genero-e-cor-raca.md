# Fontes para gênero e para cor ou raça

Entrega da Trilha 3, semana 1. Localiza as duas fontes que sustentam o quinto
elo da cadeia analítica, aquele que não existe pronto em base nenhuma, e
registra o que cada uma entrega, o que ela não entrega e como citá la.

As duas já estão implementadas e testadas contra as APIs reais, não apenas
localizadas.

## Gênero: API de nomes do IBGE

### A fonte

A base é o Censo Demográfico de 2010, exposta pela API de nomes do IBGE em
`servicodados.ibge.gov.br/api/v2/censos/nomes/{nome}`. Não exige chave nem
autenticação.

A consulta aceita o parâmetro `sexo` com valores M ou F, e devolve a série de
frequências do nome por década de nascimento. Somando as frequências de cada
série chega se ao total por sexo.

Um detalhe importante: sem o parâmetro `sexo`, a API devolve apenas o total
agregado, com o campo sexo em nulo. Não existe uma chamada única que traga a
quebra por sexo, então são duas requisições por nome.

### A regra de classificação

Para cada nome, tomamos o primeiro nome, normalizamos para maiúsculas sem
acento, somamos as frequências de cada sexo e calculamos a proporção
dominante. Classificamos como feminino ou masculino quando essa proporção
alcança 90%, e como indeterminado caso contrário.

O denominador é sempre a soma de masculino mais feminino, nunca o total da
chamada sem o parâmetro sexo. A razão é que a supressão de valores pequenos do
IBGE é aplicada célula a célula, por nome, sexo, década e localidade, então o
total agregado é maior que a soma dos sexos. Medimos essa diferença no nome
ALEX: a soma por sexo dá 311.517 e o total agregado dá 311.536, dezenove
ocorrências suprimidas. Usar o total agregado subestimaria a proporção.

Três exemplos que ilustram a regra, medidos em 20 de setembro de 2026:

| nome | feminino | masculino | proporção | classificação |
|---|---|---|---|---|
| MARIA | 11.694.738 | 39.391 | 99,7% F | feminino |
| JOSE | 22.021 | 5.732.508 | 99,6% M | masculino |
| ARIEL | 2.715 | 27.111 | 90,9% M | no limite do corte |

### Os limites, que precisam estar declarados

O IBGE só publica nomes com pelo menos vinte ocorrências no Brasil, quinze na
unidade federativa e dez no município. Abaixo disso o nome simplesmente não
aparece, e a resposta vem como lista vazia, indistinguível de nome inexistente.
Nomes raros e estrangeiros caem em indeterminado por esse motivo.

Nomes compostos não funcionam. A consulta por MARIA JOSE devolve lista vazia,
porque a base é de primeiro nome isolado. Por isso o pipeline separa o nome no
primeiro token e consulta apenas ele.

A base foi gravada sem sinais gráficos, e há um filtro de aplicação na frente
da API que rejeita a URL com caractere acentuado, respondendo HTML em vez de
JSON. A normalização precisa acontecer antes de montar a URL, e o código trata
resposta não JSON como erro explícito em vez de silenciosamente contar como
nome ausente.

Variantes ortográficas contam como nomes diferentes, porque o IBGE registra
como foi declarado. ANA e ANNA, LUIS e LUIZ são entradas distintas.

O sexo é o autodeclarado no recenseamento de 2010, e é uma fotografia daquele
momento. Nomes cujo uso mudou depois não estão refletidos.

Por fim, a API não permite enumerar todos os nomes: o endpoint de ranking
devolve no máximo os vinte primeiros por década. É preciso ter a própria lista
de nomes para consultar.

### O resultado do piloto

Rodamos o piloto sobre mil nomes de fornecedores pessoa física do PNCP, que são
563 primeiros nomes distintos. O resultado foi 45,3% classificados como
feminino, 49,0% como masculino e 5,7% como indeterminado.

Dos indeterminados, 4,1% do total são nomes ausentes da base, ou seja,
suprimidos por terem menos de vinte ocorrências no país, e 1,6% são nomes
genuinamente ambíguos, que aparecem na base com boa frequência mas cuja
proporção dominante não alcança os 90%.

A sensibilidade ao limiar foi medida e vale registrar, porque mostra que a
escolha dos 90% não é arbitrária nem frágil:

| limiar | indeterminados |
|---|---|
| 80% | 4,8% |
| 90% | 5,7% |
| 95% | 6,6% |
| 99% | 10,0% |

Uma observação metodológica sobre esse piloto. A RN-04 se aplica a sócios, que
vêm da Receita Federal, e o download dessa base ainda não terminou. O piloto
rodou sobre fornecedores pessoa física do PNCP, que são nomes de pessoas reais
do mesmo universo, a contratação pública brasileira. A taxa de 5,7% é portanto
uma estimativa de ordem de grandeza, não o número final. Ele será recalculado
sobre os sócios de verdade assim que a Trilha 2 entregar o arquivo, e é o
número recalculado que deve ir ao relatório final.

Testamos também uma regra adicional, descartando nomes com frequência total
abaixo de vinte por instabilidade estatística, e ela não mudou nada: zero
casos. O motivo é que a própria supressão do IBGE já opera nesse mesmo corte,
então nomes abaixo dele não chegam a aparecer. A regra fica no código como
proteção, mas é redundante na prática.

### Para rodar em escala

Consultar nome a nome serve ao piloto, não a centenas de milhares de sócios.
Existe base consolidada derivada exatamente dessa API, publicada pela Brasil.IO
no conjunto Gênero dos Nomes, com cerca de cem mil nomes e a proporção
dominante já calculada na coluna `ratio`, além de agrupamento de variantes
ortográficas que a API conta separadamente.

A licença é Creative Commons Attribution ShareAlike 4.0, que é share alike:
redistribuindo a base ou uma derivada, é preciso manter a mesma licença. A
atribuição exigida é literal e deve aparecer assim: Fonte IBGE/Censo 2010,
dados tratados por Álvaro Justen/Brasil.IO.

Cabe uma ressalva. Essa base é uma captura de 2018 feita sobre uma lista de
nomes que eles já possuíam, e não um índice completo, que não existe. Haverá
nome do nosso recorte que não está lá. A estratégia correta é casar contra o
CSV primeiro e mandar apenas os nomes não encontrados para a API, deduplicados
e com cache.

## Cor ou raça: agregado 9605 do SIDRA

### A fonte

O agregado é o de número 9605, intitulado População residente, por cor ou raça,
nos Censos Demográficos, acessado pela API de agregados do IBGE.

Ele foi escolhido em vez de outras tabelas de cor e raça porque traz 2010 e
2022 na mesma tabela, já harmonizados nas mesmas cinco categorias, o que
permite comparar censos sem trabalho de compatibilização.

A variável é a de número 93, população residente em pessoas. A classificação é
a de número 86, com as categorias 2776 branca, 2777 preta, 2778 amarela, 2779
parda, 2780 indígena e 95251 total. O nível geográfico N6 é o de município, e a
API aceita pedir todos os 5.570 de uma vez.

A chamada completa que usamos, testada e funcionando, é:

```
https://servicodados.ibge.gov.br/api/v3/agregados/9605/periodos/2022/variaveis/93?localidades=N6[all]&classificacao=86[2776,2777,2778,2779,2780]
```

O script `etl/baixar_proxy_racial.py` implementa isso e traz os 5.570
municípios em cerca de dois segundos.

### Cruzamento com sexo

O agregado 9605 não permite cruzar cor ou raça com sexo, porque sua única
classificação é a 86. Para isso existe o agregado 9606, que acrescenta a
classificação 2 de sexo, com 4 para homens e 5 para mulheres, e a 287 de idade.

Há uma armadilha ao usá lo: se a classificação de idade não for fixada no
total, a API devolve as 134 faixas etárias para cada município e o payload
explode. É preciso sempre fixar 287 no código 100362. O script já faz isso na
opção que ativa o recorte por sexo.

### Armadilhas do dado

Os valores vêm como texto, não como número, e o IBGE usa notação própria. O
traço significa zero e aparece 1.320 vezes no Censo 2022, tipicamente nas
categorias amarela e indígena de municípios pequenos. As reticências significam
dado não disponível e aparecem no Censo 2010. Uma conversão direta para inteiro
quebra a carga, e o script trata os dois casos explicitamente.

Há ainda a questão do código de município. O SIDRA usa o código do IBGE, que é
o mesmo que o PNCP fornece, mas a base da Receita Federal usa uma codificação
própria. Ligar a empresa ao perfil racial do seu território exige passar pela
tabela de tradução distribuída no próprio conjunto da Receita, e esse é um
ponto que a Trilha 2 precisa considerar no parser.

### O que foi baixado

A tabela tem 5.570 municípios com as cinco categorias, o total e o percentual
de população negra, que é a soma de preta e parda. Esse agrupamento é o que o
próprio IBGE usa nas análises de desigualdade racial, e é a variável que o
indicador interseccional do projeto vai consumir.

A distribuição do percentual de população negra entre municípios vai de 2,5% no
mínimo a 97,2% no máximo, com mediana de 60,8%. São Paulo aparece com 43,5% e
Salvador com 83,2%, o que dá uma noção da dispersão que o indicador captura.

### O que este dado é, e o que ele não é

Ele descreve o território, nunca a pessoa. O indicador permite afirmar que
determinado recurso público foi para empresas sediadas em municípios com certa
composição racial. Não permite afirmar nada sobre a cor ou raça de um sócio.

Essa distinção é o que mantém o projeto dentro da LGPD. Cor e raça são dado
sensível pelo artigo 5 da lei, e inferir no nível individual por cruzamento de
nome com bases que trazem raça autodeclarada seria reidentificação de dado
sensível. O caminho foi avaliado e rejeitado, e documentar essa rejeição é
parte do parecer de conformidade.

Metodologicamente, trata se de inferência ecológica, cuja limitação é
conhecida e precisa ser nomeada: a composição do grupo não se transfere para o
indivíduo. Um município com 80% de população negra não autoriza afirmar que os
sócios das empresas de lá sejam negros.

## Proxy setorial

A terceira fonte prevista, para compor o proxy setorial por CNAE a partir da
RAIS ou do Novo CAGED, ainda está em levantamento e será acrescentada a este
documento. O ponto metodológico já conhecido é que os microdados públicos
dessas bases são anonimizados e não trazem o CNPJ do empregador, o que obriga o
cruzamento a ser por CNAE e município e nunca empresa a empresa. Essa é a
resposta correta caso a banca pergunte por que não ligamos diretamente.

## Como citar

Para a inferência de gênero, a fonte primária é o IBGE, Censo Demográfico 2010,
consultado pela API de nomes versão 2. Se a base consolidada da Brasil.IO for
utilizada, a atribuição literal exigida é Fonte IBGE/Censo 2010, dados tratados
por Álvaro Justen/Brasil.IO, e a licença share alike precisa ser mantida.

Para a composição de cor ou raça, a fonte é o IBGE, Censo Demográfico 2022,
tabela 9605 do SIDRA, consultada pela API de agregados versão 3.
