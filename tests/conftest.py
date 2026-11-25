"""Banco de teste `hermes_teste` com o Pagila, recriado só quando não existe.

Os schemas do Hermes são zerados a cada teste; o Pagila (`public`) nunca é tocado.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import psycopg
import pytest

from hermes.config.settings import Config, carregar_config
from hermes.infra.db import conectar, executar_sql

BANCO_TESTE = "hermes_teste"
SCHEMAS = ("hermes", "bruto", "padronizado", "conferido", "relatorio")
RAIZ = Path(__file__).resolve().parents[1]


def _carregar_pagila(cfg: Config) -> None:
    """Sem ON_ERROR_STOP: o dump novo do Pagila pede a extensão `vector` (tabela
    `film_embedding`, que o Hermes não usa) e ela pode não estar instalada. O que importa
    é conferido depois, em `_pagila_ok`."""
    pasta = Path(cfg.pagila_sql_dir)
    ambiente = dict(os.environ, PGPASSWORD=cfg.senha)
    for nome in ("pagila-schema.sql", "pagila-data.sql"):
        subprocess.run(
            [
                cfg.psql,
                "-q",
                "-h",
                cfg.host,
                "-p",
                str(cfg.porta),
                "-U",
                cfg.usuario,
                "-d",
                BANCO_TESTE,
                "-f",
                str(pasta / nome),
            ],
            env=ambiente,
            check=True,
            capture_output=True,
        )


def _pagila_ok(cfg: Config) -> bool:
    try:
        with conectar(cfg) as c:
            n = c.execute(
                "select (select count(*) from public.film) f, (select count(*) from public.store) s"
            ).fetchone()
        return n["f"] == 1000 and n["s"] > 0
    except psycopg.Error:
        return False


@pytest.fixture(scope="session")
def cfg_base() -> Config:
    cfg = carregar_config(RAIZ / ".env", banco=BANCO_TESTE)
    with psycopg.connect(
        host=cfg.host,
        port=cfg.porta,
        user=cfg.usuario,
        password=cfg.senha,
        dbname="postgres",
        autocommit=True,
    ) as adm:
        existe = adm.execute(
            "select 1 from pg_database where datname = %s", (BANCO_TESTE,)
        ).fetchone()
        if existe and _pagila_ok(cfg):
            return cfg
        adm.execute(f'drop database if exists "{BANCO_TESTE}"')
        adm.execute(f'create database "{BANCO_TESTE}"')
        _carregar_pagila(cfg)
    if not _pagila_ok(cfg):
        pytest.exit("O Pagila não carregou em hermes_teste: confira PAGILA_SQL_DIR no .env", 2)
    return cfg


@pytest.fixture
def cfg(cfg_base: Config, tmp_path: Path) -> Config:
    return replace(cfg_base, pasta_entrada=tmp_path / "entrada", pasta_saida=tmp_path / "saida")


@pytest.fixture
def conn(cfg: Config):
    c = conectar(cfg)
    c.execute(f"drop schema if exists {', '.join(SCHEMAS)} cascade")
    if files("hermes.infra.sql").joinpath("001_schemas.sql").is_file():
        executar_sql(c, "001_schemas.sql")
    c.commit()
    yield c
    c.rollback()
    c.close()
