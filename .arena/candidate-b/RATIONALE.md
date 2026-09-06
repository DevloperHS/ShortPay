# Rationale — dual money ledger (candidate B)

## Problem

Pre-pay freight audit leaks money when AP pays the carrier invoice before matching accessorials to contract and dock evidence. Controllers need authorized cents vs billed cents line-by-line, then one short-pay action into ERP — not an ML confidence score. The non-obvious constraint is ownership of truth: the invoice is a claim, the contract+evidence authorize a different amount, and neither should be overwritten by the other. Grounding also forbids float money, forbids LLM-owned math, forbids becoming the GL, and demands Maximor-shaped policy (auto under threshold, escalate judgment, write decisions back). v1 is LTL/TL accessorial and detention only; ocean/parcel must skip cleanly.

## Usage (caller's view)

See [USAGE.md](./USAGE.md). Callers load an immutable `InvoiceDocument`, get a `BilledLedger` from extraction, get an `ExpectedLedger` from a pure matcher, and treat `join_ledgers(...)` as the work item. HITL calls `approve_short_pay` (primary) or `override_pay_as_billed` (secondary). They never import TensorMux/S3 wire types or a `Case` root. The type sketch in [SHAPE.md](./SHAPE.md) is derived from that usage.

## Shape

Two parallel ledgers beside an immutable invoice. `BilledLedger` is carrier claims; `ExpectedLedger` is authorized money; `LedgerJoin` (outer join on `ChargeType`) is the work item. `payable_cents` is derived as `sum(expected)`; `DisputePacket` is billed lines that exceed expected, with rule basis and evidence refs. Policy routes the join; it does not recompute detention. Agents extract only; `authorize_expected` is pure and must reproduce the hero numbers exactly (liftgate $0 with dock, detention $75, payable $925, dispute $195).

Load-bearing decisions:

- **No Case aggregate** — a Case becomes a third ledger people mutate; the join already carries billed, expected, variance, and posting inputs (`per encode-lessons-in-structure`).
- **Cents newtype + frozen dataclasses** — misuse of floats and in-place edits fail loudly (`per boundary-discipline`).
- **Matcher owns accessorial rules; policy owns auto vs escalate** — single source of truth per invariant (`per single-source-of-truth`).
- **Override does not rewrite ExpectedLedger** — pay-as-billed is a posting choice; math stays honest for the next policy seed.
- **`_boundary/` is private** — wire and vendor types never cross the public surface (`per boundary-discipline`).

Interface depth: five verbs (`extract_billed`, `authorize_expected`, `join_ledgers`, `route_join`, `approve_short_pay`) hide OCR, detention ceil math, variance join, Maximor routing, dispute packet assembly, and Kanban projection. Callers see charge lines and cents. Exposed on purpose: `LedgerJoin` and `RuleBasis` — accountants must read allowed vs actual dwell and line math, so hiding those would fight the HITL UX. The surface is no larger: no service façade, no stage objects, no Case API.

Idempotency: same `content_hash` converges extract → match → join → posting proposal (`per make-operations-idempotent`). Shared writers: ledgers are immutable values; merge is the join at read time (`per separate-before-serializing-shared-state`).

Red-flag screen: not temporal packages; not pass-through services; no TensorMux/S3 on the public surface; modules own knowledge (money, ledgers, match, policy, board).

## Synthesis decision

Deferred to arena synthesis. This package is **candidate B** — committed dual money ledger shape; not averaged with other runners.

## Tradeoffs accepted

- We accept **no Case document for workflow engines** in exchange for a single join-shaped work item that cannot drift from the ledgers.
- We accept **explicit $0 expected lines** (e.g. denied liftgate) in exchange for variance always being a total function on `ChargeType`.
- We accept **override leaving ExpectedLedger unchanged** in exchange for never laundering a human exception into false authorized math.
- We accept **FSC out of the 3-minute path** in exchange for a demo whose rules look real and finish on detention + liftgate.
- We accept **orchestration inside `open_work_items`** (batch convenience) in exchange for keeping the primary API as three composable pure-ish steps — callers who want tracing call the steps directly for Neatlogs.

## Alternatives considered

- **Case-centric aggregate** (`AuditCase` holding invoice, status, lines, decision). Hides join math behind case transitions; exposes callers to status-machine complexity and a mutable second source of truth. Lost: duplicates the ledger join and invites invoice mutation.
- **Single mutable invoice with annotated lines** (`line.status = billed|approved|disputed`). Smaller type count, but leaks temporal audit stages onto the source document and makes idempotent re-extract dangerous. Lost: destroys immutable-source invariant; shallower module that forces callers to learn line-state rules.
- **Agent-emits-payable** (LLM returns authorized total + rationale). Tiny public surface, but moves money math into non-deterministic I/O and fails the controller Monday test. Lost: wrong ownership; cannot guarantee $925.

## Open questions and risks

- Should underbills (expected > billed on a type) surface on the Kanban card, or only overbills into `DisputePacket`?
- How is "prior lane approval" for `SHORT-PAY-01` persisted — append-only decision log, or ERP memo round-trip?
- Does `extract_billed` fail closed (block join) or open a join with empty billed + extraction-error flag when OCR is low-confidence?
- Is detention rate always `$75/hr` from policy defaults, or must it appear on every `ContractFacts` row in the baseline CSV?

## Next implementation step

Implement pure `authorize_expected` + `join_ledgers` against the SHP-88220 fixture until payable `92500` and dispute `19500` assert green, then wrap `extract_billed` as a stubbed boundary returning the known billed lines for the demo.
