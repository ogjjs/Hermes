-- Fechamento do mês: aplica as decisões em conferido.saldo e grava a camada relatorio.
-- Tudo é recalculado a partir de padronizado, saldo e divergências: fechar de novo dá igual.

create temp table _decisao on commit drop as
select loja_id, film_id, codigo, estado
  from hermes.divergencia
 where mes = %(mes)s and estado <> 'aberta';

create temp table _ativo on commit drop as
select a.loja_id, a.arquivo_id
  from hermes.arquivo a
 where a.mes = %(mes)s and not a.substituido and a.leitor is not null;

-- Vale a primeira linha de cada título, decidido ou não o DUPLICADO: somar linhas repetidas
-- somaria estoque, que é posição e não movimento (a decisão fica só como registro)
create temp table _declarado on commit drop as
select distinct on (v.loja_id, v.film_id)
       v.loja_id, v.film_id, v.vendido, v.devolvido, v.estoque_final, v.preco_informado
  from padronizado.venda v
  join _ativo a using (arquivo_id)
 where v.film_id is not null
 order by v.loja_id, v.film_id, v.linha;

update conferido.saldo s
   set vendido = d.vendido, devolvido = d.devolvido, estoque_final_loja = d.estoque_final
  from _declarado d
 where s.mes = %(mes)s and s.loja_id = d.loja_id and s.film_id = d.film_id;

-- Saldo: aceito vale o estoque da loja (ajuste, sem cobrança); contestado vale o calculado e
-- a diferença é cobrada a preço de custo. Primeiro volta tudo ao calculado.
update conferido.saldo s
   set estoque_final = s.estoque_inicial + s.recebido - s.vendido - s.devolvido,
       ajuste = 0,
       cobranca = 0
 where s.mes = %(mes)s;

update conferido.saldo s
   set estoque_final = case when d.estado = 'aceita' then s.estoque_final_loja
                            else s.estoque_final end,
       ajuste = case when d.estado = 'aceita' then s.estoque_final_loja - s.estoque_final
                     else 0 end,
       cobranca = case when d.estado = 'contestada'
                       then abs(s.estoque_final_loja - s.estoque_final)
                            * round(s.preco * c.custo_pct, 2)
                       else 0 end
  from _decisao d, hermes.contrato_do_mes(%(mes)s) c
 where s.mes = %(mes)s and d.codigo = 'SALDO_NAO_FECHA'
   and d.loja_id = s.loja_id and d.film_id = s.film_id and c.loja_id = s.loja_id
   and s.estoque_final_loja is not null;

-- Linhas de venda do mês: as do saldo e as avulsas (título não enviado, aceito)
create temp table _linha on commit drop as
select s.loja_id, s.film_id, s.vendido, s.devolvido, s.estoque_final, s.estoque_inicial,
       s.recebido, s.cobranca, s.ajuste,
       case when p.estado = 'aceita' then coalesce(d.preco_informado, s.preco)
            else s.preco end as preco_venda,
       s.preco as preco_contrato
  from conferido.saldo s
  left join _declarado d using (loja_id, film_id)
  left join _decisao p on p.loja_id = s.loja_id and p.film_id = s.film_id
                      and p.codigo = 'PRECO_DIVERGENTE'
 where s.mes = %(mes)s
union all
select d.loja_id, d.film_id, d.vendido, 0, 0, 0, 0, 0, 0, pr.preco, pr.preco
  from _declarado d
  join _decisao n on n.loja_id = d.loja_id and n.film_id = d.film_id
                 and n.codigo = 'TITULO_NAO_ENVIADO' and n.estado = 'aceita'
  join hermes.contrato_do_mes(%(mes)s) c on c.loja_id = d.loja_id
  join hermes.preco pr on pr.contrato_id = c.contrato_id
  join public.film f on f.film_id = d.film_id and f.rental_rate = pr.rental_rate
 where not exists (select 1 from conferido.saldo s
                    where s.mes = %(mes)s and s.loja_id = d.loja_id and s.film_id = d.film_id);

