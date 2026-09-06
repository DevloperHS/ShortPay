# Shape — AuditCase aggregate + AP disposition state machine

Derived from [USAGE.md](USAGE.md). If they disagree, the usage wins.

Language of the sketch: Python 3.12. Bodies stay `raise NotImplementedError`. This is the contract, not the product.

---

## Invariants encoded in types

- Money is `Money(cents: int)`. Float construction is a type error. Variance may be negative.
- Time is `Minutes`. Dock dwell is **derived** from arrival/departure; it is not an ingest field.
- Invoice billed total is **derived** from lines; it is not an ingest field.
- Liftgate authorization is **derived** from `destination_has_dock`; it is not a contract flag (that would be a second source of truth).
- `Disposition` has no `Open`. Unmatched cases have `disposition is None`.
- Terminal dispositions: `AutoClosed | ShortPaid | PaidAsBilled | SkippedOutOfScope`. `NeedsReview` is the only state `decide` accepts.
- `ApproveShortPay` carries `expected_payable` so a stale UI cannot mint a new amount.
- Agents, inference, object storage, and CSV rows do not appear below the public exports.

---

## Module map

Knowledge ownership, not execution order. Tracing the hero is three files after the office: `evidence` (facts) → `matching` (assertions) → `case` (disposition + packet). `policy` is a snapshot the office passes into `case.propose_disposition`; it is not its own stop on the happy path.

```
freight_audit/
  __init__.py          public re-exports only (see bottom)
  money.py             Money, Minutes
  evidence.py          facts, FactId, constructors (boundary validation)
  matching.py          pure matcher: evidence → Assertions; scope skip; hero math
  policy.py            SHORT-PAY-01 snapshot + lane approval book
  case.py              CaseKey, AuditCase, Disposition, Decision, DisputePacket, transitions
  store.py             CaseStore protocol, InMemoryStore (no buckets)
  office.py            AuditOffice: ingest / match / decide / get / cases
  adapters/            parse wire → Evidence; not re-exported from __init__
    baseline_csv.py
    invoice_extract.py
    dock_log.py
    facility_master.py
```

Rejected layout (do not add): `ingest.py`, `validate.py`, `transform.py`, `save.py`, `agents/hunter.py`, `agents/extractor.py` as architecture, `tensormux.py` on the public path.

```
                    UI / demo / harvest script
                              |
                              v
                       AuditOffice          commands: ingest, match, decide
                              |             queries:  get, cases
              +---------------+---------------+
              v               v               v
         CaseStore       AuditCase         Matcher
         (facts +        (state            (pure)
          snapshots)      machine)
                              ^               |
                              |               v
                         EvidenceLog       PolicyBook
                              ^
                              |
                         adapters (wire → facts)
```

---

## Types

### money.py

```python
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, order=True)
class Money:
    """Integer cents. Never float. Negative is a legal variance."""
    cents: int

    def __post_init__(self) -> None:
        if isinstance(self.cents, bool) or not isinstance(self.cents, int):
            raise TypeError("Money.cents must be int")

    def __add__(self, other: Money) -> Money:
        raise NotImplementedError

    def __sub__(self, other: Money) -> Money:
        raise NotImplementedError

    def __mul__(self, n: int) -> Money:
        """n is a count (hours, lines). Not a float rate."""
        raise NotImplementedError

    def display(self) -> str:
        """Accountant copy: '$195.00'. Sign on the dollar, not a float."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True, order=True)
class Minutes:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError("Minutes.value must be int")
        if self.value < 0:
            raise ValueError("Minutes cannot be negative")

    def __sub__(self, other: Minutes) -> Minutes:
        raise NotImplementedError
```

### evidence.py

Facts are append-only by `FactId`. Re-ingest of the same identity with the same values is a no-op. Different values replace the fact and stale unmatched assertions (terminal cases do not reopen in v1).

Shipment-scoped facts (contract, facility, dwell) exist without a case. A case is **born** when an `InvoiceFact` arrives.

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import NewType, Union

