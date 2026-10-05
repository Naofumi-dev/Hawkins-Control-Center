-- Read only. Run in owned Hawkins mtdavgadkiiofwikzdtn after 004 and 005.
-- No email bodies, contacts, authentication tokens, or private settings returned.
with expected(name) as (values
 ('client_finder_mailboxes'),('client_finder_opportunities'),('client_finder_conversations'),
 ('client_finder_inbox_messages'),('client_finder_tasks'),('client_finder_agent_runs'),('client_finder_owner_actions'))
select e.name,
 case when c.relrowsecurity and has_table_privilege('service_role',c.oid,'SELECT')
   and not has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE')
   and not has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE')
   and not has_table_privilege('service_role',c.oid,'INSERT,UPDATE,DELETE') then 'PASS' else 'BLOCK' end as result
from expected e left join pg_class c on c.oid=to_regclass('public.'||e.name)
order by e.name;

select p.proname,
 case when p.prosecdef and 'search_path=pg_catalog'=any(p.proconfig)
   and not has_function_privilege('anon',p.oid,'EXECUTE')
   and not has_function_privilege('authenticated',p.oid,'EXECUTE') then 'PASS' else 'BLOCK' end as result
from pg_proc p join pg_namespace n on n.oid=p.pronamespace
where n.nspname='public' and (p.proname like 'client_finder_inbox_%' or p.proname like 'client_finder_reply_%'
 or p.proname like 'client_finder_task_%' or p.proname in ('client_finder_assert_web_owner','client_finder_invalidate_conversation',
 'client_finder_correct_classification','client_finder_set_stage','client_finder_conversation_suppress','client_finder_complete_reply','client_finder_workspace_status'))
order by p.proname;

select 'fixed_personal_identity_and_disabled_sending' as check_name,
 case when count(*)=1 and bool_and(m.email='armageddonvivas@gmail.com' and not m.replies_enabled
   and not s.sending_enabled and m.reply_limit<=20 and s.daily_send_limit<=5 and s.monthly_cost_cap_cents<=2500)
 then 'PASS' else 'BLOCK' end as result
from public.client_finder_mailboxes m cross join public.client_finder_settings s;

select 'legacy_history_preserved_compare_with_backup' as check_name,
 (select count(*) from public.cold_leads) as leads,
 (select count(*) from public.cold_campaigns) as campaigns,
 (select count(*) from public.client_finder_suppressions) as suppressions,
 (select count(*) from public.client_finder_send_attempts) as send_attempts;
