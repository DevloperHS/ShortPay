from pathlib import Path
from typing import List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from shortpay import AuditOffice, CaseKey, ApproveShortPay, OverridePayAsBilled, ShortPaid
from shortpay.adapters.baseline_csv import parse_baseline_csv
from shortpay.adapters.dock_log import parse_dock_log_json
from shortpay.adapters.facility_master import parse_facility_json
from shortpay.adapters.invoice_extract import (
    ExtractionError,
    ExtractionOutcome,
    PdfParseError,
    extract_invoice_with_fallback_details,
    extract_text_from_pdf,
    parse_invoice_json,
)
from shortpay.adapters.erp_propose import build_dispute_packet, build_erp_proposal
from shortpay.adapters.vault_hunter import discover_invoice_files
from shortpay.neatlogs import tracer

office = AuditOffice.in_memory()

_RULE_LABELS = {
    "LIFTGATE_DOCK_PRESENT": "Liftgate",
    "DETENTION_HOURS": "Detention",
    "BASE_RATE_MISMATCH": "Base rate",
    "UNEXPLAINED_LINE": "Unexplained charge",
}


def _format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(cents)
    return f"{sign}${value // 100}.{value % 100:02d}"


_RULE_ORDER = (
    "LIFTGATE_DOCK_PRESENT",
    "DETENTION_HOURS",
    "BASE_RATE_MISMATCH",
    "UNEXPLAINED_LINE",
)


def _kanban_subtitle(match_result) -> str:
    if match_result.dispute_total_cents <= 0:
        return "Clean invoice"
    fired = set(match_result.fired_rule_ids)
    labels = [_RULE_LABELS[rule_id] for rule_id in _RULE_ORDER if rule_id in fired]
    amount = _format_cents(match_result.dispute_total_cents)
    if labels:
        return f"Overbilled by {amount} ({' + '.join(labels)})"
    return f"Overbilled by {amount}"


def auto_ingest_fixtures():
    """Auto-ingest project fixtures on startup."""
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    csv_path = fixtures_dir / "freight_audit_baseline.csv"

    if csv_path.exists():
        contracts = parse_baseline_csv(str(csv_path))
        office.ingest(
            contracts,
            source="fixture:freight_audit_baseline.csv",
            emit_trace=False,
        )

    for dock_path in sorted(fixtures_dir.glob("dock_*.json")):
        dock = parse_dock_log_json(str(dock_path))
        office.ingest([dock], source=f"fixture:{dock_path.name}", emit_trace=False)

    for facility_path in sorted(fixtures_dir.glob("facility_*.json")):
        facility = parse_facility_json(str(facility_path))
        office.ingest([facility], source=f"fixture:{facility_path.name}", emit_trace=False)

    for discovered in discover_invoice_files(fixtures_dir):
        invoice = parse_invoice_json(discovered.path)
        office.ingest([invoice], source="fixture:invoice_json", emit_trace=False)
        try:
            office.match(
                CaseKey(invoice_id=invoice.invoice_id, shipment_id=invoice.shipment_id),
                emit_trace=False,
            )
        except KeyError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_ingest_fixtures()
    try:
        yield
    finally:
        tracer.shutdown()


app = FastAPI(
    title="Shortpay Freight Audit API",
    description="Backend REST API for Autonomous Office of the CFO (Syndicate by Maximor)",
    version="1.0.0",
    lifespan=lifespan,
)

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

    @model_validator(mode="after")
    def validate_override_reason(self):
        if self.action_type == "OverridePayAsBilled" and not self.override_reason.strip():
            raise ValueError("Override reason is required for OverridePayAsBilled")
        self.override_reason = self.override_reason.strip()
        return self


class SponsorInvoiceIngestRequest(BaseModel):
    raw_invoice_text: str = Field(min_length=1)
    auto_match: bool = True


@app.post("/api/ingest")
def trigger_ingest():
    auto_ingest_fixtures()
    return {"status": "success", "message": "Fixtures ingested successfully"}


def _match_extracted_invoice(
    outcome: ExtractionOutcome,
    auto_match: bool,
    workflow,
) -> Dict[str, Any]:
    office.ingest(
        [outcome.fact],
        source=f"{outcome.provider}:{outcome.model_name}",
    )
    response: Dict[str, Any] = {
        "status": "success",
        "provider": outcome.provider,
        "model": outcome.model_name,
        "invoice_id": outcome.fact.invoice_id,
        "shipment_id": outcome.fact.shipment_id,
        "billed_cents": outcome.fact.total_billed_cents,
    }
    workflow.set_attribute(
        "shortpay.trace_id",
        f"trace-freight-{outcome.fact.shipment_id.lower()}",
    )
    if auto_match:
        case = office.match(
            CaseKey(
                invoice_id=outcome.fact.invoice_id,
                shipment_id=outcome.fact.shipment_id,
            ),
            emit_trace=False,
        )
        response.update(
            {
                "expected_cents": case.match_result.expected_total_cents,
                "dispute_cents": case.match_result.dispute_total_cents,
                "disposition": case.disposition.disposition_type,
            }
        )
    workflow.set_output(response)
    return response


