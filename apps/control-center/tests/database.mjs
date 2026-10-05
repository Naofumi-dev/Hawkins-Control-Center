import { PGlite } from "@electric-sql/pglite";
import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
process.on("uncaughtException", (e) => {
  console.error("FAIL:", e.message, e.where || "");
  process.exit(1);
});

const db = new PGlite();
const root = new URL("../../../", import.meta.url);
await db.exec(`
  create role anon; create role authenticated; create role service_role;
  create schema auth;
  create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
  create table public.cold_campaigns(id uuid primary key default gen_random_uuid(), name text);
  create table public.cold_leads(id uuid primary key default gen_random_uuid(), campaign_id uuid references cold_campaigns(id),
    company_name text, location text, company_domain text, company_url text, contact_name text, contact_email text, contact_title text,
    status text default 'new', first_sent_at timestamptz, replied_at timestamptz, created_at timestamptz default now());
`);
for (const name of [
  "001_client_finder.sql",
  "002_catalog.sql",
  "004_personal_inbox.sql",
  "005_conversation_replies.sql",
]) {
  const sql = await readFile(new URL("db/" + name, root), "utf8");
  try {
    await db.exec(sql);
  } catch (e) {
    console.error("Migration failed:", name, e.message);
    throw e;
  }
}
console.log("PASS: all migrations execute in embedded PostgreSQL");
const query = async (sql, values = []) => (await db.query(sql, values)).rows;
const rpc = async (name, args = {}) => {
  const keys = Object.keys(args);
  return (
    await query(
      `select public.${name}(${keys.map((k, i) => `${k} := $${i + 1}`).join(",")}) as result`,
      Object.values(args),
    )
  )[0].result;
};
const reject = async (fn, pattern) => {
  let caught = false;
  try {
    await fn();
  } catch (e) {
    caught = true;
    assert.match(e.message, pattern);
  }
  assert.equal(caught, true, "expected operation to fail");
};
const footer = "\n\nTest Owner\n10 Test Lane\nBusiness services\nReply stop";
const actor = "11111111-1111-4111-8111-111111111111";
await query(
  `insert into auth.users values($1,'armageddonvivas@gmail.com',now())`,
  [actor],
);
const email = (id, overrides = {}) => ({
  provider_id: id,
  thread_id: "thread-" + id,
  channel: "gmail",
  direction: "in",
  sender: `${id}@agency.example`,
  recipients: ["armageddonvivas@gmail.com"],
  subject: "Project question",
  body: "Please send the proposal.",
  occurred_at: new Date().toISOString(),
  rfc_message_id: `<${id}@agency.example>`,
  acquisition_source: "direct",
  reply_email: `${id}@agency.example`,
  reply_verified: true,
  classification: {
    category: "direct_client",
    intent: "proposal_requested",
    reason: "Known conversation",
  },
  ...overrides,
});

await reject(
  () =>
    rpc("client_finder_inbox_start", { mailbox_email: "another@example.com" }),
  /wrong_mailbox/,
);
const lease = await rpc("client_finder_inbox_start", {
  mailbox_email: "armageddonvivas@gmail.com",
});
await reject(
  () =>
    rpc("client_finder_inbox_start", {
      mailbox_email: "armageddonvivas@gmail.com",
    }),
  /sync_in_progress/,
);
await rpc("client_finder_inbox_finish", {
  lease_id: lease.lease_id,
  history_id: null,
  fetched_count: 0,
  error_code: "failure",
});
assert.equal(
  (await query("select history_id from client_finder_mailboxes"))[0].history_id,
  null,
);
console.log("PASS: identity, lease, failed checkpoint");

const first = await rpc("client_finder_inbox_ingest", { item: email("first") });
assert.equal(
  (await rpc("client_finder_inbox_ingest", { item: email("first") })).status,
  "duplicate",
);
assert.equal(
  (await query("select count(*)::int n from client_finder_tasks"))[0].n,
  2,
);
await rpc("client_finder_correct_classification", {
  conversation_id: first.conversation_id,
  category: "other",
  reason: "Owner correction",
  actor,
});
await rpc("client_finder_inbox_ingest", {
  item: email("second", {
    thread_id: "thread-first",
    sender: "first@agency.example",
    reply_email: "first@agency.example",
  }),
});
assert.equal(
  (
    await query(
      "select category from client_finder_conversations where id=$1",
      [first.conversation_id],
    )
  )[0].category,
  "other",
);
console.log("PASS: event/task deduplication and persistent owner correction");

