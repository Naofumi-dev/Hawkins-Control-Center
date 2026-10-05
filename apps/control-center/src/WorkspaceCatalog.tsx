import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Tabs from "@radix-ui/react-tabs";
import { ArrowUpRight, MagnifyingGlass, X } from "@phosphor-icons/react";
import { api } from "./api";
import type { Conversation, Workspace } from "./types";

export type Overview = {
  leads: number;
  contacted: number;
  replied: number;
  proofs: number;
  deliverables: number;
};
type Lead = {
  id: string;
  company_name: string;
  company_domain: string | null;
  company_url: string | null;
  location: string | null;
  niche: string | null;
  db_source: string | null;
  contact_name: string | null;
  contact_title: string | null;
  contact_email: string | null;
  status: string;
  first_sent_at: string | null;
  replied_at: string | null;
  email_verified?: boolean;
  verification_result?: string | null;
  research_summary?: string | null;
};
type LeadPage = { leads: Lead[]; total: number; next_after: string | null };
type Detail = {
  lead: Lead;
  suppressions: { scope: string; reason: string }[];
  evidence: {
    id: string;
    evidence_kind: string;
    source_url: string;
    observed_at: string;
    fact_text: string;
  }[];
  drafts: {
    id: string;
    kind: string;
    revision: number;
    recipient_email: string;
    subject: string;
    body: string;
    status: string;
    sent_at: string | null;
  }[];
  conversations: Conversation[];
};
type Catalog = {
  proofs: {
    id: string;
    title: string;
    proof_url: string;
    proof_kind: string;
    claim_text: string;
    active: boolean;
    verified_at: string | null;
  }[];
  deliverables: {
    id: string;
    title: string;
    scope_text: string;
    active: boolean;
  }[];
  sources: {
    name: string;
    url: string;
    category: string;
    access_method: string;
    enabled: boolean;
  }[];
  source_rows: number;
  catalog_limit: number;
};
const shortDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeZone: "Asia/Manila",
      }).format(new Date(value))
    : "Not recorded";
const label = (value: string) => value.replaceAll("_", " ");
export function SafeLink({
  url,
  children,
}: {
  url: string | null;
  children: ReactNode;
}) {
  let safe = false;
  try {
    const parsed = new URL(url || "");
    safe =
      ["https:", "http:"].includes(parsed.protocol) &&
      !parsed.username &&
      !parsed.password;
  } catch {
    /* Plain text for invalid links. */
  }
  return safe ? (
    <a
      href={url!}
      target="_blank"
      rel="noopener noreferrer"
      referrerPolicy="no-referrer"
    >
      {children}
      <ArrowUpRight size={13} />
    </a>
  ) : (
    <span>{children}</span>
  );
}

