from dataclasses import replace
from decimal import Decimal

import pytest

from hermes.core.dinheiro import texto_br, texto_us, valores
from hermes.core.erros import ErroHermes
from hermes.services.cadastro_service import preparar
from hermes.services.conciliacao_service import conferir_mes
from hermes.services.decisao_service import decidir
from hermes.services.fechamento_service import fechar_mes
from hermes.services.importacao_service import importar_mes
from hermes.services.remessa_service import emitir_mes, estoque_inicial
from hermes.services.simulador_service import simular_mes, simular_vendas


@pytest.fixture
def cfg0(conn, cfg):
    cfg = replace(cfg, taxa_erro=Decimal("0"))
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    simular_mes(conn, cfg, "2025-08")
    return cfg


def _csv(cfg):
    pasta = cfg.pasta_entrada / "2025-08"
    arq = next(p for p in sorted(pasta.glob("*.csv")) if not p.name.startswith("_"))
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    return arq, linhas, sep


def _gravar(arq, linhas):
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _importar_e_conferir(conn, cfg):
    importar_mes(conn, cfg, "2025-08")
    conferir_mes(conn, cfg, "2025-08")


def _decidir_todas(conn, acao_por_codigo):
    for d in conn.execute("select * from hermes.divergencia where estado = 'aberta'").fetchall():
        decidir(conn, d["divergencia_id"], acao_por_codigo[d["codigo"]], "teste")


def _loja_do_csv(linhas):
    return int(linhas[0].split("Loja ", 1)[1].split(" ", 1)[0])


def _linha_com_preco(linhas, sep, preco_texto):
    return next(i for i in range(2, len(linhas) - 1) if linhas[i].split(sep)[4] == preco_texto)


def test_fechar_com_divergencia_aberta_recusa_e_nao_grava(conn, cfg):
    cfg = replace(cfg, taxa_erro=Decimal("1"))
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    simular_mes(conn, cfg, "2025-08")
    _importar_e_conferir(conn, cfg)
    with pytest.raises(ErroHermes, match=r"\d+ divergências abertas em 2025-08"):
        fechar_mes(conn, cfg, "2025-08")
    assert conn.execute("select count(*) n from relatorio.loja_mes").fetchone()["n"] == 0
    situacoes = conn.execute("select distinct situacao from hermes.mes_loja").fetchall()
    assert situacoes == [{"situacao": "conferido"}]  # a recusa não fecha ninguém


def test_fechar_sem_conferir_recusa(conn, cfg0):
    importar_mes(conn, cfg0, "2025-08")
    with pytest.raises(ErroHermes, match="hermes conferir 2025-08"):
        fechar_mes(conn, cfg0, "2025-08")


def test_fechamento_bate_com_a_verdade(conn, cfg0):
    _importar_e_conferir(conn, cfg0)
    fechar_mes(conn, cfg0, "2025-08")
    for r in simular_vendas(conn, cfg0, "2025-08"):
        v = [valores(x.vendido, x.preco, Decimal("0.30"), Decimal("0.40")) for x in r.linhas]
        f = conn.execute(
            "select * from relatorio.loja_mes where loja_id = %s and mes = '2025-08'",
            (r.loja_id,),
        ).fetchone()
        assert f["situacao"] == "fechado"
        assert f["venda"] == sum(x.venda for x in v)
        assert f["repasse"] == sum(x.repasse for x in v) == r.repasse
        assert f["lucro"] == sum(x.lucro for x in v)
        assert f["vendido"] == sum(x.vendido for x in r.linhas)
    geral = conn.execute("select * from relatorio.mes where mes = '2025-08'").fetchone()
    assert geral["lojas_com_relatorio"] == 24 and geral["lojas_sem_relatorio"] == 0
    assert 0 < geral["sell_through"] < 1
    assert conn.execute("select count(*) n from relatorio.titulo_mes").fetchone()["n"] > 0


