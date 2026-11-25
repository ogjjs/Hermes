# Hermes fase 1 (back-end) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma pipeline de consignação (emitir remessas → simular as lojas → importar os relatórios → conciliar → decidir → fechar o mês) em Python + PostgreSQL, rodando 12 meses com um comando.

**Architecture:** Pacote `hermes` com quatro módulos de negócio (`emissao`, `simulador`, `retorno`, `conferencia`) e uma CLI. O Pagila (`public`) é só leitura. Tudo do Hermes vive em cinco schemas do mesmo banco: `hermes` (cadastro e operação), `bruto`, `padronizado`, `conferido`, `relatorio`. Python lê e escreve arquivos; as passagens entre camadas são SQL em arquivos `.sql` versionados.

**Tech Stack:** Python 3.14 (`requires-python >= 3.12`), `pandas`, `numpy`, `psycopg[binary]` 3 (tem wheel cp314), `openpyxl` (motor do pandas para .xlsx), `pymupdf` (gera PDF e é o leitor principal), `pdfplumber` (leitor reserva de PDF), `python-dotenv`; dev: `pytest`, `pytest-cov`, `ruff`. Versões de partida: as que o autor já roda em 3.14 (`numpy 2.5.4`, `pandas 3.1.0`, `pymupdf 2.1`, `openpyxl 3.1.5`, `pytest 9.2.0`) e `psycopg-binary 3.3.9`. PostgreSQL 18 local (`psql` em `C:\Program Files\PostgreSQL\18\bin\psql.exe`).

**Spec:** `docs/specs/2026-11-23-hermes-fase-1-design.md`

## Global Constraints

- Nenhum código, regra, nome ou dado copiado do Argus, do Octopus ou da empresa.
- Tabelas do Pagila (`public`) nunca são alteradas; o Hermes só faz `SELECT` nelas.
- Credenciais só no `.env` (no `.gitignore`); `.env.example` com as chaves e sem valores.
- Preço por `rental_rate`: 0.99 → **R$ 19,90** · 2.99 → **R$ 29,90** · 4.99 → **R$ 39,90**.
- Comissão da loja **30%** sobre a venda; custo **40% do preço**; frete embutido (não existe no modelo).
- Dinheiro sempre `Decimal` / `NUMERIC(12,2)`, arredondado por linha com `ROUND_HALF_UP` para centavos. Nunca `float`.
- Mês sempre como texto `AAAA-MM`. Período simulado: **2025-08 a 2026-07**.
- Lojas parceiras: as **24 lojas do Pagila no Brasil** (`store → address → city → country = 'Brazil'`).
- Relatório da loja chega **até o dia 10** do mês seguinte; remessa do mês M é emitida no **dia 11 de M** (no primeiro mês, dia 1, estoque zero).
- Tolerância de repasse: **R$ 0,01**. Taxa padrão de relatório com erro: **0,20**.
- Nota fiscal marcada como **fictícia**, sem chave de acesso e sem CNPJ.
- Mesma semente → mesmos arquivos e mesmo `relatorio`. Proibido `hash()` de string, `random` e `numpy.random` globais: toda aleatoriedade vem de `numpy.random.default_rng(semente_derivada(...))`.
- CSV e Excel são lidos e escritos com **pandas**. PDF é gerado com **PyMuPDF** (`import pymupdf`) e lido primeiro com ele; se a leitura falhar, tenta de novo com **pdfplumber**. `hermes.arquivo.leitor` guarda qual dos dois leu.
- Ambiente virtual: **`mensagem/`** (já criado pelo autor, Python 3.14.3), fora do git.
- `ruff check` e `ruff format --check` sem achados antes de cada commit.
- Textos de interface, mensagens e nomes de domínio em português.
- O ambiente de desenvolvimento é o Windows; os comandos de teste também rodam em Linux (CI).

## Review Focus

1. **Números no formato brasileiro e no americano** ("1.234,56", "1234,56", "1,234.56", "R$ 39,90", "39.9") precisam virar o `Decimal` certo; um texto que não é número vira erro de linha, sem derrubar o arquivo. → teste em Task 6.
2. **Títulos escritos de outro jeito** (minúsculas, espaços duplos, espaço no fim) casam com o catálogo; um título que não existe vira `TITULO_NAO_ENVIADO`, não exceção. → teste em Task 7.
3. **Arquivo ilegível** (vazio, extensão desconhecida, xlsx sem cabeçalho, sem código da loja) fica registrado como `arquivo_recebido` com `erro`, e os outros arquivos do mês continuam sendo importados. → teste em Task 6.
4. **Repetir um comando no mesmo mês** (`emitir`, `importar`, `conferir`) não duplica notas, linhas nem divergências. → testes em Tasks 3, 6 e 7.
5. **Rodar um mês fora de ordem** (`emitir 2025-10` sem 2025-09 fechado; `fechar` com divergência aberta) recusa com mensagem clara que diz o que falta, sem gravar nada. → testes em Tasks 3 e 9.

---

## Estrutura de arquivos (camadas, no mesmo desenho do Octopus)

```
Hermes/
  pyproject.toml              # pacote hermes, script "hermes = hermes.main:main"
  .env.example  README.md  LICENSE  .github/workflows/testes.yml
  src/hermes/
    main.py                   # inicializador único: chama interface.cli
    interface/   <- entrada do usuário (hoje a CLI; uma tela depois). Não decide fluxo nem grava nada.
      cli.py
    application/ <- coordena o fluxo: chama os services na ordem certa. CLI e tela futura usam o mesmo.
      ciclo_app.py            # preparar, emitir, simular, importar, conferir, divergencias, decidir, fechar, rodar
    services/    <- regras de negócio e validação, com o banco pela infra
      cadastro_service.py     # preparar
      remessa_service.py      # emitir_mes, estoque_inicial
      simulador_service.py    # simular_vendas, simular_mes
      erros_service.py        # injetar_erros
      importacao_service.py   # importar_mes
      conciliacao_service.py  # conferir_mes
      decisao_service.py      # decidir, decidir_automatico
      fechamento_service.py   # fechar_mes
    domain/      <- interpretação de cada tipo de documento (puro, sem I/O)
      relatorio_loja.py       # achar loja, cabeçalho, linhas e repasse nas linhas lidas
      nota_fiscal.py          # conteúdo e atributos (JSON) do espelho da nota
    core/        <- modelos e regras puras
      modelos.py  dinheiro.py  sorteio.py  normalizacao.py  meses.py  erros.py
    infra/       <- só I/O: banco, arquivos, PDF, planilhas
      db.py  arquivos.py  leitores.py  escritores.py  pdf.py
      sql/  001_schemas.sql  padronizar.sql  conciliar.sql  fechar.sql
    config/
      settings.py             # Config e carregar_config (.env)
      contrato_padrao.py      # faixas de preço, comissão, custo, apelidos de colunas, códigos de divergência
  tests/  core/  domain/  infra/  services/  application/  interface/  conftest.py
```

