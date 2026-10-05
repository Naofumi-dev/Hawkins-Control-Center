import { useState } from "react";
import {
  ArrowUpRight,
  ArrowRight,
  CheckCircle,
  MagnifyingGlass,
  NotePencil,
  ChatCircleText,
  Plus,
  Clock,
  Pause,
  Play,
  Lightning,
  WarningCircle,
  PaperPlaneTilt,
  ArrowDown,
} from "@phosphor-icons/react";
import { useDemo } from "./store";
import { dailyAttempts, monthCost } from "./model";
import {
  Avatar,
  Badge,
  Button,
  KindFilter,
  RelativeTime,
  SectionHeading,
  Status,
  TextLink,
  ToolIcon,
} from "./ui";
import { PageHeading } from "./ui";
import type { Kind } from "./types";

export function Today() {
  const { state, navigate, dispatch, notify } = useDemo();
  const [kind, setKind] = useState<Kind | "all">("all");
  const active = state.opportunities.filter(
    (o) => !["suppressed", "closed"].includes(o.stage),
  );
  const filtered = active.filter((o) => kind === "all" || o.kind === kind);
  const review = filtered.filter(
    (o) => o.stage === "review" || o.stage === "ready",
  );
  const research = filtered.filter((o) => o.stage === "research");
  const replies = filtered.filter(
    (o) => o.stage === "replied" || o.stage === "needs_checking",
  );
  const count = review.length + research.length + replies.length;
  const groups = [
    {
      label: "Drafts to move forward",
      icon: NotePencil,
      rows: review,
      page: "drafts" as const,
    },
    {
      label: "Research to finish",
      icon: MagnifyingGlass,
      rows: research,
      page: "pipeline" as const,
    },
    {
      label: "Conversations to pick up",
      icon: ChatCircleText,
      rows: replies,
      page: "inbox" as const,
    },
  ];
  const date = new Intl.DateTimeFormat("en", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "Asia/Manila",
  }).format(new Date());
  return (
    <div className="page today-page">
      <PageHeading
        title="Make your next connection."
        description="A little research. A thoughtful message. A conversation worth having."
        eyebrow={date}
      >
        <Button onClick={() => navigate("drafts")}>
          <NotePencil size={17} /> Write a draft
        </Button>
        <Button variant="primary" onClick={() => navigate("discover")}>
          <Plus size={17} /> Find opportunities
        </Button>
      </PageHeading>
      <div className="metrics" aria-label="Workspace overview">
        <button onClick={() => navigate("pipeline")}>
          <span>
            In your pipeline <ArrowUpRight size={15} />
          </span>
          <strong>{active.length.toString().padStart(2, "0")}</strong>
          <small>
            {active.filter((o) => o.kind === "client").length} clients{" "}
            <span>·</span> {active.filter((o) => o.kind === "job").length}{" "}
            applications
          </small>
        </button>
        <button onClick={() => navigate("drafts")}>
          <span>
            Waiting for review <NotePencil size={15} />
          </span>
          <strong>
            {active
              .filter((o) => o.stage === "review")
              .length.toString()
              .padStart(2, "0")}
            <i className="metric-dot blue" />
          </strong>
          <small>Your words. Your final say.</small>
        </button>
        <button onClick={() => navigate("inbox")}>
          <span>
            New conversations <ChatCircleText size={15} />
          </span>
          <strong>
            {active
              .filter((o) => o.inboxState === "reply")
              .length.toString()
              .padStart(2, "0")}
            <i className="metric-dot green" />
          </strong>
          <small>Ready for a personal reply</small>
        </button>
        <button onClick={() => navigate("connections")}>
          <span>
            Email attempts today <PaperPlaneTilt size={15} />
          </span>
          <strong>
            {dailyAttempts(state)}
            <em>/ 5</em>
          </strong>
          <small>Includes attempts needing a check</small>
        </button>
      </div>
      <div className="today-columns">
        <section className="queue-panel">
          <div className="queue-heading">
            <div>
              <h2>
                Your work queue <span className="count-box">{count}</span>
              </h2>
              <p>The next useful step for every opportunity.</p>
            </div>
            <span className="live-label">
              <span /> Saved locally
            </span>
          </div>
          <div className="queue-toolbar">
            <KindFilter value={kind} onChange={setKind} all />
            <span className="queue-sort">
              By next action <ArrowDown size={13} />
            </span>
          </div>
          {groups.map(({ label, icon: Icon, rows, page }) => (
            <section className="queue-group" key={label}>
              <div className="group-heading">
                <Icon size={15} />
                <h3>{label}</h3>
                <span>{rows.length}</span>
              </div>
              {rows.length ? (
                rows.map((o) => (
                  <button
                    className="task-row"
                    key={o.id}
                    onClick={() => navigate(page, o.id)}
                  >
                    <Avatar o={o} />
                    <div className="task-name">
                      <strong>{o.company}</strong>
                      <span>{o.title}</span>
                    </div>
                    <span className="kind-label">
                      {o.kind === "client" ? "Client" : "Application"}
                    </span>
                    <Status o={o} />
                    <ArrowUpRight className="row-arrow" size={17} />
                  </button>
                ))
              ) : (
                <div className="queue-empty">
                  <CheckCircle size={16} /> Nothing waiting here.
                </div>
              )}
            </section>
          ))}
          <div className="queue-footer">
            <span>
              <CheckCircle size={14} /> Every message gets your approval.
            </span>
            <TextLink onClick={() => navigate("pipeline")}>
              Open pipeline
            </TextLink>
          </div>
        </section>
        <aside className="today-aside">
          <section className="daily-note">
            <div className="note-header">
              <span className="note-icon">
                <Lightning size={18} weight="duotone" />
              </span>
              <span>THE DAILY BRIEF</span>
              <Badge tone="blue">Sample</Badge>
            </div>
            <h2>A good day to follow through.</h2>
            <p>
              You have{" "}
              <strong>
                {active.filter((o) => o.stage === "review").length} drafts
              </strong>{" "}
              to make your own and{" "}
              <strong>
                {active.filter((o) => o.inboxState === "reply").length}{" "}
                conversations
              </strong>{" "}
              ready for a reply.
            </p>
            <div className="brief-divider" />
            <button onClick={() => navigate("inbox", "client-3")}>
              <Avatar
                o={state.opportunities.find((o) => o.id === "client-3")!}
                small
              />
              <span>
                <strong>Parallel House replied</strong>
                <small>“Could you share a first version?”</small>
              </span>
              <ArrowUpRight size={16} />
            </button>
          </section>
          <section className="connected-panel">
            <SectionHeading
              action={
                <button
                  className="icon-button plain"
                  onClick={() => navigate("connections")}
                  aria-label="View connections"
                >
                  <ArrowUpRight size={17} />
                </button>
              }
            >
              Connected workspace
            </SectionHeading>
            <div className="tool-list">
              {state.connections.slice(0, 5).map((c) => (
                <button
                  key={c.id}
                  onClick={() => navigate("connections", c.id)}
                >
                  <ToolIcon id={c.id} />
                  <span>{c.name}</span>
                  <span className={`connection-label ${c.status}`}>
                    {c.status === "connected"
                      ? "Connected"
                      : c.status === "attention"
                        ? "Reconnect"
                        : "Paused"}
                    <span />
                  </span>
                </button>
              ))}
            </div>
            <button
              className="connection-alert"
              onClick={() => navigate("connections", "notion")}
            >
              <WarningCircle size={17} />
              <span>
                {state.connections.find((c) => c.id === "notion")?.status ===
                "attention"
                  ? "Notion needs a quick reconnect."
                  : "Review your connected tools."}
              </span>
              <ArrowRight size={14} />
            </button>
          </section>
          <section className="automation-panel">
            <div className="section-heading">
              <h2>Working in the background</h2>
              <button
                className="icon-button plain"
                aria-label={
                  state.discoveryPaused ? "Resume discovery" : "Pause discovery"
                }
                onClick={() => {
                  dispatch({ type: "pause" });
                  notify(
                    state.discoveryPaused
                      ? "Demo discovery resumed."
                      : "Demo discovery paused.",
                  );
                }}
              >
                {state.discoveryPaused ? (
                  <Play size={16} />
                ) : (
                  <Pause size={16} />
                )}
              </button>
            </div>
            <div className="schedule-line">
              <span
                className={`status-dot ${state.discoveryPaused ? "amber" : "green"}`}
              />
              <strong>Daily discovery</strong>
              <span>{state.discoveryPaused ? "Paused" : "08:00 PHT"}</span>
            </div>
            <div className="budget-line">
              <span>Monthly demo usage</span>
              <strong>
                ${monthCost(state).toFixed(2)} <span>/ $25</span>
              </strong>
            </div>
            <div className="budget-track">
              <span
                style={{ width: `${Math.min(100, monthCost(state) * 4)}%` }}
              />
            </div>
            <small>Local simulation · Asia/Manila</small>
          </section>
        </aside>
      </div>
      <section className="recent-section">
        <SectionHeading>
          Recent activity{" "}
          <span className="section-caption">A record of the small steps.</span>
        </SectionHeading>
        <div className="activity-strip">
          {state.activities.slice(0, 3).map((a) => (
            <button
              key={a.id}
              onClick={() => navigate(a.page ?? "pipeline", a.opportunityId)}
            >
              <span className="activity-icon">
                <Clock size={18} />
              </span>
              <div>
                <strong>{a.title}</strong>
                <span>{a.detail}</span>
              </div>
              <RelativeTime value={a.at} />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
