# Verification record, updated 2026-10-05

The dated entries are cumulative. The complete acquisition workspace entry at the end records the newest implementation and live checks; earlier missing-schema and connection results are historical.

## Local

- `python3 -m unittest discover -s tests -q`: 88 passed on 2026-09-28. These are local tests with mocked providers and static SQL/workflow contracts, not live send evidence.
- `python3 -m compileall -q client_finder scripts`: passed.
- All four n8n exports parse as JSON and have `active=false`. Their Supabase URL fields point to Armageddon's owned Hawkins project, and no unverified error-workflow ID is embedded. None stores normal success/error execution payloads.
- All 146 `={{ ... }}` expressions in the four exports parse as JavaScript locally. The four workflows were imported on 2026-09-29; saved definitions were compared with the prepared exports. Runtime behavior remains untested.
- The unsent CLI preview now reports missing configuration clearly before it can start a paid search. The review workflow checks the connected Gmail account against the configured sender before it claims a send attempt. The read-only `db/postflight_existing.sql` object check was reviewed locally; the owner's subsequent live results are recorded below.
- The 2026-09-28 audit tightened same-agency and older-campaign send blocking, lock order, five-weekday timing, unexpected senders in known mail threads, US-agency location evidence, exact search-result-page research, robots checks across redirects, and credentialed API redirects. It also made partial discovery diagnostics visible, decoupled Telegram callback acknowledgment from review actions, and checks recorded Gmail IDs before reporting a confirmed send. These fixes have local tests only.
- Source registry rebuild kept all 393 spreadsheet rows and grouped them into 169 conservatively normalized URLs. Every registry source remains disabled.
- The four cited portfolio pages were opened in the browser. Their visible descriptions support the exact catalog claims; RFP Response Assistant is clearly labeled a prototype, while Workline is shown as deployed. Catalog activation remains a separate install step.
- On 2026-09-29 the four public proof pages were rechecked. Workline shows an approval-first application desk and a deployed status; Post-Call Proposal Builder shows an n8n workflow preparing reviewable drafts from approved call context; Lead Management and Recovery System shows the listed GoHighLevel intake and follow-up workflows; RFP Response Assistant is labeled a prototype and describes cited drafts with human review. These pages support the bounded catalog wording, not independently verified client outcomes or unattended operation. No activation was performed.
- The migration's duplicate `DECLARE` syntax error was corrected; a static regression check now covers it. Both migration files now have explicit transactions, and postflight requires the catalog seed and disabled sending. No local PostgreSQL compilation test was available because this workspace has no `psql` or Docker; the owner's subsequent migration and postflight evidence is recorded below.
- `research/trial_2026-09-27.md` and `research/trial_2026-09-28.md` record ten manually sourced, unsent agency working drafts with published business contacts. A source recheck replaced one stale careers URL and tightened two claims. Several still have weak buying signals. These are not ten stored Telegram cards and do not validate the Brave/n8n pipeline or cross-campaign suppression.
- `research/high_signal_replacements_2026-09-28.md` screened four more agencies for a stronger direct-email route; none qualified. No new draft was added to the ten working drafts.
- `research/high_signal_replacements_2026-09-29.md` screened an old explicit support request and a current local hiring route; neither is a current, direct-email client opportunity. The send-ready candidate count did not increase.

## Hosted foundation, read-only

