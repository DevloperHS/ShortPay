from typing import List, Union, Optional
from shortpay.evidence import InvoiceFact, ContractFact, FacilityFact, DockDwellFact, Mode
from shortpay.case import (
    CaseKey,
    AuditCase,
    NeedsReview,
    AutoClosed,
    ShortPaid,
    PaidAsBilled,
    SkippedOutOfScope,
    ApproveShortPay,
    OverridePayAsBilled,
)
from shortpay.matching import match_evidence, MatchResult
from shortpay.store import InMemoryStore
from shortpay.policy import LaneKey
from shortpay.neatlogs import tracer, compute_evidence_hash


class StaleDecisionError(ValueError):
    pass


class AuditOffice:
    def __init__(self, store: Optional[InMemoryStore] = None):
        self.store = store or InMemoryStore()

    @classmethod
    def in_memory(cls) -> "AuditOffice":
        return cls(store=InMemoryStore())

    def ingest(
        self,
        facts: List[Union[InvoiceFact, ContractFact, FacilityFact, DockDwellFact]],
        *,
        source: str = "application",
        emit_trace: bool = True,
    ):
        for fact in facts:
            if isinstance(fact, InvoiceFact):
                self.store.invoices[fact.invoice_id] = fact
                record_id = fact.invoice_id
            elif isinstance(fact, ContractFact):
                self.store.contracts[fact.shipment_id] = fact
                record_id = fact.shipment_id
                if fact.mode not in (Mode.LTL, Mode.TL):
                    self._save_out_of_scope_contract(fact)
            elif isinstance(fact, FacilityFact):
                self.store.facilities[fact.shipment_id] = fact
                record_id = fact.shipment_id
            elif isinstance(fact, DockDwellFact):
                self.store.docks[fact.shipment_id] = fact
                record_id = fact.shipment_id
            else:
                raise TypeError(f"Unsupported fact type: {type(fact).__name__}")

            if emit_trace:
                shipment_id = getattr(fact, "shipment_id")
                tracer.trace_ingest(
                    trace_id=f"trace-freight-{shipment_id.lower()}",
                    fact_type=type(fact).__name__,
                    record_id=record_id,
                    source=source,
                )

    def _save_out_of_scope_contract(self, contract: ContractFact) -> AuditCase:
        """Surface unsupported baseline rows without inventing invoice or dock facts."""
        case = AuditCase(
            case_key=CaseKey(
                invoice_id=f"OUT-OF-SCOPE-{contract.shipment_id}",
                shipment_id=contract.shipment_id,
            ),
            carrier_name=contract.carrier,
            bill_of_lading=contract.bill_of_lading,
            match_result=MatchResult(
                is_out_of_scope=True,
                skip_reason=f"Mode {contract.mode.value} is out of v1 scope",
            ),
            disposition=SkippedOutOfScope(
                skip_reason=f"Mode {contract.mode.value} is out of v1 scope"
            ),
        )
        self.store.save_case(case)
        return case

    def match(self, case_key: CaseKey, *, emit_trace: bool = True) -> AuditCase:
        existing_case = self.store.get_case(case_key)
        if existing_case and existing_case.is_terminal:
            return existing_case

        invoice = self.store.invoices.get(case_key.invoice_id)
        if not invoice:
            raise KeyError(f"Invoice {case_key.invoice_id} not found in store")

        contract = self.store.contracts.get(case_key.shipment_id)
        facility = self.store.facilities.get(case_key.shipment_id)
        dock = self.store.docks.get(case_key.shipment_id)

        if not (contract and facility and dock):
            raise KeyError(f"Incomplete facts for shipment {case_key.shipment_id}")

        match_res = match_evidence(invoice, contract, facility, dock)

        if match_res.is_out_of_scope:
            disposition = SkippedOutOfScope(skip_reason=match_res.skip_reason or "Out of scope")
        else:
            policy = self.store.get_policy_for(contract, facility)

            # Check if auto-close applies
            if policy.permits_auto_close(
                dispute_cents=match_res.dispute_total_cents,
                fired_rule_ids=match_res.fired_rule_ids,
                has_unexplained_lines=match_res.has_unexplained_lines,
            ):
                disposition = AutoClosed()
            else:
                disposition = NeedsReview()

        case = AuditCase(
            case_key=case_key,
            carrier_name=contract.carrier,
            bill_of_lading=contract.bill_of_lading,
            match_result=match_res,
            disposition=disposition,
            policy_id=policy.policy_id if not match_res.is_out_of_scope else None,
        )
        self.store.save_case(case)

        # Emit Neatlogs trace span for match_evidence
        ev_hash = compute_evidence_hash({
            "invoice_id": case_key.invoice_id,
            "shipment_id": case_key.shipment_id,
            "billed_total_cents": match_res.billed_total_cents,
            "expected_total_cents": match_res.expected_total_cents,
        })
        trace_id = f"trace-freight-{case_key.shipment_id.lower()}"
        rules_fired = match_res.fired_rule_ids
        if emit_trace:
            tracer.trace_match(
                trace_id=trace_id,
                invoice_id=case_key.invoice_id,
                shipment_id=case_key.shipment_id,
                expected_total_cents=match_res.expected_total_cents,
                dispute_total_cents=match_res.dispute_total_cents,
                rules_fired=rules_fired,
                evidence_hash=ev_hash,
            )
        return case


    def decide(
        self, case_key: CaseKey, action: Union[ApproveShortPay, OverridePayAsBilled]
    ) -> AuditCase:
        case = self.store.get_case(case_key)
        if not case:
            case = self.match(case_key)

        if case.is_terminal:
            if (
                isinstance(case.disposition, ShortPaid)
                and isinstance(action, ApproveShortPay)
                and action.expected_payable_cents
                == case.disposition.approved_payable_cents
            ):
                return case
            if (
                isinstance(case.disposition, PaidAsBilled)
                and isinstance(action, OverridePayAsBilled)
                and action.override_reason == case.disposition.override_reason
            ):
                return case
            raise ValueError("Only NeedsReview cases can be decided")

        if isinstance(action, ApproveShortPay):
            if action.expected_payable_cents != case.match_result.expected_total_cents:
                raise StaleDecisionError(
                    f"Stale payable: requested {action.expected_payable_cents}, expected {case.match_result.expected_total_cents}"
                )

            # Learn lane rules for future auto-close
            contract = self.store.contracts.get(case_key.shipment_id)
            facility = self.store.facilities.get(case_key.shipment_id)
            if contract and facility:
                policy = self.store.get_policy_for(contract, facility)
                policy.record_approved_rules(case.match_result.fired_rule_ids)

            new_disp = ShortPaid(approved_payable_cents=action.expected_payable_cents)
            payable_cents = action.expected_payable_cents
            action_type = "ApproveShortPay"
        elif isinstance(action, OverridePayAsBilled):
            new_disp = PaidAsBilled(override_reason=action.override_reason)
            payable_cents = case.match_result.billed_total_cents
            action_type = "OverridePayAsBilled"
        else:
            raise TypeError("Unsupported action type")

        updated_case = AuditCase(
            case_key=case.case_key,
            carrier_name=case.carrier_name,
            bill_of_lading=case.bill_of_lading,
            match_result=case.match_result,
            disposition=new_disp,
            policy_id=case.policy_id,
        )
        self.store.save_case(updated_case)

        # Emit Neatlogs trace span for human decision
        trace_id = f"trace-freight-{case_key.shipment_id.lower()}"
        tracer.trace_decide(
            trace_id=trace_id,
            invoice_id=case_key.invoice_id,
            shipment_id=case_key.shipment_id,
            action_type=action_type,
            disposition_type=new_disp.disposition_type,
            payable_cents=payable_cents,
        )
        return updated_case


    def cases(self) -> List[AuditCase]:
        return self.store.list_cases()