Regras das camadas: `interface` só importa `application`; `application` só importa `services` e `core`; `services` importa `domain`, `core`, `infra` e `config`; `domain` e `core` não importam `infra` nem fazem I/O; `infra` não tem regra de negócio. Um teste em `tests/test_camadas.py` (Task 1) confere os imports com `ast`.

---

### Task 1: Base do projeto e banco de teste

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/hermes/__init__.py` (e `__init__.py` de cada camada), `tests/test_camadas.py`, `src/hermes/config/settings.py`, `src/hermes/infra/db.py`, `src/hermes/core/erros.py`, `tests/conftest.py`, `tests/infra/test_db.py`

**Interfaces:**
- Produces:
  - `Config` (frozen dataclass): `host="localhost"`, `porta=5432`, `usuario="postgres"`, `senha`, `banco="pagila"`, `semente=2026`, `taxa_erro=Decimal("0.20")`, `psql` (caminho), `pagila_sql_dir` (pasta com `pagila-schema.sql` e `pagila-data.sql`), `pasta_entrada=Path("entrada")`, `pasta_saida=Path("saida")`.
  - `carregar_config(env_file: Path | None = None, **sobrepor) -> Config`. Chaves no `.env`: `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`, `HERMES_SEMENTE`, `HERMES_TAXA_ERRO`, `HERMES_PSQL`, `PAGILA_SQL_DIR`.
  - `conectar(cfg: Config, banco: str | None = None) -> psycopg.Connection` (autocommit desligado, `row_factory=dict_row`).
  - `executar_sql(conn, nome: str) -> None`: executa `src/hermes/infra/sql/<nome>` (lido com `importlib.resources`).
  - `class ErroHermes(Exception)`: mensagem em português para o usuário.
  - Fixture `conn` (pytest): conexão a `hermes_teste`, com `001_schemas.sql` aplicado (a partir da Task 2) e com os schemas do Hermes zerados a cada teste. Fixture `cfg`.

- [ ] **Step 1: `pyproject.toml`** com `requires-python = ">=3.12"`, as dependências do Tech Stack, `pytest`, `pytest-cov` e `ruff` em `[project.optional-dependencies].dev`, `[tool.ruff]` com `line-length = 100`, layout `src/`, script `hermes = "hermes.main:main"`. `.env.example` com as chaves acima, sem valores. Instalar no venv que já existe: `mensagem\Scripts\pip install -e .[dev]`.

- [ ] **Step 2: Escrever `tests/conftest.py`.** Em escopo de sessão: se o banco `hermes_teste` não existir, criá-lo (conexão ao banco `postgres`, `CREATE DATABASE`) e carregar o Pagila rodando `psql -v ON_ERROR_STOP=1 -f pagila-schema.sql` e depois `pagila-data.sql`, com `PGPASSWORD` no ambiente do subprocesso. Se ele já existir, reaproveitar. Por teste: abrir a conexão; a partir da Task 2, `DROP SCHEMA IF EXISTS hermes, bruto, padronizado, conferido, relatorio CASCADE` + `executar_sql(conn, "001_schemas.sql")`; no fim, fechar sem commit pendente.

- [ ] **Step 3: Teste que falha** em `tests/infra/test_db.py`:

```python
def test_conecta_e_le_o_pagila(conn):
    assert conn.execute("select count(*) as n from public.film").fetchone()["n"] == 1000

def test_config_le_o_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("PGPASSWORD=x\nHERMES_SEMENTE=7\n", encoding="utf-8")
    cfg = carregar_config(env)
    assert cfg.senha == "x" and cfg.semente == 7 and cfg.banco == "pagila"
```

- [ ] **Step 4:** `mensagem\Scripts\pytest tests/infra/test_db.py -v` → FAIL (import).
- [ ] **Step 5:** Implementar `config.py`, `db.py` e `erros.py`.
- [ ] **Step 6:** `mensagem\Scripts\pytest tests/infra/test_db.py -v` → PASS. Na primeira vez o carregamento do Pagila leva alguns segundos.
- [ ] **Step 7: Commit** `feat: base do projeto e banco de teste`

---

### Task 2: Schemas e cadastro (`preparar`)

**Files:**
- Create: `src/hermes/infra/sql/001_schemas.sql`, `src/hermes/core/sorteio.py`, `src/hermes/config/contrato_padrao.py`, `src/hermes/services/cadastro_service.py`, `tests/core/test_sorteio.py`, `tests/services/test_cadastro.py`

**Interfaces:**
- Consumes: `conectar`, `executar_sql`, fixture `conn`.
- Produces:
  - Tabelas (nomes exatos, usados por todas as tasks seguintes):
    - `hermes.loja(loja_id int PK  -- = public.store.store_id, cidade text, formato text CHECK in ('csv_ponto_virgula','csv_virgula','xlsx','pdf'), mapeamento jsonb)`
    - `hermes.contrato(contrato_id serial PK, loja_id FK, vigencia_inicio date, vigencia_fim date null, comissao numeric(5,4), custo_pct numeric(5,4))`
    - `hermes.preco(contrato_id FK, rental_rate numeric(4,2), preco numeric(10,2), PK(contrato_id, rental_rate))`
    - `hermes.sortimento(loja_id FK, film_id int, estoque_alvo int CHECK (estoque_alvo > 0), PK(loja_id, film_id))`
    - `hermes.nota(nota_id serial PK, numero int UNIQUE, loja_id FK, mes char(7), emitida_em date, valor_total numeric(12,2), UNIQUE(loja_id, mes))`
    - `hermes.nota_item(nota_id FK, film_id int, quantidade int CHECK (quantidade > 0), preco_unit numeric(10,2), PK(nota_id, film_id))`
    - `hermes.arquivo(arquivo_id serial PK, loja_id int null, mes char(7), nome text, sha256 char(64) UNIQUE, recebido_em date, substituido bool default false, erro text null, leitor text null CHECK in ('pandas','pymupdf','pdfplumber'))`
    - `hermes.divergencia(divergencia_id serial PK, loja_id, mes, film_id int null, codigo text, valor_loja numeric(12,2) null, valor_calculado numeric(12,2) null, estado text default 'aberta' CHECK in ('aberta','aceita','contestada'), motivo text null, decidida_em timestamptz null, UNIQUE NULLS NOT DISTINCT (loja_id, mes, film_id, codigo))`
    - `hermes.mes_loja(loja_id, mes, situacao text CHECK in ('aberto','fechado','sem_relatorio'), PK(loja_id, mes))`
    - `bruto.linha(arquivo_id FK, numero int, conteudo jsonb, PK(arquivo_id, numero))`
    - `padronizado.venda(arquivo_id FK, loja_id, mes, linha int, film_id int null, titulo_informado text, vendido int, devolvido int, estoque_final int, preco_informado numeric(10,2) null)`
    - `padronizado.repasse(arquivo_id FK, loja_id, mes, valor numeric(12,2), PK(loja_id, mes))`
    - `conferido.saldo(loja_id, mes, film_id, estoque_inicial int, recebido int, vendido int, devolvido int, estoque_final_loja int null, estoque_final int, preco numeric(10,2), cobranca numeric(12,2) default 0, ajuste int default 0, PK(loja_id, mes, film_id))`
    - `relatorio.loja_mes`, `relatorio.titulo_mes` e `relatorio.mes` (colunas definidas na Task 9).
  - `semente_derivada(semente: int, *partes: object) -> int`: `int.from_bytes(sha256("|".join(map(str,(semente,*partes))).encode()).digest()[:8], "big")`.
  - `rng(semente: int, *partes) -> numpy.random.Generator` (`default_rng(semente_derivada(semente, *partes))`).
  - `preparar(conn, cfg: Config) -> int` (devolve o número de lojas cadastradas, 24). Idempotente.

- [ ] **Step 1: Testes que falham**:

```python
# tests/core/test_sorteio.py
def test_semente_derivada_e_estavel_entre_processos():
    assert semente_derivada(2026, "loja", 5, "2025-08") == semente_derivada(2026, "loja", 5, "2025-08")
    assert semente_derivada(2026, 5) != semente_derivada(2026, 6)

