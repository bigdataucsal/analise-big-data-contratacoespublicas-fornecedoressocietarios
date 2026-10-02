# Escolha do banco: relacional versus não relacional

Entrega da Trilha 3, semana 3, atualizada em 01/10/2026 com a coleta completa de 2025. Justifica a escolha do modelo de armazenamento com o modelo de dados e com os tempos medidos, e delimita onde o não relacional entra. Os itens marcados `[PENDENTE]` dependem de medição ainda não feita e não devem ser preenchidos sem ela. As decisões do grupo estão em `docs/decisoes-do-grupo.md`.

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

Rodamos a mesma consulta em duas abordagens, cinco execuções cada, reportando a mediana.

Antes dos números, é preciso ser exato sobre o que foi medido, porque a consulta executada não é o KPI interseccional propriamente dito e seria desonesto chamá-la assim. Ela tem a mesma forma de carga, que é o que importa para comparar motores: três junções entre fato, fornecedor e município, agrupamento por faixa de composição racial do território e por faixa de valor, com soma, contagem e mediana.

Duas diferenças em relação ao KPI de verdade. Primeiro, a dimensão de fornecedor é montada a partir do próprio Parquet de contratos, e não da Receita, e o município usado é o do órgão comprador, que é o que o PNCP fornece, e não o da sede do fornecedor, que é o que a RN-06 exige. Segundo, a consulta agrupa por tipo de pessoa em vez de por gênero do controle, porque o gênero depende da tabela ponte, que não entra nesta medição. A Receita filtrada já existe (339.385 sócios), de modo que a consulta real, com a ponte, substitui esta na Fase 2.

Ou seja, a junção com a tabela ponte, que é justamente a parte que o argumento da modelagem existe para defender, ainda não está nesta medição. O que o teste mede é o custo de um padrão de junção e agregação equivalente, usado como proxy de carga.

As duas abordagens comparadas foram arquivos CSV lidos com pandas, que representam não usar banco, e um motor analítico colunar (DuckDB) lendo Parquet. `[PENDENTE: registrar a versão do DuckDB e do pandas, o número de núcleos e a memória da máquina]`

| abordagem | mediana | mínimo | máximo |
| --- | --- | --- | --- |
| arquivos CSV lidos com pandas | 5,906 s | 5,124 s | 13,479 s |
| motor colunar (DuckDB) sobre Parquet | 0,234 s | 0,185 s | 0,427 s |

A medição foi feita sobre 2.005.068 contratos, os que passam no corte de sanidade e têm valor maior que zero depois do tratamento. As duas abordagens devolveram o mesmo número de linhas, doze. `[PENDENTE: comparar também a soma de contratos e de valor entre as duas, para confirmar que o resultado é o mesmo e não apenas do mesmo tamanho]`

O motor colunar foi cerca de 25 vezes mais rápido. É preciso registrar duas ressalvas sobre esse número. A primeira é a variação entre rodadas: uma rodada anterior, feita antes de alinhar as faixas de valor entre as duas consultas, deu 35 vezes (5,710 s contra 0,163 s), e o máximo do pandas (13,5 s) é mais de duas vezes a mediana, provavelmente a primeira execução com o disco frio. Por isso reportamos a mediana e o intervalo, e não um único valor. A segunda é que a diferença não vem de um único fator. O pandas lê e converte um arquivo de texto inteiro a cada execução, enquanto o motor colunar lê só as colunas que a consulta usa, de um formato binário, e executa em paralelo em vários núcleos. O arquivo de 122 MB cabe com folga na memória, de modo que o ganho medido não vem de falta de memória. Como a diferença se comporta quando o dado deixa de caber na memória não foi medido.

O tamanho dos arquivos aponta na mesma direção. As tabelas desta medição ocupam:

| tabela | CSV | Parquet | redução |
| --- | --- | --- | --- |
| fato | 122,0 MB | 27,7 MB | 4,4 vezes |
| dim_fornecedor | 11,3 MB | 4,5 MB | 2,5 vezes |
| dim_municipio | 0,2 MB | 0,1 MB | 2,6 vezes |

