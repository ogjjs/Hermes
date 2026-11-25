"""Configuração do Hermes, lida do `.env` (nunca versionado) e do ambiente."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field, fields
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values

_PSQL_WINDOWS = r"C:\Program Files\PostgreSQL\18\bin\psql.exe"


def _psql_padrao() -> str:
    return shutil.which("psql") or _PSQL_WINDOWS


@dataclass(frozen=True)
class Config:
    host: str = "localhost"
    porta: int = 5432
    usuario: str = "postgres"
    senha: str = ""
    banco: str = "pagila"
    semente: int = 2026
    taxa_erro: Decimal = Decimal("0.20")
    psql: str = field(default_factory=_psql_padrao)
    pagila_sql_dir: Path = field(default_factory=Path.home)
    pasta_entrada: Path = Path("entrada")
    pasta_saida: Path = Path("saida")


# chave do .env -> (campo da Config, conversão)
_CHAVES = {
    "PGHOST": ("host", str),
    "PGPORT": ("porta", int),
    "PGUSER": ("usuario", str),
    "PGPASSWORD": ("senha", str),
    "PGDATABASE": ("banco", str),
    "HERMES_SEMENTE": ("semente", int),
    "HERMES_TAXA_ERRO": ("taxa_erro", Decimal),
    "HERMES_PSQL": ("psql", str),
    "PAGILA_SQL_DIR": ("pagila_sql_dir", Path),
    "HERMES_ENTRADA": ("pasta_entrada", Path),
    "HERMES_SAIDA": ("pasta_saida", Path),
}


def carregar_config(env_file: Path | None = None, **sobrepor) -> Config:
    """Valores do arquivo `.env`, depois do ambiente; `sobrepor` vence os dois."""
    arquivo = Path(env_file) if env_file else Path(".env")
    do_arquivo = dotenv_values(arquivo) if arquivo.is_file() else {}
    valores = {}
    for chave, (campo, converter) in _CHAVES.items():
        bruto = do_arquivo.get(chave) or os.environ.get(chave)
        if bruto:
            valores[campo] = converter(bruto)
    validos = {f.name for f in fields(Config)}
    desconhecidos = set(sobrepor) - validos
    if desconhecidos:
        raise TypeError(f"Campos desconhecidos na Config: {sorted(desconhecidos)}")
    valores.update(sobrepor)
    return Config(**valores)
