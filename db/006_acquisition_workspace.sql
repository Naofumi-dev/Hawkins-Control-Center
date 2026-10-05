-- Additive acquisition records. No credentials, workflow activation, or outbound enablement.
begin;
create table public.client_finder_connections (
  provider text primary key check (provider in ('google','notion','n8n','telegram','onlinejobs','calcom','fathom','ghl','loom')),
  identity text, status text not null default 'setup_required', selected jsonb not null default '{}',
  enabled boolean not null default false, verified_at timestamptz, last_success_at timestamptz,
  error_code text, checkpoint jsonb not null default '{}', lease_id uuid, lease_until timestamptz,
  updated_at timestamptz not null default now()
);
insert into public.client_finder_connections(provider) select unnest(array['google','notion','n8n','telegram','onlinejobs','calcom','fathom','ghl','loom']);
create table public.client_finder_resources (
  id uuid primary key default gen_random_uuid(), provider text not null,
  external_id text not null, kind text not null check (kind in ('resume','proof','profile','proposal','sheet','notion','calendar','pipeline')),
  title text not null, url text, version text not null, content text not null default '',
  verified_at timestamptz, active boolean not null default true, metadata jsonb not null default '{}',
  unique(provider,external_id)
);
create table public.client_finder_workflows (
  id text primary key, name text not null, purpose text not null, schedule text,
  active boolean, observed_at timestamptz, last_success_at timestamptz, last_error text,
  paused boolean not null default false, migrated boolean not null default false
);
insert into public.client_finder_workflows(id,name,purpose,schedule) values
 ('V0xHCzfFMgKR61yh','Dustin · OnlineJobs','Job discovery','Legacy schedule: 22:00; verify in n8n'),
 ('hwEDWc0F9Wam1MgB','Eleven + Steve · Score & Draft','Job qualification and cover letters','Legacy schedule: every 15 minutes'),
 ('x10lpGeWihYhpunW','Hopper · Jobs API','Legacy job review and history','On request'),
 ('TaSrrFcWgr0W0Yd7','Client Finder · Discovery','Research US agencies','08:00 Asia/Manila after activation'),
 ('2PLgsImvFAGw0JTf','Client Finder · Review & Send','Exact revision review','Owner approval'),
 ('VMx5m5ADmApXlkjU','Client Finder · Inbox Monitor','Replies and suppression','Verify hosted schedule'),
 ('G2EyMqtsewhrQJAG','Client Finder · Follow-ups','Prepare eligible follow-ups','Verify hosted schedule'),
 ('saO2Ns7Qp604kcvm','Hawkins · Prepare Proposals','Cal.com and Fathom into proposals','Booking and meeting events');
create table public.client_finder_workflow_runs (
  id uuid primary key default gen_random_uuid(), workflow_id text not null references public.client_finder_workflows(id),
  external_id text not null, status text not null, started_at timestamptz, finished_at timestamptz,
  unique(workflow_id,external_id)
);
create table public.client_finder_import_batches (
  id uuid primary key default gen_random_uuid(), provider text not null, resource_id text not null,
  digest text not null, records jsonb not null, summary jsonb not null,
  status text not null default 'preview' check (status in ('preview','committed')),
  created_by uuid not null, created_at timestamptz not null default now(), committed_at timestamptz,
  unique(provider,resource_id,digest)
);
create table public.client_finder_history (
  id uuid primary key default gen_random_uuid(), provider text not null, resource_id text not null, external_id text not null,
  kind text not null, original jsonb not null, opportunity_id uuid references public.client_finder_opportunities(id),
  imported_at timestamptz not null default now(), unique(provider,resource_id,external_id)
);
create table public.client_finder_operations (
  id uuid primary key default gen_random_uuid(), request_id uuid not null unique,
  kind text not null check (kind in ('discover','inbox_sync','agent_run','integrations_sync','ghl_mirror')),
  payload jsonb not null default '{}', status text not null default 'pending' check (status in ('pending','running','complete','blocked','needs_checking','dismissed')),
  actor uuid not null, result jsonb, error_code text, lease_id uuid, lease_until timestamptz,
  created_at timestamptz not null default now(), finished_at timestamptz
);
create table public.client_finder_meetings (
  id uuid primary key default gen_random_uuid(), provider text not null, external_id text not null,
  correlation_key text, title text not null, starts_at timestamptz, status text not null,
  summary text not null default '', action_items jsonb not null default '[]',
  opportunity_id uuid references public.client_finder_opportunities(id), version text not null,
  updated_at timestamptz not null default now(), unique(provider,external_id)
);
create table public.client_finder_crm_links (
  opportunity_id uuid primary key references public.client_finder_opportunities(id),
  remote_id text not null unique, remote_stage text not null, location_id text not null, pipeline_id text not null,
  conflict jsonb, checked_at timestamptz not null default now()
);