# tests/services/test_cadastro.py
def test_preparar_cadastra_as_24_lojas_do_brasil(conn, cfg):
    assert preparar(conn, cfg) == 24
    ids = [r["loja_id"] for r in conn.execute("select loja_id from hermes.loja order by 1")]
    assert ids[:3] == [5, 11, 51] and ids[-1] == 468

def test_preco_por_faixa_e_contrato(conn, cfg):
    preparar(conn, cfg)
    precos = {r["rental_rate"]: r["preco"] for r in conn.execute(
        "select rental_rate, preco from hermes.preco join hermes.contrato using (contrato_id) where loja_id = 5")}
    assert precos == {Decimal("0.99"): Decimal("19.90"), Decimal("2.99"): Decimal("29.90"), Decimal("4.99"): Decimal("39.90")}
    c = conn.execute("select comissao, custo_pct, vigencia_inicio from hermes.contrato where loja_id = 5").fetchone()
    assert (c["comissao"], c["custo_pct"], str(c["vigencia_inicio"])) == (Decimal("0.3000"), Decimal("0.4000"), "2025-08-01")

def test_sortimento_entre_40_e_120_titulos_e_alvo_2_a_6(conn, cfg):
    preparar(conn, cfg)
    por_loja = conn.execute("select count(*) n, min(estoque_alvo) mi, max(estoque_alvo) ma from hermes.sortimento group by loja_id").fetchall()
    assert all(40 <= r["n"] <= 120 and r["mi"] >= 2 and r["ma"] <= 6 for r in por_loja)

def test_preparar_duas_vezes_nao_duplica_e_da_o_mesmo_sortimento(conn, cfg):
    preparar(conn, cfg); antes = conn.execute("select * from hermes.sortimento order by 1,2").fetchall()
    preparar(conn, cfg); depois = conn.execute("select * from hermes.sortimento order by 1,2").fetchall()
    assert antes == depois

def test_pagila_nao_muda(conn, cfg):
    antes = conn.execute("select count(*) n, max(last_update) u from public.store").fetchone()
    preparar(conn, cfg)
    assert conn.execute("select count(*) n, max(last_update) u from public.store").fetchone() == antes
```

- [ ] **Step 2:** `pytest tests/core/test_sorteio.py tests/services/test_cadastro.py -v` → FAIL.
- [ ] **Step 3:** Escrever `001_schemas.sql` (o conftest passa a aplicá-lo) e `sorteio.py`.
- [ ] **Step 4: Implementar `preparar(conn, cfg) -> int`** em `cadastro.py`. Insere com `ON CONFLICT DO NOTHING`. Para cada loja, com `rng(cfg.semente, "loja", loja_id)`:
  - `formato`: sorteado entre os 4;
  - `mapeamento`: sorteado de um conjunto fixo de apelidos por campo. Ele fica gravado na loja e é o que o simulador escreve e o importador lê. Os campos e os apelidos são:
    - `titulo`: Título / FILME / titulo_filme
    - `vendido`: Qtd vendida / VENDIDOS / qtd_vend
    - `devolvido`: Devolvidos / DEVOL / qtd_dev
    - `estoque_final`: Estoque / SALDO FINAL / estq
    - `preco`: Preço unit. / VALOR UN / preco
  - **sortimento**: de 40 a 120 títulos, sorteados sem repetição com peso pela popularidade (aluguéis por `film_id` em `public.rental`/`inventory`, com piso 1 para os 42 títulos sem aluguel). O estoque-alvo vai de 2 a 6, e quanto mais popular o título, mais perto de 6.
- [ ] **Step 5:** `pytest tests/core/test_sorteio.py tests/services/test_cadastro.py -v` → PASS.
- [ ] **Step 6: Commit** `feat: schemas e cadastro de lojas, contratos e sortimento`

---

### Task 3: Dinheiro e emissão das remessas

**Files:**
- Create: `src/hermes/core/dinheiro.py`, `src/hermes/services/remessa_service.py`, `src/hermes/domain/nota_fiscal.py`, `src/hermes/infra/pdf.py`, `src/hermes/core/meses.py`, `tests/core/test_dinheiro.py`, `tests/services/test_remessa.py`

**Interfaces:**
- Consumes: tabelas da Task 2, `preparar`.
- Produces:
  - `centavos(v: Decimal) -> Decimal` (ROUND_HALF_UP, 2 casas).
  - `@dataclass(frozen=True) Valores: venda, comissao, repasse, custo, lucro` (todos `Decimal`).
  - `valores(vendido: int, preco: Decimal, comissao: Decimal, custo_pct: Decimal) -> Valores`: `venda = centavos(vendido*preco)`, `comissao = centavos(venda*comissao)`, `repasse = venda - comissao`, `custo = centavos(vendido * centavos(preco*custo_pct))`, `lucro = repasse - custo`.
  - `ler_valor(texto: str | int | float | Decimal | None) -> Decimal | None` (usado pela Task 6; `None` para vazio, `ValueError` para texto que não é número).
  - `mes_anterior(mes: str) -> str`, `meses(inicio: str, fim: str) -> list[str]`.
  - `emitir_mes(conn, cfg, mes: str) -> list[int]` (ids das notas). Grava `hermes.nota`, `hermes.nota_item` e um `hermes.mes_loja` com 'aberto'. Gera o espelho em `cfg.pasta_saida/notas/<mes>/nota-<numero>.pdf`.
  - `estoque_inicial(conn, loja_id: int, mes: str) -> dict[int, int]`: o `conferido.saldo.estoque_final` de `mes_anterior(mes)`, ou `{}` no primeiro mês.

- [ ] **Step 1: Testes que falham**:

```python
def test_exemplo_do_desenho():
    v = valores(8, Decimal("29.90"), Decimal("0.30"), Decimal("0.40"))
    assert v == Valores(Decimal("239.20"), Decimal("71.76"), Decimal("167.44"), Decimal("95.68"), Decimal("71.76"))

