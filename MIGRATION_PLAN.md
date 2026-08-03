# MIGRATION PLAN — Vite + React + TS + Tailwind/shadcn (frontend) · Express MVC (backend)

Status: **plan only — no code written yet.**
Baseline commit: `4cd144d`

---

## 0. What this codebase actually is (read this first)

The request describes the project as "plain HTML/CSS/JavaScript". That is accurate for the
**frontend** but not the backend:

| Layer         | Reality                                                                   | Size            |
| ------------- | ------------------------------------------------------------------------- | --------------- |
| Frontend      | 6 static HTML pages + 2 plain JS files, Tailwind/ECharts/SheetJS from CDN | **2,288 lines** |
| Backend       | **Python 3.11 · FastAPI · SQLAlchemy · Alembic**                          | **5,578 lines** |
| DB migrations | Alembic, **15 revisions**, applied to a **live production Postgres**      | —               |

So the two halves of this request are very different jobs:

- **Frontend → Vite/React/TS/Tailwind/shadcn** = a real refactor. Well-defined, incremental, low risk.
- **Backend → Express MVC** = a **full rewrite of 5,578 lines of Python**, not a refactor. This is
  where "keep all existing functionality unchanged" is at genuine risk.

The structure below covers both. Section 6 lists the specific things that can break, and
section 8 asks you to pick the backend path before any code is written.

---

## 1. Target repo structure (top level)

A pnpm workspace monorepo. **The existing Python app stays exactly where it is** during the
migration — `app/`, `migrations/`, `config/`, `alembic.ini` are untouched until the Express side
actually replaces them. That is what makes this incremental instead of a big-bang cutover.

```
exhibitiondashboard/
├── package.json                  # pnpm workspace root + shared scripts
├── pnpm-workspace.yaml
├── tsconfig.base.json            # shared compiler opts + path aliases
├── eslint.config.js              # flat config, shared
├── .prettierrc
├── .npmrc
│
├── apps/
│   ├── web/                      # NEW — Vite + React + TS + Tailwind + shadcn/ui
│   └── api/                      # NEW — Express + TS, MVC
│
├── packages/
│   └── shared/                   # NEW — types + zod schemas used by BOTH web and api
│       └── src/
│           ├── types/            # Campaign, ReportRow, RosterEntry, Platform, JobStatus…
│           ├── schemas/          # zod — single source of truth for validation
│           └── index.ts
│
├── app/                          # EXISTING FastAPI — stays until fully replaced, then deleted
├── migrations/                   # EXISTING Alembic — see §6.3, do NOT recreate
├── config/                       # EXISTING seed JSON — moves late, unchanged in content
├── scripts/                      # EXISTING dev helpers — ported last
│
├── Procfile                      # updated at cutover only
├── railway.json                  # updated at cutover only
└── MIGRATION_PLAN.md             # this file
```

---

## 2. `apps/web` — feature-based frontend

