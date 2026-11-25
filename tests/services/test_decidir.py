import pytest

from hermes.core.erros import ErroHermes
from hermes.services.cadastro_service import preparar
from hermes.services.decisao_service import decidir, decidir_automatico


def _divergencia(conn, codigo, valor_loja=None, valor_calculado=None, film_id=None, loja_id=5):
    return conn.execute(
        "insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_loja, "
        "valor_calculado) values (%s, '2025-08', %s, %s, %s, %s) returning divergencia_id",
        (loja_id, film_id, codigo, valor_loja, valor_calculado),
    ).fetchone()["divergencia_id"]


def test_decidir_grava_estado_motivo_e_data(conn, cfg):
    preparar(conn, cfg)
    d = _divergencia(conn, "SALDO_NAO_FECHA", 3, 1, film_id=1)
    decidir(conn, d, "contestar", "loja contou errado")
    r = conn.execute("select * from hermes.divergencia where divergencia_id = %s", (d,)).fetchone()
    assert r["estado"] == "contestada" and r["motivo"] == "loja contou errado"
    assert r["decidida_em"] is not None


def test_decidir_duas_vezes_recusa(conn, cfg):
    preparar(conn, cfg)
    d = _divergencia(conn, "RELATORIO_ATRASADO")
    decidir(conn, d, "aceitar", "ok")
    with pytest.raises(ErroHermes, match="já foi decidida"):
        decidir(conn, d, "contestar", "mudei de ideia")


def test_decidir_divergencia_que_nao_existe_recusa(conn, cfg):
    with pytest.raises(ErroHermes, match="não existe"):
        decidir(conn, 999999, "aceitar", "x")


@pytest.mark.parametrize("motivo", ["", "   "])
def test_decidir_motivo_vazio_recusa(conn, cfg, motivo):
    preparar(conn, cfg)
    d = _divergencia(conn, "RELATORIO_ATRASADO")
    with pytest.raises(ErroHermes, match="motivo"):
        decidir(conn, d, "aceitar", motivo)


def test_decidir_acao_invalida_recusa(conn, cfg):
    preparar(conn, cfg)
    d = _divergencia(conn, "RELATORIO_ATRASADO")
    with pytest.raises(ErroHermes, match="aceitar ou contestar"):
        decidir(conn, d, "talvez", "x")


def test_automatico_segue_a_regra(conn, cfg):
    preparar(conn, cfg)
    casos = {
        _divergencia(conn, "RELATORIO_ATRASADO"): "aceita",
        _divergencia(conn, "TITULO_AUSENTE", None, 3, film_id=1): "aceita",
        _divergencia(conn, "SALDO_NAO_FECHA", 3, 2, film_id=2): "aceita",
        _divergencia(conn, "SALDO_NAO_FECHA", 5, 2, film_id=3): "contestada",
        _divergencia(conn, "REPASSE_DIVERGENTE", 110, 100): "aceita",
        _divergencia(conn, "REPASSE_DIVERGENTE", 120, 100, loja_id=11): "contestada",
        _divergencia(conn, "PRECO_DIVERGENTE", 39.9, 29.9, film_id=4, loja_id=11): "contestada",
        _divergencia(conn, "TITULO_NAO_ENVIADO", 1, None, film_id=5, loja_id=11): "contestada",
        _divergencia(conn, "DUPLICADO", 2, None, film_id=6): "contestada",
        _divergencia(conn, "RELATORIO_FALTANDO"): "contestada",
        _divergencia(conn, "LINHA_ILEGIVEL", None, 2, film_id=7): "contestada",
    }
    contagem = decidir_automatico(conn, "2025-08")
    assert contagem == {"aceita": 4, "contestada": 7}
    for d, estado in casos.items():
        r = conn.execute(
            "select estado, motivo from hermes.divergencia where divergencia_id = %s", (d,)
        ).fetchone()
        assert r["estado"] == estado and r["motivo"].startswith("automático: ")
    assert decidir_automatico(conn, "2025-08") == {}


def test_automatico_contesta_o_repasse_que_segue_um_preco_contestado(conn, cfg):
    preparar(conn, cfg)
    preco = _divergencia(conn, "PRECO_DIVERGENTE", 39.9, 29.9, film_id=4)
    repasse = _divergencia(conn, "REPASSE_DIVERGENTE", 107, 100)
    decidir_automatico(conn, "2025-08")
    estados = {
        r["divergencia_id"]: r["estado"]
        for r in conn.execute("select divergencia_id, estado from hermes.divergencia")
    }
    assert estados == {preco: "contestada", repasse: "contestada"}
