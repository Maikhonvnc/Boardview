-- Boardview na nuvem. Cole inteiro no SQL Editor do Supabase e rode (pode rodar de novo).
-- Ninguem escreve direto nas tabelas: so pelas funcoes abaixo, que conferem o dado e
-- poem o nome de quem esta logado. Quem nao esta em "tecnico" com ativo=true nao ve nada,
-- mesmo que consiga criar uma conta.
begin;

create table if not exists public.tecnico (
  id uuid primary key references auth.users(id) on delete cascade,
  nome text not null unique check (char_length(nome) between 1 and 40),
  ativo boolean not null default true,
  criado_em timestamptz not null default now()
);
create table if not exists public.placa_versao (
  placa text not null, fp text not null, n_malhas int not null,
  alvos text[] not null, atual boolean not null default true,
  primary key (placa, fp)
);
create table if not exists public.leitura (
  seq bigint generated always as identity primary key,
  uuid uuid not null unique,
  evento text not null check (evento in ('medida','retira')),
  placa text not null, fp text not null, alvo text not null,
  tipo text not null check (tipo in ('tensao','diodo')),
  papel text not null check (papel in ('ref','reparo')),
  valor text, valor_num double precision, categoria text,
  alimentacao text, momento text, os text,
  tecnico text not null, criado_em text not null,
  recebido_em text not null default to_char(now() at time zone 'utc','YYYY-MM-DD"T"HH24:MI:SS'),
  formato int not null default 1, cancela uuid, usuario uuid
);
create index if not exists leitura_placa on public.leitura(placa);
create table if not exists public.anotacao (
  placa text not null, secao text not null check (secao in ('tipos','nomes','malhas','sugestoes')),
  chave text not null, valor jsonb,                    -- null = apagado
  usuario uuid, em timestamptz not null default now(),
  primary key (placa, secao, chave)
);
create table if not exists public.anotacao_historico (
  id bigint generated always as identity primary key,
  placa text not null, secao text not null, chave text not null,
  valor jsonb, usuario uuid, em timestamptz not null default now()
);
create table if not exists public.ajuste (
  id bigint generated always as identity primary key,
  placa text not null, dados jsonb not null, usuario uuid, em timestamptz not null default now()
);
create index if not exists ajuste_placa on public.ajuste(placa, id desc);

alter table public.tecnico enable row level security;
alter table public.placa_versao enable row level security;
alter table public.leitura enable row level security;
alter table public.anotacao enable row level security;
alter table public.anotacao_historico enable row level security;
alter table public.ajuste enable row level security;
-- sem policy nenhuma = ninguem (anon/authenticated) le nem escreve direto
revoke all on public.tecnico, public.placa_versao, public.leitura, public.anotacao,
  public.anotacao_historico, public.ajuste from anon, authenticated;
grant select, insert, update on public.tecnico, public.placa_versao, public.leitura,
  public.anotacao, public.anotacao_historico, public.ajuste to service_role;

create or replace function public.bv_tecnico() returns text
language sql stable security definer set search_path = '' as $$
  select t.nome from public.tecnico t where t.id = auth.uid() and t.ativo
$$;

create or replace function public.bv_exigir() returns text
language plpgsql stable security definer set search_path = '' as $$
declare n text := public.bv_tecnico();
begin
  if n is null then raise exception 'acesso desativado' using errcode = '42501'; end if;
  return n;
end $$;

