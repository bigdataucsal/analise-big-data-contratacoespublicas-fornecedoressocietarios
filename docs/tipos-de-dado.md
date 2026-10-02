# Classificação dos tipos de dado

Entrega da 1ª Unidade. Referência: 01/10/2026. Os trechos abaixo são reais: foram extraídos dos arquivos do projeto por `etl/exemplos_tipos.py` e estão em `docs/evidencias/exemplos_tipos.txt`. Os números vêm de `docs/5-vs.md`.

O projeto reúne as três variedades sem forçar nenhuma delas, e cada uma exige um tratamento diferente.

| Tipo | Fonte | Formato | Volume medido | Tratamento |
| --- | --- | --- | --- | --- |
| Estruturado | CSV da Receita Federal (empresas, estabelecimentos, sócios, Simples) | CSV sem cabeçalho, separador `;`, codificação latina, dentro de ZIP | 28,67 GB descompactados (7,76 GB em ZIP); 222,2 milhões de linhas lidas | Leitura em blocos, filtro por raiz de CNPJ, Parquet filtrado (69,05 MB) |
| Semiestruturado | JSON da API do PNCP (e do IBGE) | JSON, uma linha por contrato (NDJSON) | 2.023.134 contratos, 3,62 GB | Achatamento dos objetos aninhados, Parquet tratado (254,1 MB, 50 colunas) |
| Não estruturado | Campo `objetoContrato` do PNCP | Texto livre em português | 334,6 MB; média de 160 e máximo de 5.120 caracteres | Fica no Parquet; busca textual é escopo condicional da Fase 2 |

## 1. Estruturado: o quadro societário da Receita

Três linhas reais do arquivo de sócios (`Socios0.zip`), com a raiz do CNPJ, o nome do sócio e os dígitos do CPF mascarados:

```
"12******";"2";"ZENIRA D. S. M.";"***XXXXXX**";"22";"20100805";"";"***000000**";"";"00";"6"
"12******";"2";"DJANIRA Z. M.";"***XXXXXX**";"22";"20170809";"";"***000000**";"";"00";"9"
"12******";"2";"LENICE M.";"***XXXXXX**";"49";"20190205";"";"***000000**";"";"00";"7"
```

Colunas, na ordem do dicionário da Receita: `cnpj_basico; identificador_de_socio; nome_do_socio; cnpj_cpf_do_socio; qualificacao; data_entrada; pais; representante_legal; nome_representante; qualificacao_representante; faixa_etaria`.

**Por que é estruturado.** O esquema é fixo: todo registro tem as mesmas onze colunas, na mesma ordem, com significado e domínio definidos em documento oficial (o PDF de metadados e as tabelas de domínio). Não existe campo opcional que muda de registro para registro.

**Estruturado não quer dizer limpo.** O que vimos de armadilha no arquivo real:

- Não há linha de cabeçalho. A ordem das colunas só existe no PDF de metadados, e é a primeira coisa que o parser precisa saber.
- O separador é `;`, os campos vêm entre aspas, a codificação é latina e a data vem como `AAAAMMDD`, sem hífen.
- O CPF vem mascarado (`***XXXXXX**`, aqui com os dígitos trocados por `X` por nossa causa). A máscara colide: em 200 mil linhas de `Socios1.zip` (amostra, não aleatória), há 169.762 pessoas físicas distintas por máscara contra 195.748 por máscara mais nome. Por isso a chave do sócio é nome mais máscara, nunca a máscara sozinha.
- Quando não há representante legal, as colunas do representante vêm com valor de preenchimento (`***000000**` e qualificação `00`), e não vazias. Os campos `pais` e `nome_representante` são 99,71% e 98,19% nulos na mesma amostra.
- Os códigos de qualificação (`22`, `49`), o identificador de sócio (`2`) e a faixa etária (`6`, `9`, `7`) só fazem sentido com a tabela de domínio. `[CONFIRMAR: preencher as descrições a partir de qualscsv.parquet e do PDF de metadados]`.

**Tratamento.** O arquivo é lido sem extrair o ZIP, com nomes de coluna explícitos, todos os campos como texto (o CNPJ e o CPF nunca viram número) e em blocos. O filtro mantém só as raízes de CNPJ que aparecem em contratos: das 28.341.092 linhas de sócios, ficam 339.385. A chave de junção com a empresa é a **raiz de 8 dígitos**, nunca o CNPJ de 14.