def test_meses():
    assert meses("2025-08", "2026-07")[0] == "2025-08" and meses("2025-08", "2026-07")[-1] == "2026-07"
    assert len(meses("2025-08", "2026-07")) == 12 and mes_anterior("2026-01") == "2025-12"

def test_primeira_remessa_repoe_ate_o_alvo(conn, cfg):
    preparar(conn, cfg)
    emitir_mes(conn, cfg, "2025-08")
    soma = conn.execute("select sum(quantidade) q from hermes.nota_item").fetchone()["q"]
    assert soma == conn.execute("select sum(estoque_alvo) q from hermes.sortimento").fetchone()["q"]
    n = conn.execute("select emitida_em, valor_total from hermes.nota where loja_id = 5").fetchone()
    assert str(n["emitida_em"]) == "2025-08-01"

def test_emitir_duas_vezes_nao_duplica(conn, cfg):
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08"); emitir_mes(conn, cfg, "2025-08")
    assert conn.execute("select count(*) n from hermes.nota").fetchone()["n"] == 24

def test_emitir_sem_o_mes_anterior_fechado_recusa(conn, cfg):
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08")
    with pytest.raises(ErroHermes, match="2025-08 ainda não foi fechado"):
        emitir_mes(conn, cfg, "2025-09")
    assert conn.execute("select count(*) n from hermes.nota where mes = '2025-09'").fetchone()["n"] == 0

def test_espelho_pdf_diz_ficticia(conn, cfg, tmp_path):
    preparar(conn, cfg); emitir_mes(conn, replace(cfg, pasta_saida=tmp_path), "2025-08")
    pdf = next((tmp_path / "notas" / "2025-08").glob("nota-*.pdf"))
    assert "FICTÍCIA" in pymupdf.open(pdf)[0].get_text()

def test_espelho_pdf_carrega_os_valores_nos_atributos(conn, cfg, tmp_path):
    preparar(conn, cfg); emitir_mes(conn, replace(cfg, pasta_saida=tmp_path), "2025-08")
    pdf = next((tmp_path / "notas" / "2025-08").glob("nota-*.pdf"))
    dados = json.loads(pymupdf.open(pdf).metadata["keywords"])
    nota = conn.execute("select numero, loja_id, valor_total from hermes.nota where numero = %s", (dados["numero"],)).fetchone()
    assert (dados["loja_id"], Decimal(dados["valor_total"])) == (nota["loja_id"], nota["valor_total"])
    assert sum(i["quantidade"] for i in dados["itens"]) == conn.execute(
        "select sum(quantidade) q from hermes.nota_item join hermes.nota using (nota_id) where numero = %s", (dados["numero"],)).fetchone()["q"]
```

- [ ] **Step 2:** `pytest tests/core/test_dinheiro.py tests/services/test_remessa.py -v` → FAIL.
- [ ] **Step 3: Implementar `dinheiro.py`.**
- [ ] **Step 4: Implementar `emitir_mes`.** O primeiro mês é o de `vigencia_inicio` do contrato (2025-08). A data de emissão é o dia 1 no primeiro mês e o dia 11 nos outros. Num mês que não é o primeiro, todas as lojas do mês anterior precisam estar com `situacao` 'fechado' ou 'sem_relatorio'; se não estiverem, levanta `ErroHermes(f"{anterior} ainda não foi fechado: rode hermes fechar {anterior}")`. A quantidade de cada item é `max(0, alvo - estoque_inicial)` e itens com zero não entram. `numero` é o máximo já existente + 1. Tudo numa transação só. Uma loja que já tem nota no mês é pulada.
- [ ] **Step 5: Implementar `nota_pdf.gerar(nota: dict, itens: list[dict], destino: Path) -> Path`** com PyMuPDF (`pymupdf.open()` + `page.insert_htmlbox` ou `insert_text`): o cabeçalho diz "NOTA FISCAL FICTÍCIA — projeto de portfólio, sem valor fiscal", seguido de número, loja, cidade, data e uma tabela de itens com título, quantidade, preço e total. Os mesmos valores vão em JSON nos atributos do PDF (`doc.set_metadata`): `title = "Nota fictícia <numero>"`, `subject = "Hermes — nota fiscal fictícia"`, `keywords = {"numero", "loja_id", "mes", "emitida_em", "valor_total", "itens": [{"film_id", "titulo", "quantidade", "preco_unit"}]}`, com valores em texto (`"29.90"`). Eles servem de gabarito para testar a leitura de PDF, hoje e na fase 2.
- [ ] **Step 6:** `pytest tests/core/test_dinheiro.py tests/services/test_remessa.py -v` → PASS.
- [ ] **Step 7: Commit** `feat: valores do contrato e emissão das remessas`

---

### Task 4: Simulador — o que as lojas fizeram

**Files:**
- Create: `src/hermes/core/modelos.py`, `src/hermes/services/simulador_service.py`, `tests/services/test_simulador.py`

**Interfaces:**
- Consumes: `rng`, `estoque_inicial`, `hermes.nota_item`, `hermes.preco`.
- Produces:
  - `@dataclass LinhaLoja: film_id: int, titulo: str, vendido: int, devolvido: int, estoque_final: int, preco: Decimal`
  - `@dataclass RelatorioLoja: loja_id: int, mes: str, linhas: list[LinhaLoja], repasse: Decimal, recebido_em: date`
  - `simular_vendas(conn, cfg, mes: str) -> list[RelatorioLoja]` — a **verdade**, sem erro nenhum; um por loja com nota no mês.

- [ ] **Step 1: Testes que falham**:

```python
def test_verdade_fecha_a_conta(conn, cfg):
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08")
    for r in simular_vendas(conn, cfg, "2025-08"):
        recebido = {x["film_id"]: x["quantidade"] for x in conn.execute(
            "select film_id, quantidade from hermes.nota_item join hermes.nota using (nota_id) "
            "where loja_id = %s and mes = '2025-08'", (r.loja_id,))}
        for l in r.linhas:
            assert l.vendido + l.devolvido + l.estoque_final == recebido.get(l.film_id, 0)
            assert min(l.vendido, l.devolvido, l.estoque_final) >= 0