- `https://n8n.armageddonvivas.cloud/healthz` returned HTTP 200. Its signed-in UI showed Hawkins workflows and credential entries for Gmail OAuth, Supabase API, and existing Telegram bots. No dedicated Client Finder bot or Brave credential was observed.
- On 2026-09-29 the owner reported creating `@Hawkins_Client_Finder_bot` and saving its n8n credential. The signed-in credential page for `CLIENT_FINDER_TELEGRAM_BOT` independently showed **Connection tested successfully** and the Telegram API base URL. The token was not revealed. The page does not show the authenticated bot username, so that identity and owner-chat delivery are not established by this credential test alone.
- The authenticated Supabase dashboard showed Armageddon's owned `hawkins-lab` project `mtdavgadkiiofwikzdtn` healthy on the free plan. Read-only SQL confirmed `cold_leads` and `cold_campaigns`, global lower(domain/email) unique indexes, 86 leads, and 11 prior sends. The overview showed no scheduled backups.
- The currently available Codex Supabase connector is scoped through a client account and listed zero projects. It cannot access the owned Hawkins project; no Client Finder migration was applied.
- A fresh connector `list_projects` check on 2026-09-28 still returned zero projects.
- A direct `get_project` check for `mtdavgadkiiofwikzdtn` returned permission denied. Hostinger's project list showed the running n8n stack and no Client Finder service.
- On 2026-09-28 the owner pasted the `db/preflight_existing.sql` result from his dashboard. All 23 structural rows reported `PASS`: both base tables, all 18 required `cold_leads` columns, both global unique indexes, and zero existing Client Finder objects. The remaining `INFO` row estimated 109 live leads. He then supplied the `db/preflight_counts.sql` result: 109 exact leads, 11 previously sent, and zero index-domain, index-email, canonical-domain, extra canonical-domain-row, or normalized-email duplicate counts. These are owner-provided outputs, not independently observed database results. A repeat Codex connector check still listed zero projects and denied direct access.
- The owner reports that a schema-and-data backup is saved. Its files and restoreability have not been inspected here. Local migration files remain unchanged; `python3 -m unittest discover -s tests -q` passed again with 88 tests before the manual migration handoff.
- The owner supplied a screenshot of the Supabase SQL Editor on project `mtdavgadkiiofwikzdtn` showing the end of `db/001_client_finder.sql` at line 1470 (`commit;`) and the result `Success. No rows returned`. This supports a successful editor run of migration 001. Database objects, grants, and function signatures still need the read-only postflight check; migration 002 has not yet been reported.
- On 2026-09-29 the owner reported completing `db/002_catalog.sql`. No result table or editor screenshot was supplied for the migration itself; the postflight catalog result below confirms its required seed rows.
- The owner then supplied a screenshot of the second `db/postflight_existing.sql` query in the owned project's SQL Editor. All three rows reported `PASS`: four of four required deliverables, four of four required proofs, and one settings row with `sending_enabled=false`. The first postflight query's 13 object/function rows remain outstanding.
- The first read-only postflight query initially returned `Error: Failed to fetch (api.supabase.com)` in the owner's dashboard, with no SQL result rows. This is a dashboard/request failure, not evidence of a failing database check. A refresh and one retry of that SELECT were requested; no migration retry or setting change was requested.
- The refreshed first postflight query returned 13 rows in the owned project's SQL Editor; the screenshot shows all 13 required table/function checks as `PASS`. Together with the earlier three-row result, both planned postflight queries pass. This verifies the named objects, five function signatures, four seeded deliverables, four seeded proofs, and `sending_enabled=false`. It does not yet verify grants, RLS, or the RPCs' live behavior.
- `db/003_activate_reviewed_catalog.sql` was prepared after the four public proof pages were rechecked. It updates only the four reviewed proof and four deliverable IDs, then selects three confirmation rows including disabled sending. Local static checks found one transaction, all eight expected IDs, and no update to `client_finder_settings`.
- The owner subsequently reported running `db/003_activate_reviewed_catalog.sql`; the final SELECT results are recorded below.
- The owner supplied the three final result rows from `db/003_activate_reviewed_catalog.sql`: `reviewed_proofs=PASS` (4 of 4), `deliverables=PASS` (4 of 4), and `sending_disabled=PASS` (one settings row, `sending_enabled=false`). The reviewed catalog is active for drafting, while outbound sending remains disabled.
- A read-only `db/postflight_security.sql` check was added for all 12 Client Finder tables and 43 functions. Static inspection matched those counts in migration 001. It checks RLS and effective privileges without returning contact data.
- The owner reports that `db/postflight_security.sql` returned 56 `PASS` rows and zero `BLOCK` rows. The raw rows or a screenshot were not supplied, so this is owner-reported live permission evidence. RPC behavior through the deployed service remains untested.
- Browser security policy blocked opening the local migration file in the browser for the Supabase SQL editor. No indirect workaround or live database mutation was attempted.
- The first browser upload attempt was blocked. The later, explicitly approved imports succeeded through the personal Chrome profile; see the import verification below. No outreach workflow was activated.

## Hosted build, inactive

- A separate **Hawkins — Client Finder Telegram Setup** workflow (`8jTgr97z1PirxQ9x`) was created through native n8n controls on 2026-09-29. It has one Telegram Trigger for `message` updates using `CLIENT_FINDER_TELEGRAM_BOT` and no downstream nodes. Manual tests produced no visible output. Automatic approval review initially rejected persistent activation; the owner then explicitly approved it. Publication under **Temporary owner setup** was confirmed by n8n's banner. After the owner sent a fresh marker, executions `74881` and `74882` succeeded in 13 ms and 8 ms. The visible JSON for `74882` contains the exact requested marker, `is_bot=false`, `chat.type=private`, and equal sender/chat IDs matching the owner's account. IDs are retained in the private n8n execution, not copied into this repository. The workflow was immediately unpublished and the UI returned to **Publish**, confirming the temporary listener is off. No Telegram reply or email was sent by this diagnostic workflow.
- A fresh Supabase `list_projects` call still returned an empty project list after the Telegram check. A guarded query was provided for the owner to set the two verified Telegram IDs in `client_finder_settings`, requiring existing fields to be null or already match, and forcing `sending_enabled=false`. The owner reports the result was one row with `owner_verified=true`, `chat_verified=true`, and `sending_enabled=false`. The result was not independently queried through the connector. The imported drafts now contain the verified owner bindings; review-card delivery, callback handling, and service/database integration remain untested.
- The Hostinger VPS has the running `n8n_default` Docker network and enough free disk for the application image. Client Finder source and a private Compose file were staged at `/opt/hawkins-client-finder` without credentials.
- `docker build -t hawkins-client-finder:staged .` succeeded on the VPS. The staged image imported the service modules successfully with network access disabled. `docker compose config --no-env-resolution --quiet` passed.
- No Client Finder container is running. The host-only secret file has not been created, so runtime health and n8n-to-service connectivity remain unverified. Existing hosted credential entries have not been confirmed as user-owned for this personal tool.

