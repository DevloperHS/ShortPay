# Shortpay

Product requirements for a pre-pay freight surcharge audit. Track 2, Syndicate by Maximor: Autonomous Office of the CFO.

This document is the product. Architecture lives in [architecture.md](architecture.md).

## What this is

Shortpay is the AP desk that audits carrier accessorials before the money leaves.

A logistics controller uploads the weekend rate baseline. Carrier PDFs land in a vault. Dock clocks and facility facts land beside them. The product matches each LTL or TL invoice to the shipment, computes an authorized payable in integer cents, and either auto-closes under policy or puts one card in front of a human.

The human does not grade an agent. They approve a short-pay packet: pay $925.00, dispute $195.00, attach the dock receipt.

ERP stays the system of record. Shortpay proposes the payable and the dispute notice. It does not become the GL.

## Why this workflow

Freight audit and payment is already a named job in the office of the CFO. Logistics books the load. AP pays the carrier. Finance owns tolerance and coding. The leak is pre-payment.

Most teams sample a slice of invoices or outsource to contingency FAP firms. Accessorials (liftgate, detention, residential, reweigh) are the lines that fail the sample. Fuel surcharge errors show up when the carrier uses the wrong DOE week. Duplicate invoices with different numbers slip through.

FAP vendors claim 3 to 7 percent of freight spend leaks this way. Shortpay does not put that number on a slide. It proves one invoice.

Maximor's own product story is this loop: learn a short-pay policy, auto-close $38, escalate $495, tighten the policy. Shortpay is that loop on a real AP artifact, not a generic "invoice copilot."

## Who uses it

**Primary: Logistics Controller / Supply Chain AP specialist.** They already live in TMS exceptions, email PDFs, and NetSuite bills. They know what a short-pay is. They will not learn a prompt.

**Secondary: Controller.** They own the $50 auto-close threshold and the rule that a lane can auto-close only after a human has approved that rule once.

**Not a user:** the hunter agent, the extractor, TensorMux. Those are I/O.

## The job, as they do it today

1. Carrier sends a weekly consolidated invoice (PDF, portal, or EDI 210).
2. AP clerk opens the bill, searches the TMS for the BOL or PRO, opens the rate con, opens the POD.
3. They check base rate, fuel table, and each accessorial against "did this actually happen."
4. Liftgate on a dock door gets disputed. Detention past free time gets recomputed from timestamps. Fuel gets checked against the DOE week on the contract.
5. They short-pay the authorized amount, email a dispute packet, and leave the remainder open until the carrier credits it.

That takes minutes per line and hours per invoice. So they sample. The unsampled remainder is where the money goes.

## v1 scope

**In:** LTL and TL accessorials that a dock clock and a facility master can prove.

- Base freight vs agreed rate.
- Liftgate vs destination-has-dock.
- Detention vs allowed dwell and a per-hour rate.

**Hero invoice (the demo and the first test):** FedEx Freight `SHP-88220` / `BOL-US-99121` / `INV-FRT-2026-09`.

| Line | Billed | Authorized | Variance |
| --- | ---: | ---: | ---: |
| Base freight | $850.00 | $850.00 | $0.00 |
| Liftgate | $95.00 | $0.00 | -$95.00 |
| Detention | $175.00 | $75.00 | -$100.00 |
| **Total** | **$1,120.00** | **$925.00** | **-$195.00** |

Facts behind that table:

- Destination has a standard loading dock. Liftgate is not authorized.
- Dock arrival 14:12, departure 15:45. Dwell is 93 minutes.
- Contract free time is 30 minutes. Billable dwell is 63 minutes.
- Detention rate is $75 per completed hour. 63 minutes is 1 hour. Authorized detention is $75.00.

The original packet wrote `ceil(63/60) × $75 = $75`. IEEE ceil of 63/60 is 2 hours ($150). The locked dollar is $75. The contract rule we encode is completed hours (`63 // 60`), not IEEE ceil. If a later rate card uses commenced hours, that is a different rule id, not a silent change to this one.

**Out of v1 (visible skip, not silent ignore):**

