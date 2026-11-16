"""RN-07. Concentracao societaria e marcacao de sobreposicao."""

from collections import defaultdict
from decimal import Decimal

MINIMO_EMPRESAS_MULTIEMPRESA = 2


def agrupar_por_socio(vinculos):
    """Mapeia socio -> conjunto de raizes de CNPJ.

    `vinculos` e uma sequencia de pares (chave_socio, cnpj_raiz). A chave do
    socio e a da RN-09, nome mais mascara, nunca a mascara sozinha: ela colide
    (169.762 chaves para 195.748 linhas em 200 mil).
    """
    por_socio = defaultdict(set)
    for chave_socio, cnpj_raiz in vinculos:
        if not chave_socio or not cnpj_raiz:
            continue
        por_socio[chave_socio].add(cnpj_raiz)
    return dict(por_socio)


def socios_multiempresa(vinculos, minimo=MINIMO_EMPRESAS_MULTIEMPRESA):
    """Socios que integram duas ou mais empresas com contrato no recorte."""
    por_socio = agrupar_por_socio(vinculos)
    return {s: e for s, e in por_socio.items() if len(e) >= minimo}


def valor_controlado(vinculos, valor_por_empresa, minimo=MINIMO_EMPRESAS_MULTIEMPRESA):
    """Soma dos valores contratados das empresas de cada socio multiempresa.

    Devolve, por socio, o valor somado, quantas empresas ele integra e se a
    soma esta sobreposta. Sem a marcacao de sobreposicao o somatorio por socio
    ultrapassa o total contratado, porque o mesmo valor e contado uma vez para
    cada socio da empresa, e a metrica perde sentido.
    """
    multi = socios_multiempresa(vinculos, minimo)
    sobrepostas = empresas_sobrepostas(vinculos, minimo)

    resultado = {}
    for socio, empresas in multi.items():
        total = sum(
            (Decimal(str(valor_por_empresa.get(e, 0))) for e in empresas),
            Decimal("0"),
        )
        resultado[socio] = {
            "empresas": len(empresas),
            "valor_controlado": total,
            "sobreposto": any(e in sobrepostas for e in empresas),
        }
    return resultado


def empresas_sobrepostas(vinculos, minimo=MINIMO_EMPRESAS_MULTIEMPRESA):
    """Empresas com mais de um socio multiempresa no quadro."""
    multi = socios_multiempresa(vinculos, minimo)
    contagem = defaultdict(int)
    for socio, empresas in multi.items():
        for empresa in empresas:
            contagem[empresa] += 1
    return {e for e, n in contagem.items() if n > 1}


def total_sem_dupla_contagem(vinculos, valor_por_empresa,
                             minimo=MINIMO_EMPRESAS_MULTIEMPRESA):
    """Valor das empresas com ao menos um socio multiempresa, contado uma vez.

    E o numero que pode ser somado e comparado ao total contratado. A soma dos
    `valor_controlado` por socio nao pode, e e esse o ponto da regra.
    """
    multi = socios_multiempresa(vinculos, minimo)
    empresas = {e for empresas in multi.values() for e in empresas}
    return sum(
        (Decimal(str(valor_por_empresa.get(e, 0))) for e in empresas),
        Decimal("0"),
    )