## Workflow import verification, 2026-09-29

- The owner explicitly approved uploading the four files in `workflows/` to `https://n8n.armageddonvivas.cloud` as unpublished drafts, then binding the verified Telegram credential and owner IDs. This approval persists; do not ask for it again for the same files, destination, and scope.
- All four source JSON files parse, have `active=false`, use native nodes without Code/Function nodes, and contain credential names rather than secrets. A token-pattern scan found no Telegram token, JWT, or common provider-key pattern. Private owner IDs remain absent from the repository's source exports.
- The first file upload failed because Chrome profile `heartofchicagohomes.com` lacked extension file access. Opening `chrome://extensions/` was blocked by Browser's URL policy; no extension-setting change or alternate access to that page was attempted. The owner then selected personal profile `armageddon`. Its extension connection timed out, but native Chrome control and the normal Mac file picker successfully imported the approved files.

| Workflow | Saved n8n ID | Nodes | Verified Telegram bindings | State |
| --- | --- | ---: | ---: | --- |
| Daily Discovery | `TaSrrFcWgr0W0Yd7` | 26 | 9 | Unpublished |
| Review and Send | `2PLgsImvFAGw0JTf` | 60 | 21 | Unpublished |
| Inbox Monitor | `VMx5m5ADmApXlkjU` | 27 | 4 | Unpublished |
| Due Follow-ups | `G2EyMqtsewhrQJAG` | 20 | 4 | Unpublished |

- All 38 Telegram nodes use the verified `CLIENT_FINDER_TELEGRAM_BOT`. All eight owner fields across the five configuration nodes match the incoming setup event. The owned Supabase URL is preserved in each configuration node. Private owner IDs were entered only in the hosted drafts, not source files.
- The n8n file import discarded workflow-level settings. Restored `Asia/Manila`, execution order v1, no success/error execution-payload saving, no manual-execution saving, and no execution-progress saving in all four drafts. Saved exports confirm every prepared setting. The independent error workflow remains unset.
- Opening the unbound Gmail send node auto-selected the existing `Gmail account` credential. The review draft was restored from the approved source file, its owner fields were reapplied, and the saved workflow was reopened and exported again. The final export has no Gmail, Supabase, or service credential bound. No credential value was revealed or changed, and no node was executed.
- Compared fresh exports after reopening all four saved workflows: 133 nodes, connection edges, node types/versions, retry/error behavior, all configured parameter values, owner bindings, and prepared workflow settings match. The comparison permits n8n's omitted explicit default parameters and regenerated assignment IDs. The editor independently showed the expected five-minute stale-send interval, callback Answer Query operation, and Gmail Send operation. The sanitized result is `research/workflow_import_verification_2026-09-29.json`; private verification downloads were not copied into the repository.
- The inbox `backfill_start_utc` placeholder remains pending. All four exports report `active=false`. This verifies saved configuration only; credentials, RPC behavior, callbacks, research, inbox monitoring, and sending have not been exercised by these drafts.

## Outstanding live validation

1. Confirm the saved schema-and-data backup is private and nonempty. Both planned postflight queries passed in the owner's screenshots. Grants, RLS, and RPC transactions still need live validation before outreach.
2. The owner-reported `db/postflight_security.sql` result is clear. The dedicated Telegram credential and incoming owner-message tests pass; the temporary listener is off. The owner reports the verified IDs are saved in Supabase with sending disabled. All four workflows are imported and owner/Telegram bindings verified. Configure the sender identity/footer, search provider, internal service, verified Hawkins Supabase and Gmail credentials, mailbox backfill date, and an independent user-owned n8n error workflow. Keep the drafts unpublished. Brave's documentation checked on 2026-09-29 requires explicit storage rights for retained API results; confirm that the selected plan permits the discovery code's stored URLs before activating search.
3. Run real research-only discovery, review ten unsent cards, and test mailbox, approval, concurrent cap, timeout, opt-out, and controlled owner-inbox send. The ten-card milestone has not been reached.
4. Activate daily discovery and pilot only after those checks pass.

