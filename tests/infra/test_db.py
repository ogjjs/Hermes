from decimal import Decimal

from hermes.config.settings import carregar_config


def test_conecta_e_le_o_pagila(conn):
    assert conn.execute("select count(*) as n from public.film").fetchone()["n"] == 1000


def test_config_le_o_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PGPASSWORD=x\nHERMES_SEMENTE=7\n", encoding="utf-8")
    cfg = carregar_config(env)
    assert cfg.senha == "x" and cfg.semente == 7 and cfg.banco == "pagila"
    assert cfg.taxa_erro == Decimal("0.20")


def test_config_sobrepor_vence_o_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PGDATABASE=outro\n", encoding="utf-8")
    assert carregar_config(env, banco="hermes_teste").banco == "hermes_teste"
