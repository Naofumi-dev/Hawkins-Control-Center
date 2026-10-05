import {
  CheckCircle,
  PaperPlaneTilt,
  ShieldCheck,
} from "@phosphor-icons/react";
import { currentRevision, draftBlock } from "./model";
import { useDemo } from "./store";
import { Badge, Button, Modal } from "./ui";
import { resources } from "./fixtures";
import type { Opportunity } from "./types";

export function ReviewContent({
  o,
  via,
  onApproved,
}: {
  o: Opportunity;
  via: "web" | "telegram";
  onApproved?: () => void;
}) {
  const { dispatch, notify } = useDemo();
  const r = currentRevision(o);
  if (!r)
    return (
      <p className="quiet">
        Write and save a draft before creating a review card.
      </p>
    );
  const approved = o.draft?.approvedRevision === r.number;
  const blocked = draftBlock(o);
  return (
    <div
      className={`review-content ${via === "telegram" ? "telegram-review" : ""}`}
    >
      <div className="review-meta">
        <Badge tone="blue">
          {o.draft?.kind === "cover" ? "Cover letter draft" : "Email draft"}
        </Badge>
        <span>Revision {r.number}</span>
        <Badge tone={approved ? "green" : "amber"}>
          {approved ? "Approved" : "Awaiting your approval"}
        </Badge>
      </div>
      {via === "telegram" && (
        <div className="telegram-bot">
          <PaperPlaneTilt size={20} />
          <div>
            <strong>Hawkins Outreach</strong>
            <span>Owner-only Telegram card · preview</span>
          </div>
        </div>
      )}
      <div className="review-evidence">
        <strong>{o.company}</strong>
        <span>{o.website}</span>
        <p>
          <b>Why it fits:</b> {o.evidence[0]?.text}
        </p>
        <p>
          <b>Proposed:</b> {o.proposed}
        </p>
        <p>
          <b>Contact:</b> {o.contact} · {o.role}
        </p>
        <p>
          <b>Evidence:</b> {o.evidence[0]?.url}
        </p>
        <p>
          <b>Contact source:</b>{" "}
          {o.evidence.find((e) => e.label === "Published contact")?.url ??
            "Missing"}
        </p>
        <p>
          <b>References:</b>{" "}
          {r.attachments
            .map((id) => {
              const f = resources.find((x) => x.id === id);
              return f
                ? `${f.title}${f.preview ? " (prototype / preview)" : " (sample)"}`
                : id;
            })
            .join(", ") || "None attached"}
        </p>
      </div>
      <div className="exact-message">
        <div>
          <span>To</span>
          <strong>{r.recipient || "Contact missing"}</strong>
        </div>
        <div>
          <span>Subject</span>
          <strong>{r.subject}</strong>
        </div>
        <pre>{r.body}</pre>
      </div>
      {blocked && (
        <div className="inline-alert warning" role="status">
          {blocked}
        </div>
      )}
      {approved && (
        <div className="approval-receipt">
          <CheckCircle size={18} />
          <span>
            Revision {r.number} approved in{" "}
            {o.draft?.approvedVia === "telegram"
              ? "Telegram"
              : "Control Center"}
            . Both views are up to date.
          </span>
        </div>
      )}
      <div className="review-actions">
        <span>
          <ShieldCheck size={15} /> Exact revision only · demo
        </span>
        <Button
          variant="primary"
          disabled={
            !!blocked ||
            approved ||
            ["sent", "applied"].includes(o.draft!.status)
          }
          onClick={() => {
            dispatch({ type: "approve", id: o.id, revision: r.number, via });
            notify(
              `Revision ${r.number} approved in ${via === "web" ? "Control Center" : "Telegram"}.`,
            );
            onApproved?.();
          }}
        >
          <CheckCircle size={17} />
          {approved ? "Revision approved" : `Approve revision ${r.number}`}
        </Button>
      </div>
    </div>
  );
}
export function ReviewDialog({
  o,
  via,
  open,
  onClose,
}: {
  o: Opportunity;
  via: "web" | "telegram";
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        via === "telegram"
          ? "Telegram review preview"
          : "Review your exact message"
      }
      description="Fictional demo. Approval applies only to the revision displayed here."
      wide
    >
      <ReviewContent o={o} via={via} />
    </Modal>
  );
}
