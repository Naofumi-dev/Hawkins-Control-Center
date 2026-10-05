import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  SquaresFour,
  EnvelopeSimple,
  Kanban,
  NotePencil,
  PlugsConnected,
  ArrowClockwise,
  ArrowUpRight,
  LockKey,
  SignOut,
  List,
  X,
  ArrowLeft,
  CheckCircle,
  WarningCircle,
  Clock,
  Plus,
  Robot,
  PaperPlaneTilt,
  MagnifyingGlass,
  Books,
} from "@phosphor-icons/react";
import { Discover, Library, type Overview } from "./WorkspaceCatalog";
import { AcquisitionWorkspace } from "./AcquisitionWorkspace";
import {
  api,
  configRequest,
  signIn,
  refreshSession,
  OWNER,
  type Config,
  type Session,
} from "./api";
import {
  categoryLabels,
  stageLabels,
  type Workspace,
  type Conversation,
  type Message,
  type Draft,
  type Category,
  type Stage,
} from "./types";

type Page =
  | "today"
  | "discover"
  | "inbox"
  | "pipeline"
  | "drafts"
  | "library"
  | "connections";
const nav = [
  { id: "today", label: "Today", icon: SquaresFour },
  { id: "discover", label: "Discover", icon: MagnifyingGlass },
  { id: "pipeline", label: "Pipeline", icon: Kanban },
  { id: "drafts", label: "Draft Studio", icon: NotePencil },
  { id: "inbox", label: "Inbox", icon: EnvelopeSimple },
  { id: "library", label: "Library", icon: Books },
  { id: "connections", label: "Connections", icon: PlugsConnected },
] as const;
const hashPage = () =>
  nav.find((n) => "#/" + n.id === window.location.hash)?.id;
const date = (v: string | null) =>
  v
    ? new Intl.DateTimeFormat("en", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Manila",
      }).format(new Date(v))
    : "Not yet";