from freight_audit.money import Money, Minutes

InvoiceId = NewType("InvoiceId", str)
ShipmentId = NewType("ShipmentId", str)
FactId = NewType("FactId", str)


class Mode(StrEnum):
    LTL = "LTL"
    TL = "TL"
    OCEAN = "OCEAN"
    PARCEL = "PARCEL"


class ChargeCode(StrEnum):
    BASE_FREIGHT = "BASE_FREIGHT"
    DETENTION = "DETENTION_SURCHARGE"
    LIFTGATE = "LIFTGATE"
    OTHER = "OTHER"


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    charge: ChargeCode
    billed: Money
    billed_minutes: Minutes | None  # carrier's claim; matcher does not trust it


def invoice_line(
    charge: ChargeCode,
    billed: Money,
    billed_minutes: Minutes | None = None,
) -> InvoiceLine:
    raise NotImplementedError


@dataclass(frozen=True, slots=True)
class InvoiceFact:
    invoice_id: InvoiceId
    shipment_id: ShipmentId
    carrier: str
    bol: str
    lines: tuple[InvoiceLine, ...]
    billed_total: Money  # derived = sum(lines.billed); hero 1120.00


@dataclass(frozen=True, slots=True)
class DockDwellFact:
    shipment_id: ShipmentId
    arrived_at: time
    departed_at: time
    dwell: Minutes  # derived; hero 93. Same-day clock. Overnight is rejected at this constructor.


@dataclass(frozen=True, slots=True)
class FacilityFact:
    shipment_id: ShipmentId
    destination_has_dock: bool


@dataclass(frozen=True, slots=True)
class ContractFact:
    shipment_id: ShipmentId
    carrier: str
    bol: str
    mode: Mode
    agreed_base_rate: Money
    allowed_dwell: Minutes
    detention_rate_per_hour: Money
    # v1: no fuel field. CSV fuel column is dropped at the adapter.


Evidence = Union[InvoiceFact, DockDwellFact, FacilityFact, ContractFact]


def invoice_fact(
    *,
    invoice_id: InvoiceId,
    shipment_id: ShipmentId,
    carrier: str,
    bol: str,
    lines: tuple[InvoiceLine, ...],
) -> InvoiceFact:
    """Validates non-empty lines; sets billed_total from the sum."""
    raise NotImplementedError


def dock_dwell(
    *,
    shipment_id: ShipmentId,
    arrived_at: time,
    departed_at: time,
) -> DockDwellFact:
    """dwell = departed_at - arrived_at in minutes. No dwell argument exists."""
    raise NotImplementedError


def facility(*, shipment_id: ShipmentId, destination_has_dock: bool) -> FacilityFact:
    raise NotImplementedError


def contract_terms(
    *,
    shipment_id: ShipmentId,
    carrier: str,
    bol: str,
    mode: Mode,
    agreed_base_rate: Money,
    allowed_dwell: Minutes,
    detention_rate_per_hour: Money,
) -> ContractFact:
    raise NotImplementedError


def fact_id(fact: Evidence) -> FactId:
    """Identity for idempotent upsert. One invoice per (invoice_id, shipment_id), one dwell per shipment, ..."""
    raise NotImplementedError
```

### matching.py

Pure. No I/O. No office. LLM output is not an input.

Hero lock (must pass as a unit test before UI exists):

| Line | Billed | Authorized | Variance |
|---|---|---|---|
| BASE_FREIGHT | 85000 | 85000 | 0 |
| LIFTGATE | 9500 | 0 | -9500 |
| DETENTION | 17500 | 7500 | -10000 |
| **totals** | **112000** | **92500** | ledger delta **19500** |

Detention: `billable = max(0, 93 - 30) = 63`; `hours = 63 // 60 = 1`; `1 * 7500 = 7500`. Named `completed_hours`, not `ceil`. The controller packet’s `ceil(63/60) = 75.00` is a broken token; the locked dollar is $75.00.

