-- Applications share message revisions and immutable attempts; no sending is enabled.
begin;
alter table public.client_finder_tasks add column dependency_id uuid references public.client_finder_tasks(id);
alter table public.client_finder_settings
  add column application_daily_limit integer not null default 5 check(application_daily_limit between 1 and 5),
  add column applications_enabled boolean not null default false,
  add column legacy_queue_reconciled_at timestamptz,
  add column application_worker_verified_at timestamptz,
  add column application_policy_verified_at timestamptz;
create table public.client_finder_jobs (
  id uuid primary key default gen_random_uuid(), opportunity_id uuid not null unique references public.client_finder_opportunities(id),
  job_key text not null unique, platform text not null, source_url text not null, title text not null, company text not null,
  description text not null, contact_email text, source_verified_at timestamptz,
  context_version integer not null default 1, questions jsonb not null default '[]', blockers jsonb not null default '[]',
  status text not null default 'new' check(status in ('new','qualified','applied','interview','offer','hired','closed')),
  historical_applied_at timestamptz, outcome_note text, created_at timestamptz not null default now(),updated_at timestamptz not null default now()
);
alter table public.client_finder_messages add column job_id uuid references public.client_finder_jobs(id),
  add column application_payload jsonb, add column purpose text not null default 'email';
alter table public.client_finder_message_revisions add column application_payload jsonb;
alter table public.client_finder_send_attempts add column application_payload jsonb,add column provider_result jsonb;
alter table public.client_finder_messages alter column recipient_email drop not null;
alter table public.client_finder_message_revisions alter column recipient_email drop not null;
alter table public.client_finder_send_attempts alter column recipient_email drop not null;
alter table public.client_finder_messages drop constraint client_finder_messages_observed_need_check;
alter table public.client_finder_messages drop constraint client_finder_message_kind_v2;
alter table public.client_finder_messages add constraint client_finder_message_kind_v3 check (
 (kind='initial' and parent_message_id is null and lead_id is not null and proof_id is not null and deliverable_id is not null and nullif(btrim(observed_need),'') is not null and recipient_email is not null)
 or (kind='followup' and parent_message_id is not null and lead_id is not null and proof_id is not null and deliverable_id is not null and nullif(btrim(observed_need),'') is not null and recipient_email is not null)
 or (kind='reply' and parent_message_id is null and conversation_id is not null and inbound_message_id is not null and context_version is not null and recipient_email is not null)
 or (kind='application' and parent_message_id is null and job_id is not null and context_version is not null and application_payload is not null));
create unique index client_finder_one_application on public.client_finder_messages(job_id) where kind='application';
alter table public.client_finder_send_attempts drop constraint client_finder_send_attempts_send_class_check;
alter table public.client_finder_send_attempts add constraint client_finder_attempt_bucket check(send_class in ('outreach','reply','application'));
create function public.client_finder_application_payload_guard() returns trigger language plpgsql set search_path=pg_catalog as $$ begin
  if new.application_payload is distinct from old.application_payload then raise exception 'application_payload_immutable'; end if;
  return new;
end $$;
create trigger application_attempt_payload before update on public.client_finder_send_attempts for each row execute function public.client_finder_application_payload_guard();

