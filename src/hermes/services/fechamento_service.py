"""Fechamento do mês: aplica as decisões e grava a camada `relatorio`."""

from __future__ import annotations

import psycopg

from hermes.config.settings import Config
from hermes.core.erros import ErroHermes
from hermes.core.meses import validar_mes
from hermes.infra.db import executar_sql


def fechar_mes(conn: psycopg.Connection, cfg: Config, mes: str) -> None:
    """Recusa, sem gravar nada, se o mês não foi conferido ou ainda tem divergência aberta.
    Pode rodar de novo: refaz o fechamento igual."""
    validar_mes(mes)
    if not conn.execute("select 1 from hermes.mes_loja where mes = %s", (mes,)).fetchone():
        raise ErroHermes(f"Não há remessa em {mes}: rode hermes emitir {mes} primeiro.")
    if not conn.execute("select 1 from conferido.saldo where mes = %s", (mes,)).fetchone():
        raise ErroHermes(f"{mes} ainda não foi conferido: rode hermes conferir {mes}")
    abertas = conn.execute(
        "select count(*) n from hermes.divergencia where mes = %s and estado = 'aberta'", (mes,)
    ).fetchone()["n"]
    if abertas:
        raise ErroHermes(
            f"{abertas} divergências abertas em {mes}: decida cada uma com hermes decidir "
            f"(veja a lista com hermes divergencias {mes})"
        )
    try:
        executar_sql(conn, "fechar.sql", {"mes": mes})
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def resumo_mes(conn: psycopg.Connection, mes: str) -> dict | None:
    """A linha de `relatorio.mes`, mais quantas divergências o mês teve."""
    r = conn.execute("select * from relatorio.mes where mes = %s", (mes,)).fetchone()
    if r is None:
        return None
    n = conn.execute("select count(*) n from hermes.divergencia where mes = %s", (mes,)).fetchone()[
        "n"
    ]
    return {**r, "divergencias": n}
