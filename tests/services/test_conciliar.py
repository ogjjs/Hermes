from dataclasses import replace
from decimal import Decimal

import pytest

from hermes.core.dinheiro import ler_valor, texto_br, texto_us
from hermes.services.cadastro_service import preparar
from hermes.services.conciliacao_service import conferir_mes
from hermes.services.importacao_service import importar_mes
from hermes.services.remessa_service import emitir_mes
from hermes.services.simulador_service import simular_mes


def _ciclo(conn, cfg, taxa):
    cfg = replace(cfg, taxa_erro=Decimal(taxa))
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    gabarito = simular_mes(conn, cfg, "2025-08")
    return cfg, gabarito


def _um_csv(cfg):
    pasta = cfg.pasta_entrada / "2025-08"
    return next(p for p in sorted(pasta.glob("*.csv")) if not p.name.startswith("_"))


def _codigos(conn):
    return {
        (r["loja_id"], r["codigo"])
        for r in conn.execute("select loja_id, codigo from hermes.divergencia")
    }


def test_cada_erro_injetado_vira_a_divergencia_certa(conn, cfg):
    cfg, gabarito = _ciclo(conn, cfg, "1")
    importar_mes(conn, cfg, "2025-08")
    conferir_mes(conn, cfg, "2025-08")
    assert len(gabarito) >= 20
    assert {(e.loja_id, e.codigo) for e in gabarito} <= _codigos(conn)


def test_mes_sem_erro_nao_tem_divergencia(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "0")
    importar_mes(conn, cfg, "2025-08")
    assert conferir_mes(conn, cfg, "2025-08") == {}
    assert conn.execute("select count(*) n from hermes.divergencia").fetchone()["n"] == 0


def test_saldo_tem_uma_linha_por_titulo_recebido(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "0")
    importar_mes(conn, cfg, "2025-08")
    conferir_mes(conn, cfg, "2025-08")
    r = conn.execute(
        """select (select count(*) from conferido.saldo where mes = '2025-08') saldo,
                  (select count(*) from hermes.nota_item) itens,
                  (select count(*) from conferido.saldo
                    where estoque_final <> estoque_final_loja) diferentes"""
    ).fetchone()
    assert r["saldo"] == r["itens"] and r["diferentes"] == 0


def _mudar_repasse(arq, delta):
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if linhas[-1].startswith("Repasse total;") else ","
    valor = ler_valor(linhas[-1].split(sep, 1)[1]) + Decimal(delta)
    linhas[-1] = f"Repasse total{sep}{texto_br(valor) if sep == ';' else texto_us(valor)}"
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")


@pytest.mark.parametrize("delta,diverge", [("0.01", False), ("0.02", True)])
def test_repasse_tolerancia_um_centavo(conn, cfg, delta, diverge):
    cfg, _ = _ciclo(conn, cfg, "0")
    arq = _um_csv(cfg)
    _mudar_repasse(arq, delta)
    importar_mes(conn, cfg, "2025-08")
    assert ("REPASSE_DIVERGENTE" in conferir_mes(conn, cfg, "2025-08")) is diverge


def test_titulo_escrito_diferente_casa(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "0")
    arq = _um_csv(cfg)
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    titulo = linhas[2].split(sep)[0]
    linhas[2] = linhas[2].replace(titulo, "  " + titulo.lower().replace(" ", "   ") + " ", 1)
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    importar_mes(conn, cfg, "2025-08")
    assert conferir_mes(conn, cfg, "2025-08") == {}


def test_titulo_que_nao_existe_vira_nao_enviado(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "0")
    arq = _um_csv(cfg)
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    partes = linhas[2].split(sep)
    linhas.insert(3, sep.join(["FILME QUE NAO EXISTE", "0", "0", "0", partes[4]]))
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    importar_mes(conn, cfg, "2025-08")
    assert conferir_mes(conn, cfg, "2025-08") == {"TITULO_NAO_ENVIADO": 1}


def test_conferir_duas_vezes_nao_duplica_nem_reabre(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "1")
    importar_mes(conn, cfg, "2025-08")
    primeira = conferir_mes(conn, cfg, "2025-08")
    conn.execute(
        "update hermes.divergencia set estado = 'aceita', motivo = 'teste', decidida_em = now() "
        "where divergencia_id = (select min(divergencia_id) from hermes.divergencia)"
    )
    conn.commit()
    assert conferir_mes(conn, cfg, "2025-08") == primeira
    decididas = conn.execute(
        "select count(*) n from hermes.divergencia where estado = 'aceita'"
    ).fetchone()["n"]
    assert decididas == 1


def test_linha_ilegivel_vira_divergencia_propria(conn, cfg):
    cfg, _ = _ciclo(conn, cfg, "0")
    arq = _um_csv(cfg)
    linhas = arq.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    partes = linhas[2].split(sep)
    partes[1] = "abc"
    linhas[2] = sep.join(partes)
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    importar_mes(conn, cfg, "2025-08")
    assert conferir_mes(conn, cfg, "2025-08") == {"LINHA_ILEGIVEL": 1}
