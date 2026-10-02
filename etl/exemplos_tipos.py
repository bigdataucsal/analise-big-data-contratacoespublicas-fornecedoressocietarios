"""Imprime um trecho real de cada tipo de dado do projeto, com identificadores mascarados.

Uso (de dentro de etl/):
    python exemplos_tipos.py
    python exemplos_tipos.py --jsonl C:\\dados-bigdata\\raw\\pncp\\contratos_2025_completo.jsonl --socios-zip CAMINHO\\Socios1.zip

Grava a saída em docs/evidencias/exemplos_tipos.txt. REVISE o arquivo antes de commitar:
nomes de pessoa física e CPF são mascarados aqui, mas confira com os seus olhos.
"""
import argparse
import glob
import json
import random
import re
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "evidencias" / "exemplos_tipos.txt"
JSONL_PADRAO = r"C:\dados-bigdata\raw\pncp\contratos_2025_completo.jsonl"


def mascarar_nome(nome: str) -> str:
    """MARIA DA SILVA SANTOS -> MARIA D. S. S."""
    partes = nome.split()
    if not partes:
        return ""
    return partes[0] + "".join(f" {p[0]}." for p in partes[1:])


def _chave(reg: dict, alvo: str):
    """Acha a chave ignorando maiúsculas e sublinhado (camelCase ou snake_case)."""
    alvo = alvo.lower().replace("_", "")
    for k in reg:
        if k.lower().replace("_", "") == alvo:
            return k
    return None


def _chave_tipo(reg: dict):
    """No JSON real do PNCP a chave é 'tipoPessoa'; o roteiro cita 'tipoPessoaFornecedor'."""
    return _chave(reg, "tipoPessoaFornecedor") or _chave(reg, "tipoPessoa")


def exemplo_json(caminho: str):
    """Primeiro contrato de fornecedor PJ; se não houver, o primeiro registro. Mascara nome e CPF."""
    primeiro = None
    escolhido = None
    with open(caminho, encoding="utf-8") as f:
        for i, linha in enumerate(f):
            if i > 5000:
                break
            reg = json.loads(linha)
            if primeiro is None:
                primeiro = reg
            k_tipo = _chave_tipo(reg)
            if k_tipo and str(reg.get(k_tipo)).strip().upper() == "PJ":
                escolhido = reg
                break
    reg = escolhido or primeiro
    if reg is None:
        return None

    k_tipo = _chave_tipo(reg)
    eh_pj = bool(k_tipo) and str(reg.get(k_tipo)).strip().upper() == "PJ"
    k_nome = _chave(reg, "nomeRazaoSocialFornecedor")
    k_ni = _chave(reg, "niFornecedor")
    nome = (reg.get(k_nome) or "") if k_nome else ""
    # Pessoa física, ou razão social de empresário individual (traz CPF): mascarar.
    if k_nome and (not eh_pj or re.search(r"\d{8,}", nome)):
        reg[k_nome] = mascarar_nome(re.sub(r"\d+", "", nome))
    if k_ni and not eh_pj:
        reg[k_ni] = re.sub(r"\d", "X", str(reg.get(k_ni) or ""))
    return reg


def exemplo_socios(caminho_zip: str, n: int = 3):
    """Primeiras linhas do arquivo de sócios (sem cabeçalho, ; e latin-1), mascaradas."""
    with zipfile.ZipFile(caminho_zip) as z:
        with z.open(z.namelist()[0]) as f:
            linhas = [f.readline().decode("latin-1").rstrip("\r\n") for _ in range(n)]
    saida = []
    for linha in linhas:
        c = [x.strip('"') for x in linha.split(";")]
        if len(c) >= 11:
            c[0] = c[0][:2] + "******"          # raiz do CNPJ
            c[2] = mascarar_nome(c[2])          # nome do sócio
            c[3] = re.sub(r"\d", "X", c[3])     # máscara do CPF
        saida.append(";".join(f'"{x}"' for x in c))
    return saida


def exemplos_objeto(caminho: str, k: int = 3, passo: int = 500):
    """k textos de objeto de contrato, de pontos espalhados pelo arquivo."""
    candidatos = []
    with open(caminho, encoding="utf-8") as f:
        for i, linha in enumerate(f):
            if i % passo:
                continue
            obj = json.loads(linha).get("objetoContrato")
            if obj and 40 <= len(obj) <= 220:
                candidatos.append(obj)
    random.seed(1)
    return random.sample(candidatos, min(k, len(candidatos)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", default=JSONL_PADRAO)
    ap.add_argument("--socios-zip", default=None)
    args = ap.parse_args()

    zip_socios = args.socios_zip
    if not zip_socios:
        achados = glob.glob(r"C:\dados-bigdata\**\Socios*.zip", recursive=True)
        zip_socios = achados[0] if achados else None

    partes = []
    partes.append("=== SEMIESTRUTURADO: um contrato do PNCP (JSON, campos aninhados) ===")
    reg = exemplo_json(args.jsonl)
    if reg:
        partes.append("chaves de topo: " + ", ".join(reg.keys()))
        partes.append(json.dumps(reg, ensure_ascii=False, indent=2))
    else:
        partes.append("(arquivo vazio ou ilegível)")

    partes.append("\n=== ESTRUTURADO: linhas de sócios da Receita (CSV sem cabeçalho, ';', latin-1) ===")
    if zip_socios:
        partes.append(f"arquivo: {Path(zip_socios).name}")
        partes.extend(exemplo_socios(zip_socios))
        partes.append("colunas, na ordem: cnpj_basico; identificador_de_socio; nome_do_socio; "
                      "cnpj_cpf_do_socio; qualificacao; data_entrada; pais; representante_legal; "
                      "nome_representante; qualificacao_representante; faixa_etaria")
    else:
        partes.append("(Socios*.zip não encontrado: use --socios-zip CAMINHO)")

    partes.append("\n=== NÃO ESTRUTURADO: objeto do contrato (texto livre) ===")
    for i, obj in enumerate(exemplos_objeto(args.jsonl), 1):
        partes.append(f"{i}) {obj}")

    texto = "\n".join(partes)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"\nGravado em {SAIDA}")


if __name__ == "__main__":
    main()