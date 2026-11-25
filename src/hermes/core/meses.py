"""Meses no formato AAAA-MM."""

from __future__ import annotations

import re
from datetime import date

from hermes.core.erros import ErroHermes

_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def validar_mes(mes: str) -> tuple[int, int]:
    m = _MES.match(mes or "")
    if not m:
        raise ErroHermes(f"Mês inválido: {mes!r}. Use AAAA-MM, por exemplo 2025-08.")
    return int(m[1]), int(m[2])


def _texto(ano: int, mes: int) -> str:
    return f"{ano:04d}-{mes:02d}"


def mes_anterior(mes: str) -> str:
    ano, m = validar_mes(mes)
    return _texto(ano - 1, 12) if m == 1 else _texto(ano, m - 1)


def proximo_mes(mes: str) -> str:
    ano, m = validar_mes(mes)
    return _texto(ano + 1, 1) if m == 12 else _texto(ano, m + 1)


def meses(inicio: str, fim: str) -> list[str]:
    validar_mes(fim)
    lista, atual = [], inicio
    while atual <= fim:
        lista.append(atual)
        atual = proximo_mes(atual)
    return lista


def dia(mes: str, numero: int) -> date:
    ano, m = validar_mes(mes)
    return date(ano, m, numero)