def _mudar_estoque(cfg, mais):
    arq, linhas, sep = _csv(cfg)
    i = _linha_com_preco(linhas, sep, "29,90" if sep == ";" else "29.90")
    partes = linhas[i].split(sep)
    declarado = int(partes[3]) + mais
    partes[3] = str(declarado)
    linhas[i] = sep.join(partes)
    _gravar(arq, linhas)
    return _loja_do_csv(linhas), partes[0], declarado


def test_saldo_contestado_cobra_a_preco_de_custo(conn, cfg0):
    loja, _, _ = _mudar_estoque(cfg0, 2)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"SALDO_NAO_FECHA": "contestar"})
    fechar_mes(conn, cfg0, "2025-08")
    f = conn.execute("select * from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["cobranca_saldo"] == Decimal("23.92") and f["ajuste_unidades"] == 0


def test_saldo_aceito_ajusta_estoque_sem_cobrar_e_passa_para_o_mes_seguinte(conn, cfg0):
    loja, titulo, declarado = _mudar_estoque(cfg0, 2)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"SALDO_NAO_FECHA": "aceitar"})
    fechar_mes(conn, cfg0, "2025-08")
    f = conn.execute("select * from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["ajuste_unidades"] == 2 and f["cobranca_saldo"] == 0
    film_id = conn.execute(
        "select film_id from public.film where title = %s", (titulo,)
    ).fetchone()["film_id"]
    assert estoque_inicial(conn, loja, "2025-09")[film_id] == declarado
    emitir_mes(conn, cfg0, "2025-09")  # o mês fechado libera a remessa seguinte


def test_sem_relatorio_passa_o_estoque(conn, cfg0):
    arq, linhas, _ = _csv(cfg0)
    loja = _loja_do_csv(linhas)
    arq.unlink()
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"RELATORIO_FALTANDO": "contestar"})
    fechar_mes(conn, cfg0, "2025-08")
    f = conn.execute("select * from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["situacao"] == "sem_relatorio" and f["vendido"] == 0 and f["venda"] == 0
    r = conn.execute(
        "select bool_and(estoque_final = estoque_inicial + recebido) ok from conferido.saldo "
        "where loja_id = %s and mes = '2025-08'",
        (loja,),
    ).fetchone()
    assert r["ok"]
    assert (
        conn.execute("select situacao from hermes.mes_loja where loja_id = %s", (loja,)).fetchone()[
            "situacao"
        ]
        == "sem_relatorio"
    )


def test_preco_aceito_vende_pelo_preco_da_loja(conn, cfg0):
    arq, linhas, sep = _csv(cfg0)
    loja = _loja_do_csv(linhas)
    i = next(i for i in range(2, len(linhas) - 1) if int(linhas[i].split(sep)[1]) > 0)
    partes = linhas[i].split(sep)
    vendido = int(partes[1])
    antes = Decimal(partes[4].replace(",", "."))
    partes[4] = texto_br(antes + 10) if sep == ";" else texto_us(antes + 10)
    linhas[i] = sep.join(partes)
    _gravar(arq, linhas)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"PRECO_DIVERGENTE": "aceitar", "REPASSE_DIVERGENTE": "contestar"})
    fechar_mes(conn, cfg0, "2025-08")
    verdade = next(r for r in simular_vendas(conn, cfg0, "2025-08") if r.loja_id == loja)
    venda_verdade = sum(valores(x.vendido, x.preco, 0, 0).venda for x in verdade.linhas)
    f = conn.execute("select venda from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["venda"] == venda_verdade + vendido * 10


def test_titulo_nao_enviado_aceito_vira_venda_avulsa(conn, cfg0):
    arq, linhas, sep = _csv(cfg0)
    loja = _loja_do_csv(linhas)
    linhas.insert(3, sep.join(["ZORRO ARK", "1", "0", "0", "39,90" if sep == ";" else "39.90"]))
    _gravar(arq, linhas)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(
        conn,
        {"TITULO_NAO_ENVIADO": "aceitar", "REPASSE_DIVERGENTE": "aceitar"},
    )
    fechar_mes(conn, cfg0, "2025-08")
    verdade = next(r for r in simular_vendas(conn, cfg0, "2025-08") if r.loja_id == loja)
    f = conn.execute("select vendido from relatorio.loja_mes where loja_id = %s", (loja,))
    assert f.fetchone()["vendido"] == sum(x.vendido for x in verdade.linhas) + 1


def test_fechar_de_novo_refaz_igual(conn, cfg0):
    _mudar_estoque(cfg0, 2)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"SALDO_NAO_FECHA": "aceitar"})
    fechar_mes(conn, cfg0, "2025-08")
    consultas = [
        "select * from relatorio.loja_mes order by loja_id",
        "select * from relatorio.titulo_mes order by film_id",
        "select * from relatorio.mes",
        "select * from conferido.saldo order by loja_id, film_id",
    ]
    antes = [conn.execute(q).fetchall() for q in consultas]
    fechar_mes(conn, cfg0, "2025-08")
    assert [conn.execute(q).fetchall() for q in consultas] == antes


