# Control Center prototype verification

Local prototype verification on 2026-10-04. No production integrations or real outreach were exercised.

## Automated model checks

`npm test`: 21 passing tests covering:

- Twelve seeds, equal client/application representation, and duplicate company discovery.
- Exact-revision approvals, stale cards, repeated approvals from both surfaces, and approval invalidation after edits or reference changes.
- Missing published contact evidence and recipient/evidence mismatches.
- Unaccepted generated suggestions remaining separate from saved drafts.
- Immutable sent payloads, duplicate-send prevention, second-initial-email blocks, five-attempt daily limits, and suppression after approval.
- Paused Gmail, job approval versus application completion, and no email attempt for marking an application applied.
- Uncertain-send reconciliation, retaining attempted payloads, and fresh review after confirmed-not-sent results.
- Weekday follow-up timing, one-follow-up eligibility, replies/bounces/opt-outs, and budget exhaustion.
- Local notes, browser-state loading/reset, unavailable storage, and keeping unfinished editing separate from approved revisions.

`npm run build`: TypeScript and Vite production build passed. `npm run typecheck` passed separately during implementation.

## Browser journeys

Checked through the rendered app in Chrome:

- Added Cedar & Finch from discovery, generated and accepted a draft, saved it, approved its exact text on the web, confirmed the same approval in the Telegram preview, and recorded one simulated send.
- Added Common Ground Studio, generated and saved a cover letter, approved it through Telegram, and marked it applied.
- Approved Northline's revision 1, edited it, and verified revision 2 had no approval in the Telegram preview.
- Edited Notion notes and spreadsheet notes; reloaded and verified the entered values persisted.
- Left an unfinished subject edit, navigated away, and verified the editor restored it. Saved the edit and attached a reference through Library.
- Reconciled Sunday Bureau's uncertain result against a sample Sent-folder match without resending.
- Exercised empty discovery results, source failure, and successful retry. Network observation during those actions recorded no requests.
- Switched from a running client search to an application search and verified only job results appeared; changing search criteria cancels the stale result.
- Reconnected Notion in the demo, updating its card status and activity.
- Exercised global search, keyboard focus inside its dialog, and Escape handling. Focus restoration was corrected during review and checked again.

## Visual and accessibility checks

- Checked all seven screens at 390, 768, 1440, and 1728 pixels. No document or main-content horizontal overflow was found in those 28 screen/width checks.
- Inspected saved desktop, tablet, and mobile renders. The editor displays research alongside the document on wide screens, with a context dialog on smaller screens.
- The existing Hopper Desk source was inspected as a reference. This is a separate prototype; a matched before/after rendering of the existing application was not captured.
- Inspected text contrast against rendered backgrounds. The initial pass found two decorative separators below 4.5:1; their colors were raised and checked again. This is a targeted contrast check, not a full accessibility certification.
- Native form labels, visible keyboard focus, Radix dialog focus behavior, and keyboard-accessible tabs are used.
- Reduced-motion styling removes animations and transitions; search still completes while reduced-motion emulation is active.
- The final built app was opened at `http://127.0.0.1:4173`, its draft review dialog was exercised, and the fresh production check recorded no new exceptions or console errors. Development hot reloading had logged transient stale-module errors while dependencies and source were being updated; the final production preview does not use hot reloading.

Screenshots and raw observations are under `artifacts/`. Screenshot content is fictional; the final overview is reset to the initial sample state.

## Limits of this evidence

- No live scraping, credential validation, Gmail acceptance, inbox delivery, cloud sync, Telegram callback, deployment, or pilot result is claimed.
- There is no public HTTPS preview or Better Design review receipt. Better Design was unavailable due to its query quota.
- Responsive and interaction checks were performed in Chrome. Safari/Firefox and physical-device testing were not performed.
- Browser storage and reducers demonstrate the design; they are not production access control, atomic database reservations, or cross-tab concurrency protection.
