-- Conversation replies share immutable revisions/attempts and suppression with cold outreach.
begin;
alter table public.client_finder_messages
  add column if not exists conversation_id uuid references public.client_finder_conversations(id),
  add column if not exists inbound_message_id uuid references public.client_finder_inbox_messages(id),
  add column if not exists context_version integer,
  add column if not exists approved_via text,
  add column if not exists reviewed_proof_url text;
alter table public.client_finder_messages alter column lead_id drop not null,
  alter column observed_need drop not null, alter column deliverable_id drop not null, alter column proof_id drop not null;
alter table public.client_finder_message_revisions alter column observed_need drop not null,
  alter column deliverable_id drop not null, alter column proof_id drop not null;
alter table public.client_finder_messages drop constraint if exists client_finder_messages_observed_need_check;
-- Replace only the original kind/parent checks; keep unrelated payload constraints.
do $$ declare c record; begin
  for c in select conname from pg_constraint where conrelid='public.client_finder_messages'::regclass
    and contype='c' and pg_get_constraintdef(oid) like '%kind%' loop
    execute format('alter table public.client_finder_messages drop constraint %I',c.conname);
  end loop;
end $$;
alter table public.client_finder_messages add constraint client_finder_messages_observed_need_check
  check (kind='reply' or nullif(btrim(observed_need),'') is not null);
alter table public.client_finder_messages add constraint client_finder_message_kind_v2 check (
  (kind='initial' and parent_message_id is null and lead_id is not null and proof_id is not null and deliverable_id is not null and observed_need is not null)
  or (kind='followup' and parent_message_id is not null and lead_id is not null and proof_id is not null and deliverable_id is not null and observed_need is not null)
  or (kind='reply' and parent_message_id is null and conversation_id is not null and inbound_message_id is not null and context_version is not null));
create unique index if not exists client_finder_one_reply_per_inbound on public.client_finder_messages(inbound_message_id) where kind='reply';
alter table public.client_finder_send_attempts
  add column if not exists send_class text not null default 'outreach' check (send_class in ('outreach','reply')),
  add column if not exists reply_thread_id text,
  add column if not exists in_reply_to text,
  add column if not exists references_header text,
  add column if not exists rfc_message_id text;

create or replace function public.client_finder_reply_attempt_guard()
returns trigger language plpgsql security definer set search_path=pg_catalog as $$ begin
  if row(old.send_class,old.reply_thread_id,old.in_reply_to,old.references_header,old.rfc_message_id)
    is distinct from row(new.send_class,new.reply_thread_id,new.in_reply_to,new.references_header,new.rfc_message_id) then
    raise exception 'attempt_routing_is_immutable'; end if;
  return new;
end $$;
drop trigger if exists client_finder_reply_route_guard on public.client_finder_send_attempts;
create trigger client_finder_reply_route_guard before update on public.client_finder_send_attempts
  for each row execute function public.client_finder_reply_attempt_guard();

create or replace function public.client_finder_invalidate_conversation(conversation_id uuid)
returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
  update public.client_finder_tasks set status='dismissed',blocker='Conversation changed; use the latest message',updated_at=now()
    where client_finder_tasks.conversation_id=$1 and status in ('pending','running','blocked','review')
      and context_version < (select context_version from public.client_finder_conversations where id=$1);
  -- Claimed payloads are safe to cancel; a started request stays unknown until reconciled.
  update public.client_finder_send_attempts a set status='canceled',result_note='new_conversation_context'
    from public.client_finder_messages m where a.message_id=m.id and m.conversation_id=$1 and a.status='claimed';
  update public.client_finder_messages set approved_revision=null,approved_at=null,approved_via=null,
    telegram_card_id=null,telegram_card_revision=null,
    status=case when status='claimed' then 'skipped' else 'draft' end,updated_at=now()
    where client_finder_messages.conversation_id=$1 and kind='reply' and status in ('draft','pending_review','claimed','edit_requested');
end $$;

