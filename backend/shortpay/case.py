from typing import Optional, Union, Literal
from pydantic import BaseModel, field_validator
from shortpay.matching import MatchResult


class CaseKey(BaseModel):
    invoice_id: str
    shipment_id: str

    def __hash__(self):
        return hash((self.invoice_id, self.shipment_id))


class NeedsReview(BaseModel):
    disposition_type: Literal["NeedsReview"] = "NeedsReview"
    reason: str = "Overbill above policy threshold or unapproved rules on lane"


class AutoClosed(BaseModel):
    disposition_type: Literal["AutoClosed"] = "AutoClosed"
    reason: str = "Variance <= $50 policy threshold and lane rules pre-approved"


class ShortPaid(BaseModel):
    disposition_type: Literal["ShortPaid"] = "ShortPaid"
    approved_payable_cents: int


class PaidAsBilled(BaseModel):
    disposition_type: Literal["PaidAsBilled"] = "PaidAsBilled"
    override_reason: str


class SkippedOutOfScope(BaseModel):
    disposition_type: Literal["SkippedOutOfScope"] = "SkippedOutOfScope"
    skip_reason: str


Disposition = Union[NeedsReview, AutoClosed, ShortPaid, PaidAsBilled, SkippedOutOfScope]


class ApproveShortPay(BaseModel):
    expected_payable_cents: int


class OverridePayAsBilled(BaseModel):
    override_reason: str

    @field_validator("override_reason")
    @classmethod
    def require_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Override reason is required")
        return value


class AuditCase(BaseModel):
    case_key: CaseKey
    carrier_name: str
    bill_of_lading: str
    match_result: MatchResult
    disposition: Disposition
    policy_id: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return isinstance(self.disposition, (ShortPaid, PaidAsBilled, SkippedOutOfScope, AutoClosed))
