# Architecture synthesis

Arena: two structurally different sketches, then a pick. Grounding is [\_grounding.md](_grounding.md). Product is [prd.md](prd.md). Contract is [architecture.md](architecture.md).

## Rubric

1. Illegal AP states unrepresentable (cannot be short-paid and paid-as-billed).
2. Matcher is a pure function over branded money and minutes. LLM is not on the math path.
3. HITL is approve-short-pay-packet, not confirm-the-agent.
4. TensorMux, S3, CSV rows stay behind parse functions.
5. v1 is LTL/TL. Ocean skips.
6. Re-running the same invoice converges.

## Candidates

**A (AuditCase + disposition machine).** Public verbs `ingest` / `match` / `decide`. Case keyed by invoice + shipment. Stale HITL fails closed. Dwell and billed totals derived. Floor-hour detention to lock $75.

**B (dual money ledger).** Invoice immutable. Billed ledger and expected ledger. The join *is* the work item. No case root. Five verbs. Explicit $0 expected liftgate. Override does not rewrite expected math.

## Pick

Base is **A**. Graft the ledger join from **B** *inside* the case.

A future maintainer extends a board of cases (auto-close, stale click, skip ocean) without breaking cents. Kanban columns are dispositions. Maximor policy is a function of disposition plus a lane book. B's join is the right model of money and the wrong model of AP work. A board still needs somewhere to hang `NeedsReview`. If we shipped B as the root we would grow a case anyway, and then we would have two work items.

## Grafts from B

- Two frozen ledgers plus an outer join on `ChargeType`. Payable is `sum(expected)`. Dispute is billed where billed > expected.
- Explicit expected liftgate $0 when dock is present, so the math grid is a total function.
- Override does not rewrite `ExpectedLedger`.
- `PayablePosting` as an ERP proposal, named separately from the dispute packet.
- Private `adapters/` (B's `_boundary/`) so vendor types cannot leak from `__init__`.

## Rejected

- **B as the public root.** The join is a value. The specialist's object is a case with a column and a button.
- **Hunter → extractor → matcher as modules.** Temporal decomposition. Same invoice rules would repeat at every stage. Agents stay adapters.
- **LLM emits payable cents.** Fails the Monday test. Cannot lock $925.
- **Mutable invoice with line statuses.** Re-extract becomes dangerous. ERP owns paid-or-not.
- **HITL amount entry.** The specialist becomes the calculator.
- **IEEE ceil detention.** It contradicts the hero dollar. Encoded as completed hours, as a named rule, not a silent "ceil" comment.
- **FSC and ocean in v1 types.** They make the demo look broad and the rules look fake.

## Tradeoffs accepted

- We accept a case aggregate plus ledgers (two ideas) in exchange for a board that maps to AP and math that cannot drift from the card.
- We accept `ApproveShortPay.expected_payable` looking ceremonial in exchange for stale-screen safety without a version field.
- We accept no reopen of terminal cases when late dock IoT arrives, in exchange for a machine a specialist can trust this weekend. New invoice, new case.
- We accept FSC out of the 3-minute path.

## Cross-judge

Parent read both packages end to end. No separate judge model was spawned (only grok-4.6 / grok-4.5 available; parent already used a different family split across runners). Disagreement was on the root object, not on cents, purity, or HITL. The pick is the root. The graft is the money.

## Verification of this synthesis

- Hero table in PRD, architecture, and both candidates agree: 92500 / 19500.
- TensorMux appears only under adapters.
- Disposition is a sum type in the architecture doc.
- Maersk is skip, not a second matcher.

Next fill-in step is the matcher test named in architecture, not the Kanban.
