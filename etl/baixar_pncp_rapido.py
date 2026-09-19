"""
Extrator rapido de contratos do PNCP.
=====================================================================
Mesma fonte do baixar_pncp.py, mas trocando a estrategia de varredura.
NAO substitui o baixar_pncp.py nem mexe nos arquivos que ele gerou
(contratos_2025.jsonl / contratos_2025.checkpoint continuam intactos).

Por que o original demora
-------------------------
Ele pagina o ano inteiro de uma vez: 2.023.236 contratos / 100 por
pagina = 20.233 requisicoes. Pior, a API do PNCP pagina por
deslocamento, entao o custo cresce com o numero da pagina. Medido:

    pagina 1     (tamanhoPagina=500) ->  12 s
    pagina 4000  (tamanhoPagina=500) ->  52 s

Ou seja, quanto mais o download avanca, mais lento ele fica. Nesse
ritmo a varredura completa nao termina em tempo util.

O que este script faz diferente
-------------------------------
1. Quebra o periodo em janelas de 1 dia. Cada dia tem ~5.500 contratos
   = no maximo ~18 paginas, entao TODA requisicao e uma pagina rasa
   (~2 s) e o custo por pagina para de crescer.
2. tamanhoPagina=500, que e o maximo aceito (1000 responde 400).
3. Baixa varios dias em paralelo, reaproveitando conexao.
4. Segura o ritmo sozinho: a API devolve 429 quando apertamos demais,
   entao cada 429 aumenta a pausa global e sequencias de sucesso a
   reduzem de volta.

Medido nas mesmas condicoes:
    original  (paginacao profunda, sequencial) ->     ~7 registros/s
    este      (janela diaria, 3 paralelos)     ->   ~780 registros/s

Uso (rodar de dentro de etl/):
    python baixar_pncp_rapido.py
    python baixar_pncp_rapido.py --workers 6
    python baixar_pncp_rapido.py --de 20250101 --ate 20250107   # teste curto
    python baixar_pncp_rapido.py --verificar                    # so confere

Saida: dados/raw/pncp/diario/contratos_AAAA-MM-DD.jsonl (um shard por dia)

Cada dia so e renomeado para o nome final depois de baixado inteiro, entao
shard que existe e shard completo. Se cair no meio, rode o mesmo comando:
ele pula os dias ja prontos. Nao ha arquivo de checkpoint -- os proprios
shards sao o checkpoint.
"""

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

import config

BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratos"
TAMANHO_PAGINA = 500       # maximo aceito pela API; 1000 responde 400
TIMEOUT_SEGUNDOS = 120
MAX_TENTATIVAS = 6
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}
WORKERS_PADRAO = 3         # medido: 3 nao gerou nenhum 429; 4 ja gerou; 12 derrubou metade


class Regulador:
    """Ritmo global compartilhado entre as threads.

    A API do PNCP nao publica o limite e nao manda Retry-After, entao
    descobrimos na pratica: cada 429 aumenta a pausa entre requisicoes e
    uma sequencia de sucessos vai reduzindo de volta.

    Subida suave (1.8x) e teto baixo (5s) de proposito: com 2x e teto de
    10s, dois 429 simultaneos levavam a pausa a 9.6s e a rodada inteira
    passava a arrastar. Melhor perder um pouco de pico e manter o ritmo.
    """

    def __init__(self, pausa_inicial: float = 0.15, pausa_max: float = 5.0):
        self._lock = threading.Lock()
        self._pausa_min = pausa_inicial
        self._pausa = pausa_inicial
        self._pausa_max = pausa_max
        self._sucessos = 0
        self.total_429 = 0

    def aguardar(self):
        with self._lock:
            pausa = self._pausa
        time.sleep(pausa * random.uniform(0.7, 1.3))  # jitter: evita sincronia

    def penalizar(self) -> float:
        with self._lock:
            self._pausa = min(self._pausa * 1.8, self._pausa_max)
            self._sucessos = 0
            self.total_429 += 1
            return self._pausa

    def premiar(self):
        with self._lock:
            self._sucessos += 1
            if self._sucessos >= 10 and self._pausa > self._pausa_min:
                self._pausa = max(self._pausa / 1.5, self._pausa_min)
                self._sucessos = 0

    @property
    def pausa_atual(self) -> float:
        with self._lock:
            return self._pausa


