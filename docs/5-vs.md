# Os 5 V's aplicados ao dataset

Trilha 3. Referência: 30/09/2026, revisado em 02/10/2026. Os números deste documento foram medidos
contra os dados do projeto, não estimados. A base de medição é a coleta
completa do PNCP para 2025: 2.023.134 contratos publicados de 1º de janeiro a
31 de dezembro, com cobertura conferida contra o `totalRegistros` da própria
API, dia a dia, sem nenhuma diferença. Onde um número ainda vem da primeira
amostra (coleta de 1 a 20 de janeiro de 2025, com 58.769 contratos), o texto
diz, e o item está marcado com `[AMOSTRA JAN]`. Onde o número depende de uma
medição que ainda não foi feita, está marcado `[PENDENTE]`. Onde um número vier
de projeção e não de medição direta, isso está dito.

## Volume

O universo do recorte é de 2.023.134 contratos publicados no PNCP durante o
ano de 2025, com cobertura nacional e sem filtro de órgão. O número vem do
arquivo coletado (2.023.134 linhas, 2.023.134 chaves `numeroControlePncp`
distintas, nenhuma duplicata) e confere com o campo `totalRegistros` da própria
API nos 365 dias do ano, conferência feita em 30/09/2026. Uma consulta anterior
de totais tinha indicado 2.023.236; a diferença de 102 contratos (0,005%) não
foi investigada e não altera nenhuma conclusão. Em JSON bruto, o arquivo
coletado ocupa 3,62 GB (3,37 GiB); a projeção feita na amostra de janeiro, a
partir dos 104,9 MB dos 58.769 contratos, era de aproximadamente 3,5 GB e
ficou cerca de 3% abaixo do medido. Depois do tratamento, os mesmos contratos
ocupam 254,1 MB em 12 arquivos Parquet, com 50 colunas e o texto do objeto
incluído.

A segunda fonte é maior. Os Dados Abertos do CNPJ da Receita Federal, que
trazem o quadro societário, somam 7,76 GB compactados e 28,67 GB
descompactados na competência usada (2026-09-14), medidos no disco: 17,12 GB de
estabelecimentos, 5,48 GB de empresas, 3,17 GB do Simples Nacional e 2,90 GB de
sócios, mais as tabelas de domínio, que são desprezíveis. O guia do projeto
falava em mais de 80 GB compactados; esse número não se confirmou na
competência usada, e este documento usa o medido. Descompactada, a Receita tem
cerca de oito vezes o volume do JSON de contratos (28,67 GB contra 3,62 GB).

O destino é um PostgreSQL no plano gratuito da Aiven, com 1 GB. Vale registrar
que esse 1 GB é o disco de dados do serviço inteiro, e não a soma do tamanho
das tabelas: contam também os índices, o write ahead log, os arquivos
temporários gerados por consultas que não cabem na memória e o espaço deixado
por registros atualizados antes da limpeza automática. Apenas os backups ficam
fora, porque residem no armazenamento de objetos da região. Na prática o
orçamento utilizável fica entre 500 e 700 MB.

O V de Volume, neste projeto, é portanto a distância entre 28,67 GB
descompactados de origem (7,76 GB compactados) e 700 MB de destino, e a
estratégia de redução é o que o resolve. Planejamos três degraus de redução,
aplicados em sequência; os dois primeiros foram medidos e o terceiro mudou com
a cobertura nacional.

O primeiro é a conversão para formato colunar comprimido. Os mesmos 18.500
contratos de uma medição anterior ocupam 33,6 MB em JSONL, 11,8 MB em CSV e
2,1 MB em Parquet com compressão ZSTD, uma redução de dezesseis vezes em
relação ao bruto. Na coleta completa, os 2.023.134 contratos passam de 3,62 GB
em JSONL para 254,1 MB em Parquet, uma redução de cerca de catorze vezes.

