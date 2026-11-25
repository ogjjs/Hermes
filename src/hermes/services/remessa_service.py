"""Emissão das remessas (notas fiscais fictícias) do mês, repondo cada título até o alvo."""

from __future__ import annotations

import psycopg

from hermes.config import contrato_padrao as cp
from hermes.config.settings import Config
from hermes.core.erros import ErroHermes
from hermes.core.meses import dia, mes_anterior, validar_mes
from hermes.domain import nota_fiscal
from hermes.infra.pdf import gerar_pdf_tabela


def primeiro_mes(conn: psycopg.Connection) -> str:
    r = conn.execute("select min(vigencia_inicio) d from hermes.contrato").fetchone()
    if r["d"] is None:
        raise ErroHermes("Nenhuma loja cadastrada: rode hermes preparar primeiro.")
    return f"{r['d']:%Y-%m}"


def estoque_inicial(conn: psycopg.Connection, loja_id: int, mes: str) -> dict[int, int]:
    """O estoque final conferido do mês anterior, por título ({} no primeiro mês)."""
    linhas = conn.execute(
        "select film_id, estoque_final from conferido.saldo "
        "where loja_id = %s and mes = %s and estoque_final > 0",
        (loja_id, mes_anterior(mes)),
    ).fetchall()
    return {r["film_id"]: r["estoque_final"] for r in linhas}


def _exigir_mes_anterior_fechado(conn: psycopg.Connection, mes: str) -> None:
    anterior = mes_anterior(mes)
    r = conn.execute(
        "select count(*) total, "
        "count(*) filter (where situacao in ('fechado', 'sem_relatorio')) prontos "
        "from hermes.mes_loja where mes = %s",
        (anterior,),
    ).fetchone()
    if r["total"] == 0 or r["prontos"] < r["total"]:
        raise ErroHermes(f"{anterior} ainda não foi fechado: rode hermes fechar {anterior}")


def emitir_mes(conn: psycopg.Connection, cfg: Config, mes: str) -> list[int]:
    """Emite a nota de cada loja que ainda não tem nota no mês. Devolve os ids criados."""
    validar_mes(mes)
    inicio = primeiro_mes(conn)
    if mes < inicio:
        raise ErroHermes(f"O contrato começa em {inicio}: não há remessa em {mes}.")
    if mes != inicio:
        _exigir_mes_anterior_fechado(conn, mes)
    emitida_em = dia(mes, 1 if mes == inicio else cp.DIA_REMESSA)
    lojas = conn.execute(
        "select l.loja_id, l.cidade from hermes.loja l where not exists "
        "(select 1 from hermes.nota n where n.loja_id = l.loja_id and n.mes = %s) order by 1",
        (mes,),
    ).fetchall()
    criadas, pdfs = [], []
    for loja in lojas:
        estoque = estoque_inicial(conn, loja["loja_id"], mes)
        itens = []
        for s in conn.execute(
            """select s.film_id, f.title as titulo, s.estoque_alvo, p.preco
                 from hermes.sortimento s
                 join public.film f using (film_id)
                 join hermes.contrato_do_mes(%s) c on c.loja_id = s.loja_id
                 join hermes.preco p on p.contrato_id = c.contrato_id
                                    and p.rental_rate = f.rental_rate
                where s.loja_id = %s order by s.film_id""",
            (mes, loja["loja_id"]),
        ):
            quantidade = s["estoque_alvo"] - estoque.get(s["film_id"], 0)
            if quantidade > 0:
                itens.append({**s, "quantidade": quantidade, "preco_unit": s["preco"]})
        conn.execute(
            "insert into hermes.mes_loja values (%s, %s, 'aberto') on conflict do nothing",
            (loja["loja_id"], mes),
        )
        if not itens:
            continue
        numero = conn.execute("select coalesce(max(numero), 0) + 1 n from hermes.nota").fetchone()[
            "n"
        ]
        total = sum(i["quantidade"] * i["preco_unit"] for i in itens)
        nota = conn.execute(
            "insert into hermes.nota (numero, loja_id, mes, emitida_em, valor_total) "
            "values (%s, %s, %s, %s, %s) returning *",
            (numero, loja["loja_id"], mes, emitida_em, total),
        ).fetchone()
        with conn.cursor() as cur:
            cur.executemany(
                "insert into hermes.nota_item values (%s, %s, %s, %s)",
                [(nota["nota_id"], i["film_id"], i["quantidade"], i["preco_unit"]) for i in itens],
            )
        criadas.append(nota["nota_id"])
        pdfs.append((nota, itens, loja["cidade"]))
    conn.commit()
    pasta = cfg.pasta_saida / "notas" / mes
    for nota, itens, cidade in pdfs:
        gerar_pdf_tabela(
            *nota_fiscal.tabela(nota, itens, cidade),
            nota_fiscal.atributos(nota, itens),
            pasta / f"nota-{nota['numero']}.pdf",
        )
    return criadas
