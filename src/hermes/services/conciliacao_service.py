"""Conciliação do mês: o que a loja disse contra o que a distribuidora mandou."""

from __future__ import annotations

import psycopg

from hermes.config.settings import Config
from hermes.core.erros import ErroHermes
from hermes.core.meses import validar_mes
from hermes.infra.db import executar_sql


def conferir_mes(conn: psycopg.Connection, cfg: Config, mes: str) -> dict[str, int]:
    """Refaz o saldo das lojas com o mês aberto e registra as divergências novas.
    Devolve quantas divergências o mês tem, por código."""
    validar_mes(mes)
    if not conn.execute("select 1 from hermes.mes_loja where mes = %s", (mes,)).fetchone():
        raise ErroHermes(f"Não há remessa em {mes}: rode hermes emitir {mes} primeiro.")
    executar_sql(conn, "conciliar.sql", {"mes": mes})
    contagem = conn.execute(
        "select codigo, count(*) n from hermes.divergencia where mes = %s group by codigo",
        (mes,),
    ).fetchall()
    conn.commit()
    return {r["codigo"]: r["n"] for r in contagem}