const imported = await rpc("client_finder_inbox_ingest", {
  item: email("platform", {
    channel: "onlinejobs_import",
    thread_id: "",
    platform_reference: "https://www.onlinejobs.ph/messages/123",
    acquisition_source: "onlinejobs",
    imported_by: actor,
    classification: {
      category: "onlinejobs_conversation",
      intent: "loom_requested",
      reason: "Owner import",
    },
  }),
});
const direct = await rpc("client_finder_inbox_ingest", {
  item: email("moved", {
    reply_email: "platform@agency.example",
    sender: "platform@agency.example",
  }),
});
const linked = await query(
  "select acquisition_source,opportunity_id from client_finder_conversations where id in ($1,$2)",
  [imported.conversation_id, direct.conversation_id],
);
assert.equal(linked[0].opportunity_id, linked[1].opportunity_id);
assert.ok(linked.every((x) => x.acquisition_source === "onlinejobs"));
await reject(
  () =>
    rpc("client_finder_reply_save", {
      conversation_id: imported.conversation_id,
      expected_revision: 0,
      subject: "Loom",
      body: "Here is a demo",
      actor,
    }),
  /verified_loom_required/,
);
console.log("PASS: OnlineJobs origin retained and Loom proof required");

const reply = await rpc("client_finder_reply_save", {
  conversation_id: direct.conversation_id,
  expected_revision: 0,
  subject: "Re: Project question",
  body: "Thanks. What is the agreed scope?\n\nArma" + footer,
  actor,
});
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: reply.id,
      revision: 1,
      via: "web",
      actor,
    }),
  /reply_sending_disabled/,
);
await query(
  `update client_finder_mailboxes set replies_enabled=true,last_success_at=now(),verified_at=now(),error_code=null`,
);
await query(
  "update client_finder_settings set sender_email='armageddonvivas@gmail.com',sender_name='Test Owner',postal_address='10 Test Lane',commercial_label='Business services',opt_out_route='Reply stop'",
);
const attempt = await rpc("client_finder_reply_approve", {
  message_id: reply.id,
  revision: 1,
  via: "web",
  actor,
});
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: reply.id,
      revision: 1,
      via: "web",
      actor,
    }),
  /stale_approval/,
);
await rpc("client_finder_inbox_ingest", {
  item: email("new-context", {
    thread_id: "thread-moved",
    reply_email: "platform@agency.example",
    sender: "platform@agency.example",
  }),
});
await reject(
  () => rpc("client_finder_reply_begin", { attempt_id: attempt.id }),
  /attempt_unavailable/,
);
assert.equal(
  (
    await query("select status from client_finder_send_attempts where id=$1", [
      attempt.id,
    ])
  )[0].status,
  "canceled",
);
console.log(
  "PASS: disabled sends, duplicate approval, newer correspondence cancels reserved send",
);

const pending = await rpc("client_finder_reply_save", {
  conversation_id: direct.conversation_id,
  expected_revision: 0,
  subject: "Re: Project question",
  body: "Thank you.\n\nArma" + footer,
  actor,
});
const pending2 = await rpc("client_finder_reply_save", {
  conversation_id: direct.conversation_id,
  expected_revision: 1,
  subject: "Re: Project question",
  body: "Thanks for the details.\n\nArma" + footer,
  actor,
});
assert.equal(pending2.revision, 2);
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: pending.id,
      revision: 1,
      via: "web",
      actor,
    }),
  /stale_approval/,
);
const a2 = await rpc("client_finder_reply_approve", {
  message_id: pending.id,
  revision: 2,
  via: "web",
  actor,
});
await rpc("client_finder_reply_begin", { attempt_id: a2.id });
await rpc("client_finder_mark_send_unknown", { attempt_id: a2.id });
await reject(
  () =>
    rpc("client_finder_reply_save", {
      conversation_id: direct.conversation_id,
      expected_revision: 2,
      subject: "Re: Project question",
      body: "Try again",
      actor,
    }),
  /already_reserved_or_sent/,
);
await reject(
  () =>
    query("update client_finder_send_attempts set body=$1 where id=$2", [
      "changed",
      a2.id,
    ]),
  /immutable/,
);
await rpc("client_finder_complete_reply", {
  attempt_id: a2.id,
  gmail_message_id: "sent-confirmed",
  gmail_thread_id: "thread-moved",
});
console.log(
  "PASS: edited approval invalidation, unknown-send protection, immutable payload, reconciliation",
);

