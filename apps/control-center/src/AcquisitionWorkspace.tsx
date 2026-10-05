import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  Briefcase,
  WarningCircle,
  ArrowsClockwise,
  CheckCircle,
} from "@phosphor-icons/react";
import { api } from "./api";
import { SafeLink } from "./WorkspaceCatalog";
import { currentCoverLetter } from "./jobDraft";
import type { Opportunity, Task } from "./types";

type Resource = {
  id: string;
  provider: string;
  external_id: string;
  kind: string;
  title: string;
  url: string | null;
  version: string;
  content: string;
  verified_at: string | null;
  active: boolean;
};
type Job = {
  id: string;
  opportunity_id: string;
  title: string;
  company: string;
  source_url: string;
  platform: string;
  description: string;
  status: string;
  context_version: number;
  questions: string[];
  blockers: string[];
  source_verified_at: string | null;
  historical_applied_at: string | null;
};
type SavedDraft = {
  id: string;
  kind: string;
  revision: number;
  status: string;
  recipient_email: string;
  subject: string;
  body: string;
  job_id?: string;
  application_payload?: {
    letter_body?: string;
    resources: Resource[];
    answers: { question: string; answer: string }[];
    delivery: string;
    apply_points: number;
  };
  blocker?: string | null;
};
type Detail = {
  job: Job;
  draft: SavedDraft | null;
  tasks: Task[];
  drafting?: { model_configured: boolean };
  history: {
    id: string;
    original: {
      content_evidence: string;
      sent_body?: string;
      draft_body?: string;
    };
  }[];
  attempts: { id: string; status: string; provider_result?: unknown }[];
  conversation_options?: {
    id: string;
    subject: string;
    opportunity_id: string | null;
    category: string;
    reply_email: string | null;
  }[];
  linked_conversations?: { id: string; subject: string }[];
};
type Connection = {
  provider: string;
  identity: string | null;
  status: string;
  selected: Record<string, unknown>;
  verified_at: string | null;
  last_success_at: string | null;
  error_code: string | null;
  enabled: boolean;
};
type Workflow = {
  id: string;
  name: string;
  purpose: string;
  active: boolean | null;
  observed_at: string | null;
  schedule?: string;
  last_success_at?: string | null;
  last_error?: string | null;
};
type Operation = {
  id: string;
  kind: string;
  status: string;
  error_code: string | null;
  created_at: string;
};
type Meeting = {
  id: string;
  provider: string;
  title: string;
  starts_at: string | null;
  status: string;
  summary: string;
  opportunity_id: string | null;
  correlation_key: string | null;
  action_items: unknown[];
};
type Batch = {
  id: string;
  digest: string;
  status: string;
  summary: {
    records: number;
    duplicates: number;
    new: number;
    conflicts: string[];
    notice: string;
  };
  records?: Record<string, unknown>[];
};
type State = {
  ready: boolean;
  drafting?: { model_configured: boolean };
  error?: string;
  workflows: Workflow[];
  connections?: Connection[];
  jobs?: Job[];
  job_total?: number;
  drafts?: SavedDraft[];
  uncertain_outreach_attempts?: {
    id: string;
    message_id: string;
    subject: string;
  }[];
  resources?: Resource[];
  operations?: Operation[];
  meetings?: Meeting[];
  imports?: Batch[];
  recommendations?: {
    id: string;
    title: string;
    agent: string;
    status: string;
    reason: string;
    evidence: string[];
  }[];
  controls?: {
    sending_enabled?: boolean;
    applications_enabled: boolean;
    application_daily_limit: number;
    legacy_queue_reconciled_at: string | null;
  };
  budget?: {
    used_cents: number;
    outreach: number;
    applications: number;
    replies: number;
  };
  crm_links?: {
    opportunity_id: string;
    remote_id: string;
    remote_stage: string;
    conflict: {
      remote_stage: string;
      requested_stage: string;
      outcome: string;
    } | null;
  }[];
};
type Area =
  "today" | "discover" | "drafts" | "pipeline" | "library" | "connections";
const label = (s: string) => s.replaceAll("_", " ");
const when = (s: string | null | undefined) =>
  s
    ? new Date(s).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Not verified";
const jobStages = [
  "new",
  "qualified",
  "applied",
  "interview",
  "offer",
  "hired",
  "closed",
];
type Mutate = (path: string, body: unknown) => Promise<unknown>;

