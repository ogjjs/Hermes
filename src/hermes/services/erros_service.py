"""Erros postos de propósito nos relatórios das lojas, com o gabarito de onde foram postos.

Cada relatório tem chance `cfg.taxa_erro` de levar um erro. A loja continua coerente com o
que ela mesma escreveu: quando acrescenta ou tira uma linha, o repasse dela acompanha.
"""

from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal

from hermes.config import contrato_padrao as cp
from hermes.config.settings import Config
from hermes.core.dinheiro import centavos, valores
from hermes.core.modelos import ErroInjetado, LinhaLoja, RelatorioLoja
from hermes.core.sorteio import rng


def _repasse(linhas: list[LinhaLoja]) -> Decimal:
    return sum(
        (valores(x.vendido, x.preco, cp.COMISSAO, cp.CUSTO_PCT).repasse for x in linhas),
        start=Decimal("0.00"),
    )


def _aplicar(r: RelatorioLoja, codigo: str, g, catalogo: dict) -> int | None | bool:
    """Altera `r` no lugar. Devolve o film_id afetado, None (erro sem título) ou False
    quando o erro não cabe neste relatório."""
    if codigo == "SALDO_NAO_FECHA":
        x = r.linhas[int(g.integers(len(r.linhas)))]
        delta = int(g.choice([-2, -1, 1, 2]))
        x.estoque_final = (
            x.estoque_final + delta
            if x.estoque_final + delta >= 0
            else x.estoque_final + abs(delta)
        )
        return x.film_id
    if codigo == "TITULO_NAO_ENVIADO":
        da_loja = {x.film_id for x in r.linhas}
        livres = sorted(set(catalogo) - da_loja)
        film_id = int(livres[int(g.integers(len(livres)))])
        titulo, preco = catalogo[film_id]
        r.linhas.append(LinhaLoja(film_id, titulo, 1, 0, 0, preco))
        r.repasse = _repasse(r.linhas)
        return film_id
    if codigo == "TITULO_AUSENTE":
        com_estoque = [i for i, x in enumerate(r.linhas) if x.estoque_final > 0]
        if not com_estoque:
            return False
        x = r.linhas.pop(com_estoque[int(g.integers(len(com_estoque)))])
        r.repasse = _repasse(r.linhas)
        return x.film_id
    if codigo == "REPASSE_DIVERGENTE":
        delta = centavos(Decimal(int(g.integers(500, 5001))) / 100)
        r.repasse = r.repasse + (delta if g.random() < 0.5 else -delta)
        return None
    if codigo == "PRECO_DIVERGENTE":
        vendidas = [x for x in r.linhas if x.vendido > 0] or r.linhas
        x = vendidas[int(g.integers(len(vendidas)))]
        outros = sorted(p for p in cp.FAIXAS_PRECO.values() if p != x.preco)
        x.preco = outros[int(g.integers(len(outros)))]
        r.repasse = _repasse(r.linhas)
        return x.film_id
    if codigo == "DUPLICADO":
        x = r.linhas[int(g.integers(len(r.linhas)))]
        r.linhas.append(copy.copy(x))
        return x.film_id
    if codigo == "RELATORIO_ATRASADO":
        r.recebido_em = date(r.recebido_em.year, r.recebido_em.month, int(g.integers(11, 21)))
        return None
    if codigo == "RELATORIO_FALTANDO":
        return None
    raise ValueError(f"Código desconhecido: {codigo}")


def injetar_erros(
    relatorios: list[RelatorioLoja],
    cfg: Config,
    mes: str,
    catalogo: dict[int, tuple[str, Decimal]],
) -> tuple[list[RelatorioLoja], list[ErroInjetado]]:
    """Devolve cópias dos relatórios, com erros, e o gabarito. Não altera os originais.
    `catalogo`: film_id -> (título, preço de tabela)."""
    saida, gabarito = [], []
    for original in relatorios:
        r = copy.deepcopy(original)
        g = rng(cfg.semente, "erros", r.loja_id, mes)
        if not r.linhas or g.random() >= float(cfg.taxa_erro):
            saida.append(r)
            continue
        codigo = cp.CODIGOS_DIVERGENCIA[int(g.integers(len(cp.CODIGOS_DIVERGENCIA)))]
        afetado = _aplicar(r, codigo, g, catalogo)
        if afetado is not False:
            gabarito.append(ErroInjetado(r.loja_id, mes, codigo, afetado))
        if codigo != "RELATORIO_FALTANDO":
            saida.append(r)
    return saida, gabarito
