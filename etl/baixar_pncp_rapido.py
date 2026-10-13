"""
Extrator de contratos do PNCP.

Varre o periodo em janelas de um dia e grava um JSONL unico, acrescentando
linhas. O arquivo .dias ao lado lista os dias ja fechados, entao rodar de
novo retoma de onde parou. A API limita por requisicoes por minuto, nao por
concorrencia, e o intervalo entre chamadas e o que controla isso.

Saida: dados/raw/pncp/contratos_<ano>_completo.jsonl e o .dias correspondente.

Uso:
    python baixar_pncp_rapido.py
    python baixar_pncp_rapido.py --intervalo 3.0
    python baixar_pncp_rapido.py --de 20250101 --ate 20250107
    python baixar_pncp_rapido.py --verificar
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
TIMEOUT_SEGUNDOS = 120
MAX_TENTATIVAS = 6
STATUS_RETENTAVEIS = {429, 500, 502, 503, 504}

# Os workers nao regulam o ritmo, quem regula e a PortaRitmo. Eles so
# servem para esconder latencia: enquanto um espera a resposta (1,6-2,8 s),
# outro ja pode pedir a vez na porta.
WORKERS_PADRAO = 2

# Medido em 19/09/2026, ritmo sustentado com porta global:
#     ~20 req/min -> nenhum 429
#      40 req/min -> 13 de 18 requisicoes em 429
#      62 req/min -> 10 de 18
#      79 req/min -> 13 de 18   (1 thread! a concorrencia nao e o gatilho)
# O limite fica entre 20 e 40 req/min. 2,0 s da 30 req/min de alvo, mas a
# latencia das respostas puxa o ritmo efetivo para baixo disso, foi a
# configuracao que passou sem nenhum 429.
INTERVALO_PADRAO = 2.0     # segundos entre duas requisicoes quaisquer

TAMANHO_INICIAL = 500      # maximo aceito pela API; 1000 responde 400
TAMANHO_MINIMO = 100
TAMANHO_PASSO = 50
MAX_REINICIOS_DIA = 3      # refaz o dia num tamanho menor ate 3 vezes


class TamanhoPagina:
    """Escada global de tamanho de pagina: 500 -> 450 -> ... -> 100.

    So desce, nunca sobe. Se a API apertou uma vez, subir de novo so
    provocaria o proximo 429, melhor assentar no tamanho que passa.

    Importante: o tamanho NAO pode mudar no meio de um dia. As fronteiras
    de paginacao sao calculadas a partir dele, entao trocar no meio faria
    a pagina 3 de 500 e a pagina 3 de 450 cobrirem intervalos diferentes,
    pulando ou repetindo registros. Cada dia le o tamanho uma vez e o
    mantem ate terminar.
    """

    def __init__(self, inicial=TAMANHO_INICIAL, minimo=TAMANHO_MINIMO,
                 passo=TAMANHO_PASSO):
        self._lock = threading.Lock()
        self._atual = inicial
        self._minimo = minimo
        self._passo = passo
        self.reducoes = 0

    @property
    def atual(self) -> int:
        with self._lock:
            return self._atual

    def reduzir(self):
        """Desce um degrau. Devolve (tamanho_novo, mudou)."""
        with self._lock:
            if self._atual <= self._minimo:
                return self._atual, False
            self._atual = max(self._atual - self._passo, self._minimo)
            self.reducoes += 1
            return self._atual, True


class PortaRitmo:
    """Porta global: garante um intervalo minimo entre DUAS requisicoes
    quaisquer, nao importa qual thread as faca.

    Medido em 19/09/2026: requisicoes unicas espacadas 5 s passaram 5/5 sem
    nenhum 429, enquanto 2 workers disparando a toda tomaram 429 em quase
    toda pagina. O limite do PNCP e de RITMO, requisicoes por unidade de
    tempo, e nao de tamanho de resposta nem de numero de conexoes. Entao
    quem regula tem que ser o intervalo entre requisicoes, nao a pausa de
    cada thread: com pausa por thread, N threads fazem N vezes o ritmo.

    Os workers continuam servindo para esconder latencia (enquanto um espera
    a resposta, outro ja pode pedir a vez), mas quem manda no ritmo e a porta.
    """

    JANELA_PENALIDADE = 5.0   # segundos: 429s dentro disso contam como um so

    def __init__(self, intervalo: float = 1.2, minimo: float = 0.8,
                 maximo: float = 30.0):
        self._lock = threading.Lock()
        self._intervalo = intervalo
        self._minimo = minimo
        self._maximo = maximo
        self._proximo_livre = 0.0
        self._sucessos = 0
        self._ultima_penalidade = float("-inf")
        self.total_429 = 0

    def aguardar(self):
        """Bloqueia ate chegar a vez desta requisicao."""
        with self._lock:
            agora = time.monotonic()
            inicio = max(agora, self._proximo_livre)
            # Reserva a vaga ja: a proxima thread que chegar pega a seguinte.
            self._proximo_livre = inicio + self._intervalo * random.uniform(0.9, 1.1)
            espera = inicio - agora
        if espera > 0:
            time.sleep(espera)

    def penalizar(self) -> float:
        with self._lock:
            self.total_429 += 1
            agora = time.monotonic()
            # Todas as threads em voo tomam 429 do mesmo aperto. Sem esta
            # janela, um unico evento vira N multiplicacoes: foi assim que o
            # intervalo saltou de 1,2 s para o teto de 30 s em oito passos,
            # com 3 workers. Aqui, a rajada inteira conta como uma penalidade.
            if agora - self._ultima_penalidade < self.JANELA_PENALIDADE:
                return self._intervalo
            self._ultima_penalidade = agora
            self._intervalo = min(self._intervalo * 1.5, self._maximo)
            self._sucessos = 0
            return self._intervalo

    def premiar(self):
        with self._lock:
            self._sucessos += 1
            if self._sucessos >= 20 and self._intervalo > self._minimo:
                self._intervalo = max(self._intervalo * 0.9, self._minimo)
                self._sucessos = 0

    @property
    def intervalo_atual(self) -> float:
        with self._lock:
            return self._intervalo


class Escritor:
    """Arquivo unico, acrescentando linhas.

    Um dia so e gravado quando esta inteiro, de uma vez, com o lock tomado:
    assim duas threads nunca intercalam linhas e nao existe linha partida
    pela metade. Depois do fsync dos dados e que o dia entra no .dias --
    nessa ordem, para nunca marcar como pronto algo que nao esta em disco.
    """

    def __init__(self, caminho: Path):
        self.caminho = caminho
        self.caminho_dias = caminho.with_suffix(".dias")
        self._lock = threading.Lock()
        self._arquivo = open(caminho, "a", encoding="utf-8")

    def dias_concluidos(self) -> set:
        if not self.caminho_dias.exists():
            return set()
        return {l.strip() for l in self.caminho_dias.read_text(
            encoding="utf-8").splitlines() if l.strip()}

    def gravar_dia(self, rotulo: str, registros: list) -> int:
        with self._lock:
            for registro in registros:
                self._arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
            self._arquivo.flush()
            os.fsync(self._arquivo.fileno())
            with open(self.caminho_dias, "a", encoding="utf-8") as f:
                f.write(rotulo + "\n")
                f.flush()
                os.fsync(f.fileno())
        return len(registros)

    def fechar(self):
        with self._lock:
            self._arquivo.close()


class PaginaMenor(Exception):
    """A API apertou: vale refazer este dia num tamanho de pagina menor."""


def buscar_pagina(sessao, porta, tamanhos, dia: str, pagina: int, tamanho: int):
    """Uma pagina de um dia, no tamanho fixado para aquele dia.

    Devolve o dict da API, ou None se a pagina nao existe (a API responde
    400, nao vazio, quando pagina > total)."""
    params = {
        "dataInicial": dia,
        "dataFinal": dia,
        "pagina": pagina,
        "tamanhoPagina": tamanho,
    }
    if config.ORGAOS_RECORTE:
        params["cnpjOrgao"] = config.ORGAOS_RECORTE[0]

    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        porta.aguardar()
        try:
            resp = sessao.get(BASE_URL, params=params, timeout=TIMEOUT_SEGUNDOS)
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            ultimo_erro = e
            time.sleep(min(2 ** tentativa, 30) * random.uniform(0.8, 1.2))
            continue

        if resp.status_code == 204:                 # dia sem contratos
            porta.premiar()
            return {"data": [], "totalPaginas": 0, "totalRegistros": 0}

        if resp.status_code == 400 and pagina > 1:  # passou do fim do dia
            return None

        if resp.status_code in STATUS_RETENTAVEIS:
            ultimo_erro = f"HTTP {resp.status_code}"
            if resp.status_code in (429, 504):
                novo_intervalo = porta.penalizar()
                # A escada de tamanho, quando ligada, so afeta os dias que
                # ainda nao comecaram. Reduzir AQUI deslocaria as fronteiras
                # das paginas deste dia e faria pular ou repetir registros.
                if tamanhos is not None:
                    tamanhos.reduzir()
                print(f"    [{resp.status_code}] {dia} p{pagina} "
                      f"(tentativa {tentativa}/{MAX_TENTATIVAS}): "
                      f"intervalo -> {novo_intervalo:.1f}s", flush=True)
            cabecalho = resp.headers.get("Retry-After")
            espera = float(cabecalho) if cabecalho else min(2 ** tentativa, 30)
            time.sleep(espera * random.uniform(0.8, 1.2))
            continue

        resp.raise_for_status()
        porta.premiar()
        return resp.json()

    # Esgotou as tentativas nesta pagina. Se a escada estiver ligada e ja
    # tiver descido um degrau, vale refazer o dia no tamanho novo; senao o
    # dia falha e sai na lista do fim para ser refeito numa proxima rodada.
    if tamanhos is not None and tamanhos.atual < tamanho:
        raise PaginaMenor()
    raise RuntimeError(
        f"{dia} pagina {pagina} falhou apos {MAX_TENTATIVAS} tentativas "
        f"(ultimo erro: {ultimo_erro})"
    )


def baixar_dia(sessao, porta, tamanhos, escritor, dia: date):
    """Baixa um dia inteiro e o grava de uma vez.

    Junta tudo em memoria antes de gravar (um dia sao ~5.500 contratos,
    ~10 MB) porque so assim da para gravar o dia inteiro sob um unico lock
    e manter o arquivo sempre consistente.
    """
    rotulo = dia.isoformat()
    dia_api = dia.strftime("%Y%m%d")

    for reinicio in range(MAX_REINICIOS_DIA + 1):
        # Fixo do inicio ao fim deste dia. Com a escada desligada
        # (tamanhos is None) e sempre TAMANHO_INICIAL.
        tamanho = tamanhos.atual if tamanhos is not None else TAMANHO_INICIAL
        registros = []
        try:
            primeira = buscar_pagina(sessao, porta, tamanhos, dia_api, 1, tamanho)
            total_paginas = primeira.get("totalPaginas", 0) or 0
            registros.extend(primeira.get("data", []))

            for pagina in range(2, total_paginas + 1):
                dados = buscar_pagina(sessao, porta, tamanhos, dia_api,
                                      pagina, tamanho)
                if dados is None:
                    break
                lote = dados.get("data", [])
                if not lote:
                    break
                registros.extend(lote)

        except PaginaMenor:
            if reinicio < MAX_REINICIOS_DIA:
                print(f"    {rotulo}: refazendo em {tamanhos.atual} "
                      f"(tentativa {reinicio + 2})", flush=True)
                continue
            raise RuntimeError(
                f"{rotulo}: ainda batendo em 429 depois de {MAX_REINICIOS_DIA} "
                f"reinicios (tamanho atual {tamanhos.atual})")

        escritor.gravar_dia(rotulo, registros)
        return (rotulo, len(registros), tamanho)

    raise RuntimeError(f"{rotulo}: reinicios esgotados")


def criar_sessao(workers: int) -> requests.Session:
    sessao = requests.Session()
    adaptador = requests.adapters.HTTPAdapter(
        pool_connections=workers, pool_maxsize=workers, max_retries=0
    )
    sessao.mount("https://", adaptador)
    sessao.headers.update({"Accept": "application/json"})
    return sessao


def dias_do_periodo(de: str, ate: str):
    inicio = datetime.strptime(de, "%Y%m%d").date()
    fim = datetime.strptime(ate, "%Y%m%d").date()
    atual = inicio
    while atual <= fim:
        yield atual
        atual += timedelta(days=1)


def caminho_saida(args) -> Path:
    if args.saida:
        return Path(args.saida)
    return (Path(config.DIR_DADOS_RAW) / "pncp" /
            f"contratos_{config.ANO_REFERENCIA}_completo.jsonl")


def verificar(caminho: Path, de: str, ate: str) -> int:
    dias = [d.isoformat() for d in dias_do_periodo(de, ate)]
    caminho_dias = caminho.with_suffix(".dias")
    concluidos = set()
    if caminho_dias.exists():
        concluidos = {l.strip() for l in caminho_dias.read_text(
            encoding="utf-8").splitlines() if l.strip()}
    faltando = [d for d in dias if d not in concluidos]

    total = duplicados = invalidas = 0
    vistos = set()
    if caminho.exists():
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                total += 1
                try:
                    reg = json.loads(linha)
                except json.JSONDecodeError:
                    invalidas += 1
                    continue
                chave = reg.get("numeroControlePNCP")
                if chave in vistos:
                    duplicados += 1
                else:
                    vistos.add(chave)

    print(f"== Verificacao de {caminho} ==")
    print(f"  dias no periodo : {len(dias)}")
    print(f"  dias concluidos : {len(dias) - len(faltando)}")
    detalhe = ""
    if faltando:
        detalhe = " -> " + ", ".join(faltando[:10])
        if len(faltando) > 10:
            detalhe += " ..."
    print(f"  dias faltando   : {len(faltando)}{detalhe}")
    print(f"  linhas          : {total}")
    print(f"  contratos unicos: {len(vistos)}")
    print(f"  duplicados      : {duplicados}"
          + ("  (o tratamento remove)" if duplicados else ""))
    if invalidas:
        print(f"  ATENCAO: {invalidas} linha(s) invalida(s), possivel queda "
              f"no meio de uma gravacao")
    return 0 if not faltando else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Extrator rapido de contratos do PNCP")
    p.add_argument("--de", default=config.DATA_INICIAL_PNCP,
                   help="data inicial AAAAMMDD (padrao: config.py)")
    p.add_argument("--ate", default=config.DATA_FINAL_PNCP,
                   help="data final AAAAMMDD (padrao: config.py)")
    p.add_argument("--workers", type=int, default=WORKERS_PADRAO,
                   help=f"dias baixados em paralelo (padrao: {WORKERS_PADRAO}; "
                        f"use 1 se ainda vier muito 429)")
    p.add_argument("--intervalo", type=float, default=INTERVALO_PADRAO,
                   help=f"segundos entre duas requisicoes quaisquer (padrao: "
                        f"{INTERVALO_PADRAO}). E este o controle que evita 429; "
                        f"aumente se ainda vier muito.")
    p.add_argument("--tamanho-inicial", type=int, default=TAMANHO_INICIAL,
                   help=f"registros por pagina (padrao: {TAMANHO_INICIAL}, o "
                        f"maximo da API)")
    p.add_argument("--escada", action="store_true",
                   help=f"reduz a pagina de {TAMANHO_PASSO} em {TAMANHO_PASSO} "
                        f"a cada 429, ate {TAMANHO_MINIMO}. DESLIGADO por "
                        f"padrao: medimos que piora, pagina menor exige mais "
                        f"requisicoes para os mesmos dados, e o limite do PNCP "
                        f"e de requisicoes por tempo, nao de tamanho.")
    p.add_argument("--saida", default=None,
                   help="arquivo de saida (padrao: dados/raw/pncp/"
                        "contratos_ANO_completo.jsonl)")
    p.add_argument("--verificar", action="store_true",
                   help="nao baixa: so confere o que ja existe")
    args = p.parse_args()

    saida = caminho_saida(args)
    saida.parent.mkdir(parents=True, exist_ok=True)

    if args.verificar:
        return verificar(saida, args.de, args.ate)

    escritor = Escritor(saida)
    concluidos = escritor.dias_concluidos()
    dias = list(dias_do_periodo(args.de, args.ate))
    pendentes = [d for d in dias if d.isoformat() not in concluidos]

    if saida.exists() and saida.stat().st_size > 0 and not concluidos:
        print(f"AVISO: {saida.name} ja tem conteudo mas nao ha registro de dias "
              f"concluidos.\n       As linhas novas serao acrescentadas e pode "
              f"haver repeticao\n       (o tratamento deduplica).")

    print(f"== PNCP rapido: {args.de} a {args.ate} ==")
    print(f"   {len(dias)} dias no periodo, {len(concluidos)} ja concluidos, "
          f"{len(pendentes)} pendentes")
    print(f"   {args.workers} dias em paralelo, {args.intervalo}s entre "
          f"requisicoes, pagina de {args.tamanho_inicial}")
    if args.escada:
        print(f"   escada LIGADA: pagina desce ate {TAMANHO_MINIMO} a cada 429")
    print(f"   saida: {saida}")
    if not pendentes:
        print("== Nada a fazer: todos os dias ja estao concluidos ==")
        escritor.fechar()
        return 0

    porta = PortaRitmo(intervalo=args.intervalo)
    tamanhos = TamanhoPagina(inicial=args.tamanho_inicial) if args.escada else None
    sessao = criar_sessao(args.workers)
    inicio = time.time()
    total_registros = concluidos_agora = 0
    falhas = []

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futuros = {executor.submit(baixar_dia, sessao, porta, tamanhos,
                                       escritor, d): d for d in pendentes}
            for futuro in as_completed(futuros):
                dia = futuros[futuro]
                concluidos_agora += 1
                try:
                    rotulo, gravados, tamanho = futuro.result()
                except Exception as e:
                    falhas.append((dia.isoformat(), repr(e)))
                    print(f"  [{concluidos_agora}/{len(pendentes)}] "
                          f"{dia.isoformat()}: FALHOU, {e}", flush=True)
                    continue

                total_registros += gravados
                decorrido = time.time() - inicio
                ritmo = total_registros / decorrido if decorrido else 0
                restantes = len(pendentes) - concluidos_agora
                eta = (decorrido / concluidos_agora) * restantes
                print(f"  [{concluidos_agora}/{len(pendentes)}] {rotulo}: "
                      f"+{gravados} (pag {tamanho}) | {ritmo:.0f} reg/s | "
                      f"faltam {restantes} (~{eta/60:.0f} min)", flush=True)
    finally:
        escritor.fechar()

    decorrido = time.time() - inicio
    print(f"== Concluido em {decorrido/60:.1f} min: {total_registros} contratos "
          f"em {saida} ==")
    resumo = (f"   {porta.total_429} respostas 429/504, intervalo final "
              f"{porta.intervalo_atual:.1f}s")
    if tamanhos is not None:
        resumo += (f", {tamanhos.reducoes} reducao(oes) de pagina "
                   f"(final {tamanhos.atual})")
    print(resumo)
    if falhas:
        print(f"   {len(falhas)} dia(s) falharam, rode de novo para refazer "
              f"so eles:")
        for rotulo, erro in falhas[:10]:
            print(f"     {rotulo}: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