O segundo é a retirada do texto livre do banco relacional. O campo
`objetoContrato` soma 334,6 MB de dados (comprimento médio de 160 caracteres,
medido nos 2.023.134 contratos), e um índice de busca textual custaria algo
entre 430 e 500 MB, projeção feita sobre a razão estimada na amostra de
janeiro. Somados, passam de todo o orçamento utilizável em uma única coluna.
Ele permanece na camada Parquet.

O terceiro degrau do plano inicial era o recorte por órgão: manter os 50 órgãos
de maior valor contratado, que na amostra de janeiro davam 11,0% dos contratos
e 71,0% do valor, e uma tabela de fatos de cerca de 135 MB. Esse degrau foi
abandonado. A cobertura nacional é exigência do KPI de comparação entre
estados, e a coleta completa cabe sem dificuldade na máquina de tratamento: os
2.023.134 contratos foram tratados e gravados em Parquet em 30,2 segundos. O
que substitui o recorte por órgão é o corte de sanidade sobre o valor (seção
Veracidade) e o filtro do lado da Receita. A consequência foi um risco que o
benchmark no PostgreSQL permitiu medir. Extrapolando linearmente a estimativa
de 135 MB, feita para 11% dos contratos, a tabela de fatos nacional passaria de
1 GB, acima do orçamento utilizável. A medição no PostgreSQL não é diretamente
comparável com essa extrapolação, que era de uma fato com mais colunas, mas
mostra que o número de linhas, sozinho, não estoura o disco: numa fato de 5
colunas, a carga completa (2.005.068 linhas) ocupou 177 MB sem índices, e a
estimativa com índices fica entre 213 e 223 MB, conforme o método (índices em
cerca de 20% dos dados, medido com 1 milhão de linhas, ou projeção linear dessa
rodada). A fato reduzida final terá mais colunas, e seu tamanho só será
conhecido na carga da Fase 2. O limite apareceu em outro ponto: a consulta de
agregação sobre a fato completa derrubou a conexão do nó gratuito (1 CPU, 1 GB
de RAM), por causa não confirmada, e com 1 milhão de linhas a mesma consulta já
levava 6,0 s no servidor, com índices (14,3 s sem índices). Por isso o banco
recebe só a fato reduzida e o painel consulta agregados materializados
(decisão D2), enquanto a coleta nacional permanece em Parquet.

Para o lado da Receita, a redução vem de inverter a ordem do processamento.
Como a base é publicada em arquivos compactados monolíticos, sem possibilidade
de filtro no servidor, primeiro extraímos a lista de CNPJs que efetivamente
aparecem em contratos dentro do recorte e só então filtramos os arquivos
durante a leitura. No recorte nacional essa lista tem 239.605 raízes de CNPJ
distintas, dos fornecedores pessoa jurídica dos contratos que passam no corte
de sanidade e têm valor positivo, e o filtro as aplica sobre os 28,67 GB
descompactados, lidos direto dos ZIPs, sem extrair nada para o disco. Das 222,2
milhões de linhas lidas (70.085.592 de empresas, 73.366.147 de
estabelecimentos, 50.396.768 do Simples e 28.341.092 de sócios), o filtro
manteve 1,31 milhão, 0,59%: 239.600 empresas (cinco das 239.605 raízes não
constam do cadastro), 529.225 estabelecimentos, 201.427 registros do Simples e
339.385 sócios. O tamanho em disco é 69,05 MB em Parquet (estabelecimentos 49,4
MB, sócios 10,4 MB, empresas 7,2 MB, Simples 1,9 MB e municípios 0,1 MB; as
demais tabelas de domínio são desprezíveis), cerca de 400 vezes menos que os
28,67 GB descompactados de origem. É o tamanho comprimido em Parquet, não o do
PostgreSQL, que será medido na carga. No recorte inicial, de 50 órgãos, eram
3.478 raízes e 3,89 MB.

## Velocidade

O dado é atualizado continuamente na origem. O PNCP publica contratações à
medida que os órgãos as registram, e o campo `dataAtualizacaoGlobal` permite
identificar revisões de contratos já publicados, o que caracteriza ingestão
incremental e não carga única.

