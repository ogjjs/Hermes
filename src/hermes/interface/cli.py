"""Linha de comando do Hermes. Só lê os argumentos, chama a application e mostra o resultado."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hermes.application import ciclo_app
from hermes.core.dinheiro import texto_br
from hermes.core.erros import ErroHermes


def _brl(v) -> str:
    return f"R$ {texto_br(v)}"


def _linha_do_mes(mes: str, r: dict) -> str:
    aviso = "  (já fechado, não mexi)" if r.get("ja_fechado") else ""
    return (
        f"{mes}{aviso}  vendido {r['vendido']:>5}  venda {_brl(r['venda']):>15}  "
        f"lucro {_brl(r['lucro']):>14}  divergências {r['divergencias']:>3}"
    )


def _argumentos() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hermes", description="Distribuidora fictícia em consignação: o ciclo do mês."
    )
    p.add_argument("--env", default=".env", help="arquivo .env (padrão: .env)")
    sub = p.add_subparsers(dest="comando", required=True)
    sub.add_parser("preparar", help="cria as tabelas e cadastra lojas, contratos e sortimento")
    for nome, ajuda in (
        ("emitir", "emite as remessas (notas fictícias) do mês"),
        ("simular", "gera os relatórios das lojas do mês, com erros de propósito"),
        ("importar", "lê os relatórios do mês: bruto e padronizado"),
        ("conferir", "concilia o mês e registra as divergências"),
        ("divergencias", "lista as divergências abertas do mês"),
        ("fechar", "fecha o mês e grava a camada relatorio"),
    ):
        sub.add_parser(nome, help=ajuda).add_argument("mes", help="AAAA-MM")
    d = sub.add_parser("decidir", help="aceita ou contesta uma divergência")
    d.add_argument("id", type=int)
    d.add_argument("acao", choices=["aceitar", "contestar"])
    d.add_argument("motivo")
    r = sub.add_parser("rodar", help="ciclo completo de vários meses, com decisão automática")
    r.add_argument("inicio", help="AAAA-MM")
    r.add_argument("fim", help="AAAA-MM")
    return p


def _executar(a: argparse.Namespace) -> None:
    cfg = ciclo_app.carregar(Path(a.env))
    if a.comando == "preparar":
        print(f"{ciclo_app.preparar(cfg)} lojas cadastradas.")
    elif a.comando == "emitir":
        print(f"{ciclo_app.emitir(cfg, a.mes)} notas emitidas em {a.mes}.")
    elif a.comando == "simular":
        erros = ciclo_app.simular(cfg, a.mes)
        print(f"Relatórios de {a.mes} gerados, {len(erros)} com erro de propósito.")
    elif a.comando == "importar":
        r = ciclo_app.importar(cfg, a.mes)
        print(
            f"{r.lidos} lidos, {r.ignorados_repetidos} repetidos, {r.substituidos} substituídos, "
            f"{len(r.com_erro)} com erro."
        )
        for nome, motivo in r.com_erro:
            print(f"  {nome}: {motivo}")
        if r.com_erro_de_linha:
            print(f"{len(r.com_erro_de_linha)} lidos com linhas que não deu para ler:")
            for nome, motivo in r.com_erro_de_linha:
                print(f"  {nome}: {motivo}")
    elif a.comando == "conferir":
        contagem = ciclo_app.conferir(cfg, a.mes)
        print(f"{sum(contagem.values())} divergências em {a.mes}.")
        for codigo, n in sorted(contagem.items()):
            print(f"  {codigo}: {n}")
    elif a.comando == "divergencias":
        abertas = ciclo_app.divergencias(cfg, a.mes)
        print(f"{len(abertas)} divergências abertas em {a.mes}.")
        for d in abertas:
            titulo = f" · {d['titulo']}" if d["titulo"] else ""
            print(
                f"  #{d['divergencia_id']}  loja {d['loja_id']}  {d['codigo']}{titulo}  "
                f"loja: {d['valor_loja']}  calculado: {d['valor_calculado']}"
            )
    elif a.comando == "decidir":
        ciclo_app.decidir(cfg, a.id, a.acao, a.motivo)
        print(f"Divergência {a.id}: {a.acao} registrado.")
    elif a.comando == "fechar":
        print(_linha_do_mes(a.mes, ciclo_app.fechar(cfg, a.mes)))
    elif a.comando == "rodar":
        ciclo_app.rodar(cfg, a.inicio, a.fim, lambda mes, r: print(_linha_do_mes(mes, r)))


def main(argv: list[str] | None = None) -> int:
    a = _argumentos().parse_args(argv)
    try:
        _executar(a)
    except ErroHermes as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    return 0
