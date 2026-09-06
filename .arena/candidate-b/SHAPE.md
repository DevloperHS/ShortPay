# Shape — dual money ledger

Derived from [USAGE.md](./USAGE.md). Types first; signatures second; modules last.

## Invariants (encoded in types)

1. **Invoice is immutable.** `InvoiceDocument` has no setters; ledgers reference it by `content_hash`, never mutate it.
2. **Two ledgers, one join.** There is no `Case` root. `LedgerJoin` *is* the work item.
3. **Money is `Cents`.** Newtype over `int`. No `float` on the public surface.
4. **Variance is a join on `ChargeType`.** Missing expected line ⇒ authorized `0`; missing billed line ⇒ not a dispute (underbill is not short-pay).
5. **`payable_cents = sum(expected)`.** Derived, never stored separately from expected lines.
6. **`DisputePacket` = billed lines where `billed > expected`.** Evidence refs ride on expected lines / join, not on the invoice.
7. **Matcher is pure.** `authorize_expected` takes domain facts only; no I/O, no LLM.
8. **Agents are I/O.** `extract_billed` may call models behind the boundary; its return type is `BilledLedger`, not a model response.
9. **ERP is system of record.** We emit `PayablePosting` + `DisputePacket`; we do not post GL entries ourselves.
10. **Idempotency key = invoice `content_hash` + shipment_id.** Re-extract / re-match / re-join converges.

---

## Type sketch

```python
from dataclasses import dataclass
from enum import Enum
from typing import NewType, Optional, Sequence

Cents = NewType("Cents", int)  # integer cents only
ShipmentId = NewType("ShipmentId", str)
InvoiceId = NewType("InvoiceId", str)
ContentHash = NewType("ContentHash", str)


class ChargeType(Enum):
    BASE_FREIGHT = "BASE_FREIGHT"
    DETENTION = "DETENTION"
    LIFTGATE = "LIFTGATE"
    # v1 accessorials only; FSC / ocean / parcel deliberately absent from public enum


class Mode(Enum):
    LTL = "LTL"
    TL = "TL"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"  # e.g. ocean demurrage row in baseline CSV


@dataclass(frozen=True)
class InvoiceDocument:
    """Immutable carrier invoice source. Parsed at the boundary; never rewritten."""
    invoice_id: InvoiceId
    shipment_id: ShipmentId
    carrier: str
    content_hash: ContentHash
    # raw bytes / path stay private to the load implementation — not on this type


@dataclass(frozen=True)
class BilledLine:
    charge_type: ChargeType
    amount_cents: Cents
    carrier_claim_note: Optional[str]  # e.g. "billed as 60 min"


@dataclass(frozen=True)
class BilledLedger:
    """What the carrier claimed. Built only from InvoiceDocument (+ extract I/O)."""
    invoice_id: InvoiceId
    shipment_id: ShipmentId
    content_hash: ContentHash
    lines: tuple[BilledLine, ...]

    @property
    def total_cents(self) -> Cents: ...  # sum(lines); derived


@dataclass(frozen=True)
class RuleBasis:
    """Human-readable authorization basis for one expected line (accountant-facing)."""
    rule_id: str                 # e.g. "DETENTION_FREE_TIME", "LIFTGATE_DOCK"
    inputs: dict[str, str]       # e.g. {"arrival": "14:12:00", "departure": "15:45:00",
                                 #        "dwell_min": "93", "free_min": "30", "rate": "75.00/hr"}
    narrative: str               # "ceil(63/60)*75 = 75.00"


@dataclass(frozen=True)
class ExpectedLine:
    charge_type: ChargeType
    amount_cents: Cents          # 0 is explicit authorization (e.g. liftgate denied)
    basis: RuleBasis
    evidence_refs: tuple[str, ...]  # dock receipt id, facility master key, …


@dataclass(frozen=True)
class ExpectedLedger:
    """What contract + evidence authorize. Written only by the pure matcher."""
    shipment_id: ShipmentId
    lines: tuple[ExpectedLine, ...]

    @property
    def total_cents(self) -> Cents: ...  # == payable; derived


@dataclass(frozen=True)
class LineVariance:
    charge_type: ChargeType
    billed_cents: Cents          # 0 if carrier did not bill this type
    expected_cents: Cents        # 0 if not authorized
    delta_cents: Cents           # expected - billed (negative => overbill)


@dataclass(frozen=True)
class LedgerJoin:
    """
    The work item. Join of BilledLedger ⨝ ExpectedLedger on ChargeType.
    Not a Case. Not a mutable invoice.
    """
    billed: BilledLedger
    expected: ExpectedLedger
    variances: tuple[LineVariance, ...]

    @property
    def payable_cents(self) -> Cents: ...       # sum(expected)

    @property
    def dispute_cents(self) -> Cents: ...       # sum(max(0, billed - expected) per type)

    @property
    def overbill_charge_types(self) -> tuple[ChargeType, ...]: ...


@dataclass(frozen=True)
class ContractFacts:
    shipment_id: ShipmentId
    carrier: str
    bill_of_lading: str
    agreed_base_rate_cents: Cents
    allowed_dwell_minutes: int
    detention_rate_cents_per_hour: Cents  # demo: 7500
    mode: Mode


@dataclass(frozen=True)
class EvidencePack:
    """Operational facts the matcher needs. Assembled at boundary from dock/facility fixtures."""
    shipment_id: ShipmentId
    arrival_hhmmss: str
    departure_hhmmss: str
    dwell_minutes: int            # precomputed at boundary or derived once; matcher may re-derive
    destination_has_dock: bool


@dataclass(frozen=True)
class DisputeLine:
    charge_type: ChargeType
    billed_cents: Cents
    authorized_cents: Cents
    overage_cents: Cents
    basis: RuleBasis
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class DisputePacket:
    invoice_id: InvoiceId
    shipment_id: ShipmentId
    lines: tuple[DisputeLine, ...]
    total_overage_cents: Cents
    attachment_refs: tuple[str, ...]  # dock receipt, etc.


@dataclass(frozen=True)
class PayablePosting:
    """Proposal to ERP — not a GL entry."""
    invoice_id: InvoiceId
    shipment_id: ShipmentId
    amount_cents: Cents
    original_billed_cents: Cents
    reviewer: str
    action: str  # "short_pay" | "pay_as_billed"


class RouteKind(Enum):
    AUTO_CLOSE = "auto_close"
    ESCALATE = "escalate"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class Route:
    kind: RouteKind
    work: LedgerJoin
    reason: str
    policy_id: Optional[str]  # e.g. "SHORT-PAY-01"


@dataclass(frozen=True)
class LanePolicy:
    """Maximor-shaped: auto-run under threshold when rules previously approved on lane."""
    auto_close_max_variance_cents: Cents  # e.g. 5000
    require_prior_approvals: tuple[str, ...]  # rule_ids that must have been HITL-approved on lane
    lane_key: str


@dataclass(frozen=True)
class KanbanCard:
    column: str
    color_hex: str
    title: str
    subtitle: str
    work: LedgerJoin
```

