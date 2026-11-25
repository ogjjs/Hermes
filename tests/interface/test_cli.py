import pytest

from hermes.infra.db import executar_sql
from hermes.interface.cli import main
from tests.conftest import SCHEMAS


@pytest.fixture
def env_do_teste(cfg, tmp_path):
    def criar(**extra):
        valores = {
            "PGHOST": cfg.host,
            "PGPORT": cfg.porta,
            "PGUSER": cfg.usuario,
            "PGPASSWORD": cfg.senha,
            "PGDATABASE": "hermes_teste",
            "HERMES_ENTRADA": cfg.pasta_entrada,
            "HERMES_SAIDA": cfg.pasta_saida,
            **extra,
        }
        env = tmp_path / ".env.teste"
        env.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
        return str(env)

    return criar


def _zerar(conn):
    conn.execute(f"drop schema if exists {', '.join(SCHEMAS)} cascade")
    executar_sql(conn, "001_schemas.sql")
    conn.commit()


CONSULTAS = (
    "select * from relatorio.mes order by mes",
    "select * from relatorio.loja_mes order by mes, loja_id",
)


def test_rodar_12_meses_fecha_tudo_e_repete_igual(conn, env_do_teste, capsys):
    env = env_do_teste()
    assert main(["--env", env, "rodar", "2025-08", "2026-07"]) == 0
    saida = capsys.readouterr().out
    assert saida.count("\n2025-") + saida.count("\n2026-") >= 11 and "lucro" in saida
    assert conn.execute("select count(*) n from relatorio.mes").fetchone()["n"] == 12
    abertas = conn.execute(
        "select count(*) n from hermes.divergencia where estado = 'aberta'"
    ).fetchone()["n"]
    assert abertas == 0
    antes = [conn.execute(q).fetchall() for q in CONSULTAS]
    conn.commit()
    _zerar(conn)
    assert main(["--env", env, "rodar", "2025-08", "2026-07"]) == 0
    assert [conn.execute(q).fetchall() for q in CONSULTAS] == antes


def test_passo_a_passo_com_erro_vira_mensagem_sem_traceback(conn, env_do_teste, capsys):
    env = env_do_teste(HERMES_TAXA_ERRO="1")
    for comando in (
        ["preparar"],
        ["emitir", "2025-08"],
        ["simular", "2025-08"],
        ["importar", "2025-08"],
        ["conferir", "2025-08"],
    ):
        assert main(["--env", env, *comando]) == 0
    capsys.readouterr()
    assert main(["--env", env, "fechar", "2025-08"]) == 1
    erro = capsys.readouterr().err
    assert "divergências abertas" in erro and "Traceback" not in erro


def test_divergencias_lista_e_decidir_decide(conn, env_do_teste, capsys):
    env = env_do_teste(HERMES_TAXA_ERRO="1")
    for comando in (
        ["preparar"],
        ["emitir", "2025-08"],
        ["simular", "2025-08"],
        ["importar", "2025-08"],
        ["conferir", "2025-08"],
    ):
        main(["--env", env, *comando])
    capsys.readouterr()
    assert main(["--env", env, "divergencias", "2025-08"]) == 0
    lista = capsys.readouterr().out
    primeira = conn.execute("select min(divergencia_id) i from hermes.divergencia").fetchone()["i"]
    conn.commit()
    assert f"#{primeira}" in lista
    assert main(["--env", env, "decidir", str(primeira), "aceitar", "conferido por telefone"]) == 0
    estado = conn.execute(
        "select estado from hermes.divergencia where divergencia_id = %s", (primeira,)
    ).fetchone()["estado"]
    assert estado == "aceita"


def test_mes_invalido_vira_mensagem(env_do_teste, capsys):
    assert main(["--env", env_do_teste(), "emitir", "agosto"]) == 1
    assert "Mês inválido" in capsys.readouterr().err
