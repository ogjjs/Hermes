import pytest

from hermes.core.erros import ErroHermes
from hermes.domain.relatorio_loja import interpretar

CRU = [
    ["Loja 5 - Vila Velha - Relatório 2025-08"],
    [],
    ["FILME", "VENDIDOS", "DEVOL", "estq", "preco"],
    ["ACADEMY DINOSAUR", "3", "0", "1", "29,90"],
    ["", "", "", "", ""],
    ["ALIEN CENTER", "1", "1", "0", "19,90"],
    ["Repasse total", "76,58"],
]


def test_acha_loja_cabecalho_linhas_e_repasse():
    r = interpretar(CRU)
    assert r.loja_id == 5 and r.repasse == "76,58"
    assert r.linhas == [
        {"FILME": "ACADEMY DINOSAUR", "VENDIDOS": "3", "DEVOL": "0", "estq": "1", "preco": "29,90"},
        {"FILME": "ALIEN CENTER", "VENDIDOS": "1", "DEVOL": "1", "estq": "0", "preco": "19,90"},
    ]


def test_repasse_no_mesmo_texto_com_dois_pontos():
    cru = CRU[:-1] + [["Repasse total: 76,58"]]
    assert interpretar(cru).repasse == "76,58"


def test_sem_loja_recusa():
    with pytest.raises(ErroHermes, match="código da loja"):
        interpretar(CRU[1:])


def test_sem_cabecalho_recusa():
    with pytest.raises(ErroHermes, match="cabeçalho"):
        interpretar([CRU[0], ["x", "y"]])


def test_linha_com_colunas_a_mais_recusa():
    cru = CRU[:4] + [["ALIEN CENTER", "1", "1", "0", "19,90", "sobra"]] + CRU[-1:]
    with pytest.raises(ErroHermes, match="colunas"):
        interpretar(cru)


def test_sem_nenhuma_linha_recusa():
    with pytest.raises(ErroHermes, match="nenhuma linha"):
        interpretar(CRU[:3] + CRU[-1:])
