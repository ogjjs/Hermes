-- bruto -> padronizado, só dos arquivos ativos do mês (lidos e não substituídos).
-- Os números já chegam convertidos em conteudo->'_valores' (feito no Python, que registra
-- a linha inválida em hermes.arquivo.erro e a deixa fora de _valores).

delete from padronizado.venda where mes = %(mes)s;
delete from padronizado.repasse where mes = %(mes)s;

insert into padronizado.venda
    (arquivo_id, loja_id, mes, linha, film_id, titulo_informado,
     vendido, devolvido, estoque_final, preco_informado)
select b.arquivo_id, a.loja_id, a.mes, b.numero, f.film_id,
       b.conteudo -> '_valores' ->> 'titulo',
       (b.conteudo -> '_valores' ->> 'vendido')::int,
       (b.conteudo -> '_valores' ->> 'devolvido')::int,
       (b.conteudo -> '_valores' ->> 'estoque_final')::int,
       (b.conteudo -> '_valores' ->> 'preco')::numeric(10,2)
  from bruto.linha b
  join hermes.arquivo a using (arquivo_id)
  left join public.film f
         on hermes.normalizar(f.title) = hermes.normalizar(b.conteudo -> '_valores' ->> 'titulo')
 where a.mes = %(mes)s and not a.substituido and a.leitor is not null
   and b.numero > 0
   and b.conteudo -> '_valores' ?& array['vendido', 'devolvido', 'estoque_final'];

insert into padronizado.repasse (arquivo_id, loja_id, mes, valor)
select b.arquivo_id, a.loja_id, a.mes, (b.conteudo -> '_valores' ->> 'repasse')::numeric(12,2)
  from bruto.linha b
  join hermes.arquivo a using (arquivo_id)
 where a.mes = %(mes)s and not a.substituido and a.leitor is not null
   and b.numero = 0;