create function public.client_finder_job_upsert(item jsonb,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare j public.client_finder_jobs%rowtype; oid uuid; changed boolean;
begin
  perform public.client_finder_assert_web_owner($2);
  if nullif($1->>'job_key','') is null or nullif(btrim($1->>'description'),'') is null or nullif(btrim($1->>'title'),'') is null then raise exception 'job_evidence_required'; end if;
  perform pg_advisory_xact_lock(hashtextextended($1->>'job_key',881110));
  select * into j from public.client_finder_jobs where job_key=$1->>'job_key' for update;
  if not found then
    insert into public.client_finder_opportunities(title,kind,acquisition_source) values($1->>'title','job',case when $1->>'platform'='onlinejobs' then 'onlinejobs' else 'unknown' end) returning id into oid;
    insert into public.client_finder_jobs(opportunity_id,job_key,platform,source_url,title,company,description,contact_email,source_verified_at,questions,blockers,historical_applied_at,status)
      values(oid,$1->>'job_key',$1->>'platform',$1->>'source_url',$1->>'title',coalesce($1->>'company','Unspecified'),$1->>'description',$1->>'contact_email',
      case when ($1->>'source_confirmed')::boolean then now() end,coalesce($1->'questions','[]'),coalesce($1->'blockers','[]'),($1->>'applied_at')::timestamptz,
      case when $1->>'applied_at' is not null then 'applied' else 'new' end) returning * into j;
  else
    changed:=row(j.title,j.company,j.description,j.questions,j.contact_email,j.blockers) is distinct from row($1->>'title',coalesce($1->>'company',j.company),$1->>'description',coalesce($1->'questions','[]'),$1->>'contact_email',coalesce($1->'blockers','[]'));
    update public.client_finder_jobs set description=$1->>'description',title=$1->>'title',company=coalesce($1->>'company',company),
      questions=coalesce($1->'questions','[]'),blockers=coalesce($1->'blockers','[]'),contact_email=$1->>'contact_email',
      context_version=context_version+case when changed then 1 else 0 end,updated_at=now(),
      source_verified_at=case when ($1->>'source_confirmed')::boolean then now() else source_verified_at end,
      historical_applied_at=coalesce(historical_applied_at,($1->>'applied_at')::timestamptz),
      status=case when $1->>'applied_at' is not null and status in ('new','qualified') then 'applied' else status end
      where id=j.id returning * into j;
  end if;
  if j.status in ('new','qualified') then
    insert into public.client_finder_tasks(dedup_key,opportunity_id,agent,task_type,title,context_version)
      values('job-qualify:'||j.id||':'||j.context_version,j.opportunity_id,'Eleven','qualify_job','Qualify: '||j.title,j.context_version),
      ('job-draft:'||j.id||':'||j.context_version,j.opportunity_id,'Steve','cover_letter','Prepare cover letter: '||j.title,j.context_version) on conflict do nothing;
    update public.client_finder_tasks set dependency_id=(select id from public.client_finder_tasks where dedup_key='job-qualify:'||j.id||':'||j.context_version)
      where dedup_key='job-draft:'||j.id||':'||j.context_version;
  end if;
  return to_jsonb(j);
end $$;

create function public.client_finder_invalidate_job() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
  if new.context_version<>old.context_version or new.status<>old.status and new.status not in ('new','qualified') then
    update public.client_finder_send_attempts a set status='canceled',result_note='job_context_changed'
      from public.client_finder_messages m where a.message_id=m.id and m.job_id=new.id and a.status='claimed';
    update public.client_finder_messages set status='draft',approved_at=null,approved_revision=null,approved_via=null,telegram_card_id=null,telegram_card_revision=null
      where job_id=new.id and status in ('draft','pending_review','claimed','edit_requested');
    update public.client_finder_tasks set status='dismissed',blocker='Job changed; use current context' where opportunity_id=new.opportunity_id and context_version<new.context_version and task_type in ('qualify_job','cover_letter') and status in ('pending','running','blocked','review');
  end if;
  return new;
end $$;
create trigger job_context_changed after update on public.client_finder_jobs for each row execute function public.client_finder_invalidate_job();
create function public.client_finder_application_context_changed() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
  if new.latest_inbound_id is distinct from old.latest_inbound_id and new.opportunity_id is not null then
    update public.client_finder_jobs set context_version=context_version+1 where opportunity_id=new.opportunity_id;
  end if;
  return new;
end $$;
create trigger application_new_correspondence after update on public.client_finder_conversations for each row execute function public.client_finder_application_context_changed();

create function public.client_finder_application_block(message_id uuid,delivery boolean default false)
returns text language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; j public.client_finder_jobs%rowtype; s public.client_finder_settings%rowtype; a jsonb; r public.client_finder_resources%rowtype; q jsonb;
begin
  select * into m from public.client_finder_messages where id=$1;
  select * into j from public.client_finder_jobs where id=m.job_id;
  select * into s from public.client_finder_settings where id=1;
  if m.kind is distinct from 'application' or j.id is null then return 'application_required'; end if;
  if j.source_verified_at is null then return 'verify_job_source'; end if;
  if j.context_version is distinct from m.context_version then return 'stale_job_context'; end if;
  if j.status not in ('new','qualified') or j.historical_applied_at is not null then return 'already_applied_or_closed'; end if;
  if jsonb_array_length(j.blockers)>0 then return 'job_information_missing'; end if;
  if exists(select 1 from public.client_finder_conversations where opportunity_id=j.opportunity_id and (suppressed or bounced)) then return 'contact_blocked'; end if;
  if j.contact_email is not null and (exists(select 1 from public.client_finder_suppressions where (scope='email' and value=j.contact_email) or (scope='domain' and value=split_part(j.contact_email,'@',2)))
    or exists(select 1 from public.cold_leads where lower(contact_email)=j.contact_email and status in ('bounced','unsubscribed'))) then return 'contact_suppressed'; end if;
  for q in select value from jsonb_array_elements(j.questions) loop
    if not exists(select 1 from jsonb_array_elements(m.application_payload->'answers') x where x->>'question'=q#>>'{}' and nullif(btrim(x->>'answer'),'') is not null) then return 'screening_answer_missing'; end if;
  end loop;
  for a in select value from jsonb_array_elements(m.application_payload->'resources') loop
    select * into r from public.client_finder_resources where id=(a->>'id')::uuid and active and verified_at is not null;
    if not found or r.version is distinct from a->>'version' or r.url is distinct from a->>'url' then return 'resource_changed_or_unverified'; end if;
  end loop;
  if not exists(select 1 from jsonb_array_elements(m.application_payload->'resources') x join public.client_finder_resources resource on resource.id=(x->>'id')::uuid where resource.kind='profile') then return 'reviewed_profile_required'; end if;
  if $2 then
    if not s.applications_enabled or s.legacy_queue_reconciled_at is null or s.application_policy_verified_at is null then return 'application_cutover_required'; end if;
    if m.application_payload->>'delivery'='onlinejobs' and (s.application_worker_verified_at is null or not exists(select 1 from public.client_finder_connections where provider='onlinejobs' and enabled and identity='armageddonvivas@gmail.com' and verified_at>now()-interval '1 day')) then return 'personal_application_worker_unverified'; end if;
  end if;
  return null;
end $$;

create function public.client_finder_application_save(job_id uuid,expected_revision integer,subject text,body text,payload jsonb,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare j public.client_finder_jobs%rowtype; m public.client_finder_messages%rowtype; p jsonb;
begin
  perform public.client_finder_assert_web_owner($6);
  select * into j from public.client_finder_jobs where id=$1 for update;
  if not found then raise exception 'job_missing'; end if;
  if j.status not in ('new','qualified') then raise exception 'job_not_open'; end if;
  if nullif(btrim($3),'') is null or length($3)>998 or $3 ~ E'[\\r\\n]' or nullif(btrim($4),'') is null or length($4)>20000 then raise exception 'invalid_application'; end if;
  if jsonb_typeof($5->'answers') is distinct from 'array' or jsonb_typeof($5->'resources') is distinct from 'array' or ($5->>'apply_points')::integer is distinct from 1 or coalesce($5->>'delivery','') not in ('onlinejobs','manual') then raise exception 'invalid_application_payload'; end if;
  if $5->>'delivery'='onlinejobs' and j.platform<>'onlinejobs' then raise exception 'unsupported_submission_platform'; end if;
  p:=$5||jsonb_build_object('job_url',j.source_url,'job_key',j.job_key,'job_context_version',j.context_version);
  select * into m from public.client_finder_messages where client_finder_messages.job_id=$1 for update;
  if coalesce(m.revision,0) is distinct from $2 then raise exception 'stale_revision'; end if;
  if m.status in ('claimed','sending','send_unknown','sent') then raise exception 'application_already_reserved'; end if;
  if m.id is null then
    insert into public.client_finder_messages(kind,job_id,context_version,recipient_email,subject,body,evidence,status,application_payload,purpose)
      values('application',j.id,j.context_version,j.contact_email,$3,$4,jsonb_build_object('job_url',j.source_url),'pending_review',p,'cover_letter') returning * into m;
  else
    update public.client_finder_messages set revision=revision+1,context_version=j.context_version,subject=$3,body=$4,application_payload=p,
      status='pending_review',approved_revision=null,approved_at=null,approved_via=null,telegram_card_id=null,telegram_card_revision=null,updated_at=now()
      where id=m.id returning * into m;
  end if;
  insert into public.client_finder_message_revisions(message_id,revision,recipient_email,subject,body,evidence,application_payload)
    values(m.id,m.revision,m.recipient_email,m.subject,m.body,m.evidence,m.application_payload);
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($6::text,'save_application',m.id,jsonb_build_object('revision',m.revision));
  return to_jsonb(m)||jsonb_build_object('blocker',public.client_finder_application_block(m.id));
end $$;

create function public.client_finder_application_approve(message_id uuid,revision integer,via text,actor text,
  telegram_user_id bigint default null,telegram_chat_id bigint default null,telegram_card_id bigint default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; a public.client_finder_send_attempts%rowtype; reason text; today date:=(now() at time zone 'Asia/Manila')::date; jid uuid;
begin
  if $3='web' then perform public.client_finder_assert_web_owner($4::uuid);
  elsif $3='telegram' then perform public.client_finder_assert_owner($5,$6); else raise exception 'owner_required'; end if;
  select job_id into jid from public.client_finder_messages where id=$1;
  perform 1 from public.client_finder_jobs where id=jid for update;
  select * into m from public.client_finder_messages where id=$1 for update;
  if m.kind is distinct from 'application' or m.status<>'pending_review' or m.revision is distinct from $2 then raise exception 'stale_approval'; end if;
  if $3='telegram' and (m.telegram_card_id is distinct from $7 or m.telegram_card_revision is distinct from $2 or m.telegram_owner_user_id is distinct from $5 or m.telegram_chat_id is distinct from $6) then raise exception 'stale_card'; end if;
  reason:=public.client_finder_application_block(m.id,true);
  if reason is not null then raise exception '%',reason; end if;
  perform pg_advisory_xact_lock(881104,today-date '2000-01-01');
  if (select count(*) from public.client_finder_send_attempts where attempt_day=today and send_class='application') >= (select application_daily_limit from public.client_finder_settings where id=1) then raise exception 'application_daily_limit'; end if;
  insert into public.client_finder_send_attempts(message_id,revision,attempt_day,recipient_email,subject,body,status,send_class,application_payload)
    values(m.id,m.revision,today,m.recipient_email,m.subject,m.body,'claimed','application',m.application_payload) returning * into a;
  update public.client_finder_messages set status='claimed',approved_revision=$2,approved_at=now(),approved_via=$3 where id=m.id;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($4,'approve_application',m.id,jsonb_build_object('revision',$2,'via',$3));
  return to_jsonb(a);
end $$;

create function public.client_finder_application_begin(attempt_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; a public.client_finder_send_attempts%rowtype; reason text; jid uuid; mid uuid;
begin
  select message_id into mid from public.client_finder_send_attempts where id=$1;
  select job_id into jid from public.client_finder_messages where id=mid;
  perform 1 from public.client_finder_jobs where id=jid for update;
  select * into m from public.client_finder_messages where id=mid for update;
  select * into a from public.client_finder_send_attempts where id=$1 for update;
  if not found or a.send_class<>'application' or a.status<>'claimed' or m.status<>'claimed' or m.approved_revision is distinct from a.revision then raise exception 'attempt_unavailable'; end if;
  reason:=public.client_finder_application_block(m.id,true);
  if a.attempt_day<>(now() at time zone 'Asia/Manila')::date then reason:='approval_expired'; end if;
  if reason is not null then
    update public.client_finder_send_attempts set status='canceled',result_note=reason where id=a.id;
    update public.client_finder_messages set status='skipped',approved_revision=null,approved_at=null where id=m.id;
    return null;
  end if;
  update public.client_finder_send_attempts set status='sending',started_at=now() where id=a.id returning * into a;
  update public.client_finder_messages set status='sending' where id=m.id;
  return to_jsonb(a);
end $$;

create function public.client_finder_application_result(attempt_id uuid,result jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype; jid uuid; confirmed boolean;
begin
  select * into a from public.client_finder_send_attempts where id=$1 for update;
  if not found or a.send_class<>'application' or a.status not in ('sending','send_unknown') then raise exception 'attempt_not_reconcilable'; end if;
  confirmed:=($2->>'confirmed')::boolean is true and nullif($2->>'reference','') is not null and $2->>'job_key'=a.application_payload->>'job_key';
  update public.client_finder_send_attempts set status=case when confirmed then 'sent' else 'send_unknown' end,provider_result=$2,
    sent_at=case when confirmed then now() end,unknown_at=case when not confirmed then now() end where id=a.id returning * into a;
  update public.client_finder_messages set status=a.status,sent_at=a.sent_at where id=a.message_id returning job_id into jid;
  if confirmed then update public.client_finder_jobs set status='applied',updated_at=now() where id=jid; end if;
  return to_jsonb(a);
end $$;

create function public.client_finder_job_stage(job_id uuid,status text,note text,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare j public.client_finder_jobs%rowtype;
begin
  perform public.client_finder_assert_web_owner($4);
  if $2 not in ('new','qualified','interview','offer','hired','closed') then raise exception 'invalid_job_stage'; end if;
  if $2 in ('hired','closed') and nullif(btrim($3),'') is null then raise exception 'outcome_evidence_required'; end if;
  update public.client_finder_jobs set status=$2,outcome_note=$3,updated_at=now() where id=$1 returning * into j;
  if not found then raise exception 'job_missing'; end if;
  if $2='hired' then perform public.client_finder_set_stage(j.opportunity_id,'won',$3,$4); end if;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($4::text,'job_stage',j.id,jsonb_build_object('status',$2,'note',$3));
  return to_jsonb(j);
end $$;

create function public.client_finder_application_card(message_id uuid,revision integer,action text,card_id bigint,owner_user_id bigint,chat_id bigint)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype;
begin
  perform public.client_finder_assert_owner($5,$6);
  select * into m from public.client_finder_messages where id=$1 for update;
  if not found or m.kind<>'application' or m.status<>'pending_review' or m.revision is distinct from $2 then raise exception 'stale_application_card'; end if;
  if $3='bind' then
    update public.client_finder_messages set telegram_card_id=$4,telegram_card_revision=$2,telegram_owner_user_id=$5,telegram_chat_id=$6 where id=m.id;
  elsif $3 in ('edit','skip') and m.telegram_card_id=$4 and m.telegram_card_revision=$2 and m.telegram_owner_user_id=$5 and m.telegram_chat_id=$6 then
    update public.client_finder_messages set status=case when $3='edit' then 'edit_requested' else 'skipped' end,telegram_card_id=null,telegram_card_revision=null,approved_at=null,approved_revision=null where id=m.id;
  else raise exception 'invalid_application_card'; end if;
end $$;

-- Legacy outreach consumers must never reserve an application as cold email.
do $$ declare d text; f record; begin
  for f in select oid from pg_proc where pronamespace='public'::regnamespace and proname in ('_client_finder_claim_send','_client_finder_begin_send') loop
    d:=pg_get_functiondef(f.oid);
    d:=replace(d,'m.kind = ''reply''','m.kind in (''reply'',''application'')');
    execute d;
  end loop;
end $$;
alter table public.client_finder_jobs enable row level security;
revoke all on public.client_finder_jobs from public,anon,authenticated,service_role;
grant select on public.client_finder_jobs to service_role;
do $$ declare f record; begin
  for f in select oid::regprocedure signature,proname from pg_proc where pronamespace='public'::regnamespace and proname in
    ('client_finder_job_upsert','client_finder_invalidate_job','client_finder_application_context_changed','client_finder_application_block','client_finder_application_save','client_finder_application_approve','client_finder_application_begin','client_finder_application_result','client_finder_job_stage','client_finder_application_card','client_finder_application_payload_guard') loop
    execute format('revoke all on function %s from public,anon,authenticated,service_role',f.signature);
    if f.proname not in ('client_finder_invalidate_job','client_finder_application_context_changed','client_finder_application_payload_guard') then execute format('grant execute on function %s to service_role',f.signature); end if;
  end loop;
end $$;
commit;
