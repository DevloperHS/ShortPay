import os
import json
import hashlib
import time
import requests
from typing import Dict, Any, List, Optional

try:
    import neatlogs
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


def compute_evidence_hash(facts_dict: Dict[str, Any]) -> str:
    """Computes SHA-256 content hash of evidence pack facts for Neatlogs auditability."""
    serialized = json.dumps(facts_dict, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class NeatlogsTracer:
    """
    Observability adapter for Neatlogs (Track 2 sponsor integration).
    Supports both official neatlogs SDK (OpenTelemetry/OpenInference) and HTTP endpoint fallback.
    """

    def __init__(self, api_key: Optional[str] = None, workflow_name: str = "shortpay-freight-audit"):
        self.api_key = api_key or os.environ.get("NEATLOGS_API_KEY")
        self.workflow_name = workflow_name
        self.endpoint = os.environ.get("NEATLOGS_ENDPOINT", "https://api.neatlogs.com/v1/traces")
        self._sdk_initialized = False

        if self.api_key and SDK_AVAILABLE:
            try:
                neatlogs.init(
                    api_key=self.api_key,
                    workflow_name=self.workflow_name,
                )
                self._sdk_initialized = True
                print(f"[NEATLOGS SDK] Initialized successfully for workflow '{self.workflow_name}'")
            except Exception as e:
                print(f"[NEATLOGS WARNING] SDK init failed: {e}")

    def _ensure_sdk_init(self):
        if not self._sdk_initialized and SDK_AVAILABLE:
            self.api_key = self.api_key or os.environ.get("NEATLOGS_API_KEY")
            if self.api_key and self.api_key.strip():
                try:
                    neatlogs.init(
                        api_key=self.api_key,
                        workflow_name=self.workflow_name,
                    )
                    self._sdk_initialized = True
                    print(f"[NEATLOGS SDK] Initialized successfully for workflow '{self.workflow_name}'")
                except Exception as e:
                    print(f"[NEATLOGS WARNING] SDK init failed: {e}")

    def _emit(self, trace_id: str, span_name: str, payload: Dict[str, Any]):
        self._ensure_sdk_init()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        event = {
            "neatlogs_version": "1.0",
            "workflow": self.workflow_name,
            "timestamp": timestamp,
            "trace_id": trace_id,
            "span_name": span_name,
            "payload": payload,
        }
        # Print formatted log line for local terminal/uvicorn logs
        print(f"[NEATLOGS TRACE] {json.dumps(event)}")

        # Use official Neatlogs SDK if initialized
        if self._sdk_initialized:
            try:
                with neatlogs.trace(name=span_name, **payload):
                    pass
                neatlogs.flush()
            except Exception as err:
                print(f"[NEATLOGS WARNING] SDK trace failed: {err}")


        # Post via HTTP if NEATLOGS_API_KEY is configured
        if self.api_key:
            try:
                headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
                requests.post(self.endpoint, json=event, headers=headers, timeout=2.0)
            except Exception as err:
                pass

    def trace_extraction(
        self,
        trace_id: str,
        invoice_id: str,
        provider: str,
        lines_count: int,
        billed_total_cents: int,
        model_name: str,
    ):
        self._emit(
            trace_id=trace_id,
            span_name="extract_billed",
            payload={
                "invoice_id": invoice_id,
                "provider": provider,
                "model": model_name,
                "lines_count": lines_count,
                "billed_total_cents": billed_total_cents,
            },
        )

    def trace_match(
        self,
        trace_id: str,
        invoice_id: str,
        shipment_id: str,
        expected_total_cents: int,
        dispute_total_cents: int,
        rules_fired: List[str],
        evidence_hash: str,
    ):
        self._emit(
            trace_id=trace_id,
            span_name="match_evidence",
            payload={
                "invoice_id": invoice_id,
                "shipment_id": shipment_id,
                "expected_total_cents": expected_total_cents,
                "dispute_total_cents": dispute_total_cents,
                "rules_fired": rules_fired,
                "evidence_hash": evidence_hash,
            },
        )

    def trace_decide(
        self,
        trace_id: str,
        invoice_id: str,
        shipment_id: str,
        action_type: str,
        disposition_type: str,
        payable_cents: int,
    ):
        self._emit(
            trace_id=trace_id,
            span_name="decide",
            payload={
                "invoice_id": invoice_id,
                "shipment_id": shipment_id,
                "action_type": action_type,
                "disposition_type": disposition_type,
                "payable_cents": payable_cents,
            },
        )


# Global singleton instance
tracer = NeatlogsTracer()
