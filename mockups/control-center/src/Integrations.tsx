import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  ArrowClockwise,
  FileText,
  FolderSimple,
  Paperclip,
  NotePencil,
  WarningCircle,
  Clock,
  Pause,
  Play,
  ShieldCheck,
} from "@phosphor-icons/react";
import { PageHeading } from "./ui";
import { useDemo } from "./store";
import { resources } from "./fixtures";
import { dailyAttempts, monthCost } from "./model";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  Modal,
  RelativeTime,
  ResourcePreview,
  SearchInput,
  Segments,
  ToolIcon,
} from "./ui";
import type { Connection, Resource } from "./types";

export function Inbox() {
  const { state, selectedId, navigate, dispatch, notify } = useDemo();
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [reconcile, setReconcile] = useState(false),
    [outcome, setOutcome] = useState("confirmed");
  const threads = state.opportunities.filter(
    (o) =>
      o.messages.length &&
      `${o.company} ${o.title} ${o.messages.map((m) => m.text).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "replies" && o.inboxState === "reply") ||
        (filter === "attention" &&
          ["unknown", "bounce", "optout"].includes(o.inboxState ?? ""))),
  );
  const o = state.opportunities.find((x) => x.id === selectedId) ?? threads[0];
  const attempts = state.attempts.filter((a) => a.opportunityId === o?.id);
  return (
    <div className={`page inbox-page ${selectedId ? "has-thread" : ""}`}>
      <PageHeading
        title="Keep the conversation going."
        description="Replies, delivery updates, and the context behind each message."
      />
      <div className="inbox-layout">
        <aside className="inbox-list">
          <div className="inbox-list-top">
            <div className="integration-heading">
              <ToolIcon id="gmail" />
              <div>
                <strong>Your conversations</strong>
                <span>Sample Gmail mailbox</span>
              </div>
            </div>
            <SearchInput
              value={query}
              onChange={setQuery}
              placeholder="Search conversations…"
              label="Search conversations"
            />
            <Segments
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All" },
                { value: "replies", label: "Replies" },
                { value: "attention", label: "Needs attention" },
              ]}
            />
          </div>
          {threads.map((t) => (
            <button
              className={`inbox-list-item ${o?.id === t.id ? "selected" : ""}`}
              key={t.id}
              onClick={() => navigate("inbox", t.id)}
            >
              <div>
                <Avatar o={t} small />
                <strong>{t.company}</strong>
                <RelativeTime value={t.messages.at(-1)!.at} />
              </div>
              <h3>{t.title}</h3>
              <p>{t.messages.at(-1)?.text}</p>
              <Badge
                tone={
                  t.inboxState === "reply"
                    ? "green"
                    : ["unknown", "bounce"].includes(t.inboxState ?? "")
                      ? "amber"
                      : "neutral"
                }
              >
                {t.inboxState === "reply"
                  ? "Reply received"
                  : t.inboxState === "unknown"
                    ? "Needs checking"
                    : t.inboxState === "bounce"
                      ? "Bounced"
                      : t.inboxState === "optout"
                        ? "Opted out"
                        : "Sent · demo"}
              </Badge>
            </button>
          ))}
          {!threads.length && (
            <Empty title="No conversations match">
              Try another search or clear the filter.
            </Empty>
          )}
        </aside>
        <section className="thread-panel" aria-label="Conversation">
          {o ? (
            <>
              <div className="thread-header">
                <button
                  className="text-link mobile-back"
                  onClick={() => navigate("inbox")}
                >
                  <ArrowLeft size={16} />
                  All conversations
                </button>
                <div>
                  <h2>{o.title}</h2>
                  <Button
                    variant="ghost"
                    onClick={() => navigate("pipeline", o.id)}
                  >
                    Opportunity <ArrowUpRight size={15} />
                  </Button>
                </div>
                <p>
                  {o.company} <span>·</span> {o.email}
                </p>
              </div>
              <div className="thread-messages">
                {o.inboxState === "unknown" && (
                  <div className="inbox-warning">
                    <WarningCircle size={21} />
                    <div>
                      <strong>This send needs checking.</strong>
                      <p>
                        A timeout can happen after a provider accepts a message.
                        This attempt cannot be retried until reconciled.
                      </p>
                      <Button
                        onClick={() => {
                          setOutcome("confirmed");
                          setReconcile(true);
                        }}
                      >
                        Check simulated Sent folder
                      </Button>
                    </div>
                  </div>
                )}
                {o.suppressed && (
                  <div className="inline-alert warning">
                    {o.bounced
                      ? "The message bounced."
                      : "This contact opted out."}{" "}
                    Pending outreach is stopped and new sends are blocked.
                  </div>
                )}
                {o.messages.map((m) => (
                  <article
                    key={m.id}
                    className={`thread-message ${m.direction}`}
                  >
                    <div className="message-sender">
                      <span
                        className={`message-avatar ${m.direction === "in" ? o.color : ""}`}
                      >
                        {m.direction === "out"
                          ? "AV"
                          : m.direction === "system"
                            ? "H"
                            : o.initials}
                      </span>
                      <div>
                        <strong>
                          {m.direction === "out"
                            ? "You"
                            : m.direction === "system"
                              ? "Delivery update"
                              : o.company}
                        </strong>
                        <span>
                          {m.label ??
                            (m.direction === "out"
                              ? "Local simulation"
                              : o.email)}
                        </span>
                      </div>
                      <RelativeTime value={m.at} />
                    </div>
                    <p>{m.text}</p>
                  </article>
                ))}
                {attempts.length > 0 && (
                  <div className="send-receipts">
                    <span className="subsection-label">DEMO SEND RECORDS</span>
                    {attempts.map((a) => (
                      <div key={a.id}>
                        <ShieldCheck size={16} />
                        <span>
                          Revision {a.revision} · {a.outcome}
                          <small>
                            {a.providerId ?? "Provider result unknown"}
                          </small>
                        </span>
                        <RelativeTime value={a.at} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="thread-footer">
                <span>
                  Replies are written by you and reviewed before sending.
                </span>
                <Button
                  variant="primary"
                  disabled={o.suppressed || o.stage === "needs_checking"}
                  onClick={() => navigate("drafts", `${o.id}/reply`)}
                >
                  <NotePencil size={17} />
                  Write a reply
                </Button>
              </div>
            </>
          ) : (
            <Empty title="No conversation selected">
              Select a thread to read its messages.
            </Empty>
          )}
        </section>
      </div>
      <Modal
        open={reconcile}
        onClose={() => setReconcile(false)}
        title="Reconcile the uncertain send"
        description="Choose a sample Sent-folder result. This does not access Gmail."
        wide
      >
        {o && (
          <>
            <div className="document-preview">
              <span className="subsection-label">
                MATCH AGAINST THIS STORED PAYLOAD
              </span>
              <p>
                <strong>To:</strong>{" "}
                {
                  attempts.find((a) => a.outcome === "unknown")?.payload
                    .recipient
                }
              </p>
              <p>
                <strong>Subject:</strong>{" "}
                {attempts.find((a) => a.outcome === "unknown")?.payload.subject}
              </p>
              <pre>
                {attempts.find((a) => a.outcome === "unknown")?.payload.body}
              </pre>
            </div>
            <label className="field-label">
              Simulated check result
              <select
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                <option value="confirmed">
                  Matching message found in Sent
                </option>
                <option value="not_sent">Confirmed not sent</option>
              </select>
            </label>
            <div className="modal-actions">
              <Button onClick={() => setReconcile(false)}>Cancel</Button>
              <Button
                variant="primary"
                onClick={() => {
                  dispatch({
                    type: "resolve",
                    id: o.id,
                    outcome: outcome as "confirmed" | "not_sent",
                  });
                  setReconcile(false);
                  notify(
                    outcome === "confirmed"
                      ? "Sample Sent match recorded. No message was resent."
                      : "Marked not sent. A fresh revision now needs review.",
                  );
                }}
              >
                Record result
              </Button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}

export function Library() {
  const { state, selectedId, dispatch, navigate, notify } = useDemo();
  const [query, setQuery] = useState(""),
    [provider, setProvider] = useState("all"),
    [preview, setPreview] = useState<Resource | null>(null),
    [target, setTarget] = useState(selectedId || state.opportunities[0].id);
  const rows = resources.filter(
    (r) =>
      `${r.title} ${r.description}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (provider === "all" || r.provider === provider),
  );
  const selected = state.opportunities.find((o) => o.id === target);
  return (
    <div className="page">
      <PageHeading
        title="Proof, context, and good starting points."
        description="Your reference material, ready for the right conversation."
      />
      <div className="library-toolbar">
        <Segments
          value={provider}
          onChange={setProvider}
          options={[
            { value: "all", label: "All references" },
            { value: "Drive", label: "Google Drive" },
            { value: "Notion", label: "Notion" },
          ]}
        />
        <SearchInput
          value={query}
          onChange={setQuery}
          placeholder="Search your library…"
          label="Search library"
        />
      </div>
      <div className="library-grid">
        {rows.map((r) => (
          <button
            className="library-card"
            key={r.id}
            onClick={() => setPreview(r)}
          >
            <div
              className={`file-cover ${r.type === "Portfolio" ? "portfolio" : r.provider === "Notion" ? "notes-cover" : ""}`}
            >
              <span className="file-cover-meta">
                HAWKINS / {r.type.toUpperCase()}
              </span>
              <FileText size={36} weight="duotone" />
              <strong>{r.title}</strong>
              <span>
                {r.preview ? "PROTOTYPE / PREVIEW" : "SAMPLE REFERENCE"}
              </span>
            </div>
            <div className="library-card-text">
              <h2>
                {r.title}
                <ArrowUpRight size={17} />
              </h2>
              <p>{r.description}</p>
              <div>
                <ToolIcon
                  id={r.provider === "Drive" ? "drive" : "notion"}
                  size={14}
                />
                <span>{r.provider}</span>
                {r.preview && <Badge tone="amber">Preview</Badge>}
              </div>
            </div>
          </button>
        ))}
      </div>
      {!rows.length && (
        <Empty title="No references match">Try another name or provider.</Empty>
      )}
      <div className="library-footnote">
        <ShieldCheck size={18} />
        <span>
          Prototype labels travel with attached references. Sample documents are
          not verified claims about completed client work.
        </span>
      </div>
      <ResourcePreview
        resource={preview}
        onClose={() => setPreview(null)}
        action={
          <>
            <label className="field-label attach-select">
              Attach to opportunity
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                {state.opportunities
                  .filter((o) => !o.suppressed && o.stage !== "closed")
                  .map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.company} ·{" "}
                      {o.kind === "client" ? "Client" : "Application"}
                    </option>
                  ))}
              </select>
            </label>
            <Button
              variant="primary"
              disabled={!preview || !selected || selected.suppressed}
              onClick={() => {
                if (preview && selected) {
                  dispatch({
                    type: "attach",
                    id: selected.id,
                    resourceId: preview.id,
                  });
                  notify(
                    `${preview.title} linked. Review attachment choices in Draft Studio.`,
                  );
                  setPreview(null);
                  navigate("drafts", selected.id);
                }
              }}
            >
              <Paperclip size={17} />
              Use as draft context
            </Button>
          </>
        }
      />
    </div>
  );
}

