"""Todo script de extracao (PNCP, Portal da Transparencia, Receita) importa"""

ANO_REFERENCIA = 2025
DATA_INICIAL_PNCP = "20250101"
DATA_FINAL_PNCP = "20251231"
DATA_INICIAL_TRANSPARENCIA = "01/01/2025"
DATA_FINAL_TRANSPARENCIA = "31/12/2025"

UF_RECORTE = None
ORGAOS_RECORTE = None

MES_RECEITA = "2026-09-14"

import os as _os
from pathlib import Path as _Path

_DIR_BASE = _Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_DIR_BASE / ".env")
except ImportError:
    pass

DIR_DADOS_RAW = _os.getenv("DIR_DADOS_RAW") or str(_DIR_BASE / "dados" / "raw")
DIR_DADOS_PARQUET = str(_DIR_BASE / "dados" / "parquet")
DIR_INVENTARIO = str(_DIR_BASE / "inventario")

DIR_RECORTE = str(_DIR_BASE / "dados" / "recorte")
