-- Schemas e tabelas do Hermes. O Pagila (public) é só lido, nunca alterado.

create schema if not exists hermes;
create schema if not exists bruto;
create schema if not exists padronizado;
create schema if not exists conferido;
create schema if not exists relatorio;

-- Mesmo critério de hermes.core.normalizacao.normalizar_titulo
create or replace function hermes.normalizar(texto text) returns text
language sql immutable as $$
    select upper(btrim(regexp_replace(coalesce(texto, ''), '\s+', ' ', 'g')))
$$;

create table if not exists hermes.loja (
    loja_id     int primary key,            -- = public.store.store_id
    cidade      text not null,
    formato     text not null check (formato in ('csv_ponto_virgula', 'csv_virgula', 'xlsx', 'pdf')),
    mapeamento  jsonb not null
);

create table if not exists hermes.contrato (
    contrato_id     serial primary key,
    loja_id         int not null references hermes.loja,
    vigencia_inicio date not null,
    vigencia_fim    date,
    comissao        numeric(5,4) not null,
    custo_pct       numeric(5,4) not null,
    unique (loja_id, vigencia_inicio)
);

create table if not exists hermes.preco (
    contrato_id int not null references hermes.contrato,
    rental_rate numeric(4,2) not null,
    preco       numeric(10,2) not null,
    primary key (contrato_id, rental_rate)
);

create table if not exists hermes.sortimento (
    loja_id      int not null references hermes.loja,
    film_id      int not null,
    estoque_alvo int not null check (estoque_alvo > 0),
    primary key (loja_id, film_id)
);

create table if not exists hermes.nota (
    nota_id     serial primary key,
    numero      int not null unique,
    loja_id     int not null references hermes.loja,
    mes         char(7) not null,
    emitida_em  date not null,
    valor_total numeric(12,2) not null,
    unique (loja_id, mes)
);

create table if not exists hermes.nota_item (
    nota_id    int not null references hermes.nota,
    film_id    int not null,
    quantidade int not null check (quantidade > 0),
    preco_unit numeric(10,2) not null,
    primary key (nota_id, film_id)
);

create table if not exists hermes.arquivo (
    arquivo_id  serial primary key,
    loja_id     int,
    mes         char(7) not null,
    nome        text not null,
    sha256      char(64) not null unique,
    recebido_em date,
    substituido bool not null default false,
    erro        text,
    leitor      text check (leitor in ('pandas', 'pymupdf', 'pdfplumber'))
);

create table if not exists hermes.divergencia (
    divergencia_id  serial primary key,
    loja_id         int not null,
    mes             char(7) not null,
    film_id         int,
    codigo          text not null,
    valor_loja      numeric(12,2),
    valor_calculado numeric(12,2),
    estado          text not null default 'aberta' check (estado in ('aberta', 'aceita', 'contestada')),
    motivo          text,
    decidida_em     timestamptz,
    unique nulls not distinct (loja_id, mes, film_id, codigo)
);

create table if not exists hermes.mes_loja (
    loja_id  int not null references hermes.loja,
    mes      char(7) not null,
    situacao text not null check (situacao in ('aberto', 'fechado', 'sem_relatorio')),
    primary key (loja_id, mes)
);

create table if not exists bruto.linha (
    arquivo_id int not null references hermes.arquivo,
    numero     int not null,
    conteudo   jsonb not null,
    primary key (arquivo_id, numero)
);

create table if not exists padronizado.venda (
    arquivo_id       int not null references hermes.arquivo,
    loja_id          int not null,
    mes              char(7) not null,
    linha            int not null,
    film_id          int,
    titulo_informado text,
    vendido          int,
    devolvido        int,
    estoque_final    int,
    preco_informado  numeric(10,2)
);

create table if not exists padronizado.repasse (
    arquivo_id int not null references hermes.arquivo,
    loja_id    int not null,
    mes        char(7) not null,
    valor      numeric(12,2),
    primary key (loja_id, mes)
);

create table if not exists conferido.saldo (
    loja_id            int not null,
    mes                char(7) not null,
    film_id            int not null,
    estoque_inicial    int not null,
    recebido           int not null,
    vendido            int not null,
    devolvido          int not null,
    estoque_final_loja int,
    estoque_final      int not null,
    preco              numeric(10,2) not null,
    cobranca           numeric(12,2) not null default 0,
    ajuste             int not null default 0,
    primary key (loja_id, mes, film_id)
);

-- Camada que o Power BI lê (fase 3): fechamento por loja, por título e geral, por mês.
create table if not exists relatorio.loja_mes (
    loja_id         int not null,
    mes             char(7) not null,
    situacao        text not null,
    vendido         int not null,
    devolvido       int not null,
    estoque_final   int not null,
    venda           numeric(12,2) not null,
    comissao        numeric(12,2) not null,
    repasse         numeric(12,2) not null,
    custo           numeric(12,2) not null,
    lucro           numeric(12,2) not null,
    cobranca_saldo  numeric(12,2) not null,
    ajuste_unidades int not null,
    primary key (loja_id, mes)
);

create table if not exists relatorio.titulo_mes (
    film_id       int not null,
    titulo        text not null,
    categoria     text,
    mes           char(7) not null,
    enviado       int not null,
    vendido       int not null,
    devolvido     int not null,
    estoque_lojas int not null,
    venda         numeric(12,2) not null,
    lucro         numeric(12,2) not null,
    primary key (film_id, mes)
);

create table if not exists relatorio.mes (
    mes                 char(7) primary key,
    lojas_com_relatorio int not null,
    lojas_sem_relatorio int not null,
    enviado             int not null,
    vendido             int not null,
    venda               numeric(12,2) not null,
    repasse             numeric(12,2) not null,
    custo               numeric(12,2) not null,
    lucro               numeric(12,2) not null,
    cobranca_saldo      numeric(12,2) not null,
    sell_through        numeric(5,4)
);
