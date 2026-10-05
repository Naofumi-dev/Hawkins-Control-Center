import type {
  Connection,
  Opportunity,
  Resource,
  Revision,
  State,
} from "./types";

export const resources: Resource[] = [
  {
    id: "resume",
    title: "Armageddon · résumé",
    provider: "Drive",
    type: "Profile",
    description: "Automation, applications, and workflow experience.",
    preview: false,
    content:
      "SAMPLE PROFILE\nArmageddon Vivas\nAutomation & application development\n\nFocus areas\n• Workflow design and API integrations\n• Internal tools and review dashboards\n• Client onboarding and lead routing\n\nThis is fictional demo content. Replace it with your verified résumé before using a real application.",
  },
  {
    id: "onboarding",
    title: "Client onboarding portal",
    provider: "Drive",
    type: "Portfolio",
    description: "A single place for intake, documents, and next steps.",
    preview: true,
    content:
      "PROTOTYPE / PREVIEW\nClient onboarding portal\n\nExample deliverable: an intake form, document checklist, and shared progress view.\n\nThe preview demonstrates a possible interface. It is not a deployed client project or evidence of measured results.",
  },
  {
    id: "lead-review",
    title: "Lead review workbench",
    provider: "Drive",
    type: "Portfolio",
    description: "Research, qualification, and review before outreach.",
    preview: true,
    content:
      "PROTOTYPE / PREVIEW\nLead review workbench\n\nExample flow: source → research → proposed deliverable → reviewed draft.\n\nDesigned to keep factual observations and proposed improvements separate. No conversion or revenue claims.",
  },
  {
    id: "reporting",
    title: "Campaign reporting view",
    provider: "Drive",
    type: "Portfolio",
    description: "A prototype for reviewing recurring client reports.",
    preview: true,
    content:
      "PROTOTYPE / PREVIEW\nCampaign reporting view\n\nA sample dashboard concept for reviewing campaign records and the next client reporting deadline.\n\nThis is a design reference, not a deployed client project or a claim of time savings.",
  },
  {
    id: "offers",
    title: "Services & deliverables",
    provider: "Notion",
    type: "Service notes",
    description: "Small, useful outcomes for agency operations.",
    preview: false,
    content:
      "SAMPLE SERVICE NOTES\n\n1. A client onboarding portal for intake and document collection.\n2. A reviewed lead handoff between forms and CRM.\n3. An operations dashboard for one clearly defined workflow.\n\nScope, access, pricing, and delivery dates need a real project discussion.",
  },
  {
    id: "letter",
    title: "Cover letter reference",
    provider: "Notion",
    type: "Template",
    description: "A short structure that starts with the actual role.",
    preview: false,
    content:
      "SAMPLE WRITING REFERENCE\n\nStart with one requirement from the role.\nConnect it to a relevant, verified capability.\nAdd a portfolio preview with its original label.\nClose with one simple next step.\n\nAvoid generic praise, invented metrics, and unsupported experience.",
  },
];

const ago = (hours: number) =>
  new Date(Date.now() - hours * 3600000).toISOString();
const observations = [
  "Their public project brief asks for a clearer client intake and document collection process.",
  "Their services page describes recurring campaign reporting across several client accounts.",
  "The agency is inviting proposals for a small lead handoff and CRM integration project.",
  "The team lists workflow automation among its current delivery needs.",
  "The published brief mentions reviewing incoming inquiries before assigning an owner.",
  "Their service page describes website projects with a multi-step client onboarding process.",
];

