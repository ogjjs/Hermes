"""O que cada loja fez no mês (a verdade, sem erro nenhum)."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal

import psycopg

from hermes.config import contrato_padrao as cp
from hermes.config.settings import Config
from hermes.core.dinheiro import valores
from hermes.core.meses import dia, proximo_mes
from hermes.core.modelos import ErroInjetado, LinhaLoja, RelatorioLoja
from hermes.core.sorteio import rng
from hermes.infra.escritores import escrever_recebidos, escrever_relatorio
from hermes.services.cadastro_service import popularidade
from hermes.services.erros_service import injetar_erros
from hermes.services.remessa_service import estoque_inicial

CHANCE_BASE_VENDA = 0.35
CHANCE_EXTRA_POPULAR = 0.40
CHANCE_DEVOLUCAO = 0.15


def simular_vendas(conn: psycopg.Connection, cfg: Config, mes: str) -> list[RelatorioLoja]:
    pop = popularidade(conn)
    lojas = conn.execute(
        "select m.loja_id, c.comissao, c.custo_pct from hermes.mes_loja m "
        "join hermes.contrato c using (loja_id) where m.mes = %s order by 1",
        (mes,),
    ).fetchall()
    relatorios = []
    for loja in lojas:
        g = rng(cfg.semente, "vendas", loja["loja_id"], mes)
        estoque = estoque_inicial(conn, loja["loja_id"], mes)
        recebido = {
            r["film_id"]: r["quantidade"]
            for r in conn.execute(
                "select film_id, quantidade from hermes.nota_item join hermes.nota "
                "using (nota_id) where loja_id = %s and mes = %s",
                (loja["loja_id"], mes),
            )
        }
        titulos = sorted(set(estoque) | set(recebido))
        info = {
            r["film_id"]: r
            for r in conn.execute(
                """select f.film_id, f.title, p.preco
                     from public.film f
                     join hermes.contrato c on c.loja_id = %s
                     join hermes.preco p on p.contrato_id = c.contrato_id
                                        and p.rental_rate = f.rental_rate
                    where f.film_id = any(%s)""",
                (loja["loja_id"], titulos),
            )
        }
        linhas = []
        for film_id in titulos:
            disponivel = estoque.get(film_id, 0) + recebido.get(film_id, 0)
            chance = CHANCE_BASE_VENDA + CHANCE_EXTRA_POPULAR * pop[film_id]
            vendido = int(g.binomial(disponivel, chance))
            devolvido = int(g.binomial(disponivel - vendido, CHANCE_DEVOLUCAO))
            linhas.append(
                LinhaLoja(
                    film_id,
                    info[film_id]["title"],
                    vendido,
                    devolvido,
                    disponivel - vendido - devolvido,
                    info[film_id]["preco"],
                )
            )
        repasse = sum(
            (
                valores(x.vendido, x.preco, loja["comissao"], loja["custo_pct"]).repasse
                for x in linhas
            ),
            start=Decimal("0.00"),
        )
        dia_chegada = int(g.integers(1, cp.DIA_LIMITE_RELATORIO + 1))
        relatorios.append(
            RelatorioLoja(loja["loja_id"], mes, linhas, repasse, dia(proximo_mes(mes), dia_chegada))
        )
    return relatorios


_NOMES = ("relatorio_{mes}_{loja}", "vendas-{loja}", "fechamento {mes} loja {loja}")


def catalogo(conn: psycopg.Connection) -> dict[int, tuple[str, Decimal]]:
    """Todos os filmes do Pagila com o preço de tabela do contrato padrão."""
    return {
        r["film_id"]: (r["title"], cp.FAIXAS_PRECO[r["rental_rate"]])
        for r in conn.execute("select film_id, title, rental_rate from public.film")
    }


def simular_mes(conn: psycopg.Connection, cfg: Config, mes: str) -> list[ErroInjetado]:
    """Vendas do mês, erros de propósito e os arquivos em `pasta_entrada/<mes>/`, com
    `_recebidos.csv` (como chegariam por e-mail) e `_gabarito.json`. Devolve o gabarito."""
    verdade = simular_vendas(conn, cfg, mes)
    relatorios, gabarito = injetar_erros(verdade, cfg, mes, catalogo(conn))
    lojas = {
        r["loja_id"]: r
        for r in conn.execute("select loja_id, cidade, formato, mapeamento from hermes.loja")
    }
    pasta = cfg.pasta_entrada / mes
    pasta.mkdir(parents=True, exist_ok=True)
    recebidos = []
    for r in relatorios:
        g = rng(cfg.semente, "nome", r.loja_id, mes)
        nome = _NOMES[int(g.integers(len(_NOMES)))].format(mes=mes, loja=r.loja_id)
        caminho = escrever_relatorio(r, lojas[r.loja_id], pasta / nome)
        recebidos.append((caminho.name, r.recebido_em.isoformat()))
    escrever_recebidos(recebidos, pasta / "_recebidos.csv")
    (pasta / "_gabarito.json").write_text(
        json.dumps([asdict(e) for e in gabarito], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return gabarito
