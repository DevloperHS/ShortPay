# 1. Python FastAPI Backend & Next.js Frontend Repository Split

- **Status**: Accepted
- **Date**: 2026-09-06

## Context
We are building a hackathon product ("Shortpay") for Track 2 (Autonomous Office of the CFO) with a strict deadline of 9:00 PM IST today. The core product logic requires pure mathematical evaluation of freight accessorials, integer-cent calculations, and policy execution. 

The frontend will be developed by a teammate ("Shubhu") using Next.js, while the core domain engine and API will be developed in Python.

## Decision
1. **Separate Directory Structure**:
   - `backend/`: Python pure domain engine (`shortpay/` package) + FastAPI REST endpoints exposing `ingest`, `match`, `decide`, and `cases`.
   - `frontend/`: Next.js Web application for the specialist Kanban board and Math Grid modal.
2. **Backend Architecture**:
   - Strict Python 3.11+ using Pydantic `BaseModel` for validated domain models and schemas.
   - Money represented strictly as integer cents (`Money.cents`).
   - Pure function matching logic (`match_evidence`).
   - FastAPI endpoints to serve Next.js frontend requirements.

## Consequences
- Clean separation of concerns between domain calculation rules and UI presentation.
- Next.js frontend can query REST API endpoints (`/api/cases`, `/api/decide`, `/api/ingest`) and render Kanban cards.
- The Python domain core can be 100% verified via Pytest unit tests independently of the frontend.