Liftgate: `destination_has_dock ⇒ authorized = 0`. No contract boolean.

Scope: `mode not in {LTL, TL}` ⇒ `Assertions.in_scope is False`. No detention math on ocean.

Missing dock or facility ⇒ that line is `UnexplainedLine`, never a model-invented authorized amount. Any unexplained line blocks auto-close.

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence, Union

from freight_audit.evidence import ChargeCode, Evidence
from freight_audit.money import Money, Minutes


class RuleId(StrEnum):
    SCOPE = "SCOPE"
    BASE_RATE = "BASE_RATE"
    LIFTGATE_DOCK_PRESENT = "LIFTGATE_DOCK_PRESENT"
    DETENTION_HOURS = "DETENTION_HOURS"


@dataclass(frozen=True, slots=True)
class RuleFire:
    """For traces (Neatlogs wraps the office; it does not sit in this type)."""
    rule_id: RuleId
    inputs: tuple[tuple[str, str], ...]  # already rendered; no raw wire
    output: str


@dataclass(frozen=True, slots=True)
class ExplainedLine:
    charge: ChargeCode
    billed: Money
    authorized: Money
    variance: Money  # authorized - billed; negative = overbill
    basis: str       # accountant sentence, e.g. "dock present ⇒ liftgate $0"
    rule_id: RuleId


@dataclass(frozen=True, slots=True)
class UnexplainedLine:
    charge: ChargeCode
    billed: Money
    missing: str     # "dock dwell timestamps required to authorize detention"


LineAssertion = Union[ExplainedLine, UnexplainedLine]


@dataclass(frozen=True, slots=True)
class Assertions:
    lines: tuple[LineAssertion, ...]
    billed_total: Money
    expected_total: Money  # sum of authorized BASE + DETENTION + LIFTGATE only
    ledger_delta: Money    # billed_total - expected_total; hero 19500
    in_scope: bool
    skip_reason: str | None
    rule_fires: tuple[RuleFire, ...]


def completed_detention_hours(billable: Minutes) -> int:
    """Hero: 63 → 1. Integer floor hours. See RATIONALE open questions."""
    raise NotImplementedError


def match_evidence(facts: Sequence[Evidence]) -> Assertions:
    """
    Merge facts for one invoice+shipment (caller already scoped).
    Requires InvoiceFact + ContractFact; facility/dwell optional.
    Does not choose Disposition — see case.propose_disposition.
    """
    raise NotImplementedError
```

`expected_total` does not include `OTHER` / unexplained billed amounts. `ApproveShortPay` pays `expected_total`. Extra lines stay visible for the human; they are not silently paid.

### policy.py

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

from freight_audit.evidence import Mode
from freight_audit.matching import RuleId
from freight_audit.money import Money


@dataclass(frozen=True, slots=True)
class LaneKey:
    carrier: str
    mode: Mode
    destination_has_dock: bool


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    policy_id: str  # "SHORT-PAY-01"
    max_auto_overbill: Money  # $50.00 = Money(5_000)
    required_prior_rules: frozenset[RuleId]
    lane: LaneKey
    prior_approved_rules: frozenset[RuleId]


SHORT_PAY_01 = PolicySnapshot(
    policy_id="SHORT-PAY-01",
    max_auto_overbill=Money(5_000),
    required_prior_rules=frozenset(
        {RuleId.LIFTGATE_DOCK_PRESENT, RuleId.DETENTION_HOURS}
    ),
    lane=...,  # filled per case
    prior_approved_rules=frozenset(),
)


class PolicyBook(Protocol):
    def snapshot(self, lane: LaneKey) -> PolicySnapshot:
        raise NotImplementedError

    def record_short_pay(self, lane: LaneKey, rules: frozenset[RuleId]) -> None:
        """Called after human ShortPaid. Next time, auto-close may fire."""
        raise NotImplementedError
```