const opp = linked[0].opportunity_id;
await reject(
  () =>
    rpc("client_finder_set_stage", {
      opportunity_id: opp,
      stage: "won",
      note: "",
      actor,
    }),
  /evidence_required/,
);
await reject(
  () =>
    rpc("client_finder_set_stage", {
      opportunity_id: opp,
      stage: "onboarding",
      note: "",
      actor,
    }),
  /confirm_won_first/,
);
await rpc("client_finder_set_stage", {
  opportunity_id: opp,
  stage: "won",
  note: "Owner confirmed accepted agreement",
  actor,
});
await rpc("client_finder_set_stage", {
  opportunity_id: opp,
  stage: "won",
  note: "Confirmed again",
  actor,
});
assert.equal(
  (
    await query(
      "select count(*)::int n from client_finder_tasks where agent='Joyce'",
    )
  )[0].n,
  1,
);
console.log("PASS: owner-confirmed win, onboarding task deduplication");

// Current context, manual sends, and restored Gmail messages.
const createReply = async (id) => {
  const inbound = await rpc("client_finder_inbox_ingest", { item: email(id) });
  const draft = await rpc("client_finder_reply_save", {
    conversation_id: inbound.conversation_id,
    expected_revision: 0,
    subject: "Re: Project question",
    body: "Thanks for the details." + footer,
    actor,
  });
  return { inbound, draft };
};
const manual = await createReply("manual");
const ma = await rpc("client_finder_reply_approve", {
  message_id: manual.draft.id,
  revision: 1,
  via: "web",
  actor,
});
await rpc("client_finder_inbox_ingest", {
  item: email("manual-sent", {
    thread_id: "thread-manual",
    direction: "out",
    sender: "armageddonvivas@gmail.com",
    reply_email: "manual@agency.example",
    reply_verified: false,
    occurred_at: new Date(Date.now() + 1000).toISOString(),
  }),
});
assert.equal(
  (
    await query("select status from client_finder_send_attempts where id=$1", [
      ma.id,
    ])
  )[0].status,
  "canceled",
);
await rpc("client_finder_inbox_delete", { provider_id: "manual" });
await rpc("client_finder_inbox_ingest", { item: email("manual") });
assert.equal(
  (
    await query(
      "select deleted_at from client_finder_inbox_messages where provider_id='manual'",
    )
  )[0].deleted_at,
  null,
);
assert.equal(
  (
    await query(
      "select count(*)::int n from client_finder_tasks where agent='Max'",
    )
  )[0].n,
  1,
);
assert.ok(
  (
    await query(
      "select due_at > now()+interval '4 days' as future from client_finder_tasks where agent='Max'",
    )
  )[0].future,
);
console.log(
  "PASS: manual outgoing invalidates approvals, restored messages, five-weekday reminder",
);