export function Discover({
  token,
  onConversation,
}: {
  token: string;
  onConversation: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [history, setHistory] = useState("all");
  const [query, setQuery] = useState({ search: "", history: "all" });
  const [page, setPage] = useState<LeadPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const ctrl = new AbortController();
    setBusy(true);
    setError("");
    setPage(null);
    api<LeadPage>(
      token,
      "/api/leads?" + new URLSearchParams(query),
      undefined,
      ctrl.signal,
    )
      .then(setPage)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setBusy(false);
      });
    return () => ctrl.abort();
  }, [token, query, retry]);
  async function more() {
    if (!page?.next_after || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await api<LeadPage>(
        token,
        "/api/leads?" +
          new URLSearchParams({ ...query, after_id: page.next_after }),
      );
      setPage((p) =>
        p
          ? {
              ...next,
              leads: [
                ...new Map(
                  [...p.leads, ...next.leads].map((l) => [l.id, l]),
                ).values(),
              ],
            }
          : next,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    setQuery({ search, history });
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DISCOVER</p>
          <h1>Start with what you already know.</h1>
          <p className="muted">
            Your saved Hawkins leads, with their original research and contact
            history.
          </p>
        </div>
        <span className="tag">Personal records</span>
      </div>
      <form className="catalog-search panel" onSubmit={submit}>
        <label>
          Company, contact, or location
          <input
            value={search}
            maxLength={160}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search all saved leads"
          />
        </label>
        <label>
          Contact history
          <select value={history} onChange={(e) => setHistory(e.target.value)}>
            <option value="all">All leads</option>
            <option value="uncontacted">No recorded outreach</option>
            <option value="contacted">Previously contacted</option>
            <option value="replied">Replied</option>
          </select>
        </label>
        <button className="primary" disabled={busy}>
          <MagnifyingGlass size={17} />
          Search leads
        </button>
      </form>
      {error && (
        <div role="alert" className="error">
          {error}
          <button onClick={() => setRetry((n) => n + 1)}>Retry</button>
        </div>
      )}
      <section className="panel lead-results" aria-busy={busy}>
        <div className="section-heading">
          <h2>Saved leads</h2>
          <span className="muted" aria-live="polite">
            {page
              ? `${page.total.toLocaleString()} matching · ${page.leads.length} shown`
              : busy
                ? "Loading records…"
                : "Records unavailable"}
          </span>
        </div>
        <div className="lead-table">
          <div className="lead-row lead-heading" aria-hidden="true">
            <span>Company / location</span>
            <span>Contact</span>
            <span>Source</span>
            <span>History</span>
          </div>
          {page?.leads.map((l) => (
            <button
              className="lead-row"
              key={l.id}
              onClick={() => setSelected(l.id)}
            >
              <span>
                <strong>
                  {l.company_name || l.company_domain || "Unnamed lead"}
                </strong>
                <small>{l.location || "Location not recorded"}</small>
              </span>
              <span>
                <strong>{l.contact_name || "Name not recorded"}</strong>
                <small>{l.contact_email || "Email missing"}</small>
              </span>
              <span className="muted">
                {l.db_source || "Source not recorded"}
              </span>
              <span>
                <span
                  className={
                    "tag " +
                    (["bounced", "unsubscribed"].includes(l.status)
                      ? "amber"
                      : "")
                  }
                >
                  {label(l.status)}
                </span>
                <small>
                  {l.replied_at
                    ? "Replied " + shortDate(l.replied_at)
                    : l.first_sent_at
                      ? "Contacted " + shortDate(l.first_sent_at)
                      : "No recorded outreach"}
                </small>
              </span>
            </button>
          ))}
        </div>
        {page && !page.leads.length && (
          <div className="empty">
            <h3>No matching leads</h3>
            <p>Try another company or contact, or change the history filter.</p>
          </div>
        )}
        {page?.next_after && (
          <div className="catalog-footer">
            <button disabled={busy} onClick={more}>
              {busy ? "Loading…" : "Load more leads"}
            </button>
          </div>
        )}
      </section>
      <p className="catalog-footnote">
        Search covers saved records. Automated discovery still needs its hosted
        connection. A saved lead alone does not establish qualification or
        permission to contact.
      </p>
      <Dialog.Root
        open={!!selected}
        onOpenChange={(open) => !open && setSelected("")}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content className="modal lead-detail">
            <div className="modal-heading">
              <Dialog.Title>Lead record</Dialog.Title>
              <Dialog.Close
                className="icon-button"
                aria-label="Close lead record"
              >
                <X size={20} />
              </Dialog.Close>
            </div>
            <Dialog.Description className="muted">
              Saved research, evidence, and previous contact activity.
            </Dialog.Description>
            {selected && (
              <LeadDetail
                key={selected}
                id={selected}
                token={token}
                onConversation={onConversation}
              />
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}

function LeadDetail({
  id,
  token,
  onConversation,
}: {
  id: string;
  token: string;
  onConversation: (id: string) => void;
}) {
  const [detail, setDetail] = useState<Detail | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    const ctrl = new AbortController();
    api<Detail>(token, "/api/leads/" + id, undefined, ctrl.signal)
      .then(setDetail)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [id, token]);
  if (error)
    return (
      <div role="alert" className="error">
        {error}
      </div>
    );
  if (!detail) return <p role="status">Loading lead…</p>;
  const l = detail.lead;
  return (
    <div className="lead-detail-body">
      <h3>{l.company_name || l.company_domain}</h3>
      <SafeLink url={l.company_url}>
        {l.company_domain || "Company website"}
      </SafeLink>
      <dl className="record-fields">
        <dt>Contact</dt>
        <dd>
          {[l.contact_name, l.contact_title].filter(Boolean).join(" · ") ||
            "Not recorded"}
          <br />
          {l.contact_email || "Email missing"}
        </dd>
        <dt>Source</dt>
        <dd>{l.db_source || "Not recorded"}</dd>
        <dt>Status</dt>
        <dd>{label(l.status)}</dd>
        <dt>First contacted</dt>
        <dd>{shortDate(l.first_sent_at)}</dd>
        <dt>Last reply recorded</dt>
        <dd>{shortDate(l.replied_at)}</dd>
        <dt>Contact check</dt>
        <dd>{l.verification_result || "No verification evidence recorded"}</dd>
      </dl>
      {detail.suppressions.map((s, i) => (
        <p className="error" key={i}>
          Do not contact · {s.scope}: {s.reason}
        </p>
      ))}
      {["bounced", "unsubscribed"].includes(l.status) && (
        <p className="error">
          Contact is blocked by its saved {l.status} status.
        </p>
      )}
      <section>
        <h3>Saved research</h3>
        <pre>
          {l.research_summary ||
            "No research summary has been saved for this lead."}
        </pre>
      </section>
      <section>
        <h3>Source evidence</h3>
        {detail.evidence.length ? (
          detail.evidence.map((e) => (
            <article className="evidence-record" key={e.id}>
              <span className="tag">{label(e.evidence_kind)}</span>
              <p>{e.fact_text}</p>
              <SafeLink url={e.source_url}>
                View source · {shortDate(e.observed_at)}
              </SafeLink>
            </article>
          ))
        ) : (
          <p className="muted">
            No evidence records are attached. Review the research before
            preparing outreach.
          </p>
        )}
      </section>
      <section>
        <h3>Stored messages</h3>
        {detail.drafts.length ? (
          detail.drafts.map((d) => (
            <details className="evidence-record" key={d.id}>
              <summary>
                {d.subject} · revision {d.revision} · {label(d.status)}
              </summary>
              <p>To: {d.recipient_email}</p>
              <pre>{d.body}</pre>
              <p className="muted">
                {d.sent_at
                  ? "Sent " + shortDate(d.sent_at)
                  : "No confirmed send recorded"}
              </p>
            </details>
          ))
        ) : (
          <p className="muted">
            No versioned Client Finder messages are stored for this lead.
            Earlier outreach is reflected in contact history above.
          </p>
        )}
      </section>
      {detail.conversations.map((c) => (
        <button key={c.id} onClick={() => onConversation(c.id)}>
          Open conversation
          <ArrowUpRight size={15} />
        </button>
      ))}
    </div>
  );
}

const agents = [
  ["Will", "Inbox triage", "Classifies messages and extracts requests."],
  ["Eleven", "Qualification", "Prepares a brief from the available evidence."],
  ["Steve", "Drafting", "Prepares replies, Loom introductions, and proposals."],
  ["Hopper", "Owner review", "Presents exact revisions for your approval."],
  ["Max", "Follow-up", "Tracks eligibility and prepares reminders."],
  ["Mike", "Coordination", "Tracks dependencies, retries, and blockers."],
  ["Joyce", "Onboarding", "Prepares a checklist after you confirm a win."],
];
export function Library({
  token,
  workspace: w,
}: {
  token: string;
  workspace: Workspace;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [error, setError] = useState("");
  const [retry, setRetry] = useState(0),
    [sourceQuery, setSourceQuery] = useState("");
  const sources =
    catalog?.sources.filter((s) =>
      (s.name + " " + s.category)
        .toLowerCase()
        .includes(sourceQuery.toLowerCase()),
    ) || [];
  useEffect(() => {
    const ctrl = new AbortController();
    setError("");
    api<Catalog>(token, "/api/library", undefined, ctrl.signal)
      .then(setCatalog)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [token, retry]);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR TOOLKIT</p>
          <h1>The work behind your next conversation.</h1>
          <p className="muted">
            Proof, deliverables, source directory, and the agents assigned to
            each step.
          </p>
        </div>
      </div>
      <Tabs.Root defaultValue="proofs">
        <Tabs.List className="catalog-tabs" aria-label="Library sections">
          {["proofs", "deliverables", "sources", "agents"].map((t) => (
            <Tabs.Trigger key={t} value={t}>
              {t[0].toUpperCase() + t.slice(1)}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        {error && (
          <div role="alert" className="error">
            {error}
            <button onClick={() => setRetry((x) => x + 1)}>Retry</button>
          </div>
        )}
        <Tabs.Content value="proofs">
          <div className="catalog-grid">
            {catalog?.proofs.map((p) => (
              <article className="panel catalog-item" key={p.id}>
                <div className="section-heading">
                  <span className="tag">{p.proof_kind}</span>
                  <span
                    className={
                      "tag " + (p.active && p.verified_at ? "" : "amber")
                    }
                  >
                    {p.active && p.verified_at
                      ? "Available for drafting"
                      : "Needs review"}
                  </span>
                </div>
                <div className="catalog-item-body">
                  <h2>{p.title}</h2>
                  <p>{p.claim_text}</p>
                  <SafeLink url={p.proof_url}>View proof</SafeLink>
                  <small>
                    Verification recorded: {shortDate(p.verified_at)}
                  </small>
                </div>
              </article>
            ))}
          </div>
          {!catalog ? (
            <p role="status">
              {error ? "Proof library unavailable." : "Loading proof library…"}
            </p>
          ) : (
            !catalog.proofs.length && (
              <div className="empty">
                <h3>No proof saved yet</h3>
                <p>
                  Add and verify a proof item before including it in a draft.
                </p>
              </div>
            )
          )}
          <p className="catalog-footnote">
            Prototype labels and supported claims stay attached to each proof. A
            Loom request needs a verified Loom link.
          </p>
          {catalog && catalog.proofs.length >= catalog.catalog_limit && (
            <p className="catalog-footnote">
              Showing the first {catalog.catalog_limit} proof items.
            </p>
          )}
        </Tabs.Content>
        <Tabs.Content value="deliverables">
          <div className="catalog-grid">
            {catalog?.deliverables.map((d) => (
              <article className="panel catalog-item" key={d.id}>
                <div className="catalog-item-body">
                  <span className="tag">
                    {d.active ? "Available for drafting" : "Inactive"}
                  </span>
                  <h2>{d.title}</h2>
                  <p>{d.scope_text}</p>
                </div>
              </article>
            ))}
          </div>
          {!catalog ? (
            <p role="status">
              {error ? "Deliverables unavailable." : "Loading deliverables…"}
            </p>
          ) : (
            !catalog.deliverables.length && (
              <div className="empty">
                <h3>No deliverables saved yet</h3>
                <p>Define a supported scope before preparing a proposal.</p>
              </div>
            )
          )}
          {catalog && catalog.deliverables.length >= catalog.catalog_limit && (
            <p className="catalog-footnote">
              Showing the first {catalog.catalog_limit} deliverables.
            </p>
          )}
        </Tabs.Content>
        <Tabs.Content value="sources">
          <div className="panel">
            <div className="section-heading">
              <h2>Source directory</h2>
              <span className="muted">
                {catalog
                  ? `${catalog.sources.length} sources · ${catalog.source_rows} original rows`
                  : error
                    ? "Unavailable"
                    : "Loading…"}
              </span>
            </div>
            <div className="source-search">
              <label>
                Find a source
                <input
                  value={sourceQuery}
                  onChange={(e) => setSourceQuery(e.target.value)}
                  placeholder="Name or category"
                />
              </label>
            </div>
            {sources.map((s) => (
              <div className="source-row" key={s.url}>
                <SafeLink url={s.url}>{s.name}</SafeLink>
                <span className="muted">{label(s.category)}</span>
                <span className="tag">
                  {s.enabled ? label(s.access_method) : "Manual review"}
                </span>
              </div>
            ))}
            {catalog && !sources.length && (
              <div className="empty">
                <h3>No matching sources</h3>
                <p>Try another name or category.</p>
              </div>
            )}
          </div>
          <p className="catalog-footnote">
            Directory entries are research sources, not qualified prospects.
            Automated access is not enabled by opening a source.
          </p>
        </Tabs.Content>
        <Tabs.Content value="agents">
          <div className="panel">
            <div className="section-heading">
              <h2>Your agent team</h2>
              <span className="tag">Owner approval required</span>
            </div>
            {agents.map(([name, role, responsibility]) => {
              const tasks = w.tasks.filter(
                (t) =>
                  t.agent === name && !["done", "dismissed"].includes(t.status),
              );
              const latest = w.runs.find((r) => r.agent === name);
              return (
                <div className="agent-roster-row" key={name}>
                  <span className="agent-initial">{name[0]}</span>
                  <div>
                    <strong>
                      {name} <span className="muted">/ {role}</span>
                    </strong>
                    <p>{responsibility}</p>
                  </div>
                  <div>
                    <span className="tag">
                      {tasks.length
                        ? `${tasks.length} open tasks`
                        : "No open tasks"}
                    </span>
                    <small>
                      {latest
                        ? "Last run: " + label(latest.status)
                        : "No run recorded"}
                    </small>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="catalog-footnote">
            Run status comes from saved activity. Hosted scheduling and model
            credentials need verification before automatic work begins.
          </p>
        </Tabs.Content>
      </Tabs.Root>
    </>
  );
}