Na coleta completa, a taxa média de publicação é de 5.543 contratos por dia
(2.023.134 em 365 dias). O dia mais cheio, 20/08/2025, teve 12.589 contratos, o
mais fraco teve 31, e o mês mais cheio, outubro, teve 201.717 contratos, contra
116.210 em janeiro. A
amostra de 1 a 20 de janeiro, com 2.938 contratos por dia, subestimava a média
anual em 47%, e por isso nenhum percentual de janeiro foi tratado como
representativo do ano.

Do lado da ingestão, o fator limitante não é o nosso processamento e sim o
limite de requisições da API pública. Medimos esse limite de forma controlada,
com ritmo sustentado e dezoito requisições por degrau `[AMOSTRA JAN]`. Cerca de
20 requisições por minuto passaram sem nenhuma resposta 429. Com 40 requisições
por minuto, treze das dezoito falharam; com 62, dez; e com 79 usando uma única
linha de execução, treze. O limite portanto é de requisições por unidade de
tempo e não de concorrência, e fica entre 20 e 40 por minuto.

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

A coleta completa confirmou o desenho com checkpoint por dia. O servidor
interrompeu a coleta em 28/02/2025 por falhas de conexão, e ela foi retomada
sem reprocessar os dias já concluídos. A última rodada, que fechou os dias
restantes, levou 1,4 minuto para 7.660 contratos, com dois dias em paralelo,
2,0 segundos entre requisições e páginas de 500, sem nenhuma resposta 429 ou
504. O arquivo final tem 2.023.134 linhas para 2.023.134 chaves distintas. As
demais etapas foram rápidas: a conferência dos 365 dias contra a API levou
cerca de 6 minutos, e o tratamento e a gravação em Parquet, 30,2 segundos. O
filtro da Receita sobre os 28,67 GB levou 1h24m50s (de 15:27 a 16:51 de
30/09/2026), a cerca de 5,6 MB descompactados por segundo e 44 mil linhas por
segundo; por arquivo, empresas levaram 13,5 minutos, estabelecimentos 36,4,
Simples 22,2 e sócios 11,7. O gargalo seguinte foi a API de nomes do IBGE (v3,
uma chamada por nome): 18.965 nomes em 107,7 minutos, cerca de 176 por minuto.

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
Transparência e do IBGE. Cada contrato do PNCP tem 41 campos de topo, e a
estrutura é aninhada: `orgaoEntidade`, `unidadeOrgao`, `tipoContrato` e
`categoriaProcesso` são objetos, e os dois últimos seguem o padrão de código
mais descrição, o que os torna candidatos naturais a tabelas de dimensão. Outros
dois, `orgaoSubRogado` e `unidadeSubRogada`, também são objetos, mas só vêm
preenchidos em 0,31% dos contratos do ano; nos demais a chave existe e vale
nulo. Nos 58.769 contratos de janeiro que conferimos localmente, todos os
registros trazem exatamente os mesmos 41 campos `[AMOSTRA JAN]`, e o exemplo do
ano em `docs/evidencias/exemplos_tipos.txt` também. Os nomes nem sempre batem
com o roteiro do projeto: o tipo do fornecedor vem no campo `tipoPessoa`, e não
em `tipoPessoaFornecedor`, que não existe no dado.

O dado não estruturado é o campo `objetoContrato`, texto livre em português,
sem padronização, com média de 160 caracteres e máximo de 5.120 nos 2.023.134
contratos. É o candidato à busca textual e à análise de termos frequentes.

A variedade também aparece na dispersão institucional dos dados. Os 2.023.134
contratos vêm de 11.813 órgãos distintos, distribuídos por 27 unidades
federativas e 4.196 municípios. A composição por esfera é de 69,89% municipal,
15,97% estadual, 12,63% federal, 1,40% nacional e 0,11% distrital, o que
significa que a análise não é federal e sim predominantemente municipal, com
todas as implicações de heterogeneidade de preenchimento que isso traz. A
amostra de janeiro, com 3.495 órgãos, 2.080 municípios e 56,31% de contratos
municipais, já apontava a direção, mas subestimava o peso municipal.