await query(
  "update client_finder_settings set owner_telegram_user_id=101,owner_telegram_chat_id=101",
);
const telegram = await createReply("telegram");
await rpc("client_finder_reply_bind_card", {
  message_id: telegram.draft.id,
  revision: 1,
  card_id: 202,
  owner_user_id: 101,
  chat_id: 101,
});
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: telegram.draft.id,
      revision: 1,
      via: "telegram",
      actor: "telegram:999",
      telegram_user_id: 999,
      telegram_chat_id: 101,
      telegram_card_id: 202,
    }),
  /owner/,
);
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: telegram.draft.id,
      revision: 1,
      via: "telegram",
      actor: "telegram:101",
      telegram_user_id: 101,
      telegram_chat_id: 101,
      telegram_card_id: 201,
    }),
  /stale_card/,
);
const ta = await rpc("client_finder_reply_approve", {
  message_id: telegram.draft.id,
  revision: 1,
  via: "telegram",
  actor: "telegram:101",
  telegram_user_id: 101,
  telegram_chat_id: 101,
  telegram_card_id: 202,
});
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: telegram.draft.id,
      revision: 1,
      via: "web",
      actor,
    }),
  /stale_approval/,
);
await rpc("client_finder_conversation_suppress", {
  conversation_id: telegram.inbound.conversation_id,
  actor,
});
assert.equal(
  (
    await query("select status from client_finder_send_attempts where id=$1", [
      ta.id,
    ])
  )[0].status,
  "canceled",
);
console.log(
  "PASS: Telegram owner/card checks, shared web approval, suppression after approval",
);

const limit = await createReply("limit");
const used = (
  await query(
    "select count(*)::int n from client_finder_send_attempts where send_class='reply'",
  )
)[0].n;
await query("update client_finder_mailboxes set reply_limit=$1", [used]);
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: limit.draft.id,
      revision: 1,
      via: "web",
      actor,
    }),
  /reply_daily_limit/,
);
await query("update client_finder_mailboxes set reply_limit=20");
const coldDef = (
  await query(
    "select pg_get_functiondef('public._client_finder_claim_send(uuid,integer,bigint,bigint,bigint)'::regprocedure) as def",
  )
)[0].def;
assert.ok(coldDef.includes("send_class = 'outreach'"));
assert.equal(
  (await query("select daily_send_limit from client_finder_settings"))[0]
    .daily_send_limit,
  5,
);
const competing = await Promise.allSettled([
  rpc("client_finder_reply_approve", {
    message_id: limit.draft.id,
    revision: 1,
    via: "web",
    actor,
  }),
  rpc("client_finder_reply_approve", {
    message_id: limit.draft.id,
    revision: 1,
    via: "web",
    actor,
  }),
]);
assert.equal(competing.filter((r) => r.status === "fulfilled").length, 1);
console.log(
  "PASS: reply cap includes canceled/uncertain attempts, separate outreach bucket, duplicate competing approvals",
);

const lastSlotA = await createReply("last-slot-a"),
  lastSlotB = await createReply("last-slot-b");
const nowUsed = (
  await query(
    "select count(*)::int n from client_finder_send_attempts where send_class='reply'",
  )
)[0].n;
await query("update client_finder_mailboxes set reply_limit=$1", [nowUsed + 1]);
const lastSlot = await Promise.allSettled(
  [lastSlotA, lastSlotB].map((x) =>
    rpc("client_finder_reply_approve", {
      message_id: x.draft.id,
      revision: 1,
      via: "web",
      actor,
    }),
  ),
);
assert.equal(lastSlot.filter((r) => r.status === "fulfilled").length, 1);
await query("update client_finder_mailboxes set reply_limit=20");
console.log(
  "PASS: competing distinct messages cannot exceed the last available reply slot (serialized embedded database)",
);

const legacy = (
  await query(
    "insert into cold_leads(company_name,contact_email,first_sent_at) values('Synthetic prior campaign','known@agency.example',now()-interval '7 days') returning id",
  )
)[0];
const known = await rpc("client_finder_inbox_ingest", {
  item: email("known", {
    classification: {
      category: "needs_review",
      intent: "reply",
      reason: "Human reply to an older campaign",
    },
  }),
});
const knownRow = (
  await query(
    "select c.category,o.lead_id from client_finder_conversations c join client_finder_opportunities o on o.id=c.opportunity_id where c.id=$1",
    [known.conversation_id],
  )
)[0];
assert.equal(knownRow.category, "direct_client");
assert.equal(knownRow.lead_id, legacy.id);
assert.equal(
  (await query("select status from cold_leads where id=$1", [legacy.id]))[0]
    .status,
  "replied",
);
for (const suffix of ["a", "b"])
  await rpc("client_finder_inbox_ingest", {
    item: email("ambiguous-" + suffix, {
      channel: "onlinejobs_import",
      thread_id: "",
      platform_reference:
        "https://www.onlinejobs.ph/messages/ambiguous-" + suffix,
      acquisition_source: "onlinejobs",
      imported_by: actor,
      reply_email: "two-projects@agency.example",
      classification: {
        category: "onlinejobs_conversation",
        intent: "question",
        reason: "Owner imported another project",
      },
    }),
  });
