export const fixtureOwner = "armageddonvivas@gmail.com";
const at = "2026-10-05T03:12:00Z";
export const leadFixtures = [
  {
    id: "11111111-1111-4111-8111-111111111111",
    company_name: "Cedar Studio · test fixture",
    company_domain: "cedar.example",
    company_url: "https://cedar.example",
    location: "Portland, United States",
    niche: "Design agency",
    db_source: "Manual research",
    contact_name: "Test Contact",
    contact_title: "Founder",
    contact_email: "contact@cedar.example",
    status: "new",
    first_sent_at: null,
    replied_at: null,
  },
  {
    id: "22222222-2222-4222-8222-222222222222",
    company_name: "Harbor Agency · test fixture",
    company_domain: "harbor.example",
    company_url: "javascript:alert(1)",
    location: "Austin, United States",
    niche: "Marketing agency",
    db_source: "Public website",
    contact_name: null,
    contact_title: null,
    contact_email: "contact@harbor.example",
    status: "unsubscribed",
    first_sent_at: at,
    replied_at: null,
  },
  {
    id: "33333333-3333-4333-8333-333333333333",
    company_name: "Fieldwork Team · test fixture",
    company_domain: "fieldwork.example",
    company_url: null,
    location: "United States",
    niche: "Web agency",
    db_source: "Manual research",
    contact_name: null,
    contact_title: null,
    contact_email: null,
    status: "new",
    first_sent_at: null,
    replied_at: null,
  },
];
export const overviewFixture = {
  leads: 3,
  contacted: 1,
  replied: 0,
  proofs: 2,
  deliverables: 1,
};
export const catalogFixture = {
  proofs: [
    {
      id: "intake",
      title: "Intake recovery demo · test fixture",
      proof_url: "https://portfolio.example/intake",
      proof_kind: "prototype",
      claim_text:
        "A fictional preview of an intake queue. No live client results claimed.",
      active: true,
      verified_at: at,
    },
    {
      id: "loom",
      title: "Loom walkthrough · test fixture",
      proof_url: "javascript:alert(1)",
      proof_kind: "prototype",
      claim_text: "Missing reviewed proof. This item cannot support a draft.",
      active: false,
      verified_at: null,
    },
  ],
  deliverables: [
    {
      id: "intake",
      title: "Lead intake and follow-up",
      scope_text: "A bounded intake workflow with an owner review queue.",
      active: true,
    },
  ],
  sources: [
    {
      name: "Job board · test fixture",
      url: "https://jobs.example",
      category: "platforms",
      access_method: "manual_review",
      enabled: false,
    },
  ],
  source_rows: 1,
  catalog_limit: 1000,
};
export const emptyWorkspaceFixture = {
  owner_email: fixtureOwner,
  conversations: [],
  tasks: [],
  opportunities: [],
  drafts: [],
  proofs: [],
  runs: [],
  mailbox: null,
  settings: {
    daily_send_limit: 5,
    monthly_cost_cap_cents: 2500,
    sending_enabled: false,
  },
  page_limit: 200,
  next_before: null,
  statistics: {
    stored_messages: 0,
    pending_tasks: 0,
    blocked_tasks: 0,
    scheduled_tasks: 0,
  },
};
export function catalogResponse(url) {
  if (url.pathname === "/api/overview") return overviewFixture;
  if (url.pathname === "/api/library") return catalogFixture;
  if (url.pathname === "/api/leads") {
    const q = (url.searchParams.get("search") || "").toLowerCase();
    const history = url.searchParams.get("history") || "all";
    const filtered = leadFixtures.filter(
      (l) =>
        JSON.stringify(l).toLowerCase().includes(q) &&
        (history === "all" ||
          (history === "contacted" && l.first_sent_at) ||
          (history === "uncontacted" && !l.first_sent_at) ||
          (history === "replied" && l.replied_at)),
    );
    const remaining = filtered.filter(
      (l) => l.id > (url.searchParams.get("after_id") || ""),
    );
    const leads = remaining.slice(0, 2);
    return {
      leads,
      total: filtered.length,
      next_after: remaining.length > 2 ? leads.at(-1).id : null,
    };
  }
  if (url.pathname.startsWith("/api/leads/")) {
    const lead = leadFixtures.find(
      (l) => l.id === url.pathname.split("/").at(-1),
    );
    if (!lead) throw new Error("Unknown fixture lead");
    return {
      lead: {
        ...lead,
        research_summary:
          "A fixture summary. <script>alert('untrusted')</script>",
        verification_result: "MX record only; mailbox receipt unverified",
      },
      suppressions:
        lead.status === "unsubscribed"
          ? [{ scope: "domain", reason: "Owner request" }]
          : [],
      evidence: [],
      drafts: [],
      conversations: [],
    };
  }
  return undefined;
}
