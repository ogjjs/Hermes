from decimal import Decimal

import pytest

from hermes.core.dinheiro import Valores, centavos, ler_valor, valores
from hermes.core.meses import mes_anterior, meses, proximo_mes
from hermes.core.normalizacao import normalizar_titulo


def test_exemplo_do_desenho():
    v = valores(8, Decimal("29.90"), Decimal("0.30"), Decimal("0.40"))
    assert v == Valores(
        Decimal("239.20"), Decimal("71.76"), Decimal("167.44"), Decimal("95.68"), Decimal("71.76")
    )


def test_centavos_arredonda_meio_para_cima():
    assert centavos(Decimal("0.125")) == Decimal("0.13")
    assert centavos(Decimal("0.124")) == Decimal("0.12")


def test_nada_vendido_da_zero():
    assert valores(0, Decimal("39.90"), Decimal("0.30"), Decimal("0.40")) == Valores(
        *(Decimal("0.00"),) * 5
    )


def test_meses():
    lista = meses("2025-08", "2026-07")
    assert lista[0] == "2025-08" and lista[-1] == "2026-07" and len(lista) == 12
    assert mes_anterior("2026-01") == "2025-12"
    assert proximo_mes("2025-12") == "2026-01"


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.234,56", "1234.56"),
        ("1234,56", "1234.56"),
        ("1,234.56", "1234.56"),
        ("R$ 39,90", "39.90"),
        ("39.9", "39.90"),
        ("1.234.567", "1234567"),
        ("  ", None),
        (None, None),
        (7, "7"),
        (29.9, "29.9"),
    ],
)
def test_ler_valor(texto, esperado):
    assert ler_valor(texto) == (None if esperado is None else Decimal(esperado))


@pytest.mark.parametrize("texto", ["abc", "12a", "1,2,3"])
def test_ler_valor_texto_invalido(texto):
    with pytest.raises(ValueError):
        ler_valor(texto)


def test_normalizar_titulo():
    assert normalizar_titulo("  academy   dinosaur ") == "ACADEMY DINOSAUR"
    assert normalizar_titulo("ﬁsh") == "FISH"