create or replace function public.client_finder_reply_save(conversation_id uuid, expected_revision integer,
  subject text, body text, proof_id text default null, actor uuid default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_conversations%rowtype; i public.client_finder_inbox_messages%rowtype;
  m public.client_finder_messages%rowtype; new_evidence jsonb; proof public.client_finder_proofs%rowtype;
begin
  perform public.client_finder_assert_web_owner($6);
  select * into c from public.client_finder_conversations where id=$1 for update;
  select * into i from public.client_finder_inbox_messages where id=c.latest_inbound_id;
  if c.id is null or i.id is null or i.deleted_at is not null or i.direction<>'in' then raise exception 'inbound_context_required'; end if;
  if c.category not in ('onlinejobs_conversation','direct_client') then raise exception 'classify_conversation_first'; end if;
  if not c.reply_verified or nullif(c.reply_email,'') is null then raise exception 'verified_recipient_required'; end if;
  if c.suppressed or c.bounced then raise exception 'contact_blocked'; end if;
  if nullif(btrim($3),'') is null or nullif(btrim($4),'') is null or length($3)>998 or length($4)>20000
    or $3 ~ E'[\\r\\n]' then raise exception 'invalid_message'; end if;
  if i.channel='gmail' and i.reply_verified and $3 not in (i.subject,'Re: '||i.subject) then raise exception 'reply_subject_must_match'; end if;
  if $5 is not null then
    select * into proof from public.client_finder_proofs where id=$5 and active and verified_at is not null;
    if not found then raise exception 'verified_proof_required'; end if;
    if position(proof.proof_url in $4)=0 then raise exception 'include_selected_proof_link'; end if;
  end if;
  if i.classification->>'intent'='loom_requested' and (proof.id is null or proof.proof_url !~ '^https://(www[.])?loom[.]com/share/') then raise exception 'verified_loom_required'; end if;
  select * into m from public.client_finder_messages where inbound_message_id=i.id and kind='reply' for update;
  if found and m.status in ('sending','send_unknown','sent','claimed') then raise exception 'message_already_reserved_or_sent'; end if;
  if coalesce(m.revision,0) is distinct from $2 then raise exception 'stale_revision'; end if;
  new_evidence:=jsonb_build_object('inbound_message_id',i.id,'context_version',c.context_version,'proof_url',proof.proof_url);
  if m.id is null then
    insert into public.client_finder_messages(kind,conversation_id,inbound_message_id,context_version,recipient_email,
      subject,body,evidence,proof_id,reviewed_proof_url,status)
      values('reply',c.id,i.id,c.context_version,c.reply_email,$3,$4,new_evidence,$5,proof.proof_url,'pending_review') returning * into m;
  else
    update public.client_finder_messages set revision=revision+1,recipient_email=c.reply_email,subject=$3,body=$4,evidence=new_evidence,
      context_version=c.context_version,proof_id=$5,reviewed_proof_url=proof.proof_url,status='pending_review',approved_revision=null,approved_at=null,approved_via=null,
      telegram_card_id=null,telegram_card_revision=null,updated_at=now() where id=m.id returning * into m;
  end if;
  insert into public.client_finder_message_revisions(message_id,revision,recipient_email,subject,body,evidence,proof_id)
    values(m.id,m.revision,m.recipient_email,m.subject,m.body,m.evidence,m.proof_id);
  insert into public.client_finder_owner_actions(actor,action,object_id,details)
    values(coalesce($6::text,'agent'),'save_reply',m.id,jsonb_build_object('revision',m.revision));
  insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,status,context_version)
    values('review:'||m.id||':'||m.revision,c.id,c.opportunity_id,i.id,'Hopper','review_reply','Review the exact reply revision','review',c.context_version) on conflict do nothing;
  return to_jsonb(m);
end $$;

create or replace function public.client_finder_reply_block(message_id uuid)
returns text language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; c public.client_finder_conversations%rowtype;
  i public.client_finder_inbox_messages%rowtype; box public.client_finder_mailboxes%rowtype;
  settings public.client_finder_settings%rowtype;
