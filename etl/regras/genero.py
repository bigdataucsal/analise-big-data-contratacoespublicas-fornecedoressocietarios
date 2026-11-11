"""RN-04. Inferencia de genero pelo primeiro nome."""

import unicodedata

LIMIAR_PADRAO = 0.90
MINIMO_OCORRENCIAS = 20

FEMININO = "feminino"
MASCULINO = "masculino"
INDETERMINADO = "indeterminado"

PARTICULAS = frozenset({
    "DE", "DA", "DO", "DAS", "DOS", "E", "D", "DI", "DEL", "VAN", "VON",
})


def normalizar(texto: str) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return "".join(c for c in sem_acento.upper() if c.isalpha() or c.isspace()).strip()


def primeiro_nome(nome_completo: str) -> str:
    for token in normalizar(nome_completo).split():
        if token in PARTICULAS:
            continue
        return token if len(token) >= 3 else ""
    return ""


def classificar(freq_f: int, freq_m: int, limiar: float = LIMIAR_PADRAO,
                minimo: int = MINIMO_OCORRENCIAS):
    """Classifica o nome e devolve (classe, proporcao_dominante, motivo).

    O denominador e sempre feminino mais masculino, nunca o total que a API
    devolve sem o parametro de sexo: a supressao de valores pequenos do IBGE e
    aplicada celula a celula, e usar o total subestimaria a proporcao.
    """
    total = freq_f + freq_m
    if total == 0:
        return INDETERMINADO, 0.0, "ausente"
    if total < minimo:
        return INDETERMINADO, max(freq_f, freq_m) / total, "instavel"
    p_f = freq_f / total
    if p_f >= limiar:
        return FEMININO, p_f, "classificado"
    if (1 - p_f) >= limiar:
        return MASCULINO, 1 - p_f, "classificado"
    return INDETERMINADO, max(p_f, 1 - p_f), "ambiguo"
