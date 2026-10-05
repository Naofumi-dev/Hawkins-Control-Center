-- Hawkins Client Finder catalog, matching data/deliverables.json.
-- Apply after 001_client_finder.sql. All entries start inactive; proof pages
-- must be opened and checked before setting a deliverable active and marking
-- its proof active with verified_at. Re-running preserves later review state.

begin;

insert into public.client_finder_deliverables (id, title, scope_text, active)
values
  ('client_application', 'Client application and portal',
   'a small client portal or internal tool with a clear review step', false),
  ('proposal_preparation', 'Proposal preparation',
   'a system that prepares a proposal draft from approved project notes and keeps the lead record current', false),
  ('lead_follow_up', 'Lead intake and follow-up',
   'a lead intake and follow-up system with reminders and a clear handoff to your team', false),
  ('document_assistant', 'Document and RFP assistant',
   'an assistant that gathers approved evidence and prepares a cited draft for human review', false)
on conflict (id) do nothing;

insert into public.client_finder_proofs
  (id, title, proof_url, claim_text, proof_kind, verified_at, active)
values
  ('workline', 'Workline',
   'https://armageddonvivas.cloud/work/workline',
   'I built an application desk for intake, review, and follow-up; its public preview shows the interface',
   'project', null, false),
  ('proposal-agent', 'Post-Call Proposal Builder',
   'https://armageddonvivas.cloud/work/proposal-agent',
   'I built an n8n workflow that prepares reviewable proposal drafts from approved call context',
   'project', null, false),
  ('lead-intake-recovery', 'Lead Management and Recovery System',
   'https://armageddonvivas.cloud/work/lead-intake-recovery',
   'I built GoHighLevel workflows for intake, qualification, reminders, missed calls, and no-shows',
   'project', null, false),
  ('rfp-response-assistant', 'RFP Response Assistant',
   'https://armageddonvivas.cloud/work/rfp-response-assistant',
   'I prototyped a workflow that validates RFP intake, uses approved evidence, and stops at human review',
   'prototype', null, false)
on conflict (id) do nothing;

commit;

-- Manual activation after opening all four public proof pages and checking
-- their visible claims against the rows above. HTTP 200 alone is insufficient.
-- Run this only after the review; it changes no campaign or sending setting.
-- begin;
-- update public.client_finder_proofs
--   set verified_at = now(), active = true, updated_at = now()
--   where id in ('workline', 'proposal-agent',
--                'lead-intake-recovery', 'rfp-response-assistant');
-- update public.client_finder_deliverables
--   set active = true, updated_at = now()
--   where id in ('client_application', 'proposal_preparation',
--                'lead_follow_up', 'document_assistant');
-- commit;