Auto-close fires only when `in_scope` and every line is `ExplainedLine` and `ledger_delta <= max_auto_overbill` (overbill, so delta ≥ 0 and ≤ $50) **and** both required rules are in `prior_approved_rules`. Hero $195 never auto-closes. Underbill (negative delta) is always `NeedsReview` in v1.

### case.py

Packet types live here so `ShortPaid` / `AutoClosed` do not import a satellite module, and so `matching.py` never imports the state machine. This product does not post ERP. `proposed_erp_payable` is what a later adapter may write. Building the packet twice yields the same packet.

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union

from freight_audit.evidence import Evidence, FactId, InvoiceId, ShipmentId
from freight_audit.matching import Assertions, LineAssertion
from freight_audit.money import Money
from freight_audit.policy import PolicySnapshot


@dataclass(frozen=True, slots=True)
class CaseKey:
    carrier_invoice_id: InvoiceId
    shipment_id: ShipmentId


@dataclass(frozen=True, slots=True)
class AttachmentRef:
    """Points at evidence already on the case. Not a URL."""
    kind: Literal["dock_receipt", "invoice", "facility_master", "contract"]
    fact_id: FactId


@dataclass(frozen=True, slots=True)
class DisputePacket:
    case_key: CaseKey
    billed: Money
    proposed_erp_payable: Money
    lines: tuple[LineAssertion, ...]
    attachments: tuple[AttachmentRef, ...]
    notice: str


@dataclass(frozen=True, slots=True)
class AutoClosed:
    policy_id: str
    payable: Money
    packet: DisputePacket


@dataclass(frozen=True, slots=True)
class NeedsReview:
    proposed_payable: Money
    title: str      # "FedEx Freight - SHP-88220"
    subtitle: str   # "Overbilled by $195.00 (Liftgate + Detention)"


@dataclass(frozen=True, slots=True)
class ShortPaid:
    payable: Money
    packet: DisputePacket
    actor: str  # "human"


@dataclass(frozen=True, slots=True)
class PaidAsBilled:
    payable: Money  # == billed_total
    override_reason: str
    actor: str


@dataclass(frozen=True, slots=True)
class SkippedOutOfScope:
    reason: str  # "ocean — v1 is LTL/TL accessorial and detention"
    mode: str


Disposition = Union[AutoClosed, NeedsReview, ShortPaid, PaidAsBilled, SkippedOutOfScope]


@dataclass(frozen=True, slots=True)
class ApproveShortPay:
    expected_payable: Money


@dataclass(frozen=True, slots=True)
class OverridePayAsBilled:
    expected_billed: Money
    reason: str  # non-empty; constructors reject blank


Decision = Union[ApproveShortPay, OverridePayAsBilled]


class IllegalTransition(Exception):
    """decide() on a non-NeedsReview case. match() on a terminal case is a no-op read, not this error."""


class StaleDecision(Exception):
    """expected_payable / expected_billed does not match current assertions."""


class CaseNotFound(Exception):
    """match/decide/get before an InvoiceFact exists for the key."""


class IncompleteCase(Exception):
    """match() without InvoiceFact+ContractFact. Missing dock is not this error."""


def build_packet(key: CaseKey, assertions: Assertions, evidence: tuple[Evidence, ...]) -> DisputePacket:
    """Pure. Attachments are refs to facts already ingested, never bytes or paths."""
    raise NotImplementedError


@dataclass(frozen=True, slots=True)
class AuditCase:
    key: CaseKey
    carrier: str
    bol: str
    evidence: tuple[Evidence, ...]
    assertions: Assertions | None
    disposition: Disposition | None  # None = ingested, unmatched

    def dwell_evidence(self):
        """The DockDwellFact or None. UI shows timestamps from here, not from assertions."""
        raise NotImplementedError

    def facility_evidence(self):
        raise NotImplementedError

    def apply_match(self, assertions: Assertions, disposition: Disposition) -> AuditCase:
        """
        Legal: disposition is None, or current is NeedsReview (evidence changed, rematch).
        Terminal (AutoClosed/ShortPaid/PaidAsBilled/SkippedOutOfScope): return self unchanged.
        """
        raise NotImplementedError

    def apply_decision(self, action: Decision) -> AuditCase:
        """
        NeedsReview + ApproveShortPay(expected==proposed_payable) → ShortPaid
        NeedsReview + OverridePayAsBilled(expected==billed, reason) → PaidAsBilled
        Same decision against the same terminal case → self (idempotent)
        Anything else → IllegalTransition / StaleDecision
        """
        raise NotImplementedError