const ambiguous = await rpc("client_finder_inbox_ingest", {
  item: email("ambiguous-direct", {
    reply_email: "two-projects@agency.example",
  }),
});
const ambiguity = (
  await query(
    "select category,opportunity_id from client_finder_conversations where id=$1",
    [ambiguous.conversation_id],
  )
)[0];
assert.equal(ambiguity.category, "needs_review");
assert.equal(ambiguity.opportunity_id, null);
console.log(
  "PASS: legacy contact history linkage and ambiguous cross-channel matching",
);

const task = await rpc("client_finder_task_claim");
assert.ok(task.lease_id);
await rpc("client_finder_task_finish", {
  task_id: task.id,
  lease_id: task.lease_id,
  result: null,
  blocker: "Provider unavailable",
});
await rpc("client_finder_task_action", {
  task_id: task.id,
  action: "retry",
  actor,
});
const retry = await rpc("client_finder_task_claim");
assert.equal(retry.id, task.id);
assert.equal(retry.attempts, 2);
await rpc("client_finder_task_finish", {
  task_id: retry.id,
  lease_id: retry.lease_id,
  result: { summary: "Reviewed" },
  blocker: null,
});
await reject(
  () =>
    rpc("client_finder_task_action", {
      task_id: task.id,
      action: "retry",
      actor,
    }),
  /task_not_retryable/,
);
assert.equal(
  (
    await query(
      "select count(*)::int n from client_finder_agent_runs where task_id=$1",
      [task.id],
    )
  )[0].n,
  2,
);
const reserved = await rpc("client_finder_reserve_cost", {
  idempotency_key: "cap-test",
  provider: "openrouter",
  operation: "synthetic",
  max_cost_cents: 2500,
});
await rpc("client_finder_begin_cost_call", { reservation_id: reserved.id });
await reject(
  () =>
    rpc("client_finder_reserve_cost", {
      idempotency_key: "cap-overflow",
      provider: "brave",
      operation: "synthetic",
      max_cost_cents: 0.5,
    }),
  /monthly cost cap/,
);
console.log(
  "PASS: failed agent runs, explicit retry, recorded attempts, shared hard cost cap",
);

// Applying the two additive migrations again preserves data and disabled defaults.
for (const name of ["004_personal_inbox.sql", "005_conversation_replies.sql"])
  await db.exec(await readFile(new URL("db/" + name, root), "utf8"));
assert.equal(
  (
    await query(
      "select count(*)::int n from client_finder_agent_runs where task_id=$1",
      [task.id],
    )
  )[0].n,
  2,
);
console.log("PASS: additive migration reapply preserves stored records");

const postflight = await db.exec(
  await readFile(new URL("db/postflight_personal.sql", root), "utf8"),
);
// This fixture intentionally enables replies for behavior checks. Restore both
// flags only for the pre-activation postflight assertion.
await query("update client_finder_mailboxes set replies_enabled=false");
const disabledPostflight = await db.exec(
  await readFile(new URL("db/postflight_personal.sql", root), "utf8"),
);
assert.ok(
  disabledPostflight
    .flatMap((r) => r.rows)
    .filter((r) => r.result)
    .every((r) => r.result === "PASS"),
);
console.log("PASS: read-only personal postflight SQL and permissions");

await db.exec("set role authenticated");
await reject(
  () => query("select * from client_finder_inbox_messages"),
  /permission denied/,
);
await reject(
  () =>
    rpc("client_finder_reply_approve", {
      message_id: pending.id,
      revision: 2,
      via: "web",
      actor,
    }),
  /permission denied/,
);
await db.exec("reset role");
console.log(
  "PASS: browser cannot directly read private inbox or invoke send authority",
);
await db.close();