## 2. Semiestruturado: o contrato do PNCP

Um contrato real da coleta, com campos aninhados e vários campos opcionais vazios:

```json
{
  "numeroControlePncpAta": null,
  "codigoPaisFornecedor": null,
  "orgaoEntidade": {
    "cnpj": "00394460005887",
    "razaoSocial": "MINISTERIO DA ECONOMIA",
    "poderId": "E",
    "esferaId": "F"
  },
  "anoContrato": 2024,
  "sequencialContrato": 7096,
  "tipoContrato": {
    "id": 1,
    "nome": "Contrato (termo inicial)"
  },
  "numeroContratoEmpenho": "0900100/3166",
  "categoriaProcesso": {
    "id": 11,
    "nome": "Alienação de bens móveis/imóveis"
  },
  "tipoPessoa": "PJ",
  "niFornecedor": "06121879000106",
  "nomeRazaoSocialFornecedor": "IMPERIO TRANSPORTES TURISTICOS LTDA",
  "tipoPessoaSubContratada": null,
  "niFornecedorSubContratado": null,
  "nomeFornecedorSubContratado": null,
  "objetoContrato": "Alienação de mercadorias apreendidas pela Receita Federal",
  "valorInicial": 7000.0,
  "valorParcela": 7000.0,
  "valorGlobal": 7000.0,
  "valorAcumulado": null,
  "dataAssinatura": "2024-12-31",
  "dataVigenciaInicio": "2024-12-31",
  "dataVigenciaFim": "2025-01-30",
  "identificadorCipi": null,
  "urlCipi": null,
  "unidadeOrgao": {
    "ufNome": "Paraná",
    "ufSigla": "PR",
    "municipioNome": "Curitiba",
    "codigoIbge": "4106902",
    "codigoUnidade": "900100",
    "nomeUnidade": "Superintendência Regional da Receita Federal do Brasil da 9ª Região Fiscal"
  },
  "dataPublicacaoPncp": "2025-01-01T00:30:03",
  "dataAtualizacaoGlobal": "2025-01-01T00:30:03",
  "dataAtualizacao": "2025-01-01T00:30:03",
  "emendaParlamentar": null,
  "processo": "10905720159202490",
  "informacaoComplementar": null,
  "orgaoSubRogado": null,
  "unidadeSubRogada": null,
  "receita": true,
  "numeroParcelas": 1,
  "numeroRetificacao": 0,
  "temRemanejamento": null,
  "frutoAdesao": null,
  "numeroControlePNCP": "00394460005887-2-007096/2024",
  "usuarioNome": "Ministério da Fazenda / Receita Federal",
  "numeroControlePncpCompra": "00394460005887-1-000067/2024"
}
```

**Por que é semiestruturado.** Há estrutura, mas ela não é plana nem rígida:

- **Aninhamento.** Quatro campos são objetos: `orgaoEntidade`, `tipoContrato`, `categoriaProcesso` e `unidadeOrgao`. Os dois do meio seguem o padrão código mais descrição, o que os torna candidatos naturais a tabelas de dimensão.
- **Campos opcionais.** O registro tem 41 campos de topo, e muitos vêm `null` (`numeroControlePncpAta`, `codigoPaisFornecedor`, dados de subcontratada, `valorAcumulado`). Outros nem sempre existem: `orgaoSubRogado` e `unidadeSubRogada` aparecem em 0,31% dos contratos do ano. Cada registro traz o que tem.
- **Convenções mistas.** Datas ora são só data (`2024-12-31`), ora data e hora sem fuso (`2025-01-01T00:30:03`). Valores monetários são números de ponto flutuante (`7000.0`). A caixa das chaves não é uniforme: `numeroControlePncpAta`, `numeroControlePncpCompra` e `numeroControlePNCP` (esta última é a chave de deduplicação).
- **O nome do campo no dado real difere do roteiro.** O tipo de pessoa do fornecedor vem como `tipoPessoa` (PJ, PF ou PE), não `tipoPessoaFornecedor`.