---

## Function signatures

Bodies are `not implemented`. Docstrings state intent and idempotency.

```python
def InvoiceDocument.load(path: str) -> InvoiceDocument:
    """Parse PDF/EDI/CSV wire at the boundary into an immutable document.
    Raises on unsupported mode payloads that must not enter the ledger path.
    not implemented
    """
    raise NotImplementedError


def extract_billed(invoice: InvoiceDocument) -> BilledLedger:
    """Agent I/O: OCR/LLM extract → BilledLedger.
    Idempotent on invoice.content_hash: same hash ⇒ same ledger (cached or recomputed).
    Never mutates invoice. Public return type has no model/vendor types.
    not implemented
    """
    raise NotImplementedError


def authorize_expected(
    shipment_id: ShipmentId,
    contract: ContractFacts,
    evidence: EvidencePack,
) -> ExpectedLedger:
    """Pure matcher. Deterministic cents from contract + evidence.
    Hero rules (encoded here, not in an LLM):
      - BASE = agreed_base_rate_cents
      - DETENTION = ceil(max(0, dwell - allowed) / 60) * rate_per_hour
      - LIFTGATE = 0 if destination_has_dock else schedule amount (v1: dock ⇒ 0)
    Omits OUT_OF_SCOPE modes (caller filters) — if mode is OUT_OF_SCOPE, raises.
    not implemented
    """
    raise NotImplementedError
    # TODO: detention = ceil_div(max(0, evidence.dwell_minutes - contract.allowed_dwell_minutes), 60)
    #              * contract.detention_rate_cents_per_hour
    # TODO: liftgate ExpectedLine(amount=0, basis=LIFTGATE_DOCK) when has_dock


def join_ledgers(billed: BilledLedger, expected: ExpectedLedger) -> LedgerJoin:
    """Outer join on ChargeType. Invariant: billed.shipment_id == expected.shipment_id.
    payable and dispute are derived properties — not arguments.
    Idempotent: pure function of the two ledgers.
    not implemented
    """
    raise NotImplementedError


def route_join(work: LedgerJoin, policy: LanePolicy) -> Route:
    """Policy over the join. Auto-close when dispute_cents <= threshold AND
    every overbill rule_id has a prior lane approval; else escalate.
    Does not post. Does not mutate ledgers.
    not implemented
    """
    raise NotImplementedError


def approve_short_pay(
    work: LedgerJoin,
    reviewer: str,
) -> tuple[PayablePosting, DisputePacket]:
    """HITL primary action: post ExpectedLedger total; attach dispute for overbills.
    Idempotent on (work.billed.content_hash, action=short_pay): re-approve same join
    yields the same posting proposal.
    not implemented
    """
    raise NotImplementedError


def override_pay_as_billed(
    work: LedgerJoin,
    reason: str,
    reviewer: str,
) -> tuple[PayablePosting, None]:
    """HITL secondary: pay billed total; reason becomes a policy seed (written by shell).
    Does not change ExpectedLedger math — override is a posting choice, not a re-match.
    not implemented
    """
    raise NotImplementedError


def kanban_card(work: LedgerJoin) -> KanbanCard:
    """Projection for the demo board. Major Exceptions + soft rose when dispute_cents > 0.
    not implemented
    """
    raise NotImplementedError


def load_baseline(path: str) -> Sequence[ContractFacts]:
    """Parse controller CSV at boundary → ContractFacts (Mode.OUT_OF_SCOPE for ocean rows).
    not implemented
    """
    raise NotImplementedError


def open_work_items(contract: ContractFacts) -> LedgerJoin:
    """Convenience for batch: load invoice + evidence for shipment, extract, authorize, join.
    Skips / raises cleanly for OUT_OF_SCOPE. Idempotent convergence on content_hash.
    Owns orchestration; still no Case type.
    not implemented
    """
    raise NotImplementedError
```

