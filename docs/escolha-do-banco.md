# Escolha do banco: relacional versus não relacional

Entrega da Trilha 3, semana 3. Justifica a escolha do modelo de armazenamento
com o modelo de dados e com os tempos medidos, e delimita onde o não relacional
entra.

## A pergunta, colocada corretamente

O barema pergunta por que relacional. A resposta honesta não começa por
desempenho, começa pela forma do dado.

Nossa análise é feita inteiramente de junções entre entidades bem definidas,
com cardinalidade conhecida e estável. Um contrato pertence a um órgão, tem um
fornecedor, ocorre numa data e num município. Um fornecedor tem um CNAE, um
porte e uma sede. E um fornecedor tem vários sócios, enquanto um sócio
participa de várias empresas. Essas relações não mudam de forma de registro
para registro, e todas as perguntas analíticas são recortes e agregações sobre
elas.

Esse é exatamente o caso em que o modelo relacional é a ferramenta certa, e em
que um banco de documentos seria a errada. Num banco de documentos teríamos que
escolher entre duplicar o quadro societário dentro de cada contrato, o que
multiplica o volume e cria inconsistência na atualização, ou guardar referências
e resolver as junções na aplicação, que é fazer à mão o que o banco já faz bem.

## A decisão de modelagem que vale defesa

A relação entre empresa e sócio é de muitos para muitos, e essa é a parte do
modelo que exige atenção.

Um sócio participa de várias empresas fornecedoras, e é precisamente isso que a
nossa terceira pergunta analítica quer medir. Uma empresa tem vários sócios, e é
isso que a classificação de controle por gênero precisa contar. Uma relação
desse tipo não cabe numa dimensão comum: não se pode pendurar o sócio como
atributo da empresa nem a empresa como atributo do sócio sem perder informação
ou duplicar linhas.

A solução é a tabela ponte, `ponte_empresa_socio`, que registra o vínculo como
entidade própria. Isso não é apenas correção formal: a qualificação do sócio e
a data de entrada descrevem o vínculo, não a empresa nem a pessoa, e só existem
lugar numa tabela de ligação.

É essa tabela que permite as duas leituras que o projeto precisa. Agregando por
empresa, chega se à classificação de controle. Agregando por sócio, chega se à
concentração societária, ou seja, quantas empresas fornecedoras cada pessoa
integra e quanto valor essas empresas capturaram.

O modelo completo está em `etl/schema_estrela.sql`, com dez tabelas, duas
visões materializadas e doze índices, validado contra o parser oficial do
PostgreSQL.

## A evidência de desempenho

Rodamos a mesma consulta nas duas abordagens, cinco execuções cada, reportando
a mediana.

Antes dos números, é preciso ser exato sobre o que foi medido, porque a
consulta executada não é o KPI interseccional propriamente dito e seria
desonesto chamá la assim. Ela tem a mesma forma de carga, que é o que importa
para comparar motores: três junções entre fato, fornecedor e município,
agrupamento por faixa de composição racial do território e por faixa de valor,
com soma, contagem e mediana.

Duas diferenças em relação ao KPI de verdade, e ambas existem porque a base de
sócios da Receita ainda não foi baixada. Primeiro, o município usado é o do
órgão comprador, que é o que o PNCP fornece, e não o da sede do fornecedor, que
é o que a RN-06 exige e que só vem com a Receita. Segundo, a consulta agrupa
por tipo de pessoa em vez de por gênero do controle, porque o gênero depende da
tabela ponte, que ainda não tem conteúdo.

Ou seja, a junção com a tabela ponte, que é justamente a parte que o argumento
da modelagem existe para defender, não está nesta medição. O que o teste mede é
o custo de um padrão de junção e agregação equivalente, usado como proxy de
carga. Quando a Receita chegar, a consulta real substitui esta.

| abordagem | mediana | mínimo | máximo |
|---|---|---|---|
| arquivos soltos lidos com pandas | 0,114 s | 0,100 s | 0,123 s |
| motor colunar sobre Parquet | 0,028 s | 0,024 s | 0,047 s |

As duas produziram o mesmo resultado, doze linhas, o que confirma que a
comparação é justa.

O motor colunar foi quatro vezes mais rápido. É preciso dizer com clareza que
essa medição foi feita sobre os 58.328 contratos já coletados, e não sobre os
2.023.236 do recorte completo.

Sobre esse 58.328, cabe uma reconciliação, porque aparecem três números
próximos em documentos diferentes deste projeto e a diferença tem explicação.
São 58.769 contratos coletados no bruto. Aplicando a RN-02 sobre o bruto, ficam
58.333, que é o número do arquivo de recorte. Aplicando a mesma regra sobre o
dado já tratado, ficam 58.328. Os cinco de diferença são contratos com valor de
um décimo de milésimo de real, que o tratamento arredonda para zero ao converter
para decimal de duas casas e que então não passam no critério de valor maior que
zero. O arredondamento está correto: contrato de R$ 0,0001 não representa
transferência de recurso.

Voltando à escala: com 58 mil contratos os dois caminhos cabem inteiros na
memória, então a diferença de quatro vezes subestima o que acontece no volume
real. É justamente quando o dado deixa de caber na memória que a leitura
colunar, que carrega apenas as colunas consultadas, se separa da leitura linha
a linha.

O tamanho dos arquivos aponta na mesma direção e não depende de escala. A mesma
tabela de fatos ocupa 3,4 MB em CSV e 0,8 MB em Parquet, uma redução de 4,6
vezes. Sobre o conjunto tratado inteiro a redução é ainda maior: 105 MB de JSONL
bruto viram 6,7 MB de Parquet, quase dezesseis vezes menos.

O teste pode ser reproduzido com `python benchmark_banco.py`.

### O número que falta

