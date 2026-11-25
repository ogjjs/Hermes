"""O contrato vale pela vigência: um segundo contrato para a mesma loja não quebra nada."""

from dataclasses import replace
from decimal import Decimal

import psycopg
import pytest

from hermes.application import ciclo_app
from hermes.services.cadastro_service import preparar

LOJA = 5


def _novo_contrato(conn, inicio: str, comissao: str) -> None:
    conn.execute(
        "update hermes.contrato set vigencia_fim = %s::date - 1 where loja_id = %s "
        "and vigencia_fim is null",
        (inicio, LOJA),
    )
    novo = conn.execute(
        "insert into hermes.contrato (loja_id, vigencia_inicio, comissao, custo_pct) "
        "values (%s, %s, %s, 0.40) returning contrato_id",
        (LOJA, inicio, comissao),
    ).fetchone()["contrato_id"]
    conn.execute(
        "insert into hermes.preco select %s, rental_rate, preco from hermes.preco "
        "where contrato_id = (select min(contrato_id) from hermes.contrato where loja_id = %s)",
        (novo, LOJA),
    )
    conn.commit()


def _comissao(conn, mes):
    return conn.execute(
        "select comissao from hermes.contrato_do_mes(%s) where loja_id = %s", (mes, LOJA)
    ).fetchone()["comissao"]


def test_contrato_do_mes_escolhe_o_vigente(conn, cfg):
    preparar(conn, cfg)
    _novo_contrato(conn, "2026-01-01", "0.25")
    assert _comissao(conn, "2025-12") == Decimal("0.30")
    assert _comissao(conn, "2026-01") == Decimal("0.25")
    n = conn.execute(
        "select count(*) n from hermes.contrato_do_mes('2026-01') where loja_id = %s", (LOJA,)
    ).fetchone()["n"]
    assert n == 1


def test_vigencias_sobrepostas_sao_recusadas(conn, cfg):
    preparar(conn, cfg)
    with pytest.raises(psycopg.errors.ExclusionViolation):
        conn.execute(
            "insert into hermes.contrato (loja_id, vigencia_inicio, comissao, custo_pct) "
            "values (%s, '2026-01-01', 0.25, 0.40)",
            (LOJA,),
        )


def test_troca_de_contrato_no_meio_do_ciclo_vale_no_mes_certo(conn, cfg):
    cfg = replace(cfg, taxa_erro=Decimal("0"))
    preparar(conn, cfg)
    _novo_contrato(conn, "2025-09-01", "0.25")
    ciclo_app.rodar(cfg, "2025-08", "2025-09")
    assert conn.execute("select count(*) n from hermes.divergencia").fetchone()["n"] == 0
    r = {
        x["mes"]: x
        for x in conn.execute(
            "select mes, venda, comissao from relatorio.loja_mes where loja_id = %s", (LOJA,)
        )
    }
    assert abs(r["2025-08"]["comissao"] - r["2025-08"]["venda"] * Decimal("0.30")) < 1
    assert abs(r["2025-09"]["comissao"] - r["2025-09"]["venda"] * Decimal("0.25")) < 1
