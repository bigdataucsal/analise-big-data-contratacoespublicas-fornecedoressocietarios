# Parser dos arquivos da Receita Federal

Entrega da Trilha 2, semana 3, e da carga inicial da T2 (semana 1). Registra o que o parser faz, a evidência de que ele leu os arquivos reais de ponta a ponta e como o resultado vai para o banco. A fonte dos números de leitura é o manifesto `docs/evidencias/manifesto_receita.json`, gerado pelo próprio `etl/baixar_receita.py` na competência 2026-09-14 da Receita.

## O que o parser faz

- **Lê direto dos ZIPs, em chunks, sem extrair.** A Receita publica 7,76 GB compactados (28,67 GB descompactados), e nada disso é gravado em disco descompactado.
- **Trata o formato de origem.** Os arquivos são CSV sem linha de cabeçalho, com separador `;` e codificação latina. Os nomes das colunas vêm do PDF de metadados da Receita, e o manifesto registra o nome e o tipo de origem de cada coluna.
- **Grava todas as colunas como texto.** É proposital: zeros à esquerda são significativos em CNPJ, CEP, código de município e CNAE. A conversão de tipo pertence ao tratamento. As datas vêm como AAAAMMDD, com ausência representada por `00000000`, e a moeda vem com vírgula decimal.
- **Filtra pelo CNPJ.** Mantém só as linhas de empresas, estabelecimentos, Simples e sócios cuja raiz de 8 dígitos (`cnpj_basico`) está na lista de 239.605 raízes dos contratos do recorte. As tabelas de domínio (CNAE, motivo, município, natureza jurídica, país e qualificação do sócio) são gravadas por inteiro.
- **Grava Parquet e manifesto.** Um arquivo Parquet por tabela e um manifesto com as linhas lidas e gravadas.

## Evidência: leitura completa de cada arquivo

| Arquivo | Linhas lidas na origem | Linhas gravadas | Mantido |
| --- | --- | --- | --- |
| Empresas | 70.085.592 | 239.600 | 0,34% |
| Estabelecimentos | 73.366.147 | 529.225 | 0,72% |
| Simples Nacional | 50.396.768 | 201.427 | 0,40% |
| Sócios | 28.341.092 | 339.385 | 1,20% |
| **Total dos quatro arquivos** | **222.189.599** | **1.309.637** | **0,59%** |

Nas tabelas de domínio, o número de linhas lidas é igual ao de gravadas: CNAE (1.359), motivo (63), município (5.572), natureza jurídica (91), país (255) e qualificação do sócio (68).

Duas conferências de coerência. A tabela de empresas tem 239.600 linhas para 239.605 raízes pedidas, e as cinco que faltam são raízes que não constam do cadastro da Receita. E as tabelas de domínio, que não passam pelo filtro, voltam inteiras.

A execução do filtro levou 1h24m50s (de 15:27 a 16:51 de 30/09/2026), a cerca de 44 mil linhas por segundo. Por arquivo: empresas 13,5 min, estabelecimentos 36,4 min, Simples 22,2 min e sócios 11,7 min.

## Limites do que este documento prova

- O manifesto registra linhas lidas e gravadas, não linhas rejeitadas. `[PENDENTE: conferir no log da execução se houve aviso de linha malformada; se não houve, substituir esta frase por "nenhuma linha foi rejeitada"]`
- O filtro descarta linhas sem validá-las: a contagem de "lidas" mostra que o arquivo foi percorrido até o fim, não que cada linha descartada seja válida.
- A leitura é da competência 2026-09-14. Se a Receita mudar o layout dos arquivos, a ordem das colunas do manifesto precisa ser revista contra o PDF de metadados.

## Carga no banco

A carga é feita por `etl/carregar_receita_aiven.py`, que lê os Parquet (sem reler os ZIPs) e preenche, no modelo estrela do PostgreSQL da Aiven, as tabelas `dim_fornecedor`, `dim_socio` e `ponte_empresa_socio`. O schema vem de `etl/schema_estrela.sql`, aplicado antes por `etl/aplicar_schema.py`.