export function opportunity(
  index: number,
  kind: "client" | "job",
  company: string,
  title: string,
  stage: Opportunity["stage"],
  source: string,
): Opportunity {
  const slug = company.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const locations = [
    "Austin, TX",
    "Portland, OR",
    "Chicago, IL",
    "Denver, CO",
    "Brooklyn, NY",
    "Seattle, WA",
  ];
  return {
    id: `${kind}-${index}`,
    kind,
    company,
    title,
    initials: company
      .split(" ")
      .filter((s) => /^[a-z]/i.test(s))
      .map((s) => s[0])
      .slice(0, 2)
      .join(""),
    color: ["sage", "blue", "amber", "rose", "slate", "mint"][index % 6],
    location: locations[index % 6],
    source,
    contact:
      kind === "client"
        ? ["Morgan Ellis", "General business inbox", "Rowan Brooks"][index % 3]
        : "Hiring team",
    role:
      kind === "client"
        ? index % 3 === 1
          ? "Role not established"
          : "Operations lead"
        : "Published application contact",
    email: stage === "research" ? "" : `hello@${slug}.example`,
    website: `https://${slug}.example`,
    fit:
      stage === "research"
        ? "Needs research"
        : index % 3 === 0
          ? "Good fit"
          : "Strong fit",
    stage,
    evidence: [
      {
        label:
          kind === "client" ? "Published project brief" : "Role requirements",
        text:
          kind === "client"
            ? observations[index % 6]
            : `The ${title} listing requests experience with integrations, clear documentation, and human review of automated actions.`,
        url: `https://${slug}.example/${kind === "client" ? "brief" : "careers"}`,
        observedAt: ago(26),
      },
      {
        label: "Company & location",
        text: `${company} lists ${locations[index % 6]} as its US location.`,
        url: `https://${slug}.example/about`,
        observedAt: ago(26),
      },
      ...(stage === "research"
        ? []
        : [
            {
              label: "Published contact",
              text: `The public contact page lists hello@${slug}.example.`,
              url: `https://${slug}.example/contact`,
              observedAt: ago(25),
            },
          ]),
    ],
    proposed:
      kind === "client"
        ? [
            "A scoped intake portal with a document checklist and clear next steps.",
            "A reporting dashboard that brings one recurring review into a single view.",
            "A lead handoff workflow with a review step before CRM updates.",
            "A small operations workflow with explicit review points and handoff documentation.",
            "An inquiry review queue that assigns a clear owner before updating the CRM.",
            "A scoped intake portal with a document checklist and clear next steps.",
          ][index % 6]
        : "A short cover letter connecting the published role requirements to relevant project previews.",
    notes:
      "Review the published requirements before choosing a deliverable. Confirm scope in a conversation.",
    sheetNotes: "Owner: Armageddon\nNext step: review research",
    messages: [],
    resourceIds:
      kind === "client"
        ? [
            "offers",
            [
              "onboarding",
              "reporting",
              "lead-review",
              "lead-review",
              "lead-review",
              "onboarding",
            ][index % 6],
          ]
        : ["resume", "letter"],
    suppressed: stage === "suppressed",
    bounced: false,
  };
}

export function createRevision(o: Opportunity, body?: string): Revision {
  return {
    number: 1,
    recipient: o.email,
    subject:
      o.kind === "client"
        ? `A thought on ${o.company}'s client workflow`
        : `Application: ${o.title}`,
    createdAt: ago(2),
    attachments: [...o.resourceIds],
    body:
      body ??
      (o.kind === "client"
        ? `Hi ${o.contact === "General business inbox" ? "there" : o.contact.split(" ")[0]},\n\nI saw your published brief about ${o.title.toLowerCase()}. I could help with ${o.proposed.charAt(0).toLowerCase() + o.proposed.slice(1)}\n\nI've included a related portfolio preview as a starting point. It's a prototype, so it shows the approach rather than a finished client result.\n\nWould it be useful if I outlined a small first version?\n\nArmageddon Vivas\nSample commercial outreach · Fictional demo address\nReply “no thanks” to opt out. This demo never sends email.`
        : `Hi ${o.company} team,\n\nI'm interested in your ${o.title} role. Your focus on integrations and clear documentation matches the kind of work I want to contribute.\n\nI'd start by mapping the current workflow, identifying where human review belongs, and building a small version that can be tested against real examples. My attached résumé and prototype references provide context for that approach.\n\nI'd be glad to discuss the first workflow you want to improve.\n\nArmageddon Vivas\nFictional application draft for this demo.`),
  };
}