def test_repasse_da_verdade_e_o_do_contrato(conn, cfg):
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08")
    r = simular_vendas(conn, cfg, "2025-08")[0]
    assert r.repasse == sum(valores(l.vendido, l.preco, Decimal("0.30"), Decimal("0.40")).repasse for l in r.linhas)
    assert date(2025, 9, 1) <= r.recebido_em <= date(2025, 9, 10)

def test_mesma_semente_mesma_verdade(conn, cfg):
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08")
    assert simular_vendas(conn, cfg, "2025-08") == simular_vendas(conn, cfg, "2025-08")
```

- [ ] **Step 2:** `pytest tests/services/test_simulador.py -v` → FAIL.
- [ ] **Step 3: Implementar `simular_vendas`.** O sorteio usa `rng(cfg.semente, "vendas", loja_id, mes)`. Para cada título do sortimento: `disponivel = estoque_inicial + recebido`. Cada unidade é vendida com probabilidade `p = 0.35 + 0.40 * popularidade_normalizada`. Das que sobram, cada uma é devolvida com probabilidade 0.15, e o resto fica em estoque. `recebido_em` é um dia sorteado entre 1 e 10 do mês seguinte. Títulos com `disponivel == 0` não entram no relatório.
- [ ] **Step 4:** `pytest tests/services/test_simulador.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: simulador de vendas das lojas`

---

### Task 5: Simulador — erros e arquivos

**Files:**
- Create: `src/hermes/services/erros_service.py`, `src/hermes/infra/escritores.py`
- Modify: `tests/services/test_simulador.py`

**Interfaces:**
- Consumes: `RelatorioLoja`, `LinhaLoja`, `hermes.loja.formato/mapeamento`.
- Produces:
  - `@dataclass(frozen=True) ErroInjetado: loja_id: int, mes: str, codigo: str, film_id: int | None`. Os códigos são os da tabela de divergências do desenho.
  - `injetar_erros(relatorios: list[RelatorioLoja], cfg, mes: str, catalogo: dict[int, str]) -> tuple[list[RelatorioLoja], list[ErroInjetado]]`. `catalogo` é o mapa `film_id` → título de todos os filmes, usado para inventar um título não enviado. Para `RELATORIO_FALTANDO`, a loja sai da lista.
  - `escrever_arquivos(conn, relatorios, pasta: Path) -> list[Path]`: um arquivo por loja em `pasta/<mes>/`, mais `pasta/<mes>/_recebidos.csv` (`arquivo;recebido_em`, este com data ISO), que simula o registro dos e-mails.
  - `simular_mes(conn, cfg, mes: str) -> list[ErroInjetado]`: junta simular, injetar e escrever, e grava o gabarito em `cfg.pasta_entrada/<mes>/_gabarito.json`.

- [ ] **Step 1: Testes que falham** (em `tests/services/test_simulador.py`):

```python
def test_taxa_de_erro_perto_de_20_por_cento(conn, cfg):
    # 12 meses × 24 lojas: entre 12% e 28% dos relatórios com algum erro
    ...
def test_cada_codigo_aparece_em_12_meses(conn, cfg): ...  # todos os 8 códigos aparecem ao menos uma vez com a semente padrão
def test_arquivo_tem_codigo_da_loja_e_apelidos_do_mapeamento(conn, cfg, tmp_path):
    # primeira linha de texto de cada arquivo contém f"Loja {loja_id}"; cabeçalho usa os apelidos de hermes.loja.mapeamento
def test_atrasado_tem_recebido_em_depois_do_dia_10(conn, cfg, tmp_path): ...
def test_mesma_semente_mesmos_bytes(conn, cfg, tmp_path):
    # CSV e XLSX idênticos byte a byte em duas execuções (xlsx: fixar created/modified do openpyxl); PDF: mesmo texto extraído
```

- [ ] **Step 2:** `pytest tests/services/test_simulador.py -v` → FAIL.
- [ ] **Step 3: Implementar `injetar_erros`.** O sorteio usa `rng(cfg.semente, "erros", loja_id, mes)`. Cada relatório tem chance `cfg.taxa_erro` de receber **um** erro, escolhido com o mesmo peso entre os 8 códigos. O que cada código faz:
  - `SALDO_NAO_FECHA`: soma ±1 ou ±2 ao `estoque_final` de uma linha.
  - `TITULO_NAO_ENVIADO`: acrescenta uma linha com um título do catálogo que a loja não recebeu.
  - `TITULO_AUSENTE`: tira uma linha que tem `estoque_final > 0`.
  - `REPASSE_DIVERGENTE`: muda o repasse entre R$ 5 e R$ 50.
  - `PRECO_DIVERGENTE`: troca o preço de uma linha pelo de outra faixa.
  - `DUPLICADO`: repete uma linha.
  - `RELATORIO_ATRASADO`: `recebido_em` entre os dias 11 e 20.
  - `RELATORIO_FALTANDO`: tira a loja da lista.
- [ ] **Step 4: Implementar `escrever_arquivos`** (CSV e XLSX por `DataFrame.to_csv` / `to_excel` com `openpyxl`, PDF por PyMuPDF). A primeira linha é `Loja {id} - {cidade} - Relatório {mes}` em todos os formatos. No CSV ela vem antes do cabeçalho; no XLSX fica na A1, com o cabeçalho na linha 3; no PDF é o título da página. Os números saem no formato brasileiro (`39,90`) no CSV com `;` e no PDF, e no americano (`39.90`) no CSV com `,`. A última linha é `Repasse total;<valor>`, ou a célula equivalente no XLSX e no PDF. O nome do arquivo é livre e sorteado entre `relatorio_<mes>_<id>`, `vendas-<id>` e `fechamento <mes> loja <id>`.
- [ ] **Step 5:** `pytest tests/services/test_simulador.py -v` → PASS.
- [ ] **Step 6: Commit** `feat: erros injetados e arquivos das lojas`

---

### Task 6: Leitura e importação (`bruto` → `padronizado`)

**Files:**
- Create: `src/hermes/infra/leitores.py`, `src/hermes/infra/arquivos.py`, `src/hermes/domain/relatorio_loja.py`, `src/hermes/core/normalizacao.py`, `src/hermes/services/importacao_service.py`, `src/hermes/infra/sql/padronizar.sql`, `tests/infra/test_leitores.py`, `tests/services/test_importar.py`

**Interfaces:**
- Consumes: `ler_valor`, `hermes.loja.mapeamento`, os arquivos da Task 5.
- Produces:
  - `@dataclass LeituraArquivo: loja_id: int | None, linhas: list[dict[str, str]], repasse: str | None`. Cada linha é um `dict` com os nomes de coluna **originais** e os valores como texto.
  - `ler_arquivo(caminho: Path) -> LeituraArquivo` (`.csv` com `;` ou `,` detectado, `.xlsx`, `.pdf`; outra extensão levanta `ErroHermes`).
  - `normalizar_titulo(texto: str) -> str` (`upper`, `strip`, espaços colapsados).
  - `@dataclass ResumoImportacao: lidos: int, ignorados_repetidos: int, substituidos: int, com_erro: list[tuple[str, str]]`
  - `importar_mes(conn, cfg, mes: str) -> ResumoImportacao`: grava em `hermes.arquivo` e `bruto.linha` e depois roda `padronizar.sql` com o parâmetro `mes`.

- [ ] **Step 1: Testes que falham**:

```python
@pytest.mark.parametrize("texto,esperado", [("1.234,56","1234.56"),("1234,56","1234.56"),("1,234.56","1234.56"),
    ("R$ 39,90","39.90"),("39.9","39.90"),("  ",None),(None,None),(7,"7")])
