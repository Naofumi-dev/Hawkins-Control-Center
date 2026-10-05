import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  CheckCircle,
  FileText,
  NotePencil,
  PaperPlaneTilt,
  Sparkle,
  ClockCounterClockwise,
  Paperclip,
  ShieldCheck,
  FloppyDisk,
  ArrowLeft,
} from "@phosphor-icons/react";
import { PageHeading } from "./ui";
import { useDemo } from "./store";
import {
  currentRevision,
  draftBlock,
  generatedDraft,
  monthCost,
  sendBlock,
} from "./model";
import { resources } from "./fixtures";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  KindFilter,
  Modal,
  ResourcePreview,
  SearchInput,
  Status,
} from "./ui";
import { ReviewDialog } from "./Review";
import { EvidenceList } from "./OpportunityPanel";
import type { DraftKind, Kind, Opportunity, Resource, Revision } from "./types";

export function DraftStudio() {
  const { state, selectedId, navigate } = useDemo();
  const [filter, setFilter] = useState<Kind | "all">("all"),
    [search, setSearch] = useState("");
  const selected = state.opportunities.find((o) => o.id === selectedId);
  const list = state.opportunities.filter(
    (o) =>
      (filter === "all" || o.kind === filter) &&
      `${o.company} ${o.title}`.toLowerCase().includes(search.toLowerCase()),
  );
  const replyMode = location.hash.endsWith("/reply");
  return (
    <div className={`page drafts-page ${selected ? "has-draft" : ""}`}>
      <PageHeading
        title="Your words. A stronger starting point."
        description="Turn researched context into a message that sounds like you."
      />
      <div className="studio-layout">
        <aside className="draft-list">
          <div className="draft-list-top">
            <div className="section-heading">
              <h2>Draft Studio</h2>
              <Badge>{list.length}</Badge>
            </div>
            <KindFilter value={filter} onChange={setFilter} all />
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Find an opportunity…"
              label="Search drafts"
            />
          </div>
          <div className="draft-list-rows">
            {list.map((o) => (
              <button
                key={o.id}
                className={`draft-list-item ${selected?.id === o.id ? "selected" : ""}`}
                onClick={() => navigate("drafts", o.id)}
              >
                <Avatar o={o} small />
                <div>
                  <strong>{o.company}</strong>
                  <p>{o.title}</p>
                  <Status o={o} />
                </div>
              </button>
            ))}
            {!list.length && (
              <Empty title="No matches">Try another company or role.</Empty>
            )}
          </div>
        </aside>
        {selected ? (
          <DraftEditor
            key={`${selected.id}-${replyMode}`}
            o={selected}
            replyMode={replyMode}
          />
        ) : (
          <div className="studio-welcome">
            <span className="large-search">
              <NotePencil size={35} weight="duotone" />
            </span>
            <h2>A thoughtful message starts with context.</h2>
            <p>
              Choose a client or application to review its research, write a
              draft, and make it your own.
            </p>
            <Button
              variant="primary"
              onClick={() => {
                const o = list.find((o) => o.stage === "review") ?? list[0];
                if (o) navigate("drafts", o.id);
              }}
            >
              Open the next draft <ArrowUpRight size={16} />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function DraftEditor({ o, replyMode }: { o: Opportunity; replyMode: boolean }) {
  const { state, dispatch, notify, navigate } = useDemo();
  const current = currentRevision(o);
  const bufferKey = `${o.id}:${replyMode ? "reply" : "main"}`;
  const buffer = state.buffers?.[bufferKey];
  const initial =
    buffer ??
    (replyMode
      ? {
          recipient: o.email,
          subject: `Re: ${o.title}`,
          body: "",
          attachments: [],
        }
      : (current ?? {
          recipient: o.email,
          subject: "",
          body: "",
          attachments: [...o.resourceIds],
        }));
  const [recipient, setRecipient] = useState(initial.recipient),
    [subject, setSubject] = useState(initial.subject),
    [body, setBody] = useState(initial.body),
    [attachments, setAttachments] = useState<string[]>(initial.attachments);
  const [draftKind, setDraftKind] = useState<DraftKind>(
    buffer?.kind ??
      (replyMode
        ? "reply"
        : (o.draft?.kind ?? (o.kind === "job" ? "cover" : "outreach"))),
  );
  const [tone, setTone] = useState("Natural"),
    [length, setLength] = useState("Short"),
    [brief, setBrief] = useState("");
  const [generating, setGenerating] = useState(false),
    [suggestion, setSuggestion] = useState<ReturnType<
      typeof generatedDraft
    > | null>(null);
  const [review, setReview] = useState<"web" | "telegram" | null>(null),
    [history, setHistory] = useState(false),
    [historyRevision, setHistoryRevision] = useState<Revision | null>(null),
    [contextOpen, setContextOpen] = useState(false),
    [preview, setPreview] = useState<Resource | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const dirty =
    !current ||
    current.recipient !== recipient ||
    current.subject !== subject ||
    current.body !== body ||
    JSON.stringify(current.attachments) !== JSON.stringify(attachments) ||
    o.draft?.kind !== draftKind;
  const locked =
    o.suppressed || o.bounced || ["closed", "needs_checking"].includes(o.stage);
  const blocked = draftBlock(o);
  const ready =
    !dirty &&
    o.draft?.approvedRevision === current?.number &&
    o.draft?.status === "approved";
  const sendingBlock = sendBlock(state, o);
  useEffect(() => {
    dispatch({
      type: "buffer",
      key: bufferKey,
      value: dirty
        ? { recipient, subject, body, attachments, kind: draftKind }
        : undefined,
    });
  }, [
    recipient,
    subject,
    body,
    attachments,
    draftKind,
    dirty,
    bufferKey,
    dispatch,
  ]);
  function save() {
    if (locked) return;
    if (draftKind === "followup" && o.inboxState === "reply") {
      notify(
        "This contact replied. Write a manual reply instead of a follow-up.",
      );
      return;
    }
    if (
      draftKind === "followup" &&
      (!o.confirmedAt ||
        (o.followupCreated &&
          (o.draft?.kind !== "followup" || o.draft?.status === "sent")))
    ) {
      notify(
        "Only one follow-up is allowed, after an eligible confirmed initial send.",
      );
      return;
    }
    const proposed = {
      ...o,
      draft: {
        kind: draftKind,
        status: "draft" as const,
        revisions: [
          {
            number: 1,
            recipient,
            subject,
            body,
            attachments,
            createdAt: new Date().toISOString(),
          },
        ],
      },
    };
    if (draftKind === "followup" && draftBlock(proposed)) {
      notify(draftBlock(proposed)!);
      return;
    }
    dispatch({
      type: "save",
      id: o.id,
      revision: { recipient, subject, body, attachments },
      kind: draftKind,
    });
    notify("Draft saved. Review this revision before approving.");
  }
  function generate() {
    if (monthCost(state) + 0.04 > 25) {
      notify("Monthly demo budget reached. You can still write manually.");
      return;
    }
    setGenerating(true);
    dispatch({ type: "cost", amount: 0.04, label: "Demo draft generation" });
    timer.current = setTimeout(() => {
      setSuggestion(generatedDraft(o, draftKind, tone, length, brief));
      setGenerating(false);
    }, 700);
  }
  const context = (
    <>
      <EvidenceList o={o} />
      <div className="context-resources">
        <span className="subsection-label">REFERENCE MATERIAL</span>
        {resources.map((r) => (
          <div className="reference-check" key={r.id}>
            <label>
              <input
                type="checkbox"
                checked={attachments.includes(r.id)}
                disabled={locked}
                onChange={(e) =>
                  setAttachments((v) =>
                    e.target.checked
                      ? [...v, r.id]
                      : v.filter((id) => id !== r.id),
                  )
                }
              />
              <span>
                <strong>{r.title}</strong>
                <small>{r.preview ? "Prototype / preview" : r.provider}</small>
              </span>
            </label>
            <button
              className="plain icon-button"
              aria-label={`Preview ${r.title}`}
              onClick={() => setPreview(r)}
            >
              <ArrowUpRight size={15} />
            </button>
          </div>
        ))}
      </div>
    </>
  );
  return (
    <section className="draft-editor">
      <div className="editor-header">
        <button
          className="mobile-back text-link"
          onClick={() => navigate("drafts")}
        >
          <ArrowLeft size={16} />
          All drafts
        </button>
        <div className="editor-company">
          <Avatar o={o} small />
          <div>
            <h2>{o.company}</h2>
            <span>{o.title}</span>
          </div>
        </div>
        <div className="editor-header-actions">
          <Button variant="ghost" onClick={() => setContextOpen(true)}>
            <FileText size={16} />
            Research & files
          </Button>
          <Button
            variant="ghost"
            className="icon-button"
            aria-label="View revision history"
            onClick={() => {
              setHistoryRevision(current ?? null);
              setHistory(true);
            }}
          >
            <ClockCounterClockwise size={19} />
          </Button>
        </div>
      </div>
      <div className="editor-scroll">
        <div className="composer-controls">
          <label className="field-label">
            Message type
            <select
              value={draftKind}
              disabled={locked}
              onChange={(e) => setDraftKind(e.target.value as DraftKind)}
            >
              {o.kind === "job" ? (
                <option value="cover">Cover letter</option>
              ) : (
                <option value="outreach">Outreach email</option>
              )}
              <option value="followup">Follow-up email</option>
              <option value="reply">Manual reply</option>
            </select>
          </label>
          <label className="field-label">
            Tone
            <select value={tone} onChange={(e) => setTone(e.target.value)}>
              <option>Natural</option>
              <option>Formal</option>
            </select>
          </label>
          <label className="field-label">
            Length
            <select value={length} onChange={(e) => setLength(e.target.value)}>
              <option>Short</option>
              <option>Detailed</option>
            </select>
          </label>
        </div>
        <div className="writing-brief">
          <label className="field-label">
            Your direction <span>Optional</span>
            <input
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder="e.g. Focus on the onboarding workflow…"
              disabled={locked || draftKind === "reply"}
            />
          </label>
          <Button
            onClick={generate}
            disabled={locked || generating || draftKind === "reply"}
          >
            <Sparkle size={17} />
            {generating ? "Preparing a suggestion…" : "Generate suggestion"}
          </Button>
          {generating && (
            <Button
              variant="ghost"
              onClick={() => {
                if (timer.current) clearTimeout(timer.current);
                setGenerating(false);
                notify("Generation stopped. Your current draft is unchanged.");
              }}
            >
              Stop
            </Button>
          )}
        </div>
        {draftKind === "reply" && (
          <div className="inline-note">
            Replies are written by you. Read the linked conversation before
            composing.
          </div>
        )}
        <div className="editor-context-summary">
          <ShieldCheck size={16} />
          <span>
            {o.evidence.length} sample sources<span className="mid-dot">·</span>
            {attachments.length} reference files
          </span>
          <button className="text-link" onClick={() => setContextOpen(true)}>
            View context <ArrowUpRight size={13} />
          </button>
        </div>
        <div className="email-editor">
          <div className="email-field">
            <label htmlFor="draft-to">To</label>
            <input
              id="draft-to"
              type="email"
              placeholder="Published contact email needed"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              disabled={locked}
            />
          </div>
          <div className="email-field">
            <label htmlFor="draft-subject">Subject</label>
            <input
              id="draft-subject"
              placeholder="Add a subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={locked}
            />
          </div>
          <label className="sr-only" htmlFor="draft-body">
            Message body
          </label>
          <textarea
            id="draft-body"
            className="body-editor"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={
              draftKind === "reply"
                ? "Write your reply…"
                : "Write your message, or generate a starting point from the research."
            }
            disabled={locked}
          />
          <div className="editor-document-footer">
            <span>
              {body.trim() ? body.trim().split(/\s+/).length : 0} words
            </span>
            <span>
              {dirty
                ? "Unreviewed edits · kept locally"
                : `Revision ${current?.number ?? 1} · Saved locally`}
            </span>
          </div>
        </div>
        {attachments.length > 0 && (
          <div className="attachment-chips">
            {attachments.map((id) => {
              const r = resources.find((r) => r.id === id);
              return (
                r && (
                  <button key={id} onClick={() => setPreview(r)}>
                    <Paperclip size={14} />
                    {r.title}
                    {r.preview && <span>Preview</span>}
                  </button>
                )
              );
            })}
          </div>
        )}
        {blocked && <div className="inline-alert warning">{blocked}</div>}
        {ready && (
          <div className="approval-receipt">
            <CheckCircle size={19} />
            <span>
              Approved in{" "}
              {o.draft?.approvedVia === "telegram"
                ? "Telegram"
                : "Control Center"}{" "}
              · revision {current?.number}.{" "}
              {draftKind === "cover"
                ? "Ready for you to apply."
                : "Ready for a simulated send."}
            </span>
          </div>
        )}
        {o.draft?.status === "sent" && !dirty && (
          <div className="approval-receipt">
            <CheckCircle size={19} />
            This revision was sent in the demo. See Inbox for its recorded
            result.
          </div>
        )}
        {o.draft?.status === "applied" && !dirty && (
          <div className="approval-receipt">
            <CheckCircle size={19} />
            This application is marked applied in the demo.
          </div>
        )}
      </div>
      <aside className="editor-context-rail">
        <div className="context-rail-title">
          <FileText size={16} />
          <h3>At a glance</h3>
        </div>
        <span className="subsection-label">WHY THIS OPPORTUNITY</span>
        <p>{o.evidence[0]?.text}</p>
        <button className="source-link" onClick={() => setContextOpen(true)}>
          <ArrowUpRight size={13} />
          View source evidence
        </button>
        <div className="rail-divider" />
        <span className="subsection-label">PROPOSED DELIVERABLE</span>
        <p>{o.proposed}</p>
        <div className="rail-divider" />
        <span className="subsection-label">DRAFT REFERENCES</span>
        {attachments.map((id) => {
          const r = resources.find((r) => r.id === id);
          return (
            r && (
              <button
                key={id}
                className="rail-file"
                onClick={() => setPreview(r)}
              >
                <Paperclip size={15} />
                <span>
                  {r.title}
                  <small>
                    {r.preview ? "Prototype / preview" : "Sample reference"}
                  </small>
                </span>
              </button>
            )
          );
        })}
        <Button variant="ghost" onClick={() => setContextOpen(true)}>
          Manage context <ArrowUpRight size={14} />
        </Button>
      </aside>
      <div className="editor-actions">
        <Button onClick={save} disabled={!dirty || locked}>
          <FloppyDisk size={16} />
          Save draft
        </Button>
        <Button
          onClick={() => setReview("telegram")}
          disabled={dirty || !current}
        >
          <PaperPlaneTilt size={16} />
          Telegram preview
        </Button>
        {ready ? (
          draftKind === "cover" ? (
            <Button
              variant="primary"
              onClick={() => {
                dispatch({ type: "apply", id: o.id });
                notify("Application marked applied in the demo.");
              }}
            >
              <CheckCircle size={17} />
              Mark applied · demo
            </Button>
          ) : (
            <Button
              variant="primary"
              title={sendingBlock}
              disabled={!!sendingBlock}
              onClick={() => {
                dispatch({ type: "send", id: o.id, revision: current!.number });
                notify(
                  "Email send simulated. A demo result is recorded in Inbox.",
                );
              }}
            >
              <PaperPlaneTilt size={17} />
              Simulate send
            </Button>
          )
        ) : (
          <Button
            variant="primary"
            disabled={
              dirty ||
              !current ||
              !!blocked ||
              ["sent", "applied"].includes(o.draft?.status ?? "")
            }
            onClick={() => setReview("web")}
          >
            <ShieldCheck size={17} />
            Review & approve
          </Button>
        )}
        {ready && sendingBlock && draftKind !== "cover" && (
          <p className="action-reason">{sendingBlock}</p>
        )}
      </div>
      <ReviewDialog
        o={o}
        via={review ?? "web"}
        open={!!review}
        onClose={() => setReview(null)}
      />
      <Modal
        open={contextOpen}
        onClose={() => setContextOpen(false)}
        title="Research & reference files"
        description="Facts, proposals, and reference context for this draft."
        wide
      >
        {context}
      </Modal>
      <Modal
        open={!!suggestion}
        onClose={() => setSuggestion(null)}
        title="A starting point for your message"
        description="Generated from fixed sample content. Review it before replacing your editor text."
        wide
      >
        {suggestion && (
          <>
            <div className="suggestion-preview">
              <Badge tone="blue">Generated suggestion · demo</Badge>
              <h3>{suggestion.subject}</h3>
              <pre>{suggestion.body}</pre>
            </div>
            <div className="modal-actions">
              <Button onClick={() => setSuggestion(null)}>Keep my draft</Button>
              <Button
                variant="primary"
                onClick={() => {
                  setRecipient(suggestion.recipient);
                  setSubject(suggestion.subject);
                  setBody(suggestion.body);
                  setAttachments(suggestion.attachments);
                  setSuggestion(null);
                  notify("Suggestion added to the editor. Save it when ready.");
                }}
              >
                Use this draft
              </Button>
            </div>
          </>
        )}
      </Modal>
      <Modal
        open={history}
        onClose={() => setHistory(false)}
        title="Revision history"
        description="Saved versions are retained. Editing creates a new revision and clears old approval."
        wide
      >
        <div className="history-versions">
          {o.draft?.revisions.map((r) => (
            <button
              key={r.number}
              aria-pressed={historyRevision?.number === r.number}
              onClick={() => setHistoryRevision(r)}
            >
              Revision {r.number}
            </button>
          ))}
        </div>
        {historyRevision ? (
          <div className="document-preview">
            <span>{historyRevision.recipient}</span>
            <h3>{historyRevision.subject}</h3>
            <pre>{historyRevision.body}</pre>
          </div>
        ) : (
          <Empty title="No saved revisions yet">
            Save a draft to start its history.
          </Empty>
        )}
      </Modal>
      <ResourcePreview resource={preview} onClose={() => setPreview(null)} />
    </section>
  );
}