export function AcquisitionWorkspace({
  token,
  area,
  opportunities = [],
}: {
  token: string;
  area: Area;
  opportunities?: Opportunity[];
}) {
  const [state, setState] = useState<State | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [jobId, setJobId] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null),
    [tab, setTab] = useState("jobs");
  const [moreJobs, setMoreJobs] = useState<Job[]>([]);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const load = useCallback(async () => {
    setState(await api<State>(token, "/api/acquisition"));
  }, [token]);
  useEffect(() => {
    let alive = true;
    const run = () => load().catch((e) => alive && setError(e.message));
    run();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") run();
    }, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [load]);
  useEffect(() => {
    if (!jobId) {
      setDetail(null);
      return;
    }
    const ctrl = new AbortController();
    api<Detail>(token, "/api/acquisition/jobs/" + jobId, undefined, ctrl.signal)
      .then(setDetail)
      .catch((e) => !ctrl.signal.aborted && setError(e.message));
    return () => ctrl.abort();
  }, [token, jobId, state]);
  const mutate: Mutate = async (path, body) => {
    if (busy) throw new Error("Wait for the current action");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await api<{ result: unknown }>(
        token,
        "/api/acquisition/" + path,
        body,
      );
      await load();
      setNotice("Saved to your personal workspace.");
      return response.result;
    } catch (e) {
      setError((e as Error).message);
      throw e;
    } finally {
      setBusy(false);
    }
  };
  const run = (kind: string) =>
    mutate("queue", { kind, request_id: crypto.randomUUID() })
      .then(() =>
        setNotice(
          "Queued for the hosted worker. Check Connections for its result.",
        ),
      )
      .catch(() => {});
  if (!state)
    return <p className="muted">{error || "Loading acquisition workspace…"}</p>;
  const resources = state.resources || [],
    jobs = [
      ...new Map(
        [...(state.jobs || []), ...moreJobs].map((j) => [j.id, j]),
      ).values(),
    ];
  const loadMoreJobs = async () => {
    setLoadingJobs(true);
    try {
      const page = await api<{ jobs: Job[] }>(
        token,
        "/api/acquisition/jobs?after_id=" +
          encodeURIComponent(jobs[jobs.length - 1].id),
      );
      setMoreJobs((old) => [...old, ...page.jobs]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingJobs(false);
    }
  };
  return (
    <div className="acquisition-workspace">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="acq-notice" role="status">
          <CheckCircle size={17} />
          {notice}
        </p>
      )}
      {!state.ready && (
        <section className="panel acq-warning">
          <WarningCircle size={22} />
          <div>
            <h2>Acquisition setup needs attention</h2>
            <p>{state.error}</p>
            <p className="muted">
              Your existing leads, inbox and library remain available. Saved
              workflow links are shown in Connections.
            </p>
          </div>
        </section>
      )}
      {area === "today" && state.ready && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">YOUR NEXT DECISIONS</p>
              <h2>Move the right work forward.</h2>
            </div>
            <button disabled={busy} onClick={() => run("agent_run")}>
              Run next agent task
            </button>
          </div>
          {(state.recommendations || []).slice(0, 4).map((r) => (
            <div className="acq-recommendation" key={r.id}>
              <span
                className={"tag " + (r.status === "blocked" ? "amber" : "")}
              >
                {r.agent} · {label(r.status)}
              </span>
              <h3>{r.title}</h3>
              <p>{r.reason}</p>
              {r.evidence.map((e, i) => (
                <blockquote key={i}>{e}</blockquote>
              ))}
            </div>
          ))}
          {!state.recommendations?.length && (
            <p className="muted">
              Add a researched job in Discover or connect your inbox to create
              evidence-backed next actions.
            </p>
          )}
          <div className="acq-counters">
            <span>
              {
                jobs.filter((j) => !["hired", "closed"].includes(j.status))
                  .length
              }{" "}
              open applications
            </span>
            <span>
              {state.budget?.applications || 0}/5 application attempts today
            </span>
            <span>
              ${((state.budget?.used_cents || 0) / 100).toFixed(2)} / $25 this
              month
            </span>
          </div>
        </section>
      )}
      {(area === "discover" || area === "pipeline" || area === "drafts") &&
        state.ready && (
          <section className="panel acq-jobs">
            <div className="section-heading">
              <div>
                <p className="eyebrow">CLIENTS & JOB APPLICATIONS</p>
                <h1>
                  {area === "drafts"
                    ? "Outreach and cover letters"
                    : area === "pipeline"
                      ? "Application pipeline"
                      : "Job opportunities"}
                </h1>
                <p className="muted">
                  {state.job_total || 0} saved jobs. Original source and
                  submission history stay with each opportunity.
                </p>
              </div>
              {area === "discover" && (
                <button disabled={busy} onClick={() => run("discover")}>
                  Research client prospects
                </button>
              )}
            </div>
            {area === "drafts" && (
              <div className="acq-tabs" role="group" aria-label="Draft type">
                <button
                  aria-pressed={tab === "jobs"}
                  onClick={() => setTab("jobs")}
                >
                  Job applications
                </button>
                <button
                  aria-pressed={tab === "outreach"}
                  onClick={() => setTab("outreach")}
                >
                  Client outreach
                </button>
              </div>
            )}
            {area === "discover" && (
              <details className="acq-details">
                <summary>Add a job from its original posting</summary>
                <JobIntake mutate={mutate} busy={busy} />
              </details>
            )}
            {area === "drafts" && tab === "outreach" ? (
              <Outreach
                enabled={state.controls?.sending_enabled || false}
                uncertain={state.uncertain_outreach_attempts || []}
                drafts={(state.drafts || []).filter((d) =>
                  ["initial", "followup"].includes(d.kind),
                )}
                mutate={mutate}
                busy={busy}
              />
            ) : (
              <div className="acq-split">
                <div className="acq-job-list">
                  {jobs.map((j) => (
                    <button
                      className={
                        "conversation-row " + (jobId === j.id ? "selected" : "")
                      }
                      onClick={() => setJobId(j.id)}
                      key={j.id}
                    >
                      <span className="tag">
                        {j.platform} · {label(j.status)}
                      </span>
                      <strong>{j.title}</strong>
                      <span>{j.company}</span>
                      {j.blockers.length > 0 && <small>Needs your input</small>}
                    </button>
                  ))}
                  {!jobs.length && (
                    <div className="acq-empty">
                      <Briefcase size={30} />
                      <h3>Your application queue starts here.</h3>
                      <p>
                        Add a job in Discover or preview selected history in
                        Connections.
                      </p>
                    </div>
                  )}
                  {(state.job_total || 0) > jobs.length && (
                    <button
                      disabled={loadingJobs}
                      onClick={() => void loadMoreJobs()}
                    >
                      {loadingJobs ? "Loading…" : "Load more jobs"}
                    </button>
                  )}
                </div>
                <div>
                  {detail ? (
                    <JobDetail
                      key={detail.job.id + ":" + (detail.draft?.revision || 0)}
                      detail={detail}
                      resources={resources}
                      mutate={mutate}
                      busy={busy}
                      refresh={() =>
                        void load().catch((e) => setError(e.message))
                      }
                      enabled={state.controls?.applications_enabled || false}
                    />
                  ) : (
                    <div className="acq-empty">
                      <h3>Select an opportunity</h3>
                      <p>
                        Review the posting, agent findings, cover letter,
                        screening answers, and exact application.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        )}
      {area === "library" && state.ready && (
        <ResourceLibrary resources={resources} mutate={mutate} busy={busy} />
      )}
      {area === "connections" && (
        <>
          <section className="panel">
            <div className="section-heading">
              <div>
                <p className="eyebrow">THE WORKFLOWS YOU ALREADY BUILT</p>
                <h2>Hawkins in n8n</h2>
              </div>
              {state.ready && (
                <button
                  disabled={busy}
                  onClick={() => run("integrations_sync")}
                >
                  <ArrowsClockwise size={16} /> Check selected connections
                </button>
              )}
            </div>
            <div className="acq-workflows">
              {state.workflows.map((w) => (
                <article key={w.id}>
                  <div>
                    <h3>{w.name}</h3>
                    <p className="muted">{w.purpose}</p>
                  </div>
                  <span className={"tag " + (!w.observed_at ? "amber" : "")}>
                    {w.observed_at
                      ? w.active
                        ? "Published at last check"
                        : "Inactive at last check"
                      : "Live status unverified"}
                  </span>
                  <p className="muted">
                    {w.schedule || "Schedule not checked"}
                    <br />
                    Last observed: {when(w.observed_at)}
                    <br />
                    Last successful run: {when(w.last_success_at)}
                  </p>
                  {w.last_error && (
                    <p className="error">{label(w.last_error)}</p>
                  )}
                  <SafeLink
                    url={"https://n8n.armageddonvivas.cloud/workflow/" + w.id}
                  >
                    Open workflow
                  </SafeLink>
                </article>
              ))}
            </div>
          </section>
          {state.ready && (
            <>
              <section className="panel">
                <div className="section-heading">
                  <h2>Application controls</h2>
                  <span
                    className={
                      "tag " +
                      (state.controls?.applications_enabled ? "" : "amber")
                    }
                  >
                    {state.controls?.applications_enabled
                      ? "Applications enabled"
                      : "Applications disabled"}
                  </span>
                </div>
                <p>
                  {state.controls?.application_daily_limit ?? 5} individually
                  approved application attempts per Asia/Manila day.
                </p>
                <p className="muted">
                  {state.controls?.legacy_queue_reconciled_at
                    ? "Legacy queue reconciliation recorded. Personal platform and worker checks still apply to every submission."
                    : "Legacy application queues must be reconciled before Hawkins can submit. Unknown outcomes keep their daily slot."}
                </p>
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>Personal tools</h2>
                </div>
                <p>
                  AI writing:{" "}
                  {state.drafting?.model_configured
                    ? "Personal model key configured. Successful drafting and budget checks are verified per task."
                    : "Setup needed. Steve needs the personal AI connection to prepare cover letters and replies."}
                </p>
                <p className="muted">
                  Select only your own resources. Enter credentials privately
                  through the setup command; never paste keys here.
                </p>
                <div className="acq-connections">
                  {(state.connections || []).map((c) => (
                    <ConnectionCard
                      key={c.provider}
                      connection={c}
                      mutate={mutate}
                      busy={busy}
                    />
                  ))}
                </div>
              </section>
              <HistoryImport mutate={mutate} busy={busy} />
              <section className="panel">
                <h2>Calls and proposal context</h2>
                <p className="muted">
                  Link a selected call to an opportunity to prepare a proposal.
                  Matching calendar and booking IDs are shown once.
                </p>
                {(state.meetings || [])
                  .filter(
                    (m, i, all) =>
                      !m.correlation_key ||
                      all.findIndex(
                        (x) => x.correlation_key === m.correlation_key,
                      ) === i,
                  )
                  .map((m) => (
                    <MeetingCard
                      key={m.id}
                      meeting={m}
                      opportunities={opportunities}
                      mutate={mutate}
                      busy={busy}
                    />
                  ))}
                {!state.meetings?.length && (
                  <p className="muted">
                    No personal meetings have been synchronized.
                  </p>
                )}
              </section>
              <CrmPanel
                links={state.crm_links || []}
                opportunities={opportunities}
                mutate={mutate}
                busy={busy}
              />
              <section className="panel">
                <h2>Hosted work queue</h2>
                <p className="muted">
                  Queue state is stored in Hawkins. Unknown deliveries require
                  reconciliation.
                </p>
                {(state.operations || []).map((o) => (
                  <div className="acq-operation" key={o.id}>
                    <strong>{label(o.kind)}</strong>
                    <span className="tag">{label(o.status)}</span>
                    <span>{when(o.created_at)}</span>
                    {o.error_code && <small>{label(o.error_code)}</small>}
                    {o.status === "needs_checking" &&
                      o.kind === "ghl_mirror" && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void mutate("crm-reconcile", {
                              operation_id: o.id,
                            }).catch(() => {})
                          }
                        >
                          Check the current CRM result
                        </button>
                      )}
                    {o.status === "blocked" && o.kind !== "ghl_mirror" && (
                      <button
                        disabled={busy}
                        onClick={() =>
                          mutate("operation", {
                            id: o.id,
                            action: "retry",
                          }).catch(() => {})
                        }
                      >
                        Retry
                      </button>
                    )}
                  </div>
                ))}
                {!state.operations?.length && <p>No operations queued.</p>}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}

function JobIntake({ mutate, busy }: { mutate: Mutate; busy: boolean }) {
  const [error, setError] = useState("");
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      d = new FormData(form);
    setError("");
    try {
      await mutate("jobs", {
        source_url: d.get("source"),
        title: d.get("title"),
        company: d.get("company"),
        description: d.get("description"),
        questions: String(d.get("questions")).split("\n").filter(Boolean),
        source_confirmed: d.get("confirmed") === "on",
      });
      form.reset();
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <form className="acq-form" onSubmit={submit}>
      <label>
        Original job URL
        <input
          name="source"
          type="url"
          required
          placeholder="https://www.onlinejobs.ph/jobseekers/job/…"
        />
      </label>
      <div className="acq-fields">
        <label>
          Job title
          <input name="title" required maxLength={500} />
        </label>
        <label>
          Company
          <input name="company" required maxLength={500} />
        </label>
      </div>
      <label>
        Job description
        <textarea name="description" required rows={5} maxLength={16000} />
      </label>
      <label>
        Screening questions, one per line
        <textarea name="questions" rows={3} />
      </label>
      <label className="acq-check">
        <input type="checkbox" name="confirmed" required />I reviewed this
        posting and its original source.
      </label>
      <button className="primary" disabled={busy}>
        Save job and prepare agent tasks
      </button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}

function JobDetail({
  detail: d,
  resources,
  mutate,
  busy,
  enabled,
  refresh,
}: {
  detail: Detail;
  resources: Resource[];
  mutate: Mutate;
  busy: boolean;
  enabled: boolean;
  refresh: () => void;
}) {
  const p = d.draft?.application_payload;
  const suggestion = currentCoverLetter(d.job, d.tasks, resources);
  const profileReady = resources.some(
    (r) => r.kind === "profile" && r.active && r.verified_at,
  );
  const currentTasks = d.tasks.filter(
    (t) =>
      t.context_version === d.job.context_version &&
      ["qualify_job", "cover_letter"].includes(t.task_type),
  );
  const blockedTask = currentTasks.find((t) => t.status === "blocked");
  const [edited, setEdited] = useState(false);
  const [manualEditing, setManualEditing] = useState(false);
  const [subject, setSubject] = useState(d.draft?.subject || d.job.title),
    [body, setBody] = useState(
      p?.letter_body || d.draft?.body || suggestion?.result?.draft_body || "",
    ),
    [answers, setAnswers] = useState<Record<string, string>>(
      Object.fromEntries((p?.answers || []).map((a) => [a.question, a.answer])),
    ),
    [selected, setSelected] = useState<string[]>(
      (p?.resources || []).map((r) => r.id),
    ),
    [delivery, setDelivery] = useState(p?.delivery || "manual"),
    [reviewed, setReviewed] = useState(false),
    [note, setNote] = useState(""),
    [stage, setStage] = useState(d.job.status),
    [reference, setReference] = useState("");
  const [conversationId, setConversationId] = useState("");
  useEffect(() => {
    if (d.draft || edited) return;
    const result = suggestion?.result;
    setBody(result?.draft_body || "");
    setAnswers(
      Object.fromEntries(
        (result?.screening_answers || []).map((a) => [a.question, a.answer]),
      ),
    );
    const content = [
      result?.draft_body,
      ...(result?.screening_answers || []).map((a) => a.answer),
    ].join("\n");
    setSelected(
      resources
        .filter(
          (r) =>
            result?.source_resources?.some((saved) => saved.id === r.id) &&
            (r.kind === "profile" || (!!r.url && content.includes(r.url))),
        )
        .map((r) => r.id),
    );
    setReviewed(false);
  }, [d.draft, edited, suggestion, resources]);
  const dirty =
    subject !== (d.draft?.subject || d.job.title) ||
    body !== (p?.letter_body || d.draft?.body || "") ||
    delivery !== (p?.delivery || "manual") ||
    JSON.stringify(selected) !==
      JSON.stringify((p?.resources || []).map((r) => r.id)) ||
    d.job.questions.some(
      (q) =>
        (answers[q] || "") !==
        (p?.answers.find((a) => a.question === q)?.answer || ""),
    );
  const editable =
    !d.draft ||
    !["claimed", "sending", "send_unknown", "sent"].includes(d.draft.status);
  const save = () =>
    mutate("application-save", {
      job_id: d.job.id,
      expected_revision: d.draft?.revision || 0,
      subject,
      body,
      resource_ids: selected,
      answers: d.job.questions.map((question) => ({
        question,
        answer: answers[question] || "",
      })),
      delivery,
    }).catch(() => {});
  return (
    <div className="acq-job-detail">
      <div className="section-heading">
        <h3>{d.job.title}</h3>
        <SafeLink url={d.job.source_url}>Original posting</SafeLink>
      </div>
      <p>
        {d.job.company} · <span className="tag">{label(d.job.status)}</span>
      </p>
      {["new", "qualified"].includes(d.job.status) && (
        <section className="acq-review" aria-label="Cover letter assistance">
          <h3>
            {d.draft
              ? "Review your cover letter"
              : suggestion
                ? "Steve’s draft is ready"
                : "Steve prepares your cover letter"}
          </h3>
          <p className="muted">
            A short letter focused on what the employer needs, what you can
            deliver, and relevant verified work. You review the wording before
            anything is submitted.
          </p>
          {!d.draft && !suggestion && (
            <>
              {!d.drafting?.model_configured && (
                <p>
                  AI writing needs its personal connection.{" "}
                  <a href="#/connections">Open Connections</a>.
                </p>
              )}
              {!profileReady && (
                <p>
                  Review your experience once in <a href="#/library">Library</a>{" "}
                  so Steve can use it across applications.
                </p>
              )}
              {blockedTask && <p className="error">{blockedTask.blocker}</p>}
              {d.drafting?.model_configured && profileReady && !blockedTask && (
                <p>
                  {currentTasks.some((t) => t.status === "running")
                    ? "Your qualification brief or cover letter is being prepared."
                    : "Waiting for the hosted worker to qualify this job and prepare your letter."}
                </p>
              )}
              <button type="button" disabled={busy} onClick={refresh}>
                Check for draft
              </button>
            </>
          )}
          {suggestion && !d.draft && (
            <p>
              AI draft loaded below, including supported screening answers.
              Review it, make any changes, then save the exact revision.
            </p>
          )}
        </section>
      )}
      <details>
        <summary>Read the job description</summary>
        <p className="acq-pre">{d.job.description}</p>
      </details>
      {d.job.blockers.map((x) => (
        <p className="error" key={x}>
          {x}
        </p>
      ))}
      <details className="acq-details">
        <summary>Linked conversations</summary>
        {(d.linked_conversations || []).map((c) => (
          <p key={c.id}>{c.subject}</p>
        ))}
        <p className="muted">
          Link only a conversation you have checked against this posting. New
          correspondence will invalidate pending application approval.
        </p>
        <label>
          Conversation
          <select
            value={conversationId}
            onChange={(e) => setConversationId(e.target.value)}
          >
            <option value="">Select a verified match</option>
            {(d.conversation_options || [])
              .filter(
                (c) =>
                  !(d.linked_conversations || []).some((x) => x.id === c.id),
              )
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.subject} · {c.reply_email || label(c.category)}
                </option>
              ))}
          </select>
        </label>
        <button
          disabled={!conversationId || busy}
          onClick={() => {
            const c = d.conversation_options?.find(
              (x) => x.id === conversationId,
            );
            if (c)
              void mutate("job-conversation", {
                job_id: d.job.id,
                conversation_id: c.id,
                expected_opportunity_id: c.opportunity_id,
              })
                .then(() => setConversationId(""))
                .catch(() => {});
          }}
        >
          Confirm conversation belongs to this job
        </button>
      </details>
      {d.tasks.map((t) => (
        <details className="acq-agent-result" key={t.id}>
          <summary>
            {t.agent} · {t.title} · {label(t.status)}
          </summary>
          <p>
            {t.blocker || t.result?.summary || "Waiting for the hosted worker"}
          </p>
          {t.result?.evidence.map((x, i) => (
            <blockquote key={i}>{x}</blockquote>
          ))}
          {t.result?.draft_body && (
            <>
              <pre className="acq-pre">{t.result.draft_body}</pre>
              {t.id === suggestion?.id && (
                <button
                  type="button"
                  disabled={!editable || busy}
                  onClick={() => {
                    setBody(t.result!.draft_body);
                    setAnswers(
                      Object.fromEntries(
                        (t.result!.screening_answers || []).map((a) => [
                          a.question,
                          a.answer,
                        ]),
                      ),
                    );
                    setEdited(true);
                    setReviewed(false);
                  }}
                >
                  Use this suggestion
                </button>
              )}
            </>
          )}
        </details>
      ))}
      {d.history.map((h) => (
        <details key={h.id}>
          <summary>
            Imported history · {label(h.original.content_evidence)}
          </summary>
          <p className="acq-pre">
            {h.original.sent_body ||
              h.original.draft_body ||
              "No message text recorded"}
          </p>
        </details>
      ))}
      {["new", "qualified"].includes(d.job.status) &&
        !body &&
        !d.draft &&
        !manualEditing && (
          <button
            type="button"
            onClick={() => {
              setManualEditing(true);
              setEdited(true);
            }}
          >
            Write a draft manually (optional)
          </button>
        )}
      {["new", "qualified"].includes(d.job.status) &&
        (!!body || !!d.draft || manualEditing) && (
          <div className="acq-form">
            <label>
              Subject
              <input
                value={subject}
                onChange={(e) => {
                  setSubject(e.target.value);
                  setEdited(true);
                  setReviewed(false);
                }}
                disabled={!editable}
              />
            </label>
            <label>
              Cover letter
              <textarea
                rows={9}
                value={body}
                onChange={(e) => {
                  setBody(e.target.value);
                  setEdited(true);
                  setReviewed(false);
                }}
                disabled={!editable}
              />
            </label>
            {d.job.questions.map((q) => (
              <label key={q}>
                {q}
                <textarea
                  rows={2}
                  value={answers[q] || ""}
                  onChange={(e) => {
                    setAnswers({ ...answers, [q]: e.target.value });
                    setEdited(true);
                    setReviewed(false);
                  }}
                  disabled={!editable}
                />
              </label>
            ))}
            <fieldset>
              <legend>Reviewed profile and document links</legend>
              <p className="muted">
                Profile facts guide the draft. Selected resume, proof, and
                proposal links appear in the exact submission below.
              </p>
              {resources
                .filter(
                  (r) =>
                    r.active &&
                    r.verified_at &&
                    ["profile", "resume", "proof", "proposal"].includes(r.kind),
                )
                .map((r) => (
                  <label className="acq-check" key={r.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(r.id)}
                      disabled={!editable}
                      onChange={(e) => {
                        setEdited(true);
                        setSelected(
                          e.target.checked
                            ? [...selected, r.id]
                            : selected.filter((i) => i !== r.id),
                        );
                        setReviewed(false);
                      }}
                    />
                    {r.title} · {r.kind}
                    {r.url && <SafeLink url={r.url}>Preview</SafeLink>}
                  </label>
                ))}
              {!resources.length && (
                <p>Add reviewed profile facts and documents in Library.</p>
              )}
            </fieldset>
            <label>
              Delivery
              <select
                value={delivery}
                disabled={!editable}
                onChange={(e) => {
                  setDelivery(e.target.value);
                  setEdited(true);
                  setReviewed(false);
                }}
              >
                <option value="manual">Approved manual handoff</option>
                <option
                  value="onlinejobs"
                  disabled={d.job.platform !== "onlinejobs"}
                >
                  OnlineJobs approved submission · 1 Apply Point
                </option>
              </select>
            </label>
            <button disabled={busy || !editable || !body.trim()} onClick={save}>
              Save exact revision
            </button>
          </div>
        )}
      {d.draft && (
        <section className="acq-review">
          <div className="section-heading">
            <h3>Exact submission · revision {d.draft.revision}</h3>
            <span className="tag">{label(d.draft.status)}</span>
          </div>
          <p>
            <strong>{d.draft.subject}</strong>
          </p>
          <pre className="acq-pre">{d.draft.body}</pre>
          <p className="muted">
            {p?.delivery === "onlinejobs"
              ? "OnlineJobs · 1 Apply Point"
              : "Manual handoff"}
          </p>
          {d.draft.blocker && <p className="error">{label(d.draft.blocker)}</p>}
          {!enabled && (
            <p className="muted">
              Submission is disabled until the personal worker, platform access,
              and legacy queue cutover are verified.
            </p>
          )}
          <label className="acq-check">
            <input
              type="checkbox"
              checked={reviewed}
              onChange={(e) => setReviewed(e.target.checked)}
              disabled={dirty || d.draft.status !== "pending_review"}
            />
            I reviewed this complete stored revision and its links.
          </label>
          <button
            className="primary"
            disabled={
              busy ||
              !enabled ||
              dirty ||
              !reviewed ||
              !!d.draft.blocker ||
              d.draft.status !== "pending_review"
            }
            onClick={() =>
              mutate("application-approve", {
                message_id: d.draft!.id,
                revision: d.draft!.revision,
              }).catch(() => {})
            }
          >
            {p?.delivery === "onlinejobs"
              ? "Approve & submit"
              : "Approve manual handoff"}
          </button>
          {dirty && (
            <p className="muted">Save your changes before approving.</p>
          )}
        </section>
      )}
      {d.attempts.map((a) => (
        <div className="acq-operation" key={a.id}>
          <span>
            {a.status === "send_unknown" ? "Needs checking" : label(a.status)}
          </span>
          {p?.delivery === "manual" && a.status === "claimed" && (
            <button
              disabled={busy}
              onClick={() =>
                void mutate("manual-handoff", { attempt_id: a.id }).catch(
                  () => {},
                )
              }
            >
              Begin approved manual handoff
            </button>
          )}
          {p?.delivery === "onlinejobs" && a.status === "send_unknown" && (
            <button
              disabled={busy}
              onClick={() =>
                void mutate("application-reconcile", {
                  attempt_id: a.id,
                }).catch(() => {})
              }
            >
              Check platform submission record
            </button>
          )}
          {p?.delivery === "manual" && ["send_unknown"].includes(a.status) && (
            <>
              <label>
                Submission receipt URL
                <input
                  type="url"
                  value={reference}
                  onChange={(e) => setReference(e.target.value)}
                />
              </label>
              <button
                disabled={busy || !reference}
                onClick={() =>
                  mutate("manual-result", {
                    attempt_id: a.id,
                    reference,
                  }).catch(() => {})
                }
              >
                Record my completed submission
              </button>
            </>
          )}
        </div>
      ))}
      <details className="acq-details">
        <summary>Update application outcome</summary>
        <div className="acq-form">
          <label>
            Stage
            <select value={stage} onChange={(e) => setStage(e.target.value)}>
              {jobStages
                .filter((s) => s !== "applied" || d.job.status === "applied")
                .map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Outcome evidence or accepted offer
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
            />
          </label>
          <button
            disabled={
              busy ||
              stage === "applied" ||
              (["hired", "closed"].includes(stage) && !note.trim())
            }
            onClick={() =>
              mutate("job-stage", {
                job_id: d.job.id,
                status: stage,
                note,
              }).catch(() => {})
            }
          >
            Save owner-confirmed stage
          </button>
        </div>
      </details>
    </div>
  );
}

function Outreach({
  drafts,
  uncertain,
  enabled,
  mutate,
  busy,
}: {
  drafts: SavedDraft[];
  enabled: boolean;
  uncertain: { id: string; message_id: string; subject: string }[];
  mutate: Mutate;
  busy: boolean;
}) {
  const [id, setId] = useState("");
  const d = drafts.find((x) => x.id === id);
  return (
    <div className="acq-split">
      <div>
        {uncertain.map((a) => (
          <div className="acq-warning" key={a.id}>
            <p>Needs checking: {a.subject}</p>
            <button
              disabled={busy}
              onClick={() =>
                void mutate("outreach-reconcile", { attempt_id: a.id }).catch(
                  () => {},
                )
              }
            >
              Check Sent mail without resending
            </button>
          </div>
        ))}
        {drafts.map((m) => (
          <button
            className="conversation-row"
            key={m.id}
            onClick={() => setId(m.id)}
          >
            <strong>{m.subject}</strong>
            <span>{m.recipient_email}</span>
            <span className="tag">{label(m.status)}</span>
          </button>
        ))}
        {!drafts.length && (
          <p className="muted">
            No researched outreach drafts are stored yet. Research prospects in
            Discover.
          </p>
        )}
      </div>
      {d ? (
        <OutreachEditor
          enabled={enabled}
          key={d.id + ":" + d.revision}
          draft={d}
          mutate={mutate}
          busy={busy}
        />
      ) : (
        <p className="muted">
          Select a researched draft to review its exact content.
        </p>
      )}
    </div>
  );
}
function OutreachEditor({
  enabled,
  draft: d,
  mutate,
  busy,
}: {
  enabled: boolean;
  draft: SavedDraft;
  mutate: Mutate;
  busy: boolean;
}) {
  const [subject, setSubject] = useState(d.subject),
    [body, setBody] = useState(d.body),
    [reviewed, setReviewed] = useState(false);
  const dirty = subject !== d.subject || body !== d.body;
  return (
    <div className="acq-form">
      <p>
        To: <strong>{d.recipient_email}</strong> · Revision {d.revision}
      </p>
      <label>
        Subject
        <input
          value={subject}
          onChange={(e) => {
            setSubject(e.target.value);
            setReviewed(false);
          }}
        />
      </label>
      <label>
        Full email
        <textarea
          rows={14}
          value={body}
          onChange={(e) => {
            setBody(e.target.value);
            setReviewed(false);
          }}
        />
      </label>
      <button
        disabled={busy || !dirty}
        onClick={() =>
          mutate("outreach", {
            message_id: d.id,
            revision: d.revision,
            action: "save",
            subject,
            body,
          }).catch(() => {})
        }
      >
        Save new revision
      </button>
      <label className="acq-check">
        <input
          type="checkbox"
          checked={reviewed}
          disabled={dirty}
          onChange={(e) => setReviewed(e.target.checked)}
        />
        I approve this exact recipient, subject and body.
      </label>
      <button
        className="primary"
        disabled={
          busy ||
          !enabled ||
          dirty ||
          !reviewed ||
          !["draft", "pending_review"].includes(d.status)
        }
        onClick={() =>
          mutate("outreach", {
            message_id: d.id,
            revision: d.revision,
            action: "approve",
          }).catch(() => {})
        }
      >
        Approve & send
      </button>
      <p className="muted">
        {enabled
          ? "Backend suppression, proof and daily-limit checks apply."
          : "Outreach sending is disabled until personal inbox and sender setup are verified."}
      </p>
    </div>
  );
}

function ResourceLibrary({
  resources,
  mutate,
  busy,
}: {
  resources: Resource[];
  mutate: Mutate;
  busy: boolean;
}) {
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget,
      d = new FormData(form);
    try {
      await mutate("resources", {
        provider: d.get("provider"),
        kind: d.get("kind"),
        title: d.get("title"),
        url: d.get("url"),
        external_id: d.get("external_id") || d.get("url") || "personal-profile",
        provider_version: d.get("provider_version"),
        content: d.get("content"),
        reviewed: d.get("reviewed") === "on",
      });
      form.reset();
    } catch {}
  }
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <p className="eyebrow">YOUR VERIFIED EXPERIENCE</p>
          <h2>Profile, resumes and reusable proof</h2>
        </div>
      </div>
      {resources.map((r) => (
        <details className="acq-details" key={r.id}>
          <summary>
            {r.title} · {r.kind} ·{" "}
            {r.verified_at ? "Owner reviewed" : "Review needed"}
          </summary>
          <p className="acq-pre">{r.content}</p>
          {r.url && <SafeLink url={r.url}>Open resource</SafeLink>}
        </details>
      ))}
      <details className="acq-details">
        <summary>Add or update a reviewed resource</summary>
        <form className="acq-form" onSubmit={save}>
          <div className="acq-fields">
            <label>
              Type
              <select name="kind">
                <option value="profile">Profile facts</option>
                <option value="resume">Resume</option>
                <option value="proof">Proof / Loom</option>
                <option value="proposal">Proposal document</option>
              </select>
            </label>
            <label>
              Source
              <select name="provider">
                <option value="manual">Owner supplied</option>
                <option value="google">Personal Drive</option>
                <option value="loom">Loom link</option>
              </select>
            </label>
          </div>
          <label>
            Title
            <input name="title" required />
          </label>
          <label>
            Reviewed link
            <input name="url" type="url" />
          </label>
          <div className="acq-fields">
            <label>
              Original file ID or stable reference
              <input name="external_id" />
            </label>
            <label>
              Drive version, if applicable
              <input name="provider_version" />
            </label>
          </div>
          <label>
            Verified facts and supported claims
            <textarea
              name="content"
              rows={5}
              required
              placeholder="Your relevant experience, actual availability, and proof. Missing rates or dates stay unspecified."
            />
          </label>
          <label className="acq-check">
            <input name="reviewed" type="checkbox" required />I reviewed these
            facts and the selected document version.
          </label>
          <button disabled={busy}>Save reviewed resource</button>
        </form>
      </details>
    </section>
  );
}

const fields: Record<string, [string, string][]> = {
  google: [
    ["calendar_ids", "Personal calendar IDs"],
    ["file_ids", "Selected Drive file IDs"],
    ["sheet_ids", "Selected spreadsheet IDs"],
  ],
  notion: [
    ["bot_id", "Personal integration ID"],
    ["data_source_ids", "Selected data source IDs"],
  ],
  n8n: [["project_ids", "Personal n8n project IDs (one per line)"]],
  calcom: [["event_type_ids", "Acquisition event type IDs"]],
  fathom: [["recording_ids", "Selected recording IDs"]],
  ghl: [
    ["location_id", "Personal location ID"],
    ["pipeline_id", "Personal pipeline ID"],
    [
      "outbound_automation_review",
      "Review of pipeline automations and outbound side effects",
    ],
  ],
};
function ConnectionCard({
  connection: c,
  mutate,
  busy,
}: {
  connection: Connection;
  mutate: Mutate;
  busy: boolean;
}) {
  const f = fields[c.provider] || [];
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget),
      selected: Record<string, unknown> = {};
    for (const [key] of f) {
      const value = String(data.get(key) || "").trim();
      if (value)
        selected[key] = key.endsWith("_ids")
          ? value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : value;
    }
    if (c.provider === "ghl") {
      const map: Record<string, string> = {};
      for (const s of [
        "new",
        "qualified",
        "loom_call",
        "proposal_offer",
        "won",
        "lost",
        "onboarding",
      ]) {
        const v = String(data.get("stage_" + s) || "").trim();
        if (v) map[s] = v;
      }
      selected.stage_map = map;
    }
    await mutate("select-connection", { provider: c.provider, selected }).catch(
      () => {},
    );
  }
  return (
    <article>
      <div className="section-heading">
        <h3>
          {c.provider === "google"
            ? "Google · Gmail / Drive / Calendar"
            : c.provider === "calcom"
              ? "Cal.com"
              : c.provider.toUpperCase()}
        </h3>
        <span className={"tag " + (c.status === "verified" ? "" : "amber")}>
          {label(c.status)}
        </span>
      </div>
      <p>{c.identity || "Identity not verified"}</p>
      <p className="muted">Last successful check: {when(c.last_success_at)}</p>
      {c.error_code && <p className="error">{label(c.error_code)}</p>}
      {c.provider === "loom" && (
        <p className="muted">Add reviewed Loom share links in Library.</p>
      )}
      {c.provider === "onlinejobs" && (
        <p className="muted">
          Personal hosted session, account checks, and legacy queue
          reconciliation are required before submitting.
        </p>
      )}
      {f.length > 0 && (
        <details>
          <summary>Select personal resources</summary>
          <form className="acq-form" onSubmit={save}>
            {f.map(([key, title]) => (
              <label key={key}>
                {title}
                {key.endsWith("_ids") && <small>Comma separated</small>}
                <input
                  name={key}
                  defaultValue={
                    Array.isArray(c.selected[key])
                      ? (c.selected[key] as string[]).join(", ")
                      : String(c.selected[key] || "")
                  }
                />
              </label>
            ))}
            {c.provider === "ghl" && (
              <fieldset>
                <legend>Map Hawkins stages to GHL stage IDs</legend>
                {[
                  "new",
                  "qualified",
                  "loom_call",
                  "proposal_offer",
                  "won",
                  "lost",
                  "onboarding",
                ].map((s) => (
                  <label key={s}>
                    {label(s)}
                    <input
                      name={"stage_" + s}
                      defaultValue={String(
                        ((c.selected.stage_map as Record<string, string>) ||
                          {})[s] || "",
                      )}
                    />
                  </label>
                ))}
              </fieldset>
            )}
            <button disabled={busy}>Save selection for verification</button>
          </form>
        </details>
      )}
      <button
        className="acq-pause"
        disabled={busy || c.status === "paused"}
        onClick={() =>
          mutate("pause", { provider: c.provider }).catch(() => {})
        }
      >
        Pause this connection
      </button>
    </article>
  );
}

