# Rationale

## Problem

Freight audit and payment is a pre-pay 4-way match: carrier invoice, contract, shipment, operational evidence. AP then pays, short-pays, or disputes. v1 is LTL/TL accessorial and detention only (hero FedEx Freight `SHP-88220`); ocean and parcel must skip, not pick up dock-dwell math. The matcher must lock $925 payable / $195 overbill in integer cents, as a pure function — extraction can be wrong, the math cannot be “the model said 75.” ERP stays system of record. Ingest/match/decide must be idempotent. Wire (CSV, PDF, inference, object storage) must die at the adapter wall. The 3-minute demo and a controller on Monday are the same object: an AP case with a primary short-pay action and an override that later tightens policy.

## Usage (caller's view)

Spec is [USAGE.md](USAGE.md). Import `AuditOffice`, evidence constructors, `ApproveShortPay`, `OverridePayAsBilled`. Three commands:

1. Demo harness: `load_controller_packet(...)` → `office.ingest(facts)` → `office.match(key)` → hero lands in `NeedsReview` with title `FedEx Freight - SHP-88220` and subtitle `Overbilled by $195.00 (Liftgate + Detention)` → `decide(ApproveShortPay(expected_payable=Money(92_500)))` → `ShortPaid` with dock-receipt packet.
2. AP pane: `get` / `cases`; show dwell timestamps, dock flag, line billed vs authorized; one click short-pay; override requires a reason. Specialist never types dollars.
3. Extractor adapter: wire bytes → `invoice_fact(...)` → `ingest`. Matcher still owns $75.

Kanban color `#FCE8E6` is UI. `learn()` is not public; `decide(ShortPaid)` records lane approvals.

## Shape

Root aggregate is `AuditCase` keyed by `(carrier_invoice_id, shipment_id)`. Facts append to an evidence log by `FactId`; shipment-scoped facts (contract, facility, dwell) exist before the invoice; the case is born on `InvoiceFact`. `match` merges at read, runs `match_evidence` (pure), then `propose_disposition` (scope skip / `SHORT-PAY-01` auto-close / `NeedsReview`). `decide` is the only human fork: `NeedsReview` → `ShortPaid` | `PaidAsBilled`. Disposition is the required sum type; unmatched is `disposition is None`, not a sixth constructor.

Load-bearing encodings, per encode-lessons-in-structure and boundary-discipline:

- `Money` / `Minutes` reject non-ints. Billed total and dwell minutes are derived, not ingested. Liftgate allowed is derived from `destination_has_dock`, not a parallel contract flag.
- Missing dock/facility yields `UnexplainedLine`, never an authorized amount. Unexplained blocks auto-close.
- `ApproveShortPay.expected_payable` must equal current `expected_total` or `StaleDecision` — the UI cannot invent $925.
- Terminal states are idempotent no-ops on the same action; other actions raise `IllegalTransition`. Revised invoices are new keys, per make-operations-idempotent.
- Hunter and extractor write facts independently; `match` is the merge, per separate-before-serializing-shared-state. Two disposition writers collide on the state machine, not a lock.

Public surface is `ingest` / `match` / `decide` plus reads `get` / `cases`. That is the interface-depth bet: callers do not sequence liftgate vs detention, do not apply $50 policy, do not assemble packets, do not see inference or buckets. Complexity remaining on the caller is the accountant’s world — facts, line assertions, two decisions.

Modules own knowledge (`money`, `evidence`, `matching`, `policy`, `case`), not time. `DisputePacket` sits in `case.py` so matching never imports the state machine and the reader’s path stays office → matching → case.

## Synthesis decision

Not synthesized. This is arena candidate A, committed to **AuditCase aggregate + AP disposition state machine**. Do not average with document-pipeline or agent-graph candidates. Internally this candidate already rejected packet-as-module (import cycle, extra hop), `Open` as a disposition constructor (not in the required sum type), and policy inside `match_evidence` (money rules must stay callable without a `PolicyBook`).

## Tradeoffs accepted

- We accept floor-hour detention (`63 // 60 = 1` → $75) in exchange for locking the hero dollars. IEEE `ceil(63/60)` is 2 hours / $150 and would fail the demo.
- We accept `disposition is None` as the unmatched state in exchange for not extending the required sum type.
- We accept no v1 reopen of terminal cases when facts change, in exchange for a machine an AP specialist can trust. New invoice id, new case.
- We accept `expected_payable` on the HITL command (looks ceremonial) in exchange for stale-screen safety without a version integer.
- We accept dropping FSC from `ContractFact` in exchange for types that do not pretend fuel is in the 3-minute path.
- We accept `OTHER` / unexplained lines excluded from `expected_total` in exchange for never auto-paying an unknown accessorial.
- We accept a demo-sized `list_cases` table scan in exchange for not inventing a query model before Monday’s volume exists.

## Alternatives considered

- **Temporal pipeline** (`ingest` / `validate` / `transform` / `save` modules). Lost: same invoice invariants repeated at every stage; callers coordinate a recipe. Shallow modules, temporal decomposition. This shape hides the recipe behind `ingest`/`match`/`decide`.
- **Agent graph as architecture** (hunter → extractor → matcher agent → HITL agent). Lost: pass-through orchestrators, inference types leak, math becomes “the agent thinks.” Agents stay adapters that emit `Evidence`. Callers would otherwise learn a graph to complete one audit.
- **Line-item aggregate** (one case per charge code). Lost: the AP action is one payable and one packet per invoice+shipment; splitting the aggregate makes the caller reassemble the short-pay. Deeper-looking internals, shallower public operation.
- **Matcher returns a recommendation the caller applies.** Lost: policy and packet leak onto the UI. Larger surface, less depth. `match` must land on a disposition.
- **HITL amount entry.** Lost: the specialist becomes the calculator. The packet already named $925; the type `ApproveShortPay` has no amount field except the stale-check token.

## Open questions and risks

- Does the lane actually floor detention hours, or was `ceil(63/60) = 75.00` a packet error and Monday should bill 2 hours / $150?
- Same-day `datetime.time` for dock clocks: what is the overnight dwell rule when departure < arrival?
- When an unexplained accessorial sits next to a clean liftgate/detention overbill, is `ApproveShortPay` still correct to pay only `expected_total` (dropping the extra line), or must the specialist explicitly exclude it?
- Auto-close uses `ledger_delta <= $50` **and** prior short-pays of both rules on `LaneKey(carrier, mode, destination_has_dock)`. Is dock-boolean a real lane, or do we need origin/destination facility ids from TMS?
- v1 freezes terminal cases. If dock IoT arrives *after* `ShortPaid`, do we need a reopen command before the first real invoice volume?
- Underbills (carrier billed *less* than authorized) always `NeedsReview` here. Should they auto-close as `PaidAsBilled` instead?

## Next implementation step

Implement `Money`, `Minutes`, evidence constructors, and `match_evidence` with a single test that locks `SHP-88220` at 92500 / 19500 before any office, store, or UI exists.
