import json
import re
from dataclasses import dataclass
from pathlib import Path


BOL_PATTERN = re.compile(r"BOL-[A-Z]{2}-[0-9]{5}")


@dataclass(frozen=True)
class DiscoveredInvoice:
    path: Path
    bill_of_lading: str


def discover_invoice_files(vault_path: str | Path) -> list[DiscoveredInvoice]:
    """Discover invoice JSON files in the mock vault using their BOL identity."""
    discovered: list[DiscoveredInvoice] = []
    for path in sorted(Path(vault_path).glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        match = BOL_PATTERN.fullmatch(str(payload.get("bill_of_lading", "")))
        if match:
            discovered.append(DiscoveredInvoice(path=path, bill_of_lading=match.group(0)))
    return discovered