begin
  select * into m from public.client_finder_messages where id=$1;
  if not found or m.kind<>'reply' then return 'reply_missing'; end if;
  select * into c from public.client_finder_conversations where id=m.conversation_id;
  select * into i from public.client_finder_inbox_messages where id=m.inbound_message_id;
  select * into box from public.client_finder_mailboxes where id=1;
  if not box.replies_enabled then return 'reply_sending_disabled'; end if;
  select * into settings from public.client_finder_settings where id=1;
  if settings.sender_email is distinct from 'armageddonvivas@gmail.com' or nullif(btrim(settings.sender_name),'') is null
    or nullif(btrim(settings.postal_address),'') is null or nullif(btrim(settings.commercial_label),'') is null
    or nullif(btrim(settings.opt_out_route),'') is null then return 'sender_setup_required'; end if;
  if position(settings.sender_name in m.body)=0 or position(settings.postal_address in m.body)=0
    or position(settings.commercial_label in m.body)=0 or position(settings.opt_out_route in m.body)=0 then return 'reviewed_sender_footer_required'; end if;
  if box.email<>'armageddonvivas@gmail.com' or box.verified_at is null or box.last_success_at is null
    or box.last_success_at<now()-interval '15 minutes' or box.error_code is not null then return 'inbox_unhealthy'; end if;
  if c.context_version is distinct from m.context_version or c.latest_inbound_id is distinct from i.id
    or i.deleted_at is not null then return 'stale_context'; end if;
  if exists(select 1 from public.client_finder_inbox_messages newer join public.client_finder_conversations sibling on sibling.id=newer.conversation_id
    where sibling.opportunity_id=c.opportunity_id and newer.direction='in' and newer.deleted_at is null
      and newer.id<>i.id and newer.occurred_at>i.occurred_at) then return 'newer_linked_correspondence'; end if;
  if exists(select 1 from public.client_finder_inbox_messages newer join public.client_finder_conversations sibling on sibling.id=newer.conversation_id
    where (sibling.id=c.id or sibling.opportunity_id=c.opportunity_id) and newer.direction='out' and newer.deleted_at is null
      and newer.occurred_at>i.occurred_at) then return 'conversation_already_answered'; end if;
  if c.category not in ('onlinejobs_conversation','direct_client') or not c.reply_verified
    or c.reply_email is distinct from m.recipient_email then return 'recipient_unverified'; end if;
  if i.direction<>'in' or not i.reply_verified or i.reply_email is distinct from m.recipient_email
    or (i.channel='onlinejobs_import' and i.imported_by is null) then return 'inbound_authority_required'; end if;
  if i.channel='gmail' and nullif(i.rfc_message_id,'') is null then return 'thread_headers_missing'; end if;
  if c.suppressed or c.bounced or exists(select 1 from public.client_finder_suppressions where
    (scope='email' and value=m.recipient_email) or (scope='domain' and value=split_part(m.recipient_email,'@',2))) then return 'suppressed_or_bounced'; end if;
  if exists(select 1 from public.cold_leads where lower(btrim(contact_email))=m.recipient_email and status in ('bounced','unsubscribed')) then return 'legacy_suppression'; end if;
  if exists(select 1 from public.client_finder_send_attempts a join public.client_finder_messages x on x.id=a.message_id
    where x.recipient_email=m.recipient_email and a.status='send_unknown') then return 'unknown_send_needs_check'; end if;
  if m.proof_id is not null and not exists(select 1 from public.client_finder_proofs where id=m.proof_id and active and verified_at is not null and proof_url=m.reviewed_proof_url) then return 'proof_changed'; end if;
  return null;
end $$;

create or replace function public.client_finder_reply_approve(message_id uuid, revision integer, via text,
  actor text, telegram_user_id bigint default null, telegram_chat_id bigint default null, telegram_card_id bigint default null)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype; c public.client_finder_conversations%rowtype;
  i public.client_finder_inbox_messages%rowtype; a public.client_finder_send_attempts%rowtype; reason text;
  today date := (now() at time zone 'Asia/Manila')::date; cid uuid;
