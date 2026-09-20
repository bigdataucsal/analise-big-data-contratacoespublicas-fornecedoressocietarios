# Os 5 V's aplicados ao dataset

Trilha 3. Todos os números deste documento foram medidos contra os dados do
projeto, não estimados. A base de medição é a coleta do PNCP de 1 a 20 de
janeiro de 2025, com 58.769 contratos, mais a consulta de totais da própria
API para o ano inteiro. Onde um número vier de projeção e não de medição
direta, isso está dito.

## Volume

O universo do recorte é de 2.023.236 contratos publicados no PNCP durante o
ano de 2025, número obtido do campo `totalRegistros` da própria API. Em JSON
bruto, isso corresponde a aproximadamente 3,5 GB, projetados a partir dos
104,9 MB que os 58.769 contratos já coletados ocupam.

A segunda fonte é maior por duas ordens de grandeza. Os Dados Abertos do CNPJ
da Receita Federal, que trazem o quadro societário, passam de 80 GB
compactados no conjunto completo, distribuídos entre os arquivos de empresas,
estabelecimentos, sócios, Simples Nacional e as tabelas de domínio.

O destino é um PostgreSQL no plano gratuito da Aiven, com 1 GB. Vale registrar
que esse 1 GB é o disco de dados do serviço inteiro, e não a soma do tamanho
das tabelas: contam também os índices, o write ahead log, os arquivos
temporários gerados por consultas que não cabem na memória e o espaço deixado
por registros atualizados antes da limpeza automática. Apenas os backups ficam
fora, porque residem no armazenamento de objetos da região. Na prática o
orçamento utilizável fica entre 500 e 700 MB.

O V de Volume, neste projeto, é portanto a distância entre 80 GB de origem e
700 MB de destino, e a estratégia de redução é o que o resolve. Medimos três
degraus de redução, aplicados em sequência.

O primeiro é a conversão para formato colunar comprimido. Os mesmos 18.500
contratos de uma medição anterior ocupam 33,6 MB em JSONL, 11,8 MB em CSV e
2,1 MB em Parquet com compressão ZSTD, uma redução de dezesseis vezes em
relação ao bruto.

O segundo é a retirada do texto livre do banco relacional. O campo
`objetoContrato` custaria cerca de 313 MB de dados mais algo entre 400 e 465 MB
de índice de busca textual, somando mais do que todo o orçamento utilizável em
uma única coluna. Ele permanece na camada Parquet.

O terceiro é o recorte. Aplicando o critério de valor e mantendo os 50 órgãos
com maior valor contratado, ficamos com 11,0% dos contratos representando
71,0% do valor, o que reduz a tabela de fatos para a ordem de 135 MB e libera
espaço para as dimensões vindas da Receita Federal.

Para o lado da Receita, a redução vem de inverter a ordem do processamento.
Como a base é publicada em arquivos compactados monolíticos, sem possibilidade
de filtro no servidor, primeiro extraímos a lista de CNPJs que efetivamente
aparecem em contratos dentro do recorte e só então filtramos os arquivos
durante a leitura. No recorte atual essa lista tem 3.478 raízes de CNPJ
distintas, contra os cerca de 60 milhões de estabelecimentos da base completa.

## Velocidade

O dado é atualizado continuamente na origem. O PNCP publica contratações à
medida que os órgãos as registram, e o campo `dataAtualizacaoGlobal` permite
identificar revisões de contratos já publicados, o que caracteriza ingestão
incremental e não carga única.

Medimos que a taxa de publicação no recorte é de aproximadamente 5.500
contratos por dia, o que corresponde a algo em torno de 2 milhões por ano.

Do lado da ingestão, o fator limitante não é o nosso processamento e sim o
limite de requisições da API pública. Medimos esse limite de forma controlada,
com ritmo sustentado e dezoito requisições por degrau. Cerca de 20 requisições
por minuto passaram sem nenhuma resposta 429. Com 40 requisições por minuto,
treze das dezoito falharam; com 62, dez; e com 79 usando uma única linha de
execução, treze. O limite portanto é de requisições por unidade de tempo e não
de concorrência, e fica entre 20 e 40 por minuto.

Esse detalhe importa para o V de Velocidade porque ele define o desenho do
extrator. Como a API pagina por deslocamento e o custo cresce com o número da
página, varrendo o ano inteiro de uma vez a página 4000 leva 52 segundos contra
12 segundos da página 1. Quebrando o período em janelas de um dia, toda
requisição volta a ser rasa e o custo por página deixa de crescer. O ganho
medido foi de aproximadamente 7 registros por segundo na varredura sequencial
profunda para cerca de 150 por segundo com a janela diária dentro do limite de
taxa.