create function public.client_finder_acquisition_action(operation text, item jsonb, actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare r jsonb; batch public.client_finder_import_batches%rowtype; rec jsonb; oid uuid; hid uuid; resource public.client_finder_resources%rowtype; existing_job record;
begin
  perform public.client_finder_assert_web_owner($3);
  if jsonb_typeof($2)<>'object' then raise exception 'object_required'; end if;
  if $1='select_connection' then
    if not exists(select 1 from public.client_finder_connections where provider=$2->>'provider') then raise exception 'unknown_provider'; end if;
    update public.client_finder_connections set selected=$2->'selected',verified_at=null,identity=null,status='setup_required',
      enabled=false,checkpoint='{}',error_code=null,updated_at=now() where provider=$2->>'provider';
    r:=jsonb_build_object('status','selection_saved');
  elsif $1='resource' then
    if coalesce($2->>'content','')='' and $2->>'kind'='profile' then raise exception 'profile_facts_required'; end if;
    if ($2->>'reviewed')::boolean is distinct from true then raise exception 'review_resource_first'; end if;
    insert into public.client_finder_resources(provider,external_id,kind,title,url,version,content,verified_at,metadata)
      values($2->>'provider',$2->>'external_id',$2->>'kind',$2->>'title',$2->>'url',$2->>'version',coalesce($2->>'content',''),now(),coalesce($2->'metadata','{}'))
      on conflict(provider,external_id) do update set kind=excluded.kind,title=excluded.title,url=excluded.url,
        version=excluded.version,content=excluded.content,verified_at=now(),active=true,metadata=excluded.metadata returning * into resource;
    r:=to_jsonb(resource);
    if resource.kind='proof' then
      insert into public.client_finder_proofs(id,title,proof_url,proof_kind,claim_text,active,verified_at)
        values('resource-'||resource.id,resource.title,resource.url,coalesce(resource.metadata->>'proof_kind','prototype'),resource.content,true,now())
        on conflict(id) do update set title=excluded.title,proof_url=excluded.proof_url,claim_text=excluded.claim_text,active=true,verified_at=now();
    end if;
  elsif $1='import_preview' then
    if jsonb_array_length($2->'records') not between 1 and 100 then raise exception 'import_batch_limit'; end if;
    insert into public.client_finder_import_batches(provider,resource_id,digest,records,summary,created_by)
      values($2->>'provider',$2->>'resource_id',$2->>'digest',$2->'records',$2->'summary',$3)
      on conflict(provider,resource_id,digest) do update set digest=excluded.digest returning * into batch;
    r:=to_jsonb(batch);
  elsif $1='import_commit' then
    select * into batch from public.client_finder_import_batches where id=($2->>'batch_id')::uuid for update;
    if not found then raise exception 'preview_required'; end if;
    if batch.status='committed' then return to_jsonb(batch); end if;
    if $2->>'digest' is distinct from batch.digest then raise exception 'stale_import_preview'; end if;
    if jsonb_array_length(batch.summary->'conflicts')>0 then raise exception 'import_conflicts_require_review'; end if;
    for rec in select value from jsonb_array_elements(batch.records) loop
      hid:=null; oid:=null;
      if exists(select 1 from public.client_finder_history where provider=batch.provider and resource_id=batch.resource_id and external_id=rec->>'external_id' and original<>rec) then raise exception 'import_changed_since_preview'; end if;
      insert into public.client_finder_history(provider,resource_id,external_id,kind,original)
        values(batch.provider,batch.resource_id,rec->>'external_id',rec->>'kind',rec)
        on conflict do nothing returning id into hid;
      if hid is null then continue; end if;
      if rec->>'kind'='job' then
        perform pg_advisory_xact_lock(hashtextextended(rec->>'job_key',881110));
        select * into existing_job from public.client_finder_jobs where job_key=rec->>'job_key' for update;
        if found then
          -- Preserve current work; a different tracker is archived, never a replacement draft.
          oid:=existing_job.opportunity_id;
          if rec->>'applied_at' is not null and existing_job.historical_applied_at is null then
            update public.client_finder_jobs set historical_applied_at=(rec->>'applied_at')::timestamptz,
              status=case when status in ('new','qualified') then 'applied' else status end,
              context_version=context_version+1,updated_at=now() where id=existing_job.id;
          elsif jsonb_array_length(coalesce(rec->'blockers','[]'))>0 then
            update public.client_finder_jobs set blockers=(select jsonb_agg(distinct value) from jsonb_array_elements(blockers||(rec->'blockers'))),
              context_version=context_version+1,updated_at=now() where id=existing_job.id;
          end if;
        else
          r:=public.client_finder_job_upsert(rec||'{"source_confirmed":false}'::jsonb,$3);
          oid:=(r->>'opportunity_id')::uuid;
        end if;
      elsif rec->>'kind'='client' then
        -- Match only an exact known lead. Ambiguous names never merge histories.
        select o.id into oid from public.client_finder_opportunities o where o.lead_id=(rec->>'lead_id')::uuid limit 1;
        if oid is null then
          insert into public.client_finder_opportunities(title,kind,acquisition_source,lead_id)
            values(rec->>'title','client','unknown',(rec->>'lead_id')::uuid) returning id into oid;
        end if;
      else raise exception 'invalid_history_kind'; end if;
      update public.client_finder_history set opportunity_id=oid where id=hid;
      if rec->>'suppressed_email' is not null then
        insert into public.client_finder_suppressions(scope,value,reason,source)
          values('email',rec->>'suppressed_email','Imported do-not-contact history',$3::text) on conflict do nothing;
      end if;
    end loop;
    update public.client_finder_import_batches set status='committed',committed_at=now() where id=batch.id returning * into batch;
    r:=to_jsonb(batch);
  elsif $1='queue' then
    if $2->>'kind' not in ('discover','inbox_sync','agent_run','integrations_sync') then raise exception 'unsupported_operation'; end if;
    insert into public.client_finder_operations(request_id,kind,actor) values(($2->>'request_id')::uuid,$2->>'kind',$3)
      on conflict(request_id) do nothing;
    select to_jsonb(o) into r from public.client_finder_operations o where request_id=($2->>'request_id')::uuid;
  elsif $1='operation_action' then
    if $2->>'action' not in ('retry','dismiss') then raise exception 'invalid_operation_action'; end if;
    update public.client_finder_operations set status=case when $2->>'action'='retry' then 'pending' else 'dismissed' end,
      error_code=null,finished_at=null where id=($2->>'id')::uuid and status='blocked' and kind<>'ghl_mirror' returning to_jsonb(client_finder_operations) into r;
    if r is null then raise exception 'operation_not_retryable'; end if;
  elsif $1='pause' then
    update public.client_finder_connections set enabled=false,status='paused',updated_at=now() where provider=$2->>'provider';
    r:=jsonb_build_object('status','paused');
  elsif $1='link_meeting' then
    if exists(select 1 from public.client_finder_meetings where id=($2->>'meeting_id')::uuid and opportunity_id is not null and opportunity_id<>($2->>'opportunity_id')::uuid) then raise exception 'meeting_already_linked'; end if;
    update public.client_finder_meetings set opportunity_id=($2->>'opportunity_id')::uuid where id=($2->>'meeting_id')::uuid returning to_jsonb(client_finder_meetings) into r;
    if r is null then raise exception 'meeting_missing'; end if;
    insert into public.client_finder_tasks(dedup_key,opportunity_id,agent,task_type,title)
      values('meeting:'||($2->>'meeting_id')||':'||(r->>'version'),($2->>'opportunity_id')::uuid,'Steve','meeting_proposal','Prepare a proposal from the selected call') on conflict do nothing;
  else raise exception 'unsupported_acquisition_action'; end if;
  insert into public.client_finder_owner_actions(actor,action,details) values($3::text,'acquisition_'||$1,jsonb_build_object('id',coalesce(r->>'id',$2->>'id'),'provider',$2->>'provider'));
  return r;
end $$;

create function public.client_finder_integration_record(operation text,item jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_connections%rowtype; r jsonb; w jsonb; oid uuid;
begin
  if $1='claim' then
    select * into c from public.client_finder_connections where provider=$2->>'provider' for update;
    if not found then raise exception 'connection_missing'; end if;
    if c.status='paused' then raise exception 'connection_paused'; end if;
    if c.lease_until>now() then raise exception 'integration_busy'; end if;
    update public.client_finder_connections set lease_id=gen_random_uuid(),lease_until=now()+interval '10 minutes' where provider=c.provider returning * into c;
    return to_jsonb(c);
  end if;
  select * into c from public.client_finder_connections where provider=$2->>'provider' for update;
  if not found or c.status='paused' or c.lease_id is null or c.lease_until is null or c.lease_id is distinct from ($2->>'lease_id')::uuid or c.lease_until<=now() then raise exception 'stale_integration_lease'; end if;
  if $1='failure' then
    update public.client_finder_connections set status='needs_attention',error_code=$2->>'error_code',lease_id=null,lease_until=null,updated_at=now() where provider=c.provider;
    return jsonb_build_object('status','needs_attention');
  end if;
  if c.provider='google' and $2->>'identity' is distinct from 'armageddonvivas@gmail.com' then raise exception 'wrong_personal_account'; end if;
  if $1='complete' then
    update public.client_finder_connections set identity=$2->>'identity',status='verified',enabled=true,verified_at=now(),last_success_at=now(),error_code=null,
      checkpoint=coalesce($2->'checkpoint',checkpoint),lease_id=null,lease_until=null,updated_at=now() where provider=c.provider;
  elsif $1='workflow' then
    update public.client_finder_workflows set active=($2->>'active')::boolean,observed_at=now() where id=$2->>'id';
    for w in select value from jsonb_array_elements(coalesce($2->'runs','[]')) loop
      insert into public.client_finder_workflow_runs(workflow_id,external_id,status,started_at,finished_at)
        values($2->>'id',w->>'id',w->>'status',(w->>'started_at')::timestamptz,(w->>'finished_at')::timestamptz)
        on conflict(workflow_id,external_id) do update set status=excluded.status,finished_at=excluded.finished_at;
    end loop;
    update public.client_finder_workflows set last_success_at=(select max(finished_at) from public.client_finder_workflow_runs where workflow_id=$2->>'id' and status='success'),
      last_error=(select status from public.client_finder_workflow_runs where workflow_id=$2->>'id' and status in ('error','crashed') order by started_at desc limit 1) where id=$2->>'id';
  elsif $1='resource_version' then
    update public.client_finder_resources set verified_at=null,active=not coalesce(($2->>'trashed')::boolean,false),
      metadata=metadata||jsonb_build_object('observed_provider_version',$2->>'provider_version')
      where provider='google' and external_id=$2->>'external_id' and (metadata->>'provider_version' is distinct from $2->>'provider_version' or ($2->>'trashed')::boolean);
  elsif $1='calendar_snapshot' then
    update public.client_finder_meetings set status='not_in_current_calendar',updated_at=now()
      where provider='google' and starts_with(external_id,($2->>'calendar_id')||':') and not ($2->'event_ids' ? external_id);
  elsif $1='meeting' then
    insert into public.client_finder_meetings(provider,external_id,correlation_key,title,starts_at,status,summary,action_items,version)
      values(c.provider,$2->>'external_id',$2->>'correlation_key',$2->>'title',($2->>'starts_at')::timestamptz,$2->>'status',coalesce($2->>'summary',''),coalesce($2->'action_items','[]'),$2->>'version')
      on conflict(provider,external_id) do update set title=excluded.title,starts_at=excluded.starts_at,status=excluded.status,summary=excluded.summary,action_items=excluded.action_items,version=excluded.version,updated_at=now();
  else raise exception 'unsupported_integration_record'; end if;
  return jsonb_build_object('status','recorded');
end $$;

create function public.client_finder_operation_worker(operation text,item jsonb default '{}')
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare o public.client_finder_operations%rowtype;
begin
  if $1='claim' then
    update public.client_finder_operations set status=case when kind='ghl_mirror' then 'needs_checking' else 'blocked' end,error_code='worker_interrupted',lease_id=null,lease_until=null where status='running' and lease_until<now();
    select * into o from public.client_finder_operations where status='pending' order by created_at for update skip locked limit 1;
    if not found then return null; end if;
    update public.client_finder_operations set status='running',lease_id=gen_random_uuid(),lease_until=now()+interval '15 minutes' where id=o.id returning * into o;
  elsif $1='finish' then
    update public.client_finder_operations set status=case when $2->>'error_code' is null then 'complete' else 'blocked' end,
      error_code=$2->>'error_code',result=$2->'result',finished_at=now(),lease_id=null,lease_until=null
      where id=($2->>'id')::uuid and status='running' and lease_id=($2->>'lease_id')::uuid and lease_until>now() returning * into o;
    if not found then raise exception 'stale_operation_lease'; end if;
  else raise exception 'invalid_worker_operation'; end if;
  return to_jsonb(o);
end $$;

do $$ declare t text; f record; begin
  foreach t in array array['connections','resources','workflows','workflow_runs','import_batches','history','operations','meetings','crm_links'] loop
    execute format('alter table public.client_finder_%I enable row level security',t);
    execute format('revoke all on public.client_finder_%I from public,anon,authenticated,service_role',t);
    execute format('grant select on public.client_finder_%I to service_role',t);
  end loop;
  for f in select oid::regprocedure as signature from pg_proc where pronamespace='public'::regnamespace and proname in
    ('client_finder_acquisition_action','client_finder_integration_record','client_finder_operation_worker') loop
    execute format('revoke all on function %s from public,anon,authenticated',f.signature);
    execute format('grant execute on function %s to service_role',f.signature);
  end loop;
end $$;
commit;
