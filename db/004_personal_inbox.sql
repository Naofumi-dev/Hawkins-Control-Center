-- Additive personal inbox. Apply only to mtdavgadkiiofwikzdtn after backup and 001-003.
-- This migration never enables discovery, sync schedules, or sending.
begin;

create table if not exists public.client_finder_mailboxes (
  id smallint primary key default 1 check (id = 1),
  email text not null default 'armageddonvivas@gmail.com' check (email = 'armageddonvivas@gmail.com'),
  history_id text,
  backfill_start timestamptz not null default now() - interval '30 days',
  last_success_at timestamptz, last_attempt_at timestamptz,
  lease_id uuid, lease_until timestamptz,
  fetched_count integer not null default 0,
  error_code text, verified_at timestamptz,
  replies_enabled boolean not null default false,
  reply_limit integer not null default 20 check (reply_limit between 1 and 20)
);
insert into public.client_finder_mailboxes(id) values(1) on conflict do nothing;

create table if not exists public.client_finder_opportunities (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid references public.cold_leads(id),
  title text not null,
  kind text not null check (kind in ('client','job')),
  acquisition_source text not null check (acquisition_source in ('onlinejobs','direct','unknown')),
  stage text not null default 'new' check (stage in ('new','qualified','loom_call','proposal_offer','won','lost','onboarding')),
  stage_note text, won_confirmed_at timestamptz,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.client_finder_conversations (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid references public.client_finder_opportunities(id),
  gmail_thread_id text unique, platform_reference text unique,
  subject text not null, acquisition_source text not null default 'unknown',
  category text not null check (category in ('onlinejobs_conversation','direct_client','job_alert','other','needs_review')),
  classification_locked boolean not null default false,
  classification_reason text not null default '',
  reply_email text, reply_verified boolean not null default false,
  context_version integer not null default 0,
  latest_inbound_id uuid, last_message_at timestamptz,
  suppressed boolean not null default false, bounced boolean not null default false,
  needs_platform_import boolean not null default false,
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.client_finder_inbox_messages (
  id uuid primary key default gen_random_uuid(),
  provider_id text not null unique,
  conversation_id uuid not null references public.client_finder_conversations(id),
  channel text not null check (channel in ('gmail','onlinejobs_import')),
  direction text not null check (direction in ('in','out')),
  sender text not null, recipients jsonb not null default '[]',
  subject text not null, body text not null,
  occurred_at timestamptz not null,
  rfc_message_id text not null default '', references_header text not null default '',
  in_reply_to text not null default '', classification jsonb not null,
  reply_email text, reply_verified boolean not null default false,
  deleted_at timestamptz, imported_by uuid,
  created_at timestamptz not null default now()
);
create index if not exists client_finder_inbox_conversation_idx
  on public.client_finder_inbox_messages(conversation_id, occurred_at);
create table if not exists public.client_finder_tasks (
  id uuid primary key default gen_random_uuid(), dedup_key text not null unique,
  conversation_id uuid references public.client_finder_conversations(id),
  opportunity_id uuid references public.client_finder_opportunities(id),
  originating_message_id uuid references public.client_finder_inbox_messages(id),
  agent text not null check (agent in ('Will','Eleven','Steve','Hopper','Max','Mike','Joyce')),
  task_type text not null, title text not null,
  status text not null default 'pending' check (status in ('pending','running','blocked','review','done','dismissed')),
  blocker text, result jsonb, context_version integer not null default 0,
  lease_id uuid, lease_until timestamptz, attempts integer not null default 0,
  due_at timestamptz not null default now(),
  created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.client_finder_agent_runs (
  id uuid primary key default gen_random_uuid(), task_id uuid not null references public.client_finder_tasks(id),
  agent text not null, attempt integer not null, input_refs jsonb not null,
  status text not null default 'running', output jsonb, error_code text,
  started_at timestamptz not null default now(), completed_at timestamptz,
  unique(task_id,attempt)
);
create table if not exists public.client_finder_owner_actions (
  id uuid primary key default gen_random_uuid(), actor text not null,
  action text not null, object_id uuid, details jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create or replace function public.client_finder_assert_web_owner(actor uuid)
returns void language plpgsql security definer set search_path=pg_catalog as $$ begin
  if not exists(select 1 from auth.users where id=$1 and lower(email)='armageddonvivas@gmail.com' and email_confirmed_at is not null) then
    raise exception 'personal_owner_required'; end if;
end $$;

create or replace function public.client_finder_inbox_start(mailbox_email text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_mailboxes%rowtype;
begin
  if mailbox_email is distinct from 'armageddonvivas@gmail.com' then raise exception 'wrong_mailbox'; end if;
  select * into m from public.client_finder_mailboxes where id=1 for update;
  if m.lease_until > now() then raise exception 'sync_in_progress'; end if;
  update public.client_finder_mailboxes set lease_id=gen_random_uuid(), lease_until=now()+interval '30 minutes',
    last_attempt_at=now(), verified_at=now(), error_code=null where id=1 returning * into m;
  return to_jsonb(m);
end $$;

create or replace function public.client_finder_inbox_finish(lease_id uuid, history_id text, fetched_count integer, error_code text default null)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_mailboxes%rowtype;
begin
  select * into m from public.client_finder_mailboxes where id=1 for update;
  if m.lease_id is distinct from $1 or m.lease_until < now() then raise exception 'stale_sync_lease'; end if;
  if $4 is null and ($2 is null or $2 !~ '^[0-9]+$') then raise exception 'invalid_checkpoint'; end if;
  update public.client_finder_mailboxes set history_id=case when $4 is null then $2 else m.history_id end,
    last_success_at=case when $4 is null then now() else m.last_success_at end,
    fetched_count=$3, error_code=$4, lease_id=null, lease_until=null where id=1;
end $$;

create or replace function public.client_finder_inbox_error()
returns void language plpgsql security definer set search_path=pg_catalog as $$ begin
  update public.client_finder_mailboxes set last_attempt_at=now(),error_code='personal_mailbox_verification_failed'
    where id=1;
end $$;

create or replace function public.client_finder_workspace_status()
returns jsonb language sql security definer set search_path=pg_catalog as $$
  select jsonb_build_object(
    'stored_messages',(select count(*) from public.client_finder_inbox_messages where deleted_at is null),
    'pending_tasks',(select count(*) from public.client_finder_tasks where status in ('pending','running') and due_at<=now()),
    'blocked_tasks',(select count(*) from public.client_finder_tasks where status='blocked'),
    'scheduled_tasks',(select count(*) from public.client_finder_tasks where status='pending' and due_at>now()));
$$;

-- Invalidates every unsent reply when the conversation context changes.
-- The outbound migration replaces this function with additional send-state updates.
create or replace function public.client_finder_invalidate_conversation(conversation_id uuid)
returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
  update public.client_finder_tasks set status='dismissed',blocker='Conversation changed; use the latest message',updated_at=now()
    where client_finder_tasks.conversation_id=$1 and status in ('pending','running','blocked','review')
      and context_version < (select context_version from public.client_finder_conversations where id=$1);
end $$;

create or replace function public.client_finder_inbox_ingest(item jsonb)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_conversations%rowtype; m public.client_finder_inbox_messages%rowtype;
  cat text := item->'classification'->>'category'; source text := item->>'acquisition_source';
  oid uuid; candidate_count integer; intent text := item->'classification'->>'intent';
  latest timestamptz; request_type text; task_agent text; task_title text;
  legacy_id uuid; contact text := nullif(item->>'reply_email','');
begin
  if item->>'channel'='onlinejobs_import' then
    perform public.client_finder_assert_web_owner(nullif(item->>'imported_by','')::uuid);
  end if;
  if jsonb_typeof(item) <> 'object' or nullif(item->>'provider_id','') is null or
    cat not in ('onlinejobs_conversation','direct_client','job_alert','other','needs_review') or
    source not in ('onlinejobs','direct','unknown') or length(item->>'body') > 32000 or
    item->>'channel' not in ('gmail','onlinejobs_import') then raise exception 'invalid_inbox_item'; end if;
  -- Serialize identity resolution and manual-import vs Gmail races.
  perform pg_advisory_xact_lock(881105,1);
  select * into m from public.client_finder_inbox_messages where provider_id=item->>'provider_id';
  if found then
    if m.deleted_at is not null then
      update public.client_finder_inbox_messages set deleted_at=null where id=m.id;
      update public.client_finder_conversations set context_version=context_version+1,updated_at=now()
        where id=m.conversation_id returning * into c;
      perform public.client_finder_invalidate_conversation(c.id);
      insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,context_version)
        values('restored:'||m.id||':'||c.context_version,c.id,c.opportunity_id,m.id,'Will','classify','Review restored conversation',c.context_version) on conflict do nothing;
    end if;
    return jsonb_build_object('status','duplicate','message_id',m.id,'conversation_id',m.conversation_id);
  end if;
  if item->>'channel'='gmail' then
    select * into c from public.client_finder_conversations where gmail_thread_id=item->>'thread_id' for update;
  else
    select * into c from public.client_finder_conversations where platform_reference=item->>'platform_reference' for update;
  end if;
  if c.id is null and nullif(item->>'platform_reference','') is not null then
    select * into c from public.client_finder_conversations where platform_reference=item->>'platform_reference' for update;
  end if;
  if c.id is null then
    select case when count(*)=1 then (array_agg(id))[1] end into legacy_id
      from public.cold_leads where lower(btrim(contact_email))=contact;
    if cat='needs_review' and item->>'direction'='in' and coalesce((item->>'reply_verified')::boolean,false)
      and exists(select 1 from public.cold_leads where id=legacy_id and first_sent_at is not null) then
      cat:='direct_client';
      if source='unknown' then source:='direct'; end if;
    end if;
    -- A direct email can continue exactly one owner-verified platform conversation.
    if contact is not null and item->>'direction'='in' and source <> 'onlinejobs' then
      select count(distinct opportunity_id), (array_agg(distinct opportunity_id))[1]
      into candidate_count, oid from public.client_finder_conversations
      where reply_email=contact and reply_verified and opportunity_id is not null;
      if candidate_count=1 then
        select acquisition_source into source from public.client_finder_opportunities where id=oid;
        cat := case when source='onlinejobs' then 'onlinejobs_conversation' else 'direct_client' end;
      elsif candidate_count>1 then oid:=null; cat:='needs_review'; end if;
    end if;
    if oid is null and cat in ('onlinejobs_conversation','direct_client') then
      insert into public.client_finder_opportunities(title,kind,acquisition_source,lead_id)
        values(left(item->>'subject',500),case when source='onlinejobs' then 'job' else 'client' end,source,legacy_id)
        returning id into oid;
    end if;
    insert into public.client_finder_conversations(gmail_thread_id,platform_reference,subject,acquisition_source,
      category,classification_reason,reply_email,reply_verified,opportunity_id)
      values(case when item->>'channel'='gmail' then item->>'thread_id' end,
        nullif(item->>'platform_reference',''),left(item->>'subject',998),source,cat,
        item->'classification'->>'reason',contact,coalesce((item->>'reply_verified')::boolean,false),oid)
      returning * into c;
  end if;
  insert into public.client_finder_inbox_messages(provider_id,conversation_id,channel,direction,sender,recipients,
    subject,body,occurred_at,rfc_message_id,references_header,in_reply_to,classification,reply_email,reply_verified,imported_by)
    values(item->>'provider_id',c.id,item->>'channel',item->>'direction',item->>'sender',coalesce(item->'recipients','[]'),
      item->>'subject',item->>'body',(item->>'occurred_at')::timestamptz,coalesce(item->>'rfc_message_id',''),
      coalesce(item->>'references_header',''),coalesce(item->>'in_reply_to',''),item->'classification',contact,
      coalesce((item->>'reply_verified')::boolean,false),nullif(item->>'imported_by','')::uuid) returning * into m;
  select occurred_at into latest from public.client_finder_inbox_messages where id=c.latest_inbound_id;
  if m.direction='in' and (latest is null or m.occurred_at>=latest or
    (m.channel='onlinejobs_import' and c.needs_platform_import and m.imported_by is not null)) then
    update public.client_finder_conversations set context_version=context_version+1,latest_inbound_id=m.id,
      reply_email=case when m.reply_verified then m.reply_email else reply_email end,
      reply_verified=reply_verified or m.reply_verified,
      needs_platform_import=coalesce((item->>'needs_platform_import')::boolean,false),
      category=case when classification_locked or acquisition_source='onlinejobs' and category='onlinejobs_conversation'
        then category else cat end,
      classification_reason=case when classification_locked then classification_reason else item->'classification'->>'reason' end,
      updated_at=now() where id=c.id returning * into c;
    perform public.client_finder_invalidate_conversation(c.id);
    -- A newer message in a linked channel also makes a pending response obsolete.
    if c.opportunity_id is not null then
      update public.client_finder_conversations set context_version=context_version+1
        where id<>c.id and opportunity_id=c.opportunity_id and coalesce(last_message_at,'-infinity')<=m.occurred_at;
      perform public.client_finder_invalidate_conversation(id) from public.client_finder_conversations
        where id<>c.id and opportunity_id=c.opportunity_id and coalesce(last_message_at,'-infinity')<=m.occurred_at;
    end if;
    if intent='optout' and contact is not null and m.reply_verified then
      insert into public.client_finder_suppressions(scope,value,reason,source) values('email',contact,'Inbound opt-out','personal_inbox') on conflict do nothing;
      update public.client_finder_conversations set suppressed=true where reply_email=contact;
    elsif intent='bounce' then
      -- A bounce must name a known recipient. Ambiguous failures cannot authorize any delivery.
      if nullif(item->>'delivery_recipient','') is not null then
        update public.client_finder_conversations set bounced=true where reply_email=lower(item->>'delivery_recipient');
      end if;
    end if;
    if c.category in ('onlinejobs_conversation','direct_client','needs_review') and intent not in ('optout','bounce')
      and not exists(select 1 from public.client_finder_inbox_messages where conversation_id=c.id and direction='out' and occurred_at>m.occurred_at) then
      request_type := case when c.category='needs_review' then 'classify' when c.needs_platform_import then 'platform_import'
        when intent='loom_requested' then 'prepare_loom' when intent='proposal_requested' then 'prepare_proposal'
        when intent='meeting_requested' then 'prepare_meeting' else 'prepare_reply' end;
      task_agent := case when request_type in ('classify','platform_import') then 'Will' else 'Steve' end;
      task_title := case request_type when 'classify' then 'Review conversation classification'
        when 'platform_import' then 'Import the full OnlineJobs conversation' when 'prepare_loom' then 'Prepare Loom email'
        when 'prepare_proposal' then 'Prepare proposal response' when 'prepare_meeting' then 'Prepare meeting response'
        else 'Prepare a reply' end;
      insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,context_version)
        values('inbox:'||m.id,c.id,c.opportunity_id,m.id,task_agent,request_type,task_title,c.context_version) on conflict do nothing;
      if c.opportunity_id is not null then
        insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,context_version)
          values('qualify:'||m.id,c.id,c.opportunity_id,m.id,'Eleven','qualify','Prepare qualification brief',c.context_version) on conflict do nothing;
      end if;
    end if;
  end if;
  if m.direction='out' then
    -- A manual Gmail reply makes an unsent draft obsolete, including linked
    -- platform conversations. Our already recorded sends keep their reminder.
    if m.occurred_at>=coalesce(c.last_message_at,'-infinity') and not exists(
      select 1 from public.client_finder_send_attempts where gmail_message_id=m.provider_id and status='sent') then
      update public.client_finder_conversations set context_version=context_version+1
        where id=c.id or (c.opportunity_id is not null and opportunity_id=c.opportunity_id);
      perform public.client_finder_invalidate_conversation(id) from public.client_finder_conversations
        where id=c.id or (c.opportunity_id is not null and opportunity_id=c.opportunity_id);
    end if;
    update public.client_finder_tasks set status='done',blocker='A newer outgoing message was observed',updated_at=now()
      where conversation_id=c.id and agent='Steve' and status in ('pending','blocked','review')
      and originating_message_id in (select id from public.client_finder_inbox_messages where conversation_id=c.id and occurred_at<m.occurred_at);
  end if;
  update public.client_finder_conversations set last_message_at=greatest(last_message_at,m.occurred_at),updated_at=now() where id=c.id;
  -- Existing cold outreach must stop for any verified reply, including cross-thread mail.
  if m.direction='in' and m.reply_verified then
    update public.cold_leads set replied_at=coalesce(replied_at,m.occurred_at),
      status=case when status in ('bounced','unsubscribed') then status else 'replied' end
      where lower(btrim(contact_email))=m.reply_email;
  end if;
  return jsonb_build_object('status','recorded','message_id',m.id,'conversation_id',c.id);
end $$;

create or replace function public.client_finder_inbox_delete(provider_id text)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare cid uuid;
begin
  update public.client_finder_inbox_messages set deleted_at=now() where client_finder_inbox_messages.provider_id=$1 and deleted_at is null returning conversation_id into cid;
  if cid is not null then
    update public.client_finder_conversations set context_version=context_version+1 where id=cid;
    perform public.client_finder_invalidate_conversation(cid);
  end if;
end $$;

create or replace function public.client_finder_correct_classification(conversation_id uuid, category text, reason text, actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_conversations%rowtype; oid uuid; intent text;
begin
  perform public.client_finder_assert_web_owner($4);
  if $2 not in ('onlinejobs_conversation','direct_client','job_alert','other','needs_review') or nullif(btrim($3),'') is null then raise exception 'invalid_correction'; end if;
  select * into c from public.client_finder_conversations where id=$1 for update;
  if not found then raise exception 'conversation_missing'; end if;
  oid:=c.opportunity_id;
  if oid is null and $2 in ('onlinejobs_conversation','direct_client') then
    insert into public.client_finder_opportunities(title,kind,acquisition_source,lead_id) values(c.subject,
      case when $2='onlinejobs_conversation' then 'job' else 'client' end,
      case when $2='onlinejobs_conversation' then 'onlinejobs' else 'direct' end,
      (select case when count(*)=1 then (array_agg(id))[1] end from public.cold_leads where lower(btrim(contact_email))=c.reply_email)) returning id into oid;
  end if;
  update public.client_finder_conversations set category=$2,classification_locked=true,classification_reason=$3,
    opportunity_id=oid,acquisition_source=case when acquisition_source='onlinejobs' or $2='onlinejobs_conversation' then 'onlinejobs'
      when $2='direct_client' then 'direct' else acquisition_source end,context_version=context_version+1,updated_at=now()
    where id=$1 returning * into c;
  perform public.client_finder_invalidate_conversation(c.id);
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($4::text,'classification',c.id,jsonb_build_object('category',$2,'reason',$3));
  if c.latest_inbound_id is not null and $2 in ('onlinejobs_conversation','direct_client') then
    select classification->>'intent' into intent from public.client_finder_inbox_messages where id=c.latest_inbound_id;
    insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,context_version)
      values('corrected:'||c.id||':'||c.context_version,c.id,oid,c.latest_inbound_id,'Steve',
        case when intent='loom_requested' then 'prepare_loom' when intent='proposal_requested' then 'prepare_proposal' else 'prepare_reply' end,
        case when intent='loom_requested' then 'Prepare Loom email' when intent='proposal_requested' then 'Prepare proposal response' else 'Prepare a reply' end,c.context_version) on conflict do nothing;
  end if;
  return to_jsonb(c);
end $$;

create or replace function public.client_finder_set_stage(opportunity_id uuid, stage text, note text, actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare o public.client_finder_opportunities%rowtype;
begin
  perform public.client_finder_assert_web_owner($4);
  select * into o from public.client_finder_opportunities where id=$1 for update;
  if not found then raise exception 'opportunity_missing'; end if;
  if $2 not in ('new','qualified','loom_call','proposal_offer','won','lost','onboarding') then raise exception 'invalid_stage'; end if;
  if $2 in ('won','lost') and nullif(btrim($3),'') is null then raise exception 'agreement_or_outcome_evidence_required'; end if;
  if $2='onboarding' and (o.won_confirmed_at is null or o.stage not in ('won','onboarding')) then raise exception 'confirm_won_first'; end if;
  update public.client_finder_opportunities set stage=$2,stage_note=$3,updated_at=now(),
    won_confirmed_at=case when $2='won' then now() when $2='onboarding' then won_confirmed_at else null end where id=$1 returning * into o;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($4::text,'stage',$1,jsonb_build_object('stage',$2,'note',$3));
  if $2='won' then
    insert into public.client_finder_tasks(dedup_key,opportunity_id,agent,task_type,title)
      values('onboarding:'||$1,$1,'Joyce','onboarding','Prepare client onboarding') on conflict do nothing;
  end if;
  return to_jsonb(o);
end $$;

create or replace function public.client_finder_task_claim()
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare t public.client_finder_tasks%rowtype; run_id uuid;
begin
  -- Crashed attempts remain visible and are not automatically charged/retried.
  update public.client_finder_tasks set status='blocked',blocker='Worker interrupted; review before retry',lease_id=null,lease_until=null
    where status='running' and lease_until<now();
  update public.client_finder_agent_runs set status='failed',error_code='worker_interrupted',completed_at=now()
    where status='running' and task_id in (select id from public.client_finder_tasks where status='blocked' and blocker='Worker interrupted; review before retry');
  select * into t from public.client_finder_tasks where status='pending' and due_at<=now() order by created_at,id for update skip locked limit 1;
  if not found then return null; end if;
  update public.client_finder_tasks set status='running',attempts=attempts+1,lease_id=gen_random_uuid(),lease_until=now()+interval '5 minutes',updated_at=now()
    where id=t.id returning * into t;
  insert into public.client_finder_agent_runs(task_id,agent,attempt,input_refs)
    values(t.id,t.agent,t.attempts,jsonb_build_object('message_id',t.originating_message_id,'context_version',t.context_version,'opportunity_id',t.opportunity_id)) returning id into run_id;
  return to_jsonb(t)||jsonb_build_object('run_id',run_id);
end $$;

create or replace function public.client_finder_task_finish(task_id uuid, lease_id uuid, result jsonb, blocker text default null)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare t public.client_finder_tasks%rowtype; stale boolean;
begin
  select * into t from public.client_finder_tasks where id=$1 for update;
  if t.lease_id is distinct from $2 or t.lease_until<now() then raise exception 'stale_task_lease'; end if;
  stale := t.conversation_id is not null and t.context_version<>(select context_version from public.client_finder_conversations where id=t.conversation_id);
  update public.client_finder_tasks set status=case when stale then 'dismissed' when $4 is null then 'review' else 'blocked' end,
    result=case when stale then null else $3 end,blocker=case when stale then 'Conversation changed; result discarded' else $4 end,
    lease_id=null,lease_until=null,updated_at=now() where id=$1;
  update public.client_finder_agent_runs set status=case when stale then 'stale' when $4 is null then 'complete' else 'blocked' end,
    output=case when stale then null else $3 end,error_code=$4,completed_at=now() where client_finder_agent_runs.task_id=$1 and attempt=t.attempts;
end $$;

create or replace function public.client_finder_task_action(task_id uuid, action text, actor uuid)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare t public.client_finder_tasks%rowtype;
begin
  perform public.client_finder_assert_web_owner($3);
  select * into t from public.client_finder_tasks where id=$1 for update;
  if not found or t.status='running' or $2 not in ('retry','done','dismiss') then raise exception 'invalid_task_action'; end if;
  if $2='retry' and (t.status<>'blocked' or (t.conversation_id is not null and t.context_version<>(select context_version from public.client_finder_conversations where id=t.conversation_id))) then raise exception 'task_not_retryable'; end if;
  update public.client_finder_tasks set status=case $2 when 'retry' then 'pending' when 'done' then 'done' else 'dismissed' end,
    blocker=null,updated_at=now() where id=$1;
  insert into public.client_finder_owner_actions(actor,action,object_id) values($3::text,'task_'||$2,$1);
end $$;

-- No browser/anonymous direct access, including service-role mutation bypasses.
do $$ declare t text; f record; begin
  foreach t in array array['mailboxes','opportunities','conversations','inbox_messages','tasks','agent_runs','owner_actions'] loop
    execute format('alter table public.client_finder_%I enable row level security',t);
    execute format('revoke all on public.client_finder_%I from public,anon,authenticated,service_role',t);
    execute format('grant select on public.client_finder_%I to service_role',t);
  end loop;
  for f in select p.oid::regprocedure as signature from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in ('client_finder_inbox_start','client_finder_inbox_finish','client_finder_inbox_error','client_finder_inbox_ingest',
      'client_finder_inbox_delete','client_finder_invalidate_conversation','client_finder_correct_classification',
      'client_finder_set_stage','client_finder_task_claim','client_finder_task_finish','client_finder_task_action','client_finder_assert_web_owner','client_finder_workspace_status') loop
    execute format('revoke all on function %s from public,anon,authenticated,service_role',f.signature);
    if f.signature::text not like '%invalidate_conversation%' and f.signature::text not like '%assert_web_owner%' then execute format('grant execute on function %s to service_role',f.signature); end if;
  end loop;
end $$;
commit;
