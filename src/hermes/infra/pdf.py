"""PDF com uma tabela de grade desenhada e texto por célula, com PyMuPDF. Só I/O.

A grade é o que deixa PyMuPDF (`find_tables`) e pdfplumber (`extract_tables`) acharem a
tabela; texto posto célula a célula mantém os espaços na extração.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

_A4 = pymupdf.paper_rect("a4")
_MARGEM = 36
_ALTURA = 16
_FONTE = 8
_PRETO = (0, 0, 0)


def _larguras(colunas: int) -> list[float]:
    util = _A4.width - 2 * _MARGEM
    if colunas == 1:
        return [util]
    primeira = util * 0.45
    return [primeira] + [(util - primeira) / (colunas - 1)] * (colunas - 1)


_HELV = pymupdf.Font("helv")
_NEGRITO = pymupdf.Font("hebo")


def _linha(forma, texto, y: float, celulas: list[str], larguras: list[float], negrito=False):
    x = _MARGEM
    for conteudo, largura in zip(celulas, larguras, strict=True):
        forma.draw_rect(pymupdf.Rect(x, y, x + largura, y + _ALTURA))
        texto.append(
            (x + 3, y + _ALTURA - 5),
            str(conteudo),
            font=_NEGRITO if negrito else _HELV,
            fontsize=_FONTE,
        )
        x += largura


def gerar_pdf_tabela(
    titulo: str,
    cabecalho: list[str],
    linhas: list[list[str]],
    rodape: list[str],
    atributos: dict[str, str],
    destino: Path,
) -> Path:
    """Título no alto da primeira página, a tabela (cabeçalho repetido em cada página) e o
    rodapé depois da última linha. Grade e texto são escritos em lote, por página."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    larguras = _larguras(len(cabecalho))
    por_pagina = int((_A4.height - 2 * _MARGEM - 3 * _ALTURA) // _ALTURA) - 1
    pedacos = [linhas[i : i + por_pagina] for i in range(0, len(linhas), por_pagina)] or [[]]
    doc = pymupdf.open()
    for numero, pedaco in enumerate(pedacos):
        pagina = doc.new_page(width=_A4.width, height=_A4.height)
        forma = pagina.new_shape()
        texto = pymupdf.TextWriter(pagina.rect)
        y = _MARGEM
        if numero == 0:
            texto.append((_MARGEM, y + 10), titulo, font=_NEGRITO, fontsize=11)
            y += 2 * _ALTURA
        _linha(forma, texto, y, cabecalho, larguras, negrito=True)
        for celulas in pedaco:
            y += _ALTURA
            _linha(forma, texto, y, celulas, larguras)
        if numero == len(pedacos) - 1:
            for linha in rodape:
                y += _ALTURA + 4
                texto.append((_MARGEM, y + 10), linha, font=_HELV, fontsize=9)
        forma.finish(color=_PRETO, width=0.5)
        forma.commit()
        texto.write_text(pagina)
    doc.set_metadata(atributos)
    doc.save(destino, deflate=True, no_new_id=True)
    doc.close()
    return destino
