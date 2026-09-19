"""
Extrator de contratos do PNCP (API publica, sem autenticacao).
==================================================================
Le o recorte de config.py -- NAO troquem as datas aqui, troquem la.

Uso (rodar de dentro de etl/):
    python baixar_pncp.py

Gera: dados/raw/pncp/contratos_2025.jsonl (um contrato JSON por linha)
      dados/raw/pncp/contratos_2025.checkpoint (pagina onde parou)

Se cair no meio (timeout, queda de conexao), rodem o mesmo comando de novo:
ele retoma da pagina seguinte a ultima concluida, sem duplicar nem
sobrescrever o que ja foi baixado.
"""

import json
import time
from pathlib import Path

import requests

import config

BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratos"
TAMANHO_PAGINA = 100  # reduzido de 500 -- paginas menores respondem mais rapido
                       # e caem menos em 504 no servidor do PNCP
TIMEOUT_SEGUNDOS = 90
MAX_TENTATIVAS = 5
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}


def buscar_pagina(pagina: int) -> dict:
    params = {
        "dataInicial": config.DATA_INICIAL_PNCP,
        "dataFinal": config.DATA_FINAL_PNCP,
        "pagina": pagina,
        "tamanhoPagina": TAMANHO_PAGINA,
    }
    # Atencao: /v1/contratos NAO aceita filtro por "uf" (isso so existe em
    # /contratacoes/publicacao). Aqui o unico filtro de recorte por orgao
    # disponivel e por CNPJ especifico.
    if config.ORGAOS_RECORTE:
        params["cnpjOrgao"] = config.ORGAOS_RECORTE[0]  # 1 CNPJ por chamada

    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SEGUNDOS)
            if resp.status_code in STATUS_RETENTAVEIS:
                espera = 5 * tentativa
                print(f"    HTTP {resp.status_code} na pagina {pagina} "
                      f"(tentativa {tentativa}/{MAX_TENTATIVAS}). "
                      f"Esperando {espera}s e tentando de novo...")
                time.sleep(espera)
                continue
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            ultimo_erro = e
            espera = 5 * tentativa  # backoff: 5s, 10s, 15s, 20s, 25s
            print(f"    timeout/conexao na pagina {pagina} "
                  f"(tentativa {tentativa}/{MAX_TENTATIVAS}). "
                  f"Esperando {espera}s e tentando de novo...")
            time.sleep(espera)

    raise RuntimeError(
        f"Pagina {pagina} falhou apos {MAX_TENTATIVAS} tentativas "
        f"(ultimo erro: {ultimo_erro})"
    ) from ultimo_erro


def ler_checkpoint(caminho: Path) -> int:
    if caminho.exists():
        return int(caminho.read_text().strip())
    return 0


def escrever_checkpoint(caminho: Path, pagina: int):
    caminho.write_text(str(pagina))


def main():
    saida_dir = Path(config.DIR_DADOS_RAW) / "pncp"
    saida_dir.mkdir(parents=True, exist_ok=True)
    saida = saida_dir / f"contratos_{config.ANO_REFERENCIA}.jsonl"
    checkpoint = saida_dir / f"contratos_{config.ANO_REFERENCIA}.checkpoint"

    ultima_pagina_ok = ler_checkpoint(checkpoint)
    pagina_inicial = ultima_pagina_ok + 1
    modo_arquivo = "a" if ultima_pagina_ok > 0 else "w"

    if ultima_pagina_ok > 0:
        print(f"== Retomando: ultima pagina concluida foi {ultima_pagina_ok}, "
              f"continuando da pagina {pagina_inicial} ==")
    else:
        print(f"== Baixando contratos PNCP: {config.DATA_INICIAL_PNCP} a "
              f"{config.DATA_FINAL_PNCP} ==")

    pagina = pagina_inicial
    total_gravado = ultima_pagina_ok * TAMANHO_PAGINA  # estimativa p/ log
    with open(saida, modo_arquivo, encoding="utf-8") as f:
        while True:
            dados = buscar_pagina(pagina)
            registros = dados.get("data", dados) if isinstance(dados, dict) else dados
            if not registros:
                break

            for registro in registros:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            f.flush()  # garante que o que foi escrito nao se perde num timeout futuro
            total_gravado += len(registros)
            print(f"  pagina {pagina}: +{len(registros)} contratos "
                  f"(total {total_gravado})")

            escrever_checkpoint(checkpoint, pagina)

            if len(registros) < TAMANHO_PAGINA:
                break  # ultima pagina
            pagina += 1
            time.sleep(0.3)  # educado com a API publica

    print(f"== Concluido: {total_gravado} contratos em {saida} ==")
    checkpoint.unlink(missing_ok=True)  # terminou de verdade, checkpoint nao serve mais


if __name__ == "__main__":
    main()