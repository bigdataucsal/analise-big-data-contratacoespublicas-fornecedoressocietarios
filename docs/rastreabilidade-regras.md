# Rastreabilidade das regras de negócio

Entrega da Trilha 3. Para cada regra de `docs/regras-de-negocio.md`: onde está
a definição lógica, qual código a aplica, qual teste a prova e o que ainda
falta. A tabela existe para que a defesa não dependa de memória — cada linha
aponta para um arquivo que pode ser aberto na hora.

Os testes rodam de dentro de `etl/`, sem dependência além do que o
`requirements.txt` já pede:

```bash
cd etl && python -m unittest discover -s testes -t . -v
```

São 118 testes, todos passando em 16/11/2026. A CI os executa em cada pull
request para a `main`, no passo "Testar as regras de negocio" de
`.github/workflows/ci-etl.yml`.

A conferência independente dos indicadores é o `etl/auditar_kpis.py`. Ele não
lê visão materializada nem painel: vai no Parquet, aplica os módulos de
`etl/regras/` e compara com os números publicados, saindo com código 1 quando
alguma coisa diverge além da tolerância. Serve de porta antes da defesa.

```bash
cd etl && python auditar_kpis.py --amostra
```

A saída sobre a amostra de janeiro está em
`docs/evidencias/auditoria_kpis_amostra_janeiro.txt`: 20.000 linhas conferidas
uma a uma entre o SQL do tratamento e o módulo de elegibilidade, com zero
divergência.

## Tabela

| RN | definição | implementação | teste | nº | situação |
|---|---|---|---|---|---|
| RN-01 Normalização de identificadores | `regras-de-negocio.md` §RN-01 | `etl/regras/identificadores.py`; SQL em `etl/tratar_contratos.py`; `etl/recorte_cnpjs.py` | `TestRN01Identificadores`, `TestTratamentoSQL.test_rn01_*` | 9 + 2 | implementada e conferida nas duas pontas |
| RN-02 Elegibilidade do contrato | §RN-02 | `etl/regras/elegibilidade.py`; `etl/recorte_cnpjs.py` | `TestRN02Elegibilidade`, `TestTratamentoSQL.test_rn02_*` | 9 + 1 | regra completa em módulo; a marcação no Parquet ainda não é gravada |
| RN-03 Sócio com poder de controle | §RN-03 | `etl/regras/qualificacoes.py` (lista de códigos); `etl/classificar_empresas.py` (critério antigo, por palavra) | `TestRN03Qualificacoes` | 11 | os dois critérios convivem de propósito; o script ainda usa o antigo |
| RN-04 Inferência de gênero | §RN-04 | `etl/regras/genero.py`; `etl/inferir_genero.py` | `TestRN04Genero` | 12 | implementada; sensibilidade ao limiar nos sócios não medida |
| RN-05 Controle da empresa | §RN-05 | `etl/regras/controle.py`; `etl/classificar_empresas.py`; `SQL_CONTROLE` em `etl/construir_agregados.py` | `TestRN05Controle`, `TestAgregadoVsRegra` | 14 + 7 | implementada e conferida contra o agregado do banco |
| RN-06 Proxy de cor ou raça | §RN-06 | `etl/regras/proxy_racial.py`; `etl/baixar_proxy_racial.py`; `etl/traduzir_municipios.py` | `TestRN06ProxyRacial` | 5 | eixo censitário pronto; eixo RAIS pendente |
| RN-07 Concentração societária | §RN-07 | `etl/regras/concentracao.py` | `TestRN07Concentracao` | 8 | regra em código pela primeira vez; falta rodar sobre a Receita filtrada |
| RN-08 Sanção na data | §RN-08 | `etl/regras/sancoes.py` | `TestRN08Sancoes` | 10 | regra em código pela primeira vez; depende do CEIS e do CNEP (T2) |
| RN-09 Anonimização e mínimo de agregação | §RN-09 | `etl/regras/anonimizacao.py` | `TestRN09Anonimizacao` | 11 | regra em código pela primeira vez; falta aplicar na camada do painel (T4) |

