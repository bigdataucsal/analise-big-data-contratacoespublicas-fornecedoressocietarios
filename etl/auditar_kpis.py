"""Recalcula os KPIs por fora do banco e confere contra os numeros publicados.

Conferencia independente da issue de auditoria: nao le visao materializada nem
painel. Vai no Parquet, aplica as regras de etl/regras/ e compara com os
numeros de referencia de docs/regras-de-negocio.md. Divergencia derruba o
script com codigo 1, para que sirva de porta antes da defesa.

Uso (rodar de dentro de etl/):
    python auditar_kpis.py
    python auditar_kpis.py --fonte raw --tolerancia 0.5
"""

import argparse
import sys
from pathlib import Path

import duckdb

import config
from regras import controle, elegibilidade

REFERENCIA_ANO = {
    "contratos": 2_023_134,
    "valor_bruto": 18_250_000_000_000.0,
    "suspeitos": 243,
    "share_suspeitos": 95.77,
    "valor_com_corte": 771_200_000_000.0,
    "sem_raiz": 78_795,
    "receita": 20_439,
}

REFERENCIA_AMOSTRA = {
    "contratos": 58_769,
    "suspeitos": 26,
    "share_suspeitos": 98.74,
    "mediana_positiva": 4_260.00,
}

REFERENCIA_SOCIETARIA = {
    "empresas": 239_600,
    "com_socio": 174_599,
    "controle_definido": 131_423,
    "feminino": 39_904,
    "masculino": 91_519,
    "sem_socio": 65_001,
    "pct_feminino": 30.4,
    "socios_pf": 327_180,
    "pct_socias": 34.3,
}


def fmt_br(valor, casas=0) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fonte_contratos(modo: str) -> str:
    parquet = Path(config.DIR_DADOS_PARQUET) / "contratos"
    if modo in ("auto", "parquet") and parquet.is_dir() and any(parquet.rglob("*.parquet")):
        caminho = str(parquet).replace("\\", "/")
        return f"read_parquet('{caminho}/**/*.parquet', hive_partitioning=true)"

    raw = Path(config.DIR_DADOS_RAW) / "pncp"
    for nome in (f"contratos_{config.ANO_REFERENCIA}_completo.jsonl",
                 f"contratos_{config.ANO_REFERENCIA}.jsonl"):
        arquivo = raw / nome
        if arquivo.is_file() and arquivo.stat().st_size > 0:
            import tratar_contratos
            return f"({tratar_contratos.montar_sql([str(arquivo).replace(chr(92), '/')])})"

    raise SystemExit(
        "ERRO: nao achei contratos nem no Parquet nem no JSONL bruto.\n"
        "  Rode o baixar_pncp.py e o tratar_contratos.py antes, de dentro de etl/."
    )


class Relatorio:

    def __init__(self, tolerancia: float):
        self.tolerancia = tolerancia
        self.divergencias = []

    def secao(self, titulo: str) -> None:
        print()
        print(titulo)
        print("-" * len(titulo))

    def linha(self, rotulo: str, medido, referencia=None, casas=0, pct=False):
        texto = fmt_br(medido, casas) + ("%" if pct else "")
        if referencia is None:
            print(f"  {rotulo:38} {texto:>20}")
            return

        esperado = fmt_br(referencia, casas) + ("%" if pct else "")
        if referencia:
            desvio = abs(medido - referencia) / abs(referencia) * 100
        else:
            desvio = 0.0 if medido == referencia else 100.0

        if desvio <= self.tolerancia:
            print(f"  {rotulo:38} {texto:>20}   ok (ref {esperado})")
        else:
            print(f"  {rotulo:38} {texto:>20}   DIVERGE de {esperado} "
                  f"({desvio:.2f}%)")
            self.divergencias.append((rotulo, medido, referencia, desvio))

    def nao_verificado(self, rotulo: str, motivo: str) -> None:
        print(f"  {rotulo:38} {'nao verificado':>20}   {motivo}")


MARCAS_RN02 = ("contrato_suspeito", "acima_sensibilidade", "elegivel_valor")


def conferir_marcas(con) -> None:
    presentes = {c[0] for c in con.execute(
        "SELECT * FROM contratos LIMIT 0").description}
    faltando = [c for c in MARCAS_RN02 if c not in presentes]
    if faltando:
        raise SystemExit(
            f"ERRO: a fonte nao tem as marcas da RN-02: {', '.join(faltando)}.\n"
            "  O Parquet foi gerado antes de 10/11/2026, quando o tratamento\n"
            "  passou a gravar essas colunas. Regere com, de dentro de etl/:\n"
            "      python tratar_contratos.py\n"
            "  Ou audite direto do bruto, sem regerar nada:\n"
            "      python auditar_kpis.py --fonte raw"
        )


