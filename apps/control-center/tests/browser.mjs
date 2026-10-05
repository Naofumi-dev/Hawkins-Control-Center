import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { catalogResponse } from "./catalog-fixtures.mjs";
const base = process.env.CONTROL_CENTER_TEST_URL || "http://127.0.0.1:8089";
if (!["127.0.0.1", "localhost"].includes(new URL(base).hostname))
  throw new Error("Tests require localhost");
const output = new URL("../../../artifacts/control-center/", import.meta.url);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
    : {}),
});
try {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
  });
  const page = await context.newPage(),
    errors = [],
    reports = [],
    mutations = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(base);
  await page
    .getByText("Personal account setup needed", { exact: true })
    .waitFor();
  assert.equal(
    await page.getByRole("button", { name: "Sign in to Hawkins" }).isDisabled(),
    true,
  );
  await page.screenshot({
    path: fileURLToPath(new URL("setup.png", output)),
    fullPage: true,
  });
  const at = "2026-10-05T03:12:00Z";
  const conversation = (id) => ({
    id,
    opportunity_id: "opp-" + id,
    subject:
      id === "loom" ? "Funding operations demo" : "Client intake project",
    category: id === "loom" ? "onlinejobs_conversation" : "direct_client",
    acquisition_source: id === "loom" ? "onlinejobs" : "direct",
    reply_email: id + "@agency.example",
    reply_verified: true,
    context_version: 1,
    latest_inbound_id: "in-" + id,
    last_message_at: at,
    classification_locked: false,
    classification_reason: "Verified incoming conversation",
    needs_platform_import: false,
    suppressed: false,
    bounced: false,
    gmail_thread_id: id === "loom" ? null : "thread-" + id,
    platform_reference:
      id === "loom" ? "https://www.onlinejobs.ph/messages/test-fixture" : null,
  });
  const c1 = conversation("loom"),
    c2 = conversation("direct");
  const state = {
    owner_email: "armageddonvivas@gmail.com",
    conversations: [c1, c2],
    tasks: [
      {
        id: "task-loom",
        conversation_id: c1.id,
        opportunity_id: c1.opportunity_id,
        originating_message_id: c1.latest_inbound_id,
        agent: "Steve",
        task_type: "prepare_loom",
        title: "Prepare Loom email",
        status: "blocked",
        blocker: "A reviewed, verified Loom link is required before drafting",
        result: null,
        context_version: 1,
        created_at: at,
        due_at: at,
      },
    ],
    opportunities: [c1, c2].map((c) => ({
      id: c.opportunity_id,
      title: c.subject,
      kind: c.id === "loom" ? "job" : "client",
      acquisition_source: c.acquisition_source,
      stage: "new",
      stage_note: null,
      won_confirmed_at: null,
    })),
    drafts: [],
    proofs: [],
    runs: [
      {
        id: "run-1",
        agent: "Steve",
        status: "blocked",
        started_at: at,
        error_code: "Missing verified Loom proof",
      },
    ],
    mailbox: {
      email: "armageddonvivas@gmail.com",
      history_id: "100",
      last_success_at: at,
      last_attempt_at: at,
      error_code: null,
      replies_enabled: false,
      reply_limit: 20,
      fetched_count: 2,
    },
    settings: {
      daily_send_limit: 5,
      monthly_cost_cap_cents: 2500,
      sending_enabled: false,
      sending_pause_reason: null,
    },
    sender_footer: "Test Owner\n10 Test Lane\nBusiness services\nReply stop",
    page_limit: 200,
    next_before: { time: at, id: "older" },
    statistics: {
      stored_messages: 2,
      pending_tasks: 0,
      blocked_tasks: 1,
      scheduled_tasks: 0,
    },
  };
  await page.route("**/*", async (route) => {
    const req = route.request(),
      url = new URL(req.url());
    const respond = (data, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(data),
      });
    if (url.origin === "https://mtdavgadkiiofwikzdtn.supabase.co") {
      assert.equal(url.pathname, "/auth/v1/token");
      assert.equal(req.postDataJSON().email, state.owner_email);
      return respond({
        access_token: "synthetic-token",
        refresh_token: "synthetic-refresh",
        expires_in: 3600,
        user: { email: state.owner_email },
      });
    }
    if (url.origin !== new URL(base).origin) return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    if (url.pathname === "/api/config")
      return respond({
        owner_email: state.owner_email,
        supabase_url: "https://mtdavgadkiiofwikzdtn.supabase.co",
        publishable_key: "synthetic-public",
        configured: true,
      });
    assert.equal(req.headers().authorization, "Bearer synthetic-token");
    if (url.pathname === "/api/workspace") return respond(state);
    const catalog = catalogResponse(url);
    if (catalog) return respond(catalog);
    if (url.pathname === "/api/conversations")
      return respond({
        conversations: [conversation("older")],
        next_before: null,
      });
    if (url.pathname.startsWith("/api/conversations/")) {
      const id = url.pathname.split("/").at(-1),
        c = state.conversations.find((c) => c.id === id) || conversation(id);
      return respond({
        conversation: c,
        messages: [
          {
            id: c.latest_inbound_id,
            channel: c.gmail_thread_id ? "gmail" : "onlinejobs_import",
            direction: "in",
            sender: c.reply_email,
            subject: c.subject,
            body:
              c.id === "loom"
                ? "Yes, please email the video."
                : "Please outline the next step. <script>window.hacked=true</script>",
            occurred_at: at,
            deleted_at: null,
            classification: {
              intent: c.id === "loom" ? "loom_requested" : "question",
              reason: "Incoming request",
            },
            reply_verified: true,
          },
        ],
        tasks: state.tasks.filter((t) => t.conversation_id === id),
        drafts: state.drafts.filter((d) => d.conversation_id === id),
        opportunities: state.opportunities.filter(
          (o) => o.id === c.opportunity_id,
        ),
      });
    }
    const body = req.postDataJSON();
    mutations.push({ path: url.pathname, body });
    if (url.pathname === "/api/drafts/save") {
      const c = state.conversations.find((c) => c.id === body.conversation_id);
      state.drafts = [
        {
          id: "draft-1",
          conversation_id: c.id,
          inbound_message_id: c.latest_inbound_id,
          revision: body.expected_revision + 1,
          context_version: c.context_version,
          recipient_email: c.reply_email,
          subject: body.subject,
          body: body.body,
          status: "pending_review",
          proof_id: null,
          approved_revision: null,
          approved_via: null,
          gmail_message_id: null,
        },
      ];
    }
    if (url.pathname === "/api/drafts/approve") {
      assert.equal(body.revision, state.drafts[0].revision);
      state.drafts[0].status = "claimed";
    }
    if (url.pathname === "/api/classification") {
      const c = state.conversations.find((c) => c.id === body.conversation_id);
      c.category = body.category;
      c.classification_locked = true;
      c.classification_reason = body.reason;
      c.context_version++;
    }
    if (url.pathname === "/api/stage") {
      const o = state.opportunities.find((o) => o.id === body.opportunity_id);
      o.stage = body.stage;
      o.stage_note = body.note;
    }
    return respond({ result: { status: "synthetic" } });
  });
  await page.reload();
  await page.getByLabel("Workspace password").fill("synthetic-password");
  await page.getByRole("button", { name: "Sign in to Hawkins" }).click();
  await page
    .getByRole("heading", { name: "Keep the next step moving." })
    .waitFor();
  async function audit(name) {
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    reports.push({
      screen: name,
      violations: results.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        nodes: v.nodes.length,
      })),
    });
    assert.equal(results.violations.length, 0, JSON.stringify(reports.at(-1)));
    assert.ok(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Overflow on " + name,
    );
  }
  await audit("today desktop");
  await page.screenshot({
    path: fileURLToPath(new URL("today-desktop.png", output)),
    fullPage: true,
  });
  await page.getByRole("button", { name: /Prepare Loom email/ }).click();
  await page.getByText("OnlineJobs origin", { exact: true }).waitFor();
  await page
    .getByText("A reviewed, verified Loom link is required before drafting", {
      exact: true,
    })
    .waitFor();
  await audit("inbox desktop");
  await page.screenshot({
    path: fileURLToPath(new URL("inbox-desktop.png", output)),
    fullPage: true,
  });
  await page
    .getByLabel("Reason for correction")
    .fill("Owner confirms the platform source.");
  await page.getByRole("button", { name: "Save correction" }).click();
  await page
    .getByText("Classification saved and locked.", { exact: true })
    .waitFor();
  await page.getByRole("button", { name: "Load older conversations" }).click();
  await page.getByText("older@agency.example", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Draft Studio", exact: true }).click();
  await page
    .getByRole("button", { name: /Client intake project/ })
    .first()
    .click();
  await page
    .getByLabel("Message", { exact: true })
    .fill(
      "Thanks. I will prepare the scope for your review.\n\n" +
        state.sender_footer,
    );
  await page.getByRole("button", { name: "Save revision" }).click();
  await page.getByText("Revision 1", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Review & approve" }).click();
  await page.getByRole("dialog", { name: "Approve revision 1" }).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Approve & queue send" })
      .isDisabled(),
    true,
  );
  assert.ok(
    (await page.locator(".review-body").textContent()).includes(
      state.sender_footer,
    ),
  );
  await audit("approval dialog");
  await page.screenshot({
    path: fileURLToPath(new URL("approval-desktop.png", output)),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Back to draft" }).click();
  state.mailbox.replies_enabled = true;
  await page.getByRole("button", { name: "Refresh workspace" }).click();
  await page.getByRole("button", { name: "Review & approve" }).click();
  await page.getByRole("button", { name: "Approve & queue send" }).click();
  await page
    .getByText(
      "Exact revision approved and queued. Gmail acceptance is still pending.",
      { exact: true },
    )
    .waitFor();
  assert.equal(
    mutations.filter((m) => m.path === "/api/drafts/approve").length,
    1,
  );
  await page.getByRole("button", { name: "Pipeline", exact: true }).click();
  await page.getByRole("button", { name: "Update stage" }).first().click();
  await page.getByRole("dialog", { name: "Update opportunity" }).waitFor();
  await page.getByRole("dialog").getByRole("combobox").selectOption("won");
  assert.equal(
    await page.getByRole("button", { name: "Save stage" }).isDisabled(),
    true,
  );
  await page
    .getByLabel("Agreement or outcome notes")
    .fill("Synthetic accepted agreement evidence.");
  await page.getByRole("button", { name: "Save stage" }).click();
  await page.getByText("Opportunity stage updated.", { exact: true }).waitFor();
  await audit("pipeline desktop");
  await page.getByRole("button", { name: "Connections", exact: true }).click();
  await audit("connections desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Inbox", exact: true }).click();
  await page.getByRole("button", { name: /direct@agency.example/ }).click();
  await page
    .getByText(
      "Please outline the next step. <script>window.hacked=true</script>",
      { exact: true },
    )
    .waitFor();
  assert.equal(await page.evaluate(() => window.hacked), undefined);
  await audit("inbox mobile");
  await page.screenshot({
    path: fileURLToPath(new URL("inbox-mobile.png", output)),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Back to inbox" }).click();
  await page.getByRole("button", { name: "Import from OnlineJobs" }).click();
  await page
    .getByLabel("OnlineJobs conversation URL")
    .fill("https://www.onlinejobs.ph/messages/test-fixture");
  await page
    .getByRole("dialog")
    .getByLabel("Subject", { exact: true })
    .fill("Funding operations");
  await page
    .getByLabel("Latest incoming message")
    .fill("Yes, please email it to me.");
  await page.getByLabel("Message time").fill("2026-10-01T12:00");
  await page.getByLabel("Contact's reply email").fill("person@agency.example");
  assert.equal(
    await page
      .getByRole("button", { name: "Import conversation", exact: true })
      .isDisabled(),
    true,
  );
  await page
    .getByLabel("Previous question or offer (optional)")
    .fill("Want the Loom of it running?");
  await page.getByRole("checkbox").check();
  await audit("manual import mobile");
  await page
    .getByRole("button", { name: "Import conversation", exact: true })
    .click();
  await page
    .getByText("Conversation imported. Its next action is in your queue.", {
      exact: true,
    })
    .waitFor();
  assert.equal(
    mutations.at(-1).body.prior_context,
    "Want the Loom of it running?",
  );
  assert.equal(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
    0,
  );
  assert.deepEqual(errors, []);
  await writeFile(
    new URL("browser-report.json", output),
    JSON.stringify(
      {
        mode: "synthetic API interception; no live authentication, mail, or sends",
        screens: reports,
        mutations: mutations.map((m) => m.path),
        runtimeErrors: errors,
      },
      null,
      2,
    ),
  );
  console.log(
    "PASS: setup boundary, owner sign-in, task origin/blocker, correction, pagination, draft revision, exact review, queued approval, won evidence, manual import, mobile navigation, injection-as-text, empty browser storage",
  );
  console.log(
    "PASS:",
    reports.length,
    "accessibility/overflow checks; screenshots in artifacts/control-center",
  );
} finally {
  await browser.close();
}
