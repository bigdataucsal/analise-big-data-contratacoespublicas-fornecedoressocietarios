# Parser dos arquivos da Receita Federal

Entrega da Trilha 2, semana 3. Registra o que o parser faz e a evidência de que ele leu os arquivos reais de ponta a ponta. A fonte dos números é o manifesto `docs/evidencias/manifesto_receita.json`, gerado pelo próprio `etl/baixar_receita.py` na competência 2026-09-14 da Receita.

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

## Como reproduzir

Com os ZIPs na pasta definida por `DIR_DADOS_RAW` no `etl/.env`, a partir de `etl/`:

```
python baixar_receita.py --sem-download --filtrar-cnpjs
```

O manifesto é regravado em `docs/evidencias/manifesto_receita.json`.