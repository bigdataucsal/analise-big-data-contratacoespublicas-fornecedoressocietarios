"""RN-05. Classificacao de controle da empresa por genero dos socios."""

LIMITE_INDETERMINADOS = 1 / 3

FEMININO = "feminino"
MASCULINO = "masculino"
MISTO = "misto_ou_indeterminado"
INDETERMINADO = "indeterminado"
SEM_SOCIO = "sem_socio_na_base"

CONTROLE_DEFINIDO = (FEMININO, MASCULINO)


def classificar_empresa(n_f: int, n_m: int, n_ind: int, tem_pj: bool):
    """Classifica a empresa e devolve (classe, motivo).

    A ordem dos testes e a mesma do classificar_empresas.py, que produziu os
    numeros publicados do recorte nacional: o socio pessoa juridica decide
    antes de qualquer contagem, porque cadeia societaria torna o genero
    indefinivel sem resolver a cadeia inteira.

    Contagem por cabeca, nao por capital: o percentual de participacao de cada
    socio nao consta dos dados abertos da Receita. Essa e a principal
    limitacao metodologica do trabalho.
    """
    n = n_f + n_m + n_ind
    if tem_pj:
        return MISTO, "socio_pj"
    if n == 0:
        return INDETERMINADO, "sem_socio_elegivel"
    if n_ind / n > LIMITE_INDETERMINADOS:
        return MISTO, "muitos_indeterminados"
    if n_f / n > 0.5:
        return FEMININO, "maioria"
    if n_m / n > 0.5:
        return MASCULINO, "maioria"
    return MISTO, "sem_maioria"


def classificar_com_base(n_f: int, n_m: int, n_ind: int, tem_pj: bool,
                         linhas_de_socio: int):
    """Igual a anterior, mas separa a empresa sem nenhuma linha de socio (D5).

    Sao 65.001 empresas do recorte, 27,1%, das quais 62.880 sao empresarios
    individuais. Nao tem controle inferivel e formam universo declarado a
    parte, sem inferencia pelo nome do titular.
    """
    if linhas_de_socio == 0:
        return SEM_SOCIO, "sem_linha_na_base"
    return classificar_empresa(n_f, n_m, n_ind, tem_pj)


def controle_definido(classe: str) -> bool:
    """So feminino e masculino contam no denominador do KPI 1."""
    return classe in CONTROLE_DEFINIDO
