import json

import pytest

from shortpay.adapters.baseline_csv import parse_baseline_csv
from shortpay.adapters.invoice_extract import parse_invoice_json
from shortpay.adapters.vault_hunter import discover_invoice_files
from shortpay.evidence import Mode


def test_csv_money_is_parsed_exactly_and_unknown_mode_is_not_ltl(tmp_path):
    csv_file = tmp_path / "baseline.csv"
    csv_file.write_text(
        "shipment_id,carrier,bill_of_lading,mode,agreed_base_rate,allowed_dwell_minutes,detention_rate_per_hour\n"
        "SHP-1,Carrier,BOL-US-12345,UNKNOWN,10.29,30,0.29\n",
        encoding="utf-8",
    )
    contract = parse_baseline_csv(str(csv_file))[0]
    assert contract.mode == Mode.OTHER
    assert contract.agreed_base_rate_cents == 1029
    assert contract.detention_rate_per_hour_cents == 29


def test_csv_money_rejects_fractional_cents(tmp_path):
    csv_file = tmp_path / "baseline.csv"
    csv_file.write_text(
        "shipment_id,carrier,bill_of_lading,mode,agreed_base_rate,allowed_dwell_minutes,detention_rate_per_hour\n"
        "SHP-1,Carrier,BOL-US-12345,LTL,10.299,30,0.29\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="more than two decimal places"):
        parse_baseline_csv(str(csv_file))


def test_hunter_discovers_invoice_by_bol_in_content(tmp_path):
    invoice = tmp_path / "carrier-document.json"
    invoice.write_text(json.dumps({"bill_of_lading": "BOL-US-12345"}), encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not an invoice", encoding="utf-8")
    found = discover_invoice_files(tmp_path)
    assert [(item.path, item.bill_of_lading) for item in found] == [
        (invoice, "BOL-US-12345")
    ]


def test_auto_close_fixture_is_loadable():
    invoice = parse_invoice_json("fixtures/invoice_INV-FRT-2026-10.json")
    assert invoice.invoice_id == "INV-FRT-2026-10"
    assert invoice.total_billed_cents == 88800
    assert invoice.lines[1].amount_cents == 3800