def criar_sessao(workers: int) -> requests.Session:
    """Sessao com pool de conexoes do tamanho do paralelismo.

    Sem isso o urllib3 refaz o TLS a cada requisicao e avisa que descartou
    conexao -- com 500 registros por resposta isso pesa.
    """
    sessao = requests.Session()
    adaptador = requests.adapters.HTTPAdapter(
        pool_connections=workers, pool_maxsize=workers, max_retries=0
    )
    sessao.mount("https://", adaptador)
    sessao.headers.update({"Accept": "application/json"})
    return sessao


def buscar_pagina(sessao, regulador, dia: str, pagina: int):
    """Uma pagina de um dia. Devolve o dict da API, ou None se a pagina
    nao existe (a API responde 400, nao vazio, quando pagina > total)."""
    params = {
        "dataInicial": dia,
        "dataFinal": dia,
        "pagina": pagina,
        "tamanhoPagina": TAMANHO_PAGINA,
    }
    if config.ORGAOS_RECORTE:
        params["cnpjOrgao"] = config.ORGAOS_RECORTE[0]

    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        regulador.aguardar()
        try:
            resp = sessao.get(BASE_URL, params=params, timeout=TIMEOUT_SEGUNDOS)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            ultimo_erro = e
            time.sleep(min(2 ** tentativa, 30) * random.uniform(0.8, 1.2))
            continue

        if resp.status_code == 204:                 # dia sem contratos
            regulador.premiar()
            return {"data": [], "totalPaginas": 0, "totalRegistros": 0}

        if resp.status_code == 400 and pagina > 1:  # passou do fim do dia
            return None

        if resp.status_code in STATUS_RETENTAVEIS:
            ultimo_erro = f"HTTP {resp.status_code}"
            if resp.status_code == 429:
                nova_pausa = regulador.penalizar()
                print(f"    [429] {dia} p{pagina}: ritmo global -> "
                      f"{nova_pausa:.2f}s entre requisicoes", flush=True)
            cabecalho = resp.headers.get("Retry-After")
            espera = float(cabecalho) if cabecalho else min(2 ** tentativa, 30)
            time.sleep(espera * random.uniform(0.8, 1.2))
            continue

        resp.raise_for_status()
        regulador.premiar()
        return resp.json()

    raise RuntimeError(
        f"{dia} pagina {pagina} falhou apos {MAX_TENTATIVAS} tentativas "
        f"(ultimo erro: {ultimo_erro})"
    )


def baixar_dia(sessao, regulador, dia: date, destino_dir: Path):
    """Baixa um dia inteiro para o seu proprio shard.

    Escreve num .parcial e so renomeia no fim: shard com nome final e
    sempre um dia completo, o que torna o resume seguro sem checkpoint.
    """
    rotulo = dia.isoformat()
    destino = destino_dir / f"contratos_{rotulo}.jsonl"
    if destino.exists():
        return (rotulo, 0, True)

    dia_api = dia.strftime("%Y%m%d")
    parcial = destino_dir / f"contratos_{rotulo}.jsonl.parcial"

    primeira = buscar_pagina(sessao, regulador, dia_api, 1)
    total_paginas = primeira.get("totalPaginas", 0) or 0
    gravados = 0

    with open(parcial, "w", encoding="utf-8") as f:
        for registro in primeira.get("data", []):
            f.write(json.dumps(registro, ensure_ascii=False) + "\n")
            gravados += 1

        for pagina in range(2, total_paginas + 1):
            dados = buscar_pagina(sessao, regulador, dia_api, pagina)
            if dados is None:
                break
            registros = dados.get("data", [])
            if not registros:
                break
            for registro in registros:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
                gravados += 1

        f.flush()
        os.fsync(f.fileno())  # so entao o rename abaixo vale como "pronto"

    parcial.replace(destino)
    return (rotulo, gravados, False)


def dias_do_periodo(de: str, ate: str):
    inicio = datetime.strptime(de, "%Y%m%d").date()
    fim = datetime.strptime(ate, "%Y%m%d").date()
    atual = inicio
    while atual <= fim:
        yield atual
        atual += timedelta(days=1)