A essas três variedades soma se uma quarta fonte, de natureza diferente: os
dados agregados do Censo, que não descrevem contratos nem empresas e sim
territórios. A composição de cor ou raça dos 5.570 municípios brasileiros já
está baixada, e o percentual de população negra varia de 2,5% a 97,2% entre
municípios, com mediana de 60,8%. É por essa via que o projeto endereça a ODS
18 sem ferir a LGPD, atribuindo o indicador ao contexto e nunca à pessoa.

## Veracidade

Este é o V onde mais encontramos material, e o que mais influenciou as regras
de negócio do projeto.

O achado principal é a presença de valores implausíveis. O valor global somado
dos 2.023.134 contratos é de R$ 18,25 trilhões. Desse total, 95,77% estão em
243 contratos (0,012% da base) com valor acima de R$ 1 bilhão; sem eles, o
total é de R$ 771,2 bilhões. Na amostra de janeiro, a mediana do valor global
era de R$ 4.153,50 e a média de R$ 45.013.038,24, ou seja, a média era 10.837
vezes a mediana, e 26 contratos concentravam 98,7% do valor somado
`[AMOSTRA JAN]`. Esses dois números de janeiro foram calculados com os contratos
de valor zero; contando só valor maior que zero, como no ano, eram R$ 4.260,00 e
R$ 45.333.160,44 (conferido nesta revisão), e a comparação a seguir deve usar
esses. No ano inteiro, a mediana é de R$ 3.486,00 e a média de
R$ 9.101.366,39, cerca de 2.611 vezes a mediana. Depois do corte de sanidade, a
média cai para R$ 384.638,09 (110 vezes a mediana), enquanto a mediana quase
não se move (R$ 3.484,00): é a mediana, e não a média, que descreve o contrato
típico.

Os quatro maiores contratos do ano têm R$ 6,03 trilhões (Secretaria Municipal
de Cultura de São Paulo), R$ 1,96 trilhão (Comando do Exército, no Pará),
R$ 1,12 trilhão (Município de Tuntum, no Maranhão) e R$ 1,03 trilhão (Polícia
Penal do Espírito Santo). Não são contratos plausíveis, e a auditoria mostra
dois padrões. O primeiro é erro de escala ou de digitação: no maior contrato do
ano o valor global é 1.000 vezes o da parcela e, no quarto maior, 1.000.000 de
vezes. O segundo é concentração em poucas origens: 159 dos 243 contratos acima
de R$ 1 bilhão vêm do Comando do Exército (48 contratos, R$ 6,7 trilhões) e da
Base Administrativa do Quartel-General do Exército (3 contratos, R$ 410
bilhões), ambos no Pará, e do Consórcio Interfederativo Minas Gerais (108
contratos, R$ 802 bilhões). São credenciamentos de serviços de saúde com
valores redondos e repetidos, como R$ 640 bilhões em três contratos e R$ 90
bilhões em seis, e o valor parece ser um teto estimado do credenciamento, e não
o preço contratado. Essa segunda leitura é uma hipótese, a confirmar no CSV de
auditoria.

Isso não é apenas uma curiosidade estatística. No recorte inicial, o critério
era o dos maiores órgãos por valor contratado, e com os valores distorcidos
dentro da base esse critério passa a selecionar os órgãos que digitaram errado
em vez dos que efetivamente contratam mais. Na amostra de janeiro, o recorte de
50 órgãos representava 99,6% do valor antes do corte de sanidade e 71,0%
depois. O primeiro número parece melhor e não significa nada. Com a cobertura
nacional o recorte por órgão foi abandonado, mas a lição permanece: todo
indicador de valor do projeto parte do valor depois do corte de sanidade.

