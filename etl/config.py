"""
Todo script de extracao (PNCP, Portal da Transparencia, Receita) importa
deste arquivo em vez de ter datas/parametros soltos no codigo. Mudar o
recorte aqui muda em todos os extratores de uma vez so.
"""

# --- PNCP e Portal da Transparencia: contratos por data de publicacao ---
ANO_REFERENCIA = 2025
DATA_INICIAL_PNCP = "20250101"        # formato YYYYMMDD (API do PNCP)
DATA_FINAL_PNCP = "20251231"
DATA_INICIAL_TRANSPARENCIA = "01/01/2025"   # formato DD/MM/AAAA (API da CGU)
DATA_FINAL_TRANSPARENCIA = "31/12/2025"

# Recorte de orgaos/UF (ajustem depois de rodar a S1 e verem o volume real).
# Deixem None para nao filtrar.
UF_RECORTE = None          # ex: "BA"
ORGAOS_RECORTE = None      # ex: ["00394429000102"] (lista de CNPJs)

# --- Receita Federal (CNPJ): snapshot mensal, nao e recorte por ano ---
# Preenchido em tempo de execucao pelo cnpj-processor.get_latest_folder();
# guardem aqui o valor usado de fato assim que descobrirem, para reprodutibilidade.
MES_RECEITA = "2026-09-14"  # ex: "2026-01" -- atualizem apos rodar baixar_receita.py

# --- Caminhos ------------------------------------------------------------
# Ancorados no diretorio DESTE arquivo (etl/), nao no diretorio de onde o
# script foi chamado. Isso importa: com caminho relativo ao cwd, rodar
# `python etl/baixar_pncp_rapido.py` da raiz do repositorio criava uma arvore
# `dados/` paralela la, separada da que vive em `etl/dados/`. Aconteceu de
# verdade -- 109 MB de PNCP foram parar no lugar errado -- e o mesmo desenho
# faria o extrator da Receita gravar numa terceira arvore.
#
# Com caminho absoluto, todo script resolve para o mesmo lugar, seja qual for
# o cwd. Quem ja prefixava com a raiz do repositorio (`REPO_ROOT / DIR_...`)
# continua funcionando sem alteracao, porque `Path(a) / Path(b)` devolve `b`
# quando `b` e absoluto.
from pathlib import Path as _Path

_DIR_BASE = _Path(__file__).resolve().parent          # .../etl

DIR_DADOS_RAW = str(_DIR_BASE / "dados" / "raw")
DIR_DADOS_PARQUET = str(_DIR_BASE / "dados" / "parquet")
DIR_INVENTARIO = str(_DIR_BASE / "inventario")

# Lista de CNPJs que define o universo da analise, produzida por
# recorte_cnpjs.py e consumida por baixar_receita.py. E o unico diretorio de
# dados que vai para o repositorio, porque e decisao e nao dado bruto.
DIR_RECORTE = str(_DIR_BASE / "dados" / "recorte")