- Ocean demurrage and detention (Maersk). Different clock, different evidence, different contract. A Maersk row in the baseline CSV becomes `SkippedOutOfScope`.
- Parcel DIM, residential, DAS.
- Fuel surcharge vs DOE. Real, but it is a second card. It will steal the 3-minute demo.
- Login, SSO, 2FA, multi-tenant admin.

## What the specialist sees

A Kanban of AP cases. Not a chat.

Columns map to disposition:

| Column | Disposition | When |
| --- | --- | --- |
| Out of scope | `SkippedOutOfScope` | Ocean or parcel in this upload |
| Auto-closed | `AutoClosed` | Variance at or under policy, and this lane has prior human approvals for the fired rules |
| Major exceptions | `NeedsReview` | Overbill above policy, or a rule this lane has never approved. Soft rose `#FCE8E6` |
| Short-paid | `ShortPaid` | Human (or auto-close) posted the authorized amount |
| Paid as billed | `PaidAsBilled` | Human override with a reason |

Hero card:

- Title: `FedEx Freight - SHP-88220`
- Subtitle: `Overbilled by $195.00 (Liftgate + Detention)`

Open the card and the math grid is the product:

| Fact | Allowed / authorized | Actual / billed |
| --- | --- | --- |
| Dwell | 30 min free | 14:12 → 15:45 (93 min) |
| Detention | $75.00 (1 completed hour × $75) | $175.00 |
| Liftgate | $0.00 (dock present) | $95.00 |
| Payable | $925.00 | $1,120.00 billed |

Primary action, one click: **Approve $925.00 and generate carrier short-pay notice.**

That action:

- Proposes ERP payable $925.00 (was $1,120.00).
- Builds a dispute packet for $195.00 with the dock receipt attached.
- Records the two rule approvals on this lane so a later $38 liftgate can auto-close.

Secondary action: **Pay as billed**, reason required. The matcher math does not change. The reason is a policy seed, not a new authorized amount.

The specialist never types a dollar amount. A stale screen that still shows $925 when the matcher now says $1,000 fails closed.

## Autonomy loop (Maximor-shaped)

1. **Learn.** First time this carrier + mode + dock-flag lane sees `LIFTGATE_DOCK_PRESENT` or `DETENTION_HOURS`, the card escalates.
2. **Run.** After a human has approved those rules, `SHORT-PAY-01` auto-closes when overbill ≤ $50.00.
3. **Escalate.** Anything above the threshold, or any unexplained line, comes back to the board.
4. **Improve.** Override reasons and approved rule ids become the next policy snapshot. There is no public `learn()` button. `decide` is how the product learns.

## Inputs

Controller weekend file `freight_audit_baseline.csv`:

```
shipment_id,carrier,bill_of_lading,mode,agreed_base_rate,allowed_dwell_minutes,detention_rate_per_hour
SHP-88219,Maersk,BOL-US-99120,OCEAN,4200.00,120,75.00
SHP-88220,FedEx Freight,BOL-US-99121,LTL,850.00,30,75.00
```

Maersk is in the file so skip behavior is visible. `mode` is explicit. Do not infer ocean from the carrier name alone in v1 if the column is present.

Also required for the hero:

- Invoice PDF (or a fixture JSON that stands in for extraction) for `INV-FRT-2026-09`.
- Dock log with arrival and departure.
- Facility master: destination has dock = true.

## Agent roles (I/O, not the product)

Call them agents in the demo. In the code they are adapters.

**Hunter.** Watches the mock vault `s3://mock-logistics-vault/invoices/` (local fixtures in the demo). Matches files with `BOL-[A-Z]{2}-[0-9]{5}` or a tracking number. Emits an invoice fact identity. Does not compute money.

**Extractor.** Sends the PDF through TensorMux. Parses the model JSON at the boundary into billed lines in cents. A bad label becomes an unexplained line. The extractor never returns an authorized payable.

**Matcher.** Pure function. No TensorMux. No S3. Facts in, assertions out. This is the only place $75 is born.

