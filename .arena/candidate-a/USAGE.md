# freight_audit — caller’s view

AP pre-pay audit for LTL/TL accessorials and detention. One aggregate (`AuditCase`), three commands (`ingest`, `match`, `decide`). The product proposes a payable and a dispute packet. ERP remains the ledger.

Money is integer cents. Time is minutes. Wire formats (CSV, PDF, dock logs, object storage, inference APIs) stop at adapters. Callers never import them.

```python
from freight_audit import (
    AuditOffice,
    CaseKey,
    InvoiceId,
    ShipmentId,
    Money,
    Minutes,
    ChargeCode,
    Mode,
    ApproveShortPay,
    OverridePayAsBilled,
    NeedsReview,
    ShortPaid,
    PaidAsBilled,
    SkippedOutOfScope,
    AutoClosed,
    invoice_fact,
    invoice_line,
    dock_dwell,
    facility,
    contract_terms,
)
```

`AuditOffice` is the whole public write surface. Reads are `get` and `cases` on the same object.

---

## Quickstart (hero path)

FedEx Freight `SHP-88220` / `INV-FRT-2026-09`. After `match`, the case is `NeedsReview` with expected payable **$925.00** and ledger delta **$195.00**. After `decide(ApproveShortPay)`, it is `ShortPaid` with a dock-receipt packet. No one types a dollar amount.

```python
from datetime import time

office = AuditOffice.in_memory()  # Monday: AuditOffice(store=SqliteStore(path))

keys = office.ingest(
    [
        contract_terms(
            shipment_id=ShipmentId("SHP-88220"),
            carrier="FedEx Freight",
            bol="BOL-US-99121",
            mode=Mode.LTL,
            agreed_base_rate=Money(85_000),
            allowed_dwell=Minutes(30),
            detention_rate_per_hour=Money(7_500),
        ),
        facility(
            shipment_id=ShipmentId("SHP-88220"),
            destination_has_dock=True,
        ),
        dock_dwell(
            shipment_id=ShipmentId("SHP-88220"),
            arrived_at=time(14, 12, 0),
            departed_at=time(15, 45, 0),
        ),  # dwell is 93 minutes, derived — not passed in
        invoice_fact(
            invoice_id=InvoiceId("INV-FRT-2026-09"),
            shipment_id=ShipmentId("SHP-88220"),
            carrier="FedEx Freight",
            bol="BOL-US-99121",
            lines=(
                invoice_line(ChargeCode.BASE_FREIGHT, Money(85_000)),
                invoice_line(
                    ChargeCode.DETENTION,
                    Money(17_500),
                    billed_minutes=Minutes(60),
                ),
                invoice_line(ChargeCode.LIFTGATE, Money(9_500)),
            ),
        ),
    ]
)

key = CaseKey(InvoiceId("INV-FRT-2026-09"), ShipmentId("SHP-88220"))
assert keys == (key,)

case = office.match(key)

assert case.assertions.expected_total == Money(92_500)   # 850 + 75 + 0
assert case.assertions.ledger_delta == Money(19_500)     # 1120 - 925
assert isinstance(case.disposition, NeedsReview)
assert case.disposition.title == "FedEx Freight - SHP-88220"
assert case.disposition.subtitle == "Overbilled by $195.00 (Liftgate + Detention)"

# Accountant: one click. Payable is the matcher’s number, confirmed not re-entered.
case = office.decide(
    key,
    ApproveShortPay(expected_payable=Money(92_500)),
)
assert isinstance(case.disposition, ShortPaid)
assert case.disposition.payable == Money(92_500)
assert case.disposition.packet.proposed_erp_payable == Money(92_500)
```

Re-running `ingest` → `match` → `decide` with the same facts and the same action converges to the same case. That is the contract.

---

## Call site 1 — demo harness (3 minutes, no login)

Adapters parse the controller’s weekend packet *behind* the office. The harness only sees facts and keys.

