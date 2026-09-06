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
3. **2-Tier Resilient LLM Extraction**: Invoice PDFs/text are parsed using **TensorMux** (`glm-4-7-flash`) primary, with automatic fallback to **Groq** (`qwen/qwen3.6-27b`).
4. **Neatlogs Observability**: Every extraction, match calculation, and human decision emits audit-compliant log spans and SHA-256 evidence hashes (`trace-freight-shp-88220`) to the **Neatlogs** dashboard.
5. **Maximor Autonomy Loop**: Auto-closes overbills $\le \$50.00$ (`SHORT-PAY-01`) only after a human has approved those specific rules on the lane.

---

## 🚀 Quickstart Guide for Backend & Frontend Engineers

### 1. Prerequisites

- Python 3.11 or higher
- Git

### 2. Installation & Setup

Clone the repository and set up a Python virtual environment:

```bash
# Clone the repository
git clone https://github.com/shubhu121/pstack-prd.git
cd pstack-prd

# Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
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

# Neatlogs Observability Tracing Gateway
NEATLOGS_API_KEY=your_neatlogs_api_key_here
NEATLOGS_ENDPOINT=https://api.neatlogs.com/v1/traces
```

---

## 🧪 Verification & Running Tests

Run the full pytest test suite to verify the hero case, REST API endpoints, and LLM extractions:

```bash
# Set PYTHONPATH to backend directory
# On Windows PowerShell:
$env:PYTHONPATH="backend"; pytest backend/tests

# On Linux/macOS:
PYTHONPATH=backend pytest backend/tests
```

*Expected Result: `5 passed in 1.45s`*

---

## 🌐 Launching the REST API Server

Launch the FastAPI Uvicorn server (CORS is enabled for Next.js frontend on `http://localhost:3000`):

```bash
# Run from project root
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The server will automatically auto-ingest baseline fixtures on startup and serve API documentation at `http://localhost:8000/docs`.

---

## 🔌 API Endpoint Reference for Next.js Frontend

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/ingest` | Triggers auto-ingestion of baseline CSVs, facility masters, dock logs, and carrier invoices. |
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
