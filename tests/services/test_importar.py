from dataclasses import replace
from decimal import Decimal

import pymupdf
import pytest

from hermes.core.dinheiro import ler_valor
from hermes.core.erros import ErroHermes
from hermes.infra import leitores
from hermes.services.cadastro_service import preparar
from hermes.services.importacao_service import importar_mes, ler_arquivo
from hermes.services.remessa_service import emitir_mes
from hermes.services.simulador_service import simular_mes, simular_vendas


def _arquivos(cfg, mes="2025-08"):
    return sorted(p for p in (cfg.pasta_entrada / mes).iterdir() if not p.name.startswith("_"))


@pytest.fixture
def mes_sem_erro(conn, cfg):
    cfg = replace(cfg, taxa_erro=Decimal("0"))
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    simular_mes(conn, cfg, "2025-08")
    return cfg


def test_le_os_quatro_formatos(conn, mes_sem_erro):
    cfg = mes_sem_erro
    verdade = {r.loja_id: r for r in simular_vendas(conn, cfg, "2025-08")}
    formatos = {r["loja_id"]: r["formato"] for r in conn.execute("select * from hermes.loja")}
    vistos = set()
    for arq in _arquivos(cfg):
        leitura = ler_arquivo(arq)
        assert len(leitura.linhas) == len(verdade[leitura.loja_id].linhas)
        assert ler_valor(leitura.repasse) == verdade[leitura.loja_id].repasse
        vistos.add(formatos[leitura.loja_id])
        if arq.suffix == ".pdf":
            assert leitura.leitor == "pymupdf"
        else:
            assert leitura.leitor == "pandas"
    assert vistos == {"csv_ponto_virgula", "csv_virgula", "xlsx", "pdf"}


def test_pdf_usa_pdfplumber_quando_pymupdf_falha(conn, mes_sem_erro, monkeypatch):
    pdf = next(p for p in _arquivos(mes_sem_erro) if p.suffix == ".pdf")
    monkeypatch.setattr(leitores, "linhas_pdf_pymupdf", lambda caminho: [["Loja 5"]])
    leitura = ler_arquivo(pdf)
    assert leitura.leitor == "pdfplumber" and len(leitura.linhas) > 0


def test_pdf_os_dois_falham(tmp_path):
    vazio = tmp_path / "branco.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(vazio)
    with pytest.raises(ErroHermes, match="pymupdf.*pdfplumber"):
        ler_arquivo(vazio)


def test_extensao_desconhecida(tmp_path):
    (tmp_path / "x.txt").write_text("oi", encoding="utf-8")
    with pytest.raises(ErroHermes, match="formato"):
        ler_arquivo(tmp_path / "x.txt")


def test_importar_duas_vezes_nao_duplica(conn, mes_sem_erro):
    primeiro = importar_mes(conn, mes_sem_erro, "2025-08")
    assert primeiro.lidos == 24 and primeiro.com_erro == []
    linhas = conn.execute("select count(*) n from bruto.linha").fetchone()["n"]
    segundo = importar_mes(conn, mes_sem_erro, "2025-08")
    assert segundo.lidos == 0 and segundo.ignorados_repetidos == 24
    assert conn.execute("select count(*) n from bruto.linha").fetchone()["n"] == linhas


def test_recebido_em_vem_do_registro_de_emails(conn, mes_sem_erro):
    importar_mes(conn, mes_sem_erro, "2025-08")
    r = conn.execute(
        "select min(recebido_em) mi, max(recebido_em) ma from hermes.arquivo"
    ).fetchone()
    assert str(r["mi"]) >= "2025-09-01" and str(r["ma"]) <= "2025-09-10"


