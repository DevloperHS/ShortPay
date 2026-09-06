import pytest
from shortpay.evidence import (
    InvoiceFact,
    InvoiceLine,
    ContractFact,
    FacilityFact,
    DockDwellFact,
    ChargeType,
    Mode,
)
from shortpay.matching import match_evidence


def test_hero_invoice_shp_88220_cents_lock():
    """
    Hero Lock Test per architecture.md:
    FedEx Freight SHP-88220 / BOL-US-99121 / INV-FRT-2026-09
    - Billed Total: $1,120.00 (112,000 cents)
    - Expected Payable: $925.00 (92,500 cents)
    - Dispute Variance: $195.00 (19,500 cents)
    """
    invoice = InvoiceFact(
        invoice_id="INV-FRT-2026-09",
        shipment_id="SHP-88220",
        carrier_name="FedEx Freight",
        bill_of_lading="BOL-US-99121",
        lines=(
            InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
            InvoiceLine(charge_type=ChargeType.DETENTION, amount_cents=17500, billed_minutes=60),
            InvoiceLine(charge_type=ChargeType.LIFTGATE, amount_cents=9500),
        ),
    )

    contract = ContractFact(
        shipment_id="SHP-88220",
        carrier="FedEx Freight",
        bill_of_lading="BOL-US-99121",
        mode=Mode.LTL,
        agreed_base_rate_cents=85000,
        allowed_dwell_minutes=30,
        detention_rate_per_hour_cents=7500,
    )

    facility = FacilityFact(
        shipment_id="SHP-88220",
        destination_has_dock=True,
    )

    dock = DockDwellFact(
        shipment_id="SHP-88220",
        arrived_at="14:12:00",
        departed_at="15:45:00",
    )

    result = match_evidence(invoice, contract, facility, dock)

    assert not result.is_out_of_scope
    assert result.dwell_minutes == 93
    assert result.billable_detention_minutes == 63
    assert result.completed_detention_hours == 1
    assert result.arrived_at == "14:12:00"
    assert result.departed_at == "15:45:00"
    assert result.allowed_dwell_minutes == 30
    assert result.destination_has_dock is True

    assert result.billed_total_cents == 112000
    assert result.expected_total_cents == 92500
    assert result.dispute_total_cents == 19500

    line_map = {billed.charge_type: (billed, exp) for billed, exp in result.lines}
    assert line_map[ChargeType.BASE_FREIGHT][1].amount_cents == 85000
    assert line_map[ChargeType.LIFTGATE][1].amount_cents == 0
    assert line_map[ChargeType.DETENTION][1].amount_cents == 7500