function HistoryImport({ mutate, busy }: { mutate: Mutate; busy: boolean }) {
  const [provider, setProvider] = useState("sheets"),
    [resource, setResource] = useState(""),
    [raw, setRaw] = useState(""),
    [batch, setBatch] = useState<Batch | null>(null),
    [error, setError] = useState("");
  async function preview(fetchSource = false) {
    setError("");
    try {
      const result = await mutate(
        fetchSource ? "import-fetch" : "import-preview",
        {
          provider,
          resource_id: resource,
          ...(fetchSource ? {} : { records: JSON.parse(raw) }),
        },
      );
      setBatch(result as Batch);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="panel">
      <h2>Bring your tracking history into Hawkins</h2>
      <p className="muted">
        Preview selected history before committing. No imported approval can
        authorize a new message or application.
      </p>
      <div className="acq-fields">
        <label>
          Source
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setBatch(null);
            }}
          >
            <option value="sheets">Google Sheets</option>
            <option value="notion">Notion</option>
            <option value="manual">Selected export</option>
          </select>
        </label>
        <label>
          Selected source ID
          <input
            value={resource}
            onChange={(e) => {
              setResource(e.target.value);
              setBatch(null);
            }}
          />
        </label>
      </div>
      <button
        disabled={busy || !resource || provider === "manual"}
        onClick={() => preview(true)}
      >
        Read selected source and preview
      </button>
      <details className="acq-details">
        <summary>Import an existing JSON export</summary>
        <label>
          Records, at most 100 per batch
          <textarea
            rows={5}
            value={raw}
            onChange={(e) => {
              setRaw(e.target.value);
              setBatch(null);
            }}
            placeholder={
              '[{"external_id":"row-1","kind":"job","title":"…","source_url":"https://…","description":"…"}]'
            }
          />
        </label>
        <button disabled={busy || !raw || !resource} onClick={() => preview()}>
          Preview import
        </button>
      </details>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {batch && (
        <div className="acq-review">
          <h3>Import preview</h3>
          <p>
            {batch.summary.records} records · {batch.summary.new} new ·{" "}
            {batch.summary.duplicates} duplicates ·{" "}
            {batch.summary.conflicts.length} conflicts
          </p>
          <p className="muted">{batch.summary.notice}</p>
          <div className="acq-import-preview">
            {batch.records?.map((r, i) => (
              <div key={i}>
                <strong>{String(r.title)}</strong>
                <p>{String(r.source_url || r.external_id)}</p>
                <span>{String(r.content_evidence || "")}</span>
                {Array.isArray(r.blockers) &&
                  r.blockers.map((x, i) => (
                    <p className="error" key={i}>
                      {String(x)}
                    </p>
                  ))}
              </div>
            ))}
          </div>
          <button
            className="primary"
            disabled={
              busy ||
              batch.status === "committed" ||
              batch.summary.conflicts.length > 0
            }
            onClick={() =>
              mutate("import-commit", {
                batch_id: batch.id,
                digest: batch.digest,
              })
                .then((r) => setBatch(r as Batch))
                .catch(() => {})
            }
          >
            {batch.status === "committed"
              ? "Imported into Hawkins"
              : "Commit reviewed import"}
          </button>
        </div>
      )}
    </section>
  );
}
function MeetingCard({
  meeting: m,
  opportunities,
  mutate,
  busy,
}: {
  meeting: Meeting;
  opportunities: Opportunity[];
  mutate: Mutate;
  busy: boolean;
}) {
  const [id, setId] = useState(m.opportunity_id || "");
  return (
    <details className="acq-details">
      <summary>
        {m.title} · {m.provider} · {when(m.starts_at)}
      </summary>
      <p className="acq-pre">{m.summary || "Summary not available"}</p>
      <label>
        Related opportunity
        <select value={id} onChange={(e) => setId(e.target.value)}>
          <option value="">Select an opportunity</option>
          {opportunities.map((o) => (
            <option key={o.id} value={o.id}>
              {o.title}
            </option>
          ))}
        </select>
      </label>
      <button
        disabled={busy || !id || !m.summary}
        onClick={() =>
          mutate("link-meeting", {
            meeting_id: m.id,
            opportunity_id: id,
          }).catch(() => {})
        }
      >
        Link call and prepare proposal
      </button>
    </details>
  );
}
function CrmPanel({
  links,
  opportunities,
  mutate,
  busy,
}: {
  links: NonNullable<State["crm_links"]>;
  opportunities: Opportunity[];
  mutate: Mutate;
  busy: boolean;
}) {
  const [id, setId] = useState(""),
    [remote, setRemote] = useState("");
  return (
    <section className="panel">
      <h2>Personal GHL pipeline mirror</h2>
      <p className="muted">
        Link an existing GHL opportunity after verifying the personal location,
        pipeline, and its automations.
      </p>
      <div className="acq-fields">
        <label>
          Hawkins opportunity
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">Select opportunity</option>
            {opportunities.map((o) => (
              <option key={o.id} value={o.id}>
                {o.title}
              </option>
            ))}
          </select>
        </label>
        <label>
          GHL opportunity ID
          <input value={remote} onChange={(e) => setRemote(e.target.value)} />
        </label>
      </div>
      <button
        disabled={busy || !id || !remote}
        onClick={() =>
          mutate("crm-link", { opportunity_id: id, remote_id: remote }).catch(
            () => {},
          )
        }
      >
        Verify and link opportunity
      </button>
      {links.map((l) => (
        <div className="acq-operation" key={l.opportunity_id}>
          <strong>
            {opportunities.find((o) => o.id === l.opportunity_id)?.title ||
              "Linked opportunity"}
          </strong>
          <span>{l.remote_id}</span>
          {l.conflict && (
            <>
              <p className="error">
                CRM {l.conflict.outcome}: review the remote change before
                writing.
              </p>
              {l.conflict.remote_stage &&
                ["keep_remote", "mirror_hawkins"].map((decision) => (
                  <button
                    key={decision}
                    disabled={busy}
                    onClick={() =>
                      mutate("crm-resolve", {
                        opportunity_id: l.opportunity_id,
                        decision,
                      }).catch(() => {})
                    }
                  >
                    {label(decision)}
                  </button>
                ))}
            </>
          )}
        </div>
      ))}
    </section>
  );
}