```
apps/web/
├── index.html                    # single Vite entry (replaces all 6 HTML pages)
├── vite.config.ts                # aliases + dev proxy /api -> backend
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.js
├── components.json               # shadcn/ui CLI config
├── .env.example                  # VITE_API_BASE_URL, VITE_GA_ID, VITE_GLOBAL_MENU_URL
├── public/
│   └── logo.png
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── vite-env.d.ts
    │
    ├── app/                      # app-level wiring — NOT a feature
    │   ├── router.tsx            # React Router route tree (all legacy URLs preserved)
    │   ├── providers.tsx         # Redux Provider > QueryClientProvider > Router
    │   ├── store.ts              # Redux Toolkit configureStore
    │   └── queryClient.ts        # TanStack Query defaults (staleTime, retry, 401 handling)
    │
    ├── features/
    │   ├── auth/
    │   │   ├── api/authApi.ts                  # POST /auth/login, GET /auth/profile
    │   │   ├── components/
    │   │   │   ├── LoginForm.tsx
    │   │   │   ├── UserChip.tsx                # avatar + dropdown + logout
    │   │   │   └── RequireAuth.tsx             # route guard
    │   │   ├── hooks/useLogin.ts · useProfile.ts
    │   │   ├── store/authSlice.ts              # RTK: token, user, roles
    │   │   ├── lib/session.ts                  # localStorage `wz_session` + URL-token handoff
    │   │   ├── types.ts
    │   │   └── pages/LoginPage.tsx
    │   │
    │   ├── campaigns/
    │   │   ├── api/campaignsApi.ts
    │   │   ├── components/
    │   │   │   ├── CampaignGrid.tsx · CampaignCard.tsx
    │   │   │   ├── CreateCampaignDialog.tsx · RenameCampaignDialog.tsx
    │   │   │   ├── DeleteCampaignDialog.tsx
    │   │   │   └── ShareLinkDialog.tsx         # view-token / client link
    │   │   ├── hooks/useCampaigns.ts · useCampaignSummary.ts · useCampaignMutations.ts
    │   │   ├── types.ts
    │   │   └── pages/HomePage.tsx
    │   │
    │   ├── report/                             # the biggest feature
    │   │   ├── api/reportApi.ts
    │   │   ├── components/
    │   │   │   ├── ReportHeader.tsx            # title line + action row
    │   │   │   ├── KpiRow.tsx                  # 6 KPI cards
    │   │   │   ├── EngagementBreakdown.tsx     # likes/comments/shares/saves
    │   │   │   ├── Podium.tsx · PodiumFilters.tsx
    │   │   │   ├── charts/
    │   │   │   │   ├── CategoryDonut.tsx       # views by category
    │   │   │   │   ├── CategoryErBar.tsx       # ER% by category
    │   │   │   │   ├── EngagementStack.tsx     # stacked engagement
    │   │   │   │   ├── TopKolBar.tsx           # top-10 by views
    │   │   │   │   └── FollowersViewsScatter.tsx
    │   │   │   ├── PostsTable.tsx              # sortable table
    │   │   │   ├── ExportCsvButton.tsx
    │   │   │   ├── RefreshDataButton.tsx · FetchProfilesButton.tsx
    │   │   │   ├── PackshotUpload.tsx · TieInButton.tsx
    │   │   │   └── CostBadge.tsx               # per-campaign Apify spend
    │   │   ├── hooks/
    │   │   │   ├── useReportData.ts
    │   │   │   └── useRefreshJob.ts · useProfilesJob.ts · useTieInJob.ts   # status polling
    │   │   ├── lib/
    │   │   │   ├── metrics.ts                  # ER rules, sums, followers-max reach
    │   │   │   └── csv.ts
    │   │   ├── store/reportFiltersSlice.ts     # category / platform / metric
    │   │   ├── types.ts
    │   │   └── pages/CampaignReportPage.tsx · PublicReportPage.tsx
    │   │
    │   ├── roster/
    │   │   ├── api/rosterApi.ts
    │   │   ├── components/
    │   │   │   ├── RosterTable.tsx · RosterRow.tsx
    │   │   │   ├── CampaignPicker.tsx
    │   │   │   ├── BulkPasteDialog.tsx · SheetImportDialog.tsx
    │   │   │   └── ResolveHandlesButton.tsx
    │   │   ├── hooks/useRoster.ts · useRosterMutations.ts · useSheetImport.ts
    │   │   ├── lib/
    │   │   │   ├── importSync.ts               # URL/platform/handle parsing + dedupe
    │   │   │   └── workbook.ts                 # SheetJS parsing
    │   │   ├── types.ts
    │   │   └── pages/RosterPage.tsx
    │   │
    │   ├── settings/
    │   │   ├── api/settingsApi.ts
    │   │   ├── components/ApifyTokenCard.tsx · AiKeyCard.tsx · TokenTestButton.tsx
    │   │   ├── hooks/useApifyToken.ts · useAiKey.ts · useAiStatus.ts
    │   │   └── pages/TokenPage.tsx
    │   │
    │   └── tracker/                            # legacy live dashboard (/tracker)
    │       ├── api/trackerApi.ts
    │       ├── components/SummaryKpis.tsx · TrendChart.tsx · PostsList.tsx
    │       │              KolDetailDrawer.tsx · GroupFilter.tsx
    │       ├── hooks/useSummary.ts · useTrend.ts · usePosts.ts · useKolDetail.ts
    │       └── pages/TrackerPage.tsx
    │
    ├── components/
    │   ├── ui/                                 # shadcn/ui generated primitives
    │   │   └── button · card · dialog · table · input · select · tabs · badge
    │   │       toast · skeleton · dropdown-menu · progress · tooltip · alert
    │   ├── layout/AppShell.tsx · NavBar.tsx · GlobalMenuScript.tsx
    │   └── common/
    │       ├── EChart.tsx                      # one ECharts wrapper (init/dispose/resize)
    │       ├── SegmentedControl.tsx            # replaces the `segs()` helper
    │       ├── StatCard.tsx · PlatformBadge.tsx · CategoryChip.tsx
    │       ├── CachedImage.tsx                 # /api/img proxy + onError hide
    │       ├── JobProgress.tsx · EmptyState.tsx · ErrorBoundary.tsx
    │
    ├── lib/
    │   ├── axios.ts              # instance + bearer interceptor + 401 -> /login
    │   ├── format.ts             # compact numbers (M/K), percent, locale
    │   ├── imageProxy.ts         # image-proxy URL builder
    │   ├── platforms.ts          # platform -> label + brand colour
    │   ├── colors.ts             # 16-colour palette + per-render category assignment
    │   ├── echarts.ts            # shared axis/grid theme
    │   ├── analytics.ts          # GA gtag
    │   └── utils.ts              # cn()
    │
    ├── hooks/usePolling.ts · useDebounce.ts · useMediaQuery.ts
    ├── types/api.ts · index.ts
    ├── config/env.ts · routes.ts                # route constants in ONE place
    └── styles/globals.css                       # Tailwind layers + CSS vars
```