O registro também ilustra a decisão de data de referência: é um contrato com `anoContrato` 2024, assinado em 31/12/2024 e publicado em 01/01/2025. Como a consulta é por data de publicação, ele entra no recorte de 2025 (no ano inteiro, 7,05% dos contratos publicados têm `anoContrato` 2024).

**Tratamento.** O bruto é guardado como veio, em NDJSON (3,62 GB). O tratamento achata os objetos aninhados em colunas, padroniza os nomes para `snake_case`, converte valores para decimal de duas casas, mantém CNPJ como texto e deduplica pela chave `numeroControlePNCP` (nenhuma duplicata nos 2.023.134 contratos). O resultado é um Parquet de 50 colunas e 254,1 MB, e é dele que saem as dimensões do modelo estrela.

Outras respostas JSON do projeto têm o mesmo caráter: a API de nomes do IBGE (v3, uma chamada por nome; 28.048 primeiros nomes distintos classificados) e a API de agregados do SIDRA (tabela 9605, composição de cor ou raça de 5.570 municípios, obtida em 4 segundos).

## 3. Não estruturado: o objeto do contrato

Três exemplos reais do campo `objetoContrato`:

1. `Contratação de empresa para a prestação dos serviços de publicação de extrato de licitações e avisos em jornal de grande circulação, sob demanda.`
2. `Contratação de empresa para execução dos serviços de pavimentação em pedra tosca na Localidade de Pé da Serra, zona rural, junto a Secretaria de Obras, Infraestrutura e Urbanismo do Município de Uruburetama.`
3. `CREDENCIAMENTO MEDICO ESPECIALIZADOS NA ÁREA DE GINECOLOGIA, OBSTETRICIA E PEDIATRIA, AFIM DE GARANTIR UM ATENDIMENTO DE QUALIDADE AOS USUARIOS DO SUS.`

**Por que é não estruturado.** O campo é texto livre em português, sem esquema, sem vocabulário controlado e sem padronização, e a informação que interessa (o tipo de serviço, a localidade, o programa) está dentro da frase, não em campos separados. Os três exemplos mostram a falta de padrão:

- **Caixa e acentuação inconsistentes.** Os dois primeiros são caixa mista com acento; o terceiro vem todo em maiúsculas e em parte sem acento (`MEDICO`, `OBSTETRICIA`, `USUARIOS`), mas com acento em `ÁREA`.
- **Erro de grafia e de concordância.** `AFIM DE` no lugar de `A FIM DE`, e `MEDICO ESPECIALIZADOS`, com singular e plural misturados (o esperado seria `MÉDICOS ESPECIALIZADOS`).
- **Entidades misturadas ao texto.** Localidade, município e secretaria aparecem no meio da frase.

Em números, no ano inteiro: média de 160 caracteres, máximo de 5.120, e 1,11% dos objetos com menos de 15 caracteres. O campo soma 334,6 MB.

**Tratamento.** Para busca e contagem de termos, o texto é normalizado (minúsculas, sem acento, sem espaços duplos), a mesma regra aplicada aos nomes de sócios. Ele não vai para o PostgreSQL: o campo e um índice de busca textual passariam, juntos, de todo o orçamento utilizável do banco gratuito (ver `docs/escolha-do-banco.md`). Permanece no Parquet e, se houver tempo na Fase 2, é indexado em um motor de busca. No painel, o texto aparece no último nível do drill-down, do setor ao órgão ao contrato individual.

## Como os tipos se conectam no pipeline

| Entrada | Saída | O que acontece |
| --- | --- | --- |
| JSON do PNCP (semiestruturado) | Parquet com colunas (estruturado) | Achatamento e tipagem |
| CSV da Receita (estruturado) | Parquet filtrado (estruturado) | Leitura em blocos e filtro por raiz de CNPJ |
| `objetoContrato` (não estruturado) | Texto normalizado no Parquet | Normalização; busca textual condicional |

## Cuidado com dados pessoais nos trechos

Os trechos de sócios têm o nome reduzido ao primeiro nome mais iniciais, a raiz do CNPJ mascarada e os dígitos do CPF substituídos por `X`. A razão social do fornecedor no contrato é de pessoa jurídica e pública. Nenhum trecho identifica uma pessoa física. Detalhes no parecer de LGPD (`docs/parecer-lgpd.md`).