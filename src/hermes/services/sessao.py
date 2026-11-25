"""Conexão de uma operação, para quem está acima dos services (application) não tocar a infra."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from hermes.config.settings import Config
from hermes.infra.db import conectar


@contextmanager
def sessao(cfg: Config) -> Iterator[psycopg.Connection]:
    conn = conectar(cfg)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
