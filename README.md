# Shortpay 🚚💰

> **Pre-Pay Freight Surcharge Audit for the Autonomous Office of the CFO**  
> *Track 2 — Syndicate by Maximor Hackathon*

Shortpay is the AP desk that audits carrier accessorials **before the money leaves**. A logistics controller uploads the rate baseline. Carrier PDFs, IoT dock timestamps, and facility facts land beside them. Shortpay matches each LTL or TL invoice, computes an authorized payable in integer cents via a pure mathematical engine, and either auto-closes under policy or presents a single intuitive math grid for human controller approval.

- **PRD Specification**: [docs/prd.md](docs/prd.md)
- **Architecture**: [docs/architecture.md](docs/architecture.md)
- **Sponsor Integration ADR**: [docs/adr/0003-pydantic-ai-and-sponsor-adapters.md](docs/adr/0003-pydantic-ai-and-sponsor-adapters.md)

---

## 🌟 Core Highlights

1. **Integer-Cent Monetary Standard**: Zero floating-point math on financial paths (`$925.00` = `92500` cents). Zero rounding errors.
2. **Pure Math Engine**: Financial math has **zero LLM dependency**. The matcher function `match_evidence()` is a pure function.
3. **2-Tier Resilient LLM Extraction**: Invoice text is parsed using **TensorMux** (`glm-4-7-flash`) primary, with automatic fallback to **Groq** (`qwen/qwen3.8-27b`).
4. **Neatlogs Observability**: Every extraction, match calculation, and human decision emits audit-compliant log spans and SHA-256 evidence hashes (`trace-freight-shp-88220`) to the **Neatlogs** dashboard.
5. **Maximor Autonomy Loop**: Auto-closes overbills $\le \$50.00$ (`SHORT-PAY-01`) only after a human has approved those specific rules on the lane.
6. **Sponsor Request Guardrail**: TensorMux and Groq are each limited to 60 outbound HTTP attempts per rolling 60-second window, including retries and concurrent calls.

---

## 🚀 Quickstart Guide for Backend & Frontend Engineers

### 1. Prerequisites

- Python 3.11 or higher
- Git

### 2. Installation & Setup

Clone the repository and install the locked environment with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```bash
# Clone the repository
git clone https://github.com/DevloperHS/parakh.git
cd parakh

uv sync
```

### 3. Environment Configuration

Copy `.env.example` to `backend/.env` and add your sponsor API keys:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:

```env
# TensorMux Primary LLM Gateway
TENSORMUX_API_KEY=your_tensormux_api_key_here
TENSORMUX_BASE_URL=https://api.tensormux.com/v1

# Groq Secondary Fallback LLM Gateway (Free Tier)
GROQ_API_KEY=your_groq_api_key_here
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=qwen/qwen3.8-27b

# Neatlogs Observability Tracing Gateway
NEATLOGS_API_KEY=your_neatlogs_api_key_here
NEATLOGS_ENDPOINT=https://ingest.neatlogs.com
```

---

## 🧪 Verification & Running Tests

Run the full pytest test suite to verify the hero case, REST API endpoints, and LLM extractions:

```bash
# Set PYTHONPATH to backend directory
# On Windows PowerShell:
$env:PYTHONPATH="backend"; uv run pytest backend/tests

# On Linux/macOS:
PYTHONPATH=backend pytest backend/tests
```

Live sponsor verification is opt-in and calls the configured external endpoints:

```bash
$env:PYTHONPATH="backend"; uv run pytest --live-sponsors backend/tests
```

---

## 🌐 Launching the REST API Server

Launch the FastAPI backend:

```bash
# Run from project root
uv run uvicorn main:app --app-dir backend --reload --port 8000
```

The server will automatically auto-ingest baseline fixtures on startup and serve API documentation at `http://localhost:8000/docs`.

Build the React UI, then launch the Flask BFF in a second terminal:

```bash
cd frontend/web
npm install
npm run build
cd ../..
uv run python -m frontend
```

The UI is available at `http://localhost:5000` and connects to the FastAPI backend on port 8000.

---

## API endpoint reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/ingest` | Triggers auto-ingestion of baseline CSVs, facility masters, dock logs, and carrier invoices. |
| `POST` | `/api/ingest/invoice` | Extracts invoice text through TensorMux with Groq fallback, then optionally matches it. |
| `GET` | `/api/cases` | Returns all Kanban cases categorized into columns (`Major exceptions`, `Auto-closed`, `Short-paid`, `Paid as billed`, `Out of scope`). |
| `GET` | `/api/cases/{invoice_id}` | Retrieves detailed math grid facts, line item variances, and current disposition for a single case. |
| `POST` | `/api/decide` | Submits human controller action (`ApproveShortPay` or `OverridePayAsBilled`). Proposes ERP posting & dispute notice. |

### Example Request: Approve Short-Pay ($925.00)

`POST /api/decide`

```json
{
  "invoice_id": "INV-FRT-2026-09",
  "shipment_id": "SHP-88220",
  "action_type": "ApproveShortPay",
  "expected_payable_cents": 92500
}
```

---

## 🎯 Hero Case (`SHP-88220`) Reference Math

- **Carrier**: FedEx Freight
- **Invoice**: `INV-FRT-2026-09` / **BOL**: `BOL-US-99121`
- **Facts**:
  - Destination facility has standard loading dock (`destination_has_dock = True`) $\rightarrow$ Liftgate not authorized ($0.00). Billed $95.00.
  - Dock arrival `14:12`, departure `15:45` (93 minutes total dwell). Contract free time is 30 min $\rightarrow$ 63 min billable dwell $\rightarrow$ 1 completed hour at $75/hr $\rightarrow$ Authorized detention $75.00. Billed $175.00.
- **Summary**:
  - Total Billed: **$1,120.00** (`112000`¢)
  - Authorized Payable: **$925.00** (`92500`¢)
  - Dispute Amount: **$195.00** (`19500`¢)

---

## Repository description

Evidence-backed freight invoice auditing with TensorMux/Groq extraction and deterministic integer-cent matching for accurate short-pay decisions.
