"""Cada camada só importa o que o desenho permite (docs/plans, "Regras das camadas")."""

import ast
from pathlib import Path

import pytest

PACOTE = Path(__file__).resolve().parents[1] / "src" / "hermes"

PERMITIDAS = {
    "interface": {"interface", "application", "core"},
    "application": {"application", "services", "core", "config"},
    "services": {"services", "domain", "core", "infra", "config"},
    "domain": {"domain", "core", "config"},
    "core": {"core"},
    "infra": {"infra", "core", "config"},
    "config": {"config", "core"},
}


def _camadas_importadas(arquivo: Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module)
    return {n.split(".")[1] for n in nomes if n.startswith("hermes.") and n.count(".") >= 1}


@pytest.mark.parametrize("camada", sorted(PERMITIDAS))
def test_camada_so_importa_o_permitido(camada):
    proibidos = {}
    for arquivo in (PACOTE / camada).rglob("*.py"):
        fora = _camadas_importadas(arquivo) - PERMITIDAS[camada]
        if fora:
            proibidos[arquivo.name] = sorted(fora)
    assert proibidos == {}


def test_regra_pega_import_proibido(tmp_path, monkeypatch):
    falso = tmp_path / "x.py"
    falso.write_text("from hermes.infra.db import conectar\n", encoding="utf-8")
    assert _camadas_importadas(falso) - PERMITIDAS["core"] == {"infra"}
