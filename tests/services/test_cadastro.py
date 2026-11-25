from decimal import Decimal

from hermes.services.cadastro_service import preparar


def test_preparar_cadastra_as_24_lojas_do_brasil(conn, cfg):
    assert preparar(conn, cfg) == 24
    ids = [r["loja_id"] for r in conn.execute("select loja_id from hermes.loja order by 1")]
    assert len(ids) == 24
    assert ids[:3] == [5, 11, 51] and ids[-1] == 468


def test_loja_tem_formato_e_mapeamento_completo(conn, cfg):
    preparar(conn, cfg)
    for r in conn.execute("select formato, mapeamento from hermes.loja"):
        assert r["formato"] in {"csv_ponto_virgula", "csv_virgula", "xlsx", "pdf"}
        assert set(r["mapeamento"]) == {"titulo", "vendido", "devolvido", "estoque_final", "preco"}


def test_preco_por_faixa_e_contrato(conn, cfg):
    preparar(conn, cfg)
    precos = {
        r["rental_rate"]: r["preco"]
        for r in conn.execute(
            "select rental_rate, preco from hermes.preco join hermes.contrato using (contrato_id) "
            "where loja_id = 5"
        )
    }
    assert precos == {
        Decimal("0.99"): Decimal("19.90"),
        Decimal("2.99"): Decimal("29.90"),
        Decimal("4.99"): Decimal("39.90"),
    }
    c = conn.execute(
        "select comissao, custo_pct, vigencia_inicio from hermes.contrato where loja_id = 5"
    ).fetchone()
    assert (c["comissao"], c["custo_pct"], str(c["vigencia_inicio"])) == (
        Decimal("0.30"),
        Decimal("0.40"),
        "2025-08-01",
    )


def test_sortimento_entre_40_e_120_titulos_e_alvo_2_a_6(conn, cfg):
    preparar(conn, cfg)
    por_loja = conn.execute(
        "select count(*) n, min(estoque_alvo) mi, max(estoque_alvo) ma "
        "from hermes.sortimento group by loja_id"
    ).fetchall()
    assert len(por_loja) == 24
    assert all(40 <= r["n"] <= 120 and r["mi"] >= 2 and r["ma"] <= 6 for r in por_loja)


def test_preparar_duas_vezes_nao_duplica_e_da_o_mesmo_sortimento(conn, cfg):
    preparar(conn, cfg)
    antes = conn.execute("select * from hermes.sortimento order by 1, 2").fetchall()
    assert preparar(conn, cfg) == 24
    depois = conn.execute("select * from hermes.sortimento order by 1, 2").fetchall()
    assert antes == depois
    assert conn.execute("select count(*) n from hermes.contrato").fetchone()["n"] == 24


def test_pagila_nao_muda(conn, cfg):
    sql = "select count(*) n, max(last_update) u from public.store"
    antes = conn.execute(sql).fetchone()
    preparar(conn, cfg)
    assert conn.execute(sql).fetchone() == antes
