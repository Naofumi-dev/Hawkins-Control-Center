-- Hawkins Client Finder: read-only live privilege check.
-- Run in the owned Supabase project's SQL Editor after migration 001.
-- Returns object names and PASS/BLOCK only; no lead or message data.
-- Expect 56 PASS rows (12 tables, 43 functions, one function-count check).

with expected_tables(name) as (
  values ('client_finder_settings'), ('client_finder_evidence'),
    ('client_finder_deliverables'), ('client_finder_proofs'),
    ('client_finder_research_tasks'), ('client_finder_suppressions'),
    ('client_finder_messages'), ('client_finder_message_revisions'),
    ('client_finder_send_attempts'), ('client_finder_mail_events'),
    ('client_finder_mail_monitor_state'), ('client_finder_cost_ledger')
), privs(priv) as (
  values ('SELECT'), ('INSERT'), ('UPDATE'), ('DELETE'),
    ('TRUNCATE'), ('REFERENCES'), ('TRIGGER')
), table_checks as (
  select 'table:' || e.name as item,
    case when c.oid is not null and c.relkind = 'r' and c.relrowsecurity
      and not exists (
        select 1 from privs v
        where coalesce(has_table_privilege('service_role', c.oid, v.priv), false)
          is distinct from (v.priv = 'SELECT' or
            (e.name in ('client_finder_evidence', 'client_finder_deliverables',
                        'client_finder_proofs') and v.priv in ('INSERT', 'UPDATE')))
          or coalesce(has_table_privilege('anon', c.oid, v.priv), false)
          or coalesce(has_table_privilege('authenticated', c.oid, v.priv), false)
      ) then 'PASS' else 'BLOCK' end as result
  from expected_tables e
  left join pg_class c on c.relnamespace = 'public'::regnamespace
                      and c.relname = e.name
), fn as (
  select p.oid, p.proname, p.prosecdef, p.proconfig
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public' and p.proname ~ '^_?client_finder_'
), function_checks as (
  select 'function:' || oid::regprocedure::text as item,
    case when prosecdef
      and coalesce('search_path=pg_catalog' = any(proconfig), false)
      and coalesce(has_function_privilege('service_role', oid, 'EXECUTE'), false)
        is not distinct from (left(proname, 1) <> '_' and proname not in
          ('client_finder_reject_immutable_change',
           'client_finder_assert_owner',
           'client_finder_contact_block_reason',
           'client_finder_resolve_unknown_not_sent'))
      and not coalesce(has_function_privilege('anon', oid, 'EXECUTE'), false)
      and not coalesce(has_function_privilege('authenticated', oid, 'EXECUTE'), false)
      then 'PASS' else 'BLOCK' end as result
  from fn
)
select item, result from table_checks
union all select item, result from function_checks
union all select 'function_count_43',
  case when count(*) = 43 then 'PASS' else 'BLOCK' end from fn
order by item;
