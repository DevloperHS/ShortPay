import asyncio

import pytest

from shortpay.adapters import invoice_extract
from shortpay.adapters.invoice_extract import (
    ExtractionError,
    ProviderRequestLimiter,
    SponsorRequestLimitError,
    extract_invoice_with_fallback,
    extract_invoice_with_fallback_details,
    parse_invoice_json,
)
from shortpay.evidence import ChargeType, InvoiceFact, InvoiceLine


def _invoice_fact() -> InvoiceFact:
    return InvoiceFact(
        invoice_id="INV-FRT-2026-09",
        shipment_id="SHP-88220",
        carrier_name="FedEx Freight",
        bill_of_lading="BOL-US-99121",
        lines=(
            InvoiceLine(charge_type=ChargeType.BASE_FREIGHT, amount_cents=85000),
            InvoiceLine(charge_type=ChargeType.DETENTION, amount_cents=17500),
            InvoiceLine(charge_type=ChargeType.LIFTGATE, amount_cents=9500),
        ),
    )


@pytest.fixture(autouse=True)
def reset_provider_request_limit():
    invoice_extract.provider_request_limiter.reset()
    yield
    invoice_extract.provider_request_limiter.reset()


def test_parse_invoice_fixture_uses_integer_cents():
    fact = parse_invoice_json("fixtures/invoice_INV-FRT-2026-09.json")

    assert fact.invoice_id == "INV-FRT-2026-09"
    assert fact.total_billed_cents == 112000
    assert [line.charge_type for line in fact.lines] == [
        ChargeType.BASE_FREIGHT,
        ChargeType.DETENTION,
        ChargeType.LIFTGATE,
    ]


def test_extraction_raises_error_when_keys_missing(monkeypatch):
    monkeypatch.delenv("TENSORMUX_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ExtractionError, match="API key missing"):
        extract_invoice_with_fallback("Sample Invoice Text")


def test_tensormux_is_the_primary_provider(monkeypatch):
    calls = []
    fact = _invoice_fact()
    monkeypatch.setenv("TENSORMUX_API_KEY", "test-tensormux-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def successful_call(**kwargs):
        calls.append(kwargs)
        return fact

    monkeypatch.setattr(invoice_extract, "_call_openai_compatible", successful_call)
    monkeypatch.setattr(invoice_extract.tracer, "trace_extraction", lambda **_: None)

    outcome = extract_invoice_with_fallback_details("invoice text")

    assert outcome.provider == "TensorMux"
    assert outcome.fact == fact
    assert len(calls) == 1
    assert calls[0]["base_url"] == "https://api.tensormux.com/v1"


def test_groq_is_used_only_after_tensormux_fails(monkeypatch):
    calls = []
    fact = _invoice_fact()
    monkeypatch.setenv("TENSORMUX_API_KEY", "test-tensormux-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")

    def fallback_call(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("primary unavailable")
        return fact

    monkeypatch.setattr(invoice_extract, "_call_openai_compatible", fallback_call)
    monkeypatch.setattr(invoice_extract.tracer, "trace_extraction", lambda **_: None)

    outcome = extract_invoice_with_fallback_details("invoice text")

    assert outcome.provider == "Groq"
    assert outcome.fact == fact
    assert [call["base_url"] for call in calls] == [
        "https://api.tensormux.com/v1",
        "https://api.groq.com/openai/v1",
    ]


def test_request_limiter_blocks_attempt_61_for_each_provider():
    now = [0.0]
    limiter = ProviderRequestLimiter(clock=lambda: now[0])

    for provider in ("TensorMux", "Groq"):
        for _ in range(60):
            limiter.acquire(provider)

        with pytest.raises(SponsorRequestLimitError, match="maximum 60"):
            limiter.acquire(provider)


def test_transport_hook_counts_attempts_and_window_expires(monkeypatch):
    now = [0.0]
    limiter = ProviderRequestLimiter(clock=lambda: now[0])
    monkeypatch.setattr(invoice_extract, "provider_request_limiter", limiter)
    hook = invoice_extract._request_limit_hook("TensorMux")

    for _ in range(60):
        asyncio.run(hook(object()))

    with pytest.raises(SponsorRequestLimitError):
        asyncio.run(hook(object()))

    now[0] = 60.001
    asyncio.run(hook(object()))