begin
  if $3 not in ('web','telegram') or nullif($4,'') is null then raise exception 'owner_required'; end if;
  if $3='web' then perform public.client_finder_assert_web_owner($4::uuid); end if;
  select conversation_id into cid from public.client_finder_messages where id=$1;
  select * into c from public.client_finder_conversations where id=cid for update;
  select * into m from public.client_finder_messages where id=$1 for update;
  if not found or m.kind<>'reply' or m.status<>'pending_review' or m.revision is distinct from $2 then raise exception 'stale_approval'; end if;
  if $3='telegram' then
    perform public.client_finder_assert_owner($5,$6);
    if m.telegram_card_id is distinct from $7 or m.telegram_card_revision is distinct from $2
      or m.telegram_owner_user_id is distinct from $5 or m.telegram_chat_id is distinct from $6 then raise exception 'stale_card'; end if;
  end if;
  reason:=public.client_finder_reply_block(m.id);
  if reason is not null then raise exception '%',reason; end if;
  perform pg_advisory_xact_lock(881103,today-date '2000-01-01');
  if (select count(*) from public.client_finder_send_attempts where attempt_day=today and send_class='reply') >=
    (select reply_limit from public.client_finder_mailboxes where id=1) then raise exception 'reply_daily_limit'; end if;
  select * into i from public.client_finder_inbox_messages where id=m.inbound_message_id;
  insert into public.client_finder_send_attempts(message_id,revision,attempt_day,recipient_email,subject,body,status,
    send_class,reply_thread_id,in_reply_to,references_header,rfc_message_id)
    values(m.id,m.revision,today,m.recipient_email,m.subject,m.body,'claimed','reply',
      case when i.channel='gmail' then c.gmail_thread_id end,i.rfc_message_id,
      trim(i.references_header||' '||i.rfc_message_id),'<hawkins-'||m.id||'-'||m.revision||'@gmail.com>') returning * into a;
  update public.client_finder_messages set status='claimed',approved_revision=$2,approved_at=now(),approved_via=$3 where id=m.id;
  update public.client_finder_tasks set status='done',updated_at=now() where dedup_key='review:'||m.id||':'||m.revision;
  insert into public.client_finder_owner_actions(actor,action,object_id,details) values($4,'approve_reply',m.id,jsonb_build_object('revision',$2,'via',$3));
  return to_jsonb(a);
end $$;

create or replace function public.client_finder_complete_reply(attempt_id uuid, gmail_message_id text, gmail_thread_id text)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype; m public.client_finder_messages%rowtype;
  c public.client_finder_conversations%rowtype; due timestamp; weekdays integer:=0;
begin
  a:=public._client_finder_complete_send($1,$2,$3);
  if a.send_class<>'reply' then raise exception 'reply_attempt_required'; end if;
  select * into m from public.client_finder_messages where id=a.message_id;
  select * into c from public.client_finder_conversations where id=m.conversation_id;
  due:=a.sent_at at time zone 'Asia/Manila';
  while weekdays<5 loop
    due:=due+interval '1 day';
    if extract(isodow from due) between 1 and 5 then weekdays:=weekdays+1; end if;
  end loop;
  insert into public.client_finder_tasks(dedup_key,conversation_id,opportunity_id,originating_message_id,agent,task_type,title,context_version,due_at)
    values('reminder:'||a.id,c.id,c.opportunity_id,m.inbound_message_id,'Max','conversation_reminder','Review unanswered conversation',m.context_version,due at time zone 'Asia/Manila') on conflict do nothing;
  return to_jsonb(a);
end $$;

create or replace function public.client_finder_reply_card_action(message_id uuid, revision integer, action text, card_id bigint, owner_user_id bigint, chat_id bigint)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare m public.client_finder_messages%rowtype;
begin
  perform public.client_finder_assert_owner($5,$6);
  select * into m from public.client_finder_messages where id=$1 for update;
  if not found or m.kind<>'reply' or m.status<>'pending_review' or m.revision is distinct from $2
    or m.telegram_card_id is distinct from $4 or m.telegram_card_revision is distinct from $2
    or m.telegram_owner_user_id is distinct from $5 or m.telegram_chat_id is distinct from $6 then raise exception 'stale_card'; end if;
  if $3='suppress' then
    perform public.client_finder_conversation_suppress(m.conversation_id,'telegram:'||$5);
  elsif $3 in ('edit','skip') then
    update public.client_finder_messages set status=case when $3='edit' then 'edit_requested' else 'skipped' end,
      approved_revision=null,approved_at=null,telegram_card_id=null,telegram_card_revision=null where id=m.id;
    update public.client_finder_tasks set status='dismissed' where dedup_key='review:'||m.id||':'||m.revision;
  else raise exception 'invalid_review_action'; end if;
