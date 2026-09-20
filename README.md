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
* Estruturado: 
* Semi-estruturado: 
* Não estruturado: 

## 3. Os 5 V's aplicados ao Dataset
*(A ser preenchido na Semana 2 com os números reais do inventário da Trilha 2)*
* Volume: 
* Velocidade: 
* Variedade: 
* Veracidade: 
* Valor: 

## 4. Arquitetura e Justificativa (Relacional vs. Não Relacional)
*(A ser preenchido na Semana 3 com base no teste comparativo de tempos e no modelo estrela proposto)*

## 5. Limpeza e Tratamento (ETL) e Dicionário de Dados
*(A ser preenchido ao longo da Fase 2)*

## 6. Regras de Negócio
*(A ser preenchido iterativamente pela Trilha 3 na Fase 2)*
* RN-01 a RN-09...

## 7. Infraestrutura, Deploy e IaC
*(A ser preenchido pela Trilha 1 detalhando o uso do Terraform e Aiven)*

## 8. Guia de Reprodução
*(A ser preenchido na Semana 6 da Fase 2)*
