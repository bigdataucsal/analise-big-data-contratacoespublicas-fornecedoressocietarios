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

# --- Caminhos (relativos a raiz do repo, quando os scripts rodam de dentro de etl/) ---
DIR_DADOS_RAW = "dados/raw"
DIR_DADOS_PARQUET = "dados/parquet"
DIR_INVENTARIO = "inventario"