### Route table — every legacy URL must survive

| URL                   | Component                     | Auth       |
| --------------------- | ----------------------------- | ---------- |
| `/`                   | `campaigns/HomePage`          | required   |
| `/c/:campaignKey`     | `report/CampaignReportPage`   | required   |
| `/v/:viewToken`       | `report/PublicReportPage`     | **public** |
| `/v/:slug/:viewToken` | `report/PublicReportPage`     | **public** |
| `/report`             | redirect → `/c/pao`           | required   |
| `/sahagroup`          | redirect → `/c/sahagroup`     | required   |
| `/sahagroup2027`      | redirect → `/c/sahagroup2027` | required   |
| `/tracker`            | `tracker/TrackerPage`         | required   |
| `/kols`               | `roster/RosterPage`           | required   |
| `/token`              | `settings/TokenPage`          | required   |
| `/login`              | `auth/LoginPage`              | public     |

---

## 3. `apps/api` — Express MVC backend

```
apps/api/
├── package.json
├── tsconfig.json
├── .env.example
└── src/
    ├── server.ts                 # bootstrap + listen + graceful shutdown
    ├── app.ts                    # express() + middleware chain + route mount
    │
    ├── config/
    │   ├── env.ts                # zod-validated process.env (fail fast on boot)
    │   ├── database.ts           # Drizzle/Prisma client + pool
    │   ├── logger.ts             # pino + request-id
    │   └── constants.ts          # lookback days, results per page, cost rates
    │
    ├── routes/
    │   ├── index.ts              # mounts /api/v1 + legacy /api aliases (§6.5)
    │   └── v1/
    │       ├── index.ts
    │       ├── health.routes.ts       # /health, /version
    │       ├── auth.routes.ts         # /auth/login, /auth/profile
    │       ├── campaigns.routes.ts    # CRUD + /summary + /view-token + /rename
    │       ├── report.routes.ts       # /data /refresh /profiles /packshot /pptx /tiein /cost
    │       ├── roster.routes.ts       # /bulk /sheet /sheet-fetch /resolve-handles
    │       ├── settings.routes.ts     # /token /token/test /ai/key /ai/status
    │       ├── media.routes.ts        # /img image cache proxy
    │       └── tracker.routes.ts      # /summary /trend /posts /kols/:u /scrape/*
    │
    ├── controllers/              # HTTP only: parse -> call service -> shape response
    │   ├── health.controller.ts · auth.controller.ts · campaigns.controller.ts
    │   ├── report.controller.ts · roster.controller.ts · settings.controller.ts
    │   ├── media.controller.ts  · tracker.controller.ts
    │
    ├── services/                # all business logic, no req/res
    │   ├── auth/wazzup.service.ts · tokenCache.service.ts
    │   ├── apify/apifyClient.service.ts · actors.ts
    │   ├── campaign/campaign.service.ts · viewToken.service.ts
    │   ├── report/
    │   │   ├── reportData.service.ts · refresh.service.ts · profiles.service.ts
    │   │   ├── aggregate.service.ts · cost.service.ts · packshot.service.ts
    │   ├── roster/roster.service.ts · sheetImport.service.ts · handleResolve.service.ts
    │   ├── media/imageCache.service.ts
    │   ├── pptx/pptxReport.service.ts          # ⚠ see §6.1
    │   ├── tiein/tiein.service.ts · frameSample.service.ts · vision.service.ts   # ⚠ §6.2
    │   ├── settings/appSettings.service.ts
    │   ├── tracker/scrape.service.ts · summary.service.ts · trend.service.ts
    │   └── jobs/jobRegistry.service.ts         # in-memory job status for long tasks
    │
    ├── repositories/            # SQL only — keeps services DB-agnostic
    │   ├── campaign.repo.ts · reportKol.repo.ts · reportPost.repo.ts
    │   ├── kolDaily.repo.ts · imageCache.repo.ts · appSettings.repo.ts
    │
    ├── middleware/
    │   ├── auth.middleware.ts          # bearer validation + OPEN-PATH allowlist (⚠ §6.4)
    │   ├── adminKey.middleware.ts      # X-ADMIN-KEY for scrape trigger
    │   ├── validate.middleware.ts      # zod (body/query/params)
    │   ├── requestLogger.middleware.ts
    │   ├── errorHandler.middleware.ts  # terminal handler, AppError -> JSON
    │   ├── notFound.middleware.ts
    │   ├── rateLimit.middleware.ts
    │   └── ssrfGuard.middleware.ts     # private/link-local/metadata IP blocking
    │
    ├── models/schema.ts                # Drizzle schema (or prisma/schema.prisma)
    ├── validators/*.validator.ts       # zod schemas, re-exported from packages/shared
    ├── utils/AppError.ts · asyncHandler.ts · httpClient.ts · dates.ts
    │
    ├── ssr/ogInjector.ts               # per-campaign <title>/OG into built HTML (⚠ §6.6)
    ├── static/spa.ts                   # serve apps/web/dist + SPA fallback
    │
    ├── db/
    │   ├── migrations/                 # generated; MUST be baselined (⚠ §6.3)
    │   └── seed/
    │       ├── cli.ts
    │       ├── seedCampaigns.ts · seedRoster.ts · seedPosts.ts · seedTracker.ts
    │       └── data/*.json             # the existing config/*.json, content unchanged
    │
    ├── jobs/dailyScrape.job.ts         # cron entry, replaces `python -m app.scrape`
    └── assets/
        ├── logos/{facebook,instagram,tiktok,youtube}.png
        └── report_template.pptx
```

