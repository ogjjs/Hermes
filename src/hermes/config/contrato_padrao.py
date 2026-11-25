"""Valores fixos do negócio fictício: contrato padrão, formatos e apelidos das colunas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

# rental_rate do Pagila -> preço de tabela em R$
FAIXAS_PRECO = {
    Decimal("0.99"): Decimal("19.90"),
    Decimal("2.99"): Decimal("29.90"),
    Decimal("4.99"): Decimal("39.90"),
}
COMISSAO = Decimal("0.30")  # fica com a loja, sobre a venda
CUSTO_PCT = Decimal("0.40")  # custo da distribuidora, sobre o preço
VIGENCIA_INICIO = date(2025, 8, 1)
PRIMEIRO_MES = "2025-08"
ULTIMO_MES = "2026-07"
PAIS_DAS_LOJAS = "Brazil"

DIA_LIMITE_RELATORIO = 10  # o relatório do mês chega até este dia do mês seguinte
DIA_REMESSA = 11  # remessa emitida neste dia (no primeiro mês, dia 1)
TOLERANCIA_REPASSE = Decimal("0.01")

TITULOS_POR_LOJA = (40, 120)
ESTOQUE_ALVO = (2, 6)

FORMATOS = ("csv_ponto_virgula", "csv_virgula", "xlsx", "pdf")

# campo padronizado -> apelidos possíveis no arquivo da loja (cada loja usa um, sempre o mesmo)
APELIDOS = {
    "titulo": ("Título", "FILME", "titulo_filme"),
    "vendido": ("Qtd vendida", "VENDIDOS", "qtd_vend"),
    "devolvido": ("Devolvidos", "DEVOL", "qtd_dev"),
    "estoque_final": ("Estoque", "SALDO FINAL", "estq"),
    "preco": ("Preço unit.", "VALOR UN", "preco"),
}

CODIGOS_DIVERGENCIA = (
    "SALDO_NAO_FECHA",
    "TITULO_NAO_ENVIADO",
    "TITULO_AUSENTE",
    "REPASSE_DIVERGENTE",
    "PRECO_DIVERGENTE",
    "RELATORIO_ATRASADO",
    "RELATORIO_FALTANDO",
    "DUPLICADO",
)
