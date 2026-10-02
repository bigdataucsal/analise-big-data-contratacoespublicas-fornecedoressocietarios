# Big Data e Analytics — Tema 9: Contratações Públicas e Fornecedores Societários

Repositório destinado ao projeto prático da disciplina de Big Data e Analytics. Este projeto mapeia quem são as pessoas físicas por trás dos CNPJs que recebem recursos públicos federais, analisando potenciais assimetrias no controle do fornecimento ao Estado.


---

## 1. Problema de Negócio e Parecer de LGPD

### O Problema Analítico
O Estado é o maior comprador do país, mas as bases de contratação pública não revelam quem são os donos do dinheiro que flui para os CNPJs fornecedores. Nosso pipeline cruza os contratos federais com o quadro societário da Receita Federal para responder:
1. **Assimetria de Gênero:** Qual a proporção do valor contratado que vai para empresas de controle feminino comparado à proporção do número de contratos?
2. **Concentração Societária:** Quantos sócios físicos controlam a maior parte do valor contratado através de múltiplas empresas?
3. **Camada Interseccional:** Os setores e territórios onde empresas de controle feminino capturam mais recursos são os mesmos com maior presença de trabalhadores negros?

### Parecer de Conformidade: LGPD e Dados Abertos
O projeto utiliza estritamente dados governamentais abertos. Para garantir conformidade com a LGPD:
* O CPF não é armazenado em texto claro e aplicamos agregação mínima nos dashboards.
* **Solução Adotada (Proxy Ecológico):** Rejeitamos o cruzamento nominal com bases de raça autodeclarada. O indicador racial é atribuído ao *contexto da empresa* (município e setor), mapeando para onde o recurso flui, não a cor do indivíduo. *(Documentação completa: `docs/parecer-lgpd.md`)*

---

## 2. Estrutura do Repositório

O projeto está modularizado nas seguintes pastas principais:

* `docs/`: Documentação de regras de negócio, dicionários de dados, justificativas arquiteturais e evidências.
* `etl/`: Scripts de extração, tratamento, carga (Python) e modelagem do banco (SQL)[cite: 1].
* `terraform/`: Infraestrutura como Código (IaC) para provisionamento do banco de dados na nuvem[cite: 1].
* `dashboard/`: Arquivos relativos à visualização de dados (em desenvolvimento)[cite: 1].

---

## 3. Pipeline de Dados (ETL)

Nossa engenharia de dados lida com a redução drástica de volume e tratamento de arquivos estruturados, semi-estruturados e não estruturados[cite: 1]. Os scripts estão organizados na pasta `etl/`[cite: 1]:

**Ingestão de Dados:**
* `baixar_pncp.py` / `baixar_pncp_rapido.py`: Consumo da API do Portal Nacional de Contratações Públicas[cite: 1].
* `baixar_receita.py`: Download e filtragem dos dados abertos de CNPJs[cite: 1].
* `baixar_transparencia.py` e `baixar_proxy_racial.py`: Consumo de bases complementares[cite: 1].

**Transformação e Limpeza:**
* `tratar_contratos.py` e `recorte_cnpjs.py`: Limpeza de texto, normalização e filtragem do escopo[cite: 1].
* `classificar_empresas.py` e `inferir_genero.py`: Aplicação das regras de negócio de diversidade[cite: 1].
* `traduzir_municipios.py`: Padronização geográfica[cite: 1].

**Testes e Auditoria:**
* `diagnostico_valores.py` e `auditar_extremos.py`: Validação de outliers e veracidade de valores[cite: 1].
* `perfil_veracidade.py` e `verificar_pncp.py`: Checagem da integridade dos contratos[cite: 1].
* `benchmark_banco.py` e `comparar_pandas_postgres.py`: Testes de performance arquitetural[cite: 1].

---

## 4. Banco de Dados e Modelagem

Optamos por um banco de dados **Relacional (PostgreSQL via Aiven)** estruturado em um modelo multidimensional (Estrela), ideal para responder à relação *muitos-para-muitos* entre CNPJs e Sócios. 

* 📄 **Esquema SQL (PostgreSQL):** `etl/schema_postgres.sql`[cite: 1]
* 📄 **Modelo Estrela (Fato/Dimensão):** `etl/schema_estrela.sql`[cite: 1]
* ⚙️ **Carga:** `etl/carregar_aiven.py`[cite: 1]
* 📖 **Dicionário de Dados:** `docs/dicionario-de-dados.md`[cite: 1]

---

## 5. Documentação Técnica e Regras de Negócio

Todo o embasamento metodológico e de negócio está documentado na pasta `docs/`[cite: 1]:
* 📐 `regras-de-negocio.md` e `decisoes-do-grupo.md`: Mapeamento das regras estritas (ex: Regra de Receita vs Despesa)[cite: 1].
* 📊 `5-vs.md` e `tipos-de-dado.md`: Comprovação das características de Big Data do projeto[cite: 1].
* 🏛️ `arquitetura.md` e `escolha-do-banco.md`: Justificativa do uso de relacional vs colunar[cite: 1].
* 📋 `mapa-colunas-receita.md` e `lista-colunas-uteis.md`: De-Para das fontes de dados[cite: 1].

---

## 6. Infraestrutura e Segurança (IaC)

A infraestrutura do banco de dados em nuvem é provisionada de forma automatizada.
* **Ferramenta:** Arquivos localizados na pasta `terraform/` (`main.tf`, `variables.tf`, `outputs.tf`)[cite: 1].
* **Provider:** Aiven (PostgreSQL).
* **Segurança:** O arquivo de estado `.tfstate`, os arquivos `.env` e os exemplos como `terraform.tfvars.example`[cite: 1] e `.env.example`[cite: 1] garantem que credenciais nunca sejam expostas no versionamento.
