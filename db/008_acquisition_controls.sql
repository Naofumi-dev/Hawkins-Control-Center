begin;
create function public.client_finder_link_job_conversation(job_id uuid,conversation_id uuid,expected_opportunity_id uuid,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare j public.client_finder_jobs%rowtype; c public.client_finder_conversations%rowtype;
begin
  perform public.client_finder_assert_web_owner($4);
  select * into j from public.client_finder_jobs where id=$1 for update;
  if not found then raise exception 'job_missing'; end if;
  select * into c from public.client_finder_conversations where id=$2 for update;
  if not found or c.opportunity_id is distinct from $3 then raise exception 'conversation_link_changed'; end if;
  if exists(select 1 from public.client_finder_jobs where opportunity_id=c.opportunity_id and id<>j.id) then raise exception 'conversation_linked_to_another_job'; end if;
  if c.opportunity_id=j.opportunity_id then return to_jsonb(c); end if;
  update public.client_finder_conversations set opportunity_id=j.opportunity_id,updated_at=now() where id=c.id returning * into c;
  update public.client_finder_tasks set opportunity_id=j.opportunity_id where client_finder_tasks.conversation_id=c.id;
  update public.client_finder_jobs set context_version=context_version+1,updated_at=now() where id=j.id;
  insert into public.client_finder_owner_actions(actor,action,object_id,details)
    values($4::text,'link_job_conversation',c.id,jsonb_build_object('job_id',j.id,'previous_opportunity_id',$3));
  return to_jsonb(c);
end $$;

create function public.client_finder_meeting_changed() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
  if new.opportunity_id is not null and new.version is distinct from old.version then
    update public.client_finder_tasks set status='dismissed',blocker='Call evidence changed; review the latest summary'
      where starts_with(dedup_key,'meeting:'||new.id||':') and status in ('pending','running','blocked','review');
    insert into public.client_finder_tasks(dedup_key,opportunity_id,agent,task_type,title)
      values('meeting:'||new.id||':'||new.version,new.opportunity_id,'Steve','meeting_proposal','Prepare a proposal from the updated call') on conflict do nothing;
  end if;
  return new;
end $$;
create trigger meeting_evidence_changed after update on public.client_finder_meetings for each row execute function public.client_finder_meeting_changed();

create function public.client_finder_application_recover() returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
  update public.client_finder_send_attempts set status='send_unknown',unknown_at=now(),result_note='Platform submission interrupted; reconcile the application record'
    where send_class='application' and status='sending' and started_at<now()-interval '10 minutes';
  update public.client_finder_messages m set status='send_unknown' where m.kind='application' and m.status='sending'
    and exists(select 1 from public.client_finder_send_attempts a where a.message_id=m.id and a.status='send_unknown');
end $$;
create function public.client_finder_application_preflight(attempt_id uuid,reason text)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare mid uuid;
begin
  update public.client_finder_send_attempts set status='canceled',result_note=$2 where id=$1 and send_class='application' and status='claimed' returning message_id into mid;
  if mid is not null then
    update public.client_finder_messages set status='skipped',approved_revision=null,approved_at=null where id=mid;
  end if;
end $$;
create function public.client_finder_task_context(task_id uuid,lease_id uuid,context jsonb)
returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
  if octet_length($3::text)>30000 or not exists(select 1 from public.client_finder_tasks where id=$1 and client_finder_tasks.lease_id=$2 and status='running' and lease_until>now()) then raise exception 'stale_or_oversize_task_context'; end if;
  update public.client_finder_agent_runs set input_refs=input_refs||jsonb_build_object('bounded_context',$3)
    where client_finder_agent_runs.task_id=$1 and status='running';
end $$;
do $$ declare d text; begin
  select pg_get_functiondef(oid) into d from pg_proc where pronamespace='public'::regnamespace and proname='client_finder_task_claim';
  d:=replace(d,'where status=''pending'' and due_at<=now() order by',
    'where status=''pending'' and due_at<=now() and (dependency_id is null or exists(select 1 from public.client_finder_tasks prerequisite where prerequisite.id=client_finder_tasks.dependency_id and prerequisite.status in (''review'',''done''))) order by');
  execute d;
  select pg_get_functiondef(oid) into d from pg_proc where pronamespace='public'::regnamespace and proname='client_finder_task_finish';
  d:=replace(d,'stale := t.conversation_id is not null and t.context_version<>(select context_version from public.client_finder_conversations where id=t.conversation_id);',
    'stale := (t.conversation_id is not null and t.context_version<>(select context_version from public.client_finder_conversations where id=t.conversation_id)) or (t.task_type in (''qualify_job'',''cover_letter'') and exists(select 1 from public.client_finder_jobs where opportunity_id=t.opportunity_id and context_version<>t.context_version));');
  execute d;
end $$;
create function public.client_finder_acquisition_usage() returns jsonb language sql security definer set search_path=pg_catalog as $$
select jsonb_build_object('day',(now() at time zone 'Asia/Manila')::date,
 'outreach',(select count(*) from public.client_finder_send_attempts where attempt_day=(now() at time zone 'Asia/Manila')::date and send_class='outreach'),
 'applications',(select count(*) from public.client_finder_send_attempts where attempt_day=(now() at time zone 'Asia/Manila')::date and send_class='application'),
 'replies',(select count(*) from public.client_finder_send_attempts where attempt_day=(now() at time zone 'Asia/Manila')::date and send_class='reply'),
 'used_cents',(select coalesce(sum(case when status='settled' then actual_cents else reserved_cents end),0) from public.client_finder_cost_ledger where status<>'released' and budget_month=date_trunc('month',now() at time zone 'Asia/Manila')::date));
$$;

create function public.client_finder_resource_invalidate() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
  if row(new.version,new.active,new.verified_at) is distinct from row(old.version,old.active,old.verified_at) then
    update public.client_finder_send_attempts a set status='canceled',result_note='reviewed_resource_changed'
      where a.status='claimed' and a.send_class='application' and exists(select 1 from jsonb_array_elements(a.application_payload->'resources') x where x->>'id'=new.id::text);
    update public.client_finder_messages m set approved_revision=null,approved_at=null,approved_via=null,status='draft',telegram_card_id=null,telegram_card_revision=null
      where m.kind='application' and m.status in ('pending_review','claimed','edit_requested') and exists(select 1 from jsonb_array_elements(m.application_payload->'resources') x where x->>'id'=new.id::text);
  end if;
  return new;
end $$;
create trigger resource_revision_changed after update on public.client_finder_resources for each row execute function public.client_finder_resource_invalidate();

create function public.client_finder_application_handoff(attempt_id uuid,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype; started jsonb;
begin
  perform public.client_finder_assert_web_owner($2);
  select * into a from public.client_finder_send_attempts where id=$1;
  if a.send_class is distinct from 'application' or a.application_payload->>'delivery' is distinct from 'manual' then raise exception 'manual_application_required'; end if;
  started:=public.client_finder_application_begin(a.id);
  if started is null then return null; end if;
  insert into public.client_finder_owner_actions(actor,action,object_id) values($2::text,'begin_manual_handoff',a.id);
  return public.client_finder_application_result(a.id,jsonb_build_object('confirmed',false,'note','Owner began the approved manual handoff; reconcile before another attempt'));
end $$;

create function public.client_finder_application_manual_result(attempt_id uuid,reference text,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype;
begin
  perform public.client_finder_assert_web_owner($3);
  select * into a from public.client_finder_send_attempts where id=$1 for update;
  if a.send_class is distinct from 'application' or a.application_payload->>'delivery'<>'manual' then raise exception 'manual_application_required'; end if;
  if a.status='claimed' then raise exception 'begin_approved_handoff_first'; end if;
  if a.id is null or nullif(btrim($2),'') is null then raise exception 'submission_evidence_required'; end if;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($3::text,'confirm_manual_submission',a.id,jsonb_build_object('reference',$2));
  return public.client_finder_application_result(a.id,jsonb_build_object('confirmed',true,'reference',$2,'job_key',a.application_payload->>'job_key','reported_by',$3));
end $$;

create function public.client_finder_crm_queue() returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_connections%rowtype; l public.client_finder_crm_links%rowtype; target text;
begin
  if new.action<>'stage' then return new; end if;
  select * into l from public.client_finder_crm_links where opportunity_id=new.object_id;
  if not found then return new; end if;
  select * into c from public.client_finder_connections where provider='ghl';
  target:=c.selected->'stage_map'->>(new.details->>'stage');
  if target is null then return new; end if;
  insert into public.client_finder_operations(request_id,kind,actor,payload)
    values(new.id,'ghl_mirror',new.actor::uuid,jsonb_build_object('opportunity_id',new.object_id,'remote_id',l.remote_id,
      'location_id',l.location_id,'pipeline_id',l.pipeline_id,'expected_stage',l.remote_stage,'target_stage',target,'local_stage',new.details->>'stage')) on conflict do nothing;
  return new;
end $$;
create trigger owner_stage_to_personal_crm after insert on public.client_finder_owner_actions for each row execute function public.client_finder_crm_queue();

create function public.client_finder_crm_action(operation text,item jsonb,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_connections%rowtype; l public.client_finder_crm_links%rowtype; o public.client_finder_opportunities%rowtype; target text;
begin
  perform public.client_finder_assert_web_owner($3);
  select * into c from public.client_finder_connections where provider='ghl';
  select * into o from public.client_finder_opportunities where id=($2->>'opportunity_id')::uuid for update;
  if not found then raise exception 'opportunity_missing'; end if;
  if $1='bind' then
    if c.selected->>'location_id' is distinct from $2->>'location_id' or c.selected->>'pipeline_id' is distinct from $2->>'pipeline_id' then raise exception 'wrong_personal_pipeline'; end if;
    insert into public.client_finder_crm_links(opportunity_id,remote_id,remote_stage,location_id,pipeline_id)
      values(o.id,$2->>'remote_id',$2->>'remote_stage',$2->>'location_id',$2->>'pipeline_id')
      on conflict(opportunity_id) do update set remote_id=excluded.remote_id,remote_stage=excluded.remote_stage,location_id=excluded.location_id,pipeline_id=excluded.pipeline_id,conflict=null,checked_at=now() returning * into l;
  elsif $1='resolve' then
    select * into l from public.client_finder_crm_links where opportunity_id=o.id for update;
    if l.conflict is null or $2->>'decision' not in ('keep_remote','mirror_hawkins') then raise exception 'review_conflict_first'; end if;
    if l.conflict->>'remote_stage' is null then raise exception 'reconcile_unknown_write_first'; end if;
    update public.client_finder_crm_links set remote_stage=conflict->>'remote_stage',conflict=null where opportunity_id=o.id returning * into l;
    update public.client_finder_operations set status='dismissed' where kind='ghl_mirror' and payload->>'opportunity_id'=o.id::text and status in ('blocked','needs_checking','pending');
    if $2->>'decision'='mirror_hawkins' then
      target:=c.selected->'stage_map'->>o.stage;
      if target is null then raise exception 'stage_mapping_required'; end if;
      insert into public.client_finder_operations(request_id,kind,actor,payload) values(gen_random_uuid(),'ghl_mirror',$3,
        jsonb_build_object('opportunity_id',o.id,'remote_id',l.remote_id,'location_id',l.location_id,'pipeline_id',l.pipeline_id,'expected_stage',l.remote_stage,'target_stage',target,'local_stage',o.stage));
    end if;
  else raise exception 'invalid_crm_action'; end if;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($3::text,'crm_'||$1,o.id,$2);
  return to_jsonb(l);
end $$;

create function public.client_finder_crm_begin(operation_id uuid,lease_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare op public.client_finder_operations%rowtype; c public.client_finder_connections%rowtype; o public.client_finder_opportunities%rowtype;
begin
  select * into op from public.client_finder_operations where id=$1 for update;
  select * into c from public.client_finder_connections where provider='ghl';
  select * into o from public.client_finder_opportunities where id=(op.payload->>'opportunity_id')::uuid for update;
  if op.kind is distinct from 'ghl_mirror' or op.status<>'running' or op.lease_id is distinct from $2 or op.lease_until<now() then raise exception 'stale_crm_operation'; end if;
  if not c.enabled or c.status<>'verified' or nullif(c.selected->>'outbound_automation_review','') is null then raise exception 'crm_side_effect_review_required'; end if;
  if c.selected->>'location_id' is distinct from op.payload->>'location_id' or c.selected->>'pipeline_id' is distinct from op.payload->>'pipeline_id'
    or c.selected->'stage_map'->>o.stage is distinct from op.payload->>'target_stage' or o.stage is distinct from op.payload->>'local_stage' then
    update public.client_finder_operations set status='dismissed',error_code='stage_or_mapping_changed',finished_at=now() where id=op.id;
    return null;
  end if;
  return op.payload;
end $$;

create function public.client_finder_crm_result(operation_id uuid,remote_stage text,outcome text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare op public.client_finder_operations%rowtype;
begin
  select * into op from public.client_finder_operations where id=$1 for update;
  if op.kind is distinct from 'ghl_mirror' or op.status not in ('running','needs_checking') or $3 not in ('confirmed','conflict','unknown') then raise exception 'invalid_crm_result'; end if;
  if $3='confirmed' and $2 is distinct from op.payload->>'target_stage' then raise exception 'unconfirmed_crm_stage'; end if;
  update public.client_finder_crm_links l set remote_stage=case when $3='confirmed' then $2 else l.remote_stage end,
    conflict=case when $3='confirmed' then null else jsonb_build_object('remote_stage',$2,'requested_stage',op.payload->>'target_stage','outcome',$3) end,checked_at=now()
    where opportunity_id=(op.payload->>'opportunity_id')::uuid;
  update public.client_finder_operations set status=case $3 when 'confirmed' then 'complete' when 'conflict' then 'blocked' else 'needs_checking' end,
    error_code=case when $3<>'confirmed' then 'crm_'||$3 end,finished_at=now(),lease_id=null,lease_until=null where id=$1 returning * into op;
  return to_jsonb(op);
end $$;

-- Keep all established cold-email checks. The private variants omit only Telegram
-- identity/card tests; the public wrapper supplies verified Supabase owner identity.
do $$ declare d text; name text; oldguard text; newguard text; begin
  foreach name in array array['claim_send','edit_message'] loop
    select pg_get_functiondef(oid) into d from pg_proc where pronamespace='public'::regnamespace and proname='_client_finder_'||name;
    if d is null then raise exception 'cold_review_foundation_missing'; end if;
    d:=replace(d,'public._client_finder_'||name||'(','public._client_finder_web_'||name||'(');
    d:=replace(d,'perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);','');
    d:=regexp_replace(d,'\s+or m.telegram_card_revision <> p_revision\s+or m.telegram_owner_user_id <> p_owner_user_id\s+or m.telegram_chat_id <> p_chat_id\s+or m.telegram_card_id <> p_card_id','', 'g');
    if position('m.telegram_card_revision <>' in d)>0 then raise exception 'unexpected_cold_card_guard'; end if;
    if name='edit_message' then d:=replace(d,'m.status <> ''edit_requested''','m.kind not in (''initial'',''followup'') or m.status not in (''draft'',''pending_review'',''edit_requested'')');
    else
      d:=replace(d,'m.status <> ''pending_review''','m.status not in (''draft'',''pending_review'')');
      d:=replace(d,'recipient_email, subject, body, status)','recipient_email, subject, body, status, rfc_message_id)');
      d:=replace(d,'m.subject, m.body, ''claimed'')','m.subject, m.body, ''claimed'', ''<hawkins-outreach-''||m.id||''-r''||m.revision||''@personal.hawkins>'')');
      if position('hawkins-outreach-' in d)=0 then raise exception 'outreach_reconciliation_key_missing'; end if;
    end if;
    execute d;
  end loop;
  select pg_get_functiondef(oid) into d from pg_proc where pronamespace='public'::regnamespace and proname='_client_finder_begin_send';
  d:=replace(d,'if a.status <> ''claimed'' then','if a.send_class <> ''outreach'' then raise exception ''outreach_attempt_required''; end if; if a.status <> ''claimed'' then');
  execute d;
end $$;
create function public.client_finder_outreach_review(message_id uuid,revision integer,action text,subject text,body text,actor uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; r jsonb;
begin
  perform public.client_finder_assert_web_owner($6);
  select * into m from public.client_finder_messages where id=$1 for update;
  if m.kind not in ('initial','followup') or m.revision is distinct from $2 then raise exception 'stale_outreach_revision'; end if;
  if $3='save' then
    r:=to_jsonb(public._client_finder_web_edit_message($1,$2,null,null,null,m.recipient_email,$4,$5));
  elsif $3='approve' then
    r:=to_jsonb(public._client_finder_web_claim_send($1,$2,null,null,null));
    update public.client_finder_messages set approved_via='web' where id=m.id;
  else raise exception 'invalid_outreach_action'; end if;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($6::text,'outreach_'||$3,m.id,jsonb_build_object('revision',$2));
  return r;
end $$;

do $$ declare f record; begin
  for f in select oid::regprocedure signature,proname from pg_proc where pronamespace='public'::regnamespace and proname in
    ('client_finder_application_handoff','client_finder_link_job_conversation','client_finder_meeting_changed','client_finder_application_recover','client_finder_application_preflight','client_finder_task_context','client_finder_acquisition_usage','client_finder_resource_invalidate','client_finder_application_manual_result','client_finder_crm_queue','client_finder_crm_action','client_finder_crm_begin','client_finder_crm_result','_client_finder_web_claim_send','_client_finder_web_edit_message','client_finder_outreach_review') loop
    execute format('revoke all on function %s from public,anon,authenticated,service_role',f.signature);
    if f.proname not in ('client_finder_meeting_changed','client_finder_resource_invalidate','client_finder_crm_queue','_client_finder_web_claim_send','_client_finder_web_edit_message') then execute format('grant execute on function %s to service_role',f.signature); end if;
  end loop;
end $$;
commit;
