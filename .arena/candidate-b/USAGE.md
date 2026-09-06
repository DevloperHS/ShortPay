# Dual money ledger — caller's usage

Pre-pay LTL/TL accessorial audit. The carrier invoice never mutates. Two ledgers sit beside it: **billed** (what they claimed) and **expected** (what contract + evidence authorize). Their join *is* the work item. HITL posts the expected total to AP and attaches a dispute packet for the overage.

Money is integer cents everywhere. Matcher math is pure. LLM extraction is I/O only.

## Quickstart (demo hero: SHP-88220)

```python
from freight_audit import (
    InvoiceDocument,
    extract_billed,
    authorize_expected,
    join_ledgers,
    route_join,
    approve_short_pay,
    override_pay_as_billed,
)

# 1. Immutable source — parse once at the boundary; never rewrite.
invoice = InvoiceDocument.load(path="fixtures/INV-FRT-2026-09.pdf")

# 2. Agent I/O → BilledLedger (carrier claims). Idempotent on invoice content hash.
billed = extract_billed(invoice)
# billed.total_cents == 112_000
# lines: BASE_FREIGHT 85000, DETENTION 17500, LIFTGATE 9500

# 3. Pure matcher → ExpectedLedger (authorized money). No LLM in this path.
expected = authorize_expected(
    shipment_id="SHP-88220",
    contract=contract_row,      # base 85000, free dwell 30, detention $75/hr
    evidence=dock_and_facility, # dwell 93m, has_dock=True
)
# expected.total_cents == 92_500
# lines: BASE_FREIGHT 85000, DETENTION 7500  (liftgate absent = $0 authorized)

# 4. The work item is the join — not a Case aggregate.
work = join_ledgers(billed, expected)
# work.payable_cents == 92_500
# work.dispute_cents == 19_500
# work.variances by charge_type:
#   LIFTGATE  -9500, DETENTION -10000, BASE_FREIGHT 0

# 5. Policy routes the join (Maximor: auto under threshold, else escalate).
decision = route_join(work, policy=lane_policy)
assert decision.kind == "escalate"  # $195 > $50; first-seen rules on this lane

# 6. Accountant HITL — one primary action.
posting, packet = approve_short_pay(work, reviewer="controller@acme")
# posting.amount_cents == 92_500  → propose to ERP (ERP stays SoR)
# packet attaches dock receipt; lists liftgate + detention overage lines

# Secondary: override (pay as billed) writes a policy seed, does not invent math.
# posting, _ = override_pay_as_billed(work, reason="customer-caused dwell", reviewer=...)
```

## Call site: batch ingest from controller CSV

```python
from freight_audit import load_baseline, open_work_items

for row in load_baseline("freight_audit_baseline.csv"):
    if row.mode not in ("LTL", "TL"):
        continue  # Maersk ocean row: out of v1; no work item opened
    work = open_work_items(row)  # extract + authorize + join; idempotent
    yield route_join(work, policy_for(row.lane))
```

## Call site: Kanban card from a join

```python
from freight_audit import kanban_card

card = kanban_card(work)
# column: Major Exceptions, color #FCE8E6
# title: "FedEx Freight - SHP-88220"
# subtitle: "Overbilled by $195.00 (Liftgate + Detention)"
```

## What callers do *not* import

- TensorMux client types, S3 URIs, PDF JSON blobs, EDI wire structs
- A `Case` / `AuditCase` root
- Float dollars
- Agent prompts or model IDs

Parse wire formats behind `InvoiceDocument.load` / `extract_billed`. Public types speak charge lines and cents.