def test_ler_valor(texto, esperado):
    assert ler_valor(texto) == (None if esperado is None else Decimal(esperado))

def test_ler_valor_texto_invalido():
    with pytest.raises(ValueError): ler_valor("abc")

def test_le_os_tres_formatos(tmp_path, conn, cfg):  # gera com escrever_arquivos e lê: mesma quantidade de linhas e loja_id certo, para csv, xlsx e pdf
def test_pdf_usa_pdfplumber_quando_pymupdf_falha(tmp_path, conn, cfg, monkeypatch):
    # monkeypatch faz a leitura PyMuPDF devolver 0 linhas: a leitura ainda dá certo e leitura.leitor == "pdfplumber"

def test_pdf_os_dois_falham(tmp_path):  # PDF em branco: ErroHermes citando os dois leitores

def test_extensao_desconhecida(tmp_path):
    (tmp_path / "x.txt").write_text("oi"); 
    with pytest.raises(ErroHermes): ler_arquivo(tmp_path / "x.txt")

def test_importar_duas_vezes_nao_duplica(conn, cfg): # 2ª vez: ignorados_repetidos == lidos da 1ª; count(bruto.linha) igual
def test_arquivo_novo_da_mesma_loja_substitui(conn, cfg):  # altera um arquivo, reimporta: substituidos == 1, só o novo em padronizado
def test_arquivo_ruim_nao_para_o_resto(conn, cfg):
    # pasta com um .xlsx vazio e os 24 normais: com_erro tem 1 item com o nome do arquivo; os outros foram importados;
    # hermes.arquivo do ruim tem erro preenchido
def test_padronizado_tem_numeros_e_titulo_ligado(conn, cfg):
    # depois de importar 2025-08: nenhuma venda com vendido null; film_id preenchido para títulos do catálogo
def test_linha_com_numero_invalido_vira_erro_de_linha(conn, cfg):  # "abc" em vendido: hermes.arquivo.erro cita a linha; as outras linhas entram
```

- [ ] **Step 2:** `pytest tests/infra/test_leitores.py tests/services/test_importar.py -v` → FAIL.
- [ ] **Step 3: Implementar `ler_valor`** em `dinheiro.py`. Tira `R$` e os espaços. Se o texto tem `,` e `.`, o separador decimal é o que aparece por último. Se tem só `,`, ela é o decimal. Se tem só `.`, ele é o decimal.
- [ ] **Step 4: Implementar `ler_arquivo`.** O `loja_id` sai da regex `(?i)loja\D{0,3}(\d+)` aplicada às 5 primeiras linhas de texto. O cabeçalho da tabela é a primeira linha que contém um dos apelidos de `titulo`. A linha de repasse é a que começa com `Repasse`. CSV e XLSX entram com `pandas.read_csv(..., header=None, dtype=str, sep=None, engine="python")` e `pandas.read_excel(..., header=None, dtype=str)`, e o cabeçalho é achado nas linhas lidas. No PDF, `ler_pdf` tenta PyMuPDF (`page.find_tables()`, ou dividir o texto de `get_text()` quando não houver tabela). A leitura **falha** se não achar a loja ou o cabeçalho, se não achar nenhuma linha, ou se alguma linha tiver número de colunas diferente do cabeçalho. Quando falha, tenta `pdfplumber` (`extract_table()` / `extract_text()`) com os mesmos critérios. Se os dois falharem, levanta `ErroHermes` com o motivo de cada um. `LeituraArquivo` ganha `leitor: str`. Sem cabeçalho ou sem loja, levanta `ErroHermes` com o motivo.
- [ ] **Step 5: Implementar `importar_mes`.**
  - Lê `_recebidos.csv` para obter o `recebido_em`; sem ele, usa a data de hoje. Pula os arquivos que começam com `_`.
  - Para cada arquivo, calcula o sha256. Se ele já existe, conta como repetido. Senão, grava `hermes.arquivo`; se a leitura falhar, grava o `erro` e segue para o próximo.
  - Se a loja e o mês já têm um arquivo ativo, marca o anterior como `substituido=true`, apaga o `padronizado` dele e as divergências daquela loja e mês, e volta `mes_loja` para 'aberto'.
  - Grava `bruto.linha`, com o repasse numa linha `numero=0` de conteúdo `{"repasse": ...}`.
  - **`padronizar.sql`**: passa de `bruto` para `padronizado.venda` e `padronizado.repasse`, só dos arquivos ativos do mês, usando o `mapeamento` da loja para escolher as chaves do jsonb. Liga o `film_id` por `normalizar_titulo` igual a `upper(title)`, com uma função SQL `hermes.normalizar(text)` equivalente a `normalizar_titulo`. A conversão de número fica no Python, antes de gravar no `bruto`: o `conteudo` guarda o texto original e mais um `"_valores"` já convertido. Uma linha com número inválido entra em `hermes.arquivo.erro` como `linha N: <campo> inválido` e fica fora de `_valores`.
- [ ] **Step 6:** `pytest tests/infra/test_leitores.py tests/services/test_importar.py -v` → PASS.
- [ ] **Step 7: Commit** `feat: leitura dos relatórios e camadas bruto e padronizado`

---

### Task 7: Conciliação e divergências

**Files:**
- Create: `src/hermes/services/conciliacao_service.py`, `src/hermes/infra/sql/conciliar.sql`, `tests/services/test_conciliar.py`

**Interfaces:**
- Consumes: `padronizado.*`, `hermes.nota_item`, `estoque_inicial`, `hermes.arquivo.recebido_em`.
- Produces:
  - `conferir_mes(conn, cfg, mes: str) -> dict[str, int]` (contagem por código). Grava `conferido.saldo` e `hermes.divergencia`. É idempotente: refaz o saldo e insere divergências com `ON CONFLICT DO NOTHING`, sem mexer nas que já foram decididas.

- [ ] **Step 1: Testes que falham**. O teste central usa o gabarito:

```python
def test_cada_erro_injetado_vira_a_divergencia_certa(conn, cfg, tmp_path):
    cfg = replace(cfg, pasta_entrada=tmp_path, pasta_saida=tmp_path)
    preparar(conn, cfg); emitir_mes(conn, cfg, "2025-08")
    gabarito = simular_mes(conn, cfg, "2025-08"); importar_mes(conn, cfg, "2025-08"); conferir_mes(conn, cfg, "2025-08")
    achadas = {(r["loja_id"], r["codigo"]) for r in conn.execute("select loja_id, codigo from hermes.divergencia")}
    assert {(e.loja_id, e.codigo) for e in gabarito} <= achadas

