# Escolha do banco: relacional versus não relacional

Entrega da Trilha 3, semana 3, atualizada em 02/10/2026 com a coleta completa de 2025 e as medições no PostgreSQL da Aiven. Justifica a escolha do modelo de armazenamento com o modelo de dados e com os tempos medidos, e delimita onde o não relacional entra. Os itens marcados `[PENDENTE]` dependem de medição ainda não feita e não devem ser preenchidos sem ela. As decisões do grupo estão em `docs/decisoes-do-grupo.md`.

## A pergunta, colocada corretamente

O barema pergunta por que relacional. A resposta honesta não começa por desempenho, começa pela forma do dado.

Nossa análise é feita inteiramente de junções entre entidades bem definidas, com cardinalidade conhecida e estável. Um contrato pertence a um órgão, tem um fornecedor, ocorre numa data e num município. Um fornecedor tem um CNAE, um porte e uma sede. E um fornecedor tem vários sócios, enquanto um sócio participa de várias empresas. Essas relações não mudam de forma de registro para registro, e todas as perguntas analíticas são recortes e agregações sobre elas.

Esse é exatamente o caso em que o modelo relacional é a ferramenta certa, e em que um banco de documentos seria a errada. Num banco de documentos teríamos que escolher entre duplicar o quadro societário dentro de cada contrato, o que multiplica o volume e cria inconsistência na atualização, ou guardar referências e resolver as junções na aplicação, que é fazer à mão o que o banco já faz bem.

## A escala do problema

| Entidade | Quantidade no recorte nacional de 2025 |
| --- | --- |
| Contratos publicados no PNCP | 2.023.134 (2.005.313 no recorte de CNPJs, depois do corte de sanidade e do valor maior que zero) |
| Raízes de CNPJ fornecedoras | 239.605 (239.600 constam do cadastro da Receita) |
| Estabelecimentos dessas empresas | 529.225 |
| Registros de sócios | 339.385 (327.180 sócios pessoa física elegíveis) |

As perguntas do projeto são todas junções e agregações: valor e número de contratos por classe de controle, cruzamento com a composição racial do território e sócios que integram várias empresas fornecedoras. Um painel com filtro cruzado repete essas agregações a cada interação.

## A decisão de modelagem que vale defesa

A relação entre empresa e sócio é de muitos para muitos, e essa é a parte do modelo que exige atenção.

Um sócio participa de várias empresas fornecedoras, e é precisamente isso que a nossa terceira pergunta analítica quer medir. Uma empresa tem vários sócios, e é isso que a classificação de controle por gênero precisa contar. Uma relação desse tipo não cabe numa dimensão comum: não se pode pendurar o sócio como atributo da empresa nem a empresa como atributo do sócio sem perder informação ou duplicar linhas.

A solução é a tabela ponte, `ponte_empresa_socio`, que registra o vínculo como entidade própria. Isso não é apenas correção formal: a qualificação do sócio e a data de entrada descrevem o vínculo, não a empresa nem a pessoa, e só têm lugar numa tabela de ligação.

É essa tabela que permite as duas leituras que o projeto precisa. Agregando por empresa, chega-se à classificação de controle. Agregando por sócio, chega-se à concentração societária, ou seja, quantas empresas fornecedoras cada pessoa integra e quanto valor essas empresas capturaram.

Duas chaves merecem registro. A chave de junção com o quadro societário é a **raiz de 8 dígitos** do CNPJ, porque o quadro societário pertence à empresa e não ao estabelecimento. E o identificador do sócio é derivado de nome mais máscara do CPF, porque a máscara sozinha colide (169.762 pessoas distintas por máscara contra 195.748 por máscara mais nome, em 200 mil linhas de amostra).

O modelo completo está em `etl/schema_estrela.sql`, com dez tabelas, duas visões materializadas e doze índices, validado contra o parser oficial do PostgreSQL.

## A evidência de desempenho

