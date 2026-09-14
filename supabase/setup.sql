-- Run once in your project's SQL Editor. Safe to rerun; existing banks are preserved.
begin;
create table if not exists public.sat_cloud_banks (
  owner_id uuid not null references auth.users(id) on delete cascade,
  bank_id text not null check (bank_id ~ '^[a-zA-Z0-9_-]{1,80}$'),
  state jsonb not null,
  questions jsonb not null check (jsonb_typeof(questions) = 'array'),
  content_hash text not null check (content_hash ~ '^[a-f0-9]{64}$'),
  revision bigint not null default 1 check (revision > 0),
  updated_at timestamptz not null default now(),
  primary key (owner_id, bank_id)
);
alter table public.sat_cloud_banks enable row level security;
revoke all on public.sat_cloud_banks from anon, authenticated;
grant select on public.sat_cloud_banks to authenticated;
drop policy if exists sat_read_own_banks on public.sat_cloud_banks;
create policy sat_read_own_banks on public.sat_cloud_banks
  for select to authenticated using ((select auth.uid()) = owner_id);

-- Writes go through this compare-and-swap function, never a blind replacement.
-- The owner comes from the verified session, not a client-supplied user ID.
create or replace function public.sat_put_bank(
  p_bank_id text, p_expected_revision bigint, p_state jsonb,
  p_content_hash text, p_questions jsonb default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  caller uuid := auth.uid();
  current_row public.sat_cloud_banks%rowtype;
  next_revision bigint;
begin
  if caller is null then raise exception 'Sign in to sync' using errcode = '42501'; end if;
  if p_bank_id is null or p_bank_id !~ '^[a-zA-Z0-9_-]{1,80}$'
     or p_expected_revision is null or p_expected_revision < 0
     or p_content_hash is null or p_content_hash !~ '^[a-f0-9]{64}$'
     or p_state is null or p_state->>'format' is distinct from 'sat-bank'
     or p_state->>'version' is distinct from '1'
     or p_state->'bank'->>'id' is distinct from p_bank_id
     or jsonb_typeof(p_state->'attempts') is distinct from 'array'
     or jsonb_typeof(p_state->'notes') is distinct from 'array'
     or jsonb_typeof(p_state->'ratings') is distinct from 'array'
     or jsonb_typeof(p_state->'reviews') is distinct from 'array'
     or jsonb_typeof(p_state->'tags') is distinct from 'array'
     or p_state ? 'questions'
     or octet_length(p_state::text) > 20000000
     or (p_questions is not null and (jsonb_typeof(p_questions) <> 'array' or octet_length(p_questions::text) > 20000000))
  then raise exception 'Invalid bank snapshot'; end if;

  -- Also serializes simultaneous first uploads, when no row exists yet.
  perform pg_advisory_xact_lock(hashtextextended(caller::text || ':' || p_bank_id, 0));
  select * into current_row from public.sat_cloud_banks
    where owner_id = caller and bank_id = p_bank_id for update;
  if not found then
    if p_expected_revision <> 0 then return jsonb_build_object('accepted',false,'revision',0); end if;
    if p_questions is null then raise exception 'Question content required for a new bank'; end if;
    insert into public.sat_cloud_banks(owner_id,bank_id,state,questions,content_hash)
      values(caller,p_bank_id,p_state,p_questions,p_content_hash);
    return jsonb_build_object('accepted',true,'revision',1);
  end if;
  if current_row.revision <> p_expected_revision then
    return jsonb_build_object('accepted',false,'revision',current_row.revision);
  end if;
  if p_questions is null and p_content_hash <> current_row.content_hash then
    raise exception 'Changed question content required';
  end if;
  if current_row.state = p_state and current_row.content_hash = p_content_hash
     and (p_questions is null or current_row.questions = p_questions) then
    return jsonb_build_object('accepted',true,'revision',current_row.revision);
  end if;
  next_revision := current_row.revision + 1;
  update public.sat_cloud_banks set state=p_state,
    questions=coalesce(p_questions,current_row.questions),content_hash=p_content_hash,
    revision=next_revision,updated_at=now()
    where owner_id=caller and bank_id=p_bank_id;
  return jsonb_build_object('accepted',true,'revision',next_revision);
end;
$$;
revoke all on function public.sat_put_bank(text,bigint,jsonb,text,jsonb) from public,anon;
grant execute on function public.sat_put_bank(text,bigint,jsonb,text,jsonb) to authenticated;
notify pgrst, 'reload schema';
commit;