def test_mes_sem_erro_nao_tem_divergencia(conn, cfg, tmp_path):  # replace(cfg, taxa_erro=Decimal("0")): zero divergências
def test_repasse_tolerancia_um_centavo(conn, cfg, tmp_path):  # repasse declarado = calculado + 0,01: sem REPASSE_DIVERGENTE; + 0,02: com
def test_titulo_escrito_diferente_casa(conn, cfg, tmp_path):  # reescreve um título como "  academy   dinosaur " num CSV: sem TITULO_NAO_ENVIADO
def test_conferir_duas_vezes_nao_duplica_nem_reabre(conn, cfg, tmp_path):
    # decide uma divergência, roda conferir_mes de novo: mesma contagem, e a decidida continua decidida
def test_saldo_usa_o_estoque_do_mes_anterior(conn, cfg, tmp_path):  # após fechar 2025-08 e emitir 2025-09: estoque_inicial de 09 = estoque_final de 08
```

- [ ] **Step 2:** `pytest tests/services/test_conciliar.py -v` → FAIL.
- [ ] **Step 3: Implementar `conciliar.sql`**, com um bloco por código:
  - **Universo:** os títulos da nota do mês, mais os títulos com estoque inicial, mais os títulos declarados pela loja.
  - **`conferido.saldo`:** guarda `estoque_inicial`, `recebido`, o vendido, o devolvido e o `estoque_final_loja` declarados, e o `estoque_final = estoque_inicial + recebido − vendido − devolvido`.
  - **`SALDO_NAO_FECHA`:** quando `estoque_final_loja` é diferente do calculado. `valor_loja` e `valor_calculado` guardam as quantidades.
  - **`TITULO_NAO_ENVIADO`:** linha com `film_id` nulo, ou com um `film_id` sem nota e sem estoque inicial.
  - **`TITULO_AUSENTE`:** título com `estoque_inicial + recebido > 0` que não aparece no relatório. Entra no saldo com vendido 0 e devolvido 0.
  - **`DUPLICADO`:** o mesmo `film_id` mais de uma vez no mesmo arquivo. O saldo usa só a primeira linha até haver decisão.
  - **`PRECO_DIVERGENTE`:** `preco_informado` diferente do `hermes.preco` do contrato.
  - **`REPASSE_DIVERGENTE`:** quando `|declarado − Σ repasse calculado| > 0,01`.
  - **`RELATORIO_ATRASADO`:** `recebido_em` depois do dia 10 do mês seguinte.
  - **`RELATORIO_FALTANDO`:** loja com nota no mês e sem arquivo ativo.
- [ ] **Step 4:** Implementar `conferir_mes`, que roda o SQL com o parâmetro `mes` e devolve as contagens.
- [ ] **Step 5:** `pytest tests/services/test_conciliar.py -v` → PASS.
- [ ] **Step 6: Commit** `feat: conciliação e divergências`

---

### Task 8: Decisões

**Files:**
- Create: `src/hermes/services/decisao_service.py`
- Modify: `tests/services/test_conciliar.py`

**Interfaces:**
- Produces:
  - `decidir(conn, divergencia_id: int, acao: Literal["aceitar","contestar"], motivo: str) -> None`. Divergência inexistente ou já decidida levanta `ErroHermes`.
  - `decidir_automatico(conn, mes: str) -> dict[str, int]` (contagem por `estado`), a regra do `rodar`:
    - **aceita** quando: `RELATORIO_ATRASADO`; `TITULO_AUSENTE`; `SALDO_NAO_FECHA` com diferença de até 1 unidade; `REPASSE_DIVERGENTE` com diferença de até R$ 10;
    - **contesta** o resto. `RELATORIO_FALTANDO` é sempre contestado, e o mês da loja vira 'sem_relatorio' no fechamento.
    - O motivo gravado é `"automático: <regra>"`.

- [ ] **Step 1: Testes que falham**: `test_decidir_grava_estado_motivo_e_data`, `test_decidir_duas_vezes_recusa`, `test_decidir_motivo_vazio_recusa`, `test_automatico_segue_a_regra` (monta uma divergência de cada caso por SQL e confere o estado de cada uma).
- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** `pytest tests/services/test_conciliar.py -v` PASS.
- [ ] **Step 5: Commit** `feat: decisão das divergências`

---

### Task 9: Fechamento e camada `relatorio`

**Files:**
- Create: `src/hermes/services/fechamento_service.py`, `src/hermes/infra/sql/fechar.sql`, `tests/services/test_fechar.py`
- Modify: `src/hermes/infra/sql/001_schemas.sql` (colunas de `relatorio.*`)

**Interfaces:**
- Produces:
  - `relatorio.loja_mes(loja_id, mes, situacao, vendido int, devolvido int, estoque_final int, venda, comissao, repasse, custo, lucro, cobranca_saldo, ajuste_unidades int, PK(loja_id, mes))`
  - `relatorio.titulo_mes(film_id, titulo, categoria, mes, enviado int, vendido int, devolvido int, estoque_lojas int, venda, lucro, PK(film_id, mes))`. A `categoria` é a de menor `category_id` em `public.film_category`.
  - `relatorio.mes(mes PK, lojas_com_relatorio int, lojas_sem_relatorio int, enviado int, vendido int, venda, repasse, custo, lucro, cobranca_saldo, sell_through numeric(5,4))`, onde `sell_through = vendido / (estoque_inicial + enviado)`.
  - `fechar_mes(conn, cfg, mes: str) -> None`.

**O que cada decisão faz** (copiado do desenho):
- **Saldo aceito:** `estoque_final := estoque_final_loja` e `ajuste := estoque_final_loja − calculado`, sem cobrança.
- **Saldo contestado:** `estoque_final` continua o calculado e `cobranca := |estoque_final_loja − calculado| × centavos(preço × custo_pct)`.
- **Repasse ou preço aceito:** vale o valor da loja. Contestado, vale o do contrato. O valor de repasse aceito entra em `relatorio.loja_mes.repasse` no lugar do calculado.
- **Título não enviado:** contestado, a linha sai. Aceito, entra como venda avulsa: vendido e preço do contrato, sem afetar o estoque.
- **Duplicado:** contestado, vale a primeira linha. Aceito, as linhas são somadas.
- **Relatório faltando:** `situacao = 'sem_relatorio'`, sem venda, com o estoque inicial passando igual.

- [ ] **Step 1: Testes que falham**:

```python
def test_fechar_com_divergencia_aberta_recusa_e_nao_grava(conn, cfg, tmp_path):
    with pytest.raises(ErroHermes, match=r"\d+ divergências abertas em 2025-08"): fechar_mes(conn, cfg, "2025-08")
    assert conn.execute("select count(*) n from relatorio.loja_mes").fetchone()["n"] == 0