---

## 4. File-by-file mapping — frontend

| Existing                  | Lines | Goes to                                                                                                                                                                                                                                                                                                                |
| ------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend/login.html`     | 95    | `features/auth/pages/LoginPage.tsx` + `LoginForm.tsx`                                                                                                                                                                                                                                                                  |
| `frontend/token.html`     | 167   | `features/settings/pages/TokenPage.tsx` + `ApifyTokenCard` / `AiKeyCard` / `TokenTestButton`                                                                                                                                                                                                                           |
| `frontend/home.html`      | 305   | `features/campaigns/pages/HomePage.tsx` + `CampaignGrid` / `CampaignCard` / 4 dialogs                                                                                                                                                                                                                                  |
| `frontend/index.html`     | 340   | `features/tracker/pages/TrackerPage.tsx` + `SummaryKpis` / `TrendChart` / `PostsList` / `KolDetailDrawer`                                                                                                                                                                                                              |
| `frontend/report.html`    | 446   | `features/report/**` — split per §2 (header, KPIs, breakdown, podium, 5 charts, table, CSV, 4 action buttons)                                                                                                                                                                                                          |
| `frontend/kols.html`      | 485   | `features/roster/**` — table, row editor, campaign picker, bulk paste, sheet import                                                                                                                                                                                                                                    |
| `frontend/auth.js`        | 278   | **split 4 ways:** `lib/axios.ts` (the `window.fetch` monkey-patch becomes a request interceptor) · `features/auth/lib/session.ts` (localStorage + URL-token handoff) · `features/auth/components/UserChip.tsx` (avatar/initials/dropdown/logout) · `features/auth/components/RequireAuth.tsx` (redirect-to-login gate) |
| `frontend/import-sync.js` | 172   | `features/roster/lib/importSync.ts` (URL normalise, platform detect, handle extract, post-id dedupe) + `workbook.ts` (SheetJS)                                                                                                                                                                                         |
| `frontend/logo.png`       | —     | `apps/web/public/logo.png`                                                                                                                                                                                                                                                                                             |

### Inline `<style>` blocks → `styles/globals.css`

Each page carries its own `<style>` with CSS variables (`--muted`, `--line`, …) and `.card` /
`.chip` / `.seg` / `.post-link` classes. These consolidate into Tailwind theme tokens +
`@layer components`, then shadcn/ui primitives take over (`.card` → `<Card>`, `.chip` → `<Badge>`,
`.seg` → `<SegmentedControl>`/`<Tabs>`).

### CDN scripts → npm dependencies

| Current CDN               | Becomes                                                               |
| ------------------------- | --------------------------------------------------------------------- |
| `cdn.tailwindcss.com`     | `tailwindcss` as a real build step (the CDN build is dev-only anyway) |
| `echarts@5.5.1`           | `echarts` npm + one `<EChart>` wrapper                                |
| `xlsx@0.18.5` (SheetJS)   | `xlsx` npm, imported only in the roster feature (code-split)          |
| `googletagmanager` gtag   | `lib/analytics.ts`, id from `VITE_GA_ID`                              |
| external `global-menu.js` | stays an external `<script defer>`; URL to `VITE_GLOBAL_MENU_URL`     |

### Cache-busting

`?v=73` / `?v=74` query strings disappear — Vite content-hashes every asset.

---

## 5. File-by-file mapping — backend (Python → Express)

| Existing                               | Lines   | Goes to                                                                                                                                                                                                 |
| -------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app/main.py`                          | 241     | `src/app.ts` (middleware chain) · `src/routes/v1/health.routes.ts` (`/version`) · `src/ssr/ogInjector.ts` (OG injection) · `src/static/spa.ts` (static + SPA fallback) · `src/db/seed/*` (startup seed) |
| `app/api/routes.py`                    | 1,198   | **split into 8 route files + 8 controllers**, business logic pushed down into `services/`                                                                                                               |
| `app/report_refresh.py`                | 1,204   | `services/report/refresh.service.ts` · `profiles.service.ts` · `cost.service.ts`                                                                                                                        |
| `app/pptx_report.py`                   | 678     | `services/pptx/pptxReport.service.ts` — **⚠ §6.1**                                                                                                                                                      |
| `app/tiein.py`                         | 540     | `services/tiein/{tiein,frameSample,vision}.service.ts` — **⚠ §6.2**                                                                                                                                     |
| `app/apify_client.py`                  | 317     | `services/apify/apifyClient.service.ts` + `actors.ts`                                                                                                                                                   |
| `app/queries.py`                       | 262     | `repositories/*.repo.ts`                                                                                                                                                                                |
| `app/aggregate.py`                     | 234     | `services/report/aggregate.service.ts`                                                                                                                                                                  |
| `app/models.py`                        | 226     | `models/schema.ts` (Drizzle) or `prisma/schema.prisma`                                                                                                                                                  |
| `app/seed.py`                          | 225     | `db/seed/{cli,seedCampaigns,seedRoster,seedPosts,seedTracker}.ts`                                                                                                                                       |
| `app/scrape.py`                        | 127     | `jobs/dailyScrape.job.ts` + `services/tracker/scrape.service.ts`                                                                                                                                        |
| `app/settings.py`                      | 102     | `services/settings/appSettings.service.ts` + `repositories/appSettings.repo.ts`                                                                                                                         |
| `app/auth.py`                          | 83      | `services/auth/wazzup.service.ts` + `tokenCache.service.ts` + `middleware/auth.middleware.ts`                                                                                                           |
| `app/config.py`                        | 69      | `config/env.ts` + `config/constants.ts`                                                                                                                                                                 |
| `app/db.py`                            | 47      | `config/database.ts`                                                                                                                                                                                    |
| `app/netguard.py`                      | 25      | `middleware/ssrfGuard.middleware.ts`                                                                                                                                                                    |
| `app/assets/logos/*.png`               | 4 files | `apps/api/src/assets/logos/`                                                                                                                                                                            |
| `app/assets/report_template.pptx`      | —       | `apps/api/src/assets/` — **⚠ §6.1**                                                                                                                                                                     |
| `config/*.json`                        | 5 files | `apps/api/src/db/seed/data/` — **content unchanged**                                                                                                                                                    |
| `migrations/` + `alembic.ini`          | 15 revs | `apps/api/src/db/migrations/` — **⚠ §6.3, must be baselined not recreated**                                                                                                                             |
| `scripts/seed_kols.py`                 | —       | `apps/api/src/db/seed/cli.ts`                                                                                                                                                                           |
| `scripts/dev_db.py`                    | 64      | `docker-compose.yml` (postgres service) — simpler than porting `pgserver`                                                                                                                               |
| `scripts/dev_fake_prevday.py`          | 99      | `apps/api/scripts/dev-fake-prevday.ts`                                                                                                                                                                  |
| `_report_test/build_report.py`         | 205     | **delete** — `HANDOFF.md` §2.3 says it is superseded by the real system                                                                                                                                 |
| `requirements*.txt`, `.python-version` | —       | **delete at cutover only**                                                                                                                                                                              |
| `Procfile`, `railway.json`             | —       | rewritten at cutover (§7 phase 6)                                                                                                                                                                       |
| `.env.example`                         | —       | split → `apps/api/.env.example` + `apps/web/.env.example`                                                                                                                                               |
| `README.md`, `HANDOFF.md`              | —       | updated at the end                                                                                                                                                                                      |

### API endpoint inventory (37 endpoints, all must be preserved)

| Group     | Endpoints                                                                                                                                                                                                                                                               |
| --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| auth      | `POST /auth/login` · `GET /auth/profile`                                                                                                                                                                                                                                |
| health    | `GET /health` · `GET /version`                                                                                                                                                                                                                                          |
| campaigns | `GET·POST /campaigns` · `GET /campaigns/summary` · `GET·PATCH·DELETE /campaigns/:key` · `GET /campaigns/:key/view-token` · `POST /campaigns/:key/rename`                                                                                                                |
| report    | `GET /report/data` · `POST /report/refresh` · `GET /report/refresh/status` · `POST /report/profiles` · `GET /report/profiles/status` · `GET·POST /report/packshot` · `GET /report/pptx` · `POST /report/tiein` · `GET /report/tiein/status` · `POST /report/cost/reset` |
| roster    | `POST /roster/report/bulk` · `GET /roster/report/sheet` · `GET /sheet/fetch` · `POST /resolve-handles`                                                                                                                                                                  |
| settings  | `GET·POST /token` · `POST /token/test` · `GET·POST /ai/key` · `GET /ai/status`                                                                                                                                                                                          |
| media     | `GET /img`                                                                                                                                                                                                                                                              |
| tracker   | `GET /summary` · `GET /trend` · `GET /posts` · `GET /kols/:username` · `POST /scrape/run` · `GET /scrape/inspect`                                                                                                                                                       |

---

## 6. Things that will break if handled carelessly

### 6.1 PPTX generation — the single biggest risk

`app/pptx_report.py` (678 lines) uses **python-pptx** and reads
`app/assets/report_template.pptx` as a real template. Node has no equivalent: `pptxgenjs`
builds decks from scratch and **cannot open an existing .pptx as a template**. Porting means
rebuilding the deck layout by hand and visually diffing against current output — expensive, and
the most likely place for silent regressions.

### 6.2 AI tie-in job

`app/tiein.py` (540 lines) does: Apify video download → **bundled ffmpeg** (`imageio-ffmpeg`)
samples ~8 frames per video → **Claude vision** picks the frame best showing the product →
cache. Portable to Node, but the ffmpeg binary has to be provisioned on Railway explicitly
(`imageio-ffmpeg` ships it today; `ffmpeg-static` is the Node equivalent).

### 6.3 Alembic → a Node ORM, against a LIVE database

15 revisions are already applied to production Postgres. A fresh `prisma migrate dev` /
`drizzle-kit push` will try to **create or drop tables that already hold real data**.
The only safe route: introspect the existing schema (`prisma db pull` / `drizzle-kit introspect`),
commit that as revision 0, and mark it **already applied** (baseline). No destructive migration
ever runs against prod.

### 6.4 The auth open-path allowlist

`app/main.py:30-48` allowlists which `/api/*` paths skip bearer auth — because the **public
client links `/v/<token>` must work with no login**. The list is subtle (prefix matches, an exact
set, plus a regex allowing `GET /api/campaigns/<key>` so the view page can read its title).
Port it as data, verbatim, with a test per entry. Get this wrong in either direction and you
either break every client link or leak the whole API.

### 6.5 API versioning vs. existing clients

The API is currently unversioned (`/api/*`). Introducing `/api/v1/*` means, during migration,
mounting the **same router at both paths** and only dropping `/api/*` once nothing calls it.

### 6.6 Server-rendered OG tags — silently lost by a plain SPA

`_report_with_og()` (`app/main.py:115`) rewrites `<title>` and injects `og:title` /
`og:description` / `twitter:card` **server-side**, specifically because LINE / Messenger /
Facebook crawlers **do not run JavaScript**. A stock Vite SPA returns one static shell → every
shared report link loses its preview. This is a real functionality loss that no amount of
client-side `document.title` fixes.
Fix: keep an Express route that reads `dist/index.html`, injects the per-campaign meta, and
returns it — plus the `window.__CAMPAIGN__` bootstrap that `/v/:token` pages depend on.

### 6.7 Redux Toolkit _and_ Zustand

Both were requested for global client state; they overlap. Recommended split, so no two tools
own the same data:

- **TanStack Query** — _all_ server data. No API responses in Redux or Zustand.
- **Redux Toolkit** — cross-cutting client session: auth token, user, roles, theme.
- **Zustand** — ephemeral per-view UI: report filters, table sort, dialog open state.

If you would rather not run two state libraries, drop Zustand and put filters in RTK slices —
say so and I will collapse it.

### 6.8 Smaller items

- `auth.js` monkey-patches `window.fetch` globally → becomes an Axios interceptor. Anything still
  using bare `fetch` (e.g. blob downloads for PPTX/CSV) must be moved onto the Axios instance or
  it silently loses its auth header.
- Long jobs (refresh / profiles / tie-in) track status **in process memory**. On Railway with >1
  replica or a restart mid-job, status is lost. Same limitation today — worth noting, not fixing
  as part of this migration unless you want it fixed.
- `POST /scrape/run` is auth-open but gated by `X-ADMIN-KEY`. Keep it that way.

---

## 7. Incremental migration order

Nothing here is a cutover; each phase ends with the app fully working.

| Phase | Work                                                                                                                                                                                                  | Risk     |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| **0** | pnpm workspace, tsconfig, ESLint/Prettier, path aliases, `packages/shared`. FastAPI untouched.                                                                                                        | none     |
| **1** | Scaffold `apps/web` (Vite/React/TS/Tailwind/shadcn). Build into a dir FastAPI serves. Port `lib/*` + auth + **TokenPage** (167 lines, smallest). Verify against prod behaviour.                       | low      |
| **2** | Port pages in risk order: Login → Home/campaigns → Roster → Tracker → **Report last**. Legacy HTML deleted per page only after its React version is verified.                                         | low–med  |
| **3** | Move OG injection to read the built `index.html`. Verify link previews in LINE + Messenger before deleting the old path.                                                                              | **med**  |
| **4** | Scaffold `apps/api` Express in front of FastAPI as a **proxy**. Port endpoints group by group — reads first (`/report/data`, `/campaigns`, `/img`), then mutations, then jobs. DB baselined per §6.3. | med–high |
| **5** | PPTX + tie-in last — or keep them in a small Python sidecar (see §8).                                                                                                                                 | **high** |
| **6** | Retire FastAPI: delete `app/`, `requirements*.txt`, `.python-version`; rewrite `Procfile` + `railway.json`; update `README.md` + `HANDOFF.md`.                                                        | med      |

Phases 0–3 deliver the entire frontend modernisation with the backend untouched. Everything
genuinely risky lives in 4–6.

---

## 8. One decision needed before code

Phases 4–6 rewrite 5,578 lines of working, deployed Python. Three options:

**A. Full Express rewrite** — everything in Node, `app/` deleted.
Matches the request exactly. Highest cost and highest regression risk, concentrated in PPTX
(§6.1) and tie-in (§6.2).

**B. Express API + thin Python sidecar** _(recommended if you want Express)_
Express owns all 37 endpoints, MVC, validation, logging, error handling. PPTX + tie-in stay a
small Python service Express calls — they are the two pieces where Python libraries
(`python-pptx`, ffmpeg tooling) have no real Node equivalent. ~85% of the backend becomes
Express; the 1,200 riskiest lines stay working code.

**C. Frontend only** — full Vite/React/TS/Tailwind/shadcn migration, FastAPI kept as-is.
Delivers the entire visible modernisation with near-zero regression risk, and no backend rewrite.

**Which one?** The frontend plan (§2, §4) is identical in all three, so I can start Phase 0–1
immediately either way — the answer only changes phases 4–6.