No prospect messages or test emails were sent by this implementation.

## Personal inbox implementation, 2026-10-05

Scope: the user-approved personal inbox/task expansion, implemented only in **Client Scraping**. Mailbox is fixed to `armageddonvivas@gmail.com`; database is fixed to Hawkins `mtdavgadkiiofwikzdtn`. The fictional `mockups/control-center` app was preserved. The connected app is `apps/control-center` and starts with no seeded business data.

### Local and synthetic evidence

| Check | Result | Boundary |
| --- | --- | --- |
| Python backend regression | **119 tests passed** | Mocked providers and local HTTP fixtures; no inbox credentials used |
| Connected app API tests | **4 passed** | Wrong identity/project, incomplete setup, wrong login user, uncertain action errors |
| Embedded PostgreSQL | **16 scenario groups passed** | Migrations 001/002/004/005 execute; new migrations reapply without losing fixture records; not hosted Supabase |
| Frontend build | **Passed** | TypeScript plus Vite production build; main JS approximately 336 KB, 100 KB gzip |
| Browser interaction checks | **Passed** | Built app against a localhost server, with all private/external APIs intercepted by synthetic fixtures |
| Browser accessibility/overflow | **7 screen/state checks passed** | Zero axe WCAG A/AA violations in tested states; desktop 1440×1000 and mobile 390×844 |
| Preserved prototype | **21 tests passed** | Existing fictional prototype's state/model tests |
| Python compile check | **Passed** | `client_finder` and `scripts` |

Embedded database scenarios cover identity/lease checks, failed checkpoints, inbox/task deduplication, classification corrections surviving resync, OnlineJobs-to-Gmail source retention, missing Loom proof, disabled delivery, duplicate approval, new correspondence canceling reserved delivery, immutable payloads, unknown-send protection, exact revision changes, owner-confirmed Won, onboarding deduplication, manual Gmail replies, restored messages, five-weekday reminders, Telegram owner/card validation, shared web approval, suppression after approval, separate reply/outreach counters, competing approvals for the final reply slot, recorded failed agent attempts/retries, and the shared monthly cost cap. PGlite serializes requests in one embedded database; these are **not independent-session PostgreSQL concurrency proof**.

Python scenarios additionally cover Gmail pagination, a failed later page leaving the checkpoint unchanged, expired-history full recovery, received/sent/label events, account rejection before mail reads/sends, notification addresses lacking reply authority, unaligned platform authentication, job alerts versus actual replies, quoted opt-outs, untrusted instructions remaining data, manual import deduplication, short replies requiring review, preceding Loom-offer evidence, no paid call after a failed cost reservation, unsupported model links, missing-proof blockers, missing Gmail result IDs, send timeout handling, inconclusive Sent reconciliation, unauthorized Telegram callbacks, and partial review-card failure without binding approval buttons.

Browser checks exercise setup-disabled sign-in, fixed personal sign-in, Today task → originating conversation, OnlineJobs origin and Loom blocker, a saved classification correction, older-conversation pagination, saved draft revision, complete recipient/subject/body review, disabled approval before reply activation, one exact-revision queue action, Won requiring evidence, Connections, mobile navigation, a manual platform import with recipient confirmation and prior context, malicious HTML displayed as plain text, and empty local/session storage. No uncaught browser runtime errors occurred. Screenshots and the machine-readable report are in ignored `artifacts/control-center/`.

The UI reuses the existing dark Geist/Phosphor layout and was visually inspected at desktop/mobile sizes. Better Design's UI, UX, and review tool requests returned **402 quota unavailable** during this implementation. No Better Design approval is claimed; local accessibility checks and manual visual review were completed.

Commands:

```sh
python3 -m unittest discover -s tests -q
python3 -m compileall -q client_finder scripts
npm --prefix apps/control-center test
npm --prefix apps/control-center run test:db
npm --prefix apps/control-center run build
npm --prefix mockups/control-center test
```

For the browser suite, start the root backend on port 8089 with no credentials and run `npm --prefix apps/control-center run test:browser`. This run used cached Chromium headless shell 1228 via `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH`. The test accepts localhost URLs only and intercepts external/private APIs.

### Live integration status

- The owned project remains inaccessible through the available Codex Supabase connector: a direct project lookup returned permission denied. No alternate project was used.
- No personal Gmail OAuth, owned Supabase service configuration, OpenRouter credential, or dedicated-bot token was available in this workspace/runtime. A connector for another account was not used to read or send mail.
- No new backup, live migration, hosted workflow import/update, deployment, schedule activation, model call, review-card message, or email send was performed.
- Local workflows 02 and 03 now include stricter fixed-personal-account checks; 02 also routes conversation reply callbacks to the shared stored-revision service. New 05–07 remain inactive. Previously imported September drafts are older versions and do not establish these changes on the host.
- The optional Docker/nginx/Traefik deployment files are prepared. Docker image rebuild, host readiness, DNS/TLS, real Supabase Auth/RLS, OAuth refresh, Gmail history behavior, and live callback concurrency have not been exercised.
- Jeff's acceptance case is represented by a **sanitized synthetic equivalent**: OnlineJobs origin, a positive answer to a preceding Loom offer, and Prepare Loom email blocked on missing verified proof. Jeff's actual thread has not been imported and no reply was sent.

