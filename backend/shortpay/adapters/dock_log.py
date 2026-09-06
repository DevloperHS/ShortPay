import json
from shortpay.evidence import DockDwellFact


def parse_dock_log_json(filepath: str) -> DockDwellFact:
    with open(filepath, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    return DockDwellFact(
        shipment_id=data["shipment_id"],
        arrived_at=data["arrived_at"],
        departed_at=data["departed_at"],
    )