export function Connections() {
  const { state, dispatch, notify, selectedId, navigate } = useDemo();
  const [selected, setSelected] = useState<string | null>(
    state.connections.some((c) => c.id === selectedId) ? selectedId : null,
  );
  const [busy, setBusy] = useState<string | null>(null);
  const timers = useRefTimers();
  useEffect(() => {
    if (state.connections.some((c) => c.id === selectedId))
      setSelected(selectedId);
  }, [selectedId]);
  const connection = state.connections.find((c) => c.id === selected);
  function operate(c: Connection, operation: "sync" | "reconnect" | "pause") {
    if (operation === "pause") {
      dispatch({ type: "connection", id: c.id, operation });
      notify(`${c.name} paused in the demo.`);
      return;
    }
    setBusy(c.id);
    timers(() => {
      dispatch({ type: "connection", id: c.id, operation });
      setBusy(null);
      notify(
        `${c.name} ${operation === "reconnect" ? "reconnected" : "synced"} in the demo.`,
      );
    }, 650);
  }
  const connected = state.connections.filter(
    (c) => c.status === "connected",
  ).length;
  return (
    <div className="page">
      <PageHeading
        title="Your tools, working together."
        description="See what is connected, what each tool does, and what needs attention."
      >
        <Badge tone="green">
          {connected} of {state.connections.length} connected · demo
        </Badge>
      </PageHeading>
      <div className="connections-grid">
        {state.connections.map((c) => (
          <article
            className={`connection-card ${c.status === "attention" ? "needs-attention" : ""}`}
            key={c.id}
          >
            <div className="connection-card-top">
              <ToolIcon id={c.id} size={24} />
              <Badge tone={c.status === "connected" ? "green" : "amber"}>
                <span className="status-dot" />
                {c.status === "connected"
                  ? "Connected"
                  : c.status === "attention"
                    ? "Needs attention"
                    : "Paused"}
              </Badge>
            </div>
            <h2>{c.name}</h2>
            <p>{c.purpose}</p>
            <div className="connection-detail-text">{c.detail}</div>
            <div className="last-sync">
              <Clock size={14} /> Last demo sync{" "}
              <RelativeTime value={c.lastSync} />
            </div>
            <div className="connection-card-actions">
              <Button variant="ghost" onClick={() => setSelected(c.id)}>
                Details <ArrowUpRight size={14} />
              </Button>
              <Button
                variant={c.status === "connected" ? "secondary" : "primary"}
                onClick={() =>
                  operate(c, c.status === "connected" ? "sync" : "reconnect")
                }
                disabled={busy !== null}
              >
                <ArrowClockwise
                  size={15}
                  className={busy === c.id ? "spinning" : ""}
                />
                {busy === c.id
                  ? "Updating…"
                  : c.status === "connected"
                    ? "Sync demo"
                    : "Reconnect demo"}
              </Button>
            </div>
          </article>
        ))}
      </div>
      <section className="limits-panel">
        <div>
          <span className="subsection-label">AUTOMATION CONTROLS</span>
          <h2>Small volume. Deliberate outreach.</h2>
          <p>These settings reflect the agreed Client Finder limits.</p>
        </div>
        <dl>
          <div>
            <dt>Email attempts</dt>
            <dd>{dailyAttempts(state)} / 5 today</dd>
          </div>
          <div>
            <dt>New client drafts</dt>
            <dd>Up to 5 per day</dd>
          </div>
          <div>
            <dt>Discovery schedule</dt>
            <dd>08:00 Asia/Manila</dd>
          </div>
          <div>
            <dt>Additional monthly budget</dt>
            <dd>${monthCost(state).toFixed(2)} / $25.00</dd>
          </div>
        </dl>
        <Button
          onClick={() => {
            dispatch({ type: "pause" });
            notify(
              state.discoveryPaused
                ? "Demo discovery resumed."
                : "Demo discovery paused.",
            );
          }}
        >
          {state.discoveryPaused ? <Play size={16} /> : <Pause size={16} />}
          {state.discoveryPaused ? "Resume discovery" : "Pause discovery"}
        </Button>
      </section>
      <Modal
        open={!!connection}
        onClose={() => {
          setSelected(null);
          if (selectedId) navigate("connections");
        }}
        title={connection?.name ?? "Connection"}
        description="Simulated connection details. No external account or credentials are accessed."
      >
        {connection && (
          <>
            <div className="integration-heading">
              <ToolIcon id={connection.id} size={26} />
              <div>
                <strong>{connection.purpose}</strong>
                <span>{connection.detail}</span>
              </div>
            </div>
            <dl className="record-fields">
              <div>
                <dt>Status</dt>
                <dd>{connection.status}</dd>
              </div>
              <div>
                <dt>Last sample sync</dt>
                <dd>
                  <RelativeTime value={connection.lastSync} />
                </dd>
              </div>
              <div>
                <dt>Data boundary</dt>
                <dd>Fictional records stored in this browser</dd>
              </div>
            </dl>
            <h3 className="small-heading">Linked resources</h3>
            <button
              className="resource-row"
              onClick={() => {
                setSelected(null);
                navigate(
                  connection.id === "gmail"
                    ? "inbox"
                    : ["drive", "notion"].includes(connection.id)
                      ? "library"
                      : connection.id === "telegram"
                        ? "drafts"
                        : ["brave", "n8n"].includes(connection.id)
                          ? "discover"
                          : "pipeline",
                );
              }}
            >
              <FolderSimple size={22} />
              <span>
                <strong>
                  {connection.id === "gmail"
                    ? "Opportunity conversations"
                    : ["drive", "notion"].includes(connection.id)
                      ? "Reference library"
                      : connection.id === "telegram"
                        ? "Draft review cards"
                        : ["brave", "n8n"].includes(connection.id)
                          ? "Discovery workspace"
                          : "Opportunity records"}
                </strong>
                <small>Open the linked sample workspace</small>
              </span>
              <ArrowUpRight size={17} />
            </button>
            <h3 className="small-heading">Recent demo activity</h3>
            <div className="connection-history">
              {state.activities
                .filter((a) => a.title.startsWith(connection.name))
                .slice(0, 4)
                .map((a) => (
                  <p key={a.id}>
                    {a.title}
                    <RelativeTime value={a.at} />
                  </p>
                ))}
              {!state.activities.some((a) =>
                a.title.startsWith(connection.name),
              ) && <p>No new sync activity in this session.</p>}
            </div>
            <div className="modal-actions">
              <Button
                onClick={() =>
                  operate(
                    connection,
                    connection.status === "connected" ? "pause" : "reconnect",
                  )
                }
              >
                {connection.status === "connected"
                  ? "Pause demo connection"
                  : "Reconnect demo"}
              </Button>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}

function useRefTimers() {
  const [timers] = useState<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.forEach(clearTimeout), [timers]);
  return (fn: () => void, delay: number) => {
    const timer = setTimeout(fn, delay);
    timers.push(timer);
  };
}
