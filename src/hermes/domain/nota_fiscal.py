"""Conteúdo do espelho da nota fiscal fictícia: a tabela visível e os atributos (JSON) do PDF.

Os atributos repetem os valores da nota para servir de gabarito à leitura de PDF.
"""

from __future__ import annotations

import json

from hermes.core.dinheiro import texto_br

AVISO = "NOTA FISCAL FICTÍCIA — projeto de portfólio, sem valor fiscal"
CABECALHO = ["Título", "Qtd", "Preço", "Total"]


def atributos(nota: dict, itens: list[dict]) -> dict[str, str]:
    dados = {
        "numero": nota["numero"],
        "loja_id": nota["loja_id"],
        "mes": nota["mes"],
        "emitida_em": str(nota["emitida_em"]),
        "valor_total": f"{nota['valor_total']:.2f}",
        "itens": [
            {
                "film_id": i["film_id"],
                "titulo": i["titulo"],
                "quantidade": i["quantidade"],
                "preco_unit": f"{i['preco_unit']:.2f}",
            }
            for i in itens
        ],
    }
    return {
        "title": f"Nota fictícia {nota['numero']}",
        "subject": "Hermes — nota fiscal fictícia",
        "keywords": json.dumps(dados, ensure_ascii=False),
        "author": "Hermes",
    }


def tabela(nota: dict, itens: list[dict], cidade: str):
    """(título, cabeçalho, linhas, rodapé) para `infra.pdf.gerar_pdf_tabela`."""
    titulo = f"{AVISO} · Nota nº {nota['numero']}"
    linhas = [
        [
            i["titulo"],
            str(i["quantidade"]),
            texto_br(i["preco_unit"]),
            texto_br(i["quantidade"] * i["preco_unit"]),
        ]
        for i in itens
    ]
    rodape = [
        f"Loja {nota['loja_id']} — {cidade} · Emitida em {nota['emitida_em']:%d/%m/%Y} · "
        f"Mês {nota['mes']}",
        f"Valor total: R$ {texto_br(nota['valor_total'])}",
    ]
    return titulo, CABECALHO, linhas, rodape
