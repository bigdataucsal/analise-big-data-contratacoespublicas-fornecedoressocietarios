"""RN-09. Anonimizacao do socio e minimo de agregacao na apresentacao."""

import hashlib
import hmac
import os
import re

MINIMO_AGREGACAO = 5
TAMANHO_PSEUDONIMO = 16

SAL_PADRAO = "recorte-2025"

_MASCARA_CPF = re.compile(r"^\*{3}\d{6}\*{2}$")


def sal() -> str:
    """Sal do pseudonimo, de variavel de ambiente quando houver.

    Fora do repositorio por principio, como as outras credenciais. Com o sal
    padrao o pseudonimo e reproduzivel entre maquinas, que e o que o trabalho
    academico precisa; com um sal secreto ele deixa de ser reconstruivel por
    quem tenha a base de origem.
    """
    return os.getenv("SAL_PSEUDONIMO") or SAL_PADRAO


def chave_socio(nome: str, cpf_mascarado: str) -> str:
    """Chave interna do socio: nome mais mascara.

    A mascara sozinha nao serve de chave, porque colide: 169.762 chaves
    distintas para 195.748 linhas de socio em 200 mil. Os seis digitos do meio
    que a Receita preserva bastam para agrupar o mesmo socio entre empresas,
    que e o que a analise de rede precisa, sem identificar a pessoa.
    """
    return f"{(nome or '').strip().upper()}|{(cpf_mascarado or '').strip()}"


def pseudonimo(nome: str, cpf_mascarado: str, sal_proprio=None) -> str:
    """Identificador derivado, estavel, que substitui o nome na apresentacao."""
    segredo = (sal_proprio or sal()).encode("utf-8")
    bruto = chave_socio(nome, cpf_mascarado).encode("utf-8")
    return hmac.new(segredo, bruto, hashlib.sha256).hexdigest()[:TAMANHO_PSEUDONIMO]


def cpf_esta_mascarado(valor) -> bool:
    """Confere a mascara da origem: 3 ocultos, 6 visiveis, 2 verificadores ocultos.

    A descaracterizacao e exigencia legal citada no PDF de metadados do CNPJ
    (art. 129 par. 2 da Lei 13.473/2017), nao escolha nossa nem da Receita.
    """
    return bool(_MASCARA_CPF.match((valor or "").strip()))


def para_apresentacao(socio: dict) -> dict:
    """Troca nome e CPF por pseudonimo antes de qualquer exibicao.

    Levanta erro se o registro trouxer CPF sem mascara, porque nesse caso a
    origem mudou e a regra precisa ser revista antes de publicar qualquer
    coisa.
    """
    cpf = socio.get("cpf_mascarado") or socio.get("cpf") or ""
    if cpf and not cpf_esta_mascarado(cpf):
        raise ValueError(
            "RN-09: CPF sem a mascara esperada na camada de dados; "
            "nao publicar sem revisar a regra"
        )
    limpo = {k: v for k, v in socio.items()
             if k not in ("nome", "cpf", "cpf_mascarado", "nome_socio")}
    limpo["socio_id"] = pseudonimo(socio.get("nome") or socio.get("nome_socio"), cpf)
    return limpo


def suprimir(valor, n_socios=None, n_empresas=None, minimo=MINIMO_AGREGACAO):
    """Devolve None quando o recorte se apoia em menos de cinco socios ou empresas.

    Mesmo principio da supressao do IBGE, que oculta nome com menos de vinte
    ocorrencias no pais. Fica na camada de apresentacao e nao na visao
    materializada, porque o mesmo agregado pode ser seguro num recorte e
    inseguro noutro.
    """
    for contagem in (n_socios, n_empresas):
        if contagem is not None and contagem < minimo:
            return None
    return valor


def agregado_publicavel(n_socios=None, n_empresas=None, minimo=MINIMO_AGREGACAO) -> bool:
    return suprimir(True, n_socios, n_empresas, minimo) is True