Um resultado contraintuitivo que vale registrar: reduzir o tamanho da página
piora o desempenho. Uma página de 500 registros leva 1,6 segundo e rende 312
registros por segundo, enquanto uma de 100 leva 0,85 segundo e rende 118. Como
o limite é de requisições e não de bytes, páginas menores gastam cinco vezes
mais requisições para os mesmos dados e atingem o limite cinco vezes mais
rápido. Numa execução real com redução progressiva de página ligada, a vazão
caiu para 2 registros por segundo.

A atualização periódica será feita por execução agendada no GitHub Actions,
ingerindo apenas o período novo. Como o extrator registra os dias já
concluídos, uma execução interrompida retoma de onde parou sem reprocessar o
que já foi baixado.

## Variedade

O projeto reúne as três variedades sem forçar nenhuma delas.

O dado estruturado são os arquivos CSV da Receita Federal, com esquema fixo,
sem linha de cabeçalho, separados por ponto e vírgula e em codificação latina.
São eles que trazem empresas, estabelecimentos e o quadro societário.

O dado semiestruturado são as respostas JSON das APIs do PNCP, do Portal da
Transparência e do IBGE. No caso do PNCP, a estrutura é aninhada: os campos
`orgaoEntidade`, `unidadeOrgao`, `tipoContrato` e `categoriaProcesso` são
objetos, e os dois últimos seguem o padrão de código mais descrição, o que os
torna candidatos naturais a tabelas de dimensão. Há ainda campos que existem
em alguns registros e não em outros, como `orgaoSubRogado` e
`unidadeSubRogada`, presentes em menos de 1% dos contratos.

O dado não estruturado é o campo `objetoContrato`, texto livre em português,
sem padronização, com média de 149 caracteres e máximo de 5.120 na base
medida. É o candidato à busca textual e à análise de termos frequentes.

A variedade também aparece na dispersão institucional dos dados. Os 58.769
contratos medidos vêm de 3.495 órgãos distintos, distribuídos por 27 unidades
federativas e 2.080 municípios. A composição por esfera é de 56,31% municipal,
28,97% federal, 13,15% estadual, 1,47% nacional e 0,11% distrital, o que
significa que a análise não é federal e sim predominantemente municipal, com
todas as implicações de heterogeneidade de preenchimento que isso traz.

A essas três variedades soma se uma quarta fonte, de natureza diferente: os
dados agregados do Censo, que não descrevem contratos nem empresas e sim
territórios. A composição de cor ou raça dos 5.570 municípios brasileiros já
está baixada, e o percentual de população negra varia de 2,5% a 97,2% entre
municípios, com mediana de 60,8%. É por essa via que o projeto endereça a ODS
18 sem ferir a LGPD, atribuindo o indicador ao contexto e nunca à pessoa.

## Veracidade

Este é o V onde mais encontramos material, e o que mais influenciou as regras
de negócio do projeto.

O achado principal é a presença de valores implausíveis. A mediana do valor
global de um contrato é de R$ 4.153,50 e a média é de R$ 45.013.038,24, ou seja,
a média é 10.837 vezes a mediana. A origem dessa distorção são 26 contratos,
0,04% da base, que concentram 98,7% do valor somado. Os quatro maiores são de
R$ 640 bilhões, R$ 640 bilhões, R$ 562,5 bilhões e R$ 250 bilhões, todos do
mesmo órgão. Não são contratos: são erros de digitação na origem, muito
provavelmente valores registrados sem o separador decimal. O somatório de vinte
dias de contratações chegava a R$ 2,6 trilhões, aproximadamente metade do
orçamento federal anual, e cai para R$ 33,3 bilhões quando se aplica um corte
de sanidade em R$ 1 bilhão.

Isso não é apenas uma curiosidade estatística. O critério de recorte que
adotamos é o dos maiores órgãos por valor contratado, e com os valores
distorcidos dentro da base esse critério passa a selecionar os órgãos que
digitaram errado em vez dos que efetivamente contratam mais. O mesmo recorte de
50 órgãos representa 99,6% do valor antes do corte de sanidade e 71,0% depois.
O primeiro número parece melhor e não significa nada.

Outros problemas medidos, em ordem de frequência:

