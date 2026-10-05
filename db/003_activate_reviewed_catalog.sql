-- Hawkins Client Finder: activate only the four reviewed catalog entries.
-- The four public proof pages were rechecked on 2026-09-29 against the claims
-- seeded by 002_catalog.sql. Run after both postflight queries pass.
-- This does not enable discovery, sending, or any workflow.

begin;

update public.client_finder_proofs
set verified_at = coalesce(verified_at, now()), active = true,
    updated_at = now()
where id in ('workline', 'proposal-agent',
             'lead-intake-recovery', 'rfp-response-assistant');

update public.client_finder_deliverables
set active = true, updated_at = now()
where id in ('client_application', 'proposal_preparation',
             'lead_follow_up', 'document_assistant');

commit;

-- Read-only confirmation. All three rows must report PASS.
select 'reviewed_proofs' as item,
  case when count(*) = 4 and bool_and(active and verified_at is not null)
    then 'PASS' else 'BLOCK' end as result,
  count(*)::text || ' of 4 required proof IDs present' as detail
from public.client_finder_proofs
where id in ('workline', 'proposal-agent',
             'lead-intake-recovery', 'rfp-response-assistant')
union all
select 'deliverables',
  case when count(*) = 4 and bool_and(active)
    then 'PASS' else 'BLOCK' end,
  count(*)::text || ' of 4 required deliverable IDs present'
from public.client_finder_deliverables
where id in ('client_application', 'proposal_preparation',
             'lead_follow_up', 'document_assistant')
union all
select 'sending_disabled',
  case when count(*) = 1 and bool_and(not sending_enabled)
    then 'PASS' else 'BLOCK' end,
  count(*)::text || ' settings row(s); sending_enabled=' ||
    coalesce(bool_or(sending_enabled)::text, 'unknown')
from public.client_finder_settings;
