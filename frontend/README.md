# Shortpay frontend

A React/Vite freight-audit interface served by a small Flask backend-for-frontend
(BFF). Flask serves the React application and proxies UI requests; extraction,
matching, money calculations, policy, and decisions remain in `backend/`.

## Run locally

From the repository root, install and build the React assets once:

```powershell
Set-Location frontend/web
npm install
npm run build
Set-Location ../..
```

Start FastAPI:

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

For React development with hot reload, run the Flask BFF first and then start
Vite in another terminal. Vite proxies `/api/ui/*` to Flask on port 5000.

```powershell
Set-Location frontend/web
npm run dev
```

Open the Vite URL shown in the terminal. The dev server uses base path `/static/react/`.

## Structure

- `__init__.py`: Flask application factory.
- `routes.py`: React shell routes plus JSON BFF endpoints.
- `services/shortpay_api.py`: the only module that talks to FastAPI.
- `templates/app.html`: the React application shell.
- `web/`: Vite source, including the React interface and styles.
- `static/react/`: generated production assets (not committed; run `npm run build`).
- `tests/`: isolated BFF behavior tests with a fake FastAPI client.
