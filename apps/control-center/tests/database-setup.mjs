// Synthetic PostgreSQL execution of the backup helper's exact migration bundle.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { PGlite } from "@electric-sql/pglite";

const root = new URL("../../../", import.meta.url);
const generated = spawnSync(
  "python3",
  ["-c", "from client_finder.database_setup import migration_bundle; print(migration_bundle({'leads':0,'campaigns':0,'suppressions':0,'send_attempts':0}))"],
  { cwd: fileURLToPath(root), encoding: "utf8" },
);
assert.equal(generated.status, 0, "migration bundle must generate without credentials");
const sql = generated.stdout;
const db = new PGlite();
try {
  await db.exec(`
    create role anon; create role authenticated; create role service_role;
    create schema auth;
    create table auth.users(id uuid primary key,email text,email_confirmed_at timestamptz);
    create table public.cold_campaigns(id uuid primary key default gen_random_uuid(), name text);
    create table public.cold_leads(id uuid primary key default gen_random_uuid(), campaign_id uuid references cold_campaigns(id),
      company_name text, location text, company_domain text, company_url text, contact_name text, contact_email text, contact_title text,
      status text default 'new', first_sent_at timestamptz, replied_at timestamptz, created_at timestamptz default now());
  `);
  for (const name of ["001_client_finder.sql", "002_catalog.sql"]) {
    await db.exec(await readFile(new URL("db/" + name, root), "utf8"));
  }
  const guard = "do $guard$ begin\n          if not exists";
  assert.ok(sql.includes(guard));
  const failed = sql.replace(guard, "grant select on public.client_finder_tasks to anon;\n" + guard);
  await assert.rejects(db.exec("begin;\n" + failed + "\ncommit;"), /personal_postflight_1_failed/);
  await db.exec("rollback;");
  assert.equal((await db.query("select to_regclass('public.client_finder_mailboxes') as mailbox")).rows[0].mailbox, null);
  assert.equal((await db.query("select count(*)::integer as n from information_schema.columns where table_schema='public' and table_name='client_finder_messages' and column_name='conversation_id'")).rows[0].n, 0);
  console.log("PASS: failed permission check rolls back both inbox migrations");

  await db.exec("begin;\n" + sql + "\ncommit;");
  const flags = (await db.query("select m.replies_enabled,s.sending_enabled from client_finder_mailboxes m cross join client_finder_settings s")).rows[0];
  assert.deepEqual(flags, { replies_enabled: false, sending_enabled: false });
  console.log("PASS: the exact setup bundle commits with disabled sending and permission checks");

  await assert.rejects(db.exec("begin;\n" + sql + "\ncommit;"), /inbox_already_installed/);
  await db.exec("rollback;");
  console.log("PASS: setup refuses to repeat an installed migration bundle");
} finally {
  await db.close();
}
