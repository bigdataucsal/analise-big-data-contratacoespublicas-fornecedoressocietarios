# Big Data e Analytics — Tema 9: Contratações Públicas e Fornecedores Societários

*Repositório destinado ao projeto prático da disciplina de Big Data e Analytics. Este documento está em construção e será preenchido iterativamente ao longo das fases do projeto.*

## 1. Problema de Negócio e Parecer de LGPD

### O Problema Analítico
*(A ser preenchido pela Trilha 3 após a definição das 2 ou 3 perguntas exatas e do recorte final)*

### Parecer de Conformidade: LGPD e Dados Abertos
O presente projeto utiliza estritamente dados governamentais abertos, em conformidade com o Decreto 8.777/2016 e a Lei de Acesso à Informação (LAI). Para garantir a conformidade com a Lei Geral de Proteção de Dados (LGPD), adotamos as seguintes diretrizes:

1. **Dados Pessoais (Art. 5º, I):** Embora o nome de sócios e seus CPFs (parcialmente mascarados na origem) sejam públicos, eles constituem dados pessoais. No nosso pipeline, o CPF nunca é armazenado em texto claro no painel final e não é exibido. O nome do sócio é substituído por um identificador derivado na camada de apresentação, e o dashboard aplica um limite mínimo de agregação (nunca exibindo resultados baseados em menos de 5 empresas ou sócios), impedindo a reidentificação direta.
2. **Dados Sensíveis (Cor/Raça - Art. 5º, II):** A cor e raça são dados sensíveis. Avaliamos e **rejeitamos ativamente** o cruzamento do nome dos sócios com bases que contêm raça autodeclarada (ex.: TSE), pois essa prática configuraria reidentificação ilegal de dado sensível.
3. **Solução Adotada (Proxy Ecológico):** Para endereçar a ODS 18 sem ferir a LGPD, utilizamos inferência ecológica. O indicador de cor/raça não é atribuído ao indivíduo (sócio), mas sim ao *contexto territorial e setorial da empresa* (via Censo do IBGE e RAIS). O indicador final relata para quais perfis demográficos de municípios e setores os recursos públicos fluem, mantendo o nível de análise estritamente macro.

---

## 2. Ingestão e Classificação dos Tipos de Dado
*(A ser preenchido na Semana 2 pelas Trilhas 2 e 4)*

> Material pronto da Trilha 3: [docs/lista-colunas-uteis.md](docs/lista-colunas-uteis.md), a lista consolidada de colunas com a fonte de cada uma e a pergunta que atende; [docs/tipos-de-dado.md](docs/tipos-de-dado.md), com um trecho real colado de cada variedade; e [docs/bases-utilizadas.md](docs/bases-utilizadas.md), que declara a base oficial do tema e justifica cada base complementar.
* Estruturado: 
* Semi-estruturado: 
* Não estruturado: 

## 3. Os 5 V's aplicados ao Dataset
*(A ser preenchido na Semana 2 com os números reais do inventário da Trilha 2)*

> Material pronto da Trilha 3: [docs/5-vs.md](docs/5-vs.md), com todos os números medidos contra os dados do projeto.
* Volume: 
* Velocidade: 
* Variedade: 
* Veracidade: 
* Valor: 

## 4. Arquitetura e Justificativa (Relacional vs. Não Relacional)
*(A ser preenchido na Semana 3 com base no teste comparativo de tempos e no modelo estrela proposto)*

> Material pronto da Trilha 3: [docs/escolha-do-banco.md](docs/escolha-do-banco.md) e o modelo em [etl/schema_estrela.sql](etl/schema_estrela.sql). Falta o tempo do PostgreSQL, que é medição da Trilha 1.

## 5. Limpeza e Tratamento (ETL) e Dicionário de Dados
*(A ser preenchido ao longo da Fase 2)*

> Material pronto da Trilha 3: [docs/dicionario-de-dados.md](docs/dicionario-de-dados.md), cobrindo as dez tabelas do modelo estrela. As colunas que vêm da Receita Federal estão descritas pelo layout oficial e marcadas como pendentes até o download concluir.

## 6. Regras de Negócio
*(A ser preenchido iterativamente pela Trilha 3 na Fase 2)*

> [docs/regras-de-negocio.md](docs/regras-de-negocio.md): RN-01 a RN-09 escritas, cada uma com enunciado, justificativa e o número medido que a sustenta.

## 7. Infraestrutura, Deploy e IaC
A infraestrutura de dados do projeto foi projetada com foco em automação, reprodutibilidade e gestão rigorosa de credenciais.

Banco de Dados em Nuvem: O serviço adotado foi o PostgreSQL hospedado na plataforma Aiven. A escolha justifica-se pela alta disponibilidade e suporte nativo a ferramentas de automação de infraestrutura.

Infrastructure as Code (IaC): O provisionamento do banco de dados não ocorreu de forma manual. Todo o ambiente foi automatizado utilizando Terraform. Os manifestos de configuração (main.tf, variables.tf e outputs.tf) encontram-se no diretório /terraform. O arquivo .terraform.lock.hcl foi versionado para garantir o congelamento das versões de provedor, garantindo reprodutibilidade em qualquer máquina.

Segurança e Gestão de Segredos: Para atender aos critérios de segurança da informação, aplicamos as seguintes diretrizes:

Nenhuma credencial sensível, como chaves de API (AIVEN_API_TOKEN) ou URLs de conexão com senha (DATABASE_URL), é exposta no repositório. Elas são gerenciadas exclusivamente via variáveis de ambiente.

O arquivo .env contendo dados reais e os arquivos de estado do Terraform (.terraform.tfstate), que poderiam vazar a estrutura da nuvem, estão rigidamente bloqueados pelo .gitignore.

Fornecemos um arquivo .env.example na raiz do projeto como um template seguro (sem valores preenchidos), servindo de manual de integração para que a equipe configure os seus ambientes locais de forma padronizada.

## 8. Guia de Reprodução
*(A ser preenchido na Semana 6 da Fase 2)*
