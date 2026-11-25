"""Contas do contrato em Decimal, arredondadas por linha para centavos (meio para cima)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTAVO = Decimal("0.01")


def centavos(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def ler_valor(texto: str | int | float | Decimal | None) -> Decimal | None:
    """Número escrito do jeito brasileiro ou americano -> Decimal. Vazio -> None.
    Com vírgula e ponto, o separador decimal é o que vem por último."""
    if texto is None:
        return None
    if isinstance(texto, (int, Decimal)):
        return Decimal(texto)
    if isinstance(texto, float):
        return Decimal(str(texto))
    s = str(texto).replace("R$", "").replace(" ", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s and "." in s:
        decimal_, milhar = (",", ".") if s.rfind(",") > s.rfind(".") else (".", ",")
        s = s.replace(milhar, "").replace(decimal_, ".")
    elif "," in s:
        if s.count(",") > 1:
            raise ValueError(f"Número inválido: {texto!r}")
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"Número inválido: {texto!r}") from None
    if not v.is_finite():
        raise ValueError(f"Número inválido: {texto!r}")
    return v


def texto_br(v: Decimal) -> str:
    """1234.5 -> "1.234,50"."""
    inteiro, _, frac = f"{centavos(v):.2f}".partition(".")
    sinal = "-" if inteiro.startswith("-") else ""
    return f"{sinal}{int(inteiro.lstrip('-')):,}".replace(",", ".") + f",{frac}"


def texto_us(v: Decimal) -> str:
    """1234.5 -> "1234.50"."""
    return f"{centavos(v):.2f}"


@dataclass(frozen=True)
class Valores:
    venda: Decimal
    comissao: Decimal
    repasse: Decimal
    custo: Decimal
    lucro: Decimal


def valores(vendido: int, preco: Decimal, comissao: Decimal, custo_pct: Decimal) -> Valores:
    """O que uma linha vendida vale: a loja fica com a comissão e repassa o resto; o custo é
    uma fração fixa do preço."""
    venda = centavos(vendido * preco)
    parte_loja = centavos(venda * comissao)
    repasse = venda - parte_loja
    custo = centavos(vendido * centavos(preco * custo_pct))
    return Valores(venda, parte_loja, repasse, custo, repasse - custo)
