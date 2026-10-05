-- Hawkins Client Finder, additive migration for the existing Hawkins Supabase project.
-- Apply after the existing cold_leads/cold_campaigns schema. Re-running does not
-- enable sending, create a campaign, or change existing cold lead records.
-- All times used for daily/monthly limits are Asia/Manila local time.

begin;

create table if not exists public.client_finder_settings (
  id smallint primary key default 1 check (id = 1),
  owner_telegram_user_id bigint,
  owner_telegram_chat_id bigint,
  discovery_enabled boolean not null default false,
  sending_enabled boolean not null default false,
  sending_pause_reason text,
  sending_paused_at timestamptz,
  inbox_monitor_verified_at timestamptz,
  sender_name text,
  sender_email text,
  postal_address text,
  commercial_label text,
  opt_out_route text,
  daily_send_limit integer not null default 5 check (daily_send_limit between 1 and 5),
  monthly_cost_cap_cents numeric(12,4) not null default 2500
    check (monthly_cost_cap_cents between 1 and 2500),
  updated_at timestamptz not null default now(),
  check (not sending_enabled or (
    sending_pause_reason is null
    and
    owner_telegram_user_id is not null and owner_telegram_chat_id is not null
    and inbox_monitor_verified_at is not null
    and nullif(btrim(sender_name), '') is not null
    and nullif(btrim(sender_email), '') is not null
    and nullif(btrim(postal_address), '') is not null
    and nullif(btrim(commercial_label), '') is not null
    and nullif(btrim(opt_out_route), '') is not null
  ))
);
insert into public.client_finder_settings (id) values (1)
on conflict (id) do nothing;

-- Existing cold_leads already has global lower(domain) and lower(email) unique
-- indexes. Repeat their declarations for installations where the base schema's
-- indexes were not yet created. Normalize surrounding whitespace before insert.
create unique index if not exists cold_leads_company_domain_uniq
  on public.cold_leads (lower(company_domain)) where company_domain is not null;
create unique index if not exists cold_leads_contact_email_uniq
  on public.cold_leads (lower(contact_email)) where contact_email is not null;

create table if not exists public.client_finder_evidence (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.cold_leads(id),
  evidence_kind text not null check (evidence_kind in
    ('company', 'us_location', 'need', 'contact')),
  source_url text not null check (source_url ~ '^https?://'),
  observed_at timestamptz not null,
  fact_text text not null check (nullif(btrim(fact_text), '') is not null),
  created_at timestamptz not null default now()
);
create index if not exists client_finder_evidence_lead_idx
  on public.client_finder_evidence (lead_id, evidence_kind);

create table if not exists public.client_finder_deliverables (
  id text primary key check (nullif(btrim(id), '') is not null),
  title text not null,
  scope_text text not null,
  active boolean not null default false,
  updated_at timestamptz not null default now()
);

create table if not exists public.client_finder_proofs (
  id text primary key check (nullif(btrim(id), '') is not null),
  title text not null,
  proof_url text not null check (proof_url ~ '^https?://'),
  claim_text text not null,
  proof_kind text not null check (proof_kind in ('project', 'prototype')),
  verified_at timestamptz,
  active boolean not null default false,
  updated_at timestamptz not null default now()
);

create table if not exists public.client_finder_suppressions (
  scope text not null check (scope in ('email', 'domain')),
  value text not null check (value = lower(btrim(value)) and value <> ''),
  reason text not null,
  source text not null,
  created_at timestamptz not null default now(),
  primary key (scope, value)
);

create table if not exists public.client_finder_messages (
  id uuid primary key default gen_random_uuid(),
  lead_id uuid not null references public.cold_leads(id),
  kind text not null check (kind in ('initial', 'followup')),
  parent_message_id uuid references public.client_finder_messages(id),
  revision integer not null default 1 check (revision > 0),
  recipient_email text not null check (recipient_email = lower(btrim(recipient_email))
    and position('@' in recipient_email) > 1),
  subject text not null check (nullif(btrim(subject), '') is not null),
  body text not null check (nullif(btrim(body), '') is not null),
  evidence jsonb not null check (jsonb_typeof(evidence) = 'object'),
  observed_need text not null check (nullif(btrim(observed_need), '') is not null),
  deliverable_id text not null references public.client_finder_deliverables(id),
  proof_id text not null references public.client_finder_proofs(id),
  status text not null default 'draft' check (status in
    ('draft', 'pending_review', 'edit_requested', 'claimed', 'sending', 'send_unknown',
     'sent', 'failed', 'skipped', 'suppressed')),
  telegram_owner_user_id bigint,
  telegram_chat_id bigint,
  telegram_card_id bigint,
  telegram_card_revision integer,
  approved_revision integer,
  approved_at timestamptz,
  gmail_message_id text,
  gmail_thread_id text,
  sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((kind = 'initial' and parent_message_id is null)
      or (kind = 'followup' and parent_message_id is not null))
);
create unique index if not exists client_finder_one_initial_per_lead
  on public.client_finder_messages (lead_id) where kind = 'initial';
create unique index if not exists client_finder_one_followup_per_initial
  on public.client_finder_messages (parent_message_id) where kind = 'followup';
create unique index if not exists client_finder_gmail_message_uniq
  on public.client_finder_messages (gmail_message_id)
  where gmail_message_id is not null;
create index if not exists client_finder_messages_status_idx
  on public.client_finder_messages (status, created_at);

-- Public research can be useful even when no published business contact is
-- found. These tasks are keyed by the same lower-case, no-www domain used by
-- discovery; a task cannot authorize a message or a send.
create table if not exists public.client_finder_research_tasks (
  domain text primary key check (
    domain = regexp_replace(lower(btrim(domain)), '^www[.]', '')
    and domain ~ '^[a-z0-9][a-z0-9.-]*[.][a-z0-9-]+$'
    and position('..' in domain) = 0),
  company_url text not null check (company_url ~ '^https?://'),
  company_name text not null check (nullif(btrim(company_name), '') is not null),
  source_url text not null check (source_url ~ '^https?://'),
  reason text not null check (nullif(btrim(reason), '') is not null),
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  attempt_count integer not null default 1 check (attempt_count > 0),
  status text not null default 'open' check (status in ('open', 'qualified', 'dismissed')),
  qualified_at timestamptz,
  qualified_message_id uuid references public.client_finder_messages(id)
);
create index if not exists client_finder_research_tasks_status_idx
  on public.client_finder_research_tasks (status, last_seen_at);

-- Every draft revision is retained. Only create_message/edit_message insert rows.
create table if not exists public.client_finder_message_revisions (
  message_id uuid not null references public.client_finder_messages(id),
  revision integer not null check (revision > 0),
  recipient_email text not null,
  subject text not null,
  body text not null,
  evidence jsonb not null,
  observed_need text not null,
  deliverable_id text not null,
  proof_id text not null,
  created_at timestamptz not null default now(),
  primary key (message_id, revision)
);

create table if not exists public.client_finder_send_attempts (
  id uuid primary key default gen_random_uuid(),
  message_id uuid not null references public.client_finder_messages(id),
  revision integer not null,
  attempt_day date not null,
  recipient_email text not null,
  subject text not null,
  body text not null,
  status text not null check (status in
    ('claimed', 'sending', 'send_unknown', 'sent', 'failed', 'canceled')),
  claimed_at timestamptz not null default now(),
  started_at timestamptz,
  unknown_at timestamptz,
  sent_at timestamptz,
  gmail_message_id text,
  gmail_thread_id text,
  result_note text,
  foreign key (message_id, revision)
    references public.client_finder_message_revisions(message_id, revision),
  unique (message_id, revision)
);
create index if not exists client_finder_send_attempts_day_idx
  on public.client_finder_send_attempts (attempt_day);
create unique index if not exists client_finder_attempt_gmail_id_uniq
  on public.client_finder_send_attempts (gmail_message_id)
  where gmail_message_id is not null;

