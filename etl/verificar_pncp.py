"""
verificar_pncp.py  (v2)
Compara o JSONL coletado do PNCP com o totalRegistros da API, dia a dia.

Uso (na pasta etl, venv ativo):
    python verificar_pncp.py                                    # ano todo
    python verificar_pncp.py --inicio 20250101 --fim 20250131   # so janeiro
    python verificar_pncp.py --arquivo C:\\caminho\\outro.jsonl

v2: acha numeroControlePncp / dataPublicacaoPncp em camelCase OU snake_case, no topo
ou aninhado; faz uma sonda da API antes do loop e PARA se a resposta nao for a esperada;
separa 404 (dia vazio) de erro de rede.

Saidas: verificacao_pncp.csv e dias_incompletos.txt. Nao altera o JSONL nem o controle.
"""
import argparse
import csv
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta

import requests

URL = "https://pncp.gov.br/api/consulta/v1/contratos"
ARQUIVO_PADRAO = r"C:\dados-bigdata\raw\pncp\contratos_2025_completo.jsonl"


def norm(k):
    return str(k).lower().replace("_", "")


def achar(obj, alvo, prof=0):
    """Procura a chave 'alvo' (normalizada) em dicts aninhados, ate 3 niveis."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        obj = obj[0]
    if not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        if norm(k) == alvo and not isinstance(v, (dict, list)):
            return v
    if prof < 3:
        for v in obj.values():
            if isinstance(v, (dict, list)):
                r = achar(v, alvo, prof + 1)
                if r is not None:
                    return r
    return None


def ler_jsonl(caminho):
    linhas = invalidas = sem_id = 0
    vistos = {}
    primeira = None
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            linhas += 1
            if primeira is None:
                primeira = linha
            try:
                reg = json.loads(linha)
            except json.JSONDecodeError:
                invalidas += 1
                continue
            chave = achar(reg, "numerocontrolepncp")
            if not chave:
                sem_id += 1
                if linhas == 2000 and sem_id == linhas:   # nenhuma chave nas primeiras 2000
                    break
                continue
            vistos[chave] = str(achar(reg, "datapublicacaopncp") or "")[:10]
    return linhas, invalidas, sem_id, vistos, primeira


def consultar(dia, tentativas=6):
    """Devolve (status_http, totalRegistros|None, trecho_da_resposta)."""
    params = {"dataInicial": dia, "dataFinal": dia, "pagina": 1, "tamanhoPagina": 10}
    ultimo = "sem resposta"
    for t in range(tentativas):
        try:
            r = requests.get(URL, params=params, timeout=60,
                             headers={"Accept": "application/json"})
            if r.status_code == 200:
                try:
                    j = r.json()
                except ValueError:
                    return 200, None, r.text[:200]
                if not isinstance(j, dict) or "totalRegistros" not in j:
                    return 200, None, r.text[:200]
                return 200, int(j["totalRegistros"]), ""
            if r.status_code == 404:
                if "Cannot GET" in r.text or "<html" in r.text[:200].lower():
                    return 404, None, r.text[:200]   # rota errada, nao e colecao vazia
                return 404, 0, r.text[:200]
            if r.status_code in (429, 500, 502, 503, 504):
                ultimo = f"HTTP {r.status_code}"
                time.sleep(min(60, 2 ** t) + random.random())
                continue
            return r.status_code, None, r.text[:200]
        except requests.RequestException as e:
            ultimo = f"{type(e).__name__}: {e}"
            time.sleep(min(60, 2 ** t) + random.random())
    return None, None, ultimo


def dias_do_periodo(ini, fim):
    d = datetime.strptime(ini, "%Y%m%d").date()
    f = datetime.strptime(fim, "%Y%m%d").date()
    while d <= f:
        yield d
        d += timedelta(days=1)


def main():
    global URL
    ap = argparse.ArgumentParser()
    ap.add_argument("--arquivo", default=ARQUIVO_PADRAO)
    ap.add_argument("--inicio", default="20250101")
    ap.add_argument("--fim", default="20251231")
    ap.add_argument("--pausa", type=float, default=1.0)
    ap.add_argument("--url", default=URL, help="endereco do endpoint /v1/contratos")
    args = ap.parse_args()
    URL = args.url

    if not os.path.exists(args.arquivo):
        sys.exit(f"Arquivo nao encontrado: {args.arquivo}")

    print(f"== Lendo {args.arquivo} ==")
    linhas, invalidas, sem_id, vistos, primeira = ler_jsonl(args.arquivo)
    if not vistos:
        print("\nNAO ACHEI numeroControlePncp em nenhuma das primeiras linhas.")
        try:
            reg = json.loads(primeira)
            print("Chaves da primeira linha:", list(reg.keys()) if isinstance(reg, dict) else type(reg))
        except Exception:
            pass
        print("Inicio da primeira linha (mande isto para o Claude):")
        print((primeira or "")[:600])
        sys.exit(1)
    por_dia = Counter(vistos.values())
    dup = linhas - invalidas - sem_id - len(vistos)
    print(f"   linhas: {linhas:,} | invalidas: {invalidas} | sem chave: {sem_id}")
    print(f"   contratos unicos: {len(vistos):,} | duplicatas: {dup:,}")
    print(f"   publicacao de {min(por_dia)} ate {max(por_dia)}")

    # --- sonda: um dia com muito dado local ---
    dia_sonda = max(por_dia, key=por_dia.get)
    print(f"\n== Sonda da API no dia mais cheio do seu arquivo ({dia_sonda}: {por_dia[dia_sonda]:,} contratos) ==")
    status, total, trecho = consultar(dia_sonda.replace("-", ""))
    print(f"   HTTP {status} | totalRegistros: {total}")
    if trecho:
        print(f"   resposta: {trecho}")
    if status != 200 or total is None:
        if "Cannot GET" in (trecho or ""):
            print("\nO endereco da API parece errado (rota nao encontrada). Confira o endereco")
            print(f"usado: {URL}")
            print("e compare com o que o seu baixar_pncp_rapido.py usa; passe com --url se precisar.")
        print("\nA API nao respondeu como esperado; a comparacao nao tem como rodar agora.")
        print("Mande esta sonda para o Claude. O que vale ate la: a coleta terminou (365 dias")
        print("concluidos no controle) e o tratamento deduplicou 2.023.134 contratos.")
        sys.exit(2)
    print(f"   (API: {total:,} | local: {por_dia[dia_sonda]:,})")

    dias = list(dias_do_periodo(args.inicio, args.fim))
    print(f"\n== Consultando a API: {len(dias)} dias ({args.inicio} a {args.fim}) ==")
    resultados, n404, nerro = [], 0, 0
    for i, d in enumerate(dias, 1):
        dia = d.strftime("%Y%m%d")
        st, api, msg = consultar(dia)
        loc = por_dia.get(d.isoformat(), 0)
        if api is None:
            status_dia = "ERRO_API"; nerro += 1
        elif st == 404:
            n404 += 1
            status_dia = "ok" if loc == 0 else "API_404_MAS_LOCAL_TEM"
        elif loc >= api:
            status_dia = "ok"
        else:
            status_dia = "INCOMPLETO"
        resultados.append((dia, api, loc, status_dia))
        if i % 30 == 0:
            print(f"   {i}/{len(dias)} dias consultados")
        time.sleep(args.pausa)

    with open("verificacao_pncp.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["dia", "total_api", "total_local", "diferenca", "status"])
        for dia, api, loc, st in resultados:
            w.writerow([dia, api, loc, (loc - api) if api is not None else "", st])
    incompletos = [r for r in resultados if r[3] == "INCOMPLETO"]
    with open("dias_incompletos.txt", "w", encoding="utf-8") as f:
        for r in incompletos:
            f.write(r[0] + "\n")

    soma_api = sum(r[1] for r in resultados if r[1] is not None)
    soma_loc = sum(r[2] for r in resultados)
    print("\n== RESULTADO ==")
    print(f"   total segundo a API : {soma_api:,}")
    print(f"   total no seu arquivo: {soma_loc:,}")
    if soma_api:
        print(f"   cobertura           : {100 * soma_loc / soma_api:.2f}%")
    print(f"   dias: {len(dias)} | 404 (vazio): {n404} | erro de API: {nerro} | incompletos: {len(incompletos)}")
    if soma_api == 0 and soma_loc > 0:
        print("   ATENCAO: a API devolveu 0 no periodo todo; verificacao INVALIDA, nao e cobertura.")
    for dia, api, loc, st in sorted(incompletos, key=lambda r: r[2] - r[1])[:10]:
        print(f"      {dia}: API={api:,} local={loc:,} (faltam {api - loc:,})")
    print("   detalhe em verificacao_pncp.csv; dias a refazer em dias_incompletos.txt")


if __name__ == "__main__":
    main()