Rodamos a mesma consulta em três abordagens: arquivos CSV lidos com pandas, um motor analítico colunar (DuckDB) sobre Parquet e o PostgreSQL do plano gratuito da Aiven. Nas duas abordagens locais foram cinco execuções cada, reportando a mediana; a medição no PostgreSQL está na seção seguinte.

Antes dos números, é preciso ser exato sobre o que foi medido, porque a consulta executada não é o KPI interseccional propriamente dito e seria desonesto chamá-la assim. Ela tem a mesma forma de carga, que é o que importa para comparar motores: três junções entre fato, fornecedor e município, agrupamento por faixa de composição racial do território e por faixa de valor, com soma, contagem e mediana.

Duas diferenças em relação ao KPI de verdade. Primeiro, a dimensão de fornecedor é montada a partir do próprio Parquet de contratos, e não da Receita, e o município usado é o do órgão comprador, que é o que o PNCP fornece, e não o da sede do fornecedor, que é o que a RN-06 exige. A dimensão tem 243.297 raízes de CNPJ, contra as 239.605 do recorte `[PENDENTE: confirmar a explicação; a hipótese é que a dimensão inclui fornecedores cujos contratos todos ficam fora do filtro de valor, aplicado só à fato]`. Segundo, a consulta agrupa por tipo de pessoa em vez de por gênero do controle, porque o gênero depende da tabela ponte, que não entra nesta medição. A Receita filtrada já existe (339.385 sócios), de modo que a consulta real, com a ponte, substitui esta na Fase 2.

Ou seja, a junção com a tabela ponte, que é justamente a parte que o argumento da modelagem existe para defender, ainda não está nesta medição. O que o teste mede é o custo de um padrão de junção e agregação equivalente, usado como proxy de carga.

As duas abordagens locais foram arquivos CSV lidos com pandas, que representam não usar banco, e o motor colunar lendo Parquet. Versões e máquina: DuckDB 1.5.5, pandas 3.0.6, Python 3.12.10, Windows 11, 12 processadores lógicos e 7,67 GiB de memória RAM.

Para que a comparação use o mesmo conteúdo nas três abordagens, o script aceita `--linhas N`, que toma as primeiras N linhas do mesmo `fato.csv` que o `benchmark_postgres.py` carrega. O volume completo é de 2.005.068 contratos, os que passam no corte de sanidade e têm valor maior que zero depois do tratamento. Rodadas de 02/10/2026, com cinco execuções cada (medianas em segundos, com mínimo e máximo):

| linhas na fato | pandas sobre CSV | DuckDB sobre Parquet | razão |
| --- | --- | --- | --- |
| 200 mil | 0,588 (0,538 a 0,700) | 0,039 (0,038 a 0,086) | 14,9 vezes |
| 1 milhão | 1,691 (1,603 a 2,007) | 0,078 (0,077 a 0,132) | 21,6 vezes |
| 2.005.068 (rodada de 02/10) | 5,419 (3,120 a 8,461) | 0,112 (0,109 a 0,161) | 48,5 vezes |
| 2.005.068 (rodada de 01/10) | 5,906 (5,124 a 13,479) | 0,234 (0,185 a 0,427) | 25 vezes |

Além do tempo, o script compara o resultado das duas abordagens, grupo a grupo. Nos três volumes os resultados são idênticos: 12 grupos, com contagem de contratos exata e soma e mediana do valor iguais até R$ 0,01. No volume completo, o resultado reúne 1.926.273 contratos e R$ 754,3 bilhões (evidências em `docs/evidencias/benchmark_banco_200000.txt`, `benchmark_banco_1000000.txt` e `benchmark_banco_completo.txt`).