create table if not exists public.client_finder_mail_events (
  provider_event_id text primary key,
  message_id uuid not null references public.client_finder_messages(id),
  event_type text not null check (event_type in ('reply', 'bounce', 'optout')),
  occurred_at timestamptz not null,
  received_at timestamptz not null default now(),
  gmail_thread_id text,
  original_gmail_message_id text,
  sender_email text,
  bounced_recipient_email text,
  event_note text
);
create index if not exists client_finder_mail_events_message_idx
  on public.client_finder_mail_events (message_id, event_type);

create table if not exists public.client_finder_mail_monitor_state (
  id smallint primary key default 1 check (id = 1),
  scanned_through timestamptz,
  last_success_at timestamptz,
  last_fetched_count integer not null default 0 check (last_fetched_count >= 0)
);
insert into public.client_finder_mail_monitor_state (id) values (1)
on conflict (id) do nothing;

create table if not exists public.client_finder_cost_ledger (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  provider text not null,
  operation text not null,
  budget_month date not null,
  reserved_cents numeric(12,4) not null check (reserved_cents >= 0),
  actual_cents numeric(12,4) check (actual_cents >= 0),
  status text not null check (status in ('reserved', 'started', 'settled', 'released')),
  created_at timestamptz not null default now(),
  started_at timestamptz,
  settled_at timestamptz,
  check (actual_cents is null or actual_cents <= reserved_cents)
);
create index if not exists client_finder_cost_month_idx
  on public.client_finder_cost_ledger (budget_month, status);

-- The backend uses RPCs for message/attempt mutations. Service role can read
-- their state, but cannot bypass approval by writing those tables directly.
alter table public.client_finder_settings enable row level security;
alter table public.client_finder_evidence enable row level security;
alter table public.client_finder_deliverables enable row level security;
alter table public.client_finder_proofs enable row level security;
alter table public.client_finder_research_tasks enable row level security;
alter table public.client_finder_suppressions enable row level security;
alter table public.client_finder_messages enable row level security;
alter table public.client_finder_message_revisions enable row level security;
alter table public.client_finder_send_attempts enable row level security;
alter table public.client_finder_mail_events enable row level security;
alter table public.client_finder_mail_monitor_state enable row level security;
alter table public.client_finder_cost_ledger enable row level security;

revoke all on public.client_finder_settings, public.client_finder_evidence,
  public.client_finder_deliverables, public.client_finder_proofs,
  public.client_finder_research_tasks, public.client_finder_suppressions,
  public.client_finder_messages,
  public.client_finder_message_revisions, public.client_finder_send_attempts,
  public.client_finder_mail_events, public.client_finder_mail_monitor_state,
  public.client_finder_cost_ledger
  from public, anon, authenticated, service_role;
grant select on public.client_finder_settings, public.client_finder_evidence,
  public.client_finder_deliverables, public.client_finder_proofs,
  public.client_finder_research_tasks, public.client_finder_suppressions,
  public.client_finder_messages,
  public.client_finder_message_revisions, public.client_finder_send_attempts,
  public.client_finder_mail_events, public.client_finder_mail_monitor_state,
  public.client_finder_cost_ledger to service_role;
grant insert, update on public.client_finder_evidence,
  public.client_finder_deliverables, public.client_finder_proofs to service_role;

create or replace function public.client_finder_reject_immutable_change()
returns trigger language plpgsql security definer set search_path = pg_catalog as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'client finder audit rows cannot be deleted';
  end if;
  if tg_table_name = 'client_finder_send_attempts' and
     row(old.message_id, old.revision, old.attempt_day, old.recipient_email,
         old.subject, old.body, old.claimed_at)
       is distinct from
     row(new.message_id, new.revision, new.attempt_day, new.recipient_email,
         new.subject, new.body, new.claimed_at) then
    raise exception 'send attempt payload is immutable';
  end if;
  if tg_table_name = 'client_finder_message_revisions' then
    raise exception 'message revisions are immutable';
  end if;
  return new;
end;
$$;
drop trigger if exists client_finder_attempt_guard on public.client_finder_send_attempts;
create trigger client_finder_attempt_guard before update or delete
  on public.client_finder_send_attempts for each row
  execute function public.client_finder_reject_immutable_change();
drop trigger if exists client_finder_revision_guard on public.client_finder_message_revisions;
create trigger client_finder_revision_guard before update or delete
  on public.client_finder_message_revisions for each row
  execute function public.client_finder_reject_immutable_change();

create or replace function public.client_finder_assert_owner(
  p_user_id bigint, p_chat_id bigint)
returns void language plpgsql security definer set search_path = pg_catalog as $$
declare s public.client_finder_settings%rowtype;
begin
  select * into s from public.client_finder_settings where id = 1;
  if s.owner_telegram_user_id is null or s.owner_telegram_chat_id is null
     or p_user_id is distinct from s.owner_telegram_user_id
     or p_chat_id is distinct from s.owner_telegram_chat_id then
    raise exception 'unauthorized Telegram owner or chat';
  end if;
end;
$$;

-- RPC: pause_sending(reason). Inbox monitor or other trusted backend paths
-- can stop delivery immediately on ambiguous mail events or monitor failures.
-- Re-enabling requires a manual settings update after reconciliation.
create or replace function public._client_finder_pause_sending(p_reason text)
returns public.client_finder_settings
language plpgsql security definer set search_path = pg_catalog as $$
declare s public.client_finder_settings%rowtype;
begin
  if nullif(btrim(p_reason), '') is null then
    raise exception 'pause reason required';
  end if;
  update public.client_finder_settings set sending_enabled = false,
    sending_pause_reason = left(p_reason, 500), sending_paused_at = now(),
    updated_at = now() where id = 1 returning * into s;
  if not found then raise exception 'settings missing'; end if;
  return s;
end;
$$;

-- RPC: record_research_task(domain, company_url, company_name, source_url,
-- reason). Every sighting increments attempt_count. A qualified or dismissed
-- task remains closed if the agency is discovered again. Returns the task row
-- as one JSON object keyed by its canonical domain.
create or replace function public.client_finder_record_research_task(
  domain text, company_url text, company_name text, source_url text, reason text)
returns jsonb
language plpgsql security definer set search_path = pg_catalog as $$
declare
  canonical_domain text := regexp_replace(lower(btrim(domain)), '^www[.]', '');
  task_row public.client_finder_research_tasks%rowtype;
begin
  if canonical_domain is null or length(canonical_domain) > 253
     or canonical_domain !~ '^[a-z0-9][a-z0-9.-]*[.][a-z0-9-]+$'
     or position('..' in canonical_domain) > 0
     or nullif(btrim(company_url), '') is null
     or nullif(btrim(company_name), '') is null
     or nullif(btrim(source_url), '') is null
     or nullif(btrim(reason), '') is null then
    raise exception 'valid research task domain, company, source, and reason required';
  end if;
  insert into public.client_finder_research_tasks
    (domain, company_url, company_name, source_url, reason)
  values (canonical_domain, company_url, company_name, source_url, reason)
  on conflict on constraint client_finder_research_tasks_pkey do update set
    company_url = excluded.company_url,
    company_name = excluded.company_name,
    source_url = excluded.source_url,
    reason = excluded.reason,
    last_seen_at = now(),
    attempt_count = public.client_finder_research_tasks.attempt_count + 1
  returning * into task_row;
  return to_jsonb(task_row);
end;
$$;

-- Returns the first reason delivery must stop. Called at claim and again
-- immediately before the Gmail node. Old Hawkins history is checked too.
create or replace function public.client_finder_contact_block_reason(p_message_id uuid)
returns text language plpgsql security definer set search_path = pg_catalog as $$
declare
  m public.client_finder_messages%rowtype;
  l public.cold_leads%rowtype;
  parent public.client_finder_messages%rowtype;
  due_local timestamp without time zone;
  n integer := 0;
