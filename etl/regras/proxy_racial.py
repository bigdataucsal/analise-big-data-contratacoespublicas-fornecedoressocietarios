"""RN-06. Proxy de composicao por cor ou raca, sempre no nivel do territorio."""

FAIXAS = (
    (0.25, "ate_25"),
    (0.50, "de_25_a_50"),
    (0.75, "de_50_a_75"),
    (1.01, "acima_de_75"),
)


def percentual_negra(preta, parda, total):
    """Soma preta e parda sobre o total, que e a definicao usada no projeto."""
    if not total:
        return None
    return (float(preta) + float(parda)) / float(total)


def faixa_composicao(percentual):
    """Discretiza o percentual para o agrupamento das visoes materializadas."""
    if percentual is None:
        return "sem_dado"
    for limite, nome in FAIXAS:
        if percentual < limite:
            return nome
    return "acima_de_75"


def atribuir(composicao_municipio, nivel="empresa"):
    """Anexa o vetor do municipio ao contexto da empresa.

    Levanta erro quando o chamador tenta atribuir a composicao a uma pessoa.
    Isso nao e defesa contra bug, e a RN-06 escrita em codigo: inferir cor ou
    raca no nivel individual seria reidentificacao de dado sensivel pelo
    artigo 5 da LGPD, caminho avaliado e rejeitado no parecer.
    """
    if nivel in ("socio", "pessoa", "individuo"):
        raise ValueError(
            "RN-06 proibe atribuir composicao racial a pessoa: "
            "o indicador descreve o territorio, nao o individuo"
        )
    return dict(composicao_municipio, nivel=nivel, metodo="inferencia_ecologica")