O resultado deixa de fora uma parte da fato: 9.349 contratos com 200 mil linhas (4,7%), 45.271 com 1 milhão (4,5%) e 78.795 no volume completo (3,9%). Medimos a causa no volume completo: os 78.795 são todos contratos cujo fornecedor não tem raiz de CNPJ (pessoa física, estrangeiro ou identificador irregular), e a junção interna com a dimensão de fornecedor os descarta. Nenhum contrato fica de fora por município (todos têm código IBGE presente na dimensão) nem por raiz ausente na dimensão. Esses contratos somam R$ 16,9 bilhões, que, somados aos R$ 754,3 bilhões do resultado, dão R$ 771,2 bilhões, o mesmo valor do recorte. O número é coerente com os 82.784 contratos sem raiz de CNPJ do ano inteiro (74.433 de pessoa física, 6.877 estrangeiros e 1.474 de PJ com identificador irregular), dos quais alguns saem antes, no filtro de valor. Isso importa para o KPI de participação feminina: é o universo de fornecedores sem quadro societário, que o projeto declara à parte.

O motor colunar foi de 15 a 48 vezes mais rápido que o pandas, e a razão cresce com o volume. É preciso registrar duas ressalvas sobre o número do volume completo. A primeira é a variação: o pandas oscilou entre 3,1 s e 8,5 s nas cinco execuções (a primeira, 4,7 s, não foi a mais lenta, de modo que não se trata só de disco frio), e a razão deu 35 vezes numa rodada anterior, feita antes de alinhar as faixas de valor (5,710 s contra 0,163 s), 25 vezes em 01/10 e 48,5 vezes em 02/10. Por isso reportamos a mediana e o intervalo, e a razão no volume completo deve ser lida como uma faixa, de cerca de 25 a 48 vezes, e não como um valor único. A segunda é que a diferença não vem de um único fator. O pandas lê e converte um arquivo de texto inteiro a cada execução, enquanto o motor colunar lê só as colunas que a consulta usa, de um formato binário, e executa em paralelo em vários núcleos. O arquivo de 122 MB cabe com folga na memória, de modo que o ganho medido não vem de falta de memória. Como a diferença se comporta quando o dado deixa de caber na memória não foi medido.

O tamanho dos arquivos aponta na mesma direção. As tabelas desta medição ocupam:

| tabela | CSV | Parquet | redução |
| --- | --- | --- | --- |
| fato | 122,0 MB | 27,7 MB | 4,4 vezes |
| dim_fornecedor | 11,3 MB | 4,5 MB | 2,5 vezes |
| dim_municipio | 0,2 MB | 0,1 MB | 2,6 vezes |

Sobre a coleta inteira, os 2.023.134 contratos passam de 3,62 GB em JSONL bruto para 254,1 MB em Parquet, cerca de catorze vezes menos.

Sobre a contagem de contratos: o recorte de CNPJs tem 2.005.313 contratos e a tabela de fatos desta medição, 2.005.068. A diferença, 245, é a mesma que separa as contagens de contratos de valor zero ou negativo (17.823 no Parquet e 17.578 no recorte): a fato da medição exclui todos os 17.823, e o recorte exclui 245 a menos. A explicação não está confirmada. Se os dois scripts leem o mesmo Parquet, o arredondamento do valor no tratamento não explica a diferença, porque afetaria os dois do mesmo modo; as hipóteses a verificar são o filtro de valor do `recorte_cnpjs.py` (por exemplo, tratar só valor igual a zero, e deixar passar valores negativos) e o tratamento de nulos. `[PENDENTE: contar, no Parquet, os contratos com valor igual a zero, menor que zero e nulo, e conferir o filtro do recorte; se o recorte aceita valor negativo, a RN-02 está descumprida por 245 contratos e isso deve ser declarado]`

O teste pode ser reproduzido com `python benchmark_banco.py` (prepara os arquivos e roda no volume completo) e com `python benchmark_banco.py --linhas N` (usa os arquivos já preparados).

### A medição no PostgreSQL