---

## Module map

Knowledge ownership, not pipeline stages. Three public modules; wire/vendor stays private.

```
freight_audit/
  __init__.py          # re-exports public surface only (types + fns above)
  money.py             # Cents, ChargeType, money helpers (sum, ceil_div)
  ledgers.py           # BilledLedger, ExpectedLedger, LedgerJoin, LineVariance
                       # join_ledgers, approve_short_pay, override_pay_as_billed,
                       # DisputePacket / PayablePosting builders
  match.py             # authorize_expected + RuleBasis construction (PURE)
  policy.py            # LanePolicy, Route, route_join
  board.py             # kanban_card projection
  _boundary/           # PRIVATE — parse wire, agent I/O, fixtures
    invoice_load.py    # PDF/EDI → InvoiceDocument
    extract.py         # TensorMux-backed extract_billed adapter
    baseline_csv.py    # load_baseline
    evidence.py        # dock log + facility master → EvidencePack
    erp_propose.py     # serialize PayablePosting / DisputePacket outbound
```

**Call chain for the hero path (≤3 hops):**

`extract_billed` → `authorize_expected` → `join_ledgers` → (`route_join` | `approve_short_pay`)

Policy and board read `LedgerJoin`; they do not re-implement variance.

---

## Deliberately rejected (named)

| Rejected | Why |
|---|---|
| `Case` / `AuditCase` as root aggregate | The join *is* the work item; a Case becomes a second mutable source of truth beside the ledgers. |
| Mutating invoice status fields (`audited`, `short_paid`) | Violates immutable-source invariant; ERP owns payment state. |
| Single blended ledger with `status=billed\|expected` rows | Collapses the two truths; variance stops being a join. |
| Agent-owned domain model (LLM emits payable cents) | Matcher math must be pure and reproducible; models extract claims only. |
| Temporal modules: `ingest/`, `extract/`, `match/`, `decide/`, `act/` as public packages | Temporal decomposition; same types leak across five boundaries. |
| Public `TensorMuxResponse`, `S3Object`, `PdfJson` | Information leakage; parse at `_boundary`. |
| Float dollars | Grounding constraint; cents only. |
| Ocean demurrage / parcel DIM in v1 `ChargeType` | Broadens rules until they look fake; `Mode.OUT_OF_SCOPE` skips cleanly. |
| Pass-through `AuditService.short_pay()` that only forwards to `approve_short_pay` | Shallow module; callers use `approve_short_pay` directly. |

---

## Hero numbers (must hold after fill-in)

```
billed.total_cents     == 112_000
expected.total_cents   ==  92_500   # 85000 + 7500
work.payable_cents     ==  92_500
work.dispute_cents     ==  19_500   # 9500 liftgate + 10000 detention
DETENTION expected     ==   7_500   # ceil(63/60)*75
LIFTGATE expected      ==       0
```
