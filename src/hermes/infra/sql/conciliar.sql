-- Conciliação do mês: conferido.saldo e hermes.divergencia, só das lojas com o mês aberto.
-- Regra central, por loja, título e mês:
--     estoque_inicial + recebido = vendido + devolvido + estoque_final

create temp table _lojas on commit drop as
select m.loja_id, c.comissao
  from hermes.mes_loja m join hermes.contrato c using (loja_id)
 where m.mes = %(mes)s and m.situacao = 'aberto';

-- arquivo ativo de cada loja no mês
create temp table _arquivo on commit drop as
select a.loja_id, a.arquivo_id, a.recebido_em
  from hermes.arquivo a join _lojas using (loja_id)
 where a.mes = %(mes)s and not a.substituido and a.leitor is not null;

-- primeira linha declarada de cada título (a repetida é o DUPLICADO)
create temp table _declarado on commit drop as
select distinct on (v.loja_id, v.film_id) v.*
  from padronizado.venda v join _arquivo a using (arquivo_id)
 where v.film_id is not null
 order by v.loja_id, v.film_id, v.linha;

create temp table _recebido on commit drop as
select n.loja_id, i.film_id, i.quantidade
  from hermes.nota n join hermes.nota_item i using (nota_id) join _lojas using (loja_id)
 where n.mes = %(mes)s;

create temp table _inicial on commit drop as
select s.loja_id, s.film_id, s.estoque_final as quantidade
  from conferido.saldo s join _lojas using (loja_id)
 where s.mes = to_char(to_date(%(mes)s || '-01', 'YYYY-MM-DD') - interval '1 month', 'YYYY-MM')
   and s.estoque_final > 0;

create temp table _preco on commit drop as
select c.loja_id, f.film_id, p.preco
  from hermes.contrato c
  join hermes.preco p using (contrato_id)
  join public.film f on f.rental_rate = p.rental_rate
  join _lojas l on l.loja_id = c.loja_id;

-- saldo: títulos recebidos ou com estoque; o declarado que não está aqui é TITULO_NAO_ENVIADO
delete from conferido.saldo s using _lojas l where s.loja_id = l.loja_id and s.mes = %(mes)s;

insert into conferido.saldo
    (loja_id, mes, film_id, estoque_inicial, recebido, vendido, devolvido,
     estoque_final_loja, estoque_final, preco)
select u.loja_id, %(mes)s, u.film_id,
       coalesce(i.quantidade, 0), coalesce(r.quantidade, 0),
       coalesce(d.vendido, 0), coalesce(d.devolvido, 0),
       d.estoque_final,
       coalesce(i.quantidade, 0) + coalesce(r.quantidade, 0)
           - coalesce(d.vendido, 0) - coalesce(d.devolvido, 0),
       p.preco
  from (select loja_id, film_id from _recebido union select loja_id, film_id from _inicial) u
  left join _recebido r using (loja_id, film_id)
  left join _inicial i using (loja_id, film_id)
  left join _declarado d using (loja_id, film_id)
  join _preco p using (loja_id, film_id);

-- divergências (as já decididas ficam como estão)
insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_loja, valor_calculado)
select loja_id, %(mes)s, film_id, 'SALDO_NAO_FECHA', estoque_final_loja, estoque_final
  from conferido.saldo join _lojas using (loja_id)
 where mes = %(mes)s and estoque_final_loja is not null and estoque_final_loja <> estoque_final
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_calculado)
select s.loja_id, %(mes)s, s.film_id, 'TITULO_AUSENTE', s.estoque_inicial + s.recebido
  from conferido.saldo s join _arquivo a using (loja_id)
 where s.mes = %(mes)s and s.estoque_final_loja is null and s.estoque_inicial + s.recebido > 0
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_loja)
select v.loja_id, %(mes)s, v.film_id, 'TITULO_NAO_ENVIADO', sum(v.vendido)
  from padronizado.venda v join _arquivo a using (arquivo_id)
 where v.film_id is null
    or not exists (select 1 from conferido.saldo s
                    where s.loja_id = v.loja_id and s.mes = %(mes)s and s.film_id = v.film_id)
 group by v.loja_id, v.film_id
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_loja)
select v.loja_id, %(mes)s, v.film_id, 'DUPLICADO', count(*)
  from padronizado.venda v join _arquivo a using (arquivo_id)
 where v.film_id is not null
 group by v.loja_id, v.film_id having count(*) > 1
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, film_id, codigo, valor_loja, valor_calculado)
select d.loja_id, %(mes)s, d.film_id, 'PRECO_DIVERGENTE', d.preco_informado, p.preco
  from _declarado d join _preco p using (loja_id, film_id)
 where d.preco_informado is distinct from p.preco
on conflict do nothing;

-- repasse calculado com o preço do contrato, por linha e arredondado como no Python
insert into hermes.divergencia (loja_id, mes, codigo, valor_loja, valor_calculado)
select x.loja_id, %(mes)s, 'REPASSE_DIVERGENTE', x.declarado, x.calculado
  from (select a.loja_id, r.valor as declarado,
               coalesce(sum(round(d.vendido * p.preco, 2)
                            - round(round(d.vendido * p.preco, 2) * l.comissao, 2)), 0)
                   as calculado
          from _arquivo a
          join _lojas l using (loja_id)
          left join padronizado.repasse r on r.arquivo_id = a.arquivo_id
          left join _declarado d on d.arquivo_id = a.arquivo_id
          left join _preco p on p.loja_id = d.loja_id and p.film_id = d.film_id
         group by a.loja_id, r.valor) x
 where x.declarado is null or abs(x.declarado - x.calculado) > 0.01
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, codigo)
select loja_id, %(mes)s, 'RELATORIO_ATRASADO'
  from _arquivo
 where recebido_em > (to_date(%(mes)s || '-01', 'YYYY-MM-DD') + interval '1 month 9 days')::date
on conflict do nothing;

insert into hermes.divergencia (loja_id, mes, codigo)
select l.loja_id, %(mes)s, 'RELATORIO_FALTANDO'
  from _lojas l
 where not exists (select 1 from _arquivo a where a.loja_id = l.loja_id)
on conflict do nothing;
