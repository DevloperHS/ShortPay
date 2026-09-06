from typing import Set
from pydantic import BaseModel, Field
from shortpay.evidence import Mode


class LaneKey(BaseModel):
    carrier: str
    mode: Mode
    destination_has_dock: bool

    def __hash__(self):
        return hash((self.carrier, self.mode, self.destination_has_dock))


class PolicyBook(BaseModel):
    policy_id: str = "SHORT-PAY-01"
    max_auto_close_dispute_cents: int = 5000  # $50.00
    approved_rules: Set[str] = Field(default_factory=set)

    def is_rule_approved(self, rule_id: str) -> bool:
        return rule_id in self.approved_rules

    def record_approved_rule(self, rule_id: str):
        self.approved_rules.add(rule_id)

    def record_approved_rules(self, rule_ids: list[str]) -> None:
        self.approved_rules.update(rule_ids)

    def permits_auto_close(self, *, dispute_cents: int, fired_rule_ids: list[str], has_unexplained_lines: bool) -> bool:
        return (
            dispute_cents <= self.max_auto_close_dispute_cents
            and not has_unexplained_lines
            and all(self.is_rule_approved(rule_id) for rule_id in fired_rule_ids)
        )