Sobre a coleta inteira, os 2.023.134 contratos passam de 3,62 GB em JSONL bruto para 254,1 MB em Parquet, cerca de catorze vezes menos.

Sobre a contagem de contratos: o recorte de CNPJs tem 2.005.313 contratos e a tabela de fatos desta medição, 2.005.068. A diferença, 245, é a mesma que separa as contagens de contratos com valor zero (17.823 no Parquet e 17.578 no recorte). A explicação mais provável é que o tratamento arredonda o valor para duas casas, e contratos de valor ínfimo, como R$ 0,0001, viram zero e deixam de passar no critério de valor maior que zero. O arredondamento é correto: um contrato desse valor não representa transferência de recurso. `[PENDENTE: confirmar contando, no dado bruto, os contratos com valor entre 0 e 0,005; o esperado é 245]`

O teste pode ser reproduzido com `python benchmark_banco.py`.

### O número que falta: o PostgreSQL

Este documento ainda não traz o tempo do PostgreSQL. A comparação entre arquivos e PostgreSQL é entrega da Trilha 2, e o script que a faz está pronto: `python benchmark_postgres.py`, que reaproveita os arquivos da medição acima, carrega num schema isolado do serviço de teste da Aiven, roda a mesma consulta com e sem índices e mede, além do tempo, o tamanho real das tabelas, o tempo de execução no servidor e os arquivos temporários gerados.

| medição | valor |
| --- | --- |
| Primeira execução, sem índices | `[PENDENTE]` |
| Mediana, sem índices | `[PENDENTE]` |
| Mediana, com índices | `[PENDENTE]` |
| Tempo de execução no servidor (EXPLAIN ANALYZE) | `[PENDENTE]` |
| Arquivos temporários gerados | `[PENDENTE]` |
| Tamanho real de fato, dimensões e índices | `[PENDENTE]` |

Esta rodada mede a latência de rede até a nuvem da Aiven, além do trabalho do banco, e por isso o tempo no servidor é reportado à parte.

Vale registrar que o argumento central deste documento não depende desse número. A escolha entre relacional e não relacional se decide pela forma do dado e pela cardinalidade das relações, e cronômetro é evidência de apoio, não o fundamento. Um nó de 1 CPU e 1 GB de memória pode levar mais tempo que o motor colunar local nesta consulta, e se isso acontecer será dito aqui. A razão de o PostgreSQL ser a camada de serviço não é a velocidade de uma consulta isolada, e sim a concorrência, os índices, a integridade referencial e o atendimento a vários usuários ao mesmo tempo.

**Conclusão da comparação:** `[PENDENTE: escrever depois da tabela]`

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
| 1 CPU e 1 GB de memória | Consulta analítica pesada a cada clique não é sustentável | Visões materializadas e cache no painel |
| No máximo 20 conexões, sem pool | O painel pode esgotar as conexões | Uma conexão reutilizada e cache das consultas |
| Desligamento por falta de atividade, com aviso | O painel pode aparecer vazio | Ligar e testar na véspera e uma hora antes; capturas de tela como plano B |
| Um serviço PostgreSQL gratuito por organização | Impede um segundo serviço | Um único serviço oficial, provisionado por Terraform |

