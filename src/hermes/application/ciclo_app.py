"""O ciclo do mês, na ordem certa. A CLI de hoje e uma tela futura chamam só daqui."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from hermes.config.settings import Config, carregar_config
from hermes.core.meses import meses, validar_mes
from hermes.core.modelos import ErroInjetado, ResumoImportacao
from hermes.services import (
    cadastro_service,
    conciliacao_service,
    decisao_service,
    fechamento_service,
    importacao_service,
    remessa_service,
    simulador_service,
)
from hermes.services.sessao import sessao


def preparar(cfg: Config) -> int:
    with sessao(cfg) as conn:
        return cadastro_service.preparar(conn, cfg)


def emitir(cfg: Config, mes: str) -> int:
    with sessao(cfg) as conn:
        return len(remessa_service.emitir_mes(conn, cfg, mes))


def simular(cfg: Config, mes: str) -> list[ErroInjetado]:
    validar_mes(mes)
    with sessao(cfg) as conn:
        return simulador_service.simular_mes(conn, cfg, mes)


def importar(cfg: Config, mes: str) -> ResumoImportacao:
    with sessao(cfg) as conn:
        return importacao_service.importar_mes(conn, cfg, mes)


def conferir(cfg: Config, mes: str) -> dict[str, int]:
    with sessao(cfg) as conn:
        return conciliacao_service.conferir_mes(conn, cfg, mes)


def divergencias(cfg: Config, mes: str) -> list[dict]:
    validar_mes(mes)
    with sessao(cfg) as conn:
        return decisao_service.listar_abertas(conn, mes)


def decidir(cfg: Config, divergencia_id: int, acao: str, motivo: str) -> None:
    with sessao(cfg) as conn:
        decisao_service.decidir(conn, divergencia_id, acao, motivo)


def fechar(cfg: Config, mes: str) -> dict | None:
    with sessao(cfg) as conn:
        fechamento_service.fechar_mes(conn, cfg, mes)
        return fechamento_service.resumo_mes(conn, mes)


def rodar(
    cfg: Config, inicio: str, fim: str, ao_fechar: Callable[[str, dict], None] | None = None
) -> list[dict]:
    """O ciclo inteiro, mês a mês, decidindo as divergências pela regra automática. Serve
    para ver tudo pronto com um comando."""
    validar_mes(inicio)
    resumos = []
    with sessao(cfg) as conn:
        cadastro_service.preparar(conn, cfg)
        for mes in meses(inicio, fim):
            remessa_service.emitir_mes(conn, cfg, mes)
            simulador_service.simular_mes(conn, cfg, mes)
            importacao_service.importar_mes(conn, cfg, mes)
            conciliacao_service.conferir_mes(conn, cfg, mes)
            decisao_service.decidir_automatico(conn, mes)
            fechamento_service.fechar_mes(conn, cfg, mes)
            resumo = fechamento_service.resumo_mes(conn, mes)
            resumos.append(resumo)
            if ao_fechar:
                ao_fechar(mes, resumo)
    return resumos


def carregar(env_file: Path) -> Config:
    return carregar_config(env_file)
