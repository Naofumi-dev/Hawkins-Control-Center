import { describe, expect, it, vi, afterEach } from "vitest";
import { discoveryCandidates, seed } from "../src/fixtures";
import {
  businessDaysSince,
  currentRevision,
  dailyAttempts,
  draftBlock,
  generatedDraft,
  loadState,
  monthCost,
  reducer,
  sendBlock,
  STORAGE_KEY,
} from "../src/model";
import type { State } from "../src/types";

const get = (s: State, id = "client-0") =>
  s.opportunities.find((o) => o.id === id)!;
const approve = (s: State, id = "client-0") =>
  reducer(s, {
    type: "approve",
    id,
    revision: currentRevision(get(s, id))!.number,
    via: "web",
  });
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("fictional workspace state", () => {
  it("starts with twelve opportunities evenly divided between client work and jobs", () => {
    const s = seed();
    expect(s.opportunities).toHaveLength(12);
    expect(s.opportunities.filter((o) => o.kind === "client")).toHaveLength(6);
    expect(s.opportunities.filter((o) => o.kind === "job")).toHaveLength(6);
  });
  it("deduplicates repeated discovery selections by company as well as id", () => {
    const s = reducer(seed(), {
      type: "add",
      opportunity: discoveryCandidates[0],
    });
    expect(
      reducer(s, {
        type: "add",
        opportunity: { ...discoveryCandidates[0], id: "another-id" },
      }),
    ).toBe(s);
  });
  it("preserves local notes and sheet updates without altering a draft approval", () => {
    let s = approve(seed());
    s = reducer(s, {
      type: "note",
      id: "client-0",
      field: "notes",
      value: "<script>untrusted sample</script>",
    });
    s = reducer(s, {
      type: "note",
      id: "client-0",
      field: "sheetNotes",
      value: "Next step: review",
    });
    expect(get(s).notes).toContain("<script>");
    expect(get(s).draft?.approvedRevision).toBe(1);
    expect(get(s).sheetNotes).toBe("Next step: review");
  });
  it("loads a saved workspace, resets it, and handles unavailable storage", () => {
    const s = reducer(seed(), {
      type: "note",
      id: "client-0",
      field: "notes",
      value: "Persist me",
    });
    vi.stubGlobal("localStorage", {
      getItem: (key: string) =>
        key === STORAGE_KEY ? JSON.stringify(s) : null,
    });
    expect(get(loadState()).notes).toBe("Persist me");
    expect(get(reducer(s, { type: "reset" })).notes).not.toBe("Persist me");
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("blocked");
      },
    });
    expect(loadState().opportunities).toHaveLength(12);
  });
  it("keeps unfinished editor text separate from the approved revision", () => {
    let s = approve(seed());
    s = reducer(s, {
      type: "buffer",
      key: "client-0:main",
      value: {
        recipient: "hello@northline-studio.example",
        subject: "Unfinished edit",
        body: "Still writing",
        attachments: [],
        kind: "outreach",
      },
    });
    expect(s.buffers?.["client-0:main"].body).toBe("Still writing");
    expect(get(s).draft?.approvedRevision).toBe(1);
    expect(currentRevision(get(s))?.body).not.toBe("Still writing");
    s = reducer(s, { type: "buffer", key: "client-0:main" });
    expect(s.buffers?.["client-0:main"]).toBeUndefined();
    expect(reducer(s, { type: "reset" }).buffers).toBeUndefined();
  });
});
describe("exact-revision approval", () => {
  it("rejects stale approval and deduplicates approvals from both surfaces", () => {
    const original = seed();
    expect(
      reducer(original, {
        type: "approve",
        id: "client-0",
        revision: 99,
        via: "telegram",
      }),
    ).toBe(original);
    const s = approve(original);
    expect(
      reducer(s, {
        type: "approve",
        id: "client-0",
        revision: 1,
        via: "telegram",
      }),
    ).toBe(s);
    expect(get(s).draft?.approvedVia).toBe("web");
  });
  it("retains previous text and invalidates approval after an edit", () => {
    let s = approve(seed());
    const old = currentRevision(get(s))!;
    s = reducer(s, {
      type: "save",
      id: "client-0",
      kind: "outreach",
      revision: { ...old, body: "A revised, personally reviewed message." },
    });
    expect(get(s).draft?.revisions).toHaveLength(2);
    expect(get(s).draft?.approvedRevision).toBeUndefined();
    expect(get(s).draft?.revisions[0].body).toBe(old.body);
    expect(sendBlock(s, get(s))).toContain("Approve");
    expect(
      reducer(s, {
        type: "approve",
        id: "client-0",
        revision: 1,
        via: "telegram",
      }),
    ).toBe(s);
  });
  it("invalidates approval if an additional reference changes the reviewed payload", () => {
    const s = reducer(approve(seed()), {
      type: "attach",
      id: "client-0",
      resourceId: "resume",
    });
    expect(currentRevision(get(s))?.attachments).toContain("resume");
    expect(currentRevision(get(s))?.number).toBe(2);
    expect(get(s).draft?.approvedRevision).toBeUndefined();
  });
  it("blocks missing contact evidence and changed recipients", () => {
    let s = seed();
    const missing = get(s, "client-2");
    s = reducer(s, {
      type: "save",
      id: missing.id,
      kind: "outreach",
      revision: generatedDraft(missing, "outreach", "Natural", "Short", ""),
    });
    expect(draftBlock(get(s, "client-2"))).toBeTruthy();
    const r = currentRevision(get(s))!;
    s = reducer(s, {
      type: "save",
      id: "client-0",
      kind: "outreach",
      revision: { ...r, recipient: "someone@unverified.example" },
    });
    expect(draftBlock(get(s))).toContain("published contact");
  });
  it("keeps generation separate from accepting and saving its result", () => {
    const o = get(seed());
    const before = JSON.stringify(o);
    expect(
      generatedDraft(
        o,
        "outreach",
        "Formal",
        "Detailed",
        "Focus on onboarding.",
      ).body,
    ).toContain("Focus on onboarding.");
    expect(JSON.stringify(o)).toBe(before);
  });
});
describe("simulated sending", () => {
  it("records the exact payload and never resends a repeated approval or click", () => {
    const approved = approve(seed());
    const payload = structuredClone(currentRevision(get(approved)));
    const s = reducer(approved, { type: "send", id: "client-0", revision: 1 });
    expect(s.attempts).toHaveLength(3);
    expect(s.attempts.at(-1)?.payload).toEqual(payload);
    expect(s.attempts.at(-1)?.providerId).toMatch(/^demo_gmail_/);
    expect(reducer(s, { type: "send", id: "client-0", revision: 1 })).toBe(s);
    expect(get(s).messages.at(-1)?.text).toBe(payload?.body);
  });
  it("blocks a second initial email even if it was edited into a new revision", () => {
    let s = reducer(approve(seed()), {
      type: "send",
      id: "client-0",
      revision: 1,
    });
    const r = currentRevision(get(s))!;
    s = reducer(s, {
      type: "save",
      id: "client-0",
      kind: "outreach",
      revision: { ...r, body: r.body + "\nExtra sentence." },
    });
    s = approve(s);
    expect(sendBlock(s, get(s))).toContain("initial email");
  });
  it("counts unresolved attempts and stops simultaneous-style dispatches at five", () => {
    let s = seed();
    s.attempts.push(
      ...[3, 4].map((n) => ({ ...s.attempts[0], id: `extra-${n}` })),
    );
    s = approve(s);
    s = approve(s, "client-1");
    s = reducer(s, { type: "send", id: "client-0", revision: 1 });
    expect(dailyAttempts(s)).toBe(5);
    const stopped = reducer(s, { type: "send", id: "client-1", revision: 1 });
    expect(stopped).toBe(s);
    expect(sendBlock(s, get(s, "client-1"))).toContain("daily limit");
  });
  it("honors suppression that arrives after approval", () => {
    const s = reducer(approve(seed()), {
      type: "stage",
      id: "client-0",
      stage: "suppressed",
    });
    expect(get(s).draft?.approvedRevision).toBeUndefined();
    expect(reducer(s, { type: "send", id: "client-0", revision: 1 })).toBe(s);
  });
  it("stops when Gmail is paused", () => {
    const s = reducer(approve(seed()), {
      type: "connection",
      id: "gmail",
      operation: "pause",
    });
    expect(sendBlock(s, get(s))).toContain("Reconnect Gmail");
  });
  it("does not turn a job approval into an email send", () => {
    const s = approve(seed(), "job-0");
    expect(get(s, "job-0").stage).toBe("ready");
    expect(reducer(s, { type: "send", id: "job-0", revision: 1 })).toBe(s);
    const applied = reducer(s, { type: "apply", id: "job-0" });
    expect(get(applied, "job-0").stage).toBe("contacted");
    expect(applied.attempts).toHaveLength(2);
    expect(reducer(applied, { type: "apply", id: "job-0" })).toBe(applied);
  });
});
describe("replies, reconciliation, and budgets", () => {
  it("never retries an unknown send; reconciling a found match does not create an attempt", () => {
    let s = seed();
    expect(
      reducer(s, { type: "approve", id: "client-4", revision: 1, via: "web" }),
    ).toBe(s);
    expect(reducer(s, { type: "send", id: "client-4", revision: 1 })).toBe(s);
    s = reducer(s, { type: "resolve", id: "client-4", outcome: "confirmed" });
    expect(s.attempts).toHaveLength(2);
    expect(get(s, "client-4").stage).toBe("contacted");
    expect(s.attempts[1].providerId).toMatch(/^demo_reconciled/);
  });
  it("requires fresh review after a confirmed-not-sent result and retains the attempt", () => {
    const original = seed();
    const s = reducer(original, {
      type: "resolve",
      id: "client-4",
      outcome: "not_sent",
    });
    expect(s.attempts).toHaveLength(2);
    expect(s.attempts[1].outcome).toBe("not_sent");
    expect(s.attempts[1].payload).toEqual(original.attempts[1].payload);
    expect(currentRevision(get(s, "client-4"))?.number).toBe(2);
    expect(get(s, "client-4").draft?.approvedRevision).toBeUndefined();
  });
  it("uses weekdays for follow-ups and blocks replied, bounced, or opted-out contacts", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-12T05:00:00Z"));
    expect(businessDaysSince("2026-10-05T05:00:00Z")).toBe(5);
    expect(businessDaysSince("2026-10-09T05:00:00Z")).toBe(1);
    let s = seed();
    const replied = get(s, "client-3");
    const attempt = reducer(s, {
      type: "save",
      id: replied.id,
      kind: "followup",
      revision: generatedDraft(replied, "followup", "Natural", "Short", ""),
    });
    expect(attempt).toBe(s);
    expect(draftBlock(get(s, "client-5"))).toContain("suppressed");
    expect(draftBlock(get(s, "job-5"))).toContain("suppressed");
  });
  it("allows one eligible follow-up and then blocks starting another", () => {
    let s = seed();
    const o = get(s);
    o.confirmedAt = new Date(Date.now() - 10 * 86400000).toISOString();
    o.inboxState = "sent";
    o.stage = "contacted";
    o.draft!.status = "sent";
    s = reducer(s, {
      type: "save",
      id: o.id,
      kind: "followup",
      revision: generatedDraft(o, "followup", "Natural", "Short", ""),
    });
    expect(get(s).followupCreated).toBe(true);
    s = approve(s);
    s = reducer(s, { type: "send", id: o.id, revision: 2 });
    expect(get(s).draft?.status).toBe("sent");
    const r = currentRevision(get(s))!;
    s = reducer(s, {
      type: "save",
      id: o.id,
      kind: "reply",
      revision: { ...r, body: "A manually composed reply." },
    });
    const again = reducer(s, {
      type: "save",
      id: o.id,
      kind: "followup",
      revision: generatedDraft(get(s), "followup", "Natural", "Short", ""),
    });
    expect(again).toBe(s);
  });
  it("never spends beyond the hard demo cap, even with repeated reservations", () => {
    let s = seed();
    s.costs = [{ label: "Near cap", amount: 24.97 }];
    expect(reducer(s, { type: "cost", label: "Draft", amount: 0.04 })).toBe(s);
    s = reducer(s, { type: "cost", label: "Small operation", amount: 0.02 });
    expect(monthCost(s)).toBeCloseTo(24.99);
    expect(reducer(s, { type: "cost", label: "Retry", amount: 0.02 })).toBe(s);
    expect(reducer(s, { type: "cost", label: "Invalid", amount: -1 })).toBe(s);
  });
});
