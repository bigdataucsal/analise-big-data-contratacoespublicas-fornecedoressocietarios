# Bases de dados utilizadas

Declara todas as bases do projeto, separando a base oficial do tema das bases
complementares, e justifica cada complementar. Existe porque o guia nomeia uma
base por tema, e usamos mais do que ela.

A regra obrigatória do guia é o uso exclusivo de bases de dados abertas
governamentais e públicas brasileiras, com alinhamento às ODS 5 e ODS 18. Todas
as bases abaixo atendem essa regra.

## Base oficial do tema

O guia atribui ao tema Contratações Públicas e Fornecedores Societários a base
PNCP e Dados do Portal da Transparência (CGU). Usamos as duas.

O Portal Nacional de Contratações Públicas é a fonte primária dos contratos.
Acessado pela API pública de consulta, sem autenticação, devolve JSON com CNPJ
do fornecedor, valor, objeto, órgão, datas e modalidade. É dele que sai a
tabela de fatos.

O Portal da Transparência da CGU cobre contratos e licitações do Executivo
Federal e, principalmente, as listas de sanção CEIS e CNEP. É a base da RN-08,
que marca contrato firmado com fornecedor sancionado. Exige chave gratuita
enviada no cabeçalho, mantida em variável de ambiente.

## Bases complementares, e por que cada uma é necessária

### Dados Abertos do CNPJ, da Receita Federal

Esta é a complementar indispensável, e a razão é o próprio nome do tema.

O PNCP entrega o CNPJ do fornecedor e para aí. Ele não tem quadro societário,
não tem sócio, não tem qualificação nem participação. Sem a base de CNPJ da
Receita Federal, o tema se reduz a Contratações Públicas e o termo Fornecedores
Societários fica sem lastro: não haveria como responder quem são as pessoas por
trás dos CNPJs que recebem recurso público, que é a pergunta central.

São três arquivos que interessam. O de sócios traz nome, qualificação, faixa
etária e CPF mascarado, chaveados pela raiz de oito dígitos do CNPJ. O de
empresas traz natureza jurídica, porte e capital social. O de estabelecimentos
traz CNAE, município e situação cadastral, e é o único que contém o CNPJ
completo de catorze dígitos.

O layout completo, com a ordem posicional das colunas e as armadilhas, está em
`docs/mapa-colunas-receita.md`.

### IBGE, base de nomes do Censo 2010

Necessária para a ODS 5. O registro societário não traz gênero, e o critério 4
do barema exige análise interseccional de gênero cruzado com raça ou cor. O
gênero precisa ser inferido, e a fonte oficial para isso é a frequência de
nomes por sexo do Censo 2010, exposta por API pública.

A regra de inferência e a taxa de indeterminados medida estão na RN-04 e em
`docs/fontes-genero-e-cor-raca.md`.

### IBGE, Censo 2022 via SIDRA

Necessária para a ODS 18, e é ela que permite endereçar cor e raça sem ferir a
LGPD.

Não existe base pública que ligue um CPF a uma declaração de cor ou raça, e é
bom que não exista, porque cor e raça são dado sensível pelo artigo 5 da LGPD.
A saída é a inferência ecológica: atribuir ao contexto territorial da empresa,
nunca à pessoa, a composição racial do município da sede, obtida do Censo.

Já baixada e implementada, com os 5.570 municípios.

### RAIS Vínculos, do Ministério do Trabalho

Complementa a anterior no eixo setorial. O Censo descreve quem mora no
município; a RAIS descreve quem trabalha formalmente naquele setor naquele
município. Cruzados, os dois eixos permitem afirmar que o recurso foi para
setores e territórios com determinada composição.

A escolha da RAIS em vez do Novo CAGED está justificada em
`docs/fontes-genero-e-cor-raca.md`: a RAIS é estoque e o CAGED é fluxo, e para
um proxy de composição fluxo é a métrica errada.

## Por que declarar isto explicitamente

Duas razões práticas.

A primeira é que a banca pode cruzar o guia com o repositório, ver quatro bases
onde o guia nomeia uma, e perguntar. Ter a justificativa escrita transforma o
que pareceria desvio em decisão metodológica.

A segunda é que a ausência da Receita Federal na lista oficial do guia é, muito
provavelmente, apenas concisão: o guia lista a fonte primária de cada tema, não
o conjunto completo. Mas quem lê não sabe disso, e a diferença entre uma base
acrescentada em silêncio e uma base acrescentada com motivo é exatamente o que
o critério de documentação avalia.

## Resumo

| base | papel | situação |
|---|---|---|
| PNCP | oficial do tema, fatos de contrato | coleta em andamento |
| Portal da Transparência (CGU) | oficial do tema, sanções CEIS e CNEP | extração em andamento |
| Receita Federal, CNPJ | complementar indispensável, quadro societário | download pendente |
| IBGE, nomes do Censo 2010 | complementar, inferência de gênero (ODS 5) | implementada e testada |
| IBGE, Censo 2022 via SIDRA | complementar, proxy territorial (ODS 18) | baixada, 5.570 municípios |
| RAIS Vínculos | complementar, proxy setorial (ODS 18) | localizada, download pendente |
