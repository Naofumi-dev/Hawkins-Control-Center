export type Kind = "client" | "job";
export type Stage =
  | "research"
  | "review"
  | "ready"
  | "contacted"
  | "replied"
  | "needs_checking"
  | "closed"
  | "suppressed";
export type DraftKind = "outreach" | "cover" | "followup" | "reply";
export type Page =
  | "today"
  | "discover"
  | "pipeline"
  | "drafts"
  | "inbox"
  | "library"
  | "connections";
export type Evidence = {
  label: string;
  text: string;
  url: string;
  observedAt: string;
};
export type Revision = {
  number: number;
  recipient: string;
  subject: string;
  body: string;
  createdAt: string;
  attachments: string[];
};
export type Draft = {
  kind: DraftKind;
  revisions: Revision[];
  approvedRevision?: number;
  approvedVia?: "web" | "telegram";
  status: "draft" | "approved" | "sent" | "applied";
};
export type Message = {
  id: string;
  direction: "in" | "out" | "system";
  text: string;
  at: string;
  label?: string;
};
export type Opportunity = {
  id: string;
  kind: Kind;
  company: string;
  title: string;
  initials: string;
  color: string;
  location: string;
  source: string;
  contact: string;
  role: string;
  email: string;
  website: string;
  fit: "Strong fit" | "Good fit" | "Needs research";
  stage: Stage;
  evidence: Evidence[];
  proposed: string;
  notes: string;
  sheetNotes: string;
  draft?: Draft;
  messages: Message[];
  inboxState?: "reply" | "bounce" | "optout" | "unknown" | "sent";
  resourceIds: string[];
  suppressed: boolean;
  bounced: boolean;
  followupCreated?: boolean;
  confirmedAt?: string;
};
export type Resource = {
  id: string;
  title: string;
  provider: "Drive" | "Notion";
  type: string;
  description: string;
  content: string;
  preview: boolean;
};
export type Connection = {
  id: string;
  name: string;
  purpose: string;
  status: "connected" | "attention" | "paused";
  lastSync: string;
  detail: string;
};
export type Activity = {
  id: string;
  title: string;
  detail: string;
  at: string;
  opportunityId?: string;
  page?: Page;
};
export type SendAttempt = {
  id: string;
  opportunityId: string;
  revision: number;
  payload: Revision;
  outcome: "confirmed" | "unknown" | "not_sent";
  at: string;
  providerId?: string;
};
export type EditorBuffer = {
  recipient: string;
  subject: string;
  body: string;
  attachments: string[];
  kind: DraftKind;
};
export type State = {
  version: 1;
  opportunities: Opportunity[];
  connections: Connection[];
  activities: Activity[];
  attempts: SendAttempt[];
  costs: { label: string; amount: number }[];
  discoveryPaused: boolean;
  buffers?: Record<string, EditorBuffer>;
};
export type Action =
  | { type: "add"; opportunity: Opportunity }
  | {
      type: "save";
      id: string;
      revision: Omit<Revision, "number" | "createdAt">;
      kind: DraftKind;
    }
  | { type: "approve"; id: string; revision: number; via: "web" | "telegram" }
  | { type: "send"; id: string; revision: number }
  | { type: "apply"; id: string }
  | { type: "stage"; id: string; stage: "closed" | "suppressed" }
  | { type: "note"; id: string; field: "notes" | "sheetNotes"; value: string }
  | { type: "attach"; id: string; resourceId: string }
  | {
      type: "connection";
      id: string;
      operation: "sync" | "reconnect" | "pause";
    }
  | { type: "resolve"; id: string; outcome: "confirmed" | "not_sent" }
  | { type: "pause" }
  | { type: "cost"; label: string; amount: number }
  | { type: "buffer"; key: string; value?: EditorBuffer }
  | { type: "reset" };