def test_arquivo_novo_da_mesma_loja_substitui(conn, mes_sem_erro):
    importar_mes(conn, mes_sem_erro, "2025-08")
    csv = next(p for p in _arquivos(mes_sem_erro) if p.suffix == ".csv")
    novo = csv.with_name("reenviado " + csv.name)
    novo.write_text(csv.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    r = importar_mes(conn, mes_sem_erro, "2025-08")
    assert r.lidos == 1 and r.substituidos == 1
    ativos = conn.execute(
        "select count(*) n from hermes.arquivo where not substituido and erro is null"
    ).fetchone()["n"]
    assert ativos == 24
    origem = conn.execute(
        "select distinct a.nome from padronizado.venda v join hermes.arquivo a using (arquivo_id) "
        "where a.nome like 'reenviado%%'"
    ).fetchall()
    assert len(origem) == 1


def test_arquivo_ruim_nao_para_o_resto(conn, mes_sem_erro):
    pasta = mes_sem_erro.pasta_entrada / "2025-08"
    (pasta / "quebrado.xlsx").write_bytes(b"isto nao e um xlsx")
    r = importar_mes(conn, mes_sem_erro, "2025-08")
    assert r.lidos == 24
    assert [nome for nome, _ in r.com_erro] == ["quebrado.xlsx"]
    erro = conn.execute("select erro from hermes.arquivo where nome = 'quebrado.xlsx'").fetchone()
    assert erro["erro"]


def test_padronizado_tem_numeros_e_titulo_ligado(conn, mes_sem_erro):
    importar_mes(conn, mes_sem_erro, "2025-08")
    r = conn.execute(
        "select count(*) total, count(*) filter (where vendido is null) sem_numero, "
        "count(*) filter (where film_id is null) sem_titulo from padronizado.venda"
    ).fetchone()
    assert r["total"] > 0 and r["sem_numero"] == 0 and r["sem_titulo"] == 0
    assert conn.execute("select count(*) n from padronizado.repasse").fetchone()["n"] == 24


def test_linha_com_numero_invalido_vira_erro_de_linha(conn, mes_sem_erro):
    csv = next(p for p in _arquivos(mes_sem_erro) if p.suffix == ".csv")
    linhas = csv.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    partes = linhas[2].split(sep)
    partes[1] = "abc"
    linhas[2] = sep.join(partes)
    csv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    importar_mes(conn, mes_sem_erro, "2025-08")
    a = conn.execute("select arquivo_id, erro from hermes.arquivo where nome = %s", (csv.name,))
    a = a.fetchone()
    assert "linha 1" in a["erro"] and "inválido" in a["erro"]
    n = conn.execute(
        "select count(*) n from padronizado.venda where arquivo_id = %s", (a["arquivo_id"],)
    ).fetchone()["n"]
    assert n == len(linhas) - 4  # título, cabeçalho, repasse e a linha inválida ficam de fora


def test_numero_fora_do_intervalo_vira_erro_de_linha(conn, mes_sem_erro):
    csv = next(p for p in _arquivos(mes_sem_erro) if p.suffix == ".csv")
    linhas = csv.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    for i, coluna, valor in ((2, 1, "99999999999"), (3, 4, "1e20")):
        partes = linhas[i].split(sep)
        partes[coluna] = valor
        linhas[i] = sep.join(partes)
    csv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    r = importar_mes(conn, mes_sem_erro, "2025-08")
    assert r.lidos == 24
    erro = conn.execute("select erro from hermes.arquivo where nome = %s", (csv.name,))
    erro = erro.fetchone()["erro"]
    assert "linha 1: vendido" in erro and "linha 2: preco" in erro


def test_erros_de_linha_aparecem_no_resumo(conn, mes_sem_erro):
    csv = next(p for p in _arquivos(mes_sem_erro) if p.suffix == ".csv")
    linhas = csv.read_text(encoding="utf-8").splitlines()
    sep = ";" if ";" in linhas[1] else ","
    partes = linhas[2].split(sep)
    partes[1] = "abc"
    linhas[2] = sep.join(partes)
    csv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    r = importar_mes(conn, mes_sem_erro, "2025-08")
    assert r.com_erro == []
    assert r.com_erro_de_linha == [(csv.name, "linha 1: vendido inválido ('abc')")]
