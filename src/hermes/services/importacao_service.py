"""Importação dos relatórios das lojas: arquivo -> `bruto` (como chegou) -> `padronizado`.

PDF é lido em duas tentativas: PyMuPDF e, se a leitura falhar, pdfplumber.
"""

from __future__ import annotations

import csv
import json
from datetime import date
from hashlib import sha256
from pathlib import Path

import psycopg

from hermes.config.settings import Config
from hermes.core.dinheiro import ler_valor
from hermes.core.erros import ErroHermes
from hermes.core.meses import validar_mes
from hermes.core.modelos import LeituraArquivo, ResumoImportacao
from hermes.core.normalizacao import normalizar_titulo
from hermes.domain.relatorio_loja import interpretar
from hermes.infra import leitores
from hermes.infra.db import executar_sql

_INTEIROS = ("vendido", "devolvido", "estoque_final")


def ler_arquivo(caminho: Path) -> LeituraArquivo:
    sufixo = caminho.suffix.lower()
    if sufixo in (".csv", ".xlsx"):
        ler = leitores.linhas_csv if sufixo == ".csv" else leitores.linhas_xlsx
        try:
            cru = ler(caminho)
        except Exception as e:  # arquivo corrompido, encoding, zip inválido...
            raise ErroHermes(f"não consegui abrir o arquivo ({type(e).__name__}: {e})") from None
        return interpretar(cru, "pandas")
    if sufixo == ".pdf":
        motivos = []
        for nome, ler in (
            ("pymupdf", lambda c: leitores.linhas_pdf_pymupdf(c)),
            ("pdfplumber", lambda c: leitores.linhas_pdf_pdfplumber(c)),
        ):
            try:
                return interpretar(ler(caminho), nome)
            except Exception as e:
                motivos.append(f"{nome}: {e}")
        raise ErroHermes("a leitura do PDF falhou nas duas tentativas — " + "; ".join(motivos))
    raise ErroHermes(f"formato não suportado: {sufixo or 'sem extensão'}")


def _recebidos(pasta: Path) -> dict[str, date]:
    registro = pasta / "_recebidos.csv"
    if not registro.is_file():
        return {}
    with registro.open(encoding="utf-8", newline="") as f:
        return {
            r["arquivo"]: date.fromisoformat(r["recebido_em"])
            for r in csv.DictReader(f, delimiter=";")
        }


def _valores(linha: dict[str, str], mapeamento: dict[str, str], numero: int, erros: list[str]):
    valores: dict[str, str] = {"titulo": normalizar_titulo(linha[mapeamento["titulo"]])}
    for campo in (*_INTEIROS, "preco"):
        texto = linha[mapeamento[campo]]
        try:
            v = ler_valor(texto)
            if v is None:
                raise ValueError
            if campo in _INTEIROS:
                if v != v.to_integral_value() or v < 0:
                    raise ValueError
                v = int(v)
            valores[campo] = str(v)
        except (ValueError, ArithmeticError):
            erros.append(f"linha {numero}: {campo} inválido ({texto!r})")
    return valores


def _gravar_leitura(conn, arquivo_id: int, leitura: LeituraArquivo, mapeamento: dict) -> list[str]:
    erros: list[str] = []
    try:
        repasse = ler_valor(leitura.repasse)
    except ValueError:
        repasse = None
    if repasse is None:
        erros.append(f"repasse inválido ({leitura.repasse!r})")
    linhas = [
        (
            arquivo_id,
            0,
            json.dumps(
                {
                    "repasse": leitura.repasse,
                    "_valores": {} if repasse is None else {"repasse": str(repasse)},
                },
                ensure_ascii=False,
            ),
        )
    ]
    for numero, original in enumerate(leitura.linhas, start=1):
        conteudo = dict(original, _valores=_valores(original, mapeamento, numero, erros))
        linhas.append((arquivo_id, numero, json.dumps(conteudo, ensure_ascii=False)))
    with conn.cursor() as cur:
        cur.executemany("insert into bruto.linha values (%s, %s, %s)", linhas)
    return erros


def _substituir_anterior(conn, loja_id: int, mes: str) -> bool:
    anterior = conn.execute(
        "update hermes.arquivo set substituido = true where loja_id = %s and mes = %s "
        "and not substituido and leitor is not null returning arquivo_id",
        (loja_id, mes),
    ).fetchall()
    if not anterior:
        return False
    conn.execute("delete from hermes.divergencia where loja_id = %s and mes = %s", (loja_id, mes))
    conn.execute(
        "update hermes.mes_loja set situacao = 'aberto' where loja_id = %s and mes = %s",
        (loja_id, mes),
    )
    return True


def importar_mes(conn: psycopg.Connection, cfg: Config, mes: str) -> ResumoImportacao:
    validar_mes(mes)
    pasta = cfg.pasta_entrada / mes
    if not pasta.is_dir():
        raise ErroHermes(f"Não há pasta de entrada para {mes}: {pasta}")
    recebidos = _recebidos(pasta)
    mapas = {r["loja_id"]: r["mapeamento"] for r in conn.execute("select * from hermes.loja")}
    resumo = ResumoImportacao()
    for arq in sorted(p for p in pasta.iterdir() if p.is_file() and not p.name.startswith("_")):
        assinatura = sha256(arq.read_bytes()).hexdigest()
        if conn.execute("select 1 from hermes.arquivo where sha256 = %s", (assinatura,)).fetchone():
            resumo.ignorados_repetidos += 1
            continue
        recebido_em = recebidos.get(arq.name, date.today())
        try:
            leitura = ler_arquivo(arq)
            if leitura.loja_id not in mapas:
                raise ErroHermes(f"loja {leitura.loja_id} não está cadastrada")
            mapa = mapas[leitura.loja_id]
            faltam = [c for c in mapa.values() if c not in leitura.linhas[0]]
            if faltam:
                raise ErroHermes(f"colunas que faltam: {', '.join(faltam)}")
        except ErroHermes as e:
            conn.execute(
                "insert into hermes.arquivo (mes, nome, sha256, recebido_em, erro) "
                "values (%s, %s, %s, %s, %s)",
                (mes, arq.name, assinatura, recebido_em, str(e)),
            )
            resumo.com_erro.append((arq.name, str(e)))
            continue
        if _substituir_anterior(conn, leitura.loja_id, mes):
            resumo.substituidos += 1
        arquivo_id = conn.execute(
            "insert into hermes.arquivo (loja_id, mes, nome, sha256, recebido_em, leitor) "
            "values (%s, %s, %s, %s, %s, %s) returning arquivo_id",
            (leitura.loja_id, mes, arq.name, assinatura, recebido_em, leitura.leitor),
        ).fetchone()["arquivo_id"]
        erros = _gravar_leitura(conn, arquivo_id, leitura, mapa)
        if erros:
            conn.execute(
                "update hermes.arquivo set erro = %s where arquivo_id = %s",
                ("; ".join(erros), arquivo_id),
            )
        resumo.lidos += 1
    executar_sql(conn, "padronizar.sql", {"mes": mes})
    conn.commit()
    return resumo