def propose_disposition(
    case: AuditCase,
    assertions: Assertions,
    policy: PolicySnapshot,
) -> Disposition:
    """
    SkippedOutOfScope | AutoClosed | NeedsReview.
    AutoClosed builds the packet here so the office does not fill fields.
    NeedsReview title/subtitle are derived (hero subtitle locked).
    """
    raise NotImplementedError
```

State machine:

```
  ingest InvoiceFact
        |
        v
  disposition is None
        |
      match
        |
        +-- mode out of scope ----------> SkippedOutOfScope   (terminal)
        +-- policy SHORT-PAY-01 --------> AutoClosed          (terminal, packet built)
        +-- otherwise ------------------> NeedsReview
                                              |
                         decide(ApproveShortPay) --> ShortPaid      (terminal, packet built)
                         decide(Override...)     --> PaidAsBilled   (terminal)
```

There is no transition from `ShortPaid` back to `NeedsReview` in v1. A revised carrier invoice is a **new** `CaseKey`.

### store.py

```python
from __future__ import annotations
from typing import Protocol, Sequence

from freight_audit.case import AuditCase, CaseKey
from freight_audit.evidence import Evidence


class CaseStore(Protocol):
    def upsert_facts(self, facts: Sequence[Evidence]) -> None:
        raise NotImplementedError

    def facts_for_invoice(self, key: CaseKey) -> tuple[Evidence, ...]:
        """InvoiceFact for the key plus shipment-scoped facts for key.shipment_id."""
        raise NotImplementedError

    def put_case(self, case: AuditCase) -> None:
        raise NotImplementedError

    def get_case(self, key: CaseKey) -> AuditCase | None:
        raise NotImplementedError

    def list_cases(self) -> tuple[AuditCase, ...]:
        raise NotImplementedError


class InMemoryStore:
    """Demo store. SqliteStore can implement the same protocol on Monday. Not a bucket."""

    def upsert_facts(self, facts: Sequence[Evidence]) -> None:
        raise NotImplementedError

    def facts_for_invoice(self, key: CaseKey) -> tuple[Evidence, ...]:
        raise NotImplementedError

    def put_case(self, case: AuditCase) -> None:
        raise NotImplementedError

    def get_case(self, key: CaseKey) -> AuditCase | None:
        raise NotImplementedError

    def list_cases(self) -> tuple[AuditCase, ...]:
        raise NotImplementedError
```

Facts from hunter and extractor land in the evidence log independently. `match` is the merge-at-read. Two writers on the same `FactId`: last upsert wins; values equal ⇒ no-op. Two writers on disposition: the state machine makes one of them illegal; the loser retries and sees `IllegalTransition` or idempotent success.

### office.py — public surface

```python
from __future__ import annotations
from typing import Sequence

from freight_audit.case import AuditCase, CaseKey, Decision
from freight_audit.evidence import Evidence
from freight_audit.policy import PolicyBook
from freight_audit.store import CaseStore


