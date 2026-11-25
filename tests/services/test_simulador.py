import json
import time
import unicodedata
from datetime import date
from decimal import Decimal

import openpyxl
import pymupdf

from hermes.config.contrato_padrao import CODIGOS_DIVERGENCIA
from hermes.core.dinheiro import valores
from hermes.core.meses import meses
from hermes.services.cadastro_service import preparar
from hermes.services.erros_service import injetar_erros
from hermes.services.remessa_service import emitir_mes
from hermes.services.simulador_service import catalogo, simular_mes, simular_vendas


def _preparado(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")


def test_verdade_fecha_a_conta(conn, cfg):
    _preparado(conn, cfg)
    relatorios = simular_vendas(conn, cfg, "2025-08")
    assert len(relatorios) == 24
    for r in relatorios:
        recebido = {
            x["film_id"]: x["quantidade"]
            for x in conn.execute(
                "select film_id, quantidade from hermes.nota_item join hermes.nota "
                "using (nota_id) where loja_id = %s and mes = '2025-08'",
                (r.loja_id,),
            )
        }
        assert {linha.film_id for linha in r.linhas} == set(recebido)
        for linha in r.linhas:
            assert linha.vendido + linha.devolvido + linha.estoque_final == recebido[linha.film_id]
            assert min(linha.vendido, linha.devolvido, linha.estoque_final) >= 0


def test_repasse_da_verdade_e_o_do_contrato(conn, cfg):
    _preparado(conn, cfg)
    r = simular_vendas(conn, cfg, "2025-08")[0]
    esperado = sum(
        valores(x.vendido, x.preco, Decimal("0.30"), Decimal("0.40")).repasse for x in r.linhas
    )
    assert r.repasse == esperado
    assert date(2025, 9, 1) <= r.recebido_em <= date(2025, 9, 10)


def test_lojas_vendem_alguma_coisa(conn, cfg):
    _preparado(conn, cfg)
    relatorios = simular_vendas(conn, cfg, "2025-08")
    vendido = sum(x.vendido for r in relatorios for x in r.linhas)
    recebido = sum(x.vendido + x.devolvido + x.estoque_final for r in relatorios for x in r.linhas)
    assert 0.35 < vendido / recebido < 0.75


def test_mesma_semente_mesma_verdade(conn, cfg):
    _preparado(conn, cfg)
    assert simular_vendas(conn, cfg, "2025-08") == simular_vendas(conn, cfg, "2025-08")


# ---------------------------------------------------------------- erros e arquivos


def _texto_do_arquivo(caminho):
    if caminho.suffix in (".csv", ".json"):
        return caminho.read_text(encoding="utf-8")
    if caminho.suffix == ".xlsx":
        ws = openpyxl.load_workbook(caminho).active
        return "\n".join(
            ";".join("" if c is None else str(c) for c in linha)
            for linha in ws.iter_rows(values_only=True)
        )
    # NFKC desfaz ligaduras que o PDF junta num caractere só ("ﬁ" -> "fi")
    texto = "\n".join(p.get_text() for p in pymupdf.open(caminho))
    return unicodedata.normalize("NFKC", texto)


def test_taxa_de_erro_perto_de_20_por_cento_e_todos_os_codigos(conn, cfg):
    _preparado(conn, cfg)
    verdade = simular_vendas(conn, cfg, "2025-08")
    cat = catalogo(conn)
    codigos = []
    for m in meses("2025-08", "2026-07"):
        _, gabarito = injetar_erros(verdade, cfg, m, cat)
        codigos += [e.codigo for e in gabarito]
    assert 0.12 <= len(codigos) / (24 * 12) <= 0.28
    assert set(codigos) == set(CODIGOS_DIVERGENCIA)


def test_injetar_nao_altera_a_verdade(conn, cfg):
    _preparado(conn, cfg)
    verdade = simular_vendas(conn, cfg, "2025-08")
    copia = simular_vendas(conn, cfg, "2025-08")
    for m in meses("2025-08", "2026-07"):
        injetar_erros(verdade, cfg, m, catalogo(conn))
    assert verdade == copia


def test_atrasado_chega_depois_do_dia_10_e_faltando_some(conn, cfg):
    _preparado(conn, cfg)
    verdade = simular_vendas(conn, cfg, "2025-08")
    for m in meses("2025-08", "2026-07"):
        com_erro, gabarito = injetar_erros(verdade, cfg, m, catalogo(conn))
        por_loja = {r.loja_id: r for r in com_erro}
        for e in gabarito:
            if e.codigo == "RELATORIO_ATRASADO":
                assert por_loja[e.loja_id].recebido_em.day > 10
            if e.codigo == "RELATORIO_FALTANDO":
                assert e.loja_id not in por_loja


def test_arquivo_tem_codigo_da_loja_e_apelidos_do_mapeamento(conn, cfg):
    _preparado(conn, cfg)
    gabarito = simular_mes(conn, cfg, "2025-08")
    faltando = {e.loja_id for e in gabarito if e.codigo == "RELATORIO_FALTANDO"}
    pasta = cfg.pasta_entrada / "2025-08"
    arquivos = [p for p in pasta.iterdir() if not p.name.startswith("_")]
    assert len(arquivos) == 24 - len(faltando)
    lojas = {
        r["loja_id"]: r["mapeamento"]
        for r in conn.execute("select loja_id, mapeamento from hermes.loja")
    }
    for arq in arquivos:
        texto = _texto_do_arquivo(arq)
        loja_id = int(texto.split("Loja ", 1)[1].split(" ", 1)[0])
        assert all(apelido in texto for apelido in lojas[loja_id].values())
        assert "Repasse total" in texto
    recebidos = (pasta / "_recebidos.csv").read_text(encoding="utf-8").splitlines()
    assert recebidos[0] == "arquivo;recebido_em" and len(recebidos) == len(arquivos) + 1
    salvo = json.loads((pasta / "_gabarito.json").read_text(encoding="utf-8"))
    assert len(salvo) == len(gabarito)


def test_mesma_semente_mesmos_bytes_em_todos_os_formatos(conn, cfg):
    _preparado(conn, cfg)
    simular_mes(conn, cfg, "2025-08")
    pasta = cfg.pasta_entrada / "2025-08"
    antes = {p.name: p.read_bytes() for p in pasta.iterdir()}
    assert {p.suffix for p in pasta.iterdir()} >= {".csv", ".xlsx", ".pdf"}
    time.sleep(2.1)  # o zip guarda a hora de 2 em 2 s: sem esperar, o teste passaria à toa
    simular_mes(conn, cfg, "2025-08")
    assert {p.name: p.read_bytes() for p in pasta.iterdir()} == antes
