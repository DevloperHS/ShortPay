# Backend vs PRD review

- **Date:** 2026-09-06
- **Branch:** `codex/sponsor-backend-pr` @ `b098590`
- **Spec:** [docs/prd.md](../prd.md)
- **Scope:** backend only (`backend/shortpay`, `backend/main.py`, `backend/tests`, `fixtures`)
- **Method:** four parallel reviewers against the Must list, eval table, decide/policy/ERP path, and adapters, then one skeptic per finding. 19 of 23 candidates survived.

Hero cents still lock. `match_evidence` is still a pure function. The rest of Track 2 is unwired, untested, or wrong.

## Demo blockers

**Ocean skip never becomes a card.** Maersk `SHP-88219` is stored as a contract. `AuditOffice.match()` requires invoice, dock, and facility before the matcher can skip, so `SkippedOutOfScope` is unreachable. `/api/cases` also omits `skip_reason`. The CSV row is not visible on the board.

**Approve short-pay does not emit ERP or a dispute packet.** `build_erp_proposal` and `build_dispute_packet` live in `backend/shortpay/adapters/erp_propose.py` and have zero callers. `POST /api/decide` returns `{status, new_disposition, approved_payable_cents}` only.

**The $38 auto-close loop is not loadable.** After a human short-pay, the next invoice on that lane should AutoClosed under `SHORT-PAY-01`. There is no `$38` fixture, no `SHORT-PAY-01` id, and no `AutoClosed` test. `ApproveShortPay` stamps hardcoded `LIFTGATE_DOCK_PRESENT` and `DETENTION_HOURS`, not the fired overbill rules.

**Hunter is missing.** No vault watcher, no `BOL-[A-Z]{2}-[0-9]{5}` harvest. Startup loads `fixtures/invoice_INV-FRT-2026-09.json` through `parse_invoice_json`.

## Wrong behavior

**Unexplained lines do not block auto-close.** Unmapped charges become `ChargeType.OTHER` with expected 0 and an explanation that claims auto-close is blocked. `office.match()` only checks dispute ≤ $50 and the two lane flags. A `$38` "gate fee" on an approved lane would AutoClosed. There is no `UnexplainedLine` type.

**Re-ingest reopens a decided case.** Same `CaseKey` means one card. `match()` always rewrites disposition to NeedsReview / AutoClosed / Skipped. `POST /api/ingest` after a short-pay puts the hero back in Major exceptions. `AuditCase.is_terminal` is unused.

**Unknown CSV `mode` becomes LTL.** `Mode` has no `OTHER`, so `baseline_csv.py` falls through to `Mode.LTL`. A bad mode gets detention math instead of skip.

**CSV money goes through float.** `int(float(rate) * 100)` in `baseline_csv.py`. `Money` is unused on that path.

**Pay-as-billed reason is optional on the backend.** Empty string is stored on `PaidAsBilled`. Only the Flask form requires a reason.

## Implemented, untested

| PRD eval | In code? | Test? |
| --- | --- | --- |
| HERO | yes, payable 92500 / dispute 19500 | `backend/tests/test_hero.py` |
| STALE (`90000` vs `92500`) | `StaleDecisionError` maps to HTTP 400 | no |
| DOCK_FALSE | liftgate authorized as billed when `has_dock` is false | no |
| DWELL_AT_FREE | `max(0, dwell - allowed)` | no |
| IDEMPOTENT | one `CaseKey`, but rematch clobbers decide | no |
| OCEAN_SKIP | matcher can skip, ingest never matches Maersk | no |
| AUTO_CLOSE | threshold and lane flags exist | no |
| BAD_EXTRACT | `OTHER` does not hard-block auto-close | no |

Neatlogs logs `trace-freight-shp-88220` and stamps `shortpay.trace_id`, but the SDK call opens a new CHAIN span with its own id. No test locks the hero trace id.

## What to build first

1. Wire ERP proposal and dispute packet into `decide` and the API, including dock-receipt evidence.
2. Let a CSV-only ocean row become `SkippedOutOfScope` without inventing dock facts, and return `skip_reason`.
3. Block auto-close on `OTHER`, add the `$38` invoice, and lock STALE / rematch / ocean in tests.
4. Stop rematch from wiping `ShortPaid`.

Hunter and a named `SHORT-PAY-01` snapshot can wait until that loop actually runs.