### Next live acceptance sequence

1. Connect the personal credentials through the host's private secret configuration and grant access to Hawkins `mtdavgadkiiofwikzdtn`. Verify identities before mailbox access. Make and inspect a fresh private database backup.
2. Apply 004 then 005; run `db/postflight_personal.sql` with both sending flags false, comparing legacy history/suppression counts with the backup. Confirm real owner-only sign-in.
3. Run the inbox sync manually. Observe a real personal inbox arrival all the way to its stored source classification, visible task, blocker/result, and saved draft. Import missing OnlineJobs context; review actual Loom proof before clearing its blocker.
4. Exercise concurrent approvals/caps, suppression during approval, stale cards, account mismatch, expired history, and ambiguous send results against the hosted stack. Verify the dedicated bot uses the same stored revision as the web app.
5. Approve one exact message to a controlled inbox explicitly, then validate its provider IDs, Sent payload, downstream records, reply detection, and follow-up cancellation. Only then enable prospect responses and the agreed schedules with authorization.

Neither the local tests nor a configured connection satisfies the live inbox or delivery acceptance milestone. The original ten-real-unsent-prospect-card pilot remains separate and open.

## Owner Auth setup follow-up, 2026-10-05

**Live, read-only dashboard check:** In personal project `mtdavgadkiiofwikzdtn`, the Auth user for `armageddonvivas@gmail.com` is email-confirmed. The project settings also identify that email as its owner. No password, Auth setting, credential, database record, or permission was changed. The Codex Supabase connector still returns permission denied for this project. Application sign-in and API access have not yet been tested with real keys.

**Local/synthetic verification:** `python3 -m unittest discover -s tests -q` passes **136 tests**. The 17 additional checks cover read-only credential verification, exact project/user/confirmation rejection, public versus privileged key separation, current and legacy key headers, safe private file loading, permissions, symlink and overwrite refusal, failed setup without saving, environment override validation, no key disclosure, and connection loading before service startup. No paid call or real provider request was made by these tests. The prior frontend, database, and browser results above were not rerun for this backend-only setup change.

The new `python3 -m client_finder configure --owner-id …` command accepts hidden Terminal input and saves verified credentials outside the source tree. No real private connection file was created during implementation. Actual API keys remain a setup requirement; backup, migrations, Gmail intake, hosted deployment, and controlled-message acceptance remain unverified.

## Saved connection and database preparation, 2026-10-05

The owner ran the private setup command and saved API credentials. A subsequent **live read-only API check** verified the exact confirmed personal Auth owner and both keys. The owned database returned 231 cold leads, one campaign, zero Client Finder send attempts, `sending_enabled=false`, daily outreach limit 5, and monthly cap 2500 cents. Requests for the mailbox, task, and conversation tables returned `PGRST205` (missing from the Data API schema). Public Auth signups are still enabled; owner-only backend authorization remains enforced. No raw keys or contact rows were printed.

PostgreSQL 17.11 client tools and their Kerberos dependency were installed from Homebrew's official formulas. The first install encountered an existing CA-certificate link conflict; the clients were installed using the existing OpenSSL 3.6.3 and current certificate bundle. No server, shell PATH changes, or Homebrew tap trust changes were made. The system CA bundle did not trust Supabase's database certificate. The public Supabase Root 2021 CA was downloaded from the personal dashboard, copied into this workspace, and pinned in the setup helper. The browser's original download was left in its configured download directory; no files in another project were moved or deleted.

The personal session-pooler endpoint was reached with full TLS and hostname verification using that certificate. The password-free probe stopped at `no password supplied`; it did not authenticate or execute a query. No SSL settings or system trust store was changed.

**Synthetic verification:** the backend suite now passes **147 tests**. The additional database setup cases cover project/owner/sending gates, inherited PostgreSQL credential isolation, certificate pinning, hidden/private password handling and cleanup, backup and archive failures preventing migration, combined transaction construction, and uncertain commit outcomes retaining the backup. The embedded PostgreSQL suite passes its earlier 16 scenario groups plus **three new groups**: a permission failure rolls back both migrations, the exact combined bundle passes all pre-commit checks with sending disabled, and repeating an installed bundle is refused. The generated bundle uses the actual repository migrations and postflight SQL.

The owner has confirmed that the database password is available for private entry. `python3 -m client_finder database-setup --apply` is ready for that step. A fresh backup and the live migration are not yet confirmed; no Gmail, hosted workflow, model call, or outgoing message was activated by this preparation.

