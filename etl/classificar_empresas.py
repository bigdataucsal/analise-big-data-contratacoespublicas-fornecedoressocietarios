"""
Classificacao de genero das EMPRESAS do recorte (RN-03, RN-04 e RN-05).
=====================================================================
O inferir_genero.py classifica nomes. Este script sobe um degrau: le os socios
das empresas do recorte no Parquet gerado pelo filtro da Receita, aplica as
tres regras e diz, para cada empresa, se o controle e feminino, masculino ou
misto/indeterminado.

    RN-03  so entram socios pessoa fisica cuja qualificacao indique
           participacao ou administracao. Procurador e representante ficam de
           fora. A regra e por PALAVRA na descricao da qualificacao (padrao:
           PROCURADOR e REPRESENTANTE) e o relatorio imprime todas as
           qualificacoes presentes, marcando quais entram, para o grupo revisar.
           Atencao: isso NAO e a lista de codigos da RN-03. No recorte nacional
           a regra por palavra nao tirou nenhuma linha, e entraram o 53 (socio
           sem capital), o 54 e o 59, que a lista deixa de fora. A divergencia
           esta declarada na RN-03; alinhar na Fase 2.
    RN-04  primeiro nome classificado pela API do Censo 2022 (limiar de 90%),
           com o cache do inferir_genero.py. Nome sem primeiro nome utilizavel
           conta como indeterminado.
    RN-05  empresa feminina se mais de 50% dos socios elegiveis sao femininos;
           masculina no caso simetrico; MISTO OU INDETERMINADO quando ha socio
           pessoa juridica, quando a taxa de indeterminados passa de um terco
           ou quando nenhum dos lados passa de 50%.

Decisoes minhas que o grupo precisa confirmar
---------------------------------------------
1. Socio estrangeiro (identificador 3) NAO entra na contagem de genero e nao
   aciona a regra de socio pessoa juridica. Aparece contado a parte. A RN-05
   so cita socio PJ, e o roteiro so exclui o REPRESENTANTE de socio estrangeiro.
2. Empresa sem nenhuma linha de socio na base (empresario individual, MEI...)
   nao tem controle inferivel: fica em "sem_socio_na_base", fora dos
   percentuais de classificacao. O relatorio mostra as naturezas juridicas mais
   comuns nesse grupo.
3. O denominador dos percentuais da RN-05 e o total de socios ELEGIVEIS,
   incluindo os indeterminados, como o enunciado da regra diz.

Privacidade (RN-09)
-------------------
Nenhum nome de socio e gravado. O cache guarda so o primeiro nome com as
frequencias (o mesmo do inferir_genero.py), e o CSV de saida e por empresa,
com o CNPJ basico e contagens, sem nome e sem documento.

Colunas usadas em dados/parquet/receita/ (nomes do Parquet, que diferem dos do
CSV bruto):
    sociocsv.parquet : cnpj_basico, identificador_socio, nome_socio_razao_social,
                       qualificacao_socio          (identificador: 1=PJ, 2=PF, 3=estrangeiro)
    qualscsv.parquet : codigo, descricao_qualificacao_socio
    emprecsv.parquet : cnpj_basico, natureza_juridica
    natjucsv.parquet : codigo, descricao_natureza_juridica     (opcional)

Uso (rodar de dentro de etl/):
    python classificar_empresas.py
    python classificar_empresas.py --limiar 0.95
    python classificar_empresas.py --excluir-palavras "PROCURADOR,REPRESENTANTE,CURADOR"
"""

import argparse
import csv
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb
import requests

import config
from inferir_genero import (INTERVALO_PADRAO, LIMIAR_PADRAO, Cache, classificar,
                            frequencia, normalizar, primeiro_nome)

BASE = Path(__file__).resolve().parent                      # .../etl
PALAVRAS_EXCLUIDAS_PADRAO = "PROCURADOR,REPRESENTANTE"
LIMITE_INDETERMINADOS = 1 / 3


def cod(valor) -> str:
    """Codigo sem zeros a esquerda, para casar '05' com '5'."""
    texto = str(valor).strip()
    return texto.lstrip("0") or "0"


def ler(con, arquivo: str, colunas, obrigatorio=True):
    caminho = Path(config.DIR_DADOS_PARQUET) / "receita" / arquivo
    if not caminho.is_file():
        if obrigatorio:
            raise SystemExit(f"ERRO: {caminho} nao existe.")
        return []
    caminho_sql = str(caminho).replace(chr(92), "/")
    return con.execute(
        f"SELECT {', '.join(colunas)} FROM read_parquet('{caminho_sql}')").fetchall()