| Tabela do banco | Origem nos Parquet | Linhas a carregar | Linhas no banco |
| --- | --- | --- | --- |
| `dim_fornecedor` | empresas, com CNAE e início de atividade da matriz (estabelecimentos) | 239.600 | `[PENDENTE]` |
| `dim_socio` | sócios, um por identificador derivado | 315.402 | `[PENDENTE]` |
| `ponte_empresa_socio` | sócios, um por vínculo | 339.385 | `[PENDENTE]` |

"Linhas a carregar" vem da simulação do script (`--simular`) de 11/11/2026, antes de conectar no banco. O total da ponte é igual ao de linhas de sócios gravadas no filtro (339.385): nenhuma linha foi perdida na montagem.

Decisões da carga:

- **Identificador do sócio (RN-09).** É o SHA-256 de máscara do CPF, nome normalizado (maiúsculas, sem acento, sem espaços duplos) e um sal secreto, truncado em 16 caracteres hexadecimais, com prefixo `S`. O sal fica no `etl/.env`, fora do repositório, e não pode mudar depois da carga. A máscara sozinha não identifica a pessoa: pessoas diferentes colidem na mesma máscara.
- **Grupo de qualificação.** É derivado da descrição na tabela de domínio da Receita, e não do código. No ensaio: participação 297.046 vínculos, administração 39.214, titularidade 1.609 e outro 1.516. Diretor, Presidente e Conselheiro de Administração entram em administração (RN-03, decisão D4).
- **Empresas sem sócio.** 174.599 das 239.600 empresas têm ao menos um sócio na base. As outras 65.001 (27,1%) não têm, e o controle delas não é inferível pela tabela de sócios (RN-05).
- **Conversões.** O capital social troca a vírgula decimal por ponto, e valores que não cabem em `NUMERIC(18,2)` viram nulos. As datas AAAAMMDD viram `DATE`, e `00000000` vira nulo.
- **Idempotência.** Cada tabela é carregada com `COPY` numa tabela temporária e `INSERT ... ON CONFLICT`, então rodar de novo não duplica. Se as duas dimensões já estiverem carregadas, o script as pula e carrega só a ponte, em lotes de 50 mil linhas, com commit a cada lote.
- **Fora desta carga.** Os estabelecimentos não viram tabela: só o CNAE e o início da atividade da matriz entram em `dim_fornecedor`. `id_municipio_sede` e `genero` ficam nulos, porque dependem da tradução do código de município da Receita e do `classificar_empresas.py`.

Primeira tentativa de carga (11/11/2026). `dim_fornecedor` (239.600) e `dim_socio` (315.402) foram gravadas e conferidas, com o banco em 139,9 MB. A ponte ficou com 0 linhas: a conexão caiu durante o insert (`SSL error: unexpected eof`) e, na tentativa seguinte, o banco estava em somente leitura (`default_transaction_read_only = on`). O serviço não voltou a ligar. A causa não foi confirmada, porque não houve acesso aos logs do serviço. O sintoma é parecido com o do benchmark (`docs/escolha-do-banco.md`) e compatível com o limite de memória e de disco do nó gratuito. A resposta foi gravar a ponte em lotes e pular as dimensões já carregadas.

Resultado da carga final: `[PENDENTE: preencher com a seção "Conferência" de docs/evidencias/carga-receita.txt, com linhas e MB por tabela, tamanho total do banco e tempo de execução]`

## Como reproduzir

Com os ZIPs na pasta definida por `DIR_DADOS_RAW` no `etl/.env`, a partir de `etl/`:

```
python baixar_receita.py --sem-download --filtrar-cnpjs
python aplicar_schema.py
python carregar_receita_aiven.py --simular
python carregar_receita_aiven.py
```

O manifesto do filtro é gravado em `etl/dados/parquet/receita/_manifesto.json`, junto dos Parquet (pasta fora do Git). A cópia versionada, usada como evidência, é `docs/evidencias/manifesto_receita.json`. A saída da carga vai para `docs/evidencias/carga-receita.txt`.