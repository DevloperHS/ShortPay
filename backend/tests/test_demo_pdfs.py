from pathlib import Path

from shortpay.adapters.invoice_extract import extract_text_from_pdf

PDF_DIR = Path(__file__).resolve().parents[2] / "pdf"

EXPECTED = {
    "INV-FRT-2026-09": ("SHP-88220", "BOL-US-99121", "BASE_FREIGHT", "DETENTION", "LIFTGATE"),
    "INV-FRT-2026-10": ("SHP-88221", "BOL-US-99122", "LIFTGATE"),
    "INV-FRT-2026-12": ("SHP-88220", "BASE_FREIGHT", "DETENTION", "LIFTGATE"),
    "INV-FRT-2026-13": ("SHP-88220", "BASE_FREIGHT"),
    "INV-FRT-2026-14": ("SHP-88220", "LIFTGATE"),
    "INV-FRT-2026-15": ("SHP-88220", "DETENTION"),
    "INV-FRT-2026-16": ("SHP-88220", "OTHER"),
    "INV-OCN-2026-01": ("SHP-88219", "OCEAN", "Maersk"),
    "INV-FRT-2026-18": ("SHP-88222", "XPO Logistics"),
    "INV-TL-2026-01": ("SHP-88223", "TL", "Old Dominion"),
}


def test_demo_pdf_folder_has_ten_invoices():
    files = sorted(path.name for path in PDF_DIR.glob("*.pdf"))
    assert files == sorted(f"{invoice_id}.pdf" for invoice_id in EXPECTED)


def test_demo_pdfs_expose_extractable_invoice_facts():
    for invoice_id, needles in EXPECTED.items():
        text = extract_text_from_pdf((PDF_DIR / f"{invoice_id}.pdf").read_bytes())
        assert invoice_id in text
        for needle in needles:
            assert needle in text, f"{invoice_id} missing {needle}"
