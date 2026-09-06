import pytest

from shortpay.case import (
    ApproveShortPay,
    AutoClosed,
    CaseKey,
    NeedsReview,
    OverridePayAsBilled,
    PaidAsBilled,
    ShortPaid,
    SkippedOutOfScope,
)
from shortpay.evidence import (
    ChargeType,
    ContractFact,
    DockDwellFact,
    FacilityFact,
    InvoiceFact,
    InvoiceLine,
    Mode,
)
from shortpay.matching import match_evidence
from shortpay.office import AuditOffice, StaleDecisionError


def _facts(
    *,
    invoice_id="INV-FRT-2026-09",
    shipment_id="SHP-88220",
    has_dock=True,
    arrived_at="14:12:00",
    departed_at="15:45:00",
    lines=None,
):
    lines = lines or (
        InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
        InvoiceLine(charge_type=ChargeType.DETENTION, amount_cents=17500),
        InvoiceLine(charge_type=ChargeType.LIFTGATE, amount_cents=9500),
    )
    return (
        InvoiceFact(
            invoice_id=invoice_id,
            shipment_id=shipment_id,
            carrier_name="FedEx Freight",
            bill_of_lading="BOL-US-99121",
            lines=lines,
        ),
        ContractFact(
            shipment_id=shipment_id,
            carrier="FedEx Freight",
            bill_of_lading="BOL-US-99121",
            mode=Mode.LTL,
            agreed_base_rate_cents=85000,
            allowed_dwell_minutes=30,
            detention_rate_per_hour_cents=7500,
        ),
        FacilityFact(shipment_id=shipment_id, destination_has_dock=has_dock),
        DockDwellFact(
            shipment_id=shipment_id,
            arrived_at=arrived_at,
            departed_at=departed_at,
        ),
    )


def _matched_office(**kwargs):
    office = AuditOffice.in_memory()
    facts = _facts(**kwargs)
    office.ingest(list(facts), emit_trace=False)
    key = CaseKey(invoice_id=facts[0].invoice_id, shipment_id=facts[0].shipment_id)
    return office, key, office.match(key, emit_trace=False)


def test_dock_false_authorizes_liftgate_as_billed():
    invoice, contract, facility, dock = _facts(has_dock=False)
    result = match_evidence(invoice, contract, facility, dock)
    liftgate = next(expected for billed, expected in result.lines if billed.charge_type == ChargeType.LIFTGATE)
    assert liftgate.amount_cents == 9500


def test_dwell_at_free_time_authorizes_zero_detention():
    invoice, contract, facility, dock = _facts(
        arrived_at="14:00:00", departed_at="14:30:00"
    )
    result = match_evidence(invoice, contract, facility, dock)
    detention = next(expected for billed, expected in result.lines if billed.charge_type == ChargeType.DETENTION)
    assert result.billable_detention_minutes == 0
    assert detention.amount_cents == 0


def test_stale_shortpay_fails_closed():
    office, key, _ = _matched_office()
    with pytest.raises(StaleDecisionError):
        office.decide(key, ApproveShortPay(expected_payable_cents=90000))


def test_rematch_does_not_reopen_terminal_case():
    office, key, _ = _matched_office()
    decided = office.decide(key, ApproveShortPay(expected_payable_cents=92500))
    assert isinstance(decided.disposition, ShortPaid)
    rematched = office.match(key, emit_trace=False)
    assert isinstance(rematched.disposition, ShortPaid)


def test_unexplained_line_blocks_auto_close():
    lines = (
        InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
        InvoiceLine(charge_type=ChargeType.OTHER, amount_cents=3800, description="Gate fee"),
    )
    office, key, first = _matched_office(lines=lines)
    contract = office.store.contracts[key.shipment_id]
    facility = office.store.facilities[key.shipment_id]
    policy = office.store.get_policy_for(contract, facility)
    policy.record_approved_rules(first.match_result.fired_rule_ids)
    rematched = office.match(key, emit_trace=False)
    assert first.match_result.has_unexplained_lines is True
    assert isinstance(rematched.disposition, NeedsReview)


def test_second_approved_lane_invoice_auto_closes_under_short_pay_01():
    office, key, first = _matched_office()
    office.decide(key, ApproveShortPay(expected_payable_cents=92500))

    second = _facts(
        invoice_id="INV-FRT-2026-10",
        shipment_id="SHP-88221",
        lines=(
            InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
            InvoiceLine(charge_type=ChargeType.LIFTGATE, amount_cents=3800),
        ),
    )
    office.ingest(list(second), emit_trace=False)
    second_key = CaseKey(invoice_id=second[0].invoice_id, shipment_id=second[0].shipment_id)
    result = office.match(second_key, emit_trace=False)
    assert result.policy_id == "SHORT-PAY-01"
    assert isinstance(result.disposition, AutoClosed)


def test_ocean_contract_becomes_visible_skip_without_dock_or_invoice():
    office = AuditOffice.in_memory()
    contract = ContractFact(
        shipment_id="SHP-88219",
        carrier="Maersk",
        bill_of_lading="BOL-US-99120",
        mode=Mode.OCEAN,
        agreed_base_rate_cents=420000,
        allowed_dwell_minutes=120,
        detention_rate_per_hour_cents=7500,
    )
    office.ingest([contract], emit_trace=False)
    cases = office.cases()
    assert len(cases) == 1
    assert isinstance(cases[0].disposition, SkippedOutOfScope)
    assert "OCEAN" in cases[0].disposition.skip_reason


def test_override_reason_cannot_be_blank():
    with pytest.raises(ValueError):
        OverridePayAsBilled(override_reason="   ")
