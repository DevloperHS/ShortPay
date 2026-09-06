import pytest

from frontend import create_app


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

    def list_cases(self):
        return [CASE]

    def get_case(self, invoice_id):
        assert invoice_id == CASE["invoice_id"]
        return CASE

    def decide(self, payload):
        self.decisions.append(payload)
        return {"status": "success", "new_disposition": "ShortPaid"}

    def ingest_invoice(self, invoice_text):
        self.ingested_text = invoice_text
        return {"invoice_id": CASE["invoice_id"], "provider": "TensorMux"}


@pytest.fixture()
def frontend_client():
    api = FakeShortpayAPI()
    app = create_app({"TESTING": True, "SECRET_KEY": "test"}, api_client=api)
    return app.test_client(), api


def test_board_renders_prd_columns_and_case(frontend_client):
    client, _ = frontend_client
    response = client.get("/")

    assert response.status_code == 200
    assert b"Major exceptions" in response.data
    assert b"FedEx Freight" in response.data
    assert b"Overbilled by $195.00" in response.data
    assert b"Protect every payable" in response.data
    assert b"At-risk spend" in response.data
    assert b"Upload PDF" in response.data
    assert b"PDF extraction is UI-only for now" in response.data


def test_case_detail_renders_locked_math(frontend_client):
    client, _ = frontend_client
    response = client.get("/cases/INV-FRT-2026-09")

    assert response.status_code == 200
    assert b"$1,120.00" in response.data
    assert b"$925.00" in response.data
    assert b"$195.00" in response.data
    assert b"93 min" in response.data
    assert b"Evidence matched" in response.data
    assert b"Approve short-pay" in response.data


def test_approve_uses_backend_expected_amount(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/cases/INV-FRT-2026-09/decide",
        data={"shipment_id": "SHP-88220", "action_type": "ApproveShortPay"},
    )

    assert response.status_code == 302
    assert api.decisions[0]["expected_payable_cents"] == 92500


def test_override_requires_reason(frontend_client):
    client, api = frontend_client
    response = client.post(
        "/cases/INV-FRT-2026-09/decide",
        data={"shipment_id": "SHP-88220", "action_type": "OverridePayAsBilled"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"A reason is required" in response.data
    assert api.decisions == []


def test_demo_ingest_calls_sponsor_api(frontend_client):
    client, api = frontend_client
    response = client.post("/ingest", data={"invoice_text": "carrier invoice"})

    assert response.status_code == 302
    assert api.ingested_text == "carrier invoice"
    assert response.headers["Location"].endswith("/cases/INV-FRT-2026-09")
