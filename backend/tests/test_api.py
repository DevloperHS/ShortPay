import pytest
from fastapi.testclient import TestClient
import main
from main import app
from pdf_support import make_text_pdf
from shortpay.adapters.invoice_extract import ExtractionOutcome
from shortpay.evidence import ChargeType, InvoiceFact, InvoiceLine

client = TestClient(app)


def test_api_auto_ingest_and_cases():
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    hero = next(case for case in data if case["invoice_id"] == "INV-FRT-2026-09")
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
    assert res["erp_proposal"]["authorized_amount_cents"] == 92500
    assert res["dispute_packet"]["disputed_total_cents"] == 19500
    assert "dock_receipt_SHP-88220.pdf" in res["dispute_packet"]["attached_evidence"]


def test_api_surfaces_ocean_skip_reason():
    response = client.get("/api/cases")
    assert response.status_code == 200
    ocean = next(case for case in response.json() if case["shipment_id"] == "SHP-88219")
    assert ocean["disposition"] == "SkippedOutOfScope"
    assert ocean["kanban"]["column"] == "Out of scope"
    assert "OCEAN" in ocean["skip_reason"]


def test_api_rejects_blank_pay_as_billed_reason():
    response = client.post(
        "/api/decide",
        json={
            "invoice_id": "INV-FRT-2026-09",
            "shipment_id": "SHP-88220",
            "action_type": "OverridePayAsBilled",
            "override_reason": "   ",
        },
    )
    assert response.status_code == 422


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


def _hero_fact() -> InvoiceFact:
    return InvoiceFact(
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


def test_pdf_ingest_parses_text_then_matches(monkeypatch):
    captured = {}

    def fake_extract(text):
        captured["text"] = text
        return ExtractionOutcome(
            fact=_hero_fact(),
            provider="TensorMux",
            model_name="glm-4-7-flash",
        )

    monkeypatch.setattr(main, "extract_invoice_with_fallback_details", fake_extract)
    pdf = make_text_pdf(
        "FedEx Freight INV-FRT-2026-09 SHP-88220 BOL-US-99121 "
        "base freight 850.00 detention 175.00 liftgate 95.00"
    )

    response = client.post(
        "/api/ingest/invoice-pdf",
        files={"invoice_pdf": ("hero.pdf", pdf, "application/pdf")},
    )

    assert response.status_code == 200
    result = response.json()
    assert "INV-FRT-2026-09" in captured["text"]
    assert "SHP-88220" in captured["text"]
    assert result["provider"] == "TensorMux"
    assert result["billed_cents"] == 112000
    assert result["expected_cents"] == 92500
    assert result["dispute_cents"] == 19500


def test_pdf_ingest_rejects_non_pdf_filename(monkeypatch):
    monkeypatch.setattr(
        main,
        "extract_invoice_with_fallback_details",
        lambda _: (_ for _ in ()).throw(AssertionError("extractor should not run")),
    )
    response = client.post(
        "/api/ingest/invoice-pdf",
        files={"invoice_pdf": ("notes.txt", b"not a pdf", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "PDF only"


def test_pdf_ingest_rejects_unreadable_pdf(monkeypatch):
    monkeypatch.setattr(
        main,
        "extract_invoice_with_fallback_details",
        lambda _: (_ for _ in ()).throw(AssertionError("extractor should not run")),
    )
    response = client.post(
        "/api/ingest/invoice-pdf",
        files={"invoice_pdf": ("hero.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 400
    assert "not a PDF" in response.json()["detail"]
