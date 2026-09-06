import csv
from decimal import Decimal, InvalidOperation
from typing import List
from shortpay.evidence import ContractFact, Mode


def _parse_cents(value: str) -> int:
    try:
        cents = Decimal(value) * 100
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary value: {value}") from exc
    if cents != cents.to_integral_value():
        raise ValueError(f"Monetary value has more than two decimal places: {value}")
    return int(cents)


def parse_baseline_csv(csv_filepath: str) -> List[ContractFact]:
    contracts = []
    with open(csv_filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mode_str = row["mode"].upper()
            try:
                mode_enum = Mode[mode_str]
            except KeyError:
                mode_enum = Mode.OTHER

            agreed_base = _parse_cents(row["agreed_base_rate"])
            detention_rate = _parse_cents(row["detention_rate_per_hour"])
            allowed_dwell = int(row["allowed_dwell_minutes"])

            contracts.append(
                ContractFact(
                    shipment_id=row["shipment_id"],
                    carrier=row["carrier"],
                    bill_of_lading=row["bill_of_lading"],
                    mode=mode_enum,
                    agreed_base_rate_cents=agreed_base,
                    allowed_dwell_minutes=allowed_dwell,
                    detention_rate_per_hour_cents=detention_rate,
                )
            )
    return contracts
