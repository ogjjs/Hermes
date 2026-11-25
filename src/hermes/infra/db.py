"""Conexão com o PostgreSQL e execução dos arquivos .sql do Hermes. Só I/O."""

from __future__ import annotations

from importlib.resources import files

import psycopg
from psycopg.rows import dict_row

from hermes.config.settings import Config


def conectar(cfg: Config, banco: str | None = None) -> psycopg.Connection:
    return psycopg.connect(
        host=cfg.host,
        port=cfg.porta,
        user=cfg.usuario,
        password=cfg.senha,
        dbname=banco or cfg.banco,
        row_factory=dict_row,
    )


def ler_sql(nome: str) -> str:
    return files("hermes.infra.sql").joinpath(nome).read_text(encoding="utf-8")


def executar_sql(conn: psycopg.Connection, nome: str, params: dict | None = None) -> None:
    """Executa um arquivo de `infra/sql/` inteiro. Parâmetros nomeados (`%(mes)s`) são
    interpolados no cliente, o que permite várias instruções no mesmo arquivo."""
    with psycopg.ClientCursor(conn) as cur:
        cur.execute(ler_sql(nome), params)
