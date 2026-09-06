# Shortpay architecture

Synthesized from two arena sketches. Rationale and the pick are in [architecture-rationale.md](architecture-rationale.md). Product intent is in [prd.md](prd.md).

Public surface is small: ingest facts, match, decide. Inside the case sit two frozen ledgers. Agents parse wire. They do not own money.

## Usage (caller's view)

```python
from shortpay import (
    AuditOffice,
    CaseKey,
    InvoiceId,
    ShipmentId,
    Money,
    Minutes,
    ChargeType,
    ApproveShortPay,
    OverridePayAsBilled,
    NeedsReview,
    ShortPaid,
    contract_terms,
    facility,
    dock_dwell,
    invoice_fact,
    invoice_line,
)

office = AuditOffice.in_memory()
office.ingest([
    contract_terms(
        shipment_id=ShipmentId("SHP-88220"),
        carrier="FedEx Freight",
        bol="BOL-US-99121",
        mode="LTL",
        agreed_base_rate=Money(85_000),
        allowed_dwell=Minutes(30),
        detention_rate_per_hour=Money(7_500),
    ),
    facility(shipment_id=ShipmentId("SHP-88220"), destination_has_dock=True),
    dock_dwell(
        shipment_id=ShipmentId("SHP-88220"),
        arrived_at="14:12:00",
        departed_at="15:45:00",
    ),
    invoice_fact(
        invoice_id=InvoiceId("INV-FRT-2026-09"),
        shipment_id=ShipmentId("SHP-88220"),
        carrier="FedEx Freight",
        lines=(
            invoice_line(ChargeType.BASE_FREIGHT, Money(85_000)),
            invoice_line(ChargeType.DETENTION, Money(17_500), billed_minutes=Minutes(60)),
            invoice_line(ChargeType.LIFTGATE, Money(9_500)),
        ),
    ),
])

key = CaseKey(InvoiceId("INV-FRT-2026-09"), ShipmentId("SHP-88220"))
case = office.match(key)
assert case.expected.total_cents == 92_500
assert case.dispute_cents == 19_500
assert isinstance(case.disposition, NeedsReview)

case = office.decide(key, ApproveShortPay(expected_payable=Money(92_500)))
assert isinstance(case.disposition, ShortPaid)
```

Kanban is a projection of `office.cases()`. Extractors call `invoice_fact`, never `match`.

## Data shape

The root the board hangs on is `AuditCase`, keyed by `(invoice_id, shipment_id)`. That is the AP work item.

Inside the case, truth is two ledgers plus a join. The carrier invoice is immutable. Expected money is a separate ledger. Variance is an outer join on `ChargeType`. Payable is `sum(expected)`. Dispute lines are billed where billed > expected.

Disposition is a sum type. Unmatched is `None`, not a fake `Open`.

```
                    harvest / UI / demo
                            |
                            v
                      AuditOffice
                   ingest, match, decide
                            |
              +-------------+-------------+
              v             v             v
         CaseStore     AuditCase      match_evidence
         (facts +      (ledgers +     (pure)
          snapshots)    disposition)
              ^             ^
              |             |
         adapters      PolicyBook
         (wire→facts)
```

### Money and time

```python
@dataclass(frozen=True)
class Money:
    cents: int  # reject bool and float

@dataclass(frozen=True)
class Minutes:
    value: int  # >= 0
```

Derived, never ingested:

- Dock dwell from arrival and departure.
- Invoice billed total from billed lines.
- Liftgate authorization from `destination_has_dock`.
- Payable from expected lines.

### Facts (append-only)

```python
ChargeType = BASE_FREIGHT | DETENTION | LIFTGATE | OTHER
Mode = LTL | TL | OCEAN | PARCEL

InvoiceFact     # identity + billed lines (cents). billed_total derived.
DockDwellFact   # arrival, departure, dwell derived. Same-day only in v1.
FacilityFact    # destination_has_dock
ContractFact    # mode, base rate, free time, detention $/hour
```

A case is born when `InvoiceFact` arrives. Contract, dock, and facility may already exist on the shipment.

### Ledgers (inside the case)

```python
BilledLedger    # carrier claims. content_hash of the invoice.
ExpectedLedger  # matcher output. Liftgate $0 is an explicit line when dock is present.
LedgerJoin      # outer join on ChargeType. payable and dispute are properties.
```

`UnexplainedLine` is a billed line the matcher cannot authorize (missing dock clock, unmapped charge). Unexplained lines are excluded from `expected_total` and they block auto-close.