begin
  select * into m from public.client_finder_messages where id = p_message_id;
  if not found then return 'message_missing'; end if;
  select * into l from public.cold_leads where id = m.lead_id;
  if not found then return 'lead_missing'; end if;
  if l.contact_email is null or lower(btrim(l.contact_email)) <> m.recipient_email then
    return 'contact_mismatch';
  end if;
  if exists (select 1 from public.client_finder_suppressions s
    where (s.scope = 'email' and s.value = m.recipient_email)
       or (s.scope = 'domain' and s.value = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', ''))) then
    return 'suppressed';
  end if;
  if l.replied_at is not null or l.status in ('replied', 'bounced', 'unsubscribed')
     or exists (select 1 from public.client_finder_mail_events e
       join public.client_finder_messages x on x.id = e.message_id
       where x.lead_id = l.id and e.event_type in ('reply', 'bounce', 'optout')) then
    return 'reply_or_bounce';
  end if;
  if l.status in ('queued', 'approved', 'uploaded') then
    return 'prior_campaign_contact';
  end if;
  if exists (select 1 from public.cold_leads x
     where x.id <> l.id
       and ((l.company_domain is not null and x.company_domain is not null
          and regexp_replace(lower(btrim(x.company_domain)), '^www[.]', '')
              = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', ''))
        or (x.contact_email is not null
          and lower(btrim(x.contact_email)) = m.recipient_email))
       and (x.first_sent_at is not null or x.replied_at is not null
         or x.status in ('queued', 'approved', 'uploaded', 'sent',
                         'replied', 'bounced', 'unsubscribed'))) then
    return 'prior_campaign_contact';
  end if;
  -- Legacy indexes use the raw domain/email. A www-prefixed or padded legacy
  -- row can represent the same agency, so also block an in-flight Client Finder
  -- attempt on another lead. claim_send serializes approvals on settings id=1.
  if exists (select 1 from public.client_finder_send_attempts a
    join public.client_finder_messages x on x.id = a.message_id
    join public.cold_leads other_lead on other_lead.id = x.lead_id
    where x.lead_id <> l.id
      and a.status in ('claimed', 'sending', 'send_unknown', 'sent')
      and (x.recipient_email = m.recipient_email
        or (nullif(btrim(l.company_domain), '') is not null
          and nullif(btrim(other_lead.company_domain), '') is not null
          and regexp_replace(lower(btrim(other_lead.company_domain)), '^www[.]', '')
              = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', '')))) then
    return 'other_company_send_in_progress';
  end if;
  if m.kind = 'initial' then
    if l.first_sent_at is not null or l.status = 'sent' then
      return 'prior_campaign_contact';
    end if;
  else
    if exists (select 1 from public.client_finder_send_attempts a
      join public.client_finder_messages x on x.id = a.message_id
      where x.lead_id = l.id and a.status = 'send_unknown') then
      return 'unknown_send_needs_check';
    end if;
    select * into parent from public.client_finder_messages
      where id = m.parent_message_id and lead_id = m.lead_id
        and kind = 'initial' and status = 'sent';
    if not found or parent.sent_at is null or parent.gmail_message_id is null then
      return 'initial_not_confirmed';
    end if;
    due_local := parent.sent_at at time zone 'Asia/Manila';
    while n < 5 loop
      due_local := due_local + interval '1 day';
      if extract(isodow from due_local) between 1 and 5 then n := n + 1; end if;
    end loop;
    if (now() at time zone 'Asia/Manila') < due_local then
      return 'followup_too_early';
    end if;
  end if;
  return null;
end;
$$;

-- RPC: create_message(lead_id, recipient_email, subject, body, evidence,
-- observed_need, deliverable_id, proof_id, kind, parent_message_id).
-- The evidence JSON must contain contact_source_url, observation_source_url,
-- us_location_source_url, and observed_at. The URLs are validated by research.
create or replace function public._client_finder_create_message(
  p_lead_id uuid, p_recipient_email text, p_subject text, p_body text,
  p_evidence jsonb, p_observed_need text, p_deliverable_id text,
  p_proof_id text, p_kind text default 'initial', p_parent_message_id uuid default null)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare
  m public.client_finder_messages%rowtype;
  l public.cold_leads%rowtype;
  day_key date := (now() at time zone 'Asia/Manila')::date;
  parent public.client_finder_messages%rowtype;
  reason text;
  evidence_at timestamptz;
begin
  if p_kind not in ('initial', 'followup') or p_kind is null then
    raise exception 'invalid message kind';
  end if;
  if jsonb_typeof(p_evidence) is distinct from 'object'
     or nullif(btrim(p_evidence->>'contact_source_url'), '') is null
     or nullif(btrim(p_evidence->>'observation_source_url'), '') is null
     or nullif(btrim(p_evidence->>'us_location_source_url'), '') is null
     or nullif(btrim(p_evidence->>'observed_at'), '') is null then
    raise exception 'contact, observation, date, and US-location evidence required';
  end if;
  select * into l from public.cold_leads where id = p_lead_id for update;
  if not found or l.contact_email is null
     or lower(btrim(l.contact_email)) <> lower(btrim(p_recipient_email)) then
    raise exception 'recipient must be the published business email on the lead';
  end if;
  if p_kind = 'initial' and (
      nullif(btrim(l.company_url), '') is null
      or nullif(btrim(l.location), '') is null) then
    raise exception 'company website and US location are required';
  end if;
  if not exists (select 1 from public.client_finder_deliverables
      where id = p_deliverable_id and active)
     or not exists (select 1 from public.client_finder_proofs
      where id = p_proof_id and active and verified_at is not null) then
    raise exception 'active deliverable and verified proof required';
  end if;
  if p_kind = 'initial' then
    if p_parent_message_id is not null then raise exception 'initial cannot have parent'; end if;
    perform pg_advisory_xact_lock(881101, day_key - date '2000-01-01');
    if (select count(*) from public.client_finder_messages
      where kind = 'initial' and (created_at at time zone 'Asia/Manila')::date = day_key) >= 5 then
      raise exception 'daily new-draft limit reached';
    end if;
  else
    select * into parent from public.client_finder_messages
      where id = p_parent_message_id and lead_id = p_lead_id
        and kind = 'initial' and status = 'sent';
    if not found or parent.recipient_email <> lower(btrim(p_recipient_email)) then
      raise exception 'follow-up requires confirmed initial message to same contact';
    end if;
  end if;
  insert into public.client_finder_messages (
    lead_id, kind, parent_message_id, recipient_email, subject, body,
    evidence, observed_need, deliverable_id, proof_id)
  values (p_lead_id, p_kind, p_parent_message_id, lower(btrim(p_recipient_email)),
    p_subject, p_body, p_evidence, p_observed_need, p_deliverable_id, p_proof_id)
  returning * into m;
  reason := public.client_finder_contact_block_reason(m.id);
  if reason is not null then raise exception 'contact blocked: %', reason; end if;
  if p_kind = 'initial' then
    evidence_at := (p_evidence->>'observed_at')::timestamptz;
    insert into public.client_finder_evidence
      (lead_id, evidence_kind, source_url, observed_at, fact_text)
    values
      (l.id, 'company', l.company_url, evidence_at, l.company_name),
      (l.id, 'us_location', p_evidence->>'us_location_source_url', evidence_at, l.location),
      (l.id, 'contact', p_evidence->>'contact_source_url', evidence_at, m.recipient_email),
      (l.id, 'need', p_evidence->>'observation_source_url', evidence_at, p_observed_need);
  end if;
  insert into public.client_finder_message_revisions (
    message_id, revision, recipient_email, subject, body, evidence,
    observed_need, deliverable_id, proof_id)
  values (m.id, 1, m.recipient_email, m.subject, m.body, m.evidence,
    m.observed_need, m.deliverable_id, m.proof_id);
  if p_kind = 'initial' and nullif(btrim(l.company_domain), '') is not null then
    update public.client_finder_research_tasks set status = 'qualified',
      qualified_at = now(), qualified_message_id = m.id
      where domain = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', '');
  end if;
  return m;
end;
$$;

-- RPC: create_due_followup(initial_message_id, subject, body). Copies the
-- initial message's evidence and verified catalog references, then delegates
-- all eligibility checks to create_message. The unique parent index permits
-- only one follow-up. This creates a draft and never approves or sends it.
create or replace function public._client_finder_create_due_followup(
  p_initial_message_id uuid, p_subject text, p_body text)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare parent public.client_finder_messages%rowtype;
begin
  select * into parent from public.client_finder_messages
    where id = p_initial_message_id for update;
  if not found or parent.kind <> 'initial' or parent.status <> 'sent'
     or parent.gmail_message_id is null or parent.gmail_thread_id is null then
    raise exception 'confirmed initial send required for follow-up';
  end if;
  return public._client_finder_create_message(
    parent.lead_id, parent.recipient_email, p_subject, p_body,
    parent.evidence, parent.observed_need, parent.deliverable_id,
    parent.proof_id, 'followup', parent.id);
end;
$$;

-- RPC: bind_card(message_id, revision, owner_user_id, chat_id, card_id).
-- Call after Telegram returns the ID for the full exact-message preview.
create or replace function public._client_finder_bind_card(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  if p_card_id is null or p_card_id <= 0 then raise exception 'card ID required'; end if;
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.revision <> p_revision or m.status <> 'draft' then
    raise exception 'draft or revision changed';
  end if;
  update public.client_finder_messages set
    status = 'pending_review', telegram_owner_user_id = p_owner_user_id,
    telegram_chat_id = p_chat_id, telegram_card_id = p_card_id,
    telegram_card_revision = p_revision, updated_at = now()
  where id = p_message_id returning * into m;
  return m;
end;
$$;

-- Internal step for the Edit button. Approval is disabled while the owner
-- supplies replacement content, and the same owner/card must submit it.
create or replace function public._client_finder_request_edit(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.status <> 'pending_review' or m.revision <> p_revision
     or m.telegram_card_revision <> p_revision
     or m.telegram_owner_user_id <> p_owner_user_id
     or m.telegram_chat_id <> p_chat_id or m.telegram_card_id <> p_card_id then
    raise exception 'stale or unauthorized card';
  end if;
  update public.client_finder_messages set status = 'edit_requested',
    updated_at = now() where id = m.id returning * into m;
  return m;
end;
$$;

-- RPC: edit_message(message_id, revision, owner_user_id, chat_id, card_id,
-- recipient_email, subject, body). Creates a new immutable revision and clears
-- the old card. The new exact preview needs bind_card before approval.
create or replace function public._client_finder_edit_message(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint, p_recipient_email text,
  p_subject text, p_body text)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
  l public.cold_leads%rowtype;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.status <> 'edit_requested' or m.revision <> p_revision
    or m.telegram_card_revision <> p_revision
    or m.telegram_owner_user_id <> p_owner_user_id
    or m.telegram_chat_id <> p_chat_id
    or m.telegram_card_id <> p_card_id then
    raise exception 'stale or unauthorized card';
  end if;
  select * into l from public.cold_leads where id = m.lead_id;
  if l.contact_email is null or lower(btrim(l.contact_email)) <> lower(btrim(p_recipient_email)) then
    raise exception 'edited recipient does not match published business email';
  end if;
  update public.client_finder_messages set
    revision = revision + 1, recipient_email = lower(btrim(p_recipient_email)),
    subject = p_subject, body = p_body, status = 'draft',
    telegram_card_id = null, telegram_card_revision = null,
    approved_revision = null, approved_at = null, updated_at = now()
  where id = p_message_id returning * into m;
  insert into public.client_finder_message_revisions (
    message_id, revision, recipient_email, subject, body, evidence,
    observed_need, deliverable_id, proof_id)
  values (m.id, m.revision, m.recipient_email, m.subject, m.body, m.evidence,
    m.observed_need, m.deliverable_id, m.proof_id);
  return m;
end;
$$;

-- RPC: skip_message(message_id, revision, owner_user_id, chat_id, card_id).
create or replace function public._client_finder_skip_message(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.status <> 'pending_review' or m.revision <> p_revision
     or m.telegram_card_revision <> p_revision
     or m.telegram_owner_user_id <> p_owner_user_id
     or m.telegram_chat_id <> p_chat_id or m.telegram_card_id <> p_card_id then
    raise exception 'stale or unauthorized card';
  end if;
  update public.client_finder_messages set status = 'skipped', updated_at = now()
    where id = p_message_id returning * into m;
  return m;
end;
$$;

-- RPC: suppress_contact(message_id, revision, owner_user_id, chat_id, card_id).
-- Keeps sent/unknown history, but prevents future delivery to this contact
-- and company. A claimed attempt is canceled; a started send needs reconciliation.
create or replace function public._client_finder_suppress_contact(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint)
returns void language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
  l public.cold_leads%rowtype;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.revision <> p_revision or m.telegram_card_revision <> p_revision
     or m.telegram_owner_user_id <> p_owner_user_id
     or m.telegram_chat_id <> p_chat_id or m.telegram_card_id <> p_card_id then
    raise exception 'stale or unauthorized card';
  end if;
  select * into l from public.cold_leads where id = m.lead_id;
  insert into public.client_finder_suppressions (scope, value, reason, source)
    values ('email', m.recipient_email, 'do_not_contact', 'telegram_owner')
    on conflict (scope, value) do nothing;
  if nullif(btrim(l.company_domain), '') is not null then
    insert into public.client_finder_suppressions (scope, value, reason, source)
      values ('domain', regexp_replace(lower(btrim(l.company_domain)), '^www[.]', ''), 'do_not_contact', 'telegram_owner')
      on conflict (scope, value) do nothing;
  end if;
  update public.client_finder_messages x set status = 'suppressed', updated_at = now()
    from public.cold_leads y where y.id = x.lead_id
      and x.status in ('draft', 'pending_review', 'edit_requested',
        'claimed', 'failed', 'skipped')
      and (x.recipient_email = m.recipient_email
        or (l.company_domain is not null and y.company_domain is not null
          and regexp_replace(lower(btrim(y.company_domain)), '^www[.]', '')
              = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', '')));
  update public.client_finder_send_attempts a set status = 'canceled',
    result_note = 'owner do not contact' where a.status = 'claimed'
    and a.message_id in (select x.id from public.client_finder_messages x
      join public.cold_leads y on y.id = x.lead_id
      where x.recipient_email = m.recipient_email
        or (l.company_domain is not null and y.company_domain is not null
          and regexp_replace(lower(btrim(y.company_domain)), '^www[.]', '')
              = regexp_replace(lower(btrim(l.company_domain)), '^www[.]', '')));
end;
$$;

-- RPC: claim_send(message_id, revision, owner_user_id, chat_id, card_id).
-- Approval and the immutable send attempt are one transaction. The n8n Gmail
-- path must use the returned attempt ID, then call begin_send immediately
-- before the provider request. No workflow may send from a message table row.
create or replace function public._client_finder_claim_send(
  p_message_id uuid, p_revision integer, p_owner_user_id bigint,
  p_chat_id bigint, p_card_id bigint)
returns public.client_finder_send_attempts
language plpgsql security definer set search_path = pg_catalog as $$
declare
  m public.client_finder_messages%rowtype;
  a public.client_finder_send_attempts%rowtype;
  s public.client_finder_settings%rowtype;
  day_key date := (now() at time zone 'Asia/Manila')::date;
  reason text;
begin
  perform public.client_finder_assert_owner(p_owner_user_id, p_chat_id);
  select * into s from public.client_finder_settings where id = 1 for update;
  if not found then raise exception 'settings missing'; end if;
  if not s.sending_enabled or s.inbox_monitor_verified_at < now() - interval '30 minutes'
     or s.inbox_monitor_verified_at is null
     or not exists (select 1 from public.client_finder_mail_monitor_state
       where id = 1 and last_success_at >= now() - interval '30 minutes'
         and scanned_through >= now() - interval '30 minutes')
     or nullif(btrim(s.sender_name), '') is null
     or nullif(btrim(s.sender_email), '') is null
     or nullif(btrim(s.postal_address), '') is null
     or nullif(btrim(s.commercial_label), '') is null
     or nullif(btrim(s.opt_out_route), '') is null then
    raise exception 'sending disabled or sender/inbox setup incomplete';
  end if;
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.status <> 'pending_review' or m.revision <> p_revision
     or m.telegram_card_revision <> p_revision
     or m.telegram_owner_user_id <> p_owner_user_id
     or m.telegram_chat_id <> p_chat_id or m.telegram_card_id <> p_card_id then
    raise exception 'stale or unauthorized approval';
  end if;
  if position(s.sender_name in m.body) = 0
     or position(s.postal_address in m.body) = 0
     or position(s.commercial_label in m.body) = 0
     or position(s.opt_out_route in m.body) = 0 then
    raise exception 'approved body is missing required sender/footer text';
  end if;
  reason := public.client_finder_contact_block_reason(m.id);
  if reason is not null then raise exception 'contact blocked: %', reason; end if;
  if not exists (select 1 from public.client_finder_proofs
     where id = m.proof_id and active and verified_at is not null) then
    raise exception 'proof no longer verified';
  end if;
  perform pg_advisory_xact_lock(881103, day_key - date '2000-01-01');
  if (select count(*) from public.client_finder_send_attempts
      where attempt_day = day_key) >= s.daily_send_limit then
    raise exception 'daily send-attempt limit reached';
  end if;
  insert into public.client_finder_send_attempts (
    message_id, revision, attempt_day, recipient_email, subject, body, status)
    values (m.id, m.revision, day_key, m.recipient_email, m.subject, m.body, 'claimed')
    returning * into a;
  update public.client_finder_messages set status = 'claimed',
    approved_revision = p_revision, approved_at = now(), updated_at = now()
    where id = m.id;
  return a;
end;
$$;

-- RPC: begin_send(attempt_id). This is the last database call before Gmail.
-- If a reply/suppression arrived after approval, no payload is returned.
create or replace function public._client_finder_begin_send(p_attempt_id uuid)
returns public.client_finder_send_attempts
language plpgsql security definer set search_path = pg_catalog as $$
declare
  a public.client_finder_send_attempts%rowtype;
  m public.client_finder_messages%rowtype;
  s public.client_finder_settings%rowtype;
  target_message_id uuid;
  reason text;
begin
  select message_id into target_message_id from public.client_finder_send_attempts
    where id = p_attempt_id;
  if not found then
    raise exception 'attempt already started or unavailable';
  end if;
  -- Lock message before attempt, matching owner suppression and inbox events.
  select * into m from public.client_finder_messages
    where id = target_message_id for update;
  select * into a from public.client_finder_send_attempts
    where id = p_attempt_id for update;
  if a.status <> 'claimed' then
    raise exception 'attempt already started or unavailable';
  end if;
  if m.status <> 'claimed' or m.approved_revision <> a.revision then
    raise exception 'approved revision changed';
  end if;
  if a.attempt_day <> (now() at time zone 'Asia/Manila')::date then
    update public.client_finder_send_attempts set status = 'canceled',
      result_note = 'approval expired at Manila midnight' where id = a.id;
    update public.client_finder_messages set status = 'draft',
      revision = revision + 1, telegram_card_id = null,
      telegram_card_revision = null, approved_revision = null,
      approved_at = null, updated_at = now()
      where id = m.id returning * into m;
    insert into public.client_finder_message_revisions (
      message_id, revision, recipient_email, subject, body, evidence,
      observed_need, deliverable_id, proof_id)
    values (m.id, m.revision, m.recipient_email, m.subject, m.body,
      m.evidence, m.observed_need, m.deliverable_id, m.proof_id);
    return null;
  end if;
  reason := public.client_finder_contact_block_reason(m.id);
  if reason is not null then
    update public.client_finder_send_attempts set status = 'canceled',
      result_note = reason where id = a.id;
    update public.client_finder_messages set
      status = case when reason = 'suppressed' then 'suppressed' else 'skipped' end,
      updated_at = now() where id = m.id;
    raise notice 'attempt canceled: %', reason;
    return null;
  end if;
  select * into s from public.client_finder_settings where id = 1;
  if not found then raise exception 'settings missing'; end if;
  if not s.sending_enabled or s.inbox_monitor_verified_at < now() - interval '30 minutes'
     or s.inbox_monitor_verified_at is null
     or not exists (select 1 from public.client_finder_mail_monitor_state
       where id = 1 and last_success_at >= now() - interval '30 minutes'
         and scanned_through >= now() - interval '30 minutes') then
    raise exception 'sending disabled or inbox monitor unhealthy';
  end if;
  if position(s.sender_name in a.body) = 0
     or position(s.postal_address in a.body) = 0
     or position(s.commercial_label in a.body) = 0
     or position(s.opt_out_route in a.body) = 0 then
    raise exception 'sender/footer configuration changed after approval';
  end if;
  update public.client_finder_send_attempts set status = 'sending',
    started_at = now() where id = a.id returning * into a;
  update public.client_finder_messages set status = 'sending', updated_at = now()
    where id = m.id;
  return a;
end;
$$;

-- RPC: complete_send(attempt_id, gmail_message_id, gmail_thread_id).
-- Also resolves send_unknown after a Sent-mail reconciliation. Provider IDs
-- must be present before the message is marked sent.
create or replace function public._client_finder_complete_send(
  p_attempt_id uuid, p_gmail_message_id text, p_gmail_thread_id text)
returns public.client_finder_send_attempts
language plpgsql security definer set search_path = pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype;
  m public.client_finder_messages%rowtype;
  target_message_id uuid;
begin
  if nullif(btrim(p_gmail_message_id), '') is null
     or nullif(btrim(p_gmail_thread_id), '') is null then
    raise exception 'Gmail message and thread IDs required';
  end if;
  select message_id into target_message_id from public.client_finder_send_attempts
    where id = p_attempt_id;
  if not found then raise exception 'attempt missing'; end if;
  select * into m from public.client_finder_messages
    where id = target_message_id for update;
  select * into a from public.client_finder_send_attempts
    where id = p_attempt_id for update;
  if not found then raise exception 'attempt missing'; end if;
  if a.status = 'sent' and a.gmail_message_id = p_gmail_message_id
     and a.gmail_thread_id = p_gmail_thread_id then return a; end if;
  if a.status not in ('sending', 'send_unknown') then
    raise exception 'attempt cannot be completed from state %', a.status;
  end if;
  update public.client_finder_send_attempts set status = 'sent',
    gmail_message_id = p_gmail_message_id, gmail_thread_id = p_gmail_thread_id,
    sent_at = now() where id = a.id returning * into a;
  update public.client_finder_messages set status = 'sent',
    gmail_message_id = p_gmail_message_id, gmail_thread_id = p_gmail_thread_id,
    sent_at = a.sent_at, updated_at = now() where id = m.id;
  if m.kind = 'initial' then
    update public.cold_leads set first_sent_at = coalesce(first_sent_at, a.sent_at),
      status = case when status in ('bounced', 'unsubscribed') then status else 'sent' end
      where id = m.lead_id;
  end if;
  return a;
end;
$$;

-- RPC: mark_send_unknown(attempt_id). Timeouts/crashes keep their daily slot.
-- No callback or workflow retry can create another attempt for this revision.
create or replace function public._client_finder_mark_send_unknown(p_attempt_id uuid)
returns public.client_finder_send_attempts
language plpgsql security definer set search_path = pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype;
  m public.client_finder_messages%rowtype;
  target_message_id uuid;
begin
  select message_id into target_message_id from public.client_finder_send_attempts
    where id = p_attempt_id;
  if not found then raise exception 'attempt missing'; end if;
  select * into m from public.client_finder_messages
    where id = target_message_id for update;
  select * into a from public.client_finder_send_attempts
    where id = p_attempt_id for update;
  if not found then raise exception 'attempt missing'; end if;
  if a.status = 'send_unknown' then return a; end if;
  if a.status not in ('claimed', 'sending') then
    raise exception 'attempt cannot become unknown from state %', a.status;
  end if;
  update public.client_finder_send_attempts set status = 'send_unknown',
    unknown_at = now(), result_note = 'check Gmail Sent before resolution'
    where id = a.id returning * into a;
  update public.client_finder_messages set status = 'send_unknown', updated_at = now()
    where id = a.message_id and status in ('claimed', 'sending');
  return a;
end;
$$;

-- RPC: mark_stale_attempts(). Run on a schedule to catch a crashed worker.
-- Unknown attempts require Sent-mail reconciliation and never auto-resend.
create or replace function public._client_finder_mark_stale_attempts()
returns integer language plpgsql security definer set search_path = pg_catalog as $$
declare
  candidate record;
  m public.client_finder_messages%rowtype;
  a public.client_finder_send_attempts%rowtype;
  n integer := 0;
begin
  for candidate in
    select id, message_id from public.client_finder_send_attempts
    where (status = 'claimed' and claimed_at < now() - interval '10 minutes')
       or (status = 'sending' and started_at < now() - interval '10 minutes')
    order by claimed_at, id
  loop
    -- Recheck after taking the same message-then-attempt locks as begin_send.
    select * into m from public.client_finder_messages
      where id = candidate.message_id for update;
    select * into a from public.client_finder_send_attempts
      where id = candidate.id for update;
    if (a.status = 'claimed' and a.claimed_at < now() - interval '10 minutes')
       or (a.status = 'sending' and a.started_at < now() - interval '10 minutes') then
      update public.client_finder_send_attempts set status = 'send_unknown',
        unknown_at = now(), result_note = 'worker stalled; check Gmail Sent'
        where id = a.id;
      update public.client_finder_messages set status = 'send_unknown',
        updated_at = now() where id = m.id and status in ('claimed', 'sending');
      n := n + 1;
    end if;
  end loop;
  return n;
end;
$$;

-- SQL-editor-only reconciliation after checking Gmail Sent and confirming no
-- message was accepted. A new revision/card/approval is required for any retry.
-- If Sent contains the message, use complete_send with its provider IDs.
create or replace function public.client_finder_resolve_unknown_not_sent(
  p_attempt_id uuid, p_reconciliation_note text)
returns public.client_finder_messages
language plpgsql security definer set search_path = pg_catalog as $$
declare a public.client_finder_send_attempts%rowtype;
  m public.client_finder_messages%rowtype;
  target_message_id uuid;
begin
  if nullif(btrim(p_reconciliation_note), '') is null then
    raise exception 'Gmail Sent reconciliation evidence required';
  end if;
  select message_id into target_message_id from public.client_finder_send_attempts
    where id = p_attempt_id;
  if not found then raise exception 'attempt is not awaiting reconciliation'; end if;
  select * into m from public.client_finder_messages
    where id = target_message_id for update;
  select * into a from public.client_finder_send_attempts
    where id = p_attempt_id for update;
  if not found or a.status <> 'send_unknown' then
    raise exception 'attempt is not awaiting reconciliation';
  end if;
  if m.status <> 'send_unknown' then
    raise exception 'message no longer awaiting reconciliation';
  end if;
  update public.client_finder_send_attempts set status = 'failed',
    result_note = p_reconciliation_note where id = a.id;
  update public.client_finder_messages set status = 'draft',
    revision = revision + 1, telegram_card_id = null,
    telegram_card_revision = null, approved_revision = null,
    approved_at = null, updated_at = now()
    where id = m.id returning * into m;
  insert into public.client_finder_message_revisions (
    message_id, revision, recipient_email, subject, body, evidence,
    observed_need, deliverable_id, proof_id)
  values (m.id, m.revision, m.recipient_email, m.subject, m.body, m.evidence,
    m.observed_need, m.deliverable_id, m.proof_id);
  return m;
end;
$$;

-- RPC: record_mail_poll(scanned_since, scanned_until, fetched_count).
-- Call only after all Gmail items in this interval were processed or surfaced
-- as owner-visible Needs checking. The next interval must overlap the last
-- completed one, so the monitor cannot silently skip a time range.
create or replace function public._client_finder_record_mail_poll(
  p_scanned_since timestamptz, p_scanned_until timestamptz,
  p_fetched_count integer)
returns public.client_finder_mail_monitor_state
language plpgsql security definer set search_path = pg_catalog as $$
declare state public.client_finder_mail_monitor_state%rowtype;
  first_attempt_at timestamptz;
begin
  if p_scanned_since is null or p_scanned_until is null
     or p_scanned_since >= p_scanned_until
     or p_scanned_until > now() + interval '1 minute'
     or p_fetched_count is null or p_fetched_count < 0 then
    raise exception 'invalid completed mailbox scan interval';
  end if;
  select * into state from public.client_finder_mail_monitor_state
    where id = 1 for update;
  if not found then raise exception 'mail monitor state missing'; end if;
  if state.scanned_through is null then
    select min(claimed_at) into first_attempt_at
      from public.client_finder_send_attempts;
    if first_attempt_at is not null and p_scanned_since > first_attempt_at then
      raise exception 'first mailbox scan starts after an outbound attempt';
    end if;
  elsif p_scanned_since > state.scanned_through then
    raise exception 'mailbox scan gap detected';
  end if;
  if state.scanned_through is not null
     and p_scanned_until <= state.scanned_through then
    return state;
  end if;
  update public.client_finder_mail_monitor_state set
    scanned_through = p_scanned_until, last_success_at = now(),
    last_fetched_count = p_fetched_count
    where id = 1 returning * into state;
  update public.client_finder_settings set inbox_monitor_verified_at = now(),
    updated_at = now() where id = 1;
  return state;
end;
$$;

-- RPC: record_mail_event(provider_event_id, message_id, event_type,
-- occurred_at, gmail_thread_id, original_gmail_message_id, sender_email,
-- bounced_recipient_email, event_note). Require an exact known Gmail
-- conversation match. A bounce requires the same thread plus an exact DSN
-- Final-Recipient; unmatched DSNs stay for owner review. Event IDs deduplicate.
create or replace function public._client_finder_record_mail_event(
  p_provider_event_id text, p_message_id uuid, p_event_type text,
  p_occurred_at timestamptz, p_gmail_thread_id text,
  p_original_gmail_message_id text, p_sender_email text,
  p_bounced_recipient_email text,
  p_event_note text default null)
returns boolean language plpgsql security definer set search_path = pg_catalog as $$
declare m public.client_finder_messages%rowtype;
  l public.cold_leads%rowtype;
  inserted_id text;
begin
  if nullif(btrim(p_provider_event_id), '') is null
     or p_event_type not in ('reply', 'bounce', 'optout')
     or p_occurred_at is null then
    raise exception 'valid mail event ID, type, and time required';
  end if;
  select * into m from public.client_finder_messages where id = p_message_id for update;
  if not found or m.status <> 'sent'
     or m.gmail_message_id is null or m.gmail_thread_id is null then
    raise exception 'mail event has no confirmed outbound message';
  end if;
  if p_gmail_thread_id is distinct from m.gmail_thread_id then
    raise exception 'mail event does not match the stored Gmail thread';
  end if;
  if p_original_gmail_message_id is not null
     and p_original_gmail_message_id is distinct from m.gmail_message_id then
    raise exception 'mail event supplied a different outbound Gmail message ID';
  end if;
  if p_event_type in ('reply', 'optout') and
     lower(btrim(p_sender_email)) is distinct from m.recipient_email then
    raise exception 'reply or opt-out sender does not match recipient';
  end if;
  if p_event_type = 'bounce' and (
       nullif(btrim(p_sender_email), '') is null
       or p_gmail_thread_id is distinct from m.gmail_thread_id
       or lower(btrim(p_bounced_recipient_email)) is distinct from m.recipient_email) then
    raise exception 'bounce needs exact thread, sender, and Final-Recipient';
  end if;
  select * into l from public.cold_leads where id = m.lead_id for update;
  insert into public.client_finder_mail_events (
    provider_event_id, message_id, event_type, occurred_at,
    gmail_thread_id, original_gmail_message_id, sender_email,
    bounced_recipient_email, event_note)
    values (p_provider_event_id, m.id, p_event_type, p_occurred_at,
      p_gmail_thread_id, p_original_gmail_message_id,
      lower(btrim(p_sender_email)),
      lower(btrim(p_bounced_recipient_email)), p_event_note)
    on conflict (provider_event_id) do nothing
    returning provider_event_id into inserted_id;
  if inserted_id is null then return false; end if;
  if p_event_type = 'reply' then
    update public.cold_leads set replied_at = coalesce(replied_at, p_occurred_at)
      where id = l.id;
  elsif p_event_type = 'bounce' then
    update public.cold_leads set status = 'bounced' where id = l.id;
    insert into public.client_finder_suppressions (scope, value, reason, source)
      values ('email', m.recipient_email, 'bounce', 'gmail_monitor')
      on conflict (scope, value) do nothing;
  else
    update public.cold_leads set status = 'unsubscribed' where id = l.id;
    insert into public.client_finder_suppressions (scope, value, reason, source)
      values ('email', m.recipient_email, 'optout', 'gmail_monitor')
      on conflict (scope, value) do nothing;
    if nullif(btrim(l.company_domain), '') is not null then
      insert into public.client_finder_suppressions (scope, value, reason, source)
        values ('domain', regexp_replace(lower(btrim(l.company_domain)), '^www[.]', ''), 'optout', 'gmail_monitor')
        on conflict (scope, value) do nothing;
    end if;
  end if;
  update public.client_finder_messages set
    status = case when p_event_type = 'optout' then 'suppressed' else 'skipped' end,
    updated_at = now()
    where lead_id = l.id and status in
      ('draft', 'pending_review', 'edit_requested', 'claimed');
  update public.client_finder_send_attempts set status = 'canceled',
    result_note = 'reply, bounce, or opt-out received'
    where status = 'claimed' and message_id in (
      select id from public.client_finder_messages where lead_id = l.id);
  return true;
end;
$$;

-- RPC: reserve_cost(idempotency_key, provider, operation, max_cost_cents).
-- All paid calls, including retries, reserve their maximum before execution.
create or replace function public._client_finder_reserve_cost(
  p_idempotency_key text, p_provider text, p_operation text,
  p_max_cost_cents numeric)
returns public.client_finder_cost_ledger
language plpgsql security definer set search_path = pg_catalog as $$
declare
  c public.client_finder_cost_ledger%rowtype;
  s public.client_finder_settings%rowtype;
  month_key date := date_trunc('month', now() at time zone 'Asia/Manila')::date;
  used_cents numeric;
begin
  if nullif(btrim(p_idempotency_key), '') is null
     or nullif(btrim(p_provider), '') is null
     or nullif(btrim(p_operation), '') is null
     or p_max_cost_cents is null or p_max_cost_cents < 0
     or p_max_cost_cents <> round(p_max_cost_cents, 4) then
    raise exception 'valid cost reservation fields required';
  end if;
  perform pg_advisory_xact_lock(881104, month_key - date '2000-01-01');
  select * into c from public.client_finder_cost_ledger
    where idempotency_key = p_idempotency_key for update;
  if found then
    if c.provider <> p_provider or c.operation <> p_operation
      or c.reserved_cents <> p_max_cost_cents then
      raise exception 'cost idempotency key reused with different operation';
    end if;
    if c.status <> 'reserved' then
      raise exception 'cost operation already started or resolved';
    end if;
    return c;
  end if;
  select * into s from public.client_finder_settings where id = 1;
  if not found then raise exception 'settings missing'; end if;
  select coalesce(sum(case when status in ('reserved', 'started') then reserved_cents
                           when status = 'settled' then actual_cents else 0 end), 0)
    into used_cents from public.client_finder_cost_ledger
    where budget_month = month_key;
  if used_cents + p_max_cost_cents > s.monthly_cost_cap_cents then
    raise exception 'monthly cost cap reached';
  end if;
  insert into public.client_finder_cost_ledger (
    idempotency_key, provider, operation, budget_month, reserved_cents, status)
    values (p_idempotency_key, p_provider, p_operation, month_key,
      p_max_cost_cents, 'reserved') returning * into c;
  return c;
end;
$$;

-- RPC: begin_cost_call(reservation_id). Must run immediately before a paid
-- provider request. It can succeed only once, so a retry needs a new reserve.
create or replace function public._client_finder_begin_cost_call(p_reservation_id uuid)
returns public.client_finder_cost_ledger
language plpgsql security definer set search_path = pg_catalog as $$
declare c public.client_finder_cost_ledger%rowtype;
begin
  select * into c from public.client_finder_cost_ledger
    where id = p_reservation_id for update;
  if not found or c.status <> 'reserved' then
    raise exception 'cost call already started or unavailable';
  end if;
  if c.budget_month <> date_trunc('month', now() at time zone 'Asia/Manila')::date then
    raise exception 'cost reservation is from a previous budget month';
  end if;
  update public.client_finder_cost_ledger set status = 'started', started_at = now()
    where id = c.id returning * into c;
  return c;
end;
$$;

-- RPC: settle_cost(reservation_id, actual_cents). Actual must fit the maximum
-- reserved before the call. An unknown provider result retains its reservation.
create or replace function public._client_finder_settle_cost(
  p_reservation_id uuid, p_actual_cents numeric)
returns public.client_finder_cost_ledger
language plpgsql security definer set search_path = pg_catalog as $$
declare c public.client_finder_cost_ledger%rowtype;
begin
  select * into c from public.client_finder_cost_ledger
    where id = p_reservation_id for update;
  if not found then raise exception 'reservation missing'; end if;
  if p_actual_cents is null or p_actual_cents < 0
     or p_actual_cents > c.reserved_cents
     or p_actual_cents <> round(p_actual_cents, 4) then
    raise exception 'actual cost exceeds reserved maximum';
  end if;
  if c.status = 'settled' and c.actual_cents = p_actual_cents then return c; end if;
  if c.status <> 'started' then raise exception 'provider call not started'; end if;
  update public.client_finder_cost_ledger set status = 'settled',
    actual_cents = p_actual_cents, settled_at = now()
    where id = c.id returning * into c;
  return c;
end;
$$;

-- RPC: release_cost(reservation_id). Only for a provider call that certainly
-- never started; otherwise leave funds reserved until reconciliation.
create or replace function public._client_finder_release_cost(p_reservation_id uuid)
returns public.client_finder_cost_ledger
language plpgsql security definer set search_path = pg_catalog as $$
declare c public.client_finder_cost_ledger%rowtype;
begin
  select * into c from public.client_finder_cost_ledger
    where id = p_reservation_id for update;
  if not found then raise exception 'reservation missing'; end if;
  if c.status = 'released' then return c; end if;
  if c.status <> 'reserved' then raise exception 'reservation already settled'; end if;
  update public.client_finder_cost_ledger set status = 'released',
    actual_cents = 0, settled_at = now() where id = c.id returning * into c;
  return c;
end;
$$;

-- Public RPC wrappers use the exact JSON argument keys expected by n8n and
-- PostgREST. The implementation functions remain private to the DB owner.
create or replace function public.client_finder_create_message(
  lead_id uuid, recipient_email text, subject text, body text,
  evidence jsonb, observed_need text, deliverable_id text, proof_id text,
  kind text default 'initial', parent_message_id uuid default null)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_create_message($1,$2,$3,$4,$5,$6,$7,$8,$9,$10));
$$;

create or replace function public.client_finder_pause_sending(reason text)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_pause_sending($1));
$$;

create or replace function public.client_finder_create_due_followup(
  initial_message_id uuid, subject text, body text)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_create_due_followup($1,$2,$3));
$$;

create or replace function public.client_finder_bind_card(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_bind_card($1,$2,$3,$4,$5));
$$;

create or replace function public.client_finder_request_edit(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_request_edit($1,$2,$3,$4,$5));
$$;

create or replace function public.client_finder_edit_message(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint, recipient_email text,
  subject text, body text)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_edit_message($1,$2,$3,$4,$5,$6,$7,$8));
$$;

create or replace function public.client_finder_skip_message(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_skip_message($1,$2,$3,$4,$5));
$$;

create or replace function public.client_finder_suppress_contact(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint)
returns void
language sql security definer set search_path = pg_catalog as $$
  select public._client_finder_suppress_contact($1,$2,$3,$4,$5);
$$;

create or replace function public.client_finder_claim_send(
  message_id uuid, revision integer, owner_user_id bigint,
  chat_id bigint, card_id bigint)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_claim_send($1,$2,$3,$4,$5));
$$;

create or replace function public.client_finder_begin_send(attempt_id uuid)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_begin_send($1));
$$;

create or replace function public.client_finder_complete_send(
  attempt_id uuid, gmail_message_id text, gmail_thread_id text)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_complete_send($1,$2,$3));
$$;

create or replace function public.client_finder_mark_send_unknown(attempt_id uuid)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_mark_send_unknown($1));
$$;

create or replace function public.client_finder_mark_stale_attempts()
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select jsonb_build_object('count', public._client_finder_mark_stale_attempts());
$$;

create or replace function public.client_finder_record_mail_poll(
  scanned_since timestamptz, scanned_until timestamptz, fetched_count integer)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_record_mail_poll($1,$2,$3));
$$;

create or replace function public.client_finder_record_mail_event(
  provider_event_id text, message_id uuid, event_type text,
  occurred_at timestamptz, gmail_thread_id text,
  original_gmail_message_id text, sender_email text,
  bounced_recipient_email text,
  event_note text default null)
returns boolean
language sql security definer set search_path = pg_catalog as $$
  select public._client_finder_record_mail_event($1,$2,$3,$4,$5,$6,$7,$8,$9);
$$;

create or replace function public.client_finder_reserve_cost(
  idempotency_key text, provider text, operation text,
  max_cost_cents numeric)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_reserve_cost($1,$2,$3,$4));
$$;

create or replace function public.client_finder_begin_cost_call(reservation_id uuid)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_begin_cost_call($1));
$$;

