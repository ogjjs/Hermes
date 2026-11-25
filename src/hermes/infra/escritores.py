"""Escreve o relatório de uma loja no formato dela (CSV, Excel ou PDF). Só I/O."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

import pandas as pd

from hermes.core.dinheiro import texto_br, texto_us
from hermes.core.modelos import RelatorioLoja
from hermes.infra.pdf import gerar_pdf_tabela

EXTENSAO = {"csv_ponto_virgula": ".csv", "csv_virgula": ".csv", "xlsx": ".xlsx", "pdf": ".pdf"}
_CAMPOS = ("titulo", "vendido", "devolvido", "estoque_final", "preco")
_DATA_FIXA = datetime(2026, 1, 1)  # o .xlsx não leva a hora em que foi gerado


def titulo_do_relatorio(r: RelatorioLoja, cidade: str) -> str:
    return f"Loja {r.loja_id} - {cidade} - Relatório {r.mes}"


def _tabela(r: RelatorioLoja, mapeamento: dict, numero) -> pd.DataFrame:
    linhas = [
        {
            mapeamento["titulo"]: x.titulo,
            mapeamento["vendido"]: x.vendido,
            mapeamento["devolvido"]: x.devolvido,
            mapeamento["estoque_final"]: x.estoque_final,
            mapeamento["preco"]: numero(x.preco),
        }
        for x in r.linhas
    ]
    return pd.DataFrame(linhas, columns=[mapeamento[c] for c in _CAMPOS])


def _csv(r: RelatorioLoja, loja: dict, destino: Path, sep: str, numero) -> None:
    corpo = io.StringIO()
    corpo.write(titulo_do_relatorio(r, loja["cidade"]) + "\n")
    _tabela(r, loja["mapeamento"], numero).to_csv(corpo, sep=sep, index=False, lineterminator="\n")
    csv.writer(corpo, delimiter=sep, lineterminator="\n").writerow(
        ["Repasse total", numero(r.repasse)]
    )
    destino.write_text(corpo.getvalue(), encoding="utf-8", newline="")


def _xlsx(r: RelatorioLoja, loja: dict, destino: Path) -> None:
    tabela = _tabela(r, loja["mapeamento"], float)
    with pd.ExcelWriter(destino, engine="openpyxl") as escritor:
        tabela.to_excel(escritor, index=False, startrow=2, sheet_name="Relatorio")
        ws = escritor.sheets["Relatorio"]
        ws["A1"] = titulo_do_relatorio(r, loja["cidade"])
        fim = len(tabela) + 4
        ws.cell(row=fim, column=1, value="Repasse total")
        ws.cell(row=fim, column=2, value=float(r.repasse))
        escritor.book.properties.created = _DATA_FIXA
        escritor.book.properties.modified = _DATA_FIXA


def _pdf(r: RelatorioLoja, loja: dict, destino: Path) -> None:
    mapa = loja["mapeamento"]
    linhas = [
        [x.titulo, str(x.vendido), str(x.devolvido), str(x.estoque_final), texto_br(x.preco)]
        for x in r.linhas
    ]
    titulo = titulo_do_relatorio(r, loja["cidade"])
    gerar_pdf_tabela(
        titulo,
        [mapa[c] for c in _CAMPOS],
        linhas,
        [f"Repasse total: {texto_br(r.repasse)}"],
        {"title": titulo},
        destino,
    )


def escrever_relatorio(r: RelatorioLoja, loja: dict, destino_sem_extensao: Path) -> Path:
    """`loja`: {"formato", "mapeamento", "cidade"}. Devolve o caminho gravado."""
    destino = destino_sem_extensao.with_name(destino_sem_extensao.name + EXTENSAO[loja["formato"]])
    destino.parent.mkdir(parents=True, exist_ok=True)
    if loja["formato"] == "csv_ponto_virgula":
        _csv(r, loja, destino, ";", texto_br)
    elif loja["formato"] == "csv_virgula":
        _csv(r, loja, destino, ",", texto_us)
    elif loja["formato"] == "xlsx":
        _xlsx(r, loja, destino)
    else:
        _pdf(r, loja, destino)
    return destino


def escrever_recebidos(recebidos: list[tuple[str, str]], destino: Path) -> Path:
    """O registro dos e-mails: nome do arquivo e data (AAAA-MM-DD) em que chegou."""
    texto = "arquivo;recebido_em\n" + "".join(f"{n};{d}\n" for n, d in recebidos)
    destino.write_text(texto, encoding="utf-8", newline="")
    return destino