O script `etl/benchmark_postgres.py` reaproveita os arquivos da medição acima, carrega a fato e as duas dimensões num schema isolado do serviço da Aiven (plano gratuito, PostgreSQL 18.6, 1 CPU, 1 GB de memória e 1 GB de disco), roda a mesma consulta com e sem índices de junção e mede, além do tempo, o tamanho real das tabelas, o tempo de execução no servidor (EXPLAIN ANALYZE) e os arquivos temporários. Esta rodada mede também a latência de rede entre a máquina local e a nuvem da Aiven, e por isso o tempo no servidor é reportado à parte. A fato desta medição tem só cinco colunas. Foram feitas três rodadas em 02/10/2026, com 200 mil, 1 milhão e todas as 2.005.068 linhas da fato:

| medição | 200 mil linhas | 1 milhão de linhas | 2.005.068 linhas |
| --- | --- | --- | --- |
| Carga da fato | 3,8 s | 97,9 s | 27,8 s |
| Sem índices: mediana no cliente (mín. a máx.) | 2,315 s (1,545 a 2,865) | 15,259 s (11,873 a 16,548) | a conexão caiu |
| Sem índices: tempo no servidor | 1,537 s | 14,292 s | n/d |
| Criação dos índices | 5,2 s | 32,3 s | não chegou a esta etapa |
| Com índices: mediana no cliente (mín. a máx.) | 1,624 s (1,422 a 2,440) | 9,204 s (6,764 a 12,441) | n/d |
| Com índices: tempo no servidor | 1,593 s | 6,010 s | n/d |
| Arquivos temporários (estatística acumulada do banco) | 190,6 MB | 1.164,1 MB | n/d |
| Fato, com índices | 23,1 MB | 111,3 MB | 177 MB sem índices (medido) |
| dim_fornecedor | 27,3 MB com índices | 27,3 MB com índices | 19 MB sem índices |
| dim_municipio | 0,8 MB com índices | 0,8 MB com índices | 0,6 MB sem índices |

Na rodada com a fato completa a carga terminou, mas a primeira consulta, sem índices, encerrou com `SSL connection has been closed unexpectedly`: o servidor derrubou a conexão. A causa não foi confirmada, porque não tivemos acesso aos logs do serviço. O console mostrava, numa janela de 60 minutos, memória em 80%, armazenamento em 62,8% e picos de CPU perto de 100% (`docs/evidencias/aiven_uso_do_no.png`), o que é compatível com falta de memória, mas não a prova. O script não conseguiu apagar o schema, que foi removido à mão (o banco voltou de 204 MB para 7,8 MB), e as tabelas foram medidas antes disso, ainda sem índices. O armazenamento de 62,8% não é comparável com os 204 MB do banco, porque o disco do serviço conta também o log de transações, os arquivos temporários e o sistema. O tempo de carga também variou entre as rodadas (97,9 s para 1 milhão de linhas contra 27,8 s para 2 milhões), e essa variação não foi investigada.

O que as medições mostram:

- **O volume cabe no orçamento.** A fato de cinco colunas com todos os contratos ocupa 177 MB sem índices. Com índices, a estimativa vai de 213 MB (os índices somaram 20,2% dos dados com 1 milhão de linhas) a 223 MB (projeção linear dessa mesma rodada); a projeção do ensaio de 200 mil linhas foi de 231,5 MB. Somando as duas dimensões, as três tabelas ficam entre 241 e 251 MB, dentro do orçamento utilizável de 500 a 700 MB. A fato reduzida final terá mais colunas, e seu tamanho será medido na carga da Fase 2.
- **O custo da consulta cresce mais que o volume.** Com 5 vezes mais linhas, o tempo no servidor foi 9,3 vezes maior sem índices (1,537 s para 14,292 s) e 3,8 vezes maior com índices (1,593 s para 6,010 s), e os arquivos temporários cresceram 6,1 vezes.
- **Os índices só mostraram efeito na escala maior.** Com 200 mil linhas o tempo no servidor ficou igual (1,537 s e 1,593 s); com 1 milhão caiu de 14,292 s para 6,010 s, 2,4 vezes. O efeito sobre consultas seletivas, como as do drill-down, não foi medido.
- **A consulta sobre a fato inteira não é viável no nó gratuito.** Com metade da fato, ela levou 6,0 s no servidor com índices; com a fato completa, o servidor derrubou a conexão.

