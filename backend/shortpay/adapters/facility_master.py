import json
from shortpay.evidence import FacilityFact


def parse_facility_json(filepath: str) -> FacilityFact:
    with open(filepath, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    return FacilityFact(
        shipment_id=data["shipment_id"],
        destination_has_dock=data["destination_has_dock"],
    )
