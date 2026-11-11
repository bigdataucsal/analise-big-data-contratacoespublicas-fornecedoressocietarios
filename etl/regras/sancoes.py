"""RN-08. Marcacao de sancao vigente na data de assinatura."""

from datetime import date, datetime

from . import identificadores

FONTES = ("CEIS", "CNEP")


def para_data(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def vigente_em(sancao, data_referencia) -> bool:
    """Sancao vigente na data dada, com fim aberto tratado como ainda vigente."""
    referencia = para_data(data_referencia)
    if referencia is None:
        return False
    inicio = para_data(sancao.get("data_inicio"))
    fim = para_data(sancao.get("data_fim"))
    if inicio is None:
        return False
    if referencia < inicio:
        return False
    return fim is None or referencia <= fim


def indexar(sancoes) -> dict:
    """Agrupa as sancoes pela raiz de CNPJ do sancionado.

    A raiz, e nao o CNPJ de 14, pela mesma razao da RN-01: a sancao alcanca a
    empresa, e o contrato pode estar em outro estabelecimento dela.
    """
    indice = {}
    for sancao in sancoes:
        digitos = identificadores.so_digitos(sancao.get("cnpj"))
        if len(digitos) < identificadores.TAMANHO_RAIZ:
            continue
        raiz = digitos[:identificadores.TAMANHO_RAIZ]
        indice.setdefault(raiz, []).append(sancao)
    return indice


def marcar_contrato(cnpj_raiz, data_assinatura, indice) -> dict:
    """Marca o contrato como firmado com fornecedor sancionado.

    A comparacao e contra a data de assinatura, nunca contra a data de
    consulta: usar a lista atual produziria acusacao indevida contra contrato
    legitimo anterior a sancao.
    """
    if not cnpj_raiz or not data_assinatura:
        return {"fornecedor_sancionado": False, "fontes": (), "motivo": "sem_chave_ou_data"}

    vigentes = [s for s in indice.get(cnpj_raiz, []) if vigente_em(s, data_assinatura)]
    if not vigentes:
        return {"fornecedor_sancionado": False, "fontes": (), "motivo": "sem_sancao_vigente"}

    fontes = tuple(sorted({(s.get("fonte") or "").upper() for s in vigentes} - {""}))
    return {"fornecedor_sancionado": True, "fontes": fontes, "motivo": "sancao_vigente"}


def competencia_do_quadro_societario(competencia: str) -> str:
    """Declara a competencia usada, exigencia da propria RN-08.

    O arquivo de socios da Receita nao tem data de saida da sociedade: e um
    retrato da competencia, e quem saiu desaparece na competencia seguinte.
    Com uma competencia so, o que se afirma e quem e socio hoje de uma empresa
    contratada naquela data, e nao quem era socio na data do contrato.
    """
    return (
        f"Quadro societario na competencia {competencia}. Sem data de saida na "
        "origem, o vinculo nao pode ser datado como a sancao."
    )