def auditar_contratos(con, fonte: str, rel: Relatorio, referencia: dict) -> int:
    con.execute(f"CREATE OR REPLACE VIEW contratos AS SELECT * FROM {fonte}")
    conferir_marcas(con)

    (total, suspeitos, receita, zerados, elegiveis, sem_raiz,
     raizes) = con.execute("""
        SELECT count(*),
               sum(CASE WHEN contrato_suspeito THEN 1 ELSE 0 END),
               sum(CASE WHEN receita THEN 1 ELSE 0 END),
               sum(CASE WHEN valor_global > 0 THEN 0 ELSE 1 END),
               sum(CASE WHEN elegivel_valor THEN 1 ELSE 0 END),
               sum(CASE WHEN cnpj_raiz_fornecedor IS NULL THEN 1 ELSE 0 END),
               count(DISTINCT cnpj_raiz_fornecedor)
        FROM contratos
    """).fetchone()

    bruto, susp_valor, eleg_valor = con.execute("""
        SELECT sum(valor_global),
               sum(CASE WHEN contrato_suspeito THEN valor_global ELSE 0 END),
               sum(CASE WHEN elegivel_valor THEN valor_global ELSE 0 END)
        FROM contratos
    """).fetchone()

    rel.secao("1. Universo e elegibilidade (RN-01 e RN-02)")
    rel.linha("contratos no recorte", total, referencia.get("contratos"))
    rel.linha("valor bruto somado", float(bruto), referencia.get("valor_bruto"), 2)
    rel.linha("contrato_suspeito (> R$ 1 bi)", suspeitos, referencia.get("suspeitos"))
    rel.linha("share dos suspeitos no valor",
              100 * float(susp_valor) / float(bruto),
              referencia.get("share_suspeitos"), 2, pct=True)
    rel.linha("valor depois do corte", float(eleg_valor + 0),
              referencia.get("valor_com_corte"), 2)
    rel.linha("contratos de receita", receita, referencia.get("receita"))
    rel.linha("valor zero em centavos", zerados)
    rel.linha("elegiveis para indicador de valor", elegiveis)
    rel.linha("sem raiz de CNPJ", sem_raiz, referencia.get("sem_raiz"))
    rel.linha("raizes distintas", raizes)

    rel.secao("2. Conferencia da marca contra o modulo das regras")
    amostra = con.execute("""
        SELECT valor_global, receita, contrato_suspeito, acima_sensibilidade,
               elegivel_valor
        FROM contratos USING SAMPLE 20000 ROWS
    """).fetchall()
    fora = 0
    for valor, rec, susp, sens, eleg in amostra:
        esperado = elegibilidade.marcar(valor, rec)
        if (susp, sens, eleg) != (esperado["contrato_suspeito"],
                                  esperado["acima_sensibilidade"],
                                  esperado["elegivel_valor"]):
            fora += 1
    rel.linha("linhas conferidas na amostra", len(amostra))
    rel.linha("linhas em que SQL e modulo divergem", fora, 0)

    return total


def auditar_societario(con, rel: Relatorio) -> None:
    rel.secao("3. Genero e controle societario (RN-03 a RN-05)")

    base = Path(config.DIR_DADOS_PARQUET) / "receita"
    genero = Path(config.DIR_DADOS_PARQUET).parent / "genero" / "genero_por_empresa.csv"

    if not genero.is_file() and not (base.is_dir() and any(base.glob("*.parquet"))):
        rel.nao_verificado("empresas classificadas", "sem a Receita filtrada nesta maquina")
        rel.nao_verificado("controle feminino", "depende do classificar_empresas.py")
        print()
        print("  A Receita filtrada e o genero_por_empresa.csv ficaram na maquina da T2.")
        print("  Com eles presentes, esta secao recalcula a RN-05 por fora do script")
        print("  que a produziu e compara com os numeros publicados.")
        return

    if genero.is_file():
        caminho = str(genero).replace("\\", "/")
        linhas = con.execute(f"""
            SELECT classificacao, count(*)
            FROM read_csv_auto('{caminho}')
            GROUP BY 1
        """).fetchall()
        contagem = {c: n for c, n in linhas}
        total = sum(contagem.values())
        definido = sum(n for c, n in contagem.items()
                       if controle.controle_definido(c))
        feminino = contagem.get(controle.FEMININO, 0)

        rel.linha("empresas no arquivo", total,
                  REFERENCIA_SOCIETARIA["empresas"])
        rel.linha("com controle definido", definido,
                  REFERENCIA_SOCIETARIA["controle_definido"])
        rel.linha("controle feminino", feminino,
                  REFERENCIA_SOCIETARIA["feminino"])
        if definido:
            rel.linha("% de controle feminino", 100 * feminino / definido,
                      REFERENCIA_SOCIETARIA["pct_feminino"], 1, pct=True)
    else:
        rel.nao_verificado("empresas classificadas",
                           "genero_por_empresa.csv ausente")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fonte", choices=("auto", "parquet", "raw"), default="auto",
                   help="de onde ler os contratos")
    p.add_argument("--tolerancia", type=float, default=0.1,
                   help="desvio percentual aceito antes de acusar divergencia")
    p.add_argument("--amostra", action="store_true",
                   help="comparar com os numeros da amostra de janeiro, nao do ano")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--memoria", default="3GB")
    args = p.parse_args()

    fonte = fonte_contratos(args.fonte)
    referencia = REFERENCIA_AMOSTRA if args.amostra else REFERENCIA_ANO

    print("Auditoria independente dos KPIs")
    print(f"  fonte .......... {fonte[:96]}")
    print(f"  referencia ..... {'amostra de janeiro' if args.amostra else 'ano de 2025'}")
    print(f"  tolerancia ..... {args.tolerancia}%")

    con = duckdb.connect(config={"threads": args.threads})
    con.execute(f"SET memory_limit='{args.memoria}'")
    rel = Relatorio(args.tolerancia)

    try:
        auditar_contratos(con, fonte, rel, referencia)
        auditar_societario(con, rel)
    finally:
        con.close()

    print()
    if rel.divergencias:
        print(f"RESULTADO: {len(rel.divergencias)} divergencia(s) acima da tolerancia.")
        for rotulo, medido, esperado, desvio in rel.divergencias:
            print(f"  - {rotulo}: medido {fmt_br(medido, 2)}, "
                  f"referencia {fmt_br(esperado, 2)} ({desvio:.2f}%)")
        print()
        print("Divergencia nao e necessariamente erro de calculo: pode ser numero")
        print("de referencia velho. Confira contra docs/regras-de-negocio.md antes")
        print("de mexer no codigo.")
        return 1

    print("RESULTADO: nenhuma divergencia acima da tolerancia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