def _somas(conn):
    return conn.execute(
        """select (select sum(lucro) from relatorio.titulo_mes) titulos,
                  (select sum(ajuste_repasse) from relatorio.loja_mes) ajuste,
                  (select sum(lucro) from relatorio.loja_mes) lojas,
                  (select lucro from relatorio.mes) mes"""
    ).fetchone()


def test_repasse_aceito_vira_ajuste_e_os_lucros_batem(conn, cfg0):
    arq, linhas, sep = _csv(cfg0)
    loja = _loja_do_csv(linhas)
    rotulo, valor = linhas[-1].split(sep, 1)
    novo = Decimal(valor.replace(".", "").replace(",", ".") if sep == ";" else valor) + 5
    linhas[-1] = sep.join([rotulo, texto_br(novo) if sep == ";" else texto_us(novo)])
    _gravar(arq, linhas)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"REPASSE_DIVERGENTE": "aceitar"})
    fechar_mes(conn, cfg0, "2025-08")
    f = conn.execute("select * from relatorio.loja_mes where loja_id = %s", (loja,)).fetchone()
    assert f["ajuste_repasse"] == Decimal("5.00")
    s = _somas(conn)
    assert s["titulos"] + s["ajuste"] == s["lojas"] == s["mes"]


def test_duplicado_aceito_vale_a_primeira_linha(conn, cfg0):
    arq, linhas, sep = _csv(cfg0)
    partes = linhas[2].split(sep)
    repetida = partes[:3] + [str(int(partes[3]) + 3)] + partes[4:]
    linhas.insert(3, sep.join(repetida))
    _gravar(arq, linhas)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"DUPLICADO": "aceitar"})
    fechar_mes(conn, cfg0, "2025-08")
    r = conn.execute(
        "select s.* from conferido.saldo s join public.film f using (film_id) "
        "where f.title = %s and s.loja_id = %s",
        (partes[0], _loja_do_csv(linhas)),
    ).fetchone()
    assert r["vendido"] == int(partes[1]) and r["estoque_final_loja"] == int(partes[3])
    assert r["estoque_final"] == int(partes[3])


def test_estoque_negativo_recusa_o_fechamento_e_nao_grava(conn, cfg0):
    arq, linhas, sep = _csv(cfg0)
    partes = linhas[2].split(sep)
    disponivel = int(partes[1]) + int(partes[2]) + int(partes[3])
    partes[1], partes[2], partes[3] = str(disponivel + 3), "0", "0"
    linhas[2] = sep.join(partes)
    _gravar(arq, linhas)
    _importar_e_conferir(conn, cfg0)
    _decidir_todas(conn, {"SALDO_NAO_FECHA": "contestar", "REPASSE_DIVERGENTE": "contestar"})
    with pytest.raises(ErroHermes, match="estoque negativo"):
        fechar_mes(conn, cfg0, "2025-08")
    assert conn.execute("select count(*) n from relatorio.loja_mes").fetchone()["n"] == 0
