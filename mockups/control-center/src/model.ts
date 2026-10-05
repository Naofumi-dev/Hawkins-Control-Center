import { seed } from "./fixtures";
import type { Action, DraftKind, Opportunity, Revision, State } from "./types";
export const STORAGE_KEY = "hawkins-control-center-demo-v1";
export const currentRevision = (o: Opportunity): Revision | undefined =>
  o.draft?.revisions.at(-1);
export const monthCost = (s: State) =>
  s.costs.reduce((total, c) => total + c.amount, 0);
const dateKey = (date: string) =>
  new Date(date).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
export const dailyAttempts = (s: State) =>
  s.attempts.filter((a) => dateKey(a.at) === dateKey(new Date().toISOString()))
    .length;
export const statusLabel = (o: Opportunity): string =>
  ({
    research: "Needs research",
    review: "Ready for review",
    ready: o.kind === "job" ? "Ready to apply" : "Approved",
    contacted: o.kind === "job" ? "Applied" : "Awaiting reply",
    replied: "Replied",
    needs_checking: "Needs checking",
    closed: "Skipped",
    suppressed: o.bounced ? "Bounced" : "Do not contact",
  })[o.stage];
export function businessDaysSince(date: string): number {
  const start = new Date(dateKey(date) + "T12:00:00Z");
  const end = new Date(dateKey(new Date().toISOString()) + "T12:00:00Z");
  let count = 0;
  while (start < end) {
    start.setUTCDate(start.getUTCDate() + 1);
    if (![0, 6].includes(start.getUTCDay())) count++;
  }
  return count;
}
export function draftBlock(o: Opportunity): string | undefined {
  if (o.suppressed || o.bounced)
    return "This contact is suppressed. Outreach is blocked.";
  if (o.stage === "closed") return "This opportunity was skipped.";
  if (o.stage === "needs_checking")
    return "Resolve the uncertain attempt in Inbox before continuing.";
  const r = currentRevision(o);
  if (!r) return "Generate or write a draft first.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.recipient))
    return "A valid sample recipient is required.";
  if (!o.email || !o.evidence.some((e) => e.label === "Published contact"))
    return "Published contact evidence is missing.";
  if (r.recipient.toLowerCase() !== o.email.toLowerCase())
    return "Recipient must match the published contact evidence.";
  if (!r.subject.trim() || !r.body.trim())
    return "Add a subject and full message before review.";
  if (o.draft?.kind === "followup") {
    if (o.inboxState === "reply")
      return "A reply stops follow-ups. Write a manual reply instead.";
    if (!o.confirmedAt || businessDaysSince(o.confirmedAt) < 5)
      return "Follow-ups become eligible after five weekdays.";
  }
}
export function sendBlock(s: State, o: Opportunity): string | undefined {
  const blocked = draftBlock(o);
  if (blocked) return blocked;
  const r = currentRevision(o)!;
  if (o.draft!.approvedRevision !== r.number)
    return "Approve this exact revision before sending.";
  if (
    o.draft!.status === "sent" ||
    o.draft!.status === "applied" ||
    s.attempts.some((a) => a.opportunityId === o.id && a.revision === r.number)
  )
    return "This revision has already been processed.";
  if (
    o.draft!.kind === "outreach" &&
    s.attempts.some(
      (a) => a.opportunityId === o.id && a.outcome === "confirmed",
    )
  )
    return "An initial email is already recorded. Use an eligible follow-up or write a reply.";
  if (dailyAttempts(s) >= 5)
    return "The daily limit of five email attempts has been reached.";
  if (s.connections.find((c) => c.id === "gmail")?.status !== "connected")
    return "Reconnect Gmail before simulating a send.";
}
export function loadState(): State {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const value = JSON.parse(raw);
      if (
        value.version === 1 &&
        Array.isArray(value.opportunities) &&
        Array.isArray(value.connections) &&
        Array.isArray(value.attempts) &&
        Array.isArray(value.costs) &&
        Array.isArray(value.activities)
      )
        return value;
    }
  } catch {
    /* An unavailable or older browser store should not prevent the demo. */
  }
  return seed();
}
export function reducer(previous: State, action: Action): State {
  if (action.type === "reset") return seed();
  const s: State = structuredClone(previous);
  const at = new Date().toISOString();
  const id = crypto.randomUUID();
  const log = (
    title: string,
    detail: string,
    opportunityId?: string,
    page?: State["activities"][number]["page"],
  ) => s.activities.unshift({ id, title, detail, at, opportunityId, page });
  const o =
    "id" in action
      ? s.opportunities.find((x) => x.id === action.id)
      : undefined;
  switch (action.type) {
    case "add": {
      if (
        s.opportunities.some(
          (x) =>
            x.id === action.opportunity.id ||
            x.website === action.opportunity.website,
        )
      )
        return previous;
      const added = structuredClone(action.opportunity);
      added.stage = "research";
      s.opportunities.unshift(added);
      log("Added to your pipeline", added.company, added.id, "pipeline");
      break;
    }
    case "save": {
      if (
        !o ||
        o.suppressed ||
        o.stage === "closed" ||
        o.stage === "needs_checking"
      )
        return previous;
      const current = currentRevision(o);
      if (
        current &&
        current.recipient === action.revision.recipient &&
        current.subject === action.revision.subject &&
        current.body === action.revision.body &&
        JSON.stringify(current.attachments) ===
          JSON.stringify(action.revision.attachments) &&
        o.draft?.kind === action.kind
      )
        return previous;
      if (
        action.kind === "followup" &&
        (o.inboxState === "reply" ||
          !o.confirmedAt ||
          businessDaysSince(o.confirmedAt) < 5 ||
          (o.followupCreated &&
            (o.draft?.kind !== "followup" || o.draft?.status === "sent")))
      )
        return previous;
      const revision = {
        ...action.revision,
        number: (current?.number ?? 0) + 1,
        createdAt: at,
      };
      o.draft = {
        kind: action.kind,
        revisions: [...(o.draft?.revisions ?? []), revision],
        status: "draft",
      };
      if (action.kind === "followup") o.followupCreated = true;
      o.stage = "review";
      log(
        "Draft saved for review",
        `${o.company} · revision ${revision.number}`,
        o.id,
        "drafts",
      );
      break;
    }
    case "approve": {
      if (
        !o ||
        draftBlock(o) ||
        currentRevision(o)?.number !== action.revision ||
        o.draft!.approvedRevision === action.revision ||
        ["sent", "applied"].includes(o.draft!.status)
      )
        return previous;
      o.draft!.approvedRevision = action.revision;
      o.draft!.approvedVia = action.via;
      o.draft!.status = "approved";
      o.stage = "ready";
      log(
        `Approved in ${action.via === "web" ? "Control Center" : "Telegram"}`,
        `${o.company} · revision ${action.revision}`,
        o.id,
        "drafts",
      );
      break;
    }
    case "send": {
      if (
        !o ||
        (o.kind === "job" && o.draft?.kind === "cover") ||
        currentRevision(o)?.number !== action.revision ||
        sendBlock(s, o)
      )
        return previous;
      const payload = structuredClone(currentRevision(o)!);
      s.attempts.push({
        id,
        opportunityId: o.id,
        revision: payload.number,
        payload,
        at,
        outcome: "confirmed",
        providerId: `demo_gmail_${id.slice(0, 8)}`,
      });
      o.draft!.status = "sent";
      o.stage = "contacted";
      o.confirmedAt = at;
      o.inboxState = "sent";
      o.messages.push({
        id,
        direction: "out",
        text: payload.body,
        at,
        label: `Demo send · ${payload.subject}`,
      });
      log(
        "Email send simulated",
        `${o.company} · ${payload.recipient}`,
        o.id,
        "inbox",
      );
      break;
    }
    case "apply": {
      if (
        !o ||
        o.kind !== "job" ||
        o.draft?.kind !== "cover" ||
        draftBlock(o) ||
        o.draft?.status !== "approved" ||
        o.draft.approvedRevision !== currentRevision(o)?.number
      )
        return previous;
      o.stage = "contacted";
      o.draft.status = "applied";
      log(
        "Application marked applied",
        `${o.company} · demo only`,
        o.id,
        "pipeline",
      );
      break;
    }
    case "stage": {
      if (!o) return previous;
      o.stage = action.stage;
      if (action.stage === "suppressed") o.suppressed = true;
      if (o.draft) {
        o.draft.approvedRevision = undefined;
        o.draft.approvedVia = undefined;
      }
      log(
        action.stage === "suppressed"
          ? "Contact suppressed"
          : "Opportunity skipped",
        o.company,
        o.id,
        "pipeline",
      );
      break;
    }
    case "note":
      if (o) {
        o[action.field] = action.value;
        log(
          action.field === "notes"
            ? "Notion note saved locally"
            : "Sheet record saved locally",
          o.company,
          o.id,
          "pipeline",
        );
      }
      break;
    case "attach": {
      if (!o || o.suppressed || ["closed", "needs_checking"].includes(o.stage))
        return previous;
      if (!o.resourceIds.includes(action.resourceId))
        o.resourceIds.push(action.resourceId);
      const r = currentRevision(o);
      if (
        r &&
        !r.attachments.includes(action.resourceId) &&
        !["sent", "applied"].includes(o.draft!.status)
      ) {
        o.draft!.revisions.push({
          ...r,
          number: r.number + 1,
          createdAt: at,
          attachments: [...r.attachments, action.resourceId],
        });
        o.draft!.approvedRevision = undefined;
        o.draft!.approvedVia = undefined;
        o.draft!.status = "draft";
        o.stage = "review";
      }
      log("Reference linked", o.company, o.id, "drafts");
      break;
    }
    case "connection": {
      const c = s.connections.find((c) => c.id === action.id);
      if (!c) return previous;
      if (action.operation === "sync" && c.status !== "connected")
        return previous;
      c.status = action.operation === "pause" ? "paused" : "connected";
      if (c.status === "connected") c.lastSync = at;
      if (action.operation === "reconnect")
        c.detail = `${c.name} · demo connection restored. No external account accessed.`;
      log(
        `${c.name} ${action.operation === "pause" ? "paused" : action.operation === "reconnect" ? "reconnected" : "sync simulated"}`,
        "Local demo state updated.",
        undefined,
        "connections",
      );
      break;
    }
    case "resolve": {
      if (!o || o.stage !== "needs_checking") return previous;
      const a = s.attempts.find(
        (a) => a.opportunityId === o.id && a.outcome === "unknown",
      );
      if (!a) return previous;
      if (action.outcome === "confirmed") {
        a.outcome = "confirmed";
        a.providerId = "demo_reconciled_" + a.id;
        o.stage = "contacted";
        o.confirmedAt = at;
        o.inboxState = "sent";
        if (o.draft) o.draft.status = "sent";
        o.messages.push({
          id,
          direction: "out",
          text: a.payload.body,
          at,
          label: "Found in simulated Sent folder",
        });
      } else {
        // Keep the immutable attempt. A new revision and new approval are required.
        a.outcome = "not_sent";
        o.stage = "review";
        o.inboxState = undefined;
        if (o.draft) {
          const r = currentRevision(o)!;
          o.draft.revisions.push({ ...r, number: r.number + 1, createdAt: at });
          o.draft.status = "draft";
          o.draft.approvedRevision = undefined;
          o.draft.approvedVia = undefined;
        }
      }
      log(
        "Send result reconciled",
        `${o.company} · ${action.outcome === "confirmed" ? "found in sample Sent mail" : "not sent; fresh review required"}`,
        o.id,
        "inbox",
      );
      break;
    }
    case "pause":
      s.discoveryPaused = !s.discoveryPaused;
      log(
        `Daily discovery ${s.discoveryPaused ? "paused" : "resumed"}`,
        "Demo schedule · 08:00 Asia/Manila",
        undefined,
        "discover",
      );
      break;
    case "cost":
      if (action.amount < 0 || monthCost(s) + action.amount > 25)
        return previous;
      s.costs.push({ label: action.label, amount: action.amount });
      break;
    case "buffer": {
      if (!action.value && !s.buffers?.[action.key]) return previous;
      s.buffers ??= {};
      if (action.value) s.buffers[action.key] = action.value;
      else delete s.buffers[action.key];
      break;
    }
  }
  return s;
}

