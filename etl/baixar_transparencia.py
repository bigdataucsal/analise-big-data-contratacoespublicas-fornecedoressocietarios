"""
Uso (rodar de dentro de etl/):
    pip install python-dotenv
    python baixar_transparencia.py

Gera: dados/raw/transparencia/contratos_2025.jsonl

IMPORTANTE: a API da CGU muda de vez em quando o nome exato dos parametros
de data por endpoint. Confiram o endpoint /contratos no Swagger antes de
rodar de verdade:
https://api.portaldatransparencia.gov.br/swagger-ui.html
"""

import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

import config

load_dotenv()

BASE_URL = "https://api.portaldatransparencia.gov.br/api-de-dados/contratos"
API_KEY = os.environ.get("TRANSPARENCIA_API_KEY")


TAMANHO_PAGINA = 500  # confirmado como maximo aceito por outros endpoints da CGU


def buscar_pagina(pagina: int, codigo_orgao: str = None) -> list:
    headers = {"chave-api-dados": API_KEY}
    params = {
        "dataInicial": config.DATA_INICIAL_TRANSPARENCIA,
        "dataFinal": config.DATA_FINAL_TRANSPARENCIA,
        "pagina": pagina,
        "tamanhoPagina": TAMANHO_PAGINA,
    }
    if codigo_orgao:
        params["codigoOrgao"] = codigo_orgao

    resp = requests.get(BASE_URL, headers=headers, params=params, timeout=60)
    if resp.status_code == 401:
        raise RuntimeError(
            "Chave invalida ou ausente. Confiram TRANSPARENCIA_API_KEY no .env."
        )
    if resp.status_code == 400:
        raise RuntimeError(
            "400 Bad Request, provavel causa: este endpoint pode EXIGIR "
            "codigoOrgao junto com as datas (diferente do PNCP, que aceita "
            "so o periodo). Confiram no Swagger: "
            "https://api.portaldatransparencia.gov.br/swagger-ui.html "
            "e, se for o caso, preencham ORGAOS_RECORTE em config.py com a "
            "lista de codigos de orgao (nao CNPJ, e um codigo SIAFI/SIORG "
            "diferente, ver /orgaos-siafi na mesma API)."
        )
    resp.raise_for_status()
    return resp.json()


def main():
    if not API_KEY:
        print("ERRO: defina TRANSPARENCIA_API_KEY no .env antes de rodar.")
        return

    saida_dir = Path(config.DIR_DADOS_RAW) / "transparencia"
    saida_dir.mkdir(parents=True, exist_ok=True)
    saida = saida_dir / f"contratos_{config.ANO_REFERENCIA}.jsonl"

    print(f"== Baixando contratos Portal da Transparencia: "
          f"{config.DATA_INICIAL_TRANSPARENCIA} a {config.DATA_FINAL_TRANSPARENCIA} ==")

    # Se ORGAOS_RECORTE estiver vazio, tentamos sem filtro de orgao primeiro.
    # Se a API responder 400 (ver mensagem de erro acima), preencham
    # ORGAOS_RECORTE em config.py e rodem de novo, o loop abaixo passa a
    # varrer 1 orgao por vez automaticamente.
    lista_orgaos = config.ORGAOS_RECORTE or [None]

    total_gravado = 0
    with open(saida, "w", encoding="utf-8") as f:
        for codigo_orgao in lista_orgaos:
            pagina = 1
            while True:
                registros = buscar_pagina(pagina, codigo_orgao)
                if not registros:
                    break

                for registro in registros:
                    f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                total_gravado += len(registros)
                rotulo = codigo_orgao or "todos"
                print(f"  orgao {rotulo}, pagina {pagina}: +{len(registros)} "
                      f"(total {total_gravado})")

                if len(registros) < TAMANHO_PAGINA:
                    break  # ultima pagina deste orgao
                pagina += 1
                time.sleep(0.5)  # a API da CGU e mais sensivel a rate limit

    print(f"== Concluido: {total_gravado} registros em {saida} ==")


if __name__ == "__main__":
    main()