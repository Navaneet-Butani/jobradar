# JobRadar — web

Next.js (App Router) frontend for JobRadar. See the repo root `README.md` for
what the product is, and `docs/self-hosting.md` for deployment.

## Local development

The backend must be running first (`uvicorn app.main:app --port 8000` from the
repo root), because every page is server-rendered against it.

```bash
npm install
npm run dev          # http://localhost:3000
```

## Environment

| Variable | Where | Purpose |
|---|---|---|
| `API_BASE_URL` | server only | Backend origin. Defaults to `http://localhost:8000`. Set this in Vercel to the Render API URL. |

There is deliberately no `NEXT_PUBLIC_*` API variable: the browser never talks
to the backend directly. Pages and Route Handlers call it server-side with the
session cookie, so the JWT stays httpOnly and the API origin isn't exposed.

## Structure

```
app/(dashboard)/      feed · search · job detail · profile · tracker · outreach
app/api/              Route Handlers — proxy client mutations, refresh tokens
components/           shared UI; components/outreach/* is the outreach surface
lib/backend.ts        authedFetch: cookie auth + token refresh
lib/session.ts        server-side data fetching for pages
proxy.ts              redirects unauthenticated requests to /login
```