```python
from pathlib import Path
from freight_audit import AuditOffice, ApproveShortPay, Money, NeedsReview, ShortPaid
from freight_audit.adapters import load_controller_packet  # CSV / PDF / dock log → Evidence

office = AuditOffice.in_memory()
facts = load_controller_packet(
    baseline=Path("freight_audit_baseline.csv"),
    invoices=Path("fixtures/invoices"),
    dock_logs=Path("fixtures/dock"),
    facilities=Path("fixtures/facilities"),
)
for key in office.ingest(facts):
    office.match(key)

hero = next(c for c in office.cases() if c.key.shipment_id == "SHP-88220")
assert isinstance(hero.disposition, NeedsReview)

# Voiceover: “approve the short-pay.”
hero = office.decide(
    hero.key,
    ApproveShortPay(expected_payable=hero.assertions.expected_total),
)
assert isinstance(hero.disposition, ShortPaid)
# Kanban column is a UI map of disposition. Color #FCE8E6 stays in the UI.
```

Maersk/ocean rows in the same CSV become `SkippedOutOfScope` at `match`. They do not pick up dock-dwell math.

---

## Call site 2 — AP specialist, Monday morning

The board reads `office.cases()`. The detail pane reads `office.get(key)`. The specialist never sees a model score. They see timestamps, a dock flag, and line money.

```python
def render_exception(office: AuditOffice, key: CaseKey) -> None:
    case = office.get(key)
    dwell = case.dwell_evidence()          # arrival 14:12, departure 15:45, 93 vs 30
    dock = case.facility_evidence()        # destination has a standard dock
    for line in case.assertions.lines:     # billed vs authorized vs variance
        print(line.charge, line.billed, line.authorized, line.variance)

    match case.disposition:
        case NeedsReview(proposed_payable=payable):
            # Primary: approve short-pay packet (dock receipt already attached).
            office.decide(key, ApproveShortPay(expected_payable=payable))
        case AutoClosed():
            pass  # already posted as a proposal; show the policy id
        case SkippedOutOfScope(reason=reason):
            print("out of v1 scope:", reason)
        case ShortPaid() | PaidAsBilled():
            pass  # terminal


def override_pay_as_billed(office: AuditOffice, key: CaseKey, reason: str) -> None:
    case = office.get(key)
    billed = case.assertions.billed_total
    office.decide(key, OverridePayAsBilled(expected_billed=billed, reason=reason))
    # reason is stored on PaidAsBilled and becomes lane policy later.
    # There is no learn() on the public surface.
```

Stale screens fail closed: `ApproveShortPay(expected_payable=...)` must equal the current matcher total or `decide` raises `StaleDecision`. The specialist refreshes, not types a new amount.

---

## Call site 3 — extractor adapter (I/O, not the domain)

Hunters and extractors parse wire into `Evidence`. They do not own `AuditCase` and they do not compute $75.

```python
from freight_audit import InvoiceFact, invoice_fact
from freight_audit.adapters import InvoiceExtractor

class PdfExtractor:
    def extract(self, invoice_bytes: bytes) -> InvoiceFact:
        # Wire JSON / inference payload is local to this file.
        raw = InvoiceExtractor.parse_bytes(invoice_bytes)
        return invoice_fact(
            invoice_id=raw.invoice_id,
            shipment_id=raw.shipment_id,
            carrier=raw.carrier,
            bol=raw.bol,
            lines=raw.lines,  # already Money cents, ChargeCode
        )

office.ingest([PdfExtractor().extract(pdf_bytes)])
# match() still does the math. A wrong liftgate label becomes UnexplainedLine, not a guessed amount.
```

---

## What you do not call

- No `set_payable`, no `post_to_erp`, no `ask_model_for_detention`.
- No load / validate / transform / save steps. `ingest` accepts already-valid facts; constructors validate.
- No TensorMux client, no bucket URL, no CSV row type on this surface.
- No hunter agent to orchestrate. Harvest is a script that calls `ingest`.