Em 62,65% dos contratos publicados no período, o campo `anoContrato` é 2024, e
não 2025. Como a consulta da API é por data de publicação, a coleta do ano de
2025 captura majoritariamente contratos assinados no ano anterior. Isso não é
erro do dado, é característica da fonte, mas obriga a decidir explicitamente se
a análise se dá por data de publicação ou por data de assinatura, e a declarar
essa escolha.

Em 55,99% dos registros o campo `valorAcumulado` é nulo, o que inviabiliza usá
lo como métrica principal.

Em 2,42% dos casos o identificador do fornecedor tem 11 dígitos, ou seja, é um
CPF e não um CNPJ, e portanto esses fornecedores não possuem quadro societário
a ser cruzado. Outros 0,16% têm identificadores irregulares, com 7, 9, 3 ou
nenhum dígito.

Em 2,09% dos contratos o valor inicial difere do valor global, sinalizando
aditivos já incorporados.

Em 1,69% dos casos o objeto do contrato tem menos de quinze caracteres, sendo
pouco informativo para análise textual.

Em 0,78% dos registros a data de assinatura é anterior a 2024, chegando a 2021.

Em 0,70% dos contratos o valor global é zero ou negativo.

Em 0,16% a data de assinatura é posterior à data de publicação, o que é uma
inconsistência temporal.

Em 0,02% o nome do fornecedor está vazio.

Há ainda um problema de duplicação que não vem da fonte e sim do processo de
coleta. A primeira versão do extrator, ao retomar uma coleta interrompida,
regravou páginas já baixadas: 18.900 linhas para 18.500 chaves únicas, ou seja,
400 duplicatas. O extrator atual, que só marca um dia como concluído após
gravar e sincronizar os dados em disco, produziu 58.769 linhas para 58.769
chaves únicas, sem nenhuma duplicata. A deduplicação pela chave natural
`numeroControlePNCP` permanece no tratamento como garantia.

## Valor

O valor analítico do conjunto está em responder uma pergunta que nenhuma das
bases responde sozinha: quem são as pessoas por trás dos CNPJs que recebem
recurso público, e se há assimetria de gênero e de cor ou raça nesse controle.

A cadeia que sustenta essa pergunta tem cinco elos. O órgão público contrata, o
contrato registra valor e objeto, o CNPJ identifica o fornecedor, o quadro
societário revela os sócios, e só então se chega à pessoa. Os quatro primeiros
elos existem em bases públicas e são unidos por junções bem definidas. O quinto
não existe em base nenhuma e precisa ser inferido, com regra explícita e margem
de erro declarada.

É esse quinto elo que diferencia o tema. As três perguntas analíticas que
orientam o recorte são a assimetria de gênero na captura de recurso público, a
camada interseccional entre gênero do controle societário e composição de cor
ou raça obtida por proxy setorial e territorial, e a concentração societária,
ou seja, quantos sócios controlam que parcela do valor contratado e quais
aparecem em múltiplas empresas fornecedoras.

O quinto elo já tem uma primeira medição. O piloto de inferência de gênero,
rodado sobre mil nomes de fornecedores pessoa física do PNCP, classificou 45,3%
como feminino, 49,0% como masculino e deixou 5,7% como indeterminado. Essa taxa
de indeterminados é o que torna a inferência auditável: ela não é falha do
método, é a medida explícita do que o método não consegue decidir. Dos 5,7%,
quatro pontos são nomes que o IBGE suprime por terem menos de vinte ocorrências
no país, e um ponto e meio são nomes genuinamente ambíguos. O número definitivo
sai quando o piloto rodar sobre os sócios da Receita Federal, que é a população
à qual a regra se aplica de fato.

Vale notar que a terceira pergunta é a que mais restringe o desenho técnico,
porque análise de rede exige ver todos os contratos de cada sócio dentro do
recorte. É por isso que reduzimos o universo por recorte de órgão e não por
amostragem aleatória: recortar preserva a rede íntegra dentro do universo
escolhido, enquanto amostrar a fragmenta e faz a métrica de concentração
subestimar sistematicamente o fenômeno que se quer medir.

## Nota sobre reprodutibilidade

Os números de Volume, Velocidade e Veracidade deste documento podem ser
reproduzidos com os scripts do diretório `etl`. O perfil de qualidade que
sustenta a seção de Veracidade sai de consultas diretas sobre o arquivo bruto,
e o recorte com o corte de sanidade sai de `recorte_cnpjs.py`. A base de
medição foi a coleta de 1 a 20 de janeiro de 2025; quando a coleta do ano
completo terminar, os percentuais devem ser recalculados antes da entrega
final, porque nada garante que a distribuição de janeiro se repita ao longo do
ano.
