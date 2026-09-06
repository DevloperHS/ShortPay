# 4. Vite React SPA with Flask BFF

- **Status**: Accepted
- **Date**: 2026-09-06
- **Supersedes**: the Next.js frontend named in ADR 0001 and ADR 0002

## Context

ADR 0001 split the repo so a teammate could ship Next.js against the FastAPI contract. The specialist UI that landed is a Vite React application served by Flask. Flask owns cookies, static files, and `/api/ui/*` proxies. React never calls FastAPI directly. That keeps HITL from posting a typed payable, and it keeps CORS off the demo path.

## Decision

1. Keep FastAPI as the domain HTTP API on port 8000.
2. Serve the specialist UI from Flask on port 5000. `GET /` and `GET /cases/<invoice_id>` return `templates/app.html`, which mounts `frontend/static/react/`.
3. Build the UI with Vite from `frontend/web/`. Production assets live under `frontend/static/react/`.
4. React talks only to `/api/ui/*`. Flask translates those calls to FastAPI `/api/cases`, `/api/cases/{id}`, `/api/decide`, and `/api/ingest/invoice`.
5. Approve short-pay sends the payable shown on screen as `expected_payable_cents`. The matcher still rejects a stale amount. Flask does not replace that number with a live GET.

## Consequences

- ADR 0001's directory split still holds. `backend/` owns money. `frontend/` owns presentation.
- Docs and CORS comments that still say Next.js are stale. This ADR is the stack of record.
- A clone needs `npm run build` in `frontend/web` before Flask can serve a working UI. Built assets are gitignored.
