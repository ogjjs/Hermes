"""Cadastro das lojas parceiras, do contrato padrão e do sortimento de cada loja."""

from __future__ import annotations

import json

import numpy as np
import psycopg

from hermes.config import contrato_padrao as cp
from hermes.config.settings import Config
from hermes.core.sorteio import rng
from hermes.infra.db import executar_sql


def popularidade(conn: psycopg.Connection) -> dict[int, float]:
    """Aluguéis de cada filme no Pagila, normalizados de 0 a 1. Filme sem aluguel conta como 1
    aluguel, para ainda poder ser sorteado."""
    linhas = conn.execute(
        """select f.film_id, greatest(count(r.rental_id), 1) as n
             from public.film f
             left join public.inventory i on i.film_id = f.film_id
             left join public.rental r on r.inventory_id = i.inventory_id
            group by f.film_id order by f.film_id"""
    ).fetchall()
    maior = max(r["n"] for r in linhas)
    return {r["film_id"]: r["n"] / maior for r in linhas}


def _lojas_do_brasil(conn: psycopg.Connection) -> list[dict]:
    return conn.execute(
        """select s.store_id as loja_id, ci.city as cidade
             from public.store s
             join public.address a using (address_id)
             join public.city ci using (city_id)
             join public.country co using (country_id)
            where co.country = %s
            order by s.store_id""",
        (cp.PAIS_DAS_LOJAS,),
    ).fetchall()


def _sortimento(cfg: Config, loja_id: int, pop: dict[int, float]) -> list[tuple[int, int]]:
    g = rng(cfg.semente, "sortimento", loja_id)
    ids = np.array(sorted(pop))
    pesos = np.array([pop[i] for i in ids])
    minimo, maximo = cp.TITULOS_POR_LOJA
    n = int(g.integers(minimo, maximo + 1))
    escolhidos = g.choice(ids, size=n, replace=False, p=pesos / pesos.sum())
    alvo_min, alvo_max = cp.ESTOQUE_ALVO
    resultado = []
    for film_id in sorted(int(f) for f in escolhidos):
        extra = int(g.binomial(alvo_max - alvo_min, 0.25 + 0.75 * pop[film_id]))
        resultado.append((film_id, alvo_min + extra))
    return resultado


def preparar(conn: psycopg.Connection, cfg: Config) -> int:
    """Cadastra lojas, contratos, preços e sortimentos. Pode rodar de novo: não duplica e,
    com a mesma semente, chega ao mesmo cadastro. Cria os schemas se faltarem. Devolve o
    número de lojas."""
    executar_sql(conn, "001_schemas.sql")
    pop = popularidade(conn)
    lojas = _lojas_do_brasil(conn)
    for loja in lojas:
        g = rng(cfg.semente, "loja", loja["loja_id"])
        formato = cp.FORMATOS[int(g.integers(len(cp.FORMATOS)))]
        mapeamento = {
            campo: apelidos[int(g.integers(len(apelidos)))]
            for campo, apelidos in cp.APELIDOS.items()
        }
        conn.execute(
            "insert into hermes.loja (loja_id, cidade, formato, mapeamento) "
            "values (%s, %s, %s, %s) on conflict do nothing",
            (loja["loja_id"], loja["cidade"], formato, json.dumps(mapeamento)),
        )
        contrato = conn.execute(
            """insert into hermes.contrato (loja_id, vigencia_inicio, comissao, custo_pct)
               values (%s, %s, %s, %s)
               on conflict (loja_id, vigencia_inicio) do update set loja_id = excluded.loja_id
               returning contrato_id""",
            (loja["loja_id"], cp.VIGENCIA_INICIO, cp.COMISSAO, cp.CUSTO_PCT),
        ).fetchone()["contrato_id"]
        for faixa, preco in cp.FAIXAS_PRECO.items():
            conn.execute(
                "insert into hermes.preco values (%s, %s, %s) on conflict do nothing",
                (contrato, faixa, preco),
            )
        with conn.cursor() as cur:
            cur.executemany(
                "insert into hermes.sortimento values (%s, %s, %s) on conflict do nothing",
                [(loja["loja_id"], f, a) for f, a in _sortimento(cfg, loja["loja_id"], pop)],
            )
    conn.commit()
    return len(lojas)
