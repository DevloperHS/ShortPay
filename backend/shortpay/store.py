from typing import Dict, Optional, List
from shortpay.evidence import InvoiceFact, ContractFact, FacilityFact, DockDwellFact
from shortpay.case import CaseKey, AuditCase
from shortpay.policy import LaneKey, PolicyBook


class InMemoryStore:
    def __init__(self):
        self.invoices: Dict[str, InvoiceFact] = {}  # invoice_id -> InvoiceFact
        self.contracts: Dict[str, ContractFact] = {}  # shipment_id -> ContractFact
        self.facilities: Dict[str, FacilityFact] = {}  # shipment_id -> FacilityFact
        self.docks: Dict[str, DockDwellFact] = {}  # shipment_id -> DockDwellFact
        self.cases: Dict[CaseKey, AuditCase] = {}
        self.lane_policies: Dict[LaneKey, PolicyBook] = {}

    def get_policy(self, lane_key: LaneKey) -> PolicyBook:
        if lane_key not in self.lane_policies:
            self.lane_policies[lane_key] = PolicyBook()
        return self.lane_policies[lane_key]

    def save_case(self, case: AuditCase):
        self.cases[case.case_key] = case

    def get_case(self, case_key: CaseKey) -> Optional[AuditCase]:
        return self.cases.get(case_key)

    def list_cases(self) -> List[AuditCase]:
        return list(self.cases.values())
