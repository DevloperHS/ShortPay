from typing import List, Optional
from pydantic import BaseModel
from shortpay.case import AuditCase, ShortPaid


class PayablePosting(BaseModel):
    invoice_id: str
    shipment_id: str
    carrier_name: str
    authorized_amount_cents: int
    system_of_record_target: str = "NetSuite ERP (Mock Proposal)"


class DisputeLine(BaseModel):
    charge_type: str
    disputed_amount_cents: int
    explanation: str


class DisputePacket(BaseModel):
    invoice_id: str
    shipment_id: str
    carrier_name: str
    disputed_total_cents: int
    attached_evidence: List[str]  # e.g. ["dock_receipt_SHP-88220.pdf", "facility_dock_master.json"]
    dispute_lines: List[DisputeLine]


def build_erp_proposal(case: AuditCase) -> Optional[PayablePosting]:
    """
    Generates an ERP Payable Posting proposal. Does not write to GL directly.
    """
    if not isinstance(case.disposition, ShortPaid):
        return None

    return PayablePosting(
        invoice_id=case.case_key.invoice_id,
        shipment_id=case.case_key.shipment_id,
        carrier_name=case.carrier_name,
        authorized_amount_cents=case.disposition.approved_payable_cents,
    )


def build_dispute_packet(case: AuditCase) -> DisputePacket:
    """
    Generates a carrier dispute packet with attached dock evidence.
    """
    m = case.match_result
    dispute_lines = []
    for billed, exp in m.lines:
        variance = billed.amount_cents - exp.amount_cents
        if variance > 0:
            dispute_lines.append(
                DisputeLine(
                    charge_type=billed.charge_type.value,
                    disputed_amount_cents=variance,
                    explanation=exp.explanation,
                )
            )

    return DisputePacket(
        invoice_id=case.case_key.invoice_id,
        shipment_id=case.case_key.shipment_id,
        carrier_name=case.carrier_name,
        disputed_total_cents=m.dispute_total_cents,
        attached_evidence=[
            f"dock_receipt_{case.case_key.shipment_id}.pdf",
            f"facility_master_{case.case_key.shipment_id}.json",
        ],
        dispute_lines=dispute_lines,
    )
