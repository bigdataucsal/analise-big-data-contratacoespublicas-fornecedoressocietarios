# Big Data e Analytics — Tema 9: Contratações Públicas e Fornecedores Societários

Repositório destinado ao projeto prático da disciplina de Big Data e Analytics. Este projeto mapeia quem são as pessoas físicas por trás dos CNPJs que recebem recursos públicos federais, analisando potenciais assimetrias no controle do fornecimento ao Estado.


---

## 1. Problema de Negócio e Escopo

### O Problema Analítico
O Estado é o maior comprador do país, mas as bases de contratação pública não revelam quem são os donos do dinheiro que flui para os CNPJs fornecedores. Nosso pipeline cruza os contratos federais com o quadro societário da Receita Federal para responder:
1. **Assimetria de Gênero:** Qual a proporção do valor contratado que vai para empresas de controle feminino comparado à proporção do número de contratos?
2. **Concentração Societária:** Quantos sócios físicos controlam a maior parte do valor contratado através de múltiplas empresas?
3. **Camada Interseccional:** Os setores e territórios onde empresas de controle feminino capturam mais recursos são os mesmos com maior presença de trabalhadores negros?

### Recorte da Análise (Atualizado)
* **Cobertura:** Nacional, englobando todo o ano de **2025** (substituindo o escopo inicial de apenas 50 órgãos).
* **Contratos:** 100% dos dados foram conferidos contra a API, totalizando a extração de **2.023.134 contratos**.
* **Receita Federal:** Base de dados utilizada com data de competência em **14/09/2026**.

### Parecer de Conformidade: LGPD e Dados Abertos
O projeto utiliza estritamente dados governamentais abertos. Para garantir conformidade com a LGPD, o CPF não é armazenado em texto claro e aplicamos agregação mínima nos dashboards. Adotamos a solução de **Proxy Ecológico** para o recorte racial, atribuindo o indicador ao contexto da empresa (município e setor), sem cruzamento nominal.

---

## 2. Estrutura do Repositório

O projeto está modularizado nas seguintes pastas principais:
* `docs/`: Documentação de regras de negócio, dicionários de dados, justificativas arquiteturais e evidências.
* `etl/`: Scripts de extração, tratamento, carga (Python) e modelagem do banco (SQL).
* `terraform/`: Infraestrutura como Código (IaC) para provisionamento do banco de dados na nuvem (aguardando confirmação do `plan` pela T1).
* `dashboard/`: Arquivos relativos à visualização de dados (em desenvolvimento).

---

## 3. Pipeline de Dados (ETL) e Volumetria

Nossa engenharia de dados lida com a redução drástica de volume e tratamento de arquivos estruturados e semi-estruturados.

**Ingestão e Volumetria:**
* **Contratos (PNCP):** A coleta dos 2.023.134 contratos totalizou **3,62 GB** de dados brutos (`baixar_pncp.py`).
* **Sócios e CNPJs (Receita):** A base original de 28,67 GB foi reduzida no parser para apenas **69,05 MB** (`baixar_receita.py`), mantendo **0,59%** das linhas úteis relativas ao nosso escopo.

**Performance de Transformação:**
* Nos benchmarks executados, o motor colunar demonstrou ser de **25 a 48 vezes mais rápido** que o processamento tradicional em Pandas.

---

## 4. Banco de Dados e Modelagem

Optamos por um banco de dados **Relacional (PostgreSQL via Aiven)** estruturado em um modelo multidimensional (Estrela), ideal para responder à relação *muitos-para-muitos* entre CNPJs e Sócios. 

* **Armazenamento Fato:** A tabela fato inteira cabe no PostgreSQL, ocupando apenas **177 MB** sem índices.
* **Estratégia de BI:** Como a consulta pesada na base inteira derrubou o nó gratuito da Aiven, a arquitetura do painel foi adaptada para ler exclusivamente **agregados materializados**.
* **Arquivos-chave:** `etl/schema_postgres.sql` e `etl/schema_estrela.sql`.

---

## 5. Documentação Técnica e Regras de Negócio

Todo o embasamento técnico e metodológico está consolidado na pasta `docs/`:
* 📊 `docs/5-vs.md` e `docs/tipos-de-dado.md`: Comprovação das características de Big Data.
* 🏛️ `docs/escolha-do-banco.md`: Justificativa do relacional e comparativo de performance entre Pandas, DuckDB e PostgreSQL.
* 📐 `docs/arquitetura.md`: Diagrama de arquitetura em Mermaid (pronto para exportação para os slides).
* ⚙️ `docs/runbook-banco.md` e `docs/parser-receita.md`: Manuais de operação do banco e extração dos CNPJs.
* ⚖️ `docs/parecer-lgpd.md` e `docs/decisoes-do-grupo.md`: Governança de dados e regras estritas do negócio.
* 📂 `docs/evidencias/`: Diretório contendo os benchmarks nos três volumes, a documentação da falha de 2 milhões, o print da Aiven e o manifesto da Receita.

---

## 6. Infraestrutura e Segurança (IaC)

A infraestrutura na Aiven é provisionada via Terraform. 
* **Segurança:** Nenhuma credencial é exposta no repositório. Arquivos como `.env`, `.terraform.tfstate`, `terraform.tfvars` e a URI do banco de dados são estritamente proibidos no versionamento do projeto.
