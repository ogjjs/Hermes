"""Interpretação do relatório mensal de uma loja, a partir das linhas cruas lidas do arquivo.

Funciona igual para CSV, Excel e PDF: o leitor entrega uma lista de linhas (listas de
texto), e aqui se acham a loja, o cabeçalho, as linhas de venda e o repasse declarado.
"""

from __future__ import annotations

import re

from hermes.config.contrato_padrao import APELIDOS
from hermes.core.erros import ErroHermes
from hermes.core.modelos import LeituraArquivo
from hermes.core.normalizacao import normalizar_texto

_LOJA = re.compile(r"(?i)loja\D{0,3}(\d+)")
_APELIDOS_TITULO = {a.casefold() for a in APELIDOS["titulo"]}


def _limpar(linha: list) -> list[str]:
    celulas = [normalizar_texto("" if c is None else str(c)).strip() for c in linha]
    while celulas and not celulas[-1]:
        celulas.pop()
    return celulas


def _repasse(celulas: list[str]) -> str | None:
    if ":" in celulas[0]:
        resto = celulas[0].split(":", 1)[1].strip()
        if resto:
            return resto
    return next((c for c in celulas[1:] if c), None)


def interpretar(cru: list[list], leitor: str = "") -> LeituraArquivo:
    linhas = [_limpar(linha) for linha in cru]
    loja_id = None
    for celulas in linhas[:5]:
        m = _LOJA.search(" ".join(celulas))
        if m:
            loja_id = int(m[1])
            break
    if loja_id is None:
        raise ErroHermes("não achei o código da loja nas primeiras linhas")
    inicio = next(
        (i for i, c in enumerate(linhas) if any(x.casefold() in _APELIDOS_TITULO for x in c)), None
    )
    if inicio is None:
        raise ErroHermes("não achei o cabeçalho da tabela")
    cabecalho = linhas[inicio]
    dados, repasse = [], None
    for numero, celulas in enumerate(linhas[inicio + 1 :], start=1):
        if not celulas:
            continue
        if celulas[0].casefold().startswith("repasse"):
            repasse = _repasse(celulas)
            break
        if len(celulas) != len(cabecalho):
            raise ErroHermes(
                f"linha {numero} tem {len(celulas)} colunas e o cabeçalho tem {len(cabecalho)}"
            )
        dados.append(dict(zip(cabecalho, celulas, strict=True)))
    if not dados:
        raise ErroHermes("não achei nenhuma linha de venda")
    return LeituraArquivo(loja_id, dados, repasse, leitor)
