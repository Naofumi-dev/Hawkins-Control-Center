-- Hawkins Client Finder: read-only preflight for Armageddon's existing project.
-- Run in the SQL Editor of project mtdavgadkiiofwikzdtn before 001_client_finder.sql.
-- This checks metadata only. It returns no lead names, domains, email addresses,
-- message bodies, or contact rows. BLOCK means resolve the issue before migration;
-- REVIEW means inspect the existing definition/state before re-running a migration.
-- The project should be backed up separately before any migration is applied.

with
required_tables(table_name) as (
  values ('cold_campaigns'::text), ('cold_leads'::text)
),
table_checks as (
  select t.table_name, c.oid, c.relkind
  from required_tables t
  left join pg_catalog.pg_namespace n on n.nspname = 'public'
  left join pg_catalog.pg_class c
    on c.relnamespace = n.oid and c.relname = t.table_name
),
-- Columns read or written by 001_client_finder.sql and client_finder/*.py.
required_columns(column_name, expected_type) as (
  values
    ('id', 'uuid'::pg_catalog.regtype),
    ('niche', 'text'::pg_catalog.regtype),
    ('db_source', 'text'::pg_catalog.regtype),
    ('company_name', 'text'::pg_catalog.regtype),
    ('company_domain', 'text'::pg_catalog.regtype),
    ('company_url', 'text'::pg_catalog.regtype),
    ('location', 'text'::pg_catalog.regtype),
    ('company_info', 'jsonb'::pg_catalog.regtype),
    ('contact_name', 'text'::pg_catalog.regtype),
    ('contact_title', 'text'::pg_catalog.regtype),
    ('contact_email', 'text'::pg_catalog.regtype),
    ('email_verified', 'boolean'::pg_catalog.regtype),
    ('verification_result', 'text'::pg_catalog.regtype),
    ('research_summary', 'text'::pg_catalog.regtype),
    ('enriched_at', 'timestamp with time zone'::pg_catalog.regtype),
    ('status', 'text'::pg_catalog.regtype),
    ('first_sent_at', 'timestamp with time zone'::pg_catalog.regtype),
    ('replied_at', 'timestamp with time zone'::pg_catalog.regtype)
),
column_checks as (
  select r.column_name, r.expected_type,
    a.atttypid::pg_catalog.regtype as actual_type
  from required_columns r
  left join table_checks t on t.table_name = 'cold_leads'
  left join pg_catalog.pg_attribute a
    on a.attrelid = t.oid and a.attname = r.column_name
      and a.attnum > 0 and not a.attisdropped
),
expected_indexes(index_name, indexed_column) as (
  values
    ('cold_leads_company_domain_uniq'::text, 'company_domain'::text),
    ('cold_leads_contact_email_uniq'::text, 'contact_email'::text)
),
index_checks as (
  select e.index_name, e.indexed_column, index_class.relkind as object_kind,
    i.indisunique, i.indisvalid,
    i.indisready, i.indnkeyatts, source_table.relname as source_table,
    pg_catalog.pg_get_expr(i.indexprs, i.indrelid) as key_expression,
    pg_catalog.pg_get_expr(i.indpred, i.indrelid) as predicate,
    pg_catalog.pg_get_indexdef(index_class.oid) as definition
  from expected_indexes e
  left join pg_catalog.pg_namespace n on n.nspname = 'public'
  left join pg_catalog.pg_class index_class
    on index_class.relnamespace = n.oid and index_class.relname = e.index_name
  left join pg_catalog.pg_index i
    on i.indexrelid = index_class.oid and index_class.relkind = 'i'
  left join pg_catalog.pg_class source_table on source_table.oid = i.indrelid
),
client_finder_objects as (
  select 'relation'::text as kind, c.relname::text as name
  from pg_catalog.pg_class c
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and (
    left(c.relname, 14) = 'client_finder_'
    or left(c.relname, 15) = '_client_finder_')
  union all
  select 'function', p.proname::text
  from pg_catalog.pg_proc p
  join pg_catalog.pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public' and (
    left(p.proname, 14) = 'client_finder_'
    or left(p.proname, 15) = '_client_finder_')
  union all
  select 'trigger', tr.tgname::text
  from pg_catalog.pg_trigger tr
  join pg_catalog.pg_class c on c.oid = tr.tgrelid
  join pg_catalog.pg_namespace n on n.oid = c.relnamespace
  where n.nspname = 'public' and (
    left(tr.tgname, 14) = 'client_finder_'
    or left(tr.tgname, 15) = '_client_finder_')
),
report as (
  select 'base_table'::text as check_kind, 'public.' || table_name as item,
    case when relkind in ('r', 'p') then 'PASS' else 'BLOCK' end as result,
    case when oid is null then 'Missing table'
      when relkind not in ('r', 'p') then 'Object exists but is not a table'
      else 'Table exists' end as detail
  from table_checks
  union all
  select 'cold_leads_column', column_name,
    case when actual_type = expected_type then 'PASS' else 'BLOCK' end,
    case when actual_type is null then 'Missing; expected ' || expected_type::text
      else 'Expected ' || expected_type::text || '; found ' || actual_type::pg_catalog.regtype::text end
  from column_checks
  union all
  select 'global_unique_index', index_name,
    case when object_kind is null then 'REVIEW'
      when object_kind <> 'i' then 'BLOCK'
      when definition is null then 'BLOCK'
      when source_table is distinct from 'cold_leads'
        or indisunique is distinct from true
        or indisvalid is distinct from true
        or indisready is distinct from true
        or indnkeyatts is distinct from 1
        or pg_catalog.regexp_replace(key_expression, '[[:space:]]', '', 'g')
             is distinct from 'lower(' || indexed_column || ')'
        or pg_catalog.regexp_replace(predicate, '[[:space:]()]', '', 'g')
             is distinct from indexed_column || 'ISNOTNULL'
      then 'BLOCK' else 'PASS' end,
    case when object_kind is null then 'Missing; migration would try to create it. Check aggregate duplicates first.'
      when object_kind <> 'i' then 'Expected index name belongs to another object type; migration cannot create this index.'
      when definition is null then 'Index metadata unavailable; inspect before migration.'
      else definition end
  from index_checks
  union all
  select 'existing_client_finder_objects', 'public.client_finder_* or public._client_finder_*',
    case when count(*) = 0 then 'PASS' else 'REVIEW' end,
    count(*)::text || ' objects already exist; inspect for partial/prior install before re-running migration'
  from client_finder_objects
  union all
  select 'lead_count_estimate', 'public.cold_leads', 'INFO',
    case when t.oid is null then 'Unavailable: table missing'
      else 'Approximate live rows: ' || coalesce(s.n_live_tup::text, 'unknown') ||
        '. Run the optional aggregate query below for exact lead and prior-send counts.' end
  from table_checks t
  left join pg_catalog.pg_stat_all_tables s on s.relid = t.oid
  where t.table_name = 'cold_leads'
)
select check_kind, item, result, detail
from report
order by case result when 'BLOCK' then 0 when 'REVIEW' then 1 else 2 end,
  check_kind, item;

-- OPTIONAL SECOND QUERY. Run only after the first query confirms that both
-- base tables and all required cold_leads columns exist. This returns aggregate
-- counts only: no domain, email, person, company, or message values.
--
-- with index_domain_counts as (
--   select lower(company_domain) as key, count(*) as copies
--   from public.cold_leads
--   where company_domain is not null
--   group by 1
-- ), index_email_counts as (
--   select lower(contact_email) as key, count(*) as copies
--   from public.cold_leads
--   where contact_email is not null
--   group by 1
-- ), canonical_domain_counts as (
--   select regexp_replace(lower(btrim(company_domain)), '^www[.]', '') as key,
--     count(*) as copies
--   from public.cold_leads
--   where nullif(btrim(company_domain), '') is not null
--   group by 1
-- ), normalized_email_counts as (
--   select lower(btrim(contact_email)) as key, count(*) as copies
--   from public.cold_leads
--   where nullif(btrim(contact_email), '') is not null
--   group by 1
-- )
-- select
--   (select count(*) from public.cold_leads) as lead_count,
--   (select count(*) from public.cold_leads where first_sent_at is not null)
--     as previously_sent_count,
--   (select count(*) from index_domain_counts where copies > 1)
--     as duplicate_index_domain_groups,
--   (select count(*) from index_email_counts where copies > 1)
--     as duplicate_index_email_groups,
--   (select count(*) from canonical_domain_counts where copies > 1)
--     as duplicate_canonical_domain_groups,
--   (select coalesce(sum(copies - 1), 0) from canonical_domain_counts where copies > 1)
--     as extra_canonical_domain_rows,
--   (select count(*) from normalized_email_counts where copies > 1)
--     as duplicate_normalized_email_groups;