end $$;

create or replace function public.client_finder_reply_begin(attempt_id uuid)
returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype; m public.client_finder_messages%rowtype; cid uuid; mid uuid; reason text;
begin
  select message_id into mid from public.client_finder_send_attempts where id=$1;
  select conversation_id into cid from public.client_finder_messages where id=mid;
  perform 1 from public.client_finder_conversations where id=cid for update;
  select * into m from public.client_finder_messages where id=mid for update;
  select * into a from public.client_finder_send_attempts where id=$1 for update;
  if not found or a.status<>'claimed' or a.send_class<>'reply' or m.approved_revision is distinct from a.revision or m.status<>'claimed' then raise exception 'attempt_unavailable'; end if;
  reason:=public.client_finder_reply_block(m.id);
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

create or replace function public.client_finder_reply_bind_card(message_id uuid, revision integer, card_id bigint, owner_user_id bigint, chat_id bigint)
returns void language plpgsql security definer set search_path=pg_catalog as $$
begin
  perform public.client_finder_assert_owner($4,$5);
  update public.client_finder_messages set telegram_card_id=$3,telegram_card_revision=$2,telegram_owner_user_id=$4,telegram_chat_id=$5
    where id=$1 and kind='reply' and client_finder_messages.revision=$2 and status='pending_review';
  if not found then raise exception 'stale_card'; end if;
end $$;

create or replace function public.client_finder_conversation_suppress(conversation_id uuid, actor text)
returns void language plpgsql security definer set search_path=pg_catalog as $$
declare c public.client_finder_conversations%rowtype;
begin
  select * into c from public.client_finder_conversations where id=$1 for update;
  if not found then raise exception 'conversation_missing'; end if;
  if c.reply_email is not null then
    insert into public.client_finder_suppressions(scope,value,reason,source) values('email',c.reply_email,'Owner requested do not contact','personal_control_center') on conflict do nothing;
  end if;
  update public.client_finder_conversations set suppressed=true,context_version=context_version+1 where id=c.id or reply_email=c.reply_email;
  perform public.client_finder_invalidate_conversation(id) from public.client_finder_conversations where id=c.id or reply_email=c.reply_email;
  insert into public.client_finder_owner_actions(actor,action,object_id) values($2,'suppress',$1);
end $$;

-- Preserve the original cold approval checks; narrow only its daily counter.
-- Reject replies on legacy callbacks: they use the new exact-context approval RPC.
do $$ declare definition text; begin
  select pg_get_functiondef('public._client_finder_claim_send(uuid,integer,bigint,bigint,bigint)'::regprocedure) into definition;
  if position('send_class' in definition)=0 then
    if position('where attempt_day = day_key)' in definition)=0 then raise exception 'unexpected_cold_claim_definition'; end if;
    definition:=replace(definition,'where attempt_day = day_key)','where attempt_day = day_key and send_class = ''outreach'')');
    definition:=replace(definition,'if not found or m.status <> ''pending_review''','if not found or m.kind = ''reply'' or m.status <> ''pending_review''');
    execute definition;
  end if;
end $$;

do $$ declare f record; begin
  for f in select p.oid::regprocedure as signature,p.proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and (p.proname like 'client_finder_reply_%' or p.proname in ('client_finder_conversation_suppress','client_finder_complete_reply')) loop
    execute format('revoke all on function %s from public,anon,authenticated,service_role',f.signature);
    if f.proname not in ('client_finder_reply_attempt_guard','client_finder_reply_block') then
      execute format('grant execute on function %s to service_role',f.signature);
    end if;
  end loop;
end $$;
commit;
