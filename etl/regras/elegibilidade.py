"""RN-02. Elegibilidade do contrato: valor, corte de sanidade e receita."""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CORTE_SANIDADE = Decimal("1000000000.00")
CORTE_SENSIBILIDADE = Decimal("100000000.00")

CENTAVO = Decimal("0.01")


def para_decimal(valor):
    """Converte para DECIMAL(18,2) do mesmo jeito que o TRY_CAST do DuckDB.

    Devolve None no lugar de levantar erro, porque o tratamento usa TRY_CAST e
    um valor ilegivel vira nulo em vez de derrubar a carga.
    """
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def centavos(valor) -> int:
    """Valor em centavos, que e a unidade em que a regra do maior que zero vale.

    E aqui que moram os 245 contratos do JSON bruto com valor positivo menor
    que meio centavo: eles arredondam para zero e deixam de ser elegiveis.
    """
    convertido = para_decimal(valor)
    if convertido is None:
        return 0
    return int(convertido * 100)


def valor_positivo(valor) -> bool:
    return centavos(valor) > 0


def acima_do_corte(valor, corte=CORTE_SANIDADE) -> bool:
    convertido = para_decimal(valor)
    if convertido is None:
        return False
    return convertido > Decimal(corte)


def elegivel(valor_global, receita=False, corte=CORTE_SANIDADE) -> bool:
    """Entra nos indicadores de valor e nos KPIs.

    O periodo nao aparece como parametro porque e garantido pela coleta: a API
    do PNCP e consultada por data de publicacao (D7).
    """
    if not valor_positivo(valor_global):
        return False
    if acima_do_corte(valor_global, corte):
        return False
    return not bool(receita)


def marcar(valor_global, receita=False) -> dict:
    """Marca em vez de apagar (D3 e D9).

    Quem falha no corte de sanidade ou e contrato de receita continua no
    Parquet com a marca, e sai so dos indicadores de valor.
    """
    receita = bool(receita)
    suspeito = acima_do_corte(valor_global)
    positivo = valor_positivo(valor_global)
    return {
        "valor_centavos": centavos(valor_global),
        "valor_zerado": not positivo,
        "contrato_suspeito": suspeito,
        "acima_sensibilidade": acima_do_corte(valor_global, CORTE_SENSIBILIDADE),
        "receita": receita,
        "elegivel_valor": positivo and not suspeito and not receita,
    }
