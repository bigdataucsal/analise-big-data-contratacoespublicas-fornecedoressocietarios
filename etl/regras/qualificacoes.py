"""RN-03. Quais socios entram no calculo, por codigo de qualificacao."""

IDENTIFICADOR_PJ = 1
IDENTIFICADOR_PF = 2
IDENTIFICADOR_ESTRANGEIRO = 3

GRUPO_PARTICIPACAO = frozenset({
    22, 23, 24, 25, 26, 28, 29, 30, 31, 37,
    38, 47, 48, 49, 52, 55, 56, 57, 58, 74,
})

GRUPO_TITULARIDADE = frozenset({34, 50, 65, 66, 67, 68, 78, 79})

GRUPO_ADMINISTRACAO = frozenset({5, 8, 10, 16, 64, 70, 71, 72, 73})

EXCLUIDOS = frozenset({53, 63})

PARA_CONTROLE = frozenset(GRUPO_PARTICIPACAO | GRUPO_TITULARIDADE | GRUPO_ADMINISTRACAO)
PARA_CONCENTRACAO = frozenset(GRUPO_PARTICIPACAO | GRUPO_TITULARIDADE)

PALAVRAS_EXCLUIDAS = ("PROCURADOR", "REPRESENTANTE")


def codigo(valor):
    """Normaliza o codigo de qualificacao, que vem com zero a esquerda ('05')."""
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        return int(texto)
    except ValueError:
        return None


def eh_pessoa_fisica(identificador_socio) -> bool:
    """A distincao PF/PJ vem do identificador, nunca do tamanho do documento."""
    return codigo(identificador_socio) == IDENTIFICADOR_PF


def eh_estrangeiro(identificador_socio) -> bool:
    return codigo(identificador_socio) == IDENTIFICADOR_ESTRANGEIRO


def eh_pessoa_juridica(identificador_socio) -> bool:
    return codigo(identificador_socio) == IDENTIFICADOR_PJ


def grupo(cod_qualificacao):
    cod = codigo(cod_qualificacao)
    if cod in GRUPO_PARTICIPACAO:
        return "participacao"
    if cod in GRUPO_TITULARIDADE:
        return "titularidade"
    if cod in GRUPO_ADMINISTRACAO:
        return "administracao"
    if cod in EXCLUIDOS:
        return "excluido"
    return None


def socio_elegivel(identificador_socio, cod_qualificacao, para="controle") -> bool:
    """Socio entra no calculo.

    `para="controle"` e a RN-05, que inclui administracao porque a pergunta e
    quem decide. `para="concentracao"` e a RN-07, que exclui administracao
    porque ali a pergunta e quem e dono do capital.
    """
    if not eh_pessoa_fisica(identificador_socio):
        return False
    aceitos = PARA_CONTROLE if para == "controle" else PARA_CONCENTRACAO
    return codigo(cod_qualificacao) in aceitos


def socio_elegivel_por_palavra(identificador_socio, descricao_qualificacao) -> bool:
    """Criterio antigo do classificar_empresas.py, mantido para reproducao.

    Foi ele que produziu os numeros publicados do recorte nacional. Difere da
    lista de codigos em no maximo 1.608 linhas (0,49% dos socios elegiveis),
    segundo a RN-03, e fica aqui para que a diferenca seja mensuravel em vez de
    perdida.
    """
    if not eh_pessoa_fisica(identificador_socio):
        return False
    texto = (descricao_qualificacao or "").upper()
    return not any(palavra in texto for palavra in PALAVRAS_EXCLUIDAS)
