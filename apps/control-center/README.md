# Personal Hawkins command center

Connected frontend for **armageddonvivas@gmail.com** and Hawkins Supabase **mtdavgadkiiofwikzdtn**. The separate fictional prototype stays in `../../mockups/control-center`. No real records are seeded here.

From this directory:

```sh
npm ci
npm run build
npm test
npm run test:db
```

From the workspace root, run `python3 -m client_finder serve`, then open `http://127.0.0.1:8088`. Without personal configuration the app displays setup needed and disables sign-in. For development, `npm run dev` uses port 5174 and proxies `/api` to that backend.

The backend serves the compiled app and validates owner sessions through the fixed Supabase Auth project. Access and refresh tokens stay in React memory; reloading the page requires signing in again. Mail, tasks, revisions, approvals, and stage decisions live in PostgreSQL. There is no browser-storage authority or demo fallback.

Today shows due tasks. Inbox shows original source, actual channel, incoming text, request evidence, and classification corrections. Draft Studio saves immutable revisions and displays the complete recipient, subject, and body before approval. Pipeline requires an outcome note for Won or Lost. Connections shows persisted sync state, task backlog, and errors. Inbox loads older conversations in pages; an opened conversation loads its latest 500 messages and associated tasks/drafts. Older history remains in the backend.

The complete acquisition extension adds job views in Discover/Pipeline, outreach and application views in Draft Studio, reviewed resources in Library, and all saved n8n links in Connections. Jobs page through stored history; exact application revisions include screening answers and selected document links. Calls, import previews, personal resource selection and CRM conflicts are owner-authenticated backend actions. Missing migrations or credentials produce setup/error states, never simulated connections. Read [the acquisition setup guide](../../ACQUISITION_SETUP.md) before enabling a worker.

For an entirely isolated visual check, `node tests/catalog-preview.mjs` serves **synthetic data** at port 8090 with any test password and blocked external API access. This is test infrastructure, not the personal app at 8088. It is not packaged in the application image.

For browser checks, run the root backend on port 8089 without credentials, then:

```sh
npx playwright install chromium
npm run test:browser
```

`CONTROL_CENTER_TEST_URL` can select another localhost port. `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` optionally selects an already installed Chromium binary. The browser suite intercepts all API calls with synthetic fixtures, denies other network destinations, and does not authenticate a real account or send a message. Screenshots and accessibility results go to `../../artifacts/control-center` (ignored). Database tests use embedded PostgreSQL/PGlite, not the hosted Supabase database. Independent-session concurrency and live RLS/JWT behavior still require hosted checks.

See the root [setup guide](../../README.md#personal-inbox-setup) and [verification record](../../VERIFICATION.md#personal-inbox-implementation-2026-10-05).
