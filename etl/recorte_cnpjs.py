"""
Gera a lista de CNPJs do recorte -- a entrega da T3 que destrava a T2.
=====================================================================
A base do CNPJ da Receita Federal e publicada como ZIP monoliticos: nao
existe filtro por CNPJ no servidor, entao a T2 baixa tudo e filtra na
hora de parsear. O que a T2 precisa da T3 nao e o download, e a LISTA
contra a qual filtrar.

Este script produz essa lista a partir dos contratos do PNCP ja baixados.
Pode rodar antes do download terminar: sai uma lista preliminar, boa para
a T2 desenvolver e testar o parser, e depois e so rodar de novo para
gerar a definitiva.

Saida (em config.DIR_RECORTE, que e etl/dados/recorte/):
    cnpjs_raiz.csv        CSV com cabecalho `cnpj_basico`, um por linha.
                          E ESTE o arquivo que o baixar_receita.py consome:
                              python baixar_receita.py
                                  --filtrar-cnpjs dados/recorte/cnpjs_raiz.csv
    cnpjs_raiz.txt        a mesma lista sem cabecalho, para leitura humana
    cnpjs_completos.txt   CNPJ de 14 digitos, para conferencia. NAO serve de
                          filtro: o quadro societario e chaveado pela raiz,
                          e filtrar por 14 digitos devolveria zero linhas.
    orgaos_recorte.csv    os orgaos escolhidos, com contratos e valor
    recorte.md            o recorte por escrito, para o README

Esta e a unica pasta de dados que vai para o repositorio, porque e decisao
e nao dado bruto: quem for filtrar os arquivos da Receita precisa dela, e
regerar exigiria ter o bruto do PNCP, que nao e versionado.

Uso (rodar de dentro de etl/):
    python recorte_cnpjs.py                      # top 50 orgaos, corte em 1 bi
    python recorte_cnpjs.py --top-orgaos 100
    python recorte_cnpjs.py --sem-corte-sanidade # mantem os outliers
    python recorte_cnpjs.py --todos-orgaos       # sem recorte de orgao

Sobre o corte de sanidade
-------------------------
Medido em 20/09/2026 sobre 58.769 contratos (1 a 20 de janeiro):

    mediana do contrato  R$      4.153,50
    media                R$ 45.013.038,24     <- 10.837x a mediana
    maior contrato       R$ 640.000.000.000,00

26 contratos (0,04% da base) concentram 98,7% do valor somado, e os
quatro maiores sao de R$ 640 bilhoes, R$ 640 bilhoes, R$ 562 bilhoes e
R$ 250 bilhoes, todos do mesmo orgao. Nao sao contratos: sao erros de
digitacao na origem, provavelmente valor sem separador decimal.

Isso importa porque "top N orgaos por valor" e um criterio de recorte, e
com os outliers dentro ele seleciona os orgaos errados: passa a premiar
quem digitou errado. Com o corte em R$ 1 bilhao, os top 50 respondem por
71% do valor; sem o corte, por 99,6% -- um numero que parece otimo e nao
significa nada.

O limite de R$ 1 bilhao e defensavel mas e uma escolha: e uma ordem de
grandeza acima do maior contrato federal plausivel para um unico objeto.
Documentem o valor escolhido e quantos contratos ele exclui.
"""

import argparse
import sys
from pathlib import Path

import duckdb

import config

CORTE_SANIDADE_PADRAO = 1_000_000_000.0   # R$ 1 bilhao
TOP_ORGAOS_PADRAO = 50


def fonte_contratos(raw_dir: Path) -> str:
    """O JSONL do PNCP que existir, na ordem de preferencia."""
    pncp = raw_dir / "pncp"
    for nome in (f"contratos_{config.ANO_REFERENCIA}_completo.jsonl",
                 f"contratos_{config.ANO_REFERENCIA}.jsonl"):
        caminho = pncp / nome
        if caminho.is_file() and caminho.stat().st_size > 0:
            return str(caminho).replace("\\", "/")
    raise SystemExit(
        f"ERRO: nenhum JSONL de contratos em {pncp}.\n"
        f"      Rode antes: python baixar_pncp_rapido.py"
    )