The local command center was started with the saved connection at `http://127.0.0.1:8088`: the page returned HTTP 200, public configuration reported the fixed personal identity and `configured=true`, and an unauthenticated workspace request returned HTTP 403. This verifies the local server and anonymous access rejection; an authenticated workspace load still depends on the missing inbox migration.

## Full command center restored, 2026-10-05

This update supersedes the missing-schema status immediately above. The private first-install manifest at `~/.config/hawkins-personal/backups/20261005T083420Z-18d974ce/` records a 560,989-byte logical archive and `committed_with_postflight_checks` for migrations 004/005. Its history baseline is 231 leads, one campaign, zero suppressions, and zero Client Finder send attempts. The temporary password file was not read. No deployed migration was edited or reapplied.

**Live, read-only personal API verification:** The fixed confirmed owner and personal project were verified again. The inbox workspace now loads: zero conversations, tasks, opportunities, or agent runs, and no connected mailbox. New catalog queries return 231 leads, 11 with recorded first contact, zero recorded replies, four proofs, and four deliverables. All 231 lead IDs were read across three bounded pages with no duplicates or omissions. Lead detail, linked-opportunity lookup, full-result search, and quoted reserved-character search completed successfully. The bundled directory contains 169 sources from 393 original rows. These checks printed counts only, not credentials or contact records. `sending_enabled` remains false.

**Implementation:** Restored Discover and Library alongside Today, Pipeline, Draft Studio, Inbox, and Connections. Today exposes existing records before inbox sync; Pipeline links to saved leads. Discover provides paginated search, contact-history filters, saved research, evidence, suppression, and stored-message inspection. Library shows active/inactive and verified/unverified proof, deliverables, source directory, and the seven agents with recorded task/run status. Hash links survive sign-in. The source directory is included in the Docker backend; no deployment was performed. All new data routes require the same verified owner session. They do not mutate business data, launch research, approve messages, or send.

**Local/synthetic checks:** 157 Python tests pass, including ten added catalog/count/authorization checks. Four frontend API tests pass and the final TypeScript/Vite production build succeeds. A separate `tests/catalog-preview.mjs` localhost fixture served the actual production build with synthetic records and blocked external requests. Browser checks verified all seven navigation entries, Today record links, Discover pagination/search/contact filtering, missing contacts, suppression details, literal untrusted script text, rejected unsafe links, all four Library tabs, seven agent responsibilities, source-search empty state, and direct navigation after sign-in. Desktop (1440px) and mobile (390px) renders were inspected; mobile Discover, lead details, and agent roster had no horizontal overflow. No browser console warnings/errors were recorded. Better Design UI, UX, and review requests remained quota-blocked (HTTP 402); no Better Design approval is claimed. The existing embedded PostgreSQL, prototype, and automated browser suites were not rerun for this read-only catalog/UI change; prior results above remain separately dated evidence.

**Access check:** The restarted local server at `http://127.0.0.1:8088` returns HTTP 200 and configured personal sign-in. Anonymous calls to `/api/overview`, `/api/leads`, and `/api/library` return HTTP 403. The real app was opened at `#/discover`, awaiting the owner's private Auth-password sign-in. Real business data was verified through the backend API; rendered signed-in UI checks used synthetic data. The existing fictional prototype on port 4173 was preserved.

**Remaining:** Personal Gmail OAuth and first real intake, hosted service/scheduler readiness, model and dedicated-bot credentials, exact-message controlled-send acceptance, and prospect response activation. No Gmail mail was read, no paid model call was made, and no message or workflow was activated during this update.

## Complete acquisition workspace, 2026-10-05

### Installed database and local application

The owner ran `python3 -m client_finder acquisition-setup --apply` and reported **Acquisition schema ready**. Independent inspection of its private manifest confirmed a **643,268-byte** `before-acquisition.dump`, successful archive decoding, and `committed_with_postflight_checks`. All migration checksums match the deployed files. A restore rehearsal has **not** been performed. Preserve migrations 001–008 and use a new additive migration for future changes.

Read-only checks against personal project `mtdavgadkiiofwikzdtn` confirmed **231 preserved cold leads**, **9 connection records**, **8 workflow references**, and zero jobs, resources, queued operations, conversations and tasks before setup/import. Outreach and applications are disabled; no mailbox is enabled for replies. The local server at `http://127.0.0.1:8088` serves the updated production build, reports the fixed personal identity with `configured=true`, and returns HTTP 403 for anonymous acquisition snapshot and job requests. Database checks use the private personal service connection, not the inaccessible Codex Supabase connector. No credentials or contact rows were printed.

