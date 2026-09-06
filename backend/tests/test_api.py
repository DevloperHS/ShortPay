import pytest
from fastapi.testclient import TestClient
import main
from main import app
from shortpay.adapters.invoice_extract import ExtractionOutcome
from shortpay.evidence import ChargeType, InvoiceFact, InvoiceLine

client = TestClient(app)


def test_api_auto_ingest_and_cases():
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    hero = data[0]
    assert hero["invoice_id"] == "INV-FRT-2026-09"
    assert hero["shipment_id"] == "SHP-88220"
    assert hero["billed_cents"] == 112000
    assert hero["expected_cents"] == 92500
    assert hero["dispute_cents"] == 19500
    assert hero["disposition"] == "NeedsReview"
    assert hero["kanban"]["column"] == "Major exceptions"


def test_api_case_detail():
    response = client.get("/api/cases/INV-FRT-2026-09")
    assert response.status_code == 200
    detail = response.json()
    assert detail["dwell_minutes"] == 93
    assert detail["billable_detention_minutes"] == 63
    assert detail["completed_detention_hours"] == 1
    assert len(detail["lines"]) == 3


def test_api_decide_shortpay():
    decide_payload = {
        "invoice_id": "INV-FRT-2026-09",
        "shipment_id": "SHP-88220",
        "action_type": "ApproveShortPay",
        "expected_payable_cents": 92500,
    }
    response = client.post("/api/decide", json=decide_payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "success"
    assert res["new_disposition"] == "ShortPaid"
    assert res["approved_payable_cents"] == 92500


def test_sponsor_ingest_route_connects_extraction_to_matcher(monkeypatch):
    extracted = InvoiceFact(
        invoice_id="INV-FRT-2026-09",
        shipment_id="SHP-88220",
        carrier_name="FedEx Freight",
        bill_of_lading="BOL-US-99121",
        lines=(
            InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
            InvoiceLine(
                charge_type=ChargeType.DETENTION,
                amount_cents=17500,
                billed_minutes=60,
            ),
            InvoiceLine(charge_type=ChargeType.LIFTGATE, amount_cents=9500),
        ),
    )
    monkeypatch.setattr(
        main,
        "extract_invoice_with_fallback_details",
        lambda _: ExtractionOutcome(
            fact=extracted,
            provider="TensorMux",
            model_name="glm-4-7-flash",
        ),
    )

    response = client.post(
        "/api/ingest/invoice",
        json={"raw_invoice_text": "synthetic invoice", "auto_match": True},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["provider"] == "TensorMux"
    assert result["billed_cents"] == 112000
    assert result["expected_cents"] == 92500
    assert result["dispute_cents"] == 19500
