"""Reenvio e relatório atrasado: o mês reabre, é conferido de novo e só então fecha."""

from dataclasses import replace
from decimal import Decimal

import pytest

from hermes.core.erros import ErroHermes
from hermes.services.cadastro_service import preparar
from hermes.services.conciliacao_service import conferir_mes
from hermes.services.decisao_service import decidir
from hermes.services.fechamento_service import fechar_mes
from hermes.services.importacao_service import importar_mes
from hermes.services.remessa_service import emitir_mes
from hermes.services.simulador_service import simular_mes


@pytest.fixture
def cfg0(conn, cfg):
    cfg = replace(cfg, taxa_erro=Decimal("0"))
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    simular_mes(conn, cfg, "2025-08")
    return cfg


def _csv(cfg):
    pasta = cfg.pasta_entrada / "2025-08"
    return next(p for p in sorted(pasta.glob("*.csv")) if not p.name.startswith("_"))


def _loja(arq):
    return int(arq.read_text(encoding="utf-8").split("Loja ", 1)[1].split(" ", 1)[0])


def _reenviar_com_estoque_a_mais(arq, mais=5):
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    partes = linhas[2].split(sep)
    partes[3] = str(int(partes[3]) + mais)
    linhas[2] = sep.join(partes)
    novo = arq.with_name("reenvio " + arq.name)
    novo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return novo


def _situacao(conn, loja, mes="2025-08"):
    return conn.execute(
        "select situacao from hermes.mes_loja where loja_id = %s and mes = %s", (loja, mes)
    ).fetchone()["situacao"]


def _fechar_tudo(conn, cfg, acao="contestar"):
    for d in conn.execute("select * from hermes.divergencia where estado = 'aberta'").fetchall():
        decidir(conn, d["divergencia_id"], acao, "teste")
    fechar_mes(conn, cfg, "2025-08")


def test_importar_e_conferir_avancam_o_estado(conn, cfg0):
    loja = _loja(_csv(cfg0))
    assert _situacao(conn, loja) == "aberto"
    importar_mes(conn, cfg0, "2025-08")
    assert _situacao(conn, loja) == "importado"
    conferir_mes(conn, cfg0, "2025-08")
    assert _situacao(conn, loja) == "conferido"


def test_fechar_sem_conferir_o_reenvio_recusa(conn, cfg0):
    importar_mes(conn, cfg0, "2025-08")
    conferir_mes(conn, cfg0, "2025-08")
    novo = _reenviar_com_estoque_a_mais(_csv(cfg0))
    importar_mes(conn, cfg0, "2025-08")
    loja = _loja(novo)
    assert _situacao(conn, loja) == "importado"
    with pytest.raises(ErroHermes, match="hermes conferir 2025-08"):
        fechar_mes(conn, cfg0, "2025-08")
    conferir_mes(conn, cfg0, "2025-08")
    codigos = {
        r["codigo"]
        for r in conn.execute("select codigo from hermes.divergencia where loja_id = %s", (loja,))
    }
    assert "SALDO_NAO_FECHA" in codigos


def test_relatorio_atrasado_reabre_o_mes_sem_relatorio(conn, cfg0, tmp_path):
    arq = _csv(cfg0)
    loja = _loja(arq)
    guardado = tmp_path / arq.name
    arq.rename(guardado)
    importar_mes(conn, cfg0, "2025-08")
    conferir_mes(conn, cfg0, "2025-08")
    _fechar_tudo(conn, cfg0)
    assert _situacao(conn, loja) == "sem_relatorio"

    guardado.rename(arq)
    importar_mes(conn, cfg0, "2025-08")
    assert _situacao(conn, loja) == "importado"
    faltando = conn.execute(
        "select count(*) n from hermes.divergencia where loja_id = %s "
        "and codigo = 'RELATORIO_FALTANDO'",
        (loja,),
    ).fetchone()["n"]
    assert faltando == 0
    conferir_mes(conn, cfg0, "2025-08")
    _fechar_tudo(conn, cfg0)
    f = conn.execute("select * from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["situacao"] == "fechado" and f["vendido"] > 0


def test_reenvio_com_o_mes_seguinte_ja_emitido_recusa_o_arquivo(conn, cfg0):
    importar_mes(conn, cfg0, "2025-08")
    conferir_mes(conn, cfg0, "2025-08")
    fechar_mes(conn, cfg0, "2025-08")
    emitir_mes(conn, cfg0, "2025-09")
    novo = _reenviar_com_estoque_a_mais(_csv(cfg0))
    r = importar_mes(conn, cfg0, "2025-08")
    assert [nome for nome, _ in r.com_erro] == [novo.name]
    assert "2025-09" in r.com_erro[0][1]
    assert _situacao(conn, _loja(novo)) == "fechado"


def test_simular_e_importar_de_novo_nao_reabre_nada(conn, cfg0):
    importar_mes(conn, cfg0, "2025-08")
    conferir_mes(conn, cfg0, "2025-08")
    simular_mes(conn, cfg0, "2025-08")
    r = importar_mes(conn, cfg0, "2025-08")
    assert (r.lidos, r.substituidos, r.ignorados_repetidos) == (0, 0, 24)
    situacoes = conn.execute("select distinct situacao from hermes.mes_loja").fetchall()
    assert situacoes == [{"situacao": "conferido"}]