def br(valor, casas=2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Gera a lista de CNPJs do recorte para a filtragem da Receita")
    p.add_argument("--top-orgaos", type=int, default=TOP_ORGAOS_PADRAO,
                   help=f"quantos orgaos manter, por valor contratado "
                        f"(padrao: {TOP_ORGAOS_PADRAO})")
    p.add_argument("--todos-orgaos", action="store_true",
                   help="nao recortar por orgao (lista de CNPJ fica bem maior)")
    p.add_argument("--corte-sanidade", type=float, default=CORTE_SANIDADE_PADRAO,
                   help=f"descarta contratos acima deste valor (padrao: "
                        f"{CORTE_SANIDADE_PADRAO:.0f}). Ver o cabecalho do arquivo.")
    p.add_argument("--sem-corte-sanidade", action="store_true",
                   help="mantem os outliers (nao recomendado; distorce o recorte)")
    p.add_argument("--saida", default=config.DIR_RECORTE,
                   help="pasta de saida (padrao: config.DIR_RECORTE)")
    args = p.parse_args()

    fonte = fonte_contratos(Path(config.DIR_DADOS_RAW))
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    con.execute(f"""
        CREATE VIEW bruto AS
        SELECT * FROM read_json('{fonte}', format='newline_delimited',
                                union_by_name=true, sample_size=-1)
    """)

    # Normaliza o que interessa e ja deduplica pela chave natural.
    con.execute("""
        CREATE VIEW contratos AS
        SELECT
            numeroControlePNCP                      AS chave,
            orgaoEntidade.cnpj                      AS orgao_cnpj,
            orgaoEntidade.razaoSocial               AS orgao_nome,
            nullif(trim(niFornecedor), '')          AS ni_fornecedor,
            upper(trim(tipoPessoa))                 AS tipo_pessoa,
            regexp_replace(niFornecedor, '[^0-9]', '', 'g') AS ni_digitos,
            valorGlobal                             AS valor
        FROM bruto
        WHERE numeroControlePNCP IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY numeroControlePNCP
                                   ORDER BY dataAtualizacaoGlobal DESC) = 1
    """)

    total = con.sql("SELECT count(*) FROM contratos").fetchone()[0]
    print(f"== Recorte a partir de {fonte} ==")
    print(f"   {br(total, 0)} contratos unicos na base\n")

    # --- corte de sanidade ---
    if args.sem_corte_sanidade:
        con.execute("CREATE VIEW elegiveis AS SELECT * FROM contratos WHERE valor > 0")
        print("   corte de sanidade: DESLIGADO (os outliers entram)")
    else:
        limite = args.corte_sanidade
        con.execute(f"""CREATE VIEW elegiveis AS
            SELECT * FROM contratos WHERE valor > 0 AND valor <= {limite}""")
        fora_alto = con.sql(
            f"SELECT count(*), coalesce(sum(valor),0) FROM contratos WHERE valor > {limite}"
        ).fetchone()
        fora_zero = con.sql("SELECT count(*) FROM contratos WHERE valor <= 0").fetchone()[0]
        soma_tudo = con.sql("SELECT sum(valor) FROM contratos").fetchone()[0]
        print(f"   corte de sanidade: R$ {br(limite)}")
        print(f"     {fora_alto[0]} contrato(s) acima do limite, "
              f"{100*fora_alto[1]/soma_tudo:.1f}% do valor bruto somado")
        print(f"     {fora_zero} contrato(s) com valor zero ou negativo")

    elegiveis, soma = con.sql("SELECT count(*), sum(valor) FROM elegiveis").fetchone()
    print(f"     restam {br(elegiveis, 0)} contratos, R$ {br(soma)}\n")

    # --- recorte de orgao ---
    if args.todos_orgaos:
        con.execute("CREATE VIEW recortados AS SELECT * FROM elegiveis")
        print("   recorte de orgao: nenhum (todos os orgaos)")
    else:
        con.execute(f"""
            CREATE VIEW orgaos_top AS
            SELECT orgao_cnpj, any_value(orgao_nome) AS orgao_nome,
                   count(*) AS contratos, sum(valor) AS valor
            FROM elegiveis GROUP BY orgao_cnpj
            ORDER BY valor DESC LIMIT {args.top_orgaos}
        """)
        con.execute("""CREATE VIEW recortados AS
            SELECT * FROM elegiveis
            WHERE orgao_cnpj IN (SELECT orgao_cnpj FROM orgaos_top)""")
        n_org = con.sql("SELECT count(*) FROM orgaos_top").fetchone()[0]
        r = con.sql("SELECT count(*), sum(valor) FROM recortados").fetchone()
        print(f"   recorte de orgao: top {n_org} por valor contratado")
        print(f"     {br(r[0], 0)} contratos ({100*r[0]/elegiveis:.1f}% dos elegiveis)")
        print(f"     R$ {br(r[1])} ({100*r[1]/soma:.1f}% do valor elegivel)")
        con.sql("""SELECT orgao_cnpj, orgao_nome, contratos, round(valor,2) AS valor
                   FROM orgaos_top""").write_csv(str(destino / "orgaos_recorte.csv"))

    # --- as listas de CNPJ ---
    completos = [r[0] for r in con.sql("""
        SELECT DISTINCT ni_digitos FROM recortados
        WHERE tipo_pessoa = 'PJ' AND length(ni_digitos) = 14
        ORDER BY 1""").fetchall()]
    raizes = [r[0] for r in con.sql("""
        SELECT DISTINCT left(ni_digitos, 8) FROM recortados
        WHERE tipo_pessoa = 'PJ' AND length(ni_digitos) = 14
        ORDER BY 1""").fetchall()]
    pf = con.sql("""SELECT count(DISTINCT ni_fornecedor) FROM recortados
                    WHERE tipo_pessoa <> 'PJ' OR length(ni_digitos) <> 14""").fetchone()[0]

    (destino / "cnpjs_completos.txt").write_text("\n".join(completos) + "\n", encoding="utf-8")
    (destino / "cnpjs_raiz.txt").write_text("\n".join(raizes) + "\n", encoding="utf-8")

    # CSV com cabecalho `cnpj_basico`: e o formato que o baixar_receita.py
    # espera em --filtrar-cnpjs, e `cnpj_basico` e o nome que a propria
    # Receita da a essa coluna. O .txt continua existindo para leitura
    # humana e para quem quiser usar em shell.
    (destino / "cnpjs_raiz.csv").write_text(
        "cnpj_basico\n" + "\n".join(raizes) + "\n", encoding="utf-8")

    print(f"\n== Listas geradas em {destino} ==")
    print(f"   cnpjs_raiz.csv      : {br(len(raizes), 0)} raizes de 8 digitos "
          f"<- e esta que alimenta o baixar_receita.py")
    print(f"   cnpjs_raiz.txt      : mesma lista, sem cabecalho")
    print(f"   cnpjs_completos.txt : {br(len(completos), 0)} CNPJ de 14 digitos "
          f"(conferencia; o filtro da Receita e pela raiz)")
    print(f"   ({pf} fornecedor(es) pessoa fisica ou com identificador "
          f"irregular ficaram de fora das listas)")

    # --- o recorte por escrito ---
    dias_cobertos = ""
    dias_arq = Path(fonte).with_suffix(".dias")
    if dias_arq.is_file():
        marcados = [l for l in dias_arq.read_text(encoding="utf-8").splitlines() if l.strip()]
        if marcados:
            dias_cobertos = (f"{len(marcados)} dia(s), de {min(marcados)} a "
                             f"{max(marcados)}")

    linhas = [
        "# Recorte congelado",
        "",
        "> **PRELIMINAR.** Esta lista NÃO é definitiva e não deve ser tratada",
        "> como tal enquanto a coleta do PNCP não terminar.",
        "",
        "## De onde veio",
        "",
        f"Arquivo de origem: `{Path(fonte).name}`, saída do `baixar_pncp_rapido.py`.",
        "",
        f"Cobertura: {dias_cobertos or 'não determinada'} de 365 dias do "
        f"período definido em `config.py`.",
        "",
        "Esse arquivo de origem **não é versionado**, porque é dado bruto e",
        "passa de 100 MB. Quem clonar o repositório recebe esta lista pronta,",
        "mas não consegue regerá-la sem antes rodar a coleta:",
        "",
        "```bash",
        "python baixar_pncp_rapido.py    # a coleta completa leva horas",
        "python recorte_cnpjs.py         # aí sim regera a lista definitiva",
        "```",
        "",
        "A lista está versionada justamente por isso: sem ela, quem for filtrar",
        "os arquivos da Receita ficaria bloqueado esperando uma coleta de horas.",
        "Ela serve para desenvolver e testar o parser contra dado real. O número",
        "de CNPJs vai crescer quando a coleta fechar o ano.",
        "",
        "## Critérios",
        "",
        f"1. Periodo: {config.DATA_INICIAL_PNCP} a {config.DATA_FINAL_PNCP} "
        f"(definido em `config.py`).",
        "2. Contratos com valor global maior que zero.",
    ]
    if not args.sem_corte_sanidade:
        linhas.append(
            f"3. Contratos com valor global ate R$ {br(args.corte_sanidade)}. "
            f"Acima disso sao erros de digitacao na origem, nao contratos: na "
            f"base medida, {fora_alto[0]} registros concentravam "
            f"{100*fora_alto[1]/soma_tudo:.1f}% do valor somado, com os maiores "
            f"passando de R$ 500 bilhoes em um unico contrato.")
    if not args.todos_orgaos:
        linhas.append(f"4. Os {args.top_orgaos} orgaos com maior valor contratado "
                      f"apos os criterios acima (lista em `orgaos_recorte.csv`).")
    linhas += [
        "",
        "## Resultado",
        "",
        f"- {br(total, 0)} contratos na base de origem",
        f"- {br(elegiveis, 0)} apos os criterios de valor",
    ]
    if not args.todos_orgaos:
        linhas.append(f"- {br(r[0], 0)} apos o recorte de orgao")
    linhas += [
        f"- {br(len(raizes), 0)} raizes de CNPJ distintas, que formam o filtro "
        f"aplicado aos arquivos da Receita Federal",
        "",
        "## Observacao",
        "",
        "A lista e preliminar enquanto o download do PNCP nao terminar. Ela serve "
        "para desenvolver e testar o parser da Receita; basta rodar este script de "
        "novo ao fim da coleta para gerar a definitiva.",
    ]
    (destino / "recorte.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"   recorte.md          : o recorte por escrito, para o README")
    return 0


if __name__ == "__main__":
    sys.exit(main())
