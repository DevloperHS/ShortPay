import csv
from typing import List
from shortpay.evidence import ContractFact, Mode


def parse_baseline_csv(csv_filepath: str) -> List[ContractFact]:
    contracts = []
    with open(csv_filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mode_str = row["mode"].upper()
            try:
                mode_enum = Mode[mode_str]
            except KeyError:
                mode_enum = Mode.OTHER if hasattr(Mode, "OTHER") else Mode.LTL

            agreed_base = int(float(row["agreed_base_rate"]) * 100)
            allowed_dwell = int(row["allowed_dwell_minutes"])
            detention_rate = int(float(row["detention_rate_per_hour"]) * 100)

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
