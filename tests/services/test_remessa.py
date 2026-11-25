import json
from decimal import Decimal

import pymupdf
import pytest

from hermes.core.erros import ErroHermes
from hermes.services.cadastro_service import preparar
from hermes.services.remessa_service import emitir_mes, estoque_inicial


def test_primeira_remessa_repoe_ate_o_alvo(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    soma = conn.execute("select sum(quantidade) q from hermes.nota_item").fetchone()["q"]
    alvo = conn.execute("select sum(estoque_alvo) q from hermes.sortimento").fetchone()["q"]
    assert soma == alvo
    n = conn.execute("select emitida_em from hermes.nota where loja_id = 5").fetchone()
    assert str(n["emitida_em"]) == "2025-08-01"


def test_valor_total_e_a_soma_dos_itens_pelo_preco_do_contrato(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    r = conn.execute(
        """select n.valor_total, sum(i.quantidade * i.preco_unit) soma,
                  bool_and(i.preco_unit in (19.90, 29.90, 39.90)) precos_ok
             from hermes.nota n join hermes.nota_item i using (nota_id)
            where n.loja_id = 5 group by n.valor_total"""
    ).fetchone()
    assert r["valor_total"] == r["soma"] and r["precos_ok"]


def test_emitir_duas_vezes_nao_duplica(conn, cfg):
    preparar(conn, cfg)
    assert len(emitir_mes(conn, cfg, "2025-08")) == 24
    assert emitir_mes(conn, cfg, "2025-08") == []
    assert conn.execute("select count(*) n from hermes.nota").fetchone()["n"] == 24
    assert conn.execute("select count(*) n from hermes.mes_loja").fetchone()["n"] == 24


def test_emitir_sem_o_mes_anterior_fechado_recusa(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    with pytest.raises(ErroHermes, match="2025-08 ainda não foi fechado"):
        emitir_mes(conn, cfg, "2025-09")
    assert (
        conn.execute("select count(*) n from hermes.nota where mes = '2025-09'").fetchone()["n"]
        == 0
    )


def test_emitir_pulando_meses_recusa(conn, cfg):
    preparar(conn, cfg)
    with pytest.raises(ErroHermes, match="2025-09 ainda não foi fechado"):
        emitir_mes(conn, cfg, "2025-10")


def test_estoque_inicial_do_primeiro_mes_e_vazio(conn, cfg):
    preparar(conn, cfg)
    assert estoque_inicial(conn, 5, "2025-08") == {}


def test_espelho_pdf_diz_ficticia(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    pdf = next((cfg.pasta_saida / "notas" / "2025-08").glob("nota-*.pdf"))
    assert "FICTÍCIA" in pymupdf.open(pdf)[0].get_text()


def test_espelho_pdf_carrega_os_valores_nos_atributos(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    pdf = next((cfg.pasta_saida / "notas" / "2025-08").glob("nota-*.pdf"))
    dados = json.loads(pymupdf.open(pdf).metadata["keywords"])
    nota = conn.execute(
        "select numero, loja_id, valor_total from hermes.nota where numero = %s",
        (dados["numero"],),
    ).fetchone()
    assert (dados["loja_id"], Decimal(dados["valor_total"])) == (
        nota["loja_id"],
        nota["valor_total"],
    )
    total_itens = conn.execute(
        "select sum(quantidade) q from hermes.nota_item join hermes.nota using (nota_id) "
        "where numero = %s",
        (dados["numero"],),
    ).fetchone()["q"]
    assert sum(i["quantidade"] for i in dados["itens"]) == total_itens
