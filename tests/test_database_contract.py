"""Static contract checks for the Supabase migration.

These checks catch accidental removal of safety gates. They do not replace a
transactional run against the actual Supabase database.
"""

from pathlib import Path
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "db" / "001_client_finder.sql").read_text()
CATALOG_SQL = (ROOT / "db" / "002_catalog.sql").read_text()
CATALOG = json.loads((ROOT / "data" / "deliverables.json").read_text())


def function(name: str) -> str:
    match = re.search(
        rf"create or replace function public\.{re.escape(name)}\s*\(.*?\)"
        rf"\s*returns .*?\bas \$\$(.*?)\$\$;",
        SQL,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Missing or incomplete function: {name}")
    return match.group(1).lower()


def rpc_arguments(name: str) -> list[str]:
    match = re.search(
        rf"create or replace function public\.{re.escape(name)}\s*\((.*?)\)"
        rf"\s*returns",
        SQL,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Missing RPC: {name}")
    return [part.strip().split()[0] for part in match.group(1).split(",")]


class DatabaseContractTests(unittest.TestCase):
    def test_plpgsql_blocks_have_one_declare_section(self) -> None:
        # PostgreSQL rejects a second DECLARE keyword inside the same block.
        for block in SQL.split("$$")[1::2]:
            self.assertLessEqual(len(re.findall(r"(?im)^declare\b", block)), 1)

    def test_defaults_are_inert_and_singleton(self) -> None:
        self.assertRegex(SQL, r"id smallint primary key default 1 check \(id = 1\)")
        self.assertIn("discovery_enabled boolean not null default false", SQL)
        self.assertIn("sending_enabled boolean not null default false", SQL)
        self.assertIn("insert into public.client_finder_settings (id) values (1)", SQL)
        self.assertNotRegex(SQL.lower(), r"insert into public\.cold_campaigns")

    def test_postgrest_argument_names_match_workflows(self) -> None:
        self.assertEqual(
            rpc_arguments("client_finder_create_message"),
            ["lead_id", "recipient_email", "subject", "body", "evidence",
             "observed_need", "deliverable_id", "proof_id", "kind",
             "parent_message_id"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_claim_send"),
            ["message_id", "revision", "owner_user_id", "chat_id", "card_id"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_reserve_cost"),
            ["idempotency_key", "provider", "operation", "max_cost_cents"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_begin_cost_call"), ["reservation_id"]
        )
        self.assertEqual(
            rpc_arguments("client_finder_create_due_followup"),
            ["initial_message_id", "subject", "body"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_record_mail_event"),
            ["provider_event_id", "message_id", "event_type", "occurred_at",
             "gmail_thread_id", "original_gmail_message_id", "sender_email",
             "bounced_recipient_email", "event_note"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_record_mail_poll"),
            ["scanned_since", "scanned_until", "fetched_count"],
        )
        self.assertEqual(
            rpc_arguments("client_finder_record_research_task"),
            ["domain", "company_url", "company_name", "source_url", "reason"],
        )
        for name in ("client_finder_create_message", "client_finder_create_due_followup",
                     "client_finder_bind_card",
                     "client_finder_claim_send", "client_finder_reserve_cost",
                     "client_finder_begin_cost_call", "client_finder_settle_cost"):
            match = re.search(
                rf"create or replace function public\.{name}\(.*?\)\s*returns jsonb"
                rf".*?to_jsonb\(public\._{name}\(",
                SQL, re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(match, name)

    def test_draft_and_send_caps_are_atomic(self) -> None:
        create = function("_client_finder_create_message")
        claim = function("_client_finder_claim_send")
        self.assertIn("pg_advisory_xact_lock(881101", create)
        self.assertIn("kind = 'initial'", create)
        self.assertIn(">= 5", create)
        self.assertIn("at time zone 'asia/manila'", create)
        self.assertIn("pg_advisory_xact_lock(881103", claim)
        self.assertIn("attempt_day = day_key", claim)
        self.assertIn("s.daily_send_limit", claim)
        self.assertIn("daily_send_limit between 1 and 5", SQL)

    def test_edit_invalidates_old_card_and_approval(self) -> None:
        request_edit = function("_client_finder_request_edit")
        edit = function("_client_finder_edit_message")
        claim = function("_client_finder_claim_send")
        self.assertIn("status = 'edit_requested'", request_edit)
        self.assertIn("m.status <> 'edit_requested'", edit)
        self.assertIn("revision = revision + 1", edit)
        self.assertIn("telegram_card_id = null", edit)
        self.assertIn("approved_revision = null", edit)
        self.assertIn("m.status <> 'pending_review'", claim)
        self.assertIn("m.telegram_card_id <> p_card_id", claim)
        self.assertIn("m.telegram_chat_id <> p_chat_id", claim)
        self.assertIn("m.telegram_owner_user_id <> p_owner_user_id", claim)

    def test_contact_and_evidence_gates(self) -> None:
        create = function("_client_finder_create_message")
        contact = function("client_finder_contact_block_reason")
        claim = function("_client_finder_claim_send")
        begin = function("_client_finder_begin_send")
        for field in ("contact_source_url", "observation_source_url",
                      "us_location_source_url", "observed_at"):
            self.assertIn(field, create)
        self.assertIn("insert into public.client_finder_evidence", create)
        self.assertIn("verified_at is not null", create)
        self.assertIn("client_finder_suppressions", contact)
        self.assertIn("public.cold_leads x", contact)
        self.assertIn("l.replied_at is not null", contact)
        self.assertIn("followup_too_early", contact)
        self.assertIn("client_finder_contact_block_reason", claim)
        self.assertIn("client_finder_contact_block_reason", begin)
        self.assertIn("s.postal_address in m.body", claim)
        self.assertIn("s.opt_out_route in a.body", begin)

    def test_queued_legacy_contacts_and_in_flight_company_sends_block_outreach(self) -> None:
        contact = function("client_finder_contact_block_reason")
        claim = function("_client_finder_claim_send")
        begin = function("_client_finder_begin_send")
        for status in ("queued", "approved", "uploaded", "replied"):
            self.assertIn(f"'{status}'", contact)
        self.assertIn("x.lead_id <> l.id", contact)
        self.assertIn("a.status in ('claimed', 'sending', 'send_unknown', 'sent')", contact)
        self.assertIn("x.recipient_email = m.recipient_email", contact)
        self.assertIn("regexp_replace(lower(btrim(other_lead.company_domain))", contact)
        self.assertIn("client_finder_contact_block_reason", claim)
        self.assertIn("client_finder_contact_block_reason", begin)
        self.assertLess(claim.index("where id = 1 for update"),
                        claim.index("client_finder_contact_block_reason"))

    def test_followup_preserves_original_manila_send_time(self) -> None:
        contact = function("client_finder_contact_block_reason")
        self.assertIn("due_local := parent.sent_at at time zone 'asia/manila'", contact)
        self.assertIn("due_local := due_local + interval '1 day'", contact)
        self.assertIn("(now() at time zone 'asia/manila') < due_local", contact)
        self.assertNotIn("::date < due_day", contact)

    def test_send_state_transitions_lock_message_before_attempt(self) -> None:
        for name in ("_client_finder_begin_send", "_client_finder_complete_send",
                     "_client_finder_mark_send_unknown",
                     "client_finder_resolve_unknown_not_sent"):
            transition = function(name)
            self.assertLess(transition.index("where id = target_message_id for update"),
                            transition.index("where id = p_attempt_id for update"), name)
        stale = function("_client_finder_mark_stale_attempts")
        self.assertLess(stale.index("where id = candidate.message_id for update"),
                        stale.index("where id = candidate.id for update"))

    def test_missing_contact_research_queue_is_deduplicated_and_closed_on_qualification(self) -> None:
        record = function("client_finder_record_research_task")
        create = function("_client_finder_create_message")
        self.assertIn("create table if not exists public.client_finder_research_tasks", SQL)
        self.assertIn("domain text primary key", SQL)
        self.assertIn("status text not null default 'open'", SQL)
        self.assertIn("source_url text not null check (source_url ~ '^https?://')", SQL)
        self.assertIn("attempt_count integer not null default 1", SQL)
        self.assertIn("first_seen_at timestamptz not null default now()", SQL)
        self.assertIn("last_seen_at timestamptz not null default now()", SQL)
        self.assertIn("regexp_replace(lower(btrim(domain)), '^www[.]', '')", record)
        self.assertIn("on conflict on constraint client_finder_research_tasks_pkey do update", record)
        self.assertIn("attempt_count = public.client_finder_research_tasks.attempt_count + 1", record)
        self.assertIn("last_seen_at = now()", record)
        self.assertNotIn("status =", record.split("on conflict on constraint client_finder_research_tasks_pkey do update", 1)[1])
        self.assertIn("returns jsonb", SQL.split("create or replace function public.client_finder_record_research_task", 1)[1].split("$$;", 1)[0])
        self.assertIn("if p_kind = 'initial'", create)
        self.assertIn("update public.client_finder_research_tasks set status = 'qualified'", create)
        self.assertIn("qualified_message_id = m.id", create)
        self.assertIn("alter table public.client_finder_research_tasks enable row level security", SQL)
        self.assertIn("public.client_finder_research_tasks, public.client_finder_suppressions", SQL)
        self.assertNotIn("grant insert, update on public.client_finder_research_tasks", SQL)
        self.assertNotIn("client_finder_claim_send", record)
        self.assertIn("grant execute on function public.client_finder_record_research_task(text, text, text, text, text) to service_role", SQL)

    def test_send_attempts_cannot_silently_retry(self) -> None:
        begin = function("_client_finder_begin_send")
        complete = function("_client_finder_complete_send")
        unknown = function("_client_finder_mark_send_unknown")
        stale = function("_client_finder_mark_stale_attempts")
        self.assertIn("unique (message_id, revision)", SQL)
        self.assertIn(
            "references public.client_finder_message_revisions(message_id, revision)",
            SQL,
        )
        self.assertIn("attempt payload is immutable", SQL)
        self.assertIn("a.status <> 'claimed'", begin)
        self.assertIn("a.attempt_day <> (now() at time zone 'asia/manila')::date", begin)
        self.assertIn("gmail message and thread ids required", complete)
        self.assertIn("'send_unknown'", unknown)
        self.assertIn("status = 'claimed' and claimed_at", stale)
        self.assertIn("status = 'sending' and started_at", stale)
        self.assertIn("interval '10 minutes'", stale)
        self.assertIn(
            "jsonb_build_object('count', public._client_finder_mark_stale_attempts())",
            function("client_finder_mark_stale_attempts"),
        )
        reconcile = function("client_finder_resolve_unknown_not_sent")
        self.assertIn("a.status <> 'send_unknown'", reconcile)
        self.assertIn("revision = revision + 1", reconcile)
        self.assertNotIn(
            "grant execute on function public.client_finder_resolve_unknown_not_sent(",
            SQL,
        )

    def test_mail_events_dedupe_and_stop_followups(self) -> None:
        event = function("_client_finder_record_mail_event")
        due = function("_client_finder_create_due_followup")
        poll = function("_client_finder_record_mail_poll")
        self.assertIn("provider_event_id text primary key", SQL)
        self.assertIn("on conflict (provider_event_id) do nothing", event)
        self.assertIn("status = 'canceled'", event)
        self.assertIn("'optout'", event)
        self.assertIn("client_finder_suppressions", event)
        self.assertIn("p_gmail_thread_id is distinct from m.gmail_thread_id", event)
        self.assertIn("p_bounced_recipient_email", event)
        self.assertIn("p_sender_email", event)
        self.assertIn("parent.evidence", due)
        self.assertIn("'followup'", due)
        self.assertIn("mailbox scan gap detected", poll)
        self.assertIn("inbox_monitor_verified_at = now()", poll)
        self.assertIn("interval '30 minutes'", function("_client_finder_claim_send"))
        self.assertIn("interval '30 minutes'", function("_client_finder_begin_send"))

    def test_cost_reservation_has_hard_cap_and_single_start(self) -> None:
        reserve = function("_client_finder_reserve_cost")
        start = function("_client_finder_begin_cost_call")
        settle = function("_client_finder_settle_cost")
        release = function("_client_finder_release_cost")
        self.assertIn("monthly_cost_cap_cents between 1 and 2500", SQL)
        self.assertIn("reserved_cents numeric(12,4)", SQL)
        self.assertIn("actual_cents numeric(12,4)", SQL)
        self.assertIn("pg_advisory_xact_lock(881104", reserve)
        self.assertIn("used_cents + p_max_cost_cents > s.monthly_cost_cap_cents", reserve)
        self.assertIn("c.status <> 'reserved'", start)
        self.assertIn("c.budget_month <> date_trunc('month'", start)
        self.assertIn("status = 'started'", start)
        self.assertIn("c.status <> 'started'", settle)
        self.assertIn("p_actual_cents > c.reserved_cents", settle)
        self.assertIn("c.status <> 'reserved'", release)

    def test_service_role_only_rpc_access(self) -> None:
        for name in ("client_finder_create_message", "client_finder_bind_card",
                     "client_finder_request_edit", "client_finder_edit_message",
                     "client_finder_claim_send", "client_finder_begin_send",
                     "client_finder_complete_send", "client_finder_record_mail_event",
                     "client_finder_record_mail_poll", "client_finder_pause_sending",
                     "client_finder_create_due_followup",
                     "client_finder_record_research_task",
                     "client_finder_reserve_cost", "client_finder_begin_cost_call"):
            header = re.search(
                rf"create or replace function public\.{name}\(.*?\)"
                rf"\s*returns .*?set search_path = pg_catalog",
                SQL, re.IGNORECASE | re.DOTALL,
            )
            self.assertIsNotNone(header, name)
            self.assertIn(f"grant execute on function public.{name}(", SQL)
            self.assertIn(f"revoke all on function public.{name}(", SQL)
        self.assertIn("enable row level security", SQL)
        self.assertIn("from public, anon, authenticated, service_role", SQL)

    def test_pause_requires_manual_clear_before_reenable(self) -> None:
        pause = function("_client_finder_pause_sending")
        self.assertIn("sending_enabled = false", pause)
        self.assertIn("sending_pause_reason = left(p_reason, 500)", pause)
        self.assertIn("sending_pause_reason is null", SQL)

    def test_catalog_matches_draft_ids_and_stays_inactive(self) -> None:
        self.assertEqual(len(CATALOG), 4)
        for item in CATALOG:
            for value in (item["id"], item["deliverable"], item["proof_id"],
                          item["proof_title"], item["proof_claim"], item["proof_url"]):
                self.assertIn(str(value).replace("'", "''"), CATALOG_SQL)
        self.assertIn("'prototype', null, false", CATALOG_SQL)
        self.assertIn("'project', null, false", CATALOG_SQL)
        self.assertIn("on conflict (id) do nothing", CATALOG_SQL)
        self.assertNotIn("sending_enabled", CATALOG_SQL)


if __name__ == "__main__":
    unittest.main()
