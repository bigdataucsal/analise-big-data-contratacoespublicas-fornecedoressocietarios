"""Composicao de cor ou raca por municipio, do Censo 2022."""

import argparse
import sys
import time
from pathlib import Path

import requests

API = "https://servicodados.ibge.gov.br/api/v3/agregados"
CATEGORIAS = {
    "2776": "branca",
    "2777": "preta",
    "2778": "amarela",
    "2779": "parda",
    "2780": "indigena",
}
TIMEOUT = 300
MAX_TENTATIVAS = 4


def valor_para_int(bruto):
    if bruto is None:
        return None
    texto = str(bruto).strip()
    if texto == "-":
        return 0
    if texto in ("", "..", "...", "X"):
        return None
    try:
        return int(float(texto))
    except ValueError:
        return None


def buscar(agregado: str, ano: str, classificacao: str) -> list:
    url = f"{API}/{agregado}/periodos/{ano}/variaveis/93"
    params = {"localidades": "N6[all]", "classificacao": classificacao}
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            if tentativa == MAX_TENTATIVAS:
                raise
            print(f"   tentativa {tentativa} falhou ({type(e).__name__}), "
                  f"esperando...", flush=True)
            time.sleep(5 * tentativa)
            continue
        if resp.status_code >= 500 or resp.status_code == 429:
            time.sleep(5 * tentativa)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"agregado {agregado} falhou apos {MAX_TENTATIVAS} tentativas")


def extrair(payload: list, ano: str, com_sexo: bool) -> dict:
    municipios = {}
    for variavel in payload:
        for resultado in variavel.get("resultados", []):
            classes = {}
            for c in resultado.get("classificacoes", []):
                cat = c.get("categoria", {})
                if cat:
                    codigo = next(iter(cat))
                    classes[c.get("id")] = (codigo, cat[codigo])

            cor = classes.get("86", (None, None))[0]
            if cor not in CATEGORIAS:
                continue
            nome_cor = CATEGORIAS[cor]
            sufixo = ""
            if com_sexo:
                sexo = classes.get("2", (None, None))[0]
                if sexo == "4":
                    sufixo = "_homens"
                elif sexo == "5":
                    sufixo = "_mulheres"
                else:
                    continue

            for serie in resultado.get("series", []):
                loc = serie.get("localidade", {})
                cod = loc.get("id")
                if not cod:
                    continue
                reg = municipios.setdefault(cod, {
                    "codigo_ibge": cod,
                    "municipio": loc.get("nome", ""),
                })
                reg[nome_cor + sufixo] = valor_para_int(
                    serie.get("serie", {}).get(ano))
    return municipios


def main() -> int:
    p = argparse.ArgumentParser(
        description="Baixa a composicao de cor ou raca por municipio (Censo/SIDRA)")
    p.add_argument("--ano", default="2022", choices=["2010", "2022"],
                   help="periodo do censo (padrao: 2022)")
    p.add_argument("--com-sexo", action="store_true",
                   help="usa o agregado 9606 e quebra tambem por sexo")
    p.add_argument("--saida", default="dados/proxy", help="pasta de saida")
    args = p.parse_args()

    agregado = "9606" if args.com_sexo else "9605"
    cats = ",".join(CATEGORIAS)
    classificacao = f"86[{cats}]|2[4,5]|287[100362]" if args.com_sexo else f"86[{cats}]"

    print(f"== Composicao de cor ou raca por municipio ==")
    print(f"   IBGE, Censo {args.ano}, agregado {agregado}, todos os municipios")
    print(f"   baixando (uma resposta grande, pode levar um minuto)...", flush=True)

    inicio = time.time()
    payload = buscar(agregado, args.ano, classificacao)
    municipios = extrair(payload, args.ano, args.com_sexo)
    print(f"   {len(municipios)} municipios em {time.time()-inicio:.0f}s")

    if not municipios:
        print("ERRO: nenhuma linha extraida, a estrutura da resposta mudou?")
        return 1

    colunas_cor = list(CATEGORIAS.values())
    if args.com_sexo:
        colunas_cor = [c + s for c in CATEGORIAS.values()
                       for s in ("_homens", "_mulheres")]

    linhas = []
    for cod in sorted(municipios):
        r = municipios[cod]
        valores = {c: r.get(c) for c in colunas_cor}
        indefinido = any(v is None for v in valores.values())
        total = None if indefinido else sum(valores.values())
        negra = None if indefinido else sum(
            v for k, v in valores.items()
            if k.startswith("preta") or k.startswith("parda"))
        linhas.append({
            "codigo_ibge": cod,
            "municipio": r.get("municipio", ""),
            "ano_censo": args.ano,
            **valores,
            "total": total,
            "pct_negra": round(100 * negra / total, 4) if total else None,
        })

    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"cor_raca_municipio_{args.ano}" + ("_por_sexo" if args.com_sexo else "")
    csv = destino / f"{nome}.csv"
    cabecalho = list(linhas[0].keys())
    with open(csv, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(cabecalho) + "\n")
        for l in linhas:
            campos = []
            for c in cabecalho:
                v = l[c]
                if isinstance(v, str) and ("," in v or '"' in v):
                    v = '"' + v.replace('"', '""') + '"'
                campos.append("" if v is None else str(v))
            f.write(",".join(campos) + "\n")

    sem_dado = sum(1 for l in linhas if not l["total"])
    indefinidos = sum(1 for l in linhas if l["total"] is None)
    pcts = sorted(l["pct_negra"] for l in linhas if l["pct_negra"] is not None)
    print(f"\n== Gravado em {csv} ==")
    print(f"   {len(linhas)} municipios, {len(cabecalho)} colunas")
    if indefinidos:
        print(f"   {indefinidos} municipio(s) com alguma categoria nao medida "
              f"('...' no SIDRA), total e percentual ficaram nulos")
    elif sem_dado:
        print(f"   ATENCAO: {sem_dado} municipio(s) com total zero")
    if pcts:
        meio = pcts[len(pcts)//2]
        print(f"\n   percentual de populacao negra (preta + parda) por municipio:")
        print(f"     minimo  {pcts[0]:>6.1f}%   mediana {meio:>6.1f}%   "
              f"maximo {pcts[-1]:>6.1f}%")
    print(f"\n   Fonte para citar: IBGE, Censo Demografico {args.ano}, "
          f"tabela {agregado} (SIDRA).")
    print(f"   Este indicador descreve o MUNICIPIO, nunca uma pessoa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
