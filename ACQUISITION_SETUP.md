# Personal Hawkins acquisition setup

This guide covers the approved client and job acquisition expansion. All files are in Client Scraping. Gmail is fixed to `armageddonvivas@gmail.com`; Supabase is fixed to `mtdavgadkiiofwikzdtn`. HOCH accounts and projects are excluded. The personal n8n account may use its separately confirmed login email.

## Open and upgrade

**Current workspace:** migrations 006–008 have been applied and verified in the personal project. Start the server below; do not rerun the upgrade. The upgrade command is retained for a future fresh installation on the same verified inbox foundation.

Run from your own Terminal:

```sh
cd "/Users/armageddonvivas/Downloads/Client Scraping"
python3 -m client_finder serve
```

For a fresh installation that has the inbox foundation but has never installed 006–008, run `python3 -m client_finder acquisition-setup --apply` first. It privately asks for the database password, makes a full logical backup outside this workspace, checks the archive, and installs the three migrations together with permissions/history checks before commit. It refuses a repeat install and never enables sending. A lost connection at commit requires read-only inspection, not an automatic retry. Keep the backup manifest; archive decoding is not a tested restore.

Open [Personal Hawkins](http://127.0.0.1:8088). Sign in with the personal **Auth password**. The server must remain running for local access. Hosted operation is a separate setup step.

| Screen | Added behavior |
| --- | --- |
| Today | Evidence-backed task recommendations, blockers, application count and shared budget |
| Discover | Existing client leads plus researched/manual jobs; job intake preserves posting URL |
| Pipeline | Separate client and application stages; explicit accepted-offer confirmation |
| Draft Studio | Existing replies, researched outreach, cover letters and screening answers |
| Inbox | Existing 30-day Gmail import, checkpoints, OnlineJobs origin and corrections |
| Library | Reviewed profile facts, resume versions, proof/Loom and proposal links |
| Connections | Original n8n links, actual checks, selected resources, import preview, calls, CRM conflicts and durable work queue |

## Personal credentials and selected resources

Local private entry uses `python3 -m client_finder configure-integration --provider google` (replace `google` with the provider below). Inputs are hidden and saved in an owner-only file under `~/.config/hawkins-personal`, never in this repository. Restart the backend afterward. Hosted setup uses `/etc/hawkins-client-finder/.env`, mode 600; Mac configuration is not deployed automatically.

| Provider | Private setup and selection |
| --- | --- |
| Google | OAuth client/secret and refresh token. Personal Gmail profile is verified before persistence and every read/send. Request only needed Gmail, Drive metadata, Sheets readonly and Calendar readonly scopes. Select exact file, spreadsheet and calendar IDs. Gmail readonly supports intake; sending additionally requires gmail.send. |
| n8n | API key plus `HAWKINS_N8N_OWNER_EMAIL`, the personal login email confirmed by the owner. Select the personal project IDs. All eight audited workflows belong to `OR8nv0dBAKXF38uZ`; the proposal workflow is in a folder within that project. Workflow ownership must match a selected personal project before execution metadata is read. No workflow is activated by verification. |
| Telegram | Dedicated Client Finder token and expected bot ID; existing backend owner user/private chat must match. Keep the older jobs bot separate. Connections shows the verified bot identity. |
| Notion | Integration token, selected bot ID and data-source IDs. The bot owner must be the personal owner. Workspace-owned integrations that cannot establish this identity remain blocked for review. |
| Cal.com | Personal token and selected event-type IDs. Owner identity and booking hosts are checked. |
| Fathom | Personal API key and selected recording IDs. The adapter filters by the personal recorder, stores selected summaries/action items, and omits transcripts. |
| GHL | Location token, one personal location and pipeline, explicit stage map, and reviewed notes establishing that stage writes cannot trigger unapproved messages. Location ownership and pipeline are rechecked before each write. |
| OnlineJobs | A private isolated hosted browser session, reviewed account URL/email selector and platform application-confirmation selector. No legacy browser profile is loaded automatically. |
| OpenRouter / Brave | Personal provider keys and verified access/pricing. Paid backend operations reserve cost against the shared $25/month ledger before each attempt. |
| Loom | Reviewed share URL, proof notes and truthful prototype/project label. No general library synchronization. |

Provider APIs and their account/resource checks have synthetic coverage. A saved token or successful identity check does not prove live downstream operation. A failed page or cursor stops checkpoint advancement; imported records are deduplicated when retried.

## History import and cutover

In Connections, select an owned Sheet or Notion data source, read it into a **persisted preview**, then inspect and commit that exact preview. For larger or differently shaped trackers, use reviewed JSON export batches of at most 100 records. The Sheets adapter reads `Leads!A1:AZ102` and refuses a source exceeding the batch limit; Notion likewise refuses incomplete multi-page previews. It never silently imports the first 100 and discards the rest.

Example shape (synthetic):

```json
{
  "external_id": "tracker-row-17",
  "kind": "job",
  "source_url": "https://www.onlinejobs.ph/jobseekers/job/12345",
  "title": "Systems assistant",
  "company": "Example agency",
  "description": "Original posting text",
  "questions": ["Relevant experience?"],
  "status": "applied",
  "applied_at": "2026-01-01T09:00:00+08:00",
  "sent_body": "Only put the actual recorded submitted text here",
  "draft_body": "Keep historical unsubmitted text separate"
}
```

Client rows use `kind: "client"`, `external_id`, `title`, and an exact existing `lead_id` where established. `suppressed_email` preserves do-not-contact history. A name alone never merges leads. A source is not verified merely because an import says it is. Old approvals are discarded. Changed source records are conflicts; duplicate commits are idempotent. A matching job from another tracker retains current content and outcomes; historical submissions stop repeat applications. Keep original trackers as archives after cutover.

Before cutover, inventory the old Sheets statuses, jobs API queue, Telegram consumer and any Mac/hosted application worker. Reconcile pending or uncertain submissions using platform evidence. Export affected hosted workflows privately. Pause competing submission/review consumers and the legacy paid scoring path before routing their jobs to the reserved-cost backend. Do not clear the legacy-queue gate based solely on an import count.

Reuse the original Dustin workflow and its account/resource bindings. Local `09_dustin_intake_adapter.json` accepts its normalized jobs in batches of ten and sends them to the personal backend. Map actual column names during the hosted audit. Keep the original discovery, review and proposal workflow IDs; move paid qualification/drafting to guarded backend tasks before claiming the global cap is enforced. The local adapter is not connected or published by creating its JSON file.

## Hosted worker and outbound rollout

Deploy the existing `Dockerfile`/`compose.client-finder.yml` on the authorized personal host, behind the existing private n8n network. Public HTTPS should expose only the static app and owner `/api` routes using `deploy/control-center.nginx.conf`. Private service endpoints require the separate service token. Do not expose them through the public proxy.

Local exports 05/06 retain five-minute Gmail sync and bounded task processing. Export 08 handles one queued operation, an exact application review card, one approved application and one web-approved cold email per run. Export 02 routes both reply and application callbacks through the dedicated bot. All nine exports remain inactive locally. Validate credentials, error reporting, payload retention and ownership before importing changes into the existing workflows. A first node error must be investigated rather than interpreted as an idle queue.

Optional OnlineJobs browser image:

```sh
docker build -t hawkins-client-finder:local .
docker build -f Dockerfile.browser -t hawkins-client-finder:browser .
```

The optional image uses pinned `playwright==1.63.0` and Chromium. It is prepared but has not been built or deployed here. Replace the existing backend instance with this image; do not run a second submission consumer. Mount a separate persistent profile owned by its `finder` UID with mode 700, outside the build context. Establish the personal session privately. Review the real account/confirmation selectors and form navigation without submitting. Expired sessions, missing selectors, unsupported URLs, changed forms, or unavailable Apply Points block the attempt and require review; no CAPTCHA or access restriction is bypassed.

Before setting `applications_enabled`, establish and record `legacy_queue_reconciled_at` and `application_policy_verified_at` through the trusted backend administration path. Automatic OnlineJobs additionally requires `application_worker_verified_at` and a recent personal session check. Verify platform access and the one-point policy. Do not mark these prerequisites verified simply to make a disabled button clickable.

Approve a full stored revision in web or Telegram. Edits, selected resource changes, job context changes or newly linked correspondence invalidate approval. Automatic delivery repeats personal identity, resource and database checks immediately before submission. A timeout remains **Needs checking**; reconciliation reads the platform record and never resubmits. Manual handoff requires a separate begin action after approval; once begun, it also remains held until an owner records the submission receipt. Selected document links are included in the exact submitted body; binary file-upload controls require a manual handoff.

Web cold outreach uses the existing atomic cold-email controls and Gmail delivery, with a stored RFC Message-ID for uncertain-result reconciliation. The legacy Telegram workflow retains its own immediate delivery path. The new worker selects only web-approved cold attempts, so it cannot compete for Telegram-owned delivery. Limits are separate buckets: 5 outreach including cold follow-ups, 5 applications, 20 verified conversation replies. Unknown and canceled reservations consume that day's capacity.

Validate shared exact-revision web/Telegram review, then an **explicitly approved** controlled email, followed by an **explicitly approved complete** real application. Sending flags remain disabled until the required live checks pass. No implementation instruction is an approval of future prospect messages or applications.

## API and acceptance

Cover letters are an agent responsibility. After job intake, Eleven prepares the current qualification brief and Steve drafts from it and reviewed Library facts. The default style is 70–110 plain-English words, with a hard 130-word model-output limit: employer need, a concrete deliverable/result, one relevant verified example, and one easy next step. Tool names are included only where the job needs them. Screening answers are separate fields; unknown required facts block completion.

The job screen automatically loads only complete current Steve suggestions with unchanged reviewed source resources. It preserves owner edits during refresh. The saved revision and final approval remain distinct server actions. Old context, missing proof, missing model configuration and failed runs stay visible; manual writing is an optional fallback. Set up the personal OpenRouter key through the private Terminal helper, not a browser text field. No paid generation has been verified yet.

Owner routes under `/api/acquisition` provide snapshot, paginated jobs, job details/intake/stages, conversation linking, reviewed resources, import preview/fetch/commit, queue/retry, selected connection/pause, application save/approve/handoff/result/reconcile, outreach review/reconcile and CRM bind/resolve/reconcile. All sessions are checked against the fixed personal Supabase owner. Database/browser roles cannot invoke server approval authority directly.

Internal service routes add `/jobs/intake`, `/acquisition/run`, `/applications/cards`, `/applications/send`, `/applications/reconcile` and `/outreach/send`. They require the personal service token; agents cannot call them from model output. Business data, workflow observations, approvals, revisions, attempts and reservations live on the server. Queues use leases; interruptions are blocked or held for checking. GHL unknown writes are reconciled read-only before another owner decision.

Jeff's original OnlineJobs thread has been verified in the personal account and imported. Hawkins records OnlineJobs origin and **Prepare Loom email**, blocked on missing reviewed Loom proof. This is a real manual import, not automatic Gmail intake. Live acceptance still requires ten current, researched, unsent stored prospect cards; one researched job with an owner-reviewed cover letter; personal inbox arrival through reviewed draft; a selected call producing a proposal task; and an owner-confirmed agreement/offer producing Joyce's onboarding work. Interested replies cannot create a win. Delivery management and ongoing client support remain outside this release.

See [VERIFICATION.md](VERIFICATION.md) for synthetic checks versus live observations. Provider references: [Gmail sync](https://developers.google.com/workspace/gmail/api/guides/sync), [Gmail threads](https://developers.google.com/workspace/gmail/api/guides/threads), [n8n API](https://docs.n8n.io/api/api-reference), [Calendar sync](https://developers.google.com/workspace/calendar/api/guides/sync), [Cal.com bookings](https://cal.com/docs/api-reference/v2/bookings/get-all-bookings), [Fathom meetings](https://docs.fathom.ai/api-reference/meetings/list-meetings), [GHL opportunities](https://marketplace.gohighlevel.com/docs/ghl/opportunities/update-opportunity/index.html), [Playwright package](https://pypi.org/project/playwright/), [Loom API limitation](https://support.atlassian.com/loom/docs/does-loom-have-an-open-api/).
