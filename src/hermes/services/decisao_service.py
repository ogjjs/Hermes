"""Decisão das divergências: aceitar (vale o que a loja disse) ou contestar (vale o calculado)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

import psycopg

from hermes.core.erros import ErroHermes

_ESTADO = {"aceitar": "aceita", "contestar": "contestada"}

# Regra do `hermes rodar`: o que é pequeno ou só de forma é aceito; o resto, contestado.
LIMITE_SALDO = 1  # unidades
LIMITE_REPASSE = Decimal("10.00")  # R$


def decidir(
    conn: psycopg.Connection,
    divergencia_id: int,
    acao: Literal["aceitar", "contestar"],
    motivo: str,
) -> None:
    if acao not in _ESTADO:
        raise ErroHermes(f"Ação inválida: {acao!r}. Use aceitar ou contestar.")
    if not (motivo or "").strip():
        raise ErroHermes("Diga o motivo da decisão.")
    r = conn.execute(
        "select estado from hermes.divergencia where divergencia_id = %s", (divergencia_id,)
    ).fetchone()
    if r is None:
        raise ErroHermes(f"A divergência {divergencia_id} não existe.")
    if r["estado"] != "aberta":
        raise ErroHermes(f"A divergência {divergencia_id} já foi decidida ({r['estado']}).")
    conn.execute(
        "update hermes.divergencia set estado = %s, motivo = %s, decidida_em = now() "
        "where divergencia_id = %s",
        (_ESTADO[acao], motivo.strip(), divergencia_id),
    )
    conn.commit()


def _regra(d: dict) -> tuple[str, str]:
    codigo = d["codigo"]
    if codigo == "RELATORIO_ATRASADO":
        return "aceitar", "atraso não muda os números"
    if codigo == "LINHA_ILEGIVEL":
        return "contestar", "linha ilegível: conferir com a loja e pedir o reenvio"
    if codigo == "TITULO_AUSENTE":
        return "aceitar", "título sem movimento no mês"
    if codigo == "SALDO_NAO_FECHA":
        diferenca = abs(d["valor_loja"] - d["valor_calculado"])
        if diferenca <= LIMITE_SALDO:
            return "aceitar", f"diferença de {diferenca} unidade(s), até {LIMITE_SALDO}"
        return "contestar", f"diferença de {diferenca} unidades, acima de {LIMITE_SALDO}"
    if codigo == "REPASSE_DIVERGENTE" and d["valor_loja"] is not None:
        diferenca = abs(d["valor_loja"] - d["valor_calculado"])
        if diferenca <= LIMITE_REPASSE:
            return "aceitar", f"diferença de R$ {diferenca}, até R$ {LIMITE_REPASSE}"
        return "contestar", f"diferença de R$ {diferenca}, acima de R$ {LIMITE_REPASSE}"
    return "contestar", "vale o contrato"


def decidir_automatico(conn: psycopg.Connection, mes: str) -> dict[str, int]:
    """Decide todas as divergências abertas do mês pela regra acima. Devolve quantas ficaram
    em cada estado nesta rodada."""
    contagem: dict[str, int] = {}
    # o repasse por último: ele depende do que se decidiu sobre preço e títulos da loja
    abertas = conn.execute(
        "select * from hermes.divergencia where mes = %s and estado = 'aberta' "
        "order by codigo = 'REPASSE_DIVERGENTE', divergencia_id",
        (mes,),
    ).fetchall()
    for d in abertas:
        acao, regra = _regra(d)
        if (
            d["codigo"] == "REPASSE_DIVERGENTE"
            and acao == "aceitar"
            and conn.execute(
                "select 1 from hermes.divergencia where loja_id = %s and mes = %s "
                "and estado = 'contestada' "
                "and codigo in ('PRECO_DIVERGENTE', 'TITULO_NAO_ENVIADO')",
                (d["loja_id"], mes),
            ).fetchone()
        ):
            acao, regra = "contestar", "o repasse segue um preço ou título contestado"
        conn.execute(
            "update hermes.divergencia set estado = %s, motivo = %s, decidida_em = now() "
            "where divergencia_id = %s",
            (_ESTADO[acao], f"automático: {regra}", d["divergencia_id"]),
        )
        contagem[_ESTADO[acao]] = contagem.get(_ESTADO[acao], 0) + 1
    conn.commit()
    return contagem


def listar_abertas(conn: psycopg.Connection, mes: str) -> list[dict]:
    return conn.execute(
        """select d.divergencia_id, d.loja_id, d.codigo, f.title as titulo,
                  d.valor_loja, d.valor_calculado
             from hermes.divergencia d left join public.film f using (film_id)
            where d.mes = %s and d.estado = 'aberta'
            order by d.loja_id, d.codigo, d.divergencia_id""",
        (mes,),
    ).fetchall()