create temp table _valor on commit drop as
select l.*,
       round(l.vendido * l.preco_venda, 2) as venda,
       round(round(l.vendido * l.preco_venda, 2) * c.comissao, 2) as comissao,
       l.vendido * round(l.preco_contrato * c.custo_pct, 2) as custo
  from _linha l join hermes.contrato_do_mes(%(mes)s) c using (loja_id);

delete from relatorio.loja_mes where mes = %(mes)s;
insert into relatorio.loja_mes
    (loja_id, mes, situacao, vendido, devolvido, estoque_final, venda, comissao, repasse,
     custo, lucro, cobranca_saldo, ajuste_unidades)
select m.loja_id, %(mes)s,
       case when exists (select 1 from _decisao f where f.loja_id = m.loja_id
                          and f.codigo = 'RELATORIO_FALTANDO') then 'sem_relatorio'
            else 'fechado' end,
       coalesce(sum(v.vendido), 0), coalesce(sum(v.devolvido), 0),
       coalesce(sum(v.estoque_final), 0),
       coalesce(sum(v.venda), 0), coalesce(sum(v.comissao), 0),
       coalesce(case when r.estado = 'aceita' then max(pr.valor) end,
                sum(v.venda) - sum(v.comissao), 0),
       coalesce(sum(v.custo), 0), 0,
       coalesce(sum(v.cobranca), 0), coalesce(sum(v.ajuste), 0)
  from hermes.mes_loja m
  left join _valor v on v.loja_id = m.loja_id
  left join _decisao r on r.loja_id = m.loja_id and r.codigo = 'REPASSE_DIVERGENTE'
  left join padronizado.repasse pr on pr.loja_id = m.loja_id and pr.mes = %(mes)s
 where m.mes = %(mes)s
 group by m.loja_id, r.estado;

-- repasse aceito diferente do calculado: a diferença fica à parte, para o lucro por título
-- (venda - comissão - custo) mais os ajustes somar o lucro das lojas (repasse - custo)
update relatorio.loja_mes
   set lucro = repasse - custo, ajuste_repasse = repasse - (venda - comissao)
 where mes = %(mes)s;

delete from relatorio.titulo_mes where mes = %(mes)s;
insert into relatorio.titulo_mes
select v.film_id, f.title,
       (select c.name from public.film_category fc join public.category c using (category_id)
         where fc.film_id = v.film_id order by fc.category_id limit 1),
       %(mes)s, sum(v.recebido), sum(v.vendido), sum(v.devolvido), sum(v.estoque_final),
       sum(v.venda), sum(v.venda - v.comissao - v.custo)
  from _valor v join public.film f using (film_id)
 group by v.film_id, f.title;

delete from relatorio.mes where mes = %(mes)s;
insert into relatorio.mes
    (mes, lojas_com_relatorio, lojas_sem_relatorio, enviado, vendido, venda, repasse, custo,
     lucro, cobranca_saldo, sell_through, ajuste_repasse)
select %(mes)s,
       count(*) filter (where l.situacao = 'fechado'),
       count(*) filter (where l.situacao = 'sem_relatorio'),
       (select coalesce(sum(recebido), 0) from _valor),
       sum(l.vendido), sum(l.venda), sum(l.repasse), sum(l.custo), sum(l.lucro),
       sum(l.cobranca_saldo),
       round(sum(l.vendido)::numeric
             / nullif((select sum(estoque_inicial + recebido) from _valor), 0), 4),
       sum(l.ajuste_repasse)
  from relatorio.loja_mes l
 where l.mes = %(mes)s;

update hermes.mes_loja m
   set situacao = l.situacao
  from relatorio.loja_mes l
 where l.loja_id = m.loja_id and l.mes = m.mes and m.mes = %(mes)s;
