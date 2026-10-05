export type Category =
  | "onlinejobs_conversation"
  | "direct_client"
  | "job_alert"
  | "other"
  | "needs_review";
export type Stage =
  | "new"
  | "qualified"
  | "loom_call"
  | "proposal_offer"
  | "won"
  | "lost"
  | "onboarding";
export type Conversation = {
  id: string;
  opportunity_id: string | null;
  subject: string;
  category: Category;
  acquisition_source: string;
  reply_email: string | null;
  reply_verified: boolean;
  context_version: number;
  latest_inbound_id: string | null;
  last_message_at: string | null;
  classification_locked: boolean;
  classification_reason: string;
  needs_platform_import: boolean;
  suppressed: boolean;
  bounced: boolean;
  gmail_thread_id: string | null;
  platform_reference: string | null;
};
export type Message = {
  id: string;
  channel: string;
  direction: "in" | "out";
  sender: string;
  subject: string;
  body: string;
  occurred_at: string;
  deleted_at: string | null;
  classification: { intent: string; reason: string; evidence_excerpt?: string };
  reply_verified: boolean;
};
export type AgentResult = {
  summary: string;
  evidence: string[];
  missing: string[];
  draft_body: string;
  suggested_category: string;
  screening_answers?: { question: string; answer: string }[];
  source_resources?: { id: string; version: string }[];
};
export type Task = {
  id: string;
  conversation_id: string | null;
  opportunity_id: string | null;
  originating_message_id: string | null;
  agent: string;
  task_type: string;
  title: string;
  status: string;
  blocker: string | null;
  result: AgentResult | null;
  context_version: number;
  created_at: string;
  due_at: string;
};
export type Draft = {
  id: string;
  conversation_id: string;
  inbound_message_id: string;
  revision: number;
  context_version: number;
  recipient_email: string;
  subject: string;
  body: string;
  status: string;
  proof_id: string | null;
  approved_revision: number | null;
  approved_via: string | null;
  gmail_message_id: string | null;
};
export type Opportunity = {
  id: string;
  title: string;
  kind: "job" | "client";
  acquisition_source: string;
  stage: Stage;
  stage_note: string | null;
  won_confirmed_at: string | null;
};
export type Proof = {
  id: string;
  title: string;
  proof_url: string;
  proof_kind: string;
  claim_text: string;
};
export type Workspace = {
  owner_email: string;
  conversations: Conversation[];
  tasks: Task[];
  opportunities: Opportunity[];
  drafts: Draft[];
  proofs: Proof[];
  runs: {
    id: string;
    agent: string;
    status: string;
    started_at: string;
    error_code: string | null;
  }[];
  mailbox: {
    email: string;
    history_id: string | null;
    last_success_at: string | null;
    last_attempt_at: string | null;
    error_code: string | null;
    replies_enabled: boolean;
    reply_limit: number;
    fetched_count: number;
  } | null;
  settings: {
    daily_send_limit: number;
    monthly_cost_cap_cents: number;
    sending_enabled: boolean;
    sending_pause_reason: string | null;
  } | null;
  sender_footer?: string;
  page_limit: number;
  next_before: { time: string; id: string } | null;
  statistics?: {
    stored_messages: number;
    pending_tasks: number;
    blocked_tasks: number;
    scheduled_tasks: number;
  };
};
export const categoryLabels: Record<Category, string> = {
  onlinejobs_conversation: "OnlineJobs conversation",
  direct_client: "Direct client",
  job_alert: "Job alert",
  other: "Other",
  needs_review: "Needs review",
};
export const stageLabels: Record<Stage, string> = {
  new: "New",
  qualified: "Qualified",
  loom_call: "Loom / call",
  proposal_offer: "Proposal / offer",
  won: "Won",
  lost: "Lost",
  onboarding: "Onboarding",
};
