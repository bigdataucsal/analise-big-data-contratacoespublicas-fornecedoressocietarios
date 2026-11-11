"""Monta a lista de CNPJs que define o universo da analise."""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import duckdb

import config

CORTE_SANIDADE_PADRAO = 1_000_000_000.0
TOP_ORGAOS_PADRAO = 50


def fonte_contratos(raw_dir: Path) -> str:
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

    marcados = []
    dias_arq = Path(fonte).with_suffix(".dias")
    if dias_arq.is_file():
        marcados = [l for l in dias_arq.read_text(encoding="utf-8").splitlines() if l.strip()]
    dias_cobertos = (f"{len(marcados)} dia(s), de {min(marcados)} a {max(marcados)}"
                     if marcados else "")
    dias_periodo = (datetime.strptime(config.DATA_FINAL_PNCP, "%Y%m%d")
                    - datetime.strptime(config.DATA_INICIAL_PNCP, "%Y%m%d")).days + 1
    preliminar = len(marcados) < dias_periodo
    opcoes = []
    if args.todos_orgaos:
        opcoes.append("--todos-orgaos")
    elif args.top_orgaos != TOP_ORGAOS_PADRAO:
        opcoes.append(f"--top-orgaos {args.top_orgaos}")
    if args.sem_corte_sanidade:
        opcoes.append("--sem-corte-sanidade")
    elif args.corte_sanidade != CORTE_SANIDADE_PADRAO:
        opcoes.append(f"--corte-sanidade {args.corte_sanidade:.0f}")
    comando = " ".join(["python recorte_cnpjs.py"] + opcoes)

    linhas = ["# Recorte congelado", ""]
    if preliminar:
        linhas += [
            "> **PRELIMINAR.** Esta lista NÃO é definitiva e não deve ser tratada",
            "> como tal enquanto a coleta do PNCP não cobrir o período inteiro.",
            "",
        ]
    linhas += [
        "## De onde veio",
        "",
        f"Arquivo de origem: `{Path(fonte).name}`, saída do `baixar_pncp_rapido.py`.",
        "",
        f"Cobertura: {dias_cobertos or 'não determinada'} de {dias_periodo} dias do "
        f"período definido em `config.py`.",
        "",
        "Nem esse arquivo de origem nem as listas de CNPJ geradas aqui são",
        "versionados: o bruto passa de 100 MB. Para regerar a lista é preciso",
        "rodar a coleta e depois este script, com o mesmo comando:",
        "",
        "```bash",
        "python baixar_pncp_rapido.py    # a coleta completa leva horas",
        f"{comando}    # o comando que gerou este arquivo",
        "```",
        "",
        "## Critérios",
        "",
        f"1. Periodo: {config.DATA_INICIAL_PNCP} a {config.DATA_FINAL_PNCP} "
        f"(definido em `config.py`).",
        "2. Contratos com valor global maior que zero, lido no JSON bruto. A RN-02 "
        "passou a contar o valor em centavos; a diferenca esta explicada em "
        "`docs/regras-de-negocio.md`.",
    ]
    if not args.sem_corte_sanidade:
        linhas.append(
            f"3. Contratos com valor global ate R$ {br(args.corte_sanidade)}. "
            f"Acima disso o valor nao e plausivel como contrato (erro de escala "
            f"ou, como hipotese ainda a confirmar, teto estimado de "
            f"credenciamento): na base medida, {fora_alto[0]} registros "
            f"concentravam {100*fora_alto[1]/soma_tudo:.1f}% do valor somado.")
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
    ]
    if preliminar:
        linhas += [
            "",
            "## Observacao",
            "",
            "A lista e preliminar enquanto a coleta do PNCP nao cobrir o periodo. "
            "Ela serve para desenvolver e testar o parser da Receita; basta rodar "
            "este script de novo ao fim da coleta para gerar a definitiva.",
        ]
    (destino / "recorte.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"   recorte.md          : o recorte por escrito, para o README")
    return 0


if __name__ == "__main__":
    sys.exit(main())
