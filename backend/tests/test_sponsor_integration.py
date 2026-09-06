import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
pytestmark = pytest.mark.integration

INVOICE_TEXT = """
Carrier invoice INV-FRT-2026-09 from FedEx Freight for shipment SHP-88220,
BOL BOL-US-99121. Charges: base freight $850.00; driver detention $175.00
for 60 minutes; liftgate delivery service $95.00. Total billed $1,120.00.
""".strip()


def _require_sponsor_key(name: str) -> None:
    if not os.getenv(name):
        pytest.skip(f"{name} is required for live sponsor integration tests")


def test_real_tensormux_endpoint_extracts_invoice():
    _require_sponsor_key("TENSORMUX_API_KEY")
    from shortpay.adapters.invoice_extract import extract_invoice_with_fallback_details

    outcome = extract_invoice_with_fallback_details(INVOICE_TEXT)

    assert outcome.provider == "TensorMux"
    assert outcome.fact.invoice_id == "INV-FRT-2026-09"
    assert outcome.fact.shipment_id == "SHP-88220"
    assert outcome.fact.total_billed_cents == 112000


def test_real_groq_fallback_endpoint_extracts_invoice(monkeypatch):
    _require_sponsor_key("GROQ_API_KEY")
    from shortpay.adapters.invoice_extract import extract_invoice_with_fallback_details

    monkeypatch.delenv("TENSORMUX_API_KEY", raising=False)
    outcome = extract_invoice_with_fallback_details(INVOICE_TEXT)

    assert outcome.provider == "Groq"
    assert outcome.fact.invoice_id == "INV-FRT-2026-09"
    assert outcome.fact.shipment_id == "SHP-88220"
    assert outcome.fact.total_billed_cents == 112000


def test_real_sponsor_ingest_endpoint_runs_full_audit():
    _require_sponsor_key("TENSORMUX_API_KEY")
    from main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/ingest/invoice",
            json={"raw_invoice_text": INVOICE_TEXT, "auto_match": True},
        )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["provider"] == "TensorMux"
    assert result["billed_cents"] == 112000
    assert result["expected_cents"] == 92500
    assert result["dispute_cents"] == 19500
    assert result["disposition"] == "NeedsReview"


def test_real_neatlogs_authenticated_probe():
    _require_sponsor_key("NEATLOGS_API_KEY")
    from shortpay.neatlogs import _neatlogs_base_url

    doctor_env = os.environ.copy()
    doctor_env["NEATLOGS_ENDPOINT"] = _neatlogs_base_url(
        doctor_env.get("NEATLOGS_ENDPOINT")
    )
    completed = subprocess.run(
        [sys.executable, "-m", "neatlogs", "doctor", "--probe", "--json"],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=doctor_env,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    report = json.loads(completed.stdout)
    assert report["format_version"] == "neatlogs.doctor/v2"
    assert report["runtime"]["schema_version"] == "2"
    assert report["status"] == "pass"
    assert report["probe"]["visible"] is True
    assert report["probe"]["finalized"] is True