The seven screens now include job intake and separate application stages, stored cover-letter/screening-answer revisions, selected profile and document links, reviewed history preview/commit, recorded workflow observations, calls into proposal tasks, integration queues and GHL conflict review. Bounded agent runs retain context and results. Application attempts use their own five-per-day bucket, existing outreach remains five, and verified replies remain twenty. Web and Telegram share stored revisions; unknown sends/submissions require reconciliation. Manual handoff explicitly begins an approved attempt before accepting a submission receipt. Selected document links are part of the reviewed submission body; unsupported binary-upload controls require manual handling.

### Existing hosted n8n workflows: read-only audit

The owner confirmed that the signed-in personal n8n account uses a separate login email. Its exception applies only to n8n; Gmail remains fixed to `armageddonvivas@gmail.com`. All eight workflow breadcrumbs belong to personal project `OR8nv0dBAKXF38uZ`. “Hawkins - Outreach” is a folder within that project, not a different account/project.

| Saved workflow | Observed publication | Inspected execution |
| --- | --- | --- |
| [Dustin · OnlineJobs](https://n8n.armageddonvivas.cloud/workflow/V0xHCzfFMgKR61yh) | Published | `85424`, Oct 4 22:00:00, Succeeded, 1m 38.84s |
| [Eleven + Steve · Score & Draft](https://n8n.armageddonvivas.cloud/workflow/hwEDWc0F9Wam1MgB) | Published | `86775`, Oct 5 18:45:01, Succeeded, 1m 9.699s |
| [Hopper · Jobs API](https://n8n.armageddonvivas.cloud/workflow/x10lpGeWihYhpunW) | Published | `86779`, Oct 5 18:49:45, Succeeded, 3.64s |
| [Client Finder · Discovery](https://n8n.armageddonvivas.cloud/workflow/TaSrrFcWgr0W0Yd7) | Unpublished | No executions found |
| [Client Finder · Review & Send](https://n8n.armageddonvivas.cloud/workflow/2PLgsImvFAGw0JTf) | Unpublished | No executions found |
| [Client Finder · Inbox Monitor](https://n8n.armageddonvivas.cloud/workflow/VMx5m5ADmApXlkjU) | Unpublished | No executions found |
| [Client Finder · Due Follow-ups](https://n8n.armageddonvivas.cloud/workflow/G2EyMqtsewhrQJAG) | Unpublished | No executions found |
| [Hawkins · Prepare Proposals](https://n8n.armageddonvivas.cloud/workflow/saO2Ns7Qp604kcvm) | Published | No executions found |

Execution start times above are the browser-displayed Asia/Manila times. Stored finish observations are start plus the displayed duration. The Dustin execution canvas showed 76 items at Add to Sheet; the actual Sheet rows were not independently checked. Scoring/drafting shows repeated fifteen-minute successes, and Hopper shows recent API requests. These establish n8n execution status only, not correct downstream records, complete applications, or delivery.

The eight observations and three successful run references were stored in Hawkins and read back successfully. The n8n connection remains disabled/needs attention with `manual_audit_only_automated_monitoring_not_verified`. This manual audit is not an installed continuous monitor. The existing hosted workflows were not edited, paused, activated or replaced. Local exports 08/09 add an inactive work-queue consumer and a bounded Dustin intake adapter; they have not been uploaded.

### Local and synthetic verification

- **195 Python tests pass**, including wrong personal identities, n8n's explicitly configured login exception, bounded provider pagination, import normalization, review resources, stale context, exact application content, preflight failures, expired sessions, unknown submissions, dedicated Telegram previews, and web outreach delivery without competing for legacy Telegram attempts. Two final cases cover a successful HTTP 204 void RPC and rejection of an unexpectedly empty HTTP 200 JSON response. Providers are mocked; this does not verify live credentials.
- **30 embedded PostgreSQL scenario groups pass:** 16 existing inbox groups, 3 setup/transaction groups, and 11 acquisition groups. They exercise the actual additive migrations, exact revisions and immutable attempts, separate daily capacities, stale approvals, suppression, duplicate/cross-source imports, late correspondence, integration leases, changed meeting context, uncertain/manual submissions, CRM conflicts/reconciliation and owner-confirmed onboarding. The database setup test uses the exact Python-generated three-migration bundle. PGlite checks are serialized; independent production PostgreSQL connection races were not tested.
- **4 connected-frontend API tests** and **21 preserved fictional-prototype tests** pass. The final TypeScript/Vite production build succeeds.
- The production UI was exercised using a separate localhost fixture with synthetic data and external requests blocked. Checks covered the full saved application, screening answer and profile; edits disabling approval until a new revision is saved; missing cutover blocking submission; literal malicious script text; seven-screen navigation; the original eight workflow links; and mobile job review/Connections without horizontal overflow at 390px. These are synthetic UI checks, not signed-in real-data acceptance.
- Better Design UI, UX and review requests returned HTTP 402 (quota exhausted). Manual visual checks were completed; no Better Design approval is claimed.

### Jeff: real platform import and blocked task

The original thread was opened through the signed-in OnlineJobs UI. Its Account Settings independently showed the required personal email. The live thread matched the supplied screenshot, including the full incoming request, timestamp, directly provided email and preceding Loom offer. That incoming message and its original platform reference were imported into the personal database; the preceding question was retained separately as classification context. Private conversation text and recipient details were not copied into repository fixtures or documentation.

Readback confirms **one real conversation**, OnlineJobs acquisition source, `onlinejobs_conversation` classification, a verified directly provided reply address, and **Prepare Loom email** assigned to Steve. The actual prerequisite check records **A reviewed, verified Loom link is required before drafting**. Eleven's qualification task is separately blocked because the personal AI provider is not configured. No draft or outgoing attempt was created. This proves manual platform intake, classification and real task creation; automatic Gmail arrival and a reviewed draft remain unverified.

After the owner's private sign-in, the real localhost UI was also checked: Today shows the two blocked tasks and 231 saved leads; opening Prepare Loom email displays the real imported message, OnlineJobs origin, classification reason and exact missing-proof blocker in Inbox. Connections renders all eight stored workflow observations, the three successful run times and the manual-audit-only warning. A transient fetch alert from the server restart was cleared after a successful refresh. These rendered real-data checks are separate from the synthetic frontend fixture above.

The first live task completion revealed that the shared HTTP client tried to decode an empty successful void-RPC response as JSON. Read-only reconciliation confirmed the database write had committed, so it was not repeated. The client now accepts HTTP 204 without a body and still rejects a malformed HTTP 200 JSON response. After the fix, the next real prerequisite check completed and the whole acquisition/workspace snapshots loaded successfully. The server was restarted with this fix.

### Remaining live acceptance and setup

The personal Google OAuth, n8n API, model/search, other provider credentials, selected resources, hosted backend and browser worker still need verification. The signed-in OnlineJobs UI identity check does not establish a configured hosted submission session. Existing job workflows continue to run outside Hawkins; their paid calls are **not yet governed by the shared $25 ledger**. Reconcile legacy Sheet/API/application queues and stop competing consumers before cutover. No Sheets/Notion history batch has been committed and no original tracker has been archived.

Ten current stored unsent prospect cards, one researched job with a reviewed cover letter, a real Gmail inbound-to-draft cycle, a real call-to-proposal task and a confirmed-win onboarding example remain outstanding. Jeff's real manually imported Loom task is now verified, with missing proof correctly blocking drafting. No mail was read from Gmail, no paid provider call was made, no message was sent, and no application was submitted during this expansion. All three sending flags remain disabled. Follow [ACQUISITION_SETUP.md](ACQUISITION_SETUP.md) for private setup and live cutover.

## Agent-prepared cover letters, 2026-10-05

The job review page now leads with Steve's drafting status or current completed suggestion. A current suggestion fills the letter and required screening answers automatically; manual writing is optional. Owner edits survive background refreshes. Saving still creates a server revision, and approval remains a separate action. Changed job context, changed/unreviewed resources, incomplete answers, and blocked tasks cannot silently supply the editor.

Steve's cover-letter instructions now require short, plain wording focused on the employer's stated need, a useful result, relevant verified work, and one simple next step. The target is 70–110 words with a 130-word validation limit. Screening answers are separate, retain the exact question text, and expose missing required facts. The current Eleven qualification brief and reviewed resource versions are recorded with the workflow. No model, pricing, credential, or approval authority changed.

**Local/synthetic:** 204 Python tests and 10 connected-frontend tests pass; the TypeScript/Vite production build succeeds. New checks cover the scoped writing instructions, letter length, exact questions, missing answers, unverified links in answers, exhausted budget without a provider request, current qualification prerequisites, and stale job/resource suggestions. The production build was exercised against isolated localhost fixtures: a ready letter and screening answer loaded without typing, an owner edit survived polling, and saving created revision 1 with those exact fields. Submission remained blocked by the existing cutover gate. With AI configuration absent, the page showed the setup blocker and no blank editor until the optional manual-writing control was selected. Desktop and 390px mobile layouts were inspected, with no horizontal overflow or console warnings/errors. Better Design requests remained quota-blocked (HTTP 402); manual inspection is not Better Design approval. No SQL or prototype changes were made, so their previously recorded checks were not rerun.

**Actual local readiness:** The private configuration check found no personal OpenRouter key or n8n API key configured. The restarted real command center on port 8088 returns HTTP 200. This is a local UI/workflow correction, not proof of successful paid generation or hosted execution. Personal AI setup, reviewed profile facts, a verified job, and the hosted task worker remain prerequisites for a real cover letter. No paid provider request, database migration, message, application submission, or workflow activation occurred during this change.