export const discoveryCandidates: Opportunity[] = [
  opportunity(
    20,
    "client",
    "Cedar & Finch",
    "Client intake redesign",
    "research",
    "Brave Search",
  ),
  opportunity(
    21,
    "client",
    "Fieldnote Digital",
    "Campaign reporting workflow",
    "review",
    "Agency websites",
  ),
  opportunity(
    20,
    "job",
    "Common Ground Studio",
    "Automation Specialist",
    "review",
    "OnlineJobs",
  ),
  opportunity(
    21,
    "job",
    "Loomfield Works",
    "Integration Developer",
    "review",
    "Company careers",
  ),
];
// Discovery preview can illustrate complete published contact evidence.
discoveryCandidates[0].email = "hello@cedar-finch.example";
discoveryCandidates[0].fit = "Strong fit";
discoveryCandidates[0].evidence[0].text =
  "The published project brief asks for a client intake portal with a document checklist and clear next steps.";
discoveryCandidates[0].proposed =
  "A scoped intake portal with a document checklist and clear next steps.";
discoveryCandidates[0].resourceIds = ["offers", "onboarding"];
discoveryCandidates[1].evidence[0].text =
  "The agency is inviting proposals for a dashboard to review recurring client campaign reports.";
discoveryCandidates[1].proposed =
  "A reporting dashboard that brings one recurring review into a single view.";
discoveryCandidates[1].resourceIds = ["offers", "reporting"];
discoveryCandidates[0].evidence.push({
  label: "Published contact",
  text: "The brief lists hello@cedar-finch.example for project inquiries.",
  url: "https://cedar-finch.example/brief",
  observedAt: ago(2),
});

