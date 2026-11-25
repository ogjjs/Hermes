"""Modelos compartilhados entre as camadas."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class LinhaLoja:
    film_id: int | None
    titulo: str
    vendido: int
    devolvido: int
    estoque_final: int
    preco: Decimal


@dataclass
class RelatorioLoja:
    loja_id: int
    mes: str
    linhas: list[LinhaLoja]
    repasse: Decimal
    recebido_em: date


@dataclass(frozen=True)
class ErroInjetado:
    loja_id: int
    mes: str
    codigo: str
    film_id: int | None = None


@dataclass
class LeituraArquivo:
    loja_id: int | None
    linhas: list[dict[str, str]]
    repasse: str | None
    leitor: str


@dataclass
class ResumoImportacao:
    lidos: int = 0
    ignorados_repetidos: int = 0
    substituidos: int = 0
    com_erro: list[tuple[str, str]] = field(default_factory=list)
