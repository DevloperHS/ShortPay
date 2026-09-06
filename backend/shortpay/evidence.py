from enum import Enum
from typing import NewType, Tuple, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

ShipmentId = NewType("ShipmentId", str)
InvoiceId = NewType("InvoiceId", str)


class ChargeType(str, Enum):
    BASE_FREIGHT = "BASE_FREIGHT"
    DETENTION = "DETENTION"
    LIFTGATE = "LIFTGATE"
    OTHER = "OTHER"


class Mode(str, Enum):
    LTL = "LTL"
    TL = "TL"
    OCEAN = "OCEAN"
    PARCEL = "PARCEL"
    OTHER = "OTHER"


class InvoiceLine(BaseModel):
    charge_type: ChargeType
    amount_cents: int = Field(..., description="Billed amount in integer cents")
    billed_minutes: Optional[int] = Field(None, description="Billed dwell/detention minutes if present")
    description: Optional[str] = None

    @field_validator("amount_cents")
    @classmethod
    def validate_cents(cls, v: int) -> int:
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError("amount_cents must be an integer")
        return v


class InvoiceFact(BaseModel):
    invoice_id: str
    shipment_id: str
    carrier_name: str
    bill_of_lading: str
    lines: Tuple[InvoiceLine, ...]

    @property
    def total_billed_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)


class DockDwellFact(BaseModel):
    shipment_id: str
    arrived_at: str  # HH:MM:SS format
    departed_at: str  # HH:MM:SS format

    @property
    def dwell_minutes(self) -> int:
        fmt = "%H:%M:%S"
        arr = datetime.strptime(self.arrived_at, fmt)
        dep = datetime.strptime(self.departed_at, fmt)
        diff_sec = (dep - arr).total_seconds()
        if diff_sec < 0:
            raise ValueError("Overnight dock logs not supported in v1")
        return int(diff_sec // 60)


class FacilityFact(BaseModel):
    shipment_id: str
    destination_has_dock: bool


class ContractFact(BaseModel):
    shipment_id: str
    carrier: str
    bill_of_lading: str
    mode: Mode
    agreed_base_rate_cents: int
    allowed_dwell_minutes: int
    detention_rate_per_hour_cents: int