export function generatedDraft(
  o: Opportunity,
  kind: DraftKind,
  tone: string,
  length: string,
  brief: string,
): Omit<Revision, "number" | "createdAt"> {
  const greeting =
    tone === "Formal"
      ? `Hello ${o.kind === "job" ? o.company + " hiring team" : o.contact},`
      : `Hi ${o.kind === "job" ? o.company + " team" : o.contact.split(" ")[0]},`;
  const context =
    kind === "cover"
      ? `I'm interested in the ${o.title} role. Your listing calls for integrations and clear documentation.`
      : kind === "followup"
        ? `Following up on my note about ${o.title.toLowerCase()}.`
        : kind === "reply"
          ? "Thanks for your reply."
          : `I saw your published brief about ${o.title.toLowerCase()}.`;
  const main =
    kind === "cover"
      ? "I would start by mapping the workflow, identifying review points, and building a small version your team can test. The linked résumé and project previews provide context."
      : kind === "reply"
        ? ""
        : `One possible first step is ${o.proposed.charAt(0).toLowerCase() + o.proposed.slice(1)}`;
  const extra =
    length === "Detailed"
      ? "\n\nBefore proposing a scope, I would confirm the current process, who reviews the output, and what a useful first version needs to do."
      : "";
  return {
    recipient: o.email,
    subject:
      kind === "cover"
        ? `Application: ${o.title}`
        : kind === "followup"
          ? `Following up: ${o.title}`
          : kind === "reply"
            ? `Re: ${o.title}`
            : `${o.company} · ${o.title.toLowerCase()}`,
    attachments: [...o.resourceIds],
    body: `${greeting}\n\n${context}${main ? "\n\n" + main : ""}${brief.trim() ? "\n\n" + brief.trim() : ""}${extra}\n\n${kind === "cover" ? "I'd be glad to discuss the first workflow you want to improve." : kind === "reply" ? "Best," : "Would a short outline be useful?"}\n\nArmageddon Vivas\n${kind === "cover" ? "Fictional demo application." : "Sample commercial outreach · Fictional demo address\nReply “no thanks” to opt out. This demo never sends email."}`,
  };
}