Quatro classes de teste não pertencem a uma regra só. `TestTratamentoSQL`
executa a consulta de tratamento no DuckDB sobre uma amostra sintética de dez
contratos e confere RN-01 e RN-02 contra os módulos, além da tipagem, da
normalização de booleanos e da deduplicação. `TestContratoComOCarregador`
confere que o cabeçalho do `SELECT` do tratamento, a lista `COLUNAS` do
`carregar_aiven.py` e o `schema_postgres.sql` continuam de acordo — a carga
valida isso em tempo de execução e o teste antecipa a descoberta.
`TestSQLSemComentarioQuebrado` é regressão do defeito descrito abaixo. E
`TestAgregadoVsRegra` confere o agregado do banco contra a RN-05, descrito na
seção seguinte.

## O agregado do KPI e a RN-05 classificam igual, e isso está provado

O KPI de controle feminino sai da tabela `agg_kpi_genero_setor`, alimentada
pelo `SQL_CONTROLE` do `etl/construir_agregados.py`. Se aquele `CASE` e o
`etl/regras/controle.py` discordarem, o número da tela deixa de ser o número da
regra — que é exatamente o que a auditoria existe para impedir.

`testes/test_agregado_vs_regra.py` **lê o SQL do módulo** e executa o `CASE` de
verdade no DuckDB sobre onze quadros societários sintéticos, comparando linha a
linha com o módulo. Hoje os dois concordam em todos os casos, inclusive nos
dois que antes divergiam: a empresa com sócio pessoa jurídica no quadro e a
empresa sem nenhuma linha de sócio na base.

Isso é uma mudança de estado em relação à versão anterior deste documento, que
registrava as duas divergências como abertas. A T2 corrigiu as duas na
consolidação do modelo estrela, quando trocou a visão materializada
`mv_kpi_genero_setor` pela tabela de agregado.

**O caso novo que veio junto.** O `CASE` da T2 trouxe uma classe que a RN-05
escrita não previa: `nao classificado`, para a empresa que tem sócio pessoa
física elegível com gênero ainda nulo. Não é a mesma coisa que `indeterminado`
— indeterminado é um veredito da RN-04 (nome ambíguo ou ausente da base de
nomes), nulo é ausência de veredito. Misturar os dois faria a empresa parecer
avaliada quando não foi. O `regras/controle.py` passou a ter a classe, com a
mesma precedência do SQL (decide antes do sócio PJ), e a RN-05 foi atualizada.

**Por que o teste lê o SQL em vez de guardar uma cópia.** A versão anterior
guardava a transcrição do `CASE` em Python. Quando a T2 trocou a visão pelo
agregado e corrigiu a regra, o teste **continuou passando** e o documento
continuou afirmando uma divergência que já não existia — um teste verde
sustentando uma afirmação falsa, que é pior do que um teste vermelho. Lendo da
fonte, ou ele acompanha a mudança ou falha.

Conferido por mutação: retirando do `SQL_CONTROLE` o ramo do sócio pessoa
jurídica, o teste falha em três pontos e nomeia a divergência
(`regra=misto ou indeterminado agregado=feminino`); apagando o `CASE` inteiro,
ele para com a mensagem pedindo que o teste seja reapontado em vez de removido.

## O que cada regra prova, em uma linha

- **RN-01.** A raiz de `00394429000102` é `00394429`, e continua texto: o teste
  compara a raiz com `str(int(raiz))` e exige que sejam diferentes, que é a
  forma de provar que o zero à esquerda sobreviveu. PJ com onze dígitos, PF com
  catorze e identificador irregular não recebem raiz.
- **RN-02.** `0.0001` dá zero centavos e não é elegível, que é o caso dos 245
  contratos do JSON bruto. O corte de sanidade inclui o contrato de exatamente
  R$ 1 bilhão e exclui o de R$ 1.000.000.000,01. Contrato de receita sai dos
  indicadores sem ser apagado.
