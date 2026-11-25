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
    pendentes = conn.execute(
        "select count(*) n from hermes.mes_loja where mes = %s "
        "and situacao in ('aberto', 'importado')",
        (mes,),
    ).fetchone()["n"]
    if pendentes:
        raise ErroHermes(
            f"{pendentes} lojas de {mes} ainda não foram conferidas: rode hermes conferir {mes}"
        )
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
        _conferir_contas(conn, mes)
    except Exception:
        conn.rollback()
        raise
    conn.commit()


def _conferir_contas(conn: psycopg.Connection, mes: str) -> None:
    """Invariantes do fechamento; se uma falha, nada do mês é gravado."""
    negativos = conn.execute(
        "select loja_id, count(*) n from conferido.saldo where mes = %s and estoque_final < 0 "
        "group by loja_id order by loja_id",
        (mes,),
    ).fetchall()
    if negativos:
        lojas = ", ".join(str(r["loja_id"]) for r in negativos)
        raise ErroHermes(
            f"estoque negativo em {mes} (lojas {lojas}): a loja declarou mais venda e devolução "
            "do que tinha. Aceite o estoque dela ou peça o relatório corrigido."
        )
    errado = conn.execute(
        "select count(*) n from conferido.saldo where mes = %s and estoque_inicial + recebido "
        "- vendido - devolvido + ajuste <> estoque_final",
        (mes,),
    ).fetchone()["n"]
    s = conn.execute(
        "select (select coalesce(sum(lucro), 0) from relatorio.titulo_mes where mes = %(m)s) t,"
        " (select coalesce(sum(ajuste_repasse), 0) from relatorio.loja_mes where mes = %(m)s) a,"
        " (select coalesce(sum(lucro), 0) from relatorio.loja_mes where mes = %(m)s) l",
        {"m": mes},
    ).fetchone()
    if errado or s["t"] + s["a"] != s["l"]:
        raise ErroHermes(f"as contas do fechamento de {mes} não batem; nada foi gravado")


def resumo_mes(conn: psycopg.Connection, mes: str) -> dict | None:
    """A linha de `relatorio.mes`, mais quantas divergências o mês teve."""
    r = conn.execute("select * from relatorio.mes where mes = %s", (mes,)).fetchone()
    if r is None:
        return None
    n = conn.execute("select count(*) n from hermes.divergencia where mes = %s", (mes,)).fetchone()[
        "n"
    ]
    return {**r, "divergencias": n}


def mes_fechado(conn: psycopg.Connection, mes: str) -> bool:
    """Todas as lojas do mês estão fechadas (ou sem relatório)."""
    r = conn.execute(
        "select count(*) total, "
        "count(*) filter (where situacao in ('fechado', 'sem_relatorio')) prontos "
        "from hermes.mes_loja where mes = %s",
        (mes,),
    ).fetchone()
    return r["total"] > 0 and r["total"] == r["prontos"]