function Tag({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return <span className={"tag " + tone}>{children}</span>;
}
function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <EnvelopeSimple size={28} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

function mergeById<T extends { id: string }>(older: T[], current: T[]): T[] {
  return [
    ...new Map([...older, ...current].map((item) => [item.id, item])).values(),
  ];
}
function Modal({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="modal">
          <div className="modal-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label="Close">
              <X size={20} />
            </Dialog.Close>
          </div>
          <Dialog.Description className="muted">
            {description}
          </Dialog.Description>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function App() {
  const [config, setConfig] = useState<Config | null>(null),
    [session, setSession] = useState<Session | null>(null),
    [password, setPassword] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [notice, setNotice] = useState("");
  const [page, setPage] = useState<Page>(() => hashPage() || "today"),
    [selected, setSelected] = useState(""),
    [menu, setMenu] = useState(false),
    [importOpen, setImportOpen] = useState(false);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState("");
  const [acquisitionView, setAcquisitionView] = useState(false);
  useEffect(() => setAcquisitionView(false), [page]);
  const [filter, setFilter] = useState("all"),
    [search, setSearch] = useState("");
  const [olderCursor, setOlderCursor] = useState<
    Workspace["next_before"] | undefined
  >(undefined);
  useEffect(() => {
    configRequest()
      .then(setConfig)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const changed = () => {
      const next = hashPage();
      if (next) {
        setPage(next);
        setSelected("");
        setMenu(false);
      }
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (!session) {
      setOverview(null);
      return;
    }
    const ctrl = new AbortController();
    setOverviewError("");
    api<Overview>(session.access_token, "/api/overview", undefined, ctrl.signal)
      .then(setOverview)
      .catch((e) => {
        if (!ctrl.signal.aborted) setOverviewError(e.message);
      });
    return () => ctrl.abort();
  }, [session]);
  useEffect(() => {
    if (!session || !config) return;
    const timer = setTimeout(
      () => {
        refreshSession(config, session.refresh_token)
          .then(setSession)
          .catch((e) => {
            setSession(null);
            setWorkspace(null);
            setError(e.message);
          });
      },
      Math.max(10, session.expires_in - 60) * 1000,
    );
    return () => clearTimeout(timer);
  }, [session, config]);
  const reload = useCallback(async () => {
    if (!session) return;
    const data = await api<Workspace>(session.access_token, "/api/workspace");
    if (data.owner_email !== OWNER)
      throw new Error("Account mismatch. Data access stopped.");
    if (selected && (page === "inbox" || page === "drafts")) {
      const detail = await api<{
        conversation: Conversation;
        tasks: Workspace["tasks"];
        drafts: Workspace["drafts"];
        opportunities: Workspace["opportunities"];
      }>(session.access_token, "/api/conversations/" + selected);
      data.conversations = mergeById(data.conversations, [detail.conversation]);
      data.tasks = mergeById(data.tasks, detail.tasks);
      data.drafts = mergeById(data.drafts, detail.drafts);
      data.opportunities = mergeById(data.opportunities, detail.opportunities);
    }
    setWorkspace((previous) => ({
      ...data,
      conversations: mergeById(
        previous?.conversations || [],
        data.conversations,
      ).sort((a, b) =>
        (b.last_message_at || "").localeCompare(a.last_message_at || ""),
      ),
    }));
  }, [session, selected, page]);
  async function loadOlder() {
    const cursor =
      olderCursor === undefined ? workspace?.next_before : olderCursor;
    if (!cursor || !session || busy) return;
    setBusy(true);
    try {
      const data = await api<Pick<Workspace, "conversations" | "next_before">>(
        session.access_token,
        "/api/conversations?" +
          new URLSearchParams({
            before_time: cursor.time,
            before_id: cursor.id,
          }),
      );
      setWorkspace((w) =>
        w
          ? {
              ...w,
              conversations: mergeById(w.conversations, data.conversations),
            }
          : w,
      );
      setOlderCursor(data.next_before);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!session) return;
    let live = true;
    reload().catch((e) => live && setError(e.message));
    const timer = setInterval(() => {
      if (document.visibilityState === "visible")
        reload().catch((e) => live && setError(e.message));
    }, 15000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [session, reload]);
  async function action(path: string, data: unknown, success: string) {
    if (!session || busy) return false;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(session.access_token, path, data);
      await reload();
      setNotice(success);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  function go(p: Page, id = "") {
    window.history.pushState(null, "", "#/" + p);
    setPage(p);
    setSelected(id);
    setMenu(false);
    setSearch("");
    setFilter("all");
  }
  async function login(e: FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      setSession(await signIn(config, password));
      setOlderCursor(undefined);
      setPassword("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (!session)
    return (
      <div className="login-page">
        <div className="login-brand">
          <span className="brand-mark">H</span>
          <span>HAWKINS</span>
          <span className="muted">/ Personal workspace</span>
        </div>
        <main className="login-panel">
          <LockKey size={28} className="accent" />
          <p className="eyebrow">YOUR WORK, IN ONE PLACE</p>
          <h1>Pick up the conversation.</h1>
          <p className="login-intro">
            Your inbox, next actions, and client pipeline.
            <br />
            Every outgoing message stays under your review.
          </p>
          <form onSubmit={login}>
            <label>
              Personal account
              <input value={OWNER} readOnly autoComplete="username" />
            </label>
            <label>
              Workspace password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                disabled={!config?.configured || busy}
              />
            </label>
            <button
              className="primary"
              disabled={busy || loading || !config?.configured}
            >
              {busy ? "Signing in…" : "Sign in to Hawkins"}
              <ArrowUpRight size={18} />
            </button>
          </form>
          {error && (
            <div role="alert" className="error">
              <WarningCircle size={18} />
              {error}
            </div>
          )}
          {!loading && !config?.configured && (
            <div className="setup-note">
              <strong>Personal account setup needed</strong>
              <p>
                The backend needs your Hawkins authentication settings before
                sign-in is available. No mailbox has been connected by this app.
              </p>
            </div>
          )}
          <p className="login-foot">
            Private to Armageddon Vivas. Email content stays out of browser
            storage.
          </p>
        </main>
        <footer>
          Hawkins Client Finder <span>Owner approval comes first</span>
        </footer>
      </div>
    );
  const tasks =
    workspace?.tasks.filter(
      (t) =>
        !["done", "dismissed"].includes(t.status) &&
        (!t.due_at || new Date(t.due_at).getTime() <= Date.now()),
    ) || [];
  const conversations = (workspace?.conversations || []).filter(
    (c) =>
      (filter === "all" || c.category === filter) &&
      (c.subject + " " + c.reply_email)
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const c = workspace?.conversations.find((c) => c.id === selected);
  const selectedDraft = workspace?.drafts.find(
    (d) =>
      d.conversation_id === selected &&
      d.inbound_message_id === c?.latest_inbound_id,
  );
  return (
    <div className="app-shell">
      <aside className={menu ? "sidebar open" : "sidebar"}>
        <div className="brand">
          <span className="brand-mark">H</span>HAWKINS
          <button
            className="mobile-only icon-button"
            onClick={() => setMenu(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>
        <div className="owner">
          <span className="avatar">AV</span>
          <div>
            <strong>Personal workspace</strong>
            <small>Armageddon Vivas</small>
          </div>
          <LockKey size={14} />
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav aria-label="Main navigation">
          {nav.map((n) => (
            <button
              key={n.id}
              className={page === n.id ? "nav-item active" : "nav-item"}
              aria-current={page === n.id ? "page" : undefined}
              onClick={() => go(n.id)}
            >
              <n.icon size={19} />
              <span>{n.label}</span>
              {n.id === "today" && tasks.length > 0 && (
                <small>{tasks.length}</small>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sync-summary">
            <span
              className={
                "status-dot " +
                (workspace?.mailbox?.last_success_at &&
                !workspace.mailbox.error_code
                  ? "good"
                  : "")
              }
            />
            <div>
              <strong>
                {workspace?.mailbox?.last_success_at
                  ? "Personal inbox"
                  : "Awaiting first sync"}
              </strong>
              <small>
                {workspace?.mailbox?.error_code
                  ? "Sync needs attention"
                  : workspace?.mailbox?.last_success_at
                    ? date(workspace.mailbox.last_success_at)
                    : "No live mail imported yet"}
              </small>
            </div>
          </div>
          <button
            className="nav-item"
            onClick={() => {
              setSession(null);
              setWorkspace(null);
              setSelected("");
            }}
          >
            <SignOut size={18} />
            Sign out
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-only"
            onClick={() => setMenu(true)}
            aria-label="Open navigation"
          >
            <List size={22} />
          </button>
          <div>
            <span className="muted">Workspace</span>
            <span className="slash">/</span>
            {nav.find((n) => n.id === page)?.label}
          </div>
          <div className="top-actions">
            <Tag>
              <LockKey size={11} />
              Personal
            </Tag>
            <button
              className="icon-button"
              aria-label="Refresh workspace"
              onClick={() => reload().catch((e) => setError(e.message))}
            >
              <ArrowClockwise size={17} />
            </button>
          </div>
        </header>
        <main id="main">
          <div className="feedback" aria-live="polite">
            {notice && (
              <div className="notice">
                <CheckCircle size={17} />
                {notice}
                <button
                  className="icon-button"
                  aria-label="Dismiss notice"
                  onClick={() => setNotice("")}
                >
                  <X size={15} />
                </button>
              </div>
            )}
            {error && (
              <div role="alert" className="error">
                <WarningCircle size={17} />
                {error}
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setError("")}
                >
                  <X size={15} />
                </button>
              </div>
            )}
          </div>
          {!workspace ? (
            <Empty title="Loading your workspace">
              {error
                ? "Check the personal backend connection, then refresh."
                : "Reading saved inbox and task state."}
            </Empty>
          ) : (
            <>
              {["discover", "drafts", "pipeline", "library"].includes(page) && (
                <div
                  className="acq-view-tabs"
                  role="group"
                  aria-label="Workspace view"
                >
                  <button
                    aria-pressed={!acquisitionView}
                    onClick={() => setAcquisitionView(false)}
                  >
                    {
                      (
                        {
                          discover: "Client prospects",
                          drafts: "Conversation replies",
                          pipeline: "Client stages",
                          library: "Catalog & agents",
                        } as Record<string, string>
                      )[page]
                    }
                  </button>
                  <button
                    aria-pressed={acquisitionView}
                    onClick={() => setAcquisitionView(true)}
                  >
                    {
                      (
                        {
                          discover: "Job opportunities",
                          drafts: "Outreach & applications",
                          pipeline: "Application stages",
                          library: "Profile & documents",
                        } as Record<string, string>
                      )[page]
                    }
                  </button>
                </div>
              )}
              {acquisitionView &&
                ["discover", "drafts", "pipeline", "library"].includes(
                  page,
                ) && (
                  <AcquisitionWorkspace
                    token={session.access_token}
                    area={
                      page as "discover" | "drafts" | "pipeline" | "library"
                    }
                    opportunities={workspace.opportunities}
                  />
                )}
              {page === "today" && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">YOUR DAILY QUEUE</p>
                      <h1>Keep the next step moving.</h1>
                      <p className="muted">
                        Conversations that need your attention, with the context
                        beside them.
                      </p>
                    </div>
                    <button onClick={() => setImportOpen(true)}>
                      <Plus size={17} />
                      Import conversation
                    </button>
                  </div>
                  <div className="summary-strip">
                    <div>
                      <strong>{tasks.length}</strong>
                      <span>Open tasks</span>
                    </div>
                    <div>
                      <strong>
                        {tasks.filter((t) => t.status === "review").length}
                      </strong>
                      <span>Ready for review</span>
                    </div>
                    <div>
                      <strong>
                        {tasks.filter((t) => t.status === "blocked").length}
                      </strong>
                      <span>Need your input</span>
                    </div>
                    <div>
                      <strong>
                        {
                          workspace.opportunities.filter(
                            (o) =>
                              o.stage === "won" || o.stage === "onboarding",
                          ).length
                        }
                      </strong>
                      <span>Won opportunities</span>
                    </div>
                  </div>
                  <section
                    className="workspace-records panel"
                    aria-label="Existing workspace records"
                  >
                    <div>
                      <h2>Your existing workspace</h2>
                      <p className="muted">
                        {overviewError ||
                          "Saved research and proof are available before the first inbox sync."}
                      </p>
                    </div>
                    <button onClick={() => go("discover")}>
                      <strong>{overview?.leads.toLocaleString() ?? "…"}</strong>
                      <span>
                        Saved leads
                        <small>
                          {overview
                            ? `${overview.contacted} previously contacted`
                            : "Reading contact history"}
                        </small>
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                    <button onClick={() => go("library")}>
                      <strong>{overview?.proofs ?? "…"}</strong>
                      <span>
                        Proof items<small>Open your library</small>
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                  </section>
                  <div className="queue-layout">
                    <section className="panel">
                      <div className="section-heading">
                        <h2>Next actions</h2>
                        <Tag>{tasks.length} open</Tag>
                      </div>
                      {tasks.length ? (
                        tasks.map((t) => (
                          <button
                            className="task-row"
                            key={t.id}
                            onClick={() =>
                              t.conversation_id
                                ? go("inbox", t.conversation_id)
                                : go("pipeline", t.opportunity_id || "")
                            }
                          >
                            <span className="task-icon">
                              <Robot size={20} />
                            </span>
                            <span className="task-info">
                              <strong>{t.title}</strong>
                              <span>
                                {t.blocker ||
                                  t.result?.summary ||
                                  "Waiting for its assigned workflow"}
                              </span>
                              <small>
                                {t.agent} · {date(t.created_at)}
                              </small>
                            </span>
                            <Tag tone={t.status === "blocked" ? "amber" : ""}>
                              {t.status}
                            </Tag>
                            <ArrowUpRight size={17} />
                          </button>
                        ))
                      ) : (
                        <Empty title="No open tasks">
                          New business conversations will appear here after the
                          first successful inbox sync.
                        </Empty>
                      )}
                    </section>
                    <aside className="context-panel">
                      <p className="eyebrow">YOUR GUARDRAILS</p>
                      <h3>You make the final call.</h3>
                      <p>
                        Agents prepare the work. Review the full recipient,
                        subject, and message before approving a send.
                      </p>
                      <div className="rule">
                        <span>Cold outreach</span>
                        <strong>5 attempts / day</strong>
                      </div>
                      <div className="rule">
                        <span>Approved replies</span>
                        <strong>20 attempts / day</strong>
                      </div>
                      <div className="rule">
                        <span>Job applications</span>
                        <strong>5 attempts / day</strong>
                      </div>
                      <div className="rule">
                        <span>Additional running cost</span>
                        <strong>$25 / month cap</strong>
                      </div>
                      <button
                        className="text-button"
                        onClick={() => go("connections")}
                      >
                        View connections
                        <ArrowUpRight size={16} />
                      </button>
                    </aside>
                  </div>
                  <AcquisitionWorkspace
                    token={session.access_token}
                    area="today"
                    opportunities={workspace.opportunities}
                  />
                </>
              )}
              {page === "discover" && !acquisitionView && (
                <Discover
                  token={session.access_token}
                  onConversation={(id) => go("inbox", id)}
                />
              )}
              {page === "library" && !acquisitionView && (
                <Library token={session.access_token} workspace={workspace} />
              )}
              {page === "inbox" && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">CONVERSATIONS</p>
                      <h1>One inbox. Clear next steps.</h1>
                    </div>
                    <button onClick={() => setImportOpen(true)}>
                      <Plus size={17} />
                      Import from OnlineJobs
                    </button>
                  </div>
                  <div
                    className={
                      "inbox-layout " + (selected ? "has-selection" : "")
                    }
                  >
                    <section className="inbox-list">
                      <div className="filters">
                        <label className="sr-only" htmlFor="search">
                          Search conversations
                        </label>
                        <input
                          id="search"
                          placeholder="Search subject or contact"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                        <label className="sr-only" htmlFor="category">
                          Classification
                        </label>
                        <select
                          id="category"
                          value={filter}
                          onChange={(e) => setFilter(e.target.value)}
                        >
                          <option value="all">All conversations</option>
                          {Object.entries(categoryLabels).map(([v, l]) => (
                            <option key={v} value={v}>
                              {l}
                            </option>
                          ))}
                        </select>
                      </div>
                      {conversations.map((t) => (
                        <button
                          key={t.id}
                          className={
                            "conversation-row " +
                            (selected === t.id ? "selected" : "")
                          }
                          onClick={() => setSelected(t.id)}
                        >
                          <div>
                            <strong>
                              {t.reply_email || "Contact needs review"}
                            </strong>
                            <small>{date(t.last_message_at)}</small>
                          </div>
                          <span>{t.subject}</span>
                          <Tag
                            tone={t.category === "needs_review" ? "amber" : ""}
                          >
                            {categoryLabels[t.category]}
                          </Tag>
                        </button>
                      ))}
                      {!conversations.length && (
                        <Empty title="No conversations here">
                          Sync your personal mailbox or import an OnlineJobs
                          conversation.
                        </Empty>
                      )}
                    </section>
                    <section className="thread-panel">
                      {c ? (
                        <Thread
                          key={c.id}
                          conversation={c}
                          token={session.access_token}
                          tasks={workspace.tasks.filter(
                            (t) => t.conversation_id === c.id,
                          )}
                          busy={busy}
                          onBack={() => setSelected("")}
                          onDraft={() => go("drafts", c.id)}
                          action={action}
                        />
                      ) : (
                        <Empty title="Select a conversation">
                          Read the message, check its source, and review the
                          next action.
                        </Empty>
                      )}
                    </section>
                  </div>
                  {(olderCursor === undefined
                    ? workspace.next_before
                    : olderCursor) && (
                    <button disabled={busy} onClick={loadOlder}>
                      Load older conversations
                    </button>
                  )}
                </>
              )}
              {page === "drafts" && !acquisitionView && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">WRITE & REVIEW</p>
                      <h1>Say the right thing next.</h1>
                      <p className="muted">
                        Save a revision, read it in full, then approve that
                        exact message.
                      </p>
                    </div>
                  </div>
                  <div className="draft-layout">
                    <section className="draft-list">
                      {workspace.conversations
                        .filter((x) =>
                          ["onlinejobs_conversation", "direct_client"].includes(
                            x.category,
                          ),
                        )
                        .map((x) => (
                          <button
                            key={x.id}
                            className={
                              "conversation-row " +
                              (selected === x.id ? "selected" : "")
                            }
                            onClick={() => setSelected(x.id)}
                          >
                            <strong>{x.subject}</strong>
                            <span>
                              {x.reply_email || "Recipient unverified"}
                            </span>
                            <Tag>
                              {workspace.drafts.find(
                                (d) =>
                                  d.inbound_message_id === x.latest_inbound_id,
                              )?.status || "Not drafted"}
                            </Tag>
                          </button>
                        ))}
                    </section>
                    {c ? (
                      <DraftEditor
                        key={
                          c.id +
                          ":" +
                          c.context_version +
                          ":" +
                          (selectedDraft?.revision || 0)
                        }
                        conversation={c}
                        draft={selectedDraft}
                        workspace={workspace}
                        busy={busy}
                        action={action}
                      />
                    ) : (
                      <Empty title="Choose a conversation to draft">
                        Agents' suggestions stay separate from your saved
                        message until you use them.
                      </Empty>
                    )}
                  </div>
                </>
              )}
              {page === "pipeline" && !acquisitionView && (
                <Pipeline
                  workspace={workspace}
                  action={action}
                  busy={busy}
                  go={go}
                />
              )}
              {page === "connections" && (
                <>
                  <div className="page-heading">
                    <div>
                      <p className="eyebrow">CONNECTIONS & HEALTH</p>
                      <h1>Your tools and workflow health.</h1>
                      <p className="muted">
                        Saved observations, account checks and work still
                        needing setup.
                      </p>
                    </div>
                  </div>
                  <AcquisitionWorkspace
                    token={session.access_token}
                    area="connections"
                    opportunities={workspace.opportunities}
                  />
                  <Connections workspace={workspace} />
                </>
              )}
            </>
          )}
        </main>
      </div>
      <ImportDialog
        open={importOpen}
        close={() => setImportOpen(false)}
        busy={busy}
        action={action}
      />
    </div>
  );
}

type Action = (
  path: string,
  data: unknown,
  success: string,
) => Promise<boolean>;
function Thread({
  conversation: c,
  token,
  tasks,
  busy,
  onBack,
  onDraft,
  action,
}: {
  conversation: Conversation;
  token: string;
  tasks: Workspace["tasks"];
  busy: boolean;
  onBack: () => void;
  onDraft: () => void;
  action: Action;
}) {
  const [messages, setMessages] = useState<Message[]>([]),
    [historyTruncated, setHistoryTruncated] = useState(false),
    [error, setError] = useState(""),
    [category, setCategory] = useState<Category>(c.category),
    [reason, setReason] = useState(""),
    [confirmSuppress, setConfirmSuppress] = useState(false);
  useEffect(() => {
    const ctrl = new AbortController();
    api<{ messages: Message[]; history_truncated?: boolean }>(
      token,
      "/api/conversations/" + c.id,
      undefined,
      ctrl.signal,
    )
      .then((r) => {
        setMessages(r.messages);
        setHistoryTruncated(!!r.history_truncated);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => ctrl.abort();
  }, [c.id, c.context_version, token]);
  return (
    <>
      <div className="thread-heading">
        <button
          className="icon-button mobile-only"
          onClick={onBack}
          aria-label="Back to inbox"
        >
          <ArrowLeft size={20} />
        </button>
        <div>
          <h2>{c.subject}</h2>
          <p>{c.reply_email || "Reply address needs confirmation"}</p>
        </div>
        <Tag>
          {c.acquisition_source === "onlinejobs"
            ? "OnlineJobs origin"
            : c.acquisition_source === "direct"
              ? "Direct origin"
              : "Origin unconfirmed"}
        </Tag>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <div className="message-list">
        {historyTruncated && (
          <p className="muted">
            Showing the latest 500 messages. Earlier history remains saved in
            Hawkins.
          </p>
        )}
        {messages.map((m) => (
          <article
            className={"message " + m.direction}
            key={m.id}
            id={"message-" + m.id}
          >
            <div className="message-meta">
              <strong>{m.direction === "out" ? "You" : m.sender}</strong>
              <span>
                {date(m.occurred_at)} ·{" "}
                {m.channel === "onlinejobs_import" ? "Owner import" : "Gmail"}
              </span>
            </div>
            {m.deleted_at ? (
              <p className="muted">
                This message was removed from the monitored mailbox.
              </p>
            ) : (
              <pre>
                {m.body ||
                  "The notification does not contain the full message."}
              </pre>
            )}
          </article>
        ))}
      </div>
      <div className="thread-tools">
        <div className="classification-box">
          <h3>Classification</h3>
          <p>{c.classification_reason}</p>
          <div className="form-row">
            <label>
              Category
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as Category)}
              >
                {Object.entries(categoryLabels).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reason for correction
              <input
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="What supports this classification?"
              />
            </label>
          </div>
          <button
            disabled={busy || !reason.trim()}
            onClick={async () => {
              if (
                await action(
                  "/api/classification",
                  { conversation_id: c.id, category, reason },
                  "Classification saved and locked.",
                )
              )
                setReason("");
            }}
          >
            Save correction
          </button>
        </div>
        {tasks
          .filter((t) => !["done", "dismissed"].includes(t.status))
          .map((t) => (
            <div className="agent-result" key={t.id}>
              {t.originating_message_id && (
                <a
                  className="text-button"
                  href={"#message-" + t.originating_message_id}
                >
                  View originating message
                </a>
              )}
              <div className="section-heading">
                <h3>
                  {t.agent} · {t.title}
                </h3>
                <Tag tone={t.status === "blocked" ? "amber" : ""}>
                  {t.status}
                </Tag>
              </div>
              {t.blocker && <p className="amber-text">{t.blocker}</p>}
              {t.result && (
                <>
                  <p>{t.result.summary}</p>
                  {t.result.evidence.map((e, i) => (
                    <blockquote key={i}>{e}</blockquote>
                  ))}
                  {t.result.missing.length > 0 && (
                    <p className="muted">
                      Missing: {t.result.missing.join("; ")}
                    </p>
                  )}
                </>
              )}
              <div className="button-row">
                {t.status === "blocked" && (
                  <button
                    disabled={busy}
                    onClick={() =>
                      action(
                        "/api/tasks/action",
                        { task_id: t.id, action: "retry" },
                        "Task queued for retry.",
                      )
                    }
                  >
                    Retry task
                  </button>
                )}
                <button
                  disabled={busy || t.status === "running"}
                  onClick={() =>
                    action(
                      "/api/tasks/action",
                      { task_id: t.id, action: "done" },
                      "Task marked done.",
                    )
                  }
                >
                  Mark done
                </button>
                <button
                  disabled={busy || t.status === "running"}
                  onClick={() =>
                    action(
                      "/api/tasks/action",
                      { task_id: t.id, action: "dismiss" },
                      "Task dismissed.",
                    )
                  }
                >
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        <div className="thread-footer">
          <button
            className="primary"
            disabled={
              !c.reply_verified ||
              c.suppressed ||
              c.bounced ||
              !["onlinejobs_conversation", "direct_client"].includes(c.category)
            }
            onClick={onDraft}
          >
            <NotePencil size={17} />
            Prepare reply
          </button>
          <button
            className="danger-link"
            onClick={() => setConfirmSuppress(true)}
          >
            Do not contact
          </button>
        </div>
      </div>
      <Modal
        open={confirmSuppress}
        onClose={() => setConfirmSuppress(false)}
        title="Stop contact"
        description="This suppresses the contact across Hawkins campaigns and cancels pending outreach."
      >
        <p>{c.reply_email || c.subject}</p>
        <button
          disabled={busy}
          onClick={async () => {
            if (
              await action(
                "/api/suppress",
                { conversation_id: c.id },
                "Contact suppressed.",
              )
            )
              setConfirmSuppress(false);
          }}
        >
          Confirm do not contact
        </button>
      </Modal>
    </>
  );
}

function DraftEditor({
  conversation: c,
  draft,
  workspace: w,
  busy,
  action,
}: {
  conversation: Conversation;
  draft: Draft | undefined;
  workspace: Workspace;
  busy: boolean;
  action: Action;
}) {
  const [subject, setSubject] = useState(
    draft?.subject ||
      (/^(re:)/i.test(c.subject) ? c.subject : "Re: " + c.subject),
  );
  const [body, setBody] = useState(draft?.body || ""),
    [proof, setProof] = useState(draft?.proof_id || ""),
    [review, setReview] = useState(false);
  const suggestion = w.tasks.find(
    (t) =>
      t.conversation_id === c.id &&
      t.context_version === c.context_version &&
      t.result?.draft_body &&
      t.status === "review",
  );
  const dirty =
    subject !== (draft?.subject || "") ||
    body !== (draft?.body || "") ||
    proof !== (draft?.proof_id || "");
  const immutable =
    !!draft &&
    ["claimed", "sending", "send_unknown", "sent"].includes(draft.status);
  const valid = c.reply_verified && !c.suppressed && !c.bounced;
  return (
    <section className="editor panel">
      <div className="section-heading">
        <h2>Reply draft</h2>
        <Tag>{draft ? "Revision " + draft.revision : "Unsaved"}</Tag>
      </div>
      <p className="muted">
        To: <strong>{c.reply_email || "Unverified recipient"}</strong>
      </p>
      {!valid && (
        <div className="error">
          Verify this contact and resolve suppression before drafting.
        </div>
      )}
      {suggestion && !immutable && (
        <div className="suggestion">
          <Robot size={19} />
          <div>
            <strong>Steve has a suggestion</strong>
            <p>{suggestion.result?.summary}</p>
          </div>
          <button onClick={() => setBody(suggestion.result!.draft_body)}>
            Use suggestion
          </button>
        </div>
      )}
      <label>
        Subject
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          disabled={immutable}
        />
      </label>
      <label>
        Message
        <textarea
          rows={15}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Answer their current request in your own words."
          disabled={immutable}
        />
      </label>
      <label>
        Verified proof
        <select
          value={proof}
          onChange={(e) => setProof(e.target.value)}
          disabled={immutable}
        >
          <option value="">No proof selected</option>
          {w.proofs.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title} {p.proof_kind === "prototype" ? "(prototype)" : ""}
            </option>
          ))}
        </select>
      </label>
      {proof && (
        <p className="proof-note">
          {w.proofs.find((p) => p.id === proof)?.claim_text}
          <br />
          <a
            href={w.proofs.find((p) => p.id === proof)?.proof_url}
            target="_blank"
            rel="noreferrer"
          >
            View verified proof <ArrowUpRight size={13} />
          </a>
          <button
            className="text-button"
            disabled={immutable}
            onClick={() =>
              setBody(
                (b) =>
                  b + "\n\n" + w.proofs.find((p) => p.id === proof)?.proof_url,
              )
            }
          >
            Insert proof link
          </button>
        </p>
      )}
      {w.sender_footer && !immutable && (
        <button
          className="text-button"
          onClick={() => setBody((b) => b + "\n\n" + w.sender_footer)}
        >
          Insert reviewed sender footer
        </button>
      )}
      {dirty && !immutable && (
        <p className="amber-text">
          Unsaved edits. Save before reviewing; leaving this conversation
          discards unsaved text.
        </p>
      )}
      <div className="editor-footer">
        <button
          disabled={
            busy ||
            !valid ||
            !body.trim() ||
            !subject.trim() ||
            immutable ||
            !dirty
          }
          onClick={() =>
            action(
              "/api/drafts/save",
              {
                conversation_id: c.id,
                expected_revision: draft?.revision || 0,
                subject,
                body,
                proof_id: proof || null,
              },
              "New revision saved. Previous approval is invalid.",
            )
          }
        >
          Save revision
        </button>
        <button
          className="primary"
          disabled={busy || dirty || draft?.status !== "pending_review"}
          onClick={() => setReview(true)}
        >
          <PaperPlaneTilt size={17} />
          Review & approve
        </button>
      </div>
      {!w.mailbox?.replies_enabled && (
        <p className="muted">
          Sending is disabled. Drafts can still be prepared and reviewed.
        </p>
      )}
      {draft?.status === "send_unknown" && (
        <div className="error">
          Needs checking. Reconcile this attempt against Gmail Sent before any
          retry.
        </div>
      )}
      {draft?.gmail_message_id && (
        <p className="notice">
          Gmail accepted this revision. Message ID: {draft.gmail_message_id}
        </p>
      )}
      <Modal
        open={review}
        onClose={() => setReview(false)}
        title={"Approve revision " + draft?.revision}
        description="Approval applies only to this saved recipient, subject, and full message. The worker sends it after checking context and limits."
      >
        <dl className="review-meta">
          <dt>To</dt>
          <dd>{draft?.recipient_email}</dd>
          <dt>Subject</dt>
          <dd>{draft?.subject}</dd>
        </dl>
        <pre className="review-body">{draft?.body}</pre>
        <div className="button-row">
          <button onClick={() => setReview(false)}>Back to draft</button>
          <button
            className="primary"
            disabled={busy || !w.mailbox?.replies_enabled}
            onClick={async () => {
              if (
                await action(
                  "/api/drafts/approve",
                  { message_id: draft?.id, revision: draft?.revision },
                  "Exact revision approved and queued. Gmail acceptance is still pending.",
                )
              )
                setReview(false);
            }}
          >
            Approve & queue send
          </button>
        </div>
      </Modal>
    </section>
  );
}

function Pipeline({
  workspace: w,
  action,
  busy,
  go,
}: {
  workspace: Workspace;
  action: Action;
  busy: boolean;
  go: (p: Page, id?: string) => void;
}) {
  const [editing, setEditing] = useState(""),
    [stage, setStage] = useState<Stage>("new"),
    [note, setNote] = useState("");
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">FROM FIRST CONTACT TO ONBOARDING</p>
          <h1>Know where every opportunity stands.</h1>
          <p className="muted">
            A positive reply is a next step. A won deal needs your confirmation.
          </p>
        </div>
        <button onClick={() => go("discover")}>
          View saved leads
          <ArrowUpRight size={16} />
        </button>
      </div>
      <div className="pipeline-table panel">
        <div className="pipeline-row table-heading">
          <span>Opportunity</span>
          <span>Source</span>
          <span>Stage</span>
          <span>Next step</span>
        </div>
        {w.opportunities.map((o) => (
          <div className="pipeline-row" key={o.id}>
            <div>
              <strong>{o.title}</strong>
              <small>
                {o.kind === "job" ? "Application" : "Client opportunity"}
              </small>
            </div>
            <span>
              {o.acquisition_source === "onlinejobs"
                ? "OnlineJobs"
                : o.acquisition_source}
            </span>
            <Tag>{stageLabels[o.stage]}</Tag>
            <div className="button-row">
              <button
                onClick={() => {
                  setEditing(o.id);
                  setStage(o.stage);
                  setNote(o.stage_note || "");
                }}
              >
                Update stage
              </button>
              <button
                className="icon-button"
                aria-label={"Open " + o.title}
                onClick={() =>
                  go(
                    "inbox",
                    w.conversations.find((c) => c.opportunity_id === o.id)?.id,
                  )
                }
              >
                <ArrowUpRight size={17} />
              </button>
            </div>
          </div>
        ))}
        {!w.opportunities.length && (
          <Empty title="Your pipeline starts with a conversation">
            Qualified client and application conversations will appear here.
          </Empty>
        )}
      </div>
      {w.tasks
        .filter(
          (t) =>
            t.agent === "Joyce" && !["dismissed", "done"].includes(t.status),
        )
        .map((t) => (
          <section className="panel onboarding" key={t.id}>
            <div className="section-heading">
              <h2>Joyce · {t.title}</h2>
              <Tag>{t.status}</Tag>
            </div>
            <p>
              {t.blocker ||
                t.result?.summary ||
                "Your onboarding checklist is queued."}
            </p>
            {t.result?.missing.map((x, i) => (
              <p key={i}>□ {x}</p>
            ))}
            {t.result?.draft_body && <pre>{t.result.draft_body}</pre>}
            <div className="button-row">
              {t.status === "blocked" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    action(
                      "/api/tasks/action",
                      { task_id: t.id, action: "retry" },
                      "Onboarding task queued.",
                    )
                  }
                >
                  Retry
                </button>
              )}
              <button
                disabled={busy || t.status === "running"}
                onClick={() =>
                  action(
                    "/api/tasks/action",
                    { task_id: t.id, action: "done" },
                    "Onboarding task completed.",
                  )
                }
              >
                Mark done
              </button>
            </div>
          </section>
        ))}
      <Modal
        open={!!editing}
        onClose={() => setEditing("")}
        title="Update opportunity"
        description="Record the evidence for a won or lost outcome. Onboarding follows a confirmed accepted agreement."
      >
        <label>
          Stage
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as Stage)}
          >
            {Object.entries(stageLabels).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Agreement or outcome notes
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder="What was agreed, and where is it recorded?"
          />
        </label>
        <button
          className="primary"
          disabled={busy || (["won", "lost"].includes(stage) && !note.trim())}
          onClick={async () => {
            if (
              await action(
                "/api/stage",
                { opportunity_id: editing, stage, note },
                "Opportunity stage updated.",
              )
            )
              setEditing("");
          }}
        >
          Save stage
        </button>
      </Modal>
    </>
  );
}

function Connections({ workspace: w }: { workspace: Workspace }) {
  return (
    <>
      <section className="panel connection">
        <div className="connection-icon">
          <EnvelopeSimple size={25} />
        </div>
        <div>
          <h2>Personal Gmail</h2>
          <p>{w.mailbox?.email || OWNER}</p>
          <p className="muted">
            Last successful sync: {date(w.mailbox?.last_success_at || null)}
          </p>
          <p className="muted">
            Last attempt: {date(w.mailbox?.last_attempt_at || null)}
          </p>
        </div>
        <Tag tone={w.mailbox?.error_code ? "amber" : ""}>
          {w.mailbox?.error_code
            ? "Needs attention"
            : w.mailbox?.last_success_at
              ? "Sync recorded"
              : "Setup needed"}
        </Tag>
      </section>
      {w.mailbox?.error_code && (
        <div className="error">
          Inbox sync failed. Check the personal credential and hosted worker.
          Unprocessed mail remains pending.
        </div>
      )}
      <section className="panel connection">
        <div className="connection-icon">
          <LockKey size={25} />
        </div>
        <div>
          <h2>Hawkins database</h2>
          <p>mtdavgadkiiofwikzdtn</p>
          <p className="muted">
            Owner-only API access. Existing contact history and suppression are
            shared.
          </p>
        </div>
        <Tag>Connected to this workspace</Tag>
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Processing backlog</h2>
        </div>
        <p>
          {w.statistics?.stored_messages ?? "—"} messages stored ·{" "}
          {w.statistics?.pending_tasks ?? "—"} tasks waiting or running ·{" "}
          {w.statistics?.blocked_tasks ?? "—"} blocked ·{" "}
          {w.statistics?.scheduled_tasks ?? "—"} scheduled reminders
        </p>
        <p className="muted">
          Gmail's unprocessed message count is unknown until a complete sync. A
          failed scan keeps its previous checkpoint.
        </p>
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Sending controls</h2>
          <Tag tone={w.mailbox?.replies_enabled ? "" : "amber"}>
            {w.mailbox?.replies_enabled
              ? "Replies enabled"
              : "Replies disabled"}
          </Tag>
        </div>
        <div className="limits">
          <div>
            <strong>{w.settings?.daily_send_limit || 5}</strong>
            <span>Cold attempts per day</span>
          </div>
          <div>
            <strong>{w.mailbox?.reply_limit || 20}</strong>
            <span>Approved replies per day</span>
          </div>
          <div>
            <strong>
              ${(w.settings?.monthly_cost_cap_cents || 2500) / 100}
            </strong>
            <span>Shared monthly cost cap</span>
          </div>
        </div>
        <p className="muted">
          Limits use Asia/Manila. Uncertain attempts keep their slot until
          reconciled. Activation stays outside this interface.
        </p>
      </section>
      <section className="panel">
        <div className="section-heading">
          <h2>Recent agent runs</h2>
          <Clock size={18} />
        </div>
        {w.runs.length ? (
          w.runs.map((r) => (
            <div className="run-row" key={r.id}>
              <strong>{r.agent}</strong>
              <span>{date(r.started_at)}</span>
              <Tag
                tone={
                  r.status === "blocked" || r.status === "failed" ? "amber" : ""
                }
              >
                {r.status}
              </Tag>
              <span className="muted">{r.error_code || ""}</span>
            </div>
          ))
        ) : (
          <Empty title="No agent runs recorded">
            The hosted task worker will record its work here.
          </Empty>
        )}
      </section>
    </>
  );
}

function ImportDialog({
  open,
  close,
  busy,
  action,
}: {
  open: boolean;
  close: () => void;
  busy: boolean;
  action: Action;
}) {
  const [url, setUrl] = useState(""),
    [subject, setSubject] = useState(""),
    [body, setBody] = useState(""),
    [priorContext, setPriorContext] = useState(""),
    [email, setEmail] = useState(""),
    [at, setAt] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  return (
    <Modal
      open={open}
      onClose={close}
      title="Import an OnlineJobs conversation"
      description="Copy the latest incoming message from the platform. Keep its original source and the email the contact explicitly provided."
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (
            await action(
              "/api/inbox/import",
              {
                platform_reference: url,
                subject,
                body,
                prior_context: priorContext,
                reply_email: email,
                recipient_confirmed: confirmed,
                occurred_at: new Date(at + "+08:00").toISOString(),
              },
              "Conversation imported. Its next action is in your queue.",
            )
          ) {
            close();
            setUrl("");
            setSubject("");
            setBody("");
            setPriorContext("");
            setEmail("");
            setAt("");
            setConfirmed(false);
          }
        }}
      >
        <label>
          OnlineJobs conversation URL
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://www.onlinejobs.ph/messages/…"
          />
        </label>
        <label>
          Subject
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            required
          />
        </label>
        <label>
          Latest incoming message
          <textarea
            rows={6}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            required
          />
        </label>
        <div className="form-row">
          <label>
            Message time · Manila
            <input
              type="datetime-local"
              value={at}
              onChange={(e) => setAt(e.target.value)}
              required
            />
          </label>
          <label>
            Contact's reply email
            <input
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setConfirmed(false);
              }}
              placeholder="Leave empty if unavailable"
            />
          </label>
        </div>
        <label>
          Previous question or offer (optional)
          <textarea
            rows={3}
            maxLength={4000}
            value={priorContext}
            onChange={(e) => setPriorContext(e.target.value)}
            placeholder="Include the preceding Loom offer when the reply only says yes."
          />
        </label>
        {email && (
          <label className="checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              required
            />
            This contact explicitly provided this email in the conversation.
          </label>
        )}
        <div className="button-row">
          <button type="button" onClick={close}>
            Cancel
          </button>
          <button
            className="primary"
            disabled={busy || (!!email && !confirmed)}
          >
            Import conversation
          </button>
        </div>
      </form>
    </Modal>
  );
}