### Disposition

```python
Disposition = AutoClosed | NeedsReview | ShortPaid | PaidAsBilled | SkippedOutOfScope
```

`NeedsReview` is the only state `decide` accepts.

`ApproveShortPay(expected_payable=...)` must equal current `expected_total` or raise `StaleDecision`.

`OverridePayAsBilled(reason=...)` posts billed total. It does not rewrite `ExpectedLedger`.

Terminal + same action = no-op. Terminal + other action = `IllegalTransition`. A revised invoice is a new `invoice_id`.

### Policy

```python
SHORT-PAY-01:
  auto_close if dispute_cents <= 5000
             and every fired overbill rule_id is in prior_approved_rules
             for LaneKey(carrier, mode, destination_has_dock)
```

`decide(ShortPaid)` appends those rule ids to the lane book. That is how the product learns.

## Matcher rules (pure)

`match_evidence(facts) -> Assertions` has no I/O.

Hero lock, as a test, before UI:

| Charge | Billed | Expected | Delta |
| --- | ---: | ---: | ---: |
| BASE_FREIGHT | 85000 | 85000 | 0 |
| LIFTGATE | 9500 | 0 | -9500 |
| DETENTION | 17500 | 7500 | -10000 |
| totals | 112000 | 92500 | 19500 |

Detention: `billable = max(0, dwell - allowed)`; `hours = billable // 60`; `authorized = hours * rate`. Hero: 63 minutes, 1 hour, $75.00.

Liftgate: dock present ⇒ expected 0.

Scope: `mode` not LTL or TL ⇒ `SkippedOutOfScope`, no dwell math.

## Module map

Knowledge ownership, not pipeline stages.

```
shortpay/
  money.py          Money, Minutes
  evidence.py       facts, constructors (validate at the edge)
  ledgers.py        BilledLedger, ExpectedLedger, join
  matching.py       match_evidence, completed_detention_hours
  policy.py         LaneKey, SHORT-PAY-01 snapshot
  case.py           AuditCase, Disposition, Decision, DisputePacket, PayablePosting
  store.py          CaseStore protocol, InMemoryStore
  office.py         AuditOffice
  adapters/         not exported from __init__
    baseline_csv.py
    invoice_extract.py   TensorMux lives only here
    dock_log.py
    facility_master.py
    erp_propose.py
```

Call chain for the hero: `ingest` → `match` → `decide`. That is three hops. Policy and board read the case. They do not recompute detention.

## Boundaries

| Crossing | Parse into | Keep private |
| --- | --- | --- |
| Controller CSV | `ContractFact` | row dicts, filename |
| Invoice PDF | `InvoiceFact` via extractor | TensorMux response, PDF JSON |
| Dock log | `DockDwellFact` | IoT payload, S3 URI |
| Facility master | `FacilityFact` | TMS tables |
| ERP | `PayablePosting`, `DisputePacket` | NetSuite vendor bill objects |

Hunter and extractor are adapters. If they disappear, `AuditOffice.ingest` still makes sense with hand-built facts. That is the test that the swarm is not the architecture.

## Idempotency

- Fact identity: one invoice per `(invoice_id, shipment_id)`, one dwell per shipment, one facility per shipment, one contract per shipment.
- Same values, re-ingest: no-op.
- Different values on a non-terminal case: replace fact, rematch.
- Terminal case: facts do not reopen it in v1. New invoice id, new case.
- `match` is a pure function of current facts. Re-run converges.
- `decide` with the same action on a terminal case is a no-op.

## Observability

Neatlogs wraps `AuditOffice` methods and adapter calls. Domain types do not import Neatlogs.

Hero trace id: `trace-freight-shp-88220`.

Spans at minimum:

- `extract_billed` (TensorMux child span)
- `match_evidence` with rule fires
- `decide`

Evidence pack hash is SHA-256 of canonical JSON of the facts used in `match`. Store it on the case snapshot so a later auditor can see what the $75 was computed from.

## Demo runtime

Local fixtures, in-memory store, one page Kanban + modal. TensorMux is optional if the extractor adapter can return the fixture billed lines when the key is missing. The matcher test must pass without TensorMux.

ERP is a mock that records `PayablePosting(amount_cents=92500)` and a dispute email preview.

## First implementation step

`Money`, `Minutes`, evidence constructors, `match_evidence`, and a single test that locks SHP-88220 at 92500 / 19500. No office, no UI, no TensorMux until that test is green.