create or replace function public.client_finder_settle_cost(
  reservation_id uuid, actual_cents numeric)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_settle_cost($1,$2));
$$;

create or replace function public.client_finder_release_cost(reservation_id uuid)
returns jsonb
language sql security definer set search_path = pg_catalog as $$
  select to_jsonb(public._client_finder_release_cost($1));
$$;

-- Explicitly restrict every SECURITY DEFINER RPC to the backend service role.
revoke all on function public.client_finder_reject_immutable_change() from public, anon, authenticated, service_role;
revoke all on function public.client_finder_assert_owner(bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public.client_finder_contact_block_reason(uuid) from public, anon, authenticated, service_role;
revoke all on function public.client_finder_resolve_unknown_not_sent(uuid, text) from public, anon, authenticated, service_role;
revoke all on function public.client_finder_record_research_task(text, text, text, text, text) from public, anon, authenticated;
revoke all on function public._client_finder_pause_sending(text) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_create_message(uuid, text, text, text, jsonb, text, text, text, text, uuid) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_create_due_followup(uuid, text, text) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_bind_card(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_request_edit(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_edit_message(uuid, integer, bigint, bigint, bigint, text, text, text) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_skip_message(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_suppress_contact(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_claim_send(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_begin_send(uuid) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_complete_send(uuid, text, text) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_mark_send_unknown(uuid) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_mark_stale_attempts() from public, anon, authenticated, service_role;
revoke all on function public._client_finder_record_mail_poll(timestamptz, timestamptz, integer) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_record_mail_event(text, uuid, text, timestamptz, text, text, text, text, text) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_reserve_cost(text, text, text, numeric) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_begin_cost_call(uuid) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_settle_cost(uuid, numeric) from public, anon, authenticated, service_role;
revoke all on function public._client_finder_release_cost(uuid) from public, anon, authenticated, service_role;
revoke all on function public.client_finder_create_message(uuid, text, text, text, jsonb, text, text, text, text, uuid) from public, anon, authenticated;
revoke all on function public.client_finder_pause_sending(text) from public, anon, authenticated;
revoke all on function public.client_finder_create_due_followup(uuid, text, text) from public, anon, authenticated;
revoke all on function public.client_finder_bind_card(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated;
revoke all on function public.client_finder_request_edit(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated;
revoke all on function public.client_finder_edit_message(uuid, integer, bigint, bigint, bigint, text, text, text) from public, anon, authenticated;
revoke all on function public.client_finder_skip_message(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated;
revoke all on function public.client_finder_suppress_contact(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated;
revoke all on function public.client_finder_claim_send(uuid, integer, bigint, bigint, bigint) from public, anon, authenticated;
revoke all on function public.client_finder_begin_send(uuid) from public, anon, authenticated;
revoke all on function public.client_finder_complete_send(uuid, text, text) from public, anon, authenticated;
revoke all on function public.client_finder_mark_send_unknown(uuid) from public, anon, authenticated;
revoke all on function public.client_finder_mark_stale_attempts() from public, anon, authenticated;
revoke all on function public.client_finder_record_mail_poll(timestamptz, timestamptz, integer) from public, anon, authenticated;
revoke all on function public.client_finder_record_mail_event(text, uuid, text, timestamptz, text, text, text, text, text) from public, anon, authenticated;
revoke all on function public.client_finder_reserve_cost(text, text, text, numeric) from public, anon, authenticated;
revoke all on function public.client_finder_begin_cost_call(uuid) from public, anon, authenticated;
revoke all on function public.client_finder_settle_cost(uuid, numeric) from public, anon, authenticated;
revoke all on function public.client_finder_release_cost(uuid) from public, anon, authenticated;

grant execute on function public.client_finder_create_message(uuid, text, text, text, jsonb, text, text, text, text, uuid) to service_role;
grant execute on function public.client_finder_record_research_task(text, text, text, text, text) to service_role;
grant execute on function public.client_finder_pause_sending(text) to service_role;
grant execute on function public.client_finder_create_due_followup(uuid, text, text) to service_role;
grant execute on function public.client_finder_bind_card(uuid, integer, bigint, bigint, bigint) to service_role;
grant execute on function public.client_finder_request_edit(uuid, integer, bigint, bigint, bigint) to service_role;
grant execute on function public.client_finder_edit_message(uuid, integer, bigint, bigint, bigint, text, text, text) to service_role;
grant execute on function public.client_finder_skip_message(uuid, integer, bigint, bigint, bigint) to service_role;
grant execute on function public.client_finder_suppress_contact(uuid, integer, bigint, bigint, bigint) to service_role;
grant execute on function public.client_finder_claim_send(uuid, integer, bigint, bigint, bigint) to service_role;
grant execute on function public.client_finder_begin_send(uuid) to service_role;
grant execute on function public.client_finder_complete_send(uuid, text, text) to service_role;
grant execute on function public.client_finder_mark_send_unknown(uuid) to service_role;
grant execute on function public.client_finder_mark_stale_attempts() to service_role;
grant execute on function public.client_finder_record_mail_poll(timestamptz, timestamptz, integer) to service_role;
grant execute on function public.client_finder_record_mail_event(text, uuid, text, timestamptz, text, text, text, text, text) to service_role;
grant execute on function public.client_finder_reserve_cost(text, text, text, numeric) to service_role;
grant execute on function public.client_finder_begin_cost_call(uuid) to service_role;
grant execute on function public.client_finder_settle_cost(uuid, numeric) to service_role;
grant execute on function public.client_finder_release_cost(uuid) to service_role;

commit;
