# Parecer de LGPD e dados abertos

Rascunho para revisão do grupo · referência 01/10/2026 · números conforme `docs/5-vs.md`.

Este parecer é um argumento técnico e acadêmico, não uma opinião jurídica. As referências legais devem ser conferidas por quem revisar (marcadas com `[CONFIRMAR]`).

## 1. O que o projeto trata e o que é dado pessoal

| Dado | Origem | Natureza | Tratamento no projeto |
| --- | --- | --- | --- |
| Nome do sócio, CPF mascarado, qualificação, faixa etária | Receita Federal (quadro societário) | Pessoal, de acesso público | Usado só na camada de processamento. Na apresentação, o nome é substituído por identificador derivado. |
| Razão social e CNPJ de fornecedor pessoa jurídica | PNCP, Receita | Não pessoal | Exibido. Exceção: empresário individual (ver seção 5). |
| Nome e CPF de fornecedor pessoa física | PNCP | Pessoal | 74.433 contratos (3,7%). Ficam fora da inferência de gênero e não são exibidos com nome. |
| Gênero do sócio | Inferido pelo primeiro nome | Pessoal derivado, probabilístico | Classificado como F, M ou indeterminado (RN-04). Publicado só como agregado por empresa. |
| Cor/raça | Censo 2022 (agregado por município) | Sensível (LGPD, art. 5º, II), mas só em forma agregada | Nunca atribuída a pessoa. Só descreve território e setor (RN-06). |

Observação de rigor: gênero não consta do rol de dados sensíveis do art. 5º, II da LGPD (origem racial ou étnica, saúde, vida sexual, etc.). Mesmo assim o tratamos com a mesma cautela, porque é uma inferência sobre pessoa identificável e pode estar errada. Quem sustentar na banca que "gênero também é sensível" estará errado; o argumento correto é o dos princípios do art. 6º (finalidade, necessidade, não discriminação).

## 2. Base legal e de publicidade

a) **Os dados são públicos por determinação legal.** O PNCP publica contratos sob a Lei 14.133/2021; o quadro societário é divulgado nos Dados Abertos do CNPJ, no âmbito da Lei de Acesso à Informação (Lei 12.527/2011) e da Política de Dados Abertos (Decreto 8.777/2016) `[CONFIRMAR artigos]`.

b) **Dado público não é dado livre de regras.** O art. 7º, §3º da LGPD exige que o tratamento de dado de acesso público respeite a finalidade, a boa-fé e o interesse público que justificaram sua disponibilização, e o §7º permite novas finalidades desde que legítimas e específicas, com preservação dos direitos do titular `[CONFIRMAR]`. Nossa finalidade (controle social do gasto público e análise de equidade) é compatível com a finalidade original da publicidade.

c) **Finalidade acadêmica.** O trabalho se enquadra no art. 4º, II, "b" da LGPD (fins exclusivamente acadêmicos, com aplicação dos arts. 7º e 11) `[CONFIRMAR]`. Não tratamos isso como licença geral: adotamos as medidas da seção 4 como se a lei se aplicasse integralmente.

## 3. As três decisões de proteção

1. **Só agregados são publicados.** O dashboard mostra resultados por empresa, setor, órgão e território. Nenhuma tela exibe o gênero ou o nome de um sócio individual.
2. **Nome de sócio é dado pessoal mesmo sendo público.** Por isso é mascarado na exibição e substituído por identificador derivado.
3. **Cor/raça não é inferida no nível individual.** Esta é a decisão que sustenta toda a escolha do Caminho A.

## 4. O caminho de cor/raça: o que adotamos e o que rejeitamos

**Caminho A, adotado: proxy ecológico.** Atribuímos à empresa a composição racial do município da sede (Censo 2022, SIDRA) e, na Fase 2 e se houver tempo, a da força de trabalho do setor CNAE (RAIS ou Novo CAGED). O indicador diz para onde o dinheiro público flui em termos de território e setor, e não diz nada sobre o dono. A limitação (falácia ecológica) é declarada: um município de maioria negra não implica empresa de dono negro.

**Caminho B, não explorado nesta etapa: recorte de política pública.** Contratos com cláusula de cota ou preferência trariam dado direto, mas com cobertura pequena. Fica registrado como extensão possível.

