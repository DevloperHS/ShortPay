from typing import Tuple, Optional
from pydantic import BaseModel
from shortpay.evidence import ChargeType


class BilledLine(BaseModel):
    charge_type: ChargeType
    amount_cents: int
    billed_minutes: Optional[int] = None
    description: Optional[str] = None


class ExpectedLine(BaseModel):
    charge_type: ChargeType
    amount_cents: int
    explanation: str


class LedgerJoin(BaseModel):
    billed_total_cents: int
    expected_total_cents: int
    dispute_total_cents: int
    lines: Tuple[Tuple[BilledLine, ExpectedLine], ...]