**Mesmo volume, três abordagens** (mediana, em segundos). As máquinas são diferentes: pandas e DuckDB rodaram numa máquina local com 12 processadores lógicos e 7,67 GiB de memória, e o PostgreSQL no nó gratuito da Aiven, com 1 CPU e 1 GB.

| linhas na fato | pandas | DuckDB | PostgreSQL, no servidor, com índices |
| --- | --- | --- | --- |
| 200 mil | 0,588 | 0,039 | 1,593 |
| 1 milhão | 1,691 | 0,078 | 6,010 |
| 2.005.068 | 5,419 | 0,112 | a conexão caiu |

Com os mesmos volumes, o PostgreSQL gratuito levou 2,7 vezes o tempo do pandas com 200 mil linhas e 3,6 vezes com 1 milhão, sem contar a rede (o tempo medido no cliente foi de 1,624 s e 9,204 s). O resultado do PostgreSQL também tem 12 linhas, mas a conferência dos totais contra o DuckDB não aparece nas saídas dessas rodadas.

**Conclusão da comparação.** Nesta consulta, que agrega a fato inteira sem filtro, o PostgreSQL do nó gratuito não é a abordagem mais rápida. O motor colunar percorreu as 2.005.068 linhas em 0,11 a 0,23 s e o pandas em 5,4 a 5,9 s, conforme a rodada, enquanto o PostgreSQL levou 6,0 s no servidor com a metade das linhas e não terminou com a fato completa. Os volumes agora são os mesmos, mas as máquinas são diferentes, e por isso os tempos valem como ordem de grandeza, não como razão exata. Isso basta para a decisão do projeto: o painel não consulta a fato a cada interação, e sim agregados calculados previamente. A razão de o PostgreSQL ser a camada de serviço não é a velocidade de uma consulta isolada, e sim a concorrência, os índices, a integridade referencial e o atendimento a vários usuários ao mesmo tempo, que este teste não mede. O argumento central deste documento, a forma relacional do dado, não depende do cronômetro: o tempo medido apoia a decisão de materializar agregados, e não a de preferir o banco por velocidade.

A rodada completa (`--linhas 0`) não deve ser repetida no nó gratuito. O ensaio de 200 mil linhas e a rodada de 1 milhão podem ser reproduzidos com `python benchmark_postgres.py --linhas 200000` e `--linhas 1000000`, com o serviço ligado. As evidências estão em `docs/evidencias/` (`benchmark_postgres_ensaio_200k.txt`, `benchmark_postgres_1M.txt`, `benchmark_postgres_falha_2M.txt` e `aiven_uso_do_no.png`).

## Onde o não relacional entra

Rejeitar o não relacional inteiramente seria tão pouco fundamentado quanto adotá-lo sem motivo. Há exatamente um lugar no projeto onde ele se justifica.

O campo do objeto do contrato é texto livre em português, sem padronização, com média de 160 caracteres e máximo de 5.120 nos 2.023.134 contratos. Sobre ele as perguntas são de busca textual e de frequência de termos, que é o tipo de carga para o qual um índice invertido foi feito.

Há também uma razão de custo que decide a questão. O campo soma 334,6 MB de dados, e um índice de busca textual por trigramas custaria algo entre 430 e 500 MB, estimativa feita sobre a razão medida na amostra de janeiro. São entre 765 e 835 MB numa única coluna, contra um orçamento utilizável de 500 a 700 MB no plano gratuito da Aiven. Ou seja, essa coluna sozinha não cabe.

A decisão é portanto que o objeto do contrato permanece na camada Parquet e, se houver tempo, é indexado em um motor de busca. Se o tempo apertar, essa camada é a primeira a ser cortada, e o corte deve ser declarado como decisão de escopo e não como esquecimento.

