import os
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shortpay import AuditOffice, CaseKey, ApproveShortPay, OverridePayAsBilled
from shortpay.adapters.baseline_csv import parse_baseline_csv
from shortpay.adapters.dock_log import parse_dock_log_json
from shortpay.adapters.facility_master import parse_facility_json
from shortpay.adapters.invoice_extract import parse_invoice_json

office = AuditOffice.in_memory()


def auto_ingest_fixtures():
    """Auto-ingest project fixtures on startup."""
    fixtures_dir = os.path.join(os.path.dirname(__file__), "..", "fixtures")
    csv_path = os.path.join(fixtures_dir, "freight_audit_baseline.csv")
    dock_path = os.path.join(fixtures_dir, "dock_SHP-88220.json")
    facility_path = os.path.join(fixtures_dir, "facility_SHP-88220.json")
    invoice_path = os.path.join(fixtures_dir, "invoice_INV-FRT-2026-09.json")

    if os.path.exists(csv_path):
        contracts = parse_baseline_csv(csv_path)
        office.ingest(contracts)

    if os.path.exists(dock_path):
        dock = parse_dock_log_json(dock_path)
        office.ingest([dock])

    if os.path.exists(facility_path):
        facility = parse_facility_json(facility_path)
        office.ingest([facility])

    if os.path.exists(invoice_path):
        invoice = parse_invoice_json(invoice_path)
        office.ingest([invoice])
        # Auto-match hero case
        office.match(CaseKey(invoice_id=invoice.invoice_id, shipment_id=invoice.shipment_id))


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_ingest_fixtures()
    yield


app = FastAPI(
    title="Shortpay Freight Audit API",
    description="Backend REST API for Autonomous Office of the CFO (Syndicate by Maximor)",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend (Shubhu)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DecideRequest(BaseModel):
    invoice_id: str
    shipment_id: str
    action_type: str  # "ApproveShortPay" or "OverridePayAsBilled"
    expected_payable_cents: int = 0
    override_reason: str = ""


@app.post("/api/ingest")
def trigger_ingest():
    auto_ingest_fixtures()
    return {"status": "success", "message": "Fixtures ingested successfully"}


@app.get("/api/cases")
def get_kanban_cases() -> List[Dict[str, Any]]:
    cases = office.cases()
    if not cases:
        auto_ingest_fixtures()
        cases = office.cases()

    results = []
    for c in cases:
        disp_name = c.disposition.disposition_type
        if disp_name == "NeedsReview":
            col = "Major exceptions"
            color = "#FCE8E6"
        elif disp_name == "AutoClosed":
            col = "Auto-closed"
            color = "#E6F4EA"
        elif disp_name == "ShortPaid":
            col = "Short-paid"
            color = "#E8F0FE"
        elif disp_name == "PaidAsBilled":
            col = "Paid as billed"
            color = "#F1F3F4"
        else:
            col = "Out of scope"
            color = "#F8F9FA"

        m = c.match_result
        dispute_dollars = m.dispute_total_cents / 100.0

        results.append({
            "invoice_id": c.case_key.invoice_id,
            "shipment_id": c.case_key.shipment_id,
            "carrier_name": c.carrier_name,
            "bill_of_lading": c.bill_of_lading,
            "billed_cents": m.billed_total_cents,
            "expected_cents": m.expected_total_cents,
            "dispute_cents": m.dispute_total_cents,
            "disposition": disp_name,
            "kanban": {
                "column": col,
                "color": color,
                "title": f"{c.carrier_name} - {c.case_key.shipment_id}",
                "subtitle": f"Overbilled by ${dispute_dollars:.2f} (Liftgate + Detention)" if dispute_dollars > 0 else "Clean invoice",
            }
        })
    return results


@app.get("/api/cases/{invoice_id}")
def get_case_detail(invoice_id: str) -> Dict[str, Any]:
    cases = [c for c in office.cases() if c.case_key.invoice_id == invoice_id]
    if not cases:
        auto_ingest_fixtures()
        cases = [c for c in office.cases() if c.case_key.invoice_id == invoice_id]

    if not cases:
        raise HTTPException(status_code=404, detail="Case not found")

    c = cases[0]
    m = c.match_result

    lines_detail = []
    for billed, exp in m.lines:
        lines_detail.append({
            "charge_type": billed.charge_type.value,
            "billed_cents": billed.amount_cents,
            "expected_cents": exp.amount_cents,
            "explanation": exp.explanation,
        })

    return {
        "invoice_id": c.case_key.invoice_id,
        "shipment_id": c.case_key.shipment_id,
        "carrier_name": c.carrier_name,
        "bill_of_lading": c.bill_of_lading,
        "dwell_minutes": m.dwell_minutes,
        "billable_detention_minutes": m.billable_detention_minutes,
        "completed_detention_hours": m.completed_detention_hours,
        "billed_cents": m.billed_total_cents,
        "expected_cents": m.expected_total_cents,
        "dispute_cents": m.dispute_total_cents,
        "disposition": c.disposition.disposition_type,
        "lines": lines_detail,
    }


@app.post("/api/decide")
def decide_action(req: DecideRequest):
    key = CaseKey(invoice_id=req.invoice_id, shipment_id=req.shipment_id)
    if req.action_type == "ApproveShortPay":
        act = ApproveShortPay(expected_payable_cents=req.expected_payable_cents)
    elif req.action_type == "OverridePayAsBilled":
        act = OverridePayAsBilled(override_reason=req.override_reason)
    else:
        raise HTTPException(status_code=400, detail="Invalid action_type")

    try:
        updated_case = office.decide(key, act)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "new_disposition": updated_case.disposition.disposition_type,
        "approved_payable_cents": getattr(updated_case.disposition, "approved_payable_cents", None),
    }
