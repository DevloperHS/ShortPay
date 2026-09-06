from typing import Set
from pydantic import BaseModel
from shortpay.evidence import Mode


class LaneKey(BaseModel):
    carrier: str
    mode: Mode
    destination_has_dock: bool

    def __hash__(self):
        return hash((self.carrier, self.mode, self.destination_has_dock))


class PolicyBook(BaseModel):
    max_auto_close_dispute_cents: int = 5000  # $50.00
    approved_rules: Set[str] = set()

    def is_rule_approved(self, rule_id: str) -> bool:
        return rule_id in self.approved_rules

    def record_approved_rule(self, rule_id: str):
        self.approved_rules.add(rule_id)