O JSON do PNCP, por sua vez, é aninhado, mas só em quatro objetos (órgão, tipo de contrato, categoria do processo e unidade do órgão), e todos se achatam em colunas e dimensões sem perda. Um banco de documentos não traria ganho para esse dado.

## Por que não somente Parquet

Se o motor colunar é mais rápido e o Parquet é menor, cabe a pergunta de por que carregar qualquer coisa num banco.

A resposta é que o painel não faz uma consulta, faz muitas, disparadas por interação de usuário, e precisa de concorrência, de controle de acesso e de um ponto de serviço estável na rede. Arquivos Parquet, mesmo com um motor embarcado como o DuckDB, resolvem processamento em lote, não atendimento a múltiplos usuários simultâneos com filtros cruzados, e não oferecem integridade referencial. Além disso, o projeto exige um serviço de banco gerenciado.

A arquitetura resultante usa os dois, cada um onde é bom. O Parquet é a camada analítica, onde o tratamento acontece e onde o dado bruto fica preservado. O PostgreSQL é a camada de serviço, que recebe apenas o recorte modelado em estrela e responde ao painel.

## O que a restrição de 1 GB impôs ao modelo

O plano gratuito da Aiven oferece 1 GB, e esse 1 GB é o disco de dados do serviço inteiro, não a soma do tamanho das tabelas. Contam os índices, o write ahead log gerado durante a carga, os arquivos temporários de consultas que não cabem na memória e o espaço deixado por registros atualizados. Apenas os backups ficam fora. O orçamento realmente utilizável fica entre 500 e 700 MB.

O plano impõe ainda outros limites, que moldam o painel:

| Limite | Efeito | Resposta do projeto |
| --- | --- | --- |
| 1 CPU e 1 GB de memória | Consulta analítica pesada a cada clique não é sustentável; medido: a agregação sobre a fato completa derrubou a conexão | Visões materializadas e cache no painel |
| No máximo 20 conexões, sem pool | O painel pode esgotar as conexões | Uma conexão reutilizada e cache das consultas |
| Desligamento por falta de atividade, com aviso | O painel pode aparecer vazio | Ligar e testar na véspera e uma hora antes; capturas de tela como plano B |
| Um serviço PostgreSQL gratuito por organização | Impede um segundo serviço | Um único serviço oficial, provisionado por Terraform |