Os 243 contratos são marcados, não apagados. Continuam no dado bruto e no CSV
de auditoria, e só saem dos indicadores de valor. A escolha do corte de R$ 1
bilhão foi testada contra os vizinhos. Acima de R$ 100 milhões há 1.432
contratos, com 97,57% do valor bruto, e sobram R$ 444 bilhões. Acima de R$ 1
bilhão há 243, com 95,77%, e sobram R$ 771 bilhões. Acima de R$ 10 bilhões há
78, com 93,54%, e sobram R$ 1.178 bilhões. Os 1.189 contratos entre R$ 100
milhões e R$ 1 bilhão somam ainda R$ 327 bilhões, 42% do que sobra depois do
corte, e podem conter o mesmo tipo de erro; por isso a mediana e o índice de
concentração são as métricas mais sensíveis à escolha.

Outros problemas medidos, em ordem de frequência na amostra de janeiro,
comparados com o ano inteiro. A diferença entre as duas colunas é, por si só,
um achado: a amostra de janeiro não representava o ano.

| Indicador | Amostra de janeiro (58.769) | Ano inteiro (2.023.134) |
| --- | --- | --- |
| `anoContrato` igual a 2024 | 62,65% | 7,05% |
| `valorAcumulado` nulo | 55,99% | 38,68% |
| Identificador do fornecedor com 11 dígitos (CPF) | 2,42% | 3,76% |
| Identificador fora de 11 e 14 dígitos, ou ausente | 0,16% | 0,17% |
| Valor inicial diferente do valor global | 2,09% | 2,13% |
| Objeto com menos de 15 caracteres | 1,69% | 1,11% |
| Data de assinatura anterior a 2024 | 0,78% | 0,23% |
| Valor global zero | 0,70% | 0,88% (17.823 em centavos, igual em `medir_pendencias.py`, `perfil_veracidade.py` e `diagnostico_valores.py`; nenhum negativo ou nulo). No JSON bruto, que o `recorte_cnpjs.py` lê, são 17.578: a diferença de 245 são valores positivos menores que meio centavo, que o tratamento arredonda para zero (ver abaixo) |
| Assinatura posterior à publicação | 0,16% | 0,14% |
| Nome do fornecedor vazio | 0,02% | 0,01% |
| `receita` verdadeira (contrato de receita para o órgão) | 0,85% depois do corte (493 de 58.328), medido nesta revisão | 1,02% do recorte (20.439 de 2.005.068; R$ 12,2 bi). A marca erra nos dois sentidos; ver a RN-02 |

Sobre o `anoContrato`: como a consulta da API é por data de publicação, a coleta
de janeiro captura majoritariamente contratos assinados no ano anterior. Isso
não é erro do dado, é característica da fonte, mas obriga a decidir
explicitamente se a análise se dá por data de publicação ou por data de
assinatura, e a declarar essa escolha. O percentual de janeiro era efeito do
começo do ano: no ano inteiro, apenas 7,05% dos contratos publicados em 2025
têm `anoContrato` 2024 (92,69% têm 2025 e 0,25% têm outro valor ou nenhum), e o
efeito da escolha entre as duas datas é pequeno.

Sobre o valor zero, a conta dos dois números fecha assim. O tratamento lê
`valorGlobal` como número de ponto flutuante e grava o valor com duas casas
decimais, arredondando, de modo que todo valor positivo menor que meio centavo
vira R$ 0,00 no Parquet. O `recorte_cnpjs.py` lê o JSON bruto e só exclui quem
tem valor menor ou igual a zero, então deixa esses contratos passarem. Como o
Parquet não tem valor negativo nem nulo, o bruto também não tem nulo (17.578 +
243 + 2.005.313 = 2.023.134), e os dois lados têm os mesmos 243 contratos acima
de um bilhão, a diferença entre 17.823 e 17.578 só pode vir de valores entre
zero e meio centavo: são 245. É o mesmo efeito que separa os 2.005.313 contratos
do recorte dos 2.005.068 da fato do benchmark. A conta é dedução, feita com os
números publicados e a leitura do código; a contagem direta no JSON bruto do ano
não foi refeita nesta revisão, porque a coleta completa está na máquina da T2.
O mecanismo foi reproduzido nos 20 dias de janeiro que temos localmente: 410
contratos com valor zero no bruto, 415 em centavos, e a diferença são 5
contratos de R$ 0,0001 `[AMOSTRA JAN]`. A RN-02 passou a valer para o valor em
centavos.