- **RN-03.** O titular de EIRELI (65) entra, o sócio pessoa jurídica e o
  estrangeiro não entram, e o 53 e o 63 ficam de fora. A administração entra no
  controle e sai da concentração — é o único ponto em que as duas regras
  divergem, e o teste fixa a divergência.
- **RN-04.** 90 contra 10 classifica, 89 contra 11 não. Dezenove ocorrências
  não classificam; vinte classificam. O denominador é a soma dos dois sexos.
- **RN-05.** Sócio pessoa jurídica decide antes de qualquer contagem. Empate não
  é maioria. Exatamente um terço de indeterminados ainda classifica; mais de um
  terço não. O denominador do KPI 1 é 131.423, não 239.600: o teste reconstrói
  os 30,4% a partir das contagens publicadas.
- **RN-06.** Atribuir composição racial a `socio`, `pessoa` ou `individuo`
  levanta erro. A falácia ecológica deixa de ser só um parágrafo do parecer e
  passa a ser uma barreira no código.
- **RN-07.** Com dois sócios multiempresa dividindo uma empresa, a soma por
  sócio dá 400 e o total sem dupla contagem dá 300. É o teste que justifica a
  marca de sobreposição existir.
- **RN-08.** Contrato assinado em 15/07 com sanção de 01/06 a 31/12 é marcado;
  o de 31/05 não é. Sanção sem data de fim continua vigente em 2030.
- **RN-09.** O pseudônimo é estável, não contém o nome nem a máscara, e muda com
  o sal. CPF sem máscara na camada de dados levanta erro. Agregado com quatro
  sócios é suprimido; com cinco, passa.

## Evidência de que os testes pegam defeito

Um teste que nunca falhou não provou nada. O `TestTratamentoSQL` foi conferido
por mutação: reintroduzindo no `tratar_contratos.py` o defeito que a limpeza de
comentários havia causado, em que

```sql
strftime(data_publicacao, '%Y-%m') AS ano_mes   -- chave de particao
```

virou

```sql
strftime(data_publicacao, '%Y-%m') AS ano_mes, chave de particao
```

a suíte falha em três pontos. Isso importa porque o defeito atravessou três
verificações antes: o arquivo continua compilando, porque o SQL mora dentro de
uma string de Python; o `--help` continua funcionando, porque não toca na
consulta; e a comparação de AST não o vê, porque neutraliza o conteúdo das
strings. Executar a consulta é a única verificação que pega essa classe de
defeito, e é o que o teste passou a fazer.

## Pendências, por responsável

Da Trilha 3, e dependem só de dado que já existe:

1. Gravar as marcações da RN-02 no Parquet — `contrato_suspeito` pela D3 e a
   saída dos contratos de receita pela D9. O módulo já decide; o tratamento
   ainda não grava a coluna.
2. Alinhar o `classificar_empresas.py` à lista de códigos da RN-03 e medir a
   diferença contra o critério por palavra. O teto é 1.608 linhas, 0,49% dos
   sócios elegíveis; o efeito real sobre a classificação nunca foi medido.
3. Rodar a RN-07 sobre a Receita filtrada e publicar a concentração com a marca
   de sobreposição.
4. Sensibilidade do limiar da RN-04 nos sócios, com o Censo 2022, e a
   sensibilidade da D4 sem diretor, presidente e conselheiro.

Dependem de outra trilha:

5. RN-08 precisa do CEIS e do CNEP (T2, issue #27). O módulo e os testes já
   estão prontos: assim que o arquivo existir, falta só indexar e marcar.
6. RN-09 precisa da camada de apresentação (T4) para que a supressão de agregado
   pequeno tenha onde ser aplicada. O filtro fica no painel e não no agregado,
   porque o mesmo agregado pode ser seguro num recorte e inseguro noutro.

Saiu da lista: a divergência entre o agregado do KPI e a RN-05 foi fechada pela
T2 na consolidação do modelo estrela, e passou a ter teste que a mantém fechada.
