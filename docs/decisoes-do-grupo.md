# Decisões do grupo (1ª Unidade)

Registradas em 01/10/2026, sem reunião, para destravar os documentos. Ficam sujeitas à revisão do grupo; se alguma mudar, atualizar este arquivo, o `docs/5-vs.md` e o README no mesmo commit.

| # | Tema | Decisão | Motivo | Onde isso aparece |
| --- | --- | --- | --- | --- |
| D1 | Plano do banco | **Aiven free (1 GB).** Recomendação da professora. | O plano gratuito tem 1 GB de disco, 1 CPU e 1 GB de RAM, `max_connections` em 20 e sem pool de conexões. Só permite um serviço PostgreSQL por organização e pode ser desligado por falta de atividade (fonte: documentação da Aiven, "Aiven for PostgreSQL free tier"). | Argumento de Volume; `escolha-do-banco.md`; Terraform; plano B do pitch |
| D2 | O que vai para o banco | O Parquet nacional (2.023.134 contratos) **fica fora do Aiven**. O banco recebe uma fato reduzida (sem `objeto_contrato`, só colunas das RNs e dos KPIs, só contratos que passam no corte de sanidade) e as dimensões. O dashboard lê de agregados materializados. | Orçamento utilizável de 500 a 700 MB, já descontados índices e WAL. A fato nacional completa foi extrapolada em mais de 1 GB (extrapolação, não medição). | `5-vs.md` (Volume); Fase 2 |
| D3 | Corte de sanidade | **R$ 1 bi, marcando e não apagando** (coluna booleana de contrato suspeito). Na Fase 2, KPI 1 com o corte de R$ 1 bi e, como sensibilidade, com o de R$ 100 mi. | 243 contratos (0,012%) somam 95,77% do valor bruto. Os 1.189 contratos entre R$ 100 mi e R$ 1 bi (42% do que sobra) podem ter o mesmo erro, então a sensibilidade precisa existir. | `5-vs.md` (Veracidade); RN-02 |
| D4 | RN-03 | **Diretor, Presidente e Conselheiro entram como administradores**, e uma rodada de sensibilidade roda sem eles. | São quem administra a empresa, que é o que a RN-03 quer capturar. A sensibilidade mede quanto a escolha muda o resultado. | `classificar_empresas.py`; README (limitações) |
| D5 | Empresários individuais | **Universo declarado e separado, sem inferir pelo titular.** Publicar o tamanho (62.880, 26,2% do recorte nacional). | O titular não consta do quadro societário. Inferir pela razão social exigiria tratar nome de pessoa física a partir de outro campo, o que pesa na LGPD. Fica como extensão opcional da Fase 2. | RN-05; parecer de LGPD; README |
| D6 | RN-02 | Documentar o que está implementado (valor maior que zero) e o que está **pendente** (excluir anulados e cancelados, se o campo existir na coleta). Conferir 17.578 × 17.823 contratos com valor zero antes de citar qualquer um dos dois. | Evita afirmar no README uma regra que o código não cumpre. | `5-vs.md`; README |
| D7 | Data de referência | **Data de publicação no PNCP.** Declarar que 7,05% dos contratos têm `anoContrato` 2024. | A API consulta por data de publicação, e a diferença entre as duas datas é pequena. | README |
| D8 | Fonte do Censo para nomes | A definir, na mesma frase em todos os documentos. O roteiro cita o Censo 2010; o código usa a API v3 do Censo 2022. | Consistência entre README, 5 V's e parecer. | README; `5-vs.md`; parecer |

## Consequências práticas do banco gratuito

- **Conexões:** o limite é de 20 e não há pool. O Streamlit deve abrir uma conexão cacheada (`st.cache_resource`) e as consultas devem passar por `st.cache_data`.
- **Desligamento:** a Aiven pode desligar o serviço sem atividade, com aviso. Religar e testar na véspera e uma hora antes da apresentação.
- **Plano B:** capturas de tela de cada interação do dashboard em slide oculto.
- **Terraform:** o plano e a nuvem do `.tf` precisam ser os do plano gratuito, e só pode existir um serviço PostgreSQL na organização. O serviço criado no console na S1 precisa ser apagado ou importado.