export function seed(): State {
  const opportunities = [
    opportunity(
      0,
      "client",
      "Northline Studio",
      "Client onboarding",
      "review",
      "Brave Search",
    ),
    opportunity(
      1,
      "client",
      "Morrow Creative",
      "Campaign reporting",
      "review",
      "Agency websites",
    ),
    opportunity(
      2,
      "client",
      "Goodform Digital",
      "Lead handoff workflow",
      "research",
      "Source registry",
    ),
    opportunity(
      3,
      "client",
      "Parallel House",
      "Operations workflow",
      "replied",
      "Brave Search",
    ),
    opportunity(
      4,
      "client",
      "Sunday Bureau",
      "Inquiry review process",
      "needs_checking",
      "Agency websites",
    ),
    opportunity(
      5,
      "client",
      "Oak & Current",
      "Client intake",
      "suppressed",
      "Source registry",
    ),
    opportunity(
      0,
      "job",
      "Forma Collective",
      "Automation Specialist",
      "review",
      "OnlineJobs",
    ),
    opportunity(
      1,
      "job",
      "Daybreak Labs",
      "Internal Tools Developer",
      "review",
      "Company careers",
    ),
    opportunity(
      2,
      "job",
      "Plainview Partners",
      "Operations Automation Lead",
      "research",
      "OnlineJobs",
    ),
    opportunity(
      3,
      "job",
      "Westward Works",
      "Integration Developer",
      "replied",
      "Company careers",
    ),
    opportunity(
      4,
      "job",
      "Kindred Office",
      "Workflow Builder",
      "ready",
      "OnlineJobs",
    ),
    opportunity(
      5,
      "job",
      "Fernway Studio",
      "Systems Assistant",
      "suppressed",
      "Company careers",
    ),
  ];
  opportunities.forEach((o) => {
    if (o.stage !== "research")
      o.draft = {
        kind: o.kind === "client" ? "outreach" : "cover",
        revisions: [createRevision(o)],
        status: "draft",
      };
  });
  const get = (id: string) => opportunities.find((o) => o.id === id)!;
  get("client-3").messages = [
    {
      id: "m-1",
      direction: "out",
      text: createRevision(get("client-3")).body,
      at: ago(6),
      label: "Sample initial outreach",
    },
    {
      id: "m-2",
      direction: "in",
      text: "Hi Armageddon, thanks for reaching out. We are reviewing the intake process this month. Could you share what a first version might include?",
      at: ago(1),
      label: "Morgan · Parallel House",
    },
  ];
  get("client-3").inboxState = "reply";
  get("client-3").draft!.status = "sent";
  get("client-3").confirmedAt = ago(6);
  get("client-4").messages = [
    {
      id: "m-3",
      direction: "system",
      text: "The send request timed out. Check the simulated Sent folder before resolving this attempt. Retrying is blocked.",
      at: ago(3),
    },
  ];
  get("client-4").inboxState = "unknown";
  get("client-5").messages = [
    {
      id: "m-4",
      direction: "in",
      text: "Thanks, but please remove us from future outreach.",
      at: ago(4),
    },
  ];
  get("client-5").inboxState = "optout";
  get("job-3").messages = [
    {
      id: "m-5",
      direction: "in",
      text: "Thanks for your application. Could you tell us how you would document an integration handoff for a small team?",
      at: ago(2),
      label: "Hiring team · Westward Works",
    },
  ];
  get("job-3").inboxState = "reply";
  get("job-3").draft!.status = "applied";
  get("job-4").draft!.approvedRevision = 1;
  get("job-4").draft!.approvedVia = "telegram";
  get("job-4").draft!.status = "approved";
  get("job-5").messages = [
    {
      id: "m-6",
      direction: "system",
      text: "Delivery failed: the published mailbox no longer accepts messages. Pending outreach has been stopped.",
      at: ago(7),
    },
  ];
  get("job-5").inboxState = "bounce";
  get("job-5").bounced = true;
  const connections: Connection[] = [
    {
      id: "gmail",
      name: "Gmail",
      purpose: "Outreach & conversations",
      status: "connected",
      lastSync: ago(0.1),
      detail: "Sample mailbox · armageddon@hawkins.example",
    },
    {
      id: "sheets",
      name: "Google Sheets",
      purpose: "Opportunity records",
      status: "connected",
      lastSync: ago(0.3),
      detail: "Hawkins opportunities · sample workbook",
    },
    {
      id: "notion",
      name: "Notion",
      purpose: "Research & service notes",
      status: "attention",
      lastSync: ago(26),
      detail: "Sample authorization expired. Reconnect to resume demo sync.",
    },
    {
      id: "drive",
      name: "Google Drive",
      purpose: "Portfolio & reference files",
      status: "connected",
      lastSync: ago(0.5),
      detail: "Hawkins reference library · sample folder",
    },
    {
      id: "telegram",
      name: "Telegram",
      purpose: "Draft approvals & updates",
      status: "connected",
      lastSync: ago(0.05),
      detail: "Dedicated outreach bot · owner-only review preview",
    },
    {
      id: "n8n",
      name: "n8n",
      purpose: "Scheduled research",
      status: "connected",
      lastSync: ago(1),
      detail: "Daily discovery · 08:00 Asia/Manila · simulated",
    },
    {
      id: "brave",
      name: "Brave Search",
      purpose: "Public source discovery",
      status: "connected",
      lastSync: ago(1),
      detail: "Targeted public-page discovery · fixture results only",
    },
  ];
  return {
    version: 1,
    opportunities,
    connections,
    discoveryPaused: false,
    costs: [
      { label: "Sample discovery usage", amount: 4.8 },
      { label: "Sample drafting usage", amount: 1.62 },
    ],
    attempts: [
      {
        id: "attempt-1",
        opportunityId: "client-3",
        revision: 1,
        payload: createRevision(get("client-3")),
        outcome: "confirmed",
        at: ago(1),
        providerId: "demo_gmail_001",
      },
      {
        id: "attempt-2",
        opportunityId: "client-4",
        revision: 1,
        payload: createRevision(get("client-4")),
        outcome: "unknown",
        at: ago(1),
      },
    ],
    activities: [
      {
        id: "a1",
        title: "A reply from Parallel House",
        detail: "A conversation is ready for you.",
        at: ago(1),
        opportunityId: "client-3",
        page: "inbox",
      },
      {
        id: "a2",
        title: "Cover letter approved in Telegram",
        detail: "Kindred Office · revision 1",
        at: ago(2),
        opportunityId: "job-4",
        page: "drafts",
      },
      {
        id: "a3",
        title: "Daily research completed",
        detail: "Client and application research updated.",
        at: ago(3),
        page: "discover",
      },
    ],
  };
}