Neatlogs wraps every adapter call, every `match`, and every `decide`. The demo shows one trace for `SHP-88220` with the two failed assertions (`LIFTGATE_DOCK_PRESENT`, `DETENTION_HOURS`) and a content hash of the evidence pack.

## Success for Track 2

Judges should be able to answer yes to all four:

1. **Real CFO pain.** Pre-pay FAP, short-pay, accessorials. An AP specialist already has words for this.
2. **Judgment is intuitive.** The modal is a math grid and a short-pay button, not "accept agent output."
3. **The workflow is deep.** 4-way match, integer-cent rules, policy auto-close, dispute packet, ERP proposal. Not "summarize the PDF."
4. **An accountant would use it Monday.** Same object as the demo. No chat, no prompt, no typed dollars.

## Success for the 3-minute video

Minute 0:00 to 0:20. Weekend CSV lands. Maersk skipped. FedEx card appears in Major exceptions, rose background.

Minute 0:20 to 1:20. Open the card. Show 14:12 / 15:45, 93 vs 30, liftgate vs dock. Show billed $1,120 vs authorized $925.

Minute 1:20 to 2:10. Click approve short-pay. ERP payable becomes $925. Dispute email preview with dock receipt. Card moves to Short-paid.

Minute 2:10 to 2:40. Neatlogs trace. Matcher spans, not the LLM, produced $75. TensorMux span is extraction only.

Minute 2:40 to 3:00. Second invoice, $38 liftgate, same lane. Auto-closed under `SHORT-PAY-01`. That is the loop.

Do not show a login page. Do not show ocean math. Do not show fuel.

## Requirements

**Must**

- Lock hero cents in a unit test before UI exists: payable 92500, dispute 19500.
- Money is integer cents. No floats on the domain path.
- Matcher is a pure function. TensorMux is not on that path.
- Disposition is a sum type. A case cannot be short-paid and paid-as-billed.
- Re-ingest of the same invoice and facts converges. No duplicate cards.
- HITL cannot type a new payable. Stale expected amount fails closed.
- ERP proposal and dispute packet are outputs. No silent GL post in v1.
- Ocean rows skip with a reason a human can read.
- Neatlogs trace id is stable per case: `trace-freight-shp-88220`.

**Should**

- Auto-close under $50 after prior rule approvals on the lane.
- Override reason stored on `PaidAsBilled`.
- Unexplained accessorial blocks auto-close and stays visible.

**Must not**

- Let the model invent detention hours.
- Mix ocean free time into dock dwell.
- Replace NetSuite.
- Build auth, orgs, or a marketplace.

## Evals (before claiming the matcher works)

Each eval is a fixture, not a vibe.

| Id | Setup | Expect |
| --- | --- | --- |
| HERO | SHP-88220 facts | payable 92500, dispute 19500, NeedsReview |
| DOCK_FALSE | same invoice, has_dock false | liftgate unexplained or authorized per schedule; not silently $0 |
| DWELL_AT_FREE | dwell 30 | detention authorized 0 |
| OCEAN_SKIP | SHP-88219 | SkippedOutOfScope, no detention math |
| IDEMPOTENT | ingest+match twice | one case, same cents |
| BAD_EXTRACT | liftgate labeled as "gate fee" unmapped | UnexplainedLine, auto-close blocked |
| AUTO_CLOSE | $38 liftgate, lane already approved | AutoClosed |
| STALE | ApproveShortPay with 90000 after matcher says 92500 | StaleDecision |

## Open product calls

These need a human, not another sketch.

- If an unexplained line sits next to a clean liftgate overbill, does short-pay still post `expected_total` (dropping the extra line), or must the specialist exclude it by name?
- Overnight dock clocks (departure before arrival) are rejected in v1. Is that acceptable for the demo?
- Underbills (carrier charged less than authorized): NeedsReview, or auto pay-as-billed?

## What we are not building this weekend

A FAP platform. A TMS. A general AP inbox. A multi-agent "swarm" as the architecture. Hunter, extractor, and matcher are names for adapters and one pure function.

If the demo cannot show the math grid and the short-pay in three minutes, cut whatever is in the way. Keep the cents test.