Sobre os identificadores: no ano inteiro, o tipo de fornecedor é PJ em
1.941.824 contratos (96,0%), PF em 74.433 (3,7%) e PE, estrangeiro, em 6.877
(0,3%). Todos os identificadores com tamanho diferente de 11 e de 14
dígitos pertencem ao tipo PE, cujo documento não segue o formato brasileiro, de
modo que não são erro de digitação. Em 1.979 contratos (0,10%) o tipo de
pessoa contradiz o tamanho do documento: 1.472 "PJ" com 11 dígitos e 507 "PF"
com 14. Dois contratos não têm identificador de fornecedor. Não cruzam com a Receita,
por não terem raiz de CNPJ, 1.474 contratos PJ, todos os 74.433 de PF e todos os
6.877 de PE. Os fornecedores PF não têm quadro societário a ser cruzado e formam
um universo separado. A RN-01 transformou isso em regra declarada: depois do
filtro de valor, esse universo tem 78.795 contratos da fato (3,9%) e R$ 16,9
bilhões (2,2% do valor depois do corte), que ficam fora dos indicadores de
controle societário e são informados à parte.

Sobre os sócios da Receita, nas 200 mil primeiras linhas de `Socios1.zip`
(`[AMOSTRA]`, não aleatória): o campo `pais` é 99,71% nulo e
`nome_representante` é 98,19% nulo; não há linhas duplicadas; e a máscara de
CPF colide, com 169.762 pessoas físicas distintas por máscara contra 195.748
por máscara mais nome. Por isso a chave do sócio é nome mais máscara, nunca a
máscara sozinha.

Há ainda um problema de duplicação que não vem da fonte e sim do processo de
coleta. A primeira versão do extrator, ao retomar uma coleta interrompida,
regravou páginas já baixadas: 18.900 linhas para 18.500 chaves únicas, ou seja,
400 duplicatas. O extrator atual, que só marca um dia como concluído após
gravar e sincronizar os dados em disco, produziu 2.023.134 linhas para
2.023.134 chaves únicas na coleta completa, mesmo com a interrupção e a
retomada de fevereiro, sem nenhuma duplicata. A deduplicação pela chave natural
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

O quinto elo já tem medição sobre a população à qual a regra se aplica, os
sócios da Receita Federal, agora no recorte nacional. Das 239.600 empresas do
recorte, 174.599 têm linha de sócio na base e 65.001 não têm (27,1%); 62.880
dessas são empresários individuais (26,2% do recorte), cujo titular não consta
do quadro societário, e formam um universo declarado à parte, sem inferência
pelo titular (decisão D5). Os 327.180 sócios pessoa física elegíveis ficaram
34,3% como femininos, 61,8% como masculinos e 4,0% como indeterminados (112.164,
202.077 e 12.939), depois de classificar 28.048 primeiros nomes distintos. A
base de nomes é a do Censo Demográfico 2022,
consultada pela API v3 do IBGE; o roteiro cita o Censo 2010, base da API v2, que
só foi usada no piloto inicial (5,7% de indeterminados) e não em nenhum número
atual. A rodada que gerou esses números não consultou a API: os 28.048 nomes já
estavam no cache, que tinha 28.112 ("0 a consultar", em
`docs/evidencias/classificacao_genero.txt`). A diferença para os 18.965 nomes
consultados em 107,7 minutos, citados em Velocidade, é compatível com cache
acumulado nas rodadas anteriores; a contagem por rodada não foi conferida, e
nenhum número de gênero depende dela. A taxa de indeterminados por sócio foi de
3,7% no piloto de mil sócios, 3,9% no recorte inicial e 4,0% no nacional; o
piloto inicial, sobre fornecedores pessoa física, tinha dado 5,7%, e a
diferença mistura a troca de população com a troca de base. Pela
regra RN-05, 131.423 empresas têm controle definido, 54,9% do recorte e 75,3%
das que têm sócio na base: 39.904 femininas e 91.519 masculinas, ou seja, 30,4%
de controle feminino entre as de controle definido, contra 30,3% no recorte
inicial. As outras 43.176 com sócio na base ficam sem controle definido: 26.817
sem maioria, 8.282 com muitos sócios indeterminados, 8.076 com sócio pessoa
jurídica e 1 que só tem sócio estrangeiro e por isso nenhum sócio elegível. Com
essa última a soma fecha nas 174.599; sem ela, dava 174.598. A fração de
empresas com controle definido caiu de 64,8% para 54,9% porque os empresários
individuais passaram de 8,8% para 26,2% do recorte. A taxa de indeterminados é o
que torna a inferência auditável: ela não é falha do método, é a medida
explícita do que o método não consegue decidir.