create or replace function public.bv_arquivo(p_placa text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform public.bv_exigir();
  return (select jsonb_build_object('placa', placa, 'fp', fp, 'n_malhas', n_malhas)
          from public.placa_versao where placa = p_placa and atual limit 1);
end $$;

create or replace function public.bv_leituras(p_placa text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform public.bv_exigir();
  return coalesce((select jsonb_agg(to_jsonb(l) - 'usuario' order by l.seq desc)
                   from public.leitura l where l.placa = p_placa), '[]'::jsonb);
end $$;

-- Cada leitura e julgada sozinha (mesmas regras do medicoes_db.validar). Erro do DADO
-- vira rejeitada; qualquer outro erro derruba a chamada e o navegador tenta de novo.
create or replace function public.bv_inserir(p_leituras jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_nome text := public.bv_exigir();
  d jsonb; v_aceitas jsonb := '[]'; v_rejeitadas jsonb := '[]';
  m text; v text; num double precision; cat text; alv text[];
  ev text; tp text; pp text;
  re_uuid constant text := '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$';
begin
  if jsonb_typeof(p_leituras) is distinct from 'array' then
    raise exception 'lote invalido' using errcode = '22023';
  end if;
  if jsonb_array_length(p_leituras) not between 1 and 200 then
    raise exception 'lote invalido' using errcode = '22023';
  end if;
  for d in select value from jsonb_array_elements(p_leituras) loop
    m := null; v := null; num := null; cat := null; alv := null;
    ev := coalesce(d->>'evento','medida'); tp := d->>'tipo'; pp := d->>'papel';
    if coalesce(d->>'uuid','') !~ re_uuid then m := 'uuid invalido';
    elsif ev not in ('medida','retira') then m := 'evento invalido';
    elsif tp is null or tp not in ('tensao','diodo') then m := 'tipo invalido';
    elsif pp is null or pp not in ('ref','reparo') then m := 'papel invalido';
    elsif coalesce(d->>'os','') <> '' and d->>'os' !~ '^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,29}$' then m := 'OS invalida';
    elsif coalesce(d->>'criado_em','') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.Z+-]{5,20}$' then m := 'criado_em invalido';
    elsif tp = 'tensao' and coalesce(d->>'alimentacao','') not in ('fonte','bateria') then m := 'alimentacao invalida';
    elsif tp = 'tensao' and coalesce(d->>'momento','') not in ('estavel','boot') then m := 'momento invalido';
    end if;
    if m is null then
      select pv.alvos into alv from public.placa_versao pv where pv.placa = d->>'placa' and pv.fp = d->>'fp';
      if alv is null then m := 'placa ou versao desconhecida';
      elsif d->>'alvo' is null or not (d->>'alvo' = any(alv)) then m := 'alvo nao existe nesta placa';
      end if;
    end if;
    if m is null and ev = 'medida' then
      v := upper(replace(btrim(coalesce(d->>'valor','')), ',', '.'));
      if tp = 'diodo' and v = 'OL' then cat := 'OL';
      elsif v ~ '^-?[0-9]{1,3}([.][0-9]{1,6})?$' or v ~ '^-?0*[0-9]{1,3}([.][0-9]{1,6})?$' and char_length(v) <= 14 then
        num := v::double precision; cat := 'num';
        v := case when num = trunc(num) then num::text || '.0' else num::text end;
        if tp = 'diodo' and num < 0 then m := 'diodo negativo'; end if;
      else m := 'valor invalido';
      end if;
    elsif m is null then
      if coalesce(d->>'cancela','') !~ re_uuid then m := 'retira sem a medida que ele cancela';
      elsif not exists (select 1 from public.leitura l where l.uuid = (d->>'cancela')::uuid
          and l.evento = 'medida' and l.placa = d->>'placa' and l.fp = d->>'fp'
          and l.alvo = d->>'alvo' and l.tipo = tp and l.papel = pp) then
        m := 'retira aponta para medida que nao existe nesta placa/malha';
      end if;
    end if;
    if m is not null then
      v_rejeitadas := v_rejeitadas || jsonb_build_array(jsonb_build_object('uuid', d->>'uuid', 'motivo', m));
    else
      insert into public.leitura (uuid,evento,placa,fp,alvo,tipo,papel,valor,valor_num,categoria,
          alimentacao,momento,os,tecnico,criado_em,cancela,usuario)
      values ((d->>'uuid')::uuid, ev, d->>'placa', d->>'fp', d->>'alvo', tp, pp, v, num, cat,
          case when tp='tensao' then d->>'alimentacao' end, case when tp='tensao' then d->>'momento' end,
          nullif(d->>'os',''), v_nome, d->>'criado_em',
          case when ev='retira' then (d->>'cancela')::uuid end, auth.uid())
      on conflict (uuid) do nothing;
      v_aceitas := v_aceitas || jsonb_build_array(d->>'uuid');
    end if;
  end loop;
  return jsonb_build_object('aceitas', v_aceitas, 'rejeitadas', v_rejeitadas);
end $$;

create or replace function public.bv_anotacoes(p_placa text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform public.bv_exigir();
  return jsonb_build_object('tipos','{}'::jsonb,'nomes','{}'::jsonb,'malhas','{}'::jsonb,'sugestoes','{}'::jsonb)
    || coalesce((select jsonb_object_agg(s.secao, s.o) from (
         select a.secao, jsonb_object_agg(a.chave, a.valor) o from public.anotacao a
         where a.placa = p_placa and a.valor is not null group by a.secao) s), '{}'::jsonb);
end $$;

create or replace function public.bv_gravar_anotacoes(p_placa text, p_mudancas jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_nome text := public.bv_exigir(); r record; s text; k text; val jsonb; ok boolean;
  n int := 0; rec jsonb := '[]';
begin
  if not exists (select 1 from public.placa_versao where placa = p_placa) then
    raise exception 'placa desconhecida' using errcode = '22023'; end if;
  if jsonb_typeof(p_mudancas) is distinct from 'array' then
    raise exception 'lote invalido' using errcode = '22023'; end if;
  if jsonb_array_length(p_mudancas) > 20000 then
    raise exception 'lote invalido' using errcode = '22023'; end if;
  for r in select value, ordinality - 1 as i from jsonb_array_elements(p_mudancas) with ordinality loop
    ok := false;
    if jsonb_typeof(r.value) = 'array' then
      ok := jsonb_array_length(r.value) = 3
        and jsonb_typeof(r.value->0) = 'string' and jsonb_typeof(r.value->1) = 'string';
    end if;
    if ok then
      s := r.value->>0; k := r.value->>1; val := nullif(r.value->2, 'null'::jsonb);
      ok := s in ('tipos','nomes','malhas','sugestoes') and k ~ '^[A-Za-z0-9_.+-]{1,60}$';
      if ok and val is not null then
        if s = 'tipos' then
          ok := jsonb_typeof(val) = 'object';
          if ok then
            ok := coalesce(val->>'t','') in
                ('cap','res','ind','xtal','diodo','trans','mosfet','ci','con','chave','pad','vazio')
              and coalesce(jsonb_typeof(val->'v'),'null') in ('string','null')
              and coalesce(jsonb_typeof(val->'em'),'null') in ('string','null')
              and char_length(coalesce(val->>'v','')) <= 20 and char_length(coalesce(val->>'em','')) <= 30
              and (val - 't' - 'v' - 'por' - 'em') = '{}'::jsonb
              and coalesce(val->>'v','') !~ '[[:cntrl:]]';
            val := val || jsonb_build_object('por', v_nome);
          end if;
        elsif s = 'sugestoes' then ok := false;      -- o viewer so apaga sugestao
        else
          ok := jsonb_typeof(val) = 'string' and char_length(val #>> '{}') between 1 and 60
                and (val #>> '{}') !~ '[[:cntrl:]]';
        end if;
      end if;
    end if;
    if coalesce(ok, false) then
      insert into public.anotacao_historico (placa,secao,chave,valor,usuario) values (p_placa,s,k,val,auth.uid());
      insert into public.anotacao as a (placa,secao,chave,valor,usuario) values (p_placa,s,k,val,auth.uid())
        on conflict (placa,secao,chave) do update set valor = excluded.valor, usuario = excluded.usuario, em = now();
      n := n + 1;
    else
      rec := rec || jsonb_build_array(jsonb_build_object('i', r.i, 'motivo', 'mudanca invalida'));
    end if;
  end loop;
  return jsonb_build_object('ok', true, 'gravadas', n, 'recusadas', rec);
end $$;

create or replace function public.bv_ajuste(p_placa text) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
begin
  perform public.bv_exigir();
  return (select dados from public.ajuste where placa = p_placa order by id desc limit 1);
end $$;

create or replace function public.bv_gravar_ajuste(p_placa text, p_dados jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  perform public.bv_exigir();
  if not exists (select 1 from public.placa_versao where placa = p_placa)
     or jsonb_typeof(p_dados) is distinct from 'object' or length(p_dados::text) > 200000 then
    raise exception 'ajuste invalido' using errcode = '22023'; end if;
  insert into public.ajuste (placa,dados,usuario) values (p_placa,p_dados,auth.uid());
  return jsonb_build_object('ok', true);
end $$;

revoke execute on function public.bv_tecnico(), public.bv_exigir(), public.bv_arquivo(text),
  public.bv_leituras(text), public.bv_inserir(jsonb), public.bv_anotacoes(text),
  public.bv_gravar_anotacoes(text,jsonb), public.bv_ajuste(text), public.bv_gravar_ajuste(text,jsonb)
  from public, anon, authenticated;
grant execute on function public.bv_tecnico(), public.bv_arquivo(text),
  public.bv_leituras(text), public.bv_inserir(jsonb), public.bv_anotacoes(text),
  public.bv_gravar_anotacoes(text,jsonb), public.bv_ajuste(text), public.bv_gravar_ajuste(text,jsonb)
  to authenticated;

-- arquivos das placas: bucket PRIVADO, leitura so para tecnico ativo, envio so pela chave secreta
insert into storage.buckets (id, name, public) values ('placas','placas',false)
  on conflict (id) do update set public = false;
drop policy if exists bv_ler_placas on storage.objects;
create policy bv_ler_placas on storage.objects for select to authenticated
  using (bucket_id = 'placas' and (select public.bv_tecnico()) is not null);

commit;
notify pgrst, 'reload schema';
