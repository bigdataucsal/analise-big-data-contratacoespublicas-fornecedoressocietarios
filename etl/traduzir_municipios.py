"""Traduz o codigo de municipio da Receita Federal para o codigo do IBGE."""

import argparse
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import config

ARQUIVO_IBGE = Path(config.DIR_DADOS_PARQUET).parent / "proxy" / "cor_raca_municipio_2022.csv"
DIR_RECEITA = Path(config.DIR_DADOS_RAW) / "receita"
SAIDA = Path(config.DIR_DADOS_PARQUET).parent / "proxy" / "municipios_receita_ibge.csv"


def normalizar(nome: str) -> str:
    if not nome:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(nome))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    sem_apostrofo = re.sub(r"['’`´]", "", sem_acento.upper())
    limpo = re.sub(r"[^A-Za-z0-9 ]", " ", sem_apostrofo)
    return re.sub(r"\s+", " ", limpo).strip()


def carregar_ibge() -> dict:
    if not ARQUIVO_IBGE.is_file():
        raise SystemExit(
            f"ERRO: {ARQUIVO_IBGE} não existe.\n"
            f"       Gere com:  python baixar_proxy_racial.py"
        )
    import csv
    mapa = {}
    with open(ARQUIVO_IBGE, encoding="utf-8", newline="") as f:
        for linha in csv.DictReader(f):
            rotulo = linha.get("municipio", "")
            if " - " in rotulo:
                nome, uf = rotulo.rsplit(" - ", 1)
            else:
                nome, uf = rotulo, ""
            mapa[(normalizar(nome), uf.strip().upper())] = {
                "codigo_ibge": linha["codigo_ibge"],
                "nome_ibge": nome.strip(),
                "uf": uf.strip().upper(),
            }
    return mapa


def carregar_receita():
    import pandas as pd

    zips = sorted(DIR_RECEITA.glob("*.zip"))
    if not zips:
        return None, None

    nomes, ufs_por_codigo = {}, {}
    for caminho in zips:
        with zipfile.ZipFile(caminho) as arq:
            for membro in arq.namelist():
                up = membro.upper()
                if "MUNICCSV" in up:
                    with arq.open(membro) as f:
                        df = pd.read_csv(f, sep=";", header=None,
                                         names=["codigo", "descricao"],
                                         encoding="latin-1", dtype=str,
                                         on_bad_lines="warn")
                    for cod, desc in zip(df["codigo"], df["descricao"]):
                        if cod:
                            nomes[str(cod).strip()] = str(desc or "").strip()
                elif "ESTABELE" in up:
                    with arq.open(membro) as f:
                        for pedaco in pd.read_csv(
                                f, sep=";", header=None, encoding="latin-1",
                                dtype=str, usecols=[19, 20],
                                names=["uf", "municipio"],
                                chunksize=500_000, on_bad_lines="warn"):
                            for uf, mun in zip(pedaco["uf"], pedaco["municipio"]):
                                if mun and uf:
                                    ufs_por_codigo.setdefault(
                                        str(mun).strip(), set()).add(str(uf).strip().upper())
    return nomes, ufs_por_codigo


def main() -> int:
    p = argparse.ArgumentParser(
        description="Traduz o código de município da Receita para o do IBGE")
    p.add_argument("--so-conferir", action="store_true",
                   help="não grava, só mede a cobertura do casamento")
    args = p.parse_args()

    ibge = carregar_ibge()
    print(f"== Tradução de município: Receita -> IBGE ==")
    print(f"   lado IBGE   : {len(ibge)} municípios (Censo 2022)")

    nomes, ufs = carregar_receita()
    if nomes is None:
        print(f"   lado Receita: nenhum .zip em {DIR_RECEITA}")
        print()
        print("   O lado IBGE está pronto. Falta o download da Receita para")
        print("   completar a tradução:")
        print("     python baixar_receita.py")
        print("     python traduzir_municipios.py")
        print()
        print("   Enquanto isso, dim_fornecedor.id_municipio_sede fica nulo, e")
        print("   o proxy territorial da RN-06 não pode ser calculado.")
        return 2

    print(f"   lado Receita: {len(nomes)} códigos no MUNICCSV, "
          f"{len(ufs)} com UF observada nos estabelecimentos")

    pares, sem_uf, sem_par, ambiguos = [], [], [], []
    for codigo, nome in sorted(nomes.items()):
        alvo = normalizar(nome)
        candidatas = ufs.get(codigo, set())

        if not candidatas:
            sem_uf.append((codigo, nome))
            continue

        achados = [ibge[(alvo, uf)] for uf in candidatas if (alvo, uf) in ibge]
        if len(achados) == 1:
            r = achados[0]
            pares.append({
                "codigo_receita": codigo,
                "codigo_ibge": r["codigo_ibge"],
                "nome_receita": nome,
                "nome_ibge": r["nome_ibge"],
                "uf": r["uf"],
            })
        elif len(achados) > 1:
            ambiguos.append((codigo, nome, sorted(candidatas)))
        else:
            sem_par.append((codigo, nome, sorted(candidatas)))

    usados = len(pares) + len(sem_par) + len(ambiguos)
    print(f"\n   códigos que aparecem em estabelecimentos: {usados}")
    print(f"     traduzidos      : {len(pares)}"
          + (f"  ({100*len(pares)/usados:.1f}%)" if usados else ""))
    print(f"     sem par no IBGE : {len(sem_par)}")
    print(f"     ambíguos        : {len(ambiguos)}")
    print(f"   códigos sem UF observada (não usados no recorte): {len(sem_uf)}")

    for rotulo, lista in (("SEM PAR", sem_par), ("AMBÍGUO", ambiguos)):
        if lista:
            print(f"\n   {rotulo} (primeiros 10, confira e corrija à mão se preciso):")
            for item in lista[:10]:
                print(f"     {item[0]:>6}  {item[1][:40]:40}  UF={item[2]}")

    if args.so_conferir:
        print("\n== Só conferência, nada gravado ==")
        return 0 if not (sem_par or ambiguos) else 1

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(SAIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["codigo_receita", "codigo_ibge",
                                          "nome_receita", "nome_ibge", "uf"])
        w.writeheader()
        w.writerows(pares)
    print(f"\n== Gravado em {SAIDA}: {len(pares)} correspondências ==")

    if sem_par or ambiguos:
        print("   ATENÇÃO: a tradução está INCOMPLETA. Os municípios acima não")
        print("   entram no proxy territorial, e isso precisa ser reportado")
        print("   junto de qualquer resultado da RN-06.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
