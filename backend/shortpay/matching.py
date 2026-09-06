from typing import Optional, List, Tuple
from pydantic import BaseModel, Field
from shortpay.evidence import (
    InvoiceFact,
    ContractFact,
    FacilityFact,
    DockDwellFact,
    ChargeType,
    Mode,
)
from shortpay.ledgers import BilledLine, ExpectedLine


class MatchResult(BaseModel):
    is_out_of_scope: bool = False
    skip_reason: Optional[str] = None
    dwell_minutes: int = 0
    billable_detention_minutes: int = 0
    completed_detention_hours: int = 0
    billed_total_cents: int = 0
    expected_total_cents: int = 0
    dispute_total_cents: int = 0
    fired_rule_ids: List[str] = Field(default_factory=list)
    has_unexplained_lines: bool = False
    lines: List[Tuple[BilledLine, ExpectedLine]] = Field(default_factory=list)


def match_evidence(
    invoice: InvoiceFact,
    contract: ContractFact,
    facility: FacilityFact,
    dock: DockDwellFact,
) -> MatchResult:
    """
    Pure function matcher over evidence facts.
    Has zero I/O and zero LLM calls.
    """
    # Scope check: v1 only supports LTL and TL
    if contract.mode not in (Mode.LTL, Mode.TL):
        return MatchResult(
            is_out_of_scope=True,
            skip_reason=f"Mode {contract.mode.value} is out of v1 scope",
            billed_total_cents=invoice.total_billed_cents,
            expected_total_cents=0,
            dispute_total_cents=0,
        )

    dwell = dock.dwell_minutes
    allowed = contract.allowed_dwell_minutes
    billable_detention_min = max(0, dwell - allowed)
    completed_detention_hr = billable_detention_min // 60

    joined_lines: List[Tuple[BilledLine, ExpectedLine]] = []
    expected_sum = 0
    fired_rule_ids: List[str] = []
    has_unexplained_lines = False

    for line in invoice.lines:
        billed_line = BilledLine(
            charge_type=line.charge_type,
            amount_cents=line.amount_cents,
            billed_minutes=line.billed_minutes,
            description=line.description,
        )

        if line.charge_type == ChargeType.BASE_FREIGHT:
            expected_cents = contract.agreed_base_rate_cents
            exp_line = ExpectedLine(
                charge_type=ChargeType.BASE_FREIGHT,
                amount_cents=expected_cents,
                explanation=f"Base freight matched contract rate (${expected_cents / 100:.2f})",
            )
        elif line.charge_type == ChargeType.LIFTGATE:
            if facility.destination_has_dock:
                expected_cents = 0
                exp_line = ExpectedLine(
                    charge_type=ChargeType.LIFTGATE,
                    amount_cents=0,
                    explanation="Destination facility has standard loading dock; liftgate not authorized ($0.00)",
                )
            else:
                expected_cents = line.amount_cents
                exp_line = ExpectedLine(
                    charge_type=ChargeType.LIFTGATE,
                    amount_cents=expected_cents,
                    explanation="Destination has no loading dock; liftgate authorized as billed",
                )
        elif line.charge_type == ChargeType.DETENTION:
            expected_cents = completed_detention_hr * contract.detention_rate_per_hour_cents
            exp_line = ExpectedLine(
                charge_type=ChargeType.DETENTION,
                amount_cents=expected_cents,
                explanation=(
                    f"Dwell is {dwell} min ({allowed} min free). Billable: {billable_detention_min} min "
                    f"({completed_detention_hr} completed hr @ ${contract.detention_rate_per_hour_cents / 100:.2f}/hr)"
                ),
            )
        else:
            # Unexplained or OTHER line items
            has_unexplained_lines = True
            expected_cents = 0
            exp_line = ExpectedLine(
                charge_type=line.charge_type,
                amount_cents=0,
                explanation="Unexplained charge type; auto-close blocked",
            )

        expected_sum += expected_cents
        joined_lines.append((billed_line, exp_line))
        if line.amount_cents > expected_cents:
            rule_id = {
                ChargeType.DETENTION: "DETENTION_HOURS",
                ChargeType.LIFTGATE: "LIFTGATE_DOCK_PRESENT",
                ChargeType.BASE_FREIGHT: "BASE_RATE_MISMATCH",
                ChargeType.OTHER: "UNEXPLAINED_LINE",
            }[line.charge_type]
            if rule_id not in fired_rule_ids:
                fired_rule_ids.append(rule_id)

    billed_sum = invoice.total_billed_cents
    dispute_sum = max(0, billed_sum - expected_sum)

    return MatchResult(
        is_out_of_scope=False,
        dwell_minutes=dwell,
        billable_detention_minutes=billable_detention_min,
        completed_detention_hours=completed_detention_hr,
        billed_total_cents=billed_sum,
        expected_total_cents=expected_sum,
        dispute_total_cents=dispute_sum,
        fired_rule_ids=fired_rule_ids,
        has_unexplained_lines=has_unexplained_lines,
        lines=joined_lines,
    )