Duas ressalvas acompanham os 30,4%. A primeira é que eles contam empresas, não
valor: o cruzamento com o valor dos contratos, que é o que o KPI 1 pede, fica
para a Fase 2 `[PENDENTE]`. A segunda é que a contagem inclui as empresas que só
aparecem em contratos de receita, que a RN-02 passou a tirar dos indicadores;
quantas são no ano não foi medido `[PENDENTE]`. Na regra RN-03, a escolha de
contar diretor, presidente e conselheiro como administradores (decisão D4) pesa
7,8% das linhas de sócio, e a rodada sem eles fica para a Fase 2.

Vale notar que a terceira pergunta é a que mais restringe o desenho técnico,
porque análise de rede exige ver todos os contratos de cada sócio dentro do
recorte. Das três estratégias de redução de volume que o guia oferece, que são
filtros, agregações e amostragem estatística, adotamos as duas primeiras e
descartamos a terceira por causa dela: recortar preserva a rede íntegra dentro
do universo escolhido, enquanto amostrar a fragmenta e faz a métrica de
concentração subestimar sistematicamente o fenômeno que se quer medir.

## Nota sobre reprodutibilidade

Os números de Volume, Velocidade e Veracidade deste documento podem ser
reproduzidos com os scripts do diretório `etl`: `verificar_pncp.py` confere a
cobertura da coleta contra a API; `tratar_contratos.py --resumo` dá os totais do
tratamento; `recorte_cnpjs.py --todos-orgaos` aplica o corte de sanidade e gera
a lista de CNPJs (sem a opção, o script ainda faz o recorte antigo de 50
órgãos); `diagnostico_valores.py` e `auditar_extremos.py` tratam os valores
extremos e a sensibilidade do corte; `perfil_veracidade.py` recalcula os
percentuais de qualidade; `medir_pendencias.py` mede a Receita;
`classificar_empresas.py` infere o gênero do controle; e `benchmark_postgres.py`
mede o tamanho das tabelas no PostgreSQL (evidências em `docs/evidencias/`). As
medições são de 30/09/2026, sobre a coleta completa de 2025 e a competência
2026-09-14 da Receita, exceto o benchmark no PostgreSQL, de 02/10/2026. Os
itens marcados `[PENDENTE]` dependem do cruzamento do gênero com o valor dos
contratos (KPI 1) e de duas medições sobre os contratos de receita: como a marca
se distribui no ano inteiro e quantas empresas só aparecem em contratos de
receita. A diferença de 245 contratos de valor zero está explicada em
Veracidade e deixou de ser pendência. Os marcados `[AMOSTRA JAN]` são resultados
de janeiro, mantidos como histórico do método ou medidos nesta revisão sobre a
cópia local de 1 a 20 de janeiro (campos de topo, valores menores que meio
centavo e contratos de receita), já que a coleta completa e a Receita estão na
máquina da T2; a comparação contra o ano inteiro está em Veracidade, e a coleta
completa mostrou que a distribuição de janeiro não se repete ao longo do ano.