**Caminho C, considerado e rejeitado: cruzar nome de sócio com base de raça autodeclarada** (por exemplo, a de candidaturas do TSE). Rejeitamos por cinco razões:

- **Finalidade incompatível.** Os dados do TSE foram publicados para transparência eleitoral, não para classificar a raça de fornecedores do Estado (art. 6º, I; art. 7º, §3º).
- **Dado sensível.** O resultado seria uma inferência de origem racial ou étnica sobre pessoa identificável (art. 5º, II e art. 11), sem consentimento e sem hipótese legal clara.
- **Reidentificação.** Ligar duas bases por nome atribui a uma pessoa um atributo que ela declarou em outro contexto.
- **Homonímia e erro.** Nome não identifica pessoa: cruzar por nome gera falsos pares, e o erro recairia sobre terceiros inocentes, em tema discriminatório (art. 6º, IX).
- **Autodeclaração vira heteroatribuição.** A raça declarada por uma pessoa em uma candidatura passaria a ser atribuída por nós a outra, sem que ela soubesse.

Abrir mão do Caminho C custa precisão individual, que o projeto não precisa para responder suas perguntas.

## 5. Medidas técnicas

| Medida | Onde está |
| --- | --- |
| CPF nunca armazenado nem exibido na camada de apresentação (RN-09) | `[CONFIRMAR: a máscara do CPF da Receita é guardada em algum lugar? Se sim, ajustar o texto de RN-09]` |
| Identificador derivado do sócio: hash de nome + máscara, com sal guardado em segredo, nunca a máscara sozinha (ela colide: 169.762 pessoas distintas por máscara contra 195.748 por máscara + nome, em 200 mil linhas de `Socios1.zip`) | `[PROPOSTA]` a implementar na carga |
| Saída da inferência de gênero sem nome completo (só primeiro nome, no cache de classificação) | `inferir_genero.py` |
| Mínimo de agregação: nenhum recorte exibe resultado com menos de 5 sócios ou 5 empresas (RN-09) | Fase 2, painel |
| Fornecedor pessoa física: sem nome no painel | Fase 2, painel |
| Empresário individual: a razão social costuma conter o nome do titular e dígitos do CPF; mascarar no último nível do drill-down | `[CONFIRMAR no dado]`; Fase 2, painel |
| Segredos (token da Aiven, chave do Portal da Transparência) fora do repositório | `.env`, `.gitignore`, GitHub Secrets |
| Dado bruto e CSV de auditoria locais, fora do Git | `.gitignore` |

## 6. Limites e riscos residuais

- **Inferência de gênero é probabilística.** Taxa de indeterminados no recorte nacional: 4,0% dos 327.180 sócios pessoa física elegíveis. Pela RN-05, só 54,9% das empresas têm controle definido. Os 30,4% de controle feminino contam empresas, não valor.
- **Contagem por cabeça.** O percentual de participação de cada sócio não consta dos dados abertos; é a principal limitação metodológica.
- **Reidentificação por combinação.** Agregados pequenos podem expor indivíduos; daí o mínimo de cinco da RN-09. Vale o mesmo princípio que o IBGE aplica ao suprimir nomes com poucas ocorrências.
- **Risco reputacional.** O Projeto indica concentração e padrões; não afirma irregularidade de nenhuma empresa ou pessoa. A marcação de sanção (RN-08) usa a data de assinatura para não acusar contratos anteriores à sanção.

## 7. Resposta curta para a banca

> Não sabemos o gênero de um sócio: inferimos pelo primeiro nome, com limiar de 90%, e classificamos como indeterminado o que não atinge o limiar. Não inferimos cor/raça de pessoa nenhuma, porque é dado sensível; atribuímos o contexto do território e do setor. Avaliamos cruzar nomes com bases de raça autodeclarada e descartamos, por ser reidentificação.

## 8. Para fechar antes de entregar

- Conferir as referências marcadas `[CONFIRMAR]`.
- Decidir o texto de RN-09 sobre a máscara do CPF (armazenada ou não).
- Verificar no dado se a razão social dos empresários individuais traz nome e dígitos do CPF.
- Alinhar com a T3 a fonte dos nomes: o roteiro cita o Censo 2010, o código usa a API v3 do Censo 2022. O README e este parecer devem dizer a mesma coisa.