Fonte: documentação da Aiven, "Aiven for PostgreSQL free tier" (https://aiven.io/docs/products/postgresql/concepts/pg-free-tier), consultada em 01/10/2026.

O plano gratuito foi mantido por decisão do grupo, conforme a recomendação da professora, e não por falta de alternativa: é o requisito do trabalho.

Duas estimativas anteriores de tamanho divergiam entre si: uma tabela única e desnormalizada com os contratos ocuparia cerca de 1,9 GB entre dados e índices, e a normalização em estrela derrubaria os dados de cerca de 1,2 GB para cerca de 560 MB; já o documento dos 5 V's extrapolava que a tabela de fatos nacional passaria de 1 GB. A medição do PostgreSQL substitui essas estimativas para a fato de cinco colunas: 177 MB sem índices, e de 213 a 223 MB com índices. As estimativas antigas descrevem tabelas com outro conjunto de colunas e não são comparáveis com esta medição. O tamanho da fato reduzida final, que terá mais colunas, será medido na carga da Fase 2.

As decisões de modelagem que respondem ao orçamento são três.

A primeira é a normalização em estrela. Nome de órgão, de unidade, de município e de fornecedor se repetem milhões de vezes na tabela única, e substituí-los por chave estrangeira de quatro bytes reduz o volume de forma expressiva.

A segunda é a retirada do texto livre, já justificada acima.

A terceira é carregar no banco apenas uma **fato reduzida**: sem o texto do objeto e só com as colunas que as regras de negócio e os KPIs usam, para os contratos que passam no corte de sanidade. A coleta nacional completa permanece no Parquet. O plano inicial era recortar os cinquenta maiores órgãos por valor contratado; essa ideia foi abandonada, porque o KPI de comparação entre estados exige cobertura nacional, e porque o critério de valor selecionava justamente os órgãos com valores digitados errado. A estimativa de 135 MB que acompanhava aquele recorte não vale mais.

Há ainda duas otimizações menores que vale registrar porque são gratuitas. A ordem das colunas no `CREATE TABLE` não é estética: agrupar os tipos de largura fixa antes dos de texto elimina o preenchimento de alinhamento que o PostgreSQL insere entre colunas de tamanhos diferentes, o que medimos em 9,74 bytes por linha, cerca de 20 MB em 2 milhões de linhas. E usar uma chave primária inteira em vez da chave natural de 28 caracteres economiza cerca de 55 MB de índice, mantendo a chave natural como restrição de unicidade.

## Agregados calculados previamente

Um nó com 1 GB de memória não sustenta consulta analítica pesada a cada clique de filtro, e a medição acima confirma: a agregação sobre a fato completa derrubou a conexão. Além da lentidão, consultas com ordenação e junção grande geram arquivos temporários em disco que consomem a mesma cota de 1 GB (1.164,1 MB de temporários acumulados na rodada de 1 milhão de linhas, segundo a estatística do banco), de modo que um painel lento também enche o disco.

Por isso o schema traz duas visões materializadas, uma para o KPI interseccional e outra para a concentração societária, ambas com índice próprio. O painel consulta os agregados, não o fato.

O filtro de agregação mínima da RN-09, que impede exibir resultado baseado em menos de cinco sócios ou cinco empresas, fica de propósito na camada de apresentação e não na visão materializada, porque o mesmo agregado pode ser seguro num recorte e inseguro noutro.

## Alternativas descartadas

- **Arquivos Parquet com motor embarcado (DuckDB) como camada de serviço.** É a alternativa mais forte para análise local, e a usamos como camada analítica. Descartada como serviço pelas razões da seção "Por que não somente Parquet".
- **Banco de documentos (MongoDB ou similar).** Descartado: o dado analisado é tabular, com chaves e junções, e a única parte sem esquema, o texto do objeto, cabe melhor em um índice de busca do que em documentos.
- **Plano pago da Aiven.** Descartado por decisão do grupo, conforme a recomendação da professora.

## Resumo da decisão

Adotamos PostgreSQL, no plano gratuito da Aiven, com modelo estrela e tabela ponte, porque a análise é inteiramente feita de junções entre entidades de cardinalidade conhecida, e porque a relação muitos para muitos entre empresa e sócio exige uma tabela de ligação que um modelo de documentos resolveria pior.

Mantemos o Parquet como camada analítica, medida como de 25 a 48 vezes mais rápida que arquivos CSV na consulta representativa, no volume completo e cerca de catorze vezes menor que o bruto, e é nela que o tratamento acontece. O banco recebe só o recorte reduzido e modelado em estrela. No nó gratuito, a mesma consulta sobre a fato completa não chegou a terminar (a conexão caiu) e, com 1 milhão de linhas, levou 6,0 s no servidor; por isso o painel lê agregados materializados, e a escolha do banco se apoia na forma do dado, não na velocidade.

Reservamos o não relacional para o texto livre do objeto do contrato, que é onde há dado sem esquema fixo e onde a busca textual justifica um índice invertido, e cuja permanência no banco relacional, além disso, não caberia no orçamento de disco.

## Pendências deste documento

- Confirmar a explicação dos 245 contratos de diferença e das 3.692 raízes a mais na dimensão de fornecedor.
- Medir o tamanho da fato reduzida final na carga da Fase 2.
- Medir no PostgreSQL uma consulta seletiva, como a do drill-down, onde o índice deve contar.
- Conferir o resultado do PostgreSQL contra o do DuckDB nos mesmos volumes.
- Investigar a causa da queda da conexão com a fato completa, se o grupo tiver acesso aos logs do serviço.