-- Hawkins Client Finder read-only verification for the owned Supabase project.
-- Run AFTER 001_client_finder.sql and 002_catalog.sql. No contact details,
-- message bodies, credentials, or source pages are returned.
-- Both queries below must pass. The second one verifies that the catalog seed
-- ran, not only that migration 001 created its empty tables.

with required_objects(kind, name, exists_now) as (
  values
    ('table', 'client_finder_settings', to_regclass('public.client_finder_settings') is not null),
    ('table', 'client_finder_messages', to_regclass('public.client_finder_messages') is not null),
    ('table', 'client_finder_send_attempts', to_regclass('public.client_finder_send_attempts') is not null),
    ('table', 'client_finder_suppressions', to_regclass('public.client_finder_suppressions') is not null),
    ('table', 'client_finder_mail_events', to_regclass('public.client_finder_mail_events') is not null),
    ('table', 'client_finder_mail_monitor_state', to_regclass('public.client_finder_mail_monitor_state') is not null),
    ('table', 'client_finder_deliverables', to_regclass('public.client_finder_deliverables') is not null),
    ('table', 'client_finder_proofs', to_regclass('public.client_finder_proofs') is not null),
    ('function', 'client_finder_create_message', to_regprocedure('public.client_finder_create_message(uuid,text,text,text,jsonb,text,text,text,text,uuid)') is not null),
    ('function', 'client_finder_claim_send', to_regprocedure('public.client_finder_claim_send(uuid,integer,bigint,bigint,bigint)') is not null),
    ('function', 'client_finder_begin_send', to_regprocedure('public.client_finder_begin_send(uuid)') is not null),
    ('function', 'client_finder_complete_send', to_regprocedure('public.client_finder_complete_send(uuid,text,text)') is not null),
    ('function', 'client_finder_record_mail_event', to_regprocedure('public.client_finder_record_mail_event(text,uuid,text,timestamp with time zone,text,text,text,text,text)') is not null)
)
select kind, name, case when exists_now then 'PASS' else 'BLOCK' end as result
from required_objects
order by kind, name;

-- REQUIRED SECOND QUERY. Run after the first query reports all PASS. If a
-- required table is missing, this query errors and installation is incomplete.
-- Four seeded rows are required in each catalog, while sending stays off.
select 'catalog_seed' as check_kind, 'deliverables' as item,
  case when count(*) = 4 then 'PASS' else 'BLOCK' end as result,
  count(*)::text || ' of 4 required IDs present' as detail
from public.client_finder_deliverables
where id in ('client_application', 'proposal_preparation',
             'lead_follow_up', 'document_assistant')
union all
select 'catalog_seed', 'proofs',
  case when count(*) = 4 then 'PASS' else 'BLOCK' end,
  count(*)::text || ' of 4 required IDs present'
from public.client_finder_proofs
where id in ('workline', 'proposal-agent',
             'lead-intake-recovery', 'rfp-response-assistant')
union all
select 'research_safety', 'sending_disabled',
  case when count(*) = 1 and bool_and(not sending_enabled)
    then 'PASS' else 'BLOCK' end,
  count(*)::text || ' settings row(s); sending_enabled=' ||
    coalesce(bool_or(sending_enabled)::text, 'unknown')
from public.client_finder_settings;
