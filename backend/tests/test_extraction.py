import pytest
from shortpay.adapters.invoice_extract import extract_invoice_with_fallback, ExtractionError


def test_extraction_raises_error_when_keys_missing(monkeypatch):
    """
    Empirical test verifying that if both TENSORMUX_API_KEY and GROQ_API_KEY
    are missing or fail, an explicit ExtractionError is raised.
    """
    monkeypatch.delenv("TENSORMUX_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ExtractionError) as exc_info:
        extract_invoice_with_fallback("Sample Invoice Text")

    assert isinstance(exc_info.value, ExtractionError)