def verificar(destino_dir: Path, de: str, ate: str) -> int:
    """Confere o que foi baixado: dias faltando, linhas e duplicatas."""
    dias = list(dias_do_periodo(de, ate))
    faltando, total, vistos, duplicados = [], 0, set(), 0

    for dia in dias:
        caminho = destino_dir / f"contratos_{dia.isoformat()}.jsonl"
        if not caminho.exists():
            faltando.append(dia.isoformat())
            continue
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                total += 1
                try:
                    reg = json.loads(linha)
                except json.JSONDecodeError:
                    print(f"  ATENCAO: linha invalida em {caminho.name}")
                    continue
                chave = (reg.get("numeroControlePncpCompra"),
                         reg.get("sequencialContrato"))
                if chave in vistos:
                    duplicados += 1
                else:
                    vistos.add(chave)

    detalhe_faltando = ""
    if faltando:
        detalhe_faltando = " -> " + ", ".join(faltando[:10])
        if len(faltando) > 10:
            detalhe_faltando += " ..."

    print(f"== Verificacao de {destino_dir} ==")
    print(f"  dias no periodo : {len(dias)}")
    print(f"  dias baixados   : {len(dias) - len(faltando)}")
    print(f"  dias faltando   : {len(faltando)}{detalhe_faltando}")
    print(f"  registros       : {total}")
    print(f"  contratos unicos: {len(vistos)}")
    print(f"  duplicados      : {duplicados}")

    parciais = list(destino_dir.glob("*.parcial"))
    if parciais:
        print(f"  ATENCAO: {len(parciais)} shard(s) .parcial de uma execucao "
              f"interrompida -- serao refeitos na proxima rodada")
    return 0 if not faltando else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Extrator rapido de contratos do PNCP")
    p.add_argument("--de", default=config.DATA_INICIAL_PNCP,
                   help="data inicial AAAAMMDD (padrao: config.py)")
    p.add_argument("--ate", default=config.DATA_FINAL_PNCP,
                   help="data final AAAAMMDD (padrao: config.py)")
    p.add_argument("--workers", type=int, default=WORKERS_PADRAO,
                   help=f"dias baixados em paralelo (padrao: {WORKERS_PADRAO}; "
                        f"a partir de 4 a API ja devolve 429)")
    p.add_argument("--saida", default=None,
                   help="pasta de saida (padrao: dados/raw/pncp/diario)")
    p.add_argument("--verificar", action="store_true",
                   help="nao baixa nada, so confere o que ja existe")
    args = p.parse_args()

    destino_dir = (Path(args.saida) if args.saida
                   else Path(config.DIR_DADOS_RAW) / "pncp" / "diario")
    destino_dir.mkdir(parents=True, exist_ok=True)

    if args.verificar:
        return verificar(destino_dir, args.de, args.ate)

    dias = list(dias_do_periodo(args.de, args.ate))
    pendentes = [d for d in dias
                 if not (destino_dir / f"contratos_{d.isoformat()}.jsonl").exists()]
    prontos = len(dias) - len(pendentes)

    print(f"== PNCP rapido: {args.de} a {args.ate} ==")
    print(f"   {len(dias)} dias no periodo, {prontos} ja baixados, "
          f"{len(pendentes)} pendentes")
    print(f"   {args.workers} dias em paralelo, {TAMANHO_PAGINA} registros/pagina")
    print(f"   saida: {destino_dir}")
    if not pendentes:
        print("== Nada a fazer: todos os dias ja estao baixados ==")
        return 0

    regulador = Regulador()
    sessao = criar_sessao(args.workers)
    inicio = time.time()
    total_registros = 0
    concluidos = 0
    falhas = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futuros = {executor.submit(baixar_dia, sessao, regulador, d, destino_dir): d
                   for d in pendentes}
        for futuro in as_completed(futuros):
            dia = futuros[futuro]
            concluidos += 1
            try:
                rotulo, gravados, _pulado = futuro.result()
            except Exception as e:
                falhas.append((dia.isoformat(), repr(e)))
                print(f"  [{concluidos}/{len(pendentes)}] {dia.isoformat()}: "
                      f"FALHOU -- {e}", flush=True)
                continue

            total_registros += gravados
            decorrido = time.time() - inicio
            ritmo = total_registros / decorrido if decorrido else 0
            restantes = len(pendentes) - concluidos
            eta = (decorrido / concluidos) * restantes if concluidos else 0
            print(f"  [{concluidos}/{len(pendentes)}] {rotulo}: "
                  f"+{gravados} contratos | {ritmo:.0f} reg/s | "
                  f"faltam {restantes} dias (~{eta/60:.0f} min)", flush=True)

    decorrido = time.time() - inicio
    print(f"== Concluido em {decorrido/60:.1f} min: {total_registros} contratos "
          f"em {destino_dir} ==")
    print(f"   {regulador.total_429} respostas 429 "
          f"(ritmo final: {regulador.pausa_atual:.2f}s entre requisicoes)")
    if falhas:
        print(f"   {len(falhas)} dia(s) falharam -- rode de novo para refazer "
              f"so eles:")
        for rotulo, erro in falhas[:10]:
            print(f"     {rotulo}: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