@app.post("/api/ingest/invoice")
def ingest_invoice_through_sponsors(req: SponsorInvoiceIngestRequest) -> Dict[str, Any]:
    """Extract a real invoice through TensorMux/Groq, then run deterministic matching."""
    with tracer.workflow(
        "match_evidence",
        trace_id="trace-freight-invoice-ingest",
        input_value={
            "invoice_text": req.raw_invoice_text,
            "auto_match": req.auto_match,
        },
    ) as workflow:
        try:
            outcome = extract_invoice_with_fallback_details(req.raw_invoice_text)
            return _match_extracted_invoice(outcome, req.auto_match, workflow)
        except ExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invoice extracted, but matching evidence is incomplete: {exc}",
            ) from exc


@app.post("/api/ingest/invoice-pdf")
def ingest_invoice_pdf(
    invoice_pdf: UploadFile = File(...),
    auto_match: bool = True,
) -> Dict[str, Any]:
    """Parse a carrier PDF, extract billed facts, then run deterministic matching."""
    filename = invoice_pdf.filename or "invoice.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF only")

    pdf_bytes = invoice_pdf.file.read()
    with tracer.workflow(
        "match_evidence",
        trace_id="trace-freight-invoice-pdf-ingest",
        input_value={
            "filename": filename,
            "bytes": len(pdf_bytes),
            "auto_match": auto_match,
        },
    ) as workflow:
        try:
            invoice_text = extract_text_from_pdf(pdf_bytes)
            workflow.set_attribute("shortpay.pdf_chars", len(invoice_text))
            outcome = extract_invoice_with_fallback_details(invoice_text)
            return _match_extracted_invoice(outcome, auto_match, workflow)
        except PdfParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ExtractionError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invoice extracted, but matching evidence is incomplete: {exc}",
            ) from exc


@app.get("/api/cases")
def get_kanban_cases() -> List[Dict[str, Any]]:
    cases = office.cases()
    if not cases:
        auto_ingest_fixtures()
        cases = office.cases()

    cases = sorted(cases, key=lambda case: case.disposition.disposition_type == "SkippedOutOfScope")
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

        results.append({
            "invoice_id": c.case_key.invoice_id,
            "shipment_id": c.case_key.shipment_id,
            "carrier_name": c.carrier_name,
            "bill_of_lading": c.bill_of_lading,
            "billed_cents": m.billed_total_cents,
            "expected_cents": m.expected_total_cents,
            "dispute_cents": m.dispute_total_cents,
            "disposition": disp_name,
            "skip_reason": getattr(c.disposition, "skip_reason", None),
            "policy_id": c.policy_id,
            "kanban": {
                "column": col,
                "color": color,
                "title": f"{c.carrier_name} - {c.case_key.shipment_id}",
                "subtitle": _kanban_subtitle(m),
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

    payload = {
        "invoice_id": c.case_key.invoice_id,
        "shipment_id": c.case_key.shipment_id,
        "carrier_name": c.carrier_name,
        "bill_of_lading": c.bill_of_lading,
        "dwell_minutes": m.dwell_minutes,
        "billable_detention_minutes": m.billable_detention_minutes,
        "completed_detention_hours": m.completed_detention_hours,
        "arrived_at": m.arrived_at,
        "departed_at": m.departed_at,
        "allowed_dwell_minutes": m.allowed_dwell_minutes,
        "destination_has_dock": m.destination_has_dock,
        "fired_rule_ids": m.fired_rule_ids,
        "billed_cents": m.billed_total_cents,
        "expected_cents": m.expected_total_cents,
        "dispute_cents": m.dispute_total_cents,
        "disposition": c.disposition.disposition_type,
        "skip_reason": getattr(c.disposition, "skip_reason", None),
        "policy_id": c.policy_id,
        "lines": lines_detail,
        "erp_proposal": None,
        "dispute_packet": None,
    }
    if isinstance(c.disposition, ShortPaid):
        erp_proposal = build_erp_proposal(c)
        if erp_proposal is not None:
            payload["erp_proposal"] = erp_proposal.model_dump()
            payload["dispute_packet"] = build_dispute_packet(c).model_dump()
    return payload


@app.post("/api/decide")
def decide_action(req: DecideRequest):
    key = CaseKey(invoice_id=req.invoice_id, shipment_id=req.shipment_id)
    if req.action_type == "ApproveShortPay":
        act = ApproveShortPay(expected_payable_cents=req.expected_payable_cents)
    elif req.action_type == "OverridePayAsBilled":
        act = OverridePayAsBilled(override_reason=req.override_reason)
    else:
        raise HTTPException(status_code=400, detail="Invalid action_type")

    with tracer.workflow(
        "controller_decision",
        trace_id=f"trace-freight-{req.shipment_id.lower()}",
        input_value={
            "invoice_id": req.invoice_id,
            "shipment_id": req.shipment_id,
            "action_type": req.action_type,
            "expected_payable_cents": req.expected_payable_cents,
            "override_reason": req.override_reason,
        },
    ) as workflow:
        try:
            updated_case = office.decide(key, act)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        response = {
            "status": "success",
            "new_disposition": updated_case.disposition.disposition_type,
            "approved_payable_cents": getattr(
                updated_case.disposition, "approved_payable_cents", None
            ),
            "erp_proposal": None,
            "dispute_packet": None,
        }
        erp_proposal = build_erp_proposal(updated_case)
        if erp_proposal is not None:
            response["erp_proposal"] = erp_proposal.model_dump()
            response["dispute_packet"] = build_dispute_packet(updated_case).model_dump()
        workflow.set_output(response)
        return response
