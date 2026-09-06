# 2. FastAPI REST Endpoints & JSON Schema for Next.js Frontend

- **Status**: Accepted
- **Date**: 2026-09-06

## Context
The Next.js frontend needs to render the Kanban board columns, render the detail modal with fact comparison grids, and submit short-pay / pay-as-billed actions.

## Decision
Build a FastAPI web server in `backend/main.py` with CORS enabled (`CORSMiddleware`) and the following endpoints:

1. `POST /api/ingest`: Reads fixture files / baseline CSVs and ingests contract terms, facility facts, dock logs, and invoice facts into `AuditOffice`.
2. `GET /api/cases`: Returns an array of Kanban case cards formatted according to `fixtures/hero_expected.json`.
3. `GET /api/cases/{invoice_id}`: Returns detailed audit case ledgers, expected lines, variance calculations, and dispute breakdown for the Math Grid Modal.
4. `POST /api/decide`: Receives decision payloads (`ApproveShortPay` or `OverridePayAsBilled`) and posts expected payable or override to `AuditOffice`.

## Consequences
- Clean, decoupled contract between Python backend and Next.js frontend.
- Frontend developer ("Shubhu") can mock or connect directly to `http://localhost:8000/api/cases`.
