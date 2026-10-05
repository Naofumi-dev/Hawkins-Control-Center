-- Hawkins Client Finder: read-only aggregate check for the existing project.
-- Run in the SQL Editor of project mtdavgadkiiofwikzdtn after
-- db/preflight_existing.sql reports no BLOCK rows.
-- Returns counts only; no company, contact, domain, email, or message values.

with index_domain_counts as (
  select lower(company_domain) as key, count(*) as copies
  from public.cold_leads
  where company_domain is not null
  group by 1
), index_email_counts as (
  select lower(contact_email) as key, count(*) as copies
  from public.cold_leads
  where contact_email is not null
  group by 1
), canonical_domain_counts as (
  select regexp_replace(lower(btrim(company_domain)), '^www[.]', '') as key,
    count(*) as copies
  from public.cold_leads
  where nullif(btrim(company_domain), '') is not null
  group by 1
), normalized_email_counts as (
  select lower(btrim(contact_email)) as key, count(*) as copies
  from public.cold_leads
  where nullif(btrim(contact_email), '') is not null
  group by 1
)
select
  (select count(*) from public.cold_leads) as lead_count,
  (select count(*) from public.cold_leads where first_sent_at is not null)
    as previously_sent_count,
  (select count(*) from index_domain_counts where copies > 1)
    as duplicate_index_domain_groups,
  (select count(*) from index_email_counts where copies > 1)
    as duplicate_index_email_groups,
  (select count(*) from canonical_domain_counts where copies > 1)
    as duplicate_canonical_domain_groups,
  (select coalesce(sum(copies - 1), 0) from canonical_domain_counts where copies > 1)
    as extra_canonical_domain_rows,
  (select count(*) from normalized_email_counts where copies > 1)
    as duplicate_normalized_email_groups;