def test_fechamento_bate_com_valores(conn, cfg, tmp_path):  # taxa 0: para cada loja, relatorio.loja_mes.lucro == Σ valores(...).lucro
def test_saldo_contestado_cobra_a_preco_de_custo(conn, cfg, tmp_path):
    # loja declara estoque 2 a mais de um título de R$ 29,90: contestada -> cobranca_saldo == Decimal("23.92")
def test_saldo_aceito_ajusta_estoque_sem_cobrar(conn, cfg, tmp_path):  # ajuste_unidades == 2, cobranca_saldo == 0, estoque do mês seguinte usa o da loja
def test_sem_relatorio_passa_o_estoque(conn, cfg, tmp_path):  # situacao 'sem_relatorio', vendido 0, estoque_final == estoque_inicial + recebido
def test_fechar_de_novo_refaz_igual(conn, cfg, tmp_path):  # duas vezes: mesmas linhas em relatorio.*
```

- [ ] **Step 2:** FAIL → **Step 3:** implementar `fechar.sql`. Ele aplica as decisões sobre `conferido.saldo` (estoque final, ajuste, cobrança), apaga e grava `relatorio.*` do mês e atualiza `hermes.mes_loja`. O `fechar_mes` faz tudo numa transação só. Com divergência aberta, não grava nada.
- [ ] **Step 4:** `pytest tests/services/test_fechar.py -v` → PASS.
- [ ] **Step 5: Commit** `feat: fechamento do mês e camada relatorio`

---

### Task 10: Linha de comando e `rodar`

**Files:**
- Create: `src/hermes/application/ciclo_app.py`, `src/hermes/interface/cli.py`, `src/hermes/main.py`, `tests/interface/test_cli.py`

**Interfaces:**
- Consumes: todas as funções anteriores.
- Produces: `interface.cli.main(argv: list[str] | None = None) -> int`, com `argparse`, chamando só `application.ciclo_app` (uma função por subcomando, mesmos nomes). Os subcomandos e argumentos são exatamente os do desenho: `preparar`, `emitir MES`, `simular MES`, `importar MES`, `conferir MES`, `divergencias MES`, `decidir ID {aceitar,contestar} MOTIVO`, `fechar MES`, `rodar INICIO FIM`. Há uma opção global `--env CAMINHO` (padrão `.env`). Um `ErroHermes` vira mensagem no stderr e código de saída 1, sem traceback. O `rodar` passa, mês a mês, por `emitir`, `simular`, `importar`, `conferir`, `decidir_automatico` e `fechar`, e imprime uma linha por mês com vendido, venda, lucro e o número de divergências.

- [ ] **Step 1: Testes que falham**:

```python
def test_rodar_12_meses_fecha_tudo(conn, cfg, tmp_path, capsys): 
    # main(["--env", env_do_teste, "rodar", "2025-08", "2026-07"]) == 0; relatorio.mes tem 12 linhas; nenhuma divergência aberta
def test_rodar_duas_vezes_da_o_mesmo_relatorio(...):  # zera schemas, roda de novo: select * from relatorio.mes idêntico
def test_erro_vira_mensagem_sem_traceback(capsys):  # fechar com divergência aberta: código 1, stderr contém "divergências abertas", sem "Traceback"
def test_divergencias_lista_as_abertas(capsys): ...
```

O `env_do_teste` é um `.env` temporário que aponta `PGDATABASE=hermes_teste` e as pastas para o `tmp_path`.

- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** `pytest -v` com a suíte inteira → PASS.
- [ ] **Step 5:** Rodar de verdade no banco `pagila`: `mensagem\Scripts\hermes preparar` e depois `mensagem\Scripts\hermes rodar 2025-08 2026-07`. Esperado: 12 linhas impressas, código 0, e `select * from relatorio.mes` com 12 linhas.
- [ ] **Step 6: Commit** `feat: linha de comando e ciclo completo`

---

### Task 11: README e CI

**Files:**
- Create: `README.md`, `.github/workflows/testes.yml`

- [ ] **Step 1: `testes.yml`.** Roda em `ubuntu-latest`, com serviço `postgres:18` (senha `postgres`). Instala `postgresql-client` e baixa `pagila-schema.sql` e `pagila-data.sql` de `https://raw.githubusercontent.com/devrimgunduz/pagila/master/`. Usa `PAGILA_SQL_DIR`, `HERMES_PSQL=psql` e `PGPASSWORD` pelo ambiente. Depois roda `pip install -e .[dev]` e `pytest -v`. **Atenção:** o Pagila local tem 500 lojas e pagamentos até 2026-07. O teste `test_preparar_cadastra_as_24_lojas_do_brasil` precisa passar com o arquivo baixado. Se a versão do GitHub for diferente, fixar no workflow o commit do Pagila que tem as 500 lojas, ou versionar os dois `.sql` em `tests/dados/`. Decidir isso olhando o resultado do primeiro CI.
- [ ] **Step 2: `README.md`** em português, com estas seções:
  - a história do negócio, em um parágrafo, com o exemplo dos 10 enviados, 2 devolvidos e 8 vendidos;
  - um diagrama mermaid das camadas `hermes`, `bruto`, `padronizado`, `conferido` e `relatorio`;
  - uma tabela de divergências com um exemplo real tirado do `rodar`;
  - como rodar: Postgres com o Pagila, `.env` e os dois comandos;
  - as fases 2 e 3;
  - um aviso de que os dados e as notas são fictícios.
- [ ] **Step 3:** `pytest -v` local → PASS.
- [ ] **Step 4: Commit** `docs: README e CI`
