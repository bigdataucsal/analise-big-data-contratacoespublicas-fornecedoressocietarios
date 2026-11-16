"""RN-01. Normalizacao de identificadores e raiz de CNPJ."""

import re

TAMANHO_CNPJ = 14
TAMANHO_CPF = 11
TAMANHO_RAIZ = 8

AUSENTE = "ausente"
CPF = "cpf"
CNPJ = "cnpj"
IRREGULAR = "irregular"

_NAO_DIGITO = re.compile(r"[^0-9]")


def so_digitos(valor) -> str:
    if valor is None:
        return ""
    return _NAO_DIGITO.sub("", str(valor))


def classificar_identificador(ni) -> str:
    digitos = so_digitos(ni)
    if not digitos:
        return AUSENTE
    if len(digitos) == TAMANHO_CPF:
        return CPF
    if len(digitos) == TAMANHO_CNPJ:
        return CNPJ
    return IRREGULAR


def normalizar_cnpj(ni) -> str:
    """Devolve o CNPJ como texto de 14 caracteres, preservando zeros a esquerda.

    Devolve vazio quando o identificador nao tem 14 digitos: completar com
    zeros um numero de outro tamanho inventaria um CNPJ que nao existe.
    """
    digitos = so_digitos(ni)
    return digitos if len(digitos) == TAMANHO_CNPJ else ""


def raiz_cnpj(ni, tipo_pessoa) -> str:
    """Raiz de 8 digitos, so para fornecedor PJ com identificador de 14 digitos.

    Mesmo criterio do tratar_contratos.py e do recorte_cnpjs.py. Quem nao
    atende fica sem raiz e forma o universo declarado a parte da RN-01.
    """
    if (tipo_pessoa or "").strip().upper() != "PJ":
        return ""
    completo = normalizar_cnpj(ni)
    return completo[:TAMANHO_RAIZ] if completo else ""


def tem_raiz(ni, tipo_pessoa) -> bool:
    return bool(raiz_cnpj(ni, tipo_pessoa))


def tipo_contradiz_tamanho(ni, tipo_pessoa) -> bool:
    """PJ com 11 digitos ou PF com 14: os 1.979 contratos citados na RN-01."""
    tipo = (tipo_pessoa or "").strip().upper()
    classe = classificar_identificador(ni)
    return (tipo == "PJ" and classe == CPF) or (tipo == "PF" and classe == CNPJ)
