import io

import pytest

from frontend import create_app
from frontend.services.shortpay_api import ShortpayAPIError


CASE = {
    "invoice_id": "INV-FRT-2026-09",
    "shipment_id": "SHP-88220",
    "carrier_name": "FedEx Freight",
    "bill_of_lading": "BOL-US-99121",
    "billed_cents": 112000,
    "expected_cents": 92500,
    "dispute_cents": 19500,
    "disposition": "NeedsReview",
    "dwell_minutes": 93,
    "billable_detention_minutes": 63,
    "completed_detention_hours": 1,
    "lines": [
        {
            "charge_type": "DETENTION",
            "billed_cents": 17500,
            "expected_cents": 7500,
            "explanation": "1 completed detention hour at the contract rate",
        },
        {
            "charge_type": "LIFTGATE",
            "billed_cents": 9500,
            "expected_cents": 0,
            "explanation": "Destination facility has a standard dock",
        },
    ],
    "kanban": {
        "column": "Major exceptions",
        "subtitle": "Overbilled by $195.00 (Liftgate + Detention)",
    },
}


class FakeShortpayAPI:
    def __init__(self):
        self.decisions = []
        self.ingested_text = None
        self.ingested_pdf = None

    def list_cases(self):
        return [CASE]

    def get_case(self, invoice_id):
        assert invoice_id == CASE["invoice_id"]
        return CASE

    def decide(self, payload):
        self.decisions.append(payload)
        if (
            payload.get("action_type") == "ApproveShortPay"
            and payload.get("expected_payable_cents") != CASE["expected_cents"]
        ):
            raise ShortpayAPIError(
                "Stale payable: requested amount does not match the matcher.",
                status_code=400,
            )
        return {
            "status": "success",
            "new_disposition": "ShortPaid",
            "erp_proposal": {"authorized_amount_cents": CASE["expected_cents"]},
            "dispute_packet": {
                "disputed_total_cents": CASE["dispute_cents"],
                "attached_evidence": ["dock_receipt_SHP-88220.pdf"],
            },
        }

    def ingest_invoice(self, invoice_text):
        self.ingested_text = invoice_text
        return {"invoice_id": CASE["invoice_id"], "provider": "TensorMux"}

    def ingest_invoice_pdf(self, filename, file_bytes, content_type=None):
        self.ingested_pdf = (filename, file_bytes, content_type)
        return {"invoice_id": CASE["invoice_id"], "provider": "TensorMux"}


@pytest.fixture()
def frontend_client():
    api = FakeShortpayAPI()
    app = create_app({"TESTING": True, "SECRET_KEY": "test"}, api_client=api)
    return app.test_client(), api


@pytest.mark.parametrize("path", ["/", "/cases/INV-FRT-2026-09"])
def test_react_shell_is_served_for_application_routes(frontend_client, path):
    client, _ = frontend_client
    response = client.get(path)

    assert response.status_code == 200
    assert b'data-theme="light"' in response.data
    assert b'<div id="root"></div>' in response.data
    assert b"react/assets/index.css" in response.data
    assert b"react/assets/main.js" in response.data


def test_react_shell_restores_theme_before_loading_assets(frontend_client):
    client, _ = frontend_client
    html = client.get("/").get_data(as_text=True)
    assert html.index("localStorage.getItem('shortpay-theme')") < html.index('rel="stylesheet"')


def test_list_cases_proxies_fastapi_data_as_json(frontend_client):
    client, _ = frontend_client
    response = client.get("/api/ui/cases")

    assert response.status_code == 200
    assert response.is_json
    assert response.json == [CASE]


def test_case_detail_proxies_locked_math_as_json(frontend_client):
    client, _ = frontend_client
    response = client.get("/api/ui/cases/INV-FRT-2026-09")

    assert response.status_code == 200
    assert response.is_json
    assert response.json["expected_cents"] == 92500
    assert response.json["dwell_minutes"] == 93


def test_approve_forwards_displayed_payable(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/api/ui/cases/INV-FRT-2026-09/decide",
        json={"action_type": "ApproveShortPay", "expected_payable_cents": 92500},
    )

    assert response.status_code == 200
    assert response.json["new_disposition"] == "ShortPaid"
    assert api.decisions[0]["expected_payable_cents"] == 92500
    assert api.decisions[0]["shipment_id"] == "SHP-88220"


def test_approve_does_not_replace_displayed_payable(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/api/ui/cases/INV-FRT-2026-09/decide",
        json={"action_type": "ApproveShortPay", "expected_payable_cents": 90000},
    )

    assert response.status_code == 400
    assert api.decisions[0]["expected_payable_cents"] == 90000
    assert "Stale payable" in response.json["detail"]


def test_approve_requires_displayed_payable(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/api/ui/cases/INV-FRT-2026-09/decide",
        json={"action_type": "ApproveShortPay"},
    )

    assert response.status_code == 400
    assert response.json["detail"] == "Approve short-pay using the displayed payable."
    assert api.decisions == []


def test_override_requires_reason(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/api/ui/cases/INV-FRT-2026-09/decide",
        json={"shipment_id": "SHP-88220", "action_type": "OverridePayAsBilled"},
    )

    assert response.status_code == 400
    assert response.json["detail"] == "A reason is required to pay the invoice as billed."
    assert api.decisions == []


def test_demo_ingest_calls_sponsor_api(frontend_client):
    client, api = frontend_client
    response = client.post("/api/ui/ingest", json={"invoice_text": "carrier invoice"})

    assert response.status_code == 201
    assert api.ingested_text == "carrier invoice"
    assert response.json["invoice_id"] == "INV-FRT-2026-09"


def test_ingest_rejects_blank_invoice_text(frontend_client):
    client, api = frontend_client
    response = client.post("/api/ui/ingest", json={"invoice_text": "  "})

    assert response.status_code == 400
    assert response.json["detail"] == "Paste invoice text before running extraction."
    assert api.ingested_text is None


def test_pdf_ingest_calls_sponsor_api(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/ingest/pdf",
        data={"invoice_pdf": (io.BytesIO(b"%PDF-1.4 hero"), "hero.pdf")},
    )

    assert response.status_code == 302
    assert api.ingested_pdf[0] == "hero.pdf"
    assert api.ingested_pdf[1] == b"%PDF-1.4 hero"
    assert response.headers["Location"].endswith("/cases/INV-FRT-2026-09")


def test_pdf_ingest_json_returns_redirect(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/ingest/pdf",
        data={"invoice_pdf": (io.BytesIO(b"%PDF-1.4 hero"), "hero.pdf")},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert api.ingested_pdf[0] == "hero.pdf"
    assert payload["invoice_id"] == CASE["invoice_id"]
    assert payload["redirect"].endswith("/cases/INV-FRT-2026-09")


def test_pdf_ingest_rejects_missing_file(frontend_client):
    client, api = frontend_client
    response = client.post("/ingest/pdf", follow_redirects=True)

    assert response.status_code == 200
    assert b"Choose a carrier PDF" in response.data
    assert api.ingested_pdf is None