def classificar_empresa(n_f: int, n_m: int, n_ind: int, tem_pj: bool):
    """RN-05. Devolve (classificacao, motivo)."""
    n = n_f + n_m + n_ind
    if tem_pj:
        return "misto_ou_indeterminado", "socio_pj"
    if n == 0:
        return "indeterminado", "sem_socio_elegivel"
    if n_ind / n > LIMITE_INDETERMINADOS:
        return "misto_ou_indeterminado", "muitos_indeterminados"
    if n_f / n > 0.5:
        return "feminino", "maioria"
    if n_m / n > 0.5:
        return "masculino", "maioria"
    return "misto_ou_indeterminado", "sem_maioria"


def pct(parte, todo) -> str:
    return f"{100 * parte / todo:5.1f}%" if todo else "  n/d "


def main() -> int:
    p = argparse.ArgumentParser(description="Genero das empresas do recorte (RN-03/04/05)")
    p.add_argument("--limiar", type=float, default=LIMIAR_PADRAO)
    p.add_argument("--intervalo", type=float, default=INTERVALO_PADRAO,
                   help=f"segundos entre requisicoes (padrao: {INTERVALO_PADRAO})")
    p.add_argument("--excluir-palavras", default=PALAVRAS_EXCLUIDAS_PADRAO,
                   help="palavras (separadas por virgula) que tiram uma qualificacao "
                        f"da conta de genero (padrao: {PALAVRAS_EXCLUIDAS_PADRAO})")
    p.add_argument("--saida", default=str(BASE / "dados" / "genero"))
    args = p.parse_args()

    palavras = [normalizar(x) for x in args.excluir_palavras.split(",") if x.strip()]
    con = duckdb.connect()

    socios = ler(con, "sociocsv.parquet",
                 ["cnpj_basico", "identificador_socio", "nome_socio_razao_social",
                  "qualificacao_socio"])
    empresas = ler(con, "emprecsv.parquet", ["cnpj_basico", "natureza_juridica"])
    quals = {cod(c): d for c, d in ler(
        con, "qualscsv.parquet", ["codigo", "descricao_qualificacao_socio"])}
    naturezas = {cod(c): d for c, d in ler(
        con, "natjucsv.parquet", ["codigo", "descricao_natureza_juridica"], obrigatorio=False)}

    def excluida(descricao: str) -> bool:
        d = normalizar(descricao or "")
        return any(pal in d for pal in palavras)

    # --- separa os socios por empresa ---
    por_empresa, tipo, quals_pf = {}, Counter(), Counter()
    for cnpj, ident, nome, qual in socios:
        ident = str(ident).strip()
        tipo[ident] += 1
        e = por_empresa.setdefault(
            cnpj, {"nomes": [], "pj": False, "estrangeiro": 0, "excluidos": 0})
        if ident == "1":
            e["pj"] = True
        elif ident == "3":
            e["estrangeiro"] += 1
        elif ident == "2":
            descricao = quals.get(cod(qual), f"codigo {qual}")
            quals_pf[(cod(qual), descricao)] += 1
            if excluida(descricao):
                e["excluidos"] += 1
            else:
                e["nomes"].append(primeiro_nome(nome or ""))    # '' = sem primeiro nome

    distintos = sorted({pn for e in por_empresa.values() for pn in e["nomes"] if pn})
    cache = Cache(BASE / "dados" / "cache" / "nomes_ibge_2022.json")
    a_consultar = [n for n in distintos if cache.get(n) is None]

    print(f"== Genero das empresas do recorte (RN-03, RN-04, RN-05; limiar {args.limiar:.0%}) ==")
    print(f"   empresas no recorte (emprecsv)      : {len(empresas):,}")
    print(f"   empresas com linha de socio         : {len(por_empresa):,}")
    print(f"   linhas de socios                    : {len(socios):,} "
          f"(PF {tipo['2']:,} | PJ {tipo['1']:,} | estrangeiro {tipo['3']:,})")
    print(f"   primeiros nomes distintos (elegiveis): {len(distintos):,}; "
          f"{len(cache)} no cache, {len(a_consultar)} a consultar\n")

    # --- consulta o que falta (o cache e salvo mesmo se a rodada cair no meio) ---
    sessao = requests.Session()
    inicio = time.time()
    try:
        for i, nome in enumerate(a_consultar, 1):
            if i > 1:
                time.sleep(args.intervalo)
            f, m = frequencia(sessao, nome)
            cache.put(nome, {"f": f, "m": m, "consultado_em": date.today().isoformat()})
            if i % 50 == 0 or i == len(a_consultar):
                cache.salvar()
                print(f"   {i}/{len(a_consultar)} consultados "
                      f"({(time.time()-inicio)/60:.1f} min)", flush=True)
    finally:
        cache.salvar()

    # --- classifica os socios e depois as empresas ---
    def classe_socio(pn: str) -> str:
        if not pn:
            return "indeterminado"
        d = cache.get(pn) or {"f": 0, "m": 0}
        return classificar(d["f"], d["m"], args.limiar)[0]

    linhas, classes_socio, resultado = [], Counter(), Counter()
    for cnpj, natureza in empresas:
        e = por_empresa.get(cnpj)
        if e is None:
            resultado[("sem_socio_na_base", "")] += 1
            linhas.append((cnpj, 0, 0, 0, 0, "", 0, 0, "sem_socio_na_base", ""))
            continue
        cont = Counter(classe_socio(pn) for pn in e["nomes"])
        for c, n in cont.items():
            classes_socio[c] += n
        n_f, n_m, n_ind = cont["feminino"], cont["masculino"], cont["indeterminado"]
        classe, motivo = classificar_empresa(n_f, n_m, n_ind, e["pj"])
        resultado[(classe, motivo)] += 1
        linhas.append((cnpj, n_f + n_m + n_ind, n_f, n_m, n_ind, "sim" if e["pj"] else "nao",
                       e["excluidos"], e["estrangeiro"], classe, motivo))

    total_socios = sum(classes_socio.values())

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    csv_saida = destino / "genero_por_empresa.csv"
    with open(csv_saida, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["cnpj_basico", "socios_elegiveis", "feminino", "masculino", "indeterminado",
                    "tem_socio_pj", "socios_excluidos_rn03", "socios_estrangeiros",
                    "classificacao_empresa", "motivo"])
        w.writerows(linhas)

    # --- relatorio ---
    print("\n== Qualificacoes dos socios pessoa fisica (RN-03) ==")
    print("   conferir: quem esta como EXCLUIDA sai da conta de genero")
    for (c, descricao), n in quals_pf.most_common(15):
        marca = "EXCLUIDA" if excluida(descricao) else "entra"
        print(f"   {c:>3}  {descricao[:46]:46} {n:>6}  {marca}")
    if len(quals_pf) > 15:
        print(f"   ... e mais {len(quals_pf) - 15} qualificacoes")

    # O rotulo de AMOSTRA que saia aqui ficou da primeira rodada; a rodada
    # nacional (docs/evidencias/classificacao_genero.txt) saiu com ele por engano.
    print(f"\n== Socios elegiveis: {total_socios:,} ==")
    for c in ("feminino", "masculino", "indeterminado"):
        print(f"   {c:15} {classes_socio[c]:>7,} ({pct(classes_socio[c], total_socios)})")
    print(f"   TAXA DE INDETERMINADOS POR SOCIO: {pct(classes_socio['indeterminado'], total_socios).strip()}")

    com_socio = sum(n for (c, _), n in resultado.items() if c != "sem_socio_na_base")
    definidas = resultado[("feminino", "maioria")] + resultado[("masculino", "maioria")]
    print(f"\n== Empresas (RN-05): {len(empresas):,} no recorte ==")
    for (classe, motivo), n in sorted(resultado.items(), key=lambda kv: -kv[1]):
        rotulo = f"{classe}" + (f" ({motivo})" if motivo else "")
        print(f"   {rotulo:52} {n:>6,}  {pct(n, len(empresas))}")
    print(f"\n   empresas com controle definido (feminino ou masculino):")
    print(f"     {definidas:,} de {com_socio:,} com socio na base ({pct(definidas, com_socio).strip()})")
    print(f"     {definidas:,} de {len(empresas):,} no recorte ({pct(definidas, len(empresas)).strip()})")

    sem_socio = [n for c, n in empresas if c not in por_empresa]
    if sem_socio:
        print(f"\n   naturezas juridicas das {len(sem_socio):,} empresas sem socio na base:")
        for n, q in Counter(cod(n) for n in sem_socio).most_common(5):
            print(f"     {n:>5}  {naturezas.get(n, 'sem descricao')[:55]:55} {q:>6,}")

    print(f"\n   detalhe por empresa em {csv_saida}")
    print("   (CNPJ basico e contagens; sem nome e sem documento)")
    return 0


if __name__ == "__main__":
    sys.exit(main())