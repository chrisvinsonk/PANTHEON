# THE PANTHEON — Frontend (COMPANY_OS_RE_FE)

React + Vite divine council interface for the THE PANTHEON backend. Consumes the
`/api` endpoints (health, executives, board meetings, decisions) and provides the
council chamber, executive oracle profiles, and conclave archive views.

## Included
- React 18 + Vite dev server
- Council chamber: create meetings, run deliberations, record Founder decisions
- Executive oracles: CEO / CFO / CTO / CSO profiles and mandates
- Conclaves archive: meeting list with status and decision history
- Vite proxy routes `/api` to the backend (default `http://127.0.0.1:8000`)

## Requirements
- Node.js 20+
- Backend running at the configured API base URL (see `.env`)

## Quick start

```bash
# Install dependencies
npm install

# Create the environment file from the example
cp .env.example .env
# Edit .env if the backend runs on a different host/port.

# Start the dev server
npm run dev
```

Open http://localhost:5173

## Environment variables
Copy `.env.example` to `.env` and adjust as needed. Vite exposes variables prefixed
with `VITE_` to client code and to the dev-server proxy.

| Variable | Purpose | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Base URL of the THE PANTHEON backend | `http://127.0.0.1:8000` |
| `VITE_APP_NAME` | App display name | `THE PANTHEON` |

The dev server proxies `/api` to `VITE_API_BASE_URL`, so the frontend makes relative
`/api/...` requests that are forwarded to the backend.

## Connecting to the backend
1. Start the backend repo (`COMPANY_OS_PY_BE`) on port 8000.
2. Ensure `VITE_API_BASE_URL=http://127.0.0.1:8000` in frontend `.env` (default).
3. Run `npm run dev` here and open http://localhost:5173.

## Production build
```bash
npm run build      # output to dist/
npm run preview    # serve the production build locally
```

### Deploying the frontend to Render
For a Render Web Service, use:

- Build command: `npm ci && npm run build`
- Start command: `npm start`

The start command serves the built app on `0.0.0.0` and uses Render's `PORT`.
Set `VITE_API_BASE_URL` to `https://company-os-py-be.onrender.com` and set
`VITE_CLERK_PUBLISHABLE_KEY` in the Render service environment before building.
Vite embeds `VITE_` variables at build time.

After deployment, allow the frontend's exact `https://<frontend-service>.onrender.com`
origin in the backend's `API_CORS_ORIGINS` and in Clerk's allowed origins.

### Clerk redirect configuration
Clerk must know every origin the app is served from, otherwise it falls back to a
different one (this is what sent the production sign-in callback to
`http://localhost:5174`).

1. In the Clerk Dashboard, open **Configure → Paths** (development instances) or
   **Domains** (production instances) and add the deployed origin, e.g.
   `https://company-os-re-fe.onrender.com`, plus the local origins used in
   development (`http://localhost:5174`, `http://127.0.0.1:5174`).
2. The app derives every auth URL from `window.location.origin` (`src/auth.js`),
   so a deployed build always returns to the host that served it:
   - `signInUrl` / `signUpUrl` are pinned to this origin, which keeps the OAuth
     callback here instead of on Clerk's hosted Account Portal.
   - `/sign-in`, `/sign-up` and `/sso-callback` are rendered by `src/App.jsx`
     (including the `/sign-in#/sso-callback` form Clerk emits).
3. Do not rely on the instance **Home URL** for the callback: on a development
   instance the API accepts `PATCH /v1/instance` with `home_url` but Clerk does
   not persist it, so it is re-derived from the request origin.

A `pk_test_…` key means the app is using a Clerk *development* instance. For a
real production deployment, create a production instance and swap in its
`pk_live_…` key; development instances are limited to 100 users and use Clerk's
development OAuth proxy.