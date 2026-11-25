"""Leitura crua dos arquivos das lojas: cada função devolve as linhas como listas de texto.
Só I/O; quem entende o conteúdo é `domain.relatorio_loja`."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pdfplumber
import pymupdf


def linhas_csv(caminho: Path) -> list[list[str]]:
    texto = caminho.read_text(encoding="utf-8-sig")
    corpo = texto.splitlines()[1:]
    sep = ";" if sum(x.count(";") for x in corpo) >= sum(x.count(",") for x in corpo) else ","
    largura = max((len(r) for r in csv.reader(texto.splitlines(), delimiter=sep)), default=1)
    tabela = pd.read_csv(
        caminho,
        sep=sep,
        header=None,
        names=range(largura),
        dtype=str,
        keep_default_na=False,
        skip_blank_lines=False,
        encoding="utf-8-sig",
    )
    return tabela.values.tolist()


def linhas_xlsx(caminho: Path) -> list[list[str]]:
    tabela = pd.read_excel(caminho, header=None, dtype=str, engine="openpyxl")
    return tabela.fillna("").values.tolist()


def _texto_em_linhas(texto: str) -> list[list[str]]:
    return [[x] for x in texto.splitlines()]


def _linhas_da_pagina(pagina) -> list[list[str]]:
    """Monta as linhas pelas palavras e pela grade desenhada: cada retângulo é uma célula.
    Palavra fora da grade (título, repasse) vira uma linha de uma célula só."""
    celulas = [
        item[1]
        for d in pagina.get_drawings()
        for item in d["items"]
        if item[0] == "re" and item[1].width > 1
    ]
    colunas = sorted({round(r.x0, 1) for r in celulas})
    topo = min((r.y0 for r in celulas), default=0)
    base = max((r.y1 for r in celulas), default=0)
    por_linha: dict[int, dict[int, list[str]]] = {}
    for x0, y0, _x1, y1, palavra, *_ in pagina.get_text("words", sort=True):
        meio = (y0 + y1) / 2
        chave = round(meio / 4)
        if celulas and topo <= meio <= base:
            coluna = (
                max(i for i, c in enumerate(colunas) if c <= x0 + 0.5) if x0 >= colunas[0] else 0
            )
        else:
            coluna = -1
        por_linha.setdefault(chave, {}).setdefault(coluna, []).append(palavra)
    linhas = []
    for chave in sorted(por_linha):
        grupos = por_linha[chave]
        if -1 in grupos:
            linhas.append([" ".join(grupos[-1])])
            continue
        linhas.append([" ".join(grupos.get(i, [])) for i in range(len(colunas))])
    return linhas


def linhas_pdf_pymupdf(caminho: Path) -> list[list[str]]:
    """Tentativa 1: palavras + grade, página a página (o cabeçalho repetido é pulado)."""
    linhas: list[list[str]] = []
    with pymupdf.open(caminho) as doc:
        for numero, pagina in enumerate(doc):
            da_pagina = _linhas_da_pagina(pagina)
            if numero > 0:
                da_pagina = _sem_cabecalho_repetido(da_pagina, linhas)
            linhas += da_pagina
    return linhas


def _sem_cabecalho_repetido(da_pagina: list[list[str]], anteriores: list[list[str]]):
    """Na página 2 em diante, a primeira linha de várias colunas repete o cabeçalho."""
    cabecalho = next((x for x in anteriores if len(x) > 1), None)
    return [x for i, x in enumerate(da_pagina) if not (x == cabecalho and i == 0)]


def linhas_pdf_pdfplumber(caminho: Path) -> list[list[str]]:
    linhas: list[list[str]] = []
    with pdfplumber.open(caminho) as pdf:
        for numero, pagina in enumerate(pdf.pages):
            texto = pagina.extract_text() or ""
            if numero == 0:
                linhas += _texto_em_linhas(texto)[:1]
            for tabela in pagina.extract_tables():
                linhas += [[c or "" for c in x] for x in (tabela if numero == 0 else tabela[1:])]
            linhas += [x for x in _texto_em_linhas(texto) if x[0].startswith("Repasse")]
    return linhas