Este documento não traz o tempo do PostgreSQL. A comparação entre pandas sobre
CSV e PostgreSQL é a entrega da Trilha 1, e não foi possível medi la aqui por
não haver instância local nem Docker na máquina, e porque medir contra o Aiven
exigiria a credencial do serviço.

Quando esse número chegar, ele entra nesta seção. O que ele acrescenta é a
comparação entre o motor analítico e o banco transacional; o que já está medido
é a comparação entre usar um motor de consulta e não usar nenhum.

Vale registrar que o argumento central deste documento não depende desse
número. A escolha entre relacional e não relacional se decide pela forma do
dado e pela cardinalidade das relações, e cronômetro é evidência de apoio, não
o fundamento.

## Onde o não relacional entra

Rejeitar o não relacional inteiramente seria tão pouco fundamentado quanto
adotá lo sem motivo. Há exatamente um lugar no projeto onde ele se justifica.

O campo do objeto do contrato é texto livre em português, sem padronização, com
média de 149 caracteres e máximo de 5.120. Sobre ele as perguntas são de busca
textual e de frequência de termos, que é o tipo de carga para o qual um índice
invertido foi feito.

Há também uma razão de custo que decide a questão. Medimos que manter esse
campo no PostgreSQL custaria cerca de 313 MB de dados mais algo entre 400 e 465
MB de índice de busca textual por trigramas. São entre 713 e 778 MB numa única
coluna, contra um orçamento utilizável de 500 a 700 MB no plano gratuito da
Aiven. Ou seja, essa coluna sozinha não cabe.

A decisão é portanto que o objeto do contrato permanece na camada Parquet e,
se houver tempo, é indexado no OpenSearch. Se o tempo apertar, essa camada é a
primeira a ser cortada, e o corte deve ser declarado como decisão de escopo e
não como esquecimento.

## Por que não somente Parquet

Se o motor colunar é mais rápido e o Parquet é menor, cabe a pergunta de por
que carregar qualquer coisa num banco.

A resposta é que o painel não faz uma consulta, faz muitas, disparadas por
interação de usuário, e precisa de concorrência, de controle de acesso e de um
ponto de serviço estável na rede. Arquivos Parquet resolvem processamento em
lote, não atendimento a múltiplos usuários simultâneos com filtros cruzados.

A arquitetura resultante usa os dois, cada um onde é bom. O Parquet é a camada
analítica, onde o tratamento acontece e onde o dado bruto fica preservado. O
PostgreSQL é a camada de serviço, que recebe apenas o recorte modelado em
estrela e responde ao painel.

## O que a restrição de 1 GB impôs ao modelo

O plano gratuito da Aiven oferece 1 GB, e esse 1 GB é o disco de dados do
serviço inteiro, não a soma do tamanho das tabelas. Contam os índices, o write
ahead log gerado durante a carga, os arquivos temporários de consultas que não
cabem na memória e o espaço deixado por registros atualizados. Apenas os
backups ficam fora. O orçamento realmente utilizável fica entre 500 e 700 MB.

Medimos que uma tabela única e desnormalizada com os 2 milhões de contratos
ocuparia cerca de 1,9 GB entre dados e índices, quase o triplo do disponível.
Três decisões de modelagem resolvem isso.

A primeira é a normalização em estrela. Nome de órgão, de unidade, de município
e de fornecedor se repetem milhões de vezes na tabela única, e substituí los por
chave estrangeira de quatro bytes derruba os dados de cerca de 1,2 GB para cerca
de 560 MB.

A segunda é a retirada do texto livre, já justificada acima.

A terceira é o recorte dos cinquenta maiores órgãos por valor contratado, que
representa 11,0% dos contratos e 71,0% do valor, levando a tabela de fatos para
a ordem de 135 MB.

Há ainda duas otimizações menores que vale registrar porque são gratuitas. A
ordem das colunas no `CREATE TABLE` não é estética: agrupar os tipos de largura
fixa antes dos de texto elimina o preenchimento de alinhamento que o PostgreSQL
insere entre colunas de tamanhos diferentes, o que medimos em 9,74 bytes por
linha, cerca de 20 MB em 2 milhões de linhas. E usar uma chave primária inteira
em vez da chave natural de 28 caracteres economiza cerca de 55 MB de índice,
mantendo a chave natural como restrição de unicidade.

## Agregados calculados previamente

Um nó com 1 GB de memória não sustenta consulta analítica pesada a cada clique
de filtro. Além da lentidão, consultas com ordenação e junção grande geram
arquivos temporários em disco que consomem a mesma cota de 1 GB, de modo que um
painel lento também enche o disco.

Por isso o schema traz duas visões materializadas, uma para o KPI interseccional
e outra para a concentração societária, ambas com índice próprio. O painel
consulta os agregados, não o fato.

O filtro de agregação mínima da RN-09, que impede exibir resultado baseado em
menos de cinco sócios ou cinco empresas, fica de propósito na camada de
apresentação e não na visão materializada, porque o mesmo agregado pode ser
seguro num recorte e inseguro noutro.

## Resumo da decisão

Adotamos PostgreSQL com modelo estrela e tabela ponte, porque a análise é
inteiramente feita de junções entre entidades de cardinalidade conhecida, e
porque a relação muitos para muitos entre empresa e sócio exige uma tabela de
ligação que um modelo de documentos resolveria pior.

Mantemos o Parquet como camada analítica, medida como quatro vezes mais rápida
que arquivos soltos na consulta representativa e quase dezesseis vezes menor
que o bruto, e é nela que o tratamento acontece.

Reservamos o não relacional para o texto livre do objeto do contrato, que é
onde há dado sem esquema fixo e onde a busca textual justifica um índice
invertido, e cuja permanência no banco relacional, além disso, não caberia no
orçamento de disco.
