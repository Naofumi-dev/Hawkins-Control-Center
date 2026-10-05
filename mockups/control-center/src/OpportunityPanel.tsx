import { useEffect, useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import {
  ArrowLeft,
  ArrowUpRight,
  NotePencil,
  Globe,
  MapPin,
  LinkSimple,
  FileText,
  Prohibit,
  X,
  Clock,
} from "@phosphor-icons/react";
import { useDemo } from "./store";
import { resources } from "./fixtures";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  Modal,
  RelativeTime,
  ResourcePreview,
  Status,
  ToolIcon,
} from "./ui";
import { ReviewContent } from "./Review";
import type { Evidence, Opportunity, Resource } from "./types";

export function EvidenceList({ o }: { o: Opportunity }) {
  const [source, setSource] = useState<Evidence | null>(null);
  return (
    <>
      <div className="subsection-label">
        OBSERVED FACTS <Badge>Sample evidence</Badge>
      </div>
      <div className="evidence-list">
        {o.evidence.map((e) => (
          <div className="evidence-item" key={e.label}>
            <div className="evidence-heading">
              <span className="evidence-check" />
              <strong>{e.label}</strong>
            </div>
            <p>{e.text}</p>
            <button className="source-link" onClick={() => setSource(e)}>
              <LinkSimple size={13} />
              {e.url.replace("https://", "")}
              <ArrowUpRight size={12} />
            </button>
            <small>
              Observed <RelativeTime value={e.observedAt} />
            </small>
          </div>
        ))}
      </div>
      <div className="proposed-box">
        <span className="subsection-label">PROPOSED IMPROVEMENT</span>
        <p>{o.proposed}</p>
        <small>A suggestion to discuss, not a verified business problem.</small>
      </div>
      <Modal
        open={!!source}
        onClose={() => setSource(null)}
        title={source?.label ?? "Source"}
        description="Fictional source preview. This is not a live website."
      >
        <div className="document-preview">
          <span className="source-url">{source?.url}</span>
          <p>{source?.text}</p>
          <Badge>Sample observation</Badge>
        </div>
      </Modal>
    </>
  );
}

