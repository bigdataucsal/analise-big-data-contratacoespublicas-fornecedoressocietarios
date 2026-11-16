"""RN-05. Classificacao de controle da empresa por genero dos socios."""

LIMITE_INDETERMINADOS = 1 / 3

FEMININO = "feminino"
MASCULINO = "masculino"
MISTO = "misto_ou_indeterminado"
INDETERMINADO = "indeterminado"
SEM_SOCIO = "sem_socio_na_base"
NAO_CLASSIFICADO = "nao_classificado"

CONTROLE_DEFINIDO = (FEMININO, MASCULINO)

ROTULO_AGREGADO = {
    FEMININO: "feminino",
    MASCULINO: "masculino",
    MISTO: "misto ou indeterminado",
    INDETERMINADO: "indeterminado",
    SEM_SOCIO: "sem socio na base",
    NAO_CLASSIFICADO: "nao classificado",
}


def classificar_empresa(n_f: int, n_m: int, n_ind: int, tem_pj: bool,
                        n_nulo: int = 0):
    """Classifica a empresa e devolve (classe, motivo).

    A ordem dos testes e a mesma do SQL_CONTROLE do construir_agregados.py,
    que e o que alimenta a agg_kpi_genero_setor: o socio sem genero decide
    antes do socio pessoa juridica, e este antes de qualquer contagem, porque
    cadeia societaria torna o genero indefinivel sem resolver a cadeia
    inteira.

    `n_nulo` conta o socio pessoa fisica elegivel cujo genero ainda esta
    nulo, que nao e a mesma coisa que indeterminado: indeterminado e um
    veredito da RN-04 (nome ambiguo ou ausente da base de nomes), nulo e
    ausencia de veredito. Misturar os dois faria a empresa parecer avaliada
    quando ela nao foi.

    Contagem por cabeca, nao por capital: o percentual de participacao de cada
    socio nao consta dos dados abertos da Receita. Essa e a principal
    limitacao metodologica do trabalho.
    """
    n = n_f + n_m + n_ind
    if n_nulo > 0:
        return NAO_CLASSIFICADO, "socio_sem_genero"
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
                         linhas_de_socio: int, n_nulo: int = 0):
    """Igual a anterior, mas separa a empresa sem nenhuma linha de socio (D5).

    Sao 65.001 empresas do recorte, 27,1%, das quais 62.880 sao empresarios
    individuais. Nao tem controle inferivel e formam universo declarado a
    parte, sem inferencia pelo nome do titular.
    """
    if linhas_de_socio == 0:
        return SEM_SOCIO, "sem_linha_na_base"
    return classificar_empresa(n_f, n_m, n_ind, tem_pj, n_nulo)


def rotulo_agregado(classe: str) -> str:
    """Traduz a classe para o texto gravado na agg_kpi_genero_setor."""
    return ROTULO_AGREGADO[classe]


def controle_definido(classe: str) -> bool:
    """So feminino e masculino contam no denominador do KPI 1."""
    return classe in CONTROLE_DEFINIDO
