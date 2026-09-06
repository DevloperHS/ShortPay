# Grounding for freight surcharge audit (Track 2)

Greenfield. No existing codebase. Product is a 3-minute hackathon demo plus a PRD and architecture that could survive a controller's desk.

## Track

Syndicate by Maximor, Track 2: Autonomous Office of the CFO.

Judges score:

- Is this a real pain for people who work in the office of the CFO?
- Is the human-judgment step intuitive for an accountant, not an ML engineer?
- How deep is the automation inside one specific finance workflow?
- Would an AP specialist actually use this?

Track goal: take over a repetitive internal finance process end to end, including exceptions and human review. Not consumer banking, trading, lending, or payment products.

Sponsors to use for real, not as stickers:

- TensorMux: inference. LLM calls (invoice OCR / extraction) go through TensorMux. Deterministic math does not.
- Neatlogs: traces of every agent step, tool call, and rule assertion. Demo should show a trace.
- AO: required while building. Mention in the submission.
- Maximor pattern to match: learn a policy, auto-run under a threshold, escalate judgment, write the decision back as a tighter policy. Their homepage uses freight short-pay as the example (`SHORT-PAY-01`, Acme Freight auto-closed, Byte Foods escalated).

Demo video is 3 minutes. No login, auth, or 2FA theater.

## The real workflow (not the demo slogan)

Freight audit and payment (FAP) is a named office-of-the-CFO process. Logistics books the load. AP pays the carrier. Finance owns tolerance and GL coding. The leak is pre-payment: most teams sample 5% of invoices or outsource to contingency FAP firms (Cass, AFS, Trax) that take 6-12% of recovered savings.

A real pre-pay audit is a 3-way or 4-way match:

1. Carrier invoice (EDI 210, portal extract, or PDF).
2. Contract / rate confirmation (base rate, FSC method, accessorial schedule).
3. Shipment record (BOL, PRO, TMS).
4. Operational evidence (POD timestamps, dock IoT, facility attributes).

Then AP either pays, short-pays, or disputes. Short-pay is a real AP action: post the authorized amount, send a dispute packet with evidence, leave the remainder open until the carrier issues a credit or a revised invoice.

Accessorials (liftgate, detention, residential, reweigh, reclass, lumper, TONU) are the most disputed lines. Fuel surcharge errors are common when the carrier uses the wrong DOE week or a private diesel index.

Industry leak cited by FAP vendors is roughly 3-7% of freight spend on unvetted charges. Treat that as a claim to prove in the demo with one invoice, not a market-size slide.

## Narrow the product

v1 is **LTL / TL accessorial and detention audit**, not "all freight."

Ocean demurrage (Maersk) is a different clock, a different contract, and a different evidence set (terminal free time, not dock dwell). Parcel is a third product (DIM weight, residential, DAS). Mixing them in v1 makes the demo look broad and the rules look fake.

Demo hero: FedEx Freight `SHP-88220` / `BOL-US-99121`. Maersk stays in the baseline CSV as a "out of v1 scope" row so the matcher can skip it cleanly.

## Hero numbers the matcher must reproduce exactly

From the controller's weekend packet:

```
shipment_id,carrier,bill_of_lading,agreed_base_rate,allowed_dwell_minutes,contract_fuel_base_price
SHP-88220,FedEx Freight,BOL-US-99121,850.00,30,3.85
```

Facility: destination has a standard loading dock. Liftgate is not authorized.

Dock IoT:

- arrival 14:12:00
- departure 15:45:00
- dwell = 93 minutes

Carrier invoice `INV-FRT-2026-09`:

- BASE_FREIGHT 850.00
- DETENTION_SURCHARGE 175.00 (billed as 60 min)
- ACCESSORIAL liftgate 95.00
- total billed 1120.00

Rules:

- Dock present => liftgate allowed = 0. Variance = -95.00
- Billable detention minutes = max(0, 93 - 30) = 63
- Authorized detention = ceil(63/60) * 75 = 75.00
- Carrier billed 175. Variance = -100.00
- Expected total = 850 + 75 = 925.00
- Billed 1120. Ledger delta = 195.00

HITL action: approve payable 925.00, generate short-pay notice with dock receipt attached, update ERP payable from 1120 to 925.

Kanban: card lands in Major Exceptions, soft rose `#FCE8E6`. Title `FedEx Freight - SHP-88220`. Subtitle `Overbilled by $195.00 (Liftgate + Detention)`.

## What an accountant must see

Not "the agent thinks this is wrong." They need:

- Allowed vs actual dwell, with the two timestamps.
- Liftgate charged vs facility-has-dock fact.
- Authorized money vs billed money, line by line.
- One primary action: approve the short-pay packet.
- A secondary action: override (pay as billed) with a reason, which becomes policy later.
- Auto-close later: `SHORT-PAY-01` style, e.g. variance <= $50 and both rules previously approved on this lane.

## Constraints

- Money is integer cents. Never float.
- Matcher math is a pure function. LLM extraction can be wrong; the math cannot be "the model said 75."
- Ingest, extract, match, decide, act must be idempotent. Re-running the same invoice converges to the same case.
- ERP remains system of record. This product proposes a payable amount and a dispute packet. It does not become the GL.
- Parse wire types (CSV, PDF JSON, S3 objects, TensorMux responses) at the boundary. Public domain types never mention TensorMux or S3.
- Agents are I/O. They do not own the domain model.

## Demo-sized inputs

- `freight_audit_baseline.csv` uploaded by the controller.
- Mock invoice PDF in `s3://mock-logistics-vault/invoices/` (local fixture is fine).
- Mock dock log for SHP-88220.
- Mock facility master: destination has dock = true.
- Mock DOE weekly diesel (only if FSC is in the demo; it is not required for the 3-minute path).

FSC can be a second card or a "coming" rule. Do not spend the 3 minutes on it.
