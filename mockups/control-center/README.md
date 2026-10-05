# Hawkins Control Center

A clickable, dark-theme design prototype for Armageddon's personal client outreach and job application workspace. Twelve fictional opportunities start the demo: six clients and six applications. All data, drafting, approvals, sends, discovery, and tool syncs are local simulations.

## Run locally

```sh
cd "/Users/armageddonvivas/Downloads/Client Scraping/mockups/control-center"
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite binds to the loopback interface. No environment variables or credentials are needed. Node 22.12+ is supported; this implementation was checked with Node 22.22.3.

The completed build is also available through the local production preview at `http://127.0.0.1:4173`. Restart that preview with `npm run build` followed by `npm run preview`. Preview and development ports use separate browser storage.

```sh
npm test                 # Focused model and approval tests
npm run typecheck        # TypeScript checks
npm run build            # Type checks and production assets in dist/
npm run preview          # Serve the production build locally
npm run format           # Format this prototype's source files
```

## Explore the design

| Screen | Route | What to try |
| --- | --- | --- |
| Today | `#/today` | Filter the queue to clients or applications; open a task; pause the sample schedule. |
| Discover | `#/discover` | Search client or job fixtures, inspect evidence, add a result, and preview empty or failed searches. |
| Pipeline | `#/pipeline` | Search, filter, switch table/board view, open a record, edit linked notes, or suppress a contact. |
| Draft Studio | `#/drafts` | Generate a suggestion, accept it into the editor, save a revision, inspect context, and approve in either review surface. |
| Inbox | `#/inbox` | Read sample threads, write a manual reply, inspect opt-outs/bounces, and reconcile Sunday Bureau's uncertain send. |
| Library | `#/library` | Search Drive/Notion reference documents, preview them, and link them to a draft. |
| Connections | `#/connections` | Reconnect Notion, sync or pause a sample tool, and inspect the limits and linked resources. |

Global search uses **Cmd/Ctrl+K**. The mobile navigation opens from the menu button. Opportunity details and draft editors use a back action on small screens.

### Two complete demo journeys

1. **Client:** Discover → Clients → Find opportunities → add Cedar & Finch → open in Pipeline → Write a draft → Generate suggestion → Use this draft → Save draft → Review & approve → Approve revision → close preview → Simulate send. Inspect its thread and `demo_gmail_*` result in Inbox.
2. **Application:** Discover → Applications → find and add Common Ground Studio → Write a draft → generate, accept, and save → Telegram preview → approve the displayed revision → close preview → Mark applied · demo.

Web and Telegram previews share one approval state. Editing a saved message or changing reviewed references creates a new revision and clears prior approval. Saving the same payload does not create unnecessary revisions. A sent payload remains in its send record. Initial outreach cannot be repeated by editing the text into another revision.

Unfinished edits are kept separately in local browser storage when navigating away. They do not change a stored approval until saved as a new revision. **Reset demo** clears this prototype's records and editor buffers and restores the seed data.

## Data and integration boundary

- All sample businesses and contacts are fictional; contact domains end in `.example`. Evidence buttons open local source previews.
- Gmail, Sheets, Notion, Drive, Telegram, n8n, and Brave Search have simulated connection panels. No OAuth, credentials, real scraping, provider API calls, scheduled jobs, or emails exist in this app.
- Generation returns deterministic sample text. A suggestion only enters the editor after the user accepts it; final review is still separate.
- The demo enforces revision matching, suppression, missing-contact blocks, the shared five-email-attempt daily limit, budget reservations up to $25, and safe uncertain-send reconciliation. Five weekdays are required for the single follow-up. These frontend controls are illustrative, not a secure backend authority boundary.
- A cost or provider ID beginning with `demo_` is simulation evidence only. Data in local storage is not suitable for real credentials or confidential client material.
- Same-tab state is shared across web and Telegram previews. This is not cross-device or live Telegram synchronization, and multiple browser tabs are not a concurrency-safe sender.
- The real Client Finder Python service, database, inactive workflows, and external Hawkins checkout are not modified by the prototype. Actual integrations and web approval authority require a separately reviewed implementation.

## Implementation map

- `src/types.ts`, `fixtures.ts`, and `model.ts`: typed records, fictional content, and state transitions.
- `src/store.tsx`: hash navigation, local persistence, and transient feedback.
- `src/App.tsx`, `Today.tsx`, `Workspaces.tsx`, `DraftStudio.tsx`, and `Integrations.tsx`: seven screen groups.
- `src/OpportunityPanel.tsx` and `Review.tsx`: linked tool panels, source previews, and exact-revision approval surfaces.
- `src/ui.tsx` and `styles.css`: Radix dialogs/tabs, reusable controls, responsive layouts, and dark theme.

React, TypeScript, Vite, Radix primitives, Phosphor icons, and locally bundled Geist fonts are installed and locked in `package-lock.json`.

See [VERIFICATION.md](./VERIFICATION.md) for checks and limitations, and [artifacts/](./artifacts/) for screenshots and browser audit records. Better Design's API was quota-blocked; the implementation uses the agreed direction and local visual review, not a Better Design approval receipt.
