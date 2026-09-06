# Shortpay frontend

A small server-rendered Flask interface for the Shortpay FastAPI backend. Flask
owns presentation only; extraction, matching, money calculations, policy, and
decisions remain in `backend/`.

## Run locally

From the repository root, start FastAPI:

```powershell
$env:PYTHONPATH="backend"
uv run uvicorn main:app --app-dir backend --port 8000
```

In a second terminal, start Flask:

```powershell
uv sync
uv run python -m frontend
```

Open `http://127.0.0.1:5000`. Set `SHORTPAY_API_URL` to use a FastAPI service
running somewhere other than `http://127.0.0.1:8000`.

## Structure

- `__init__.py`: Flask application factory and template filters.
- `routes.py`: board, case review, ingestion, and decision routes.
- `services/shortpay_api.py`: the only module that talks to FastAPI.
- `templates/`: server-rendered product views.
- `static/`: presentation styles.
- `tests/`: isolated UI behavior tests with a fake FastAPI client.