Fonte: documentação da Aiven, "Aiven for PostgreSQL free tier" (https://aiven.io/docs/products/postgresql/concepts/pg-free-tier), consultada em 01/10/2026.

O plano gratuito foi mantido por decisão do grupo, conforme a recomendação da professora, e não por falta de alternativa: é o requisito do trabalho.

Duas estimativas anteriores de tamanho divergem entre si e serão substituídas por medição. Uma tabela única e desnormalizada com os contratos ocuparia, segundo estimativa anterior, cerca de 1,9 GB entre dados e índices, e a normalização em estrela derrubaria os dados de cerca de 1,2 GB para cerca de 560 MB. Já o documento dos 5 V's extrapola que a tabela de fatos nacional passaria de 1 GB. `[PENDENTE: medir; o benchmark_postgres.py grava o tamanho real da fato e projeta para o total]` O que as medições de hoje dizem é que uma fato de cinco colunas, a mesma desta comparação, tem 27,7 MB em Parquet, e que o tamanho no PostgreSQL será maior porque não há compressão equivalente e há índices.

As decisões de modelagem que respondem ao orçamento são três.

A primeira é a normalização em estrela. Nome de órgão, de unidade, de município e de fornecedor se repetem milhões de vezes na tabela única, e substituí-los por chave estrangeira de quatro bytes reduz o volume de forma expressiva.

A segunda é a retirada do texto livre, já justificada acima.

A terceira é carregar no banco apenas uma **fato reduzida**: sem o texto do objeto e só com as colunas que as regras de negócio e os KPIs usam, para os contratos que passam no corte de sanidade. A coleta nacional completa permanece no Parquet. O plano inicial era recortar os cinquenta maiores órgãos por valor contratado; essa ideia foi abandonada, porque o KPI de comparação entre estados exige cobertura nacional, e porque o critério de valor selecionava justamente os órgãos com valores digitados errado. A estimativa de 135 MB que acompanhava aquele recorte não vale mais.

Há ainda duas otimizações menores que vale registrar porque são gratuitas. A ordem das colunas no `CREATE TABLE` não é estética: agrupar os tipos de largura fixa antes dos de texto elimina o preenchimento de alinhamento que o PostgreSQL insere entre colunas de tamanhos diferentes, o que medimos em 9,74 bytes por linha, cerca de 20 MB em 2 milhões de linhas. E usar uma chave primária inteira em vez da chave natural de 28 caracteres economiza cerca de 55 MB de índice, mantendo a chave natural como restrição de unicidade.

## Agregados calculados previamente

Um nó com 1 GB de memória não sustenta consulta analítica pesada a cada clique de filtro. Além da lentidão, consultas com ordenação e junção grande geram arquivos temporários em disco que consomem a mesma cota de 1 GB, de modo que um painel lento também enche o disco.

Por isso o schema traz duas visões materializadas, uma para o KPI interseccional e outra para a concentração societária, ambas com índice próprio. O painel consulta os agregados, não o fato.

O filtro de agregação mínima da RN-09, que impede exibir resultado baseado em menos de cinco sócios ou cinco empresas, fica de propósito na camada de apresentação e não na visão materializada, porque o mesmo agregado pode ser seguro num recorte e inseguro noutro.

## Alternativas descartadas

- **Arquivos Parquet com motor embarcado (DuckDB) como camada de serviço.** É a alternativa mais forte para análise local, e a usamos como camada analítica. Descartada como serviço pelas razões da seção "Por que não somente Parquet".
- **Banco de documentos (MongoDB ou similar).** Descartado: o dado analisado é tabular, com chaves e junções, e a única parte sem esquema, o texto do objeto, cabe melhor em um índice de busca do que em documentos.
- **Plano pago da Aiven.** Descartado por decisão do grupo, conforme a recomendação da professora.

## Resumo da decisão

Adotamos PostgreSQL, no plano gratuito da Aiven, com modelo estrela e tabela ponte, porque a análise é inteiramente feita de junções entre entidades de cardinalidade conhecida, e porque a relação muitos para muitos entre empresa e sócio exige uma tabela de ligação que um modelo de documentos resolveria pior.

Mantemos o Parquet como camada analítica, medida como cerca de 25 vezes mais rápida que arquivos CSV na consulta representativa e cerca de catorze vezes menor que o bruto, e é nela que o tratamento acontece. O banco recebe só o recorte reduzido e modelado em estrela.

Reservamos o não relacional para o texto livre do objeto do contrato, que é onde há dado sem esquema fixo e onde a busca textual justifica um índice invertido, e cuja permanência no banco relacional, além disso, não caberia no orçamento de disco.

## Pendências deste documento

- Medir o PostgreSQL com `benchmark_postgres.py` e preencher a tabela e a conclusão.
- Registrar a versão do DuckDB e do pandas e a máquina usada.
- Conferir que as duas abordagens da medição devolvem os mesmos totais, e não só o mesmo número de linhas.
- Confirmar a explicação dos 245 contratos de diferença.
- Substituir as estimativas de tamanho pela medição real da fato no banco.