class AuditOffice:
    def __init__(self, store: CaseStore, policy_book: PolicyBook) -> None:
        raise NotImplementedError

    @classmethod
    def in_memory(cls) -> AuditOffice:
        raise NotImplementedError

    def ingest(self, facts: Sequence[Evidence]) -> tuple[CaseKey, ...]:
        """
        Upsert facts by FactId. Birth a case (disposition None) for each InvoiceFact.
        Returns keys born or updated. Shipment-only facts return no key.
        Idempotent. Does not match. Does not call inference.
        """
        raise NotImplementedError

    def match(self, key: CaseKey) -> AuditCase:
        """
        Load merged evidence, run match_evidence, propose_disposition (packet
        included on AutoClosed), persist. Terminal cases: return as stored.
        Missing invoice+contract: IncompleteCase.
        """
        raise NotImplementedError

    def decide(self, key: CaseKey, action: Decision) -> AuditCase:
        """
        Human fork from NeedsReview. Builds packet on ShortPaid.
        Records lane approvals on ShortPaid so later match can AutoClose.
        Does not post ERP.
        """
        raise NotImplementedError

    def get(self, key: CaseKey) -> AuditCase:
        raise NotImplementedError

    def cases(self) -> tuple[AuditCase, ...]:
        """Kanban source. UI maps disposition → column; domain does not know #FCE8E6."""
        raise NotImplementedError
```

Interface depth: three commands hide fact-identity merge, four-way match math, policy auto-close, packet assembly, and legal transitions. Callers pass facts and one of two decisions. They do not sequence line rules.

`get` / `cases` are queries over the same aggregate, not extra architecture.

---

## Public exports (`freight_audit/__init__.py`)

```python
from freight_audit.office import AuditOffice
from freight_audit.case import (
    CaseKey,
    ApproveShortPay,
    OverridePayAsBilled,
    AutoClosed,
    NeedsReview,
    ShortPaid,
    PaidAsBilled,
    SkippedOutOfScope,
    IllegalTransition,
    StaleDecision,
    CaseNotFound,
    IncompleteCase,
)
from freight_audit.evidence import (
    InvoiceId,
    ShipmentId,
    ChargeCode,
    Mode,
    invoice_fact,
    invoice_line,
    dock_dwell,
    facility,
    contract_terms,
)
from freight_audit.money import Money, Minutes
```

`freight_audit.adapters` is importable for the demo harness and explicitly not a domain module. Adapter functions accept `Path` / `bytes` and return `Evidence`. Inference clients and bucket clients are constructed inside those modules, never taken as arguments on `AuditOffice`.

---

## Dominant access patterns (structure must answer these without a later index)

1. **Hero invoice, one case.** Keyed by `(invoice_id, shipment_id)`. Evidence log + case snapshot. Direct lookup.
2. **Kanban of everything ingested.** `list_cases` — demo-sized; Monday can still be a full table scan until volume forces a column index on disposition, which is a store concern, not a domain type.
3. **Attach dock/facility/contract by shipment to whatever invoice arrives.** `facts_for_invoice` joins shipment-scoped facts at match. No duplicated copies on the case except the snapshot tuple for the accountant’s evidence pane.
4. **Lane auto-close.** `PolicyBook` keyed by `LaneKey`, not a scan of all historical cases at match time.

---

## Red-flag screen (this candidate)

| Flag | Verdict |
|---|---|
| Shallow module | Rejected for this shape. `AuditOffice` is three commands; policy, math, and packets stay behind it. |
| Information leakage | Wire types, inference, buckets stay in `adapters/`. `AttachmentRef` is a `FactId`, not a URL. |
| Temporal decomposition | No ingest/validate/transform/save packages. Modules own money, evidence, match rules, policy, case transitions. |
| Pass-through | `AuditOffice.match` loads, matches, proposes disposition, maybe builds a packet, persists. `AuditCase.apply_match` enforces the machine. Neither is a one-line forwarder. |
| Agents as architecture | Hunter/extractor are adapters. They produce `Evidence`. They do not sit on the call path as orchestrators. |

---

## What this system deliberately does not do

- Become the GL / post ERP.
- Audit ocean demurrage or parcel DIM.
- Compute fuel surcharge in v1 (CSV column dropped).
- Let a human type the payable.
- Let an LLM emit authorized cents.
- Reopen a terminal case when new facts arrive (v1). Revised invoice = new key.
- Expose `learn()`. Short-pay records lane approvals inside `decide`.