export function OpportunityPanel({
  o,
  onClose,
}: {
  o: Opportunity;
  onClose: () => void;
}) {
  const { navigate, dispatch, notify, state } = useDemo();
  const [tab, setTab] = useState("research"),
    [notes, setNotes] = useState(o.notes),
    [sheet, setSheet] = useState(o.sheetNotes);
  const [preview, setPreview] = useState<Resource | null>(null),
    [confirm, setConfirm] = useState<"closed" | "suppressed" | null>(null);
  useEffect(() => {
    setTab("research");
    setNotes(o.notes);
    setSheet(o.sheetNotes);
  }, [o.id]);
  const tabs = [
    { id: "research", label: "Research" },
    { id: "gmail", label: "Gmail" },
    { id: "sheets", label: "Sheet" },
    { id: "notion", label: "Notion" },
    { id: "drive", label: "Files" },
    { id: "telegram", label: "Telegram" },
  ];
  return (
    <section className="opportunity-panel" aria-label={`${o.company} details`}>
      <div className="detail-top">
        <button className="text-link" onClick={onClose}>
          <ArrowLeft size={15} /> Back to pipeline
        </button>
        <Badge>
          {o.kind === "client" ? "Client opportunity" : "Job application"}
        </Badge>
      </div>
      <div className="detail-heading">
        <Avatar o={o} />
        <div>
          <h2>{o.company}</h2>
          <p>{o.title}</p>
        </div>
        <button
          className="plain icon-button"
          onClick={onClose}
          aria-label="Close opportunity details"
        >
          <X size={18} />
        </button>
      </div>
      <div className="detail-meta">
        <span>
          <MapPin size={14} />
          {o.location}
        </span>
        <span>
          <Globe size={14} />
          {o.source}
        </span>
      </div>
      <div className="detail-status">
        <Status o={o} />
        <Badge tone={o.fit === "Needs research" ? "amber" : "green"}>
          {o.fit}
        </Badge>
      </div>
      <div className="detail-primary">
        <Button variant="primary" onClick={() => navigate("drafts", o.id)}>
          <NotePencil size={16} />
          {o.draft ? "Open draft" : "Write a draft"}
        </Button>
        <Button
          onClick={() => setConfirm("closed")}
          disabled={o.suppressed || o.stage === "closed"}
        >
          Skip
        </Button>
        <Button
          variant="ghost"
          className="icon-button"
          aria-label={`Do not contact ${o.company}`}
          onClick={() => setConfirm("suppressed")}
          disabled={o.suppressed}
        >
          <Prohibit size={18} />
        </Button>
      </div>
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="detail-tabs" aria-label="Opportunity tools">
          {tabs.map((t) => (
            <Tabs.Trigger key={t.id} value={t.id}>
              {t.label}
            </Tabs.Trigger>
          ))}
        </Tabs.List>
        <Tabs.Content value="research" className="detail-tab-content">
          <EvidenceList o={o} />
          <div className="contact-block">
            <span className="subsection-label">CONTACT</span>
            <strong>{o.contact}</strong>
            <span>{o.role}</span>
            <span>{o.email || "Published business email not found"}</span>
            {!o.email && (
              <Badge tone="amber">Research needed before approval</Badge>
            )}
          </div>
        </Tabs.Content>
        <Tabs.Content value="gmail" className="detail-tab-content">
          <div className="integration-heading">
            <ToolIcon id="gmail" />
            <div>
              <strong>Linked conversation</strong>
              <span>{o.email || "No contact yet"}</span>
            </div>
          </div>
          {o.messages.length ? (
            <>
              {o.messages.map((m) => (
                <div key={m.id} className="compact-message">
                  <Badge>
                    {m.direction === "in"
                      ? "Received"
                      : m.direction === "out"
                        ? "Sent · demo"
                        : "System"}
                  </Badge>
                  <p>{m.text}</p>
                  <RelativeTime value={m.at} />
                </div>
              ))}
              <Button onClick={() => navigate("inbox", o.id)}>
                Open in Inbox <ArrowUpRight size={15} />
              </Button>
            </>
          ) : (
            <Empty title="No conversation yet">
              Your reviewed outreach will appear here after a simulated send.
            </Empty>
          )}
        </Tabs.Content>
        <Tabs.Content value="sheets" className="detail-tab-content">
          <div className="integration-heading">
            <ToolIcon id="sheets" />
            <div>
              <strong>Hawkins opportunities</strong>
              <span>Linked sample row · {o.id}</span>
            </div>
          </div>
          <dl className="record-fields">
            <div>
              <dt>Company</dt>
              <dd>{o.company}</dd>
            </div>
            <div>
              <dt>Role / project</dt>
              <dd>{o.title}</dd>
            </div>
            <div>
              <dt>Contact</dt>
              <dd>{o.email || "Needs research"}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <Status o={o} />
              </dd>
            </div>
          </dl>
          <label className="field-label">
            Record notes
            <textarea
              value={sheet}
              onChange={(e) => setSheet(e.target.value)}
              rows={5}
            />
          </label>
          <Button
            onClick={() => {
              dispatch({
                type: "note",
                id: o.id,
                field: "sheetNotes",
                value: sheet,
              });
              notify("Sample sheet record saved locally.");
            }}
          >
            Save sample row
          </Button>
        </Tabs.Content>
        <Tabs.Content value="notion" className="detail-tab-content">
          <div className="integration-heading">
            <ToolIcon id="notion" />
            <div>
              <strong>Opportunity notes</strong>
              <span>Local copy of a sample Notion page</span>
            </div>
          </div>
          {state.connections.find((c) => c.id === "notion")?.status !==
            "connected" && (
            <div className="inline-alert warning">
              Notion needs attention. Local edits remain available.
            </div>
          )}
          <label className="field-label">
            Research notes
            <textarea
              rows={10}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </label>
          <Button
            onClick={() => {
              dispatch({
                type: "note",
                id: o.id,
                field: "notes",
                value: notes,
              });
              notify("Notion note saved locally.");
            }}
          >
            Save note
          </Button>
        </Tabs.Content>
        <Tabs.Content value="drive" className="detail-tab-content">
          <div className="integration-heading">
            <ToolIcon id="drive" />
            <div>
              <strong>Linked references</strong>
              <span>Sample files attached to this opportunity</span>
            </div>
          </div>
          {o.resourceIds.map((id) => {
            const r = resources.find((r) => r.id === id);
            return (
              r && (
                <button
                  className="resource-row"
                  key={id}
                  onClick={() => setPreview(r)}
                >
                  <FileText size={21} />
                  <span>
                    <strong>{r.title}</strong>
                    <small>
                      {r.provider} ·{" "}
                      {r.preview ? "Prototype / preview" : r.type}
                    </small>
                  </span>
                  <ArrowUpRight size={16} />
                </button>
              )
            );
          })}
          <Button onClick={() => navigate("library", o.id)}>
            Browse library
          </Button>
        </Tabs.Content>
        <Tabs.Content value="telegram" className="detail-tab-content">
          <ReviewContent o={o} via="telegram" />
        </Tabs.Content>
      </Tabs.Root>
      <div className="detail-activity">
        <span className="subsection-label">RECENT ACTIVITY</span>
        {state.activities
          .filter((a) => a.opportunityId === o.id)
          .slice(0, 3)
          .map((a) => (
            <div key={a.id}>
              <Clock size={14} />
              <span>{a.title}</span>
              <RelativeTime value={a.at} />
            </div>
          ))}
        {!state.activities.some((a) => a.opportunityId === o.id) && (
          <p>Research added to the sample workspace.</p>
        )}
      </div>
      <ResourcePreview resource={preview} onClose={() => setPreview(null)} />
      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={
          confirm === "suppressed"
            ? `Stop outreach to ${o.company}?`
            : `Skip ${o.company}?`
        }
        description={
          confirm === "suppressed"
            ? "This cancels pending approvals and blocks further demo outreach for this contact."
            : "This removes the opportunity from the daily queue and invalidates its approval."
        }
      >
        <div className="modal-actions">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => {
              if (confirm) {
                dispatch({ type: "stage", id: o.id, stage: confirm });
                notify(
                  confirm === "suppressed"
                    ? "Contact suppressed. Pending approval canceled."
                    : "Opportunity skipped.",
                );
                setConfirm(null);
              }
            }}
          >
            {confirm === "suppressed" ? "Do not contact" : "Skip opportunity"}
          </Button>
        </div>
      </Modal>
    </section>
  );
}
