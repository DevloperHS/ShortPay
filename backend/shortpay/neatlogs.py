import hashlib
import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / ".env")
logger = logging.getLogger(__name__)

try:
    import neatlogs

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


def compute_evidence_hash(facts_dict: dict[str, Any]) -> str:
    """Return a stable, compact content hash for the matched evidence pack."""
    serialized = json.dumps(facts_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _neatlogs_base_url(configured_endpoint: str | None) -> str:
    endpoint = (configured_endpoint or "https://ingest.neatlogs.com").rstrip("/")
    if endpoint.endswith("/v1/traces"):
        endpoint = endpoint[: -len("/v1/traces")]
    return endpoint


class WorkflowTrace:
    """Small facade for adding dashboard-friendly fields to a workflow root."""

    def __init__(self, span=None):
        self._span = span

    def set_output(self, value: Any) -> None:
        if self._span is not None:
            self._span.set_attribute("output.value", json.dumps(value, sort_keys=True))

    def set_attribute(self, key: str, value: Any) -> None:
        if self._span is not None:
            self._span.set_attribute(key, NeatlogsTracer._attribute_value(value))


class NeatlogsTracer:
    """Thin, failure-isolated adapter around the official Neatlogs Python SDK."""

    def __init__(
        self,
        api_key: str | None = None,
        workflow_name: str = "shortpay-freight-audit",
    ):
        self.api_key = api_key or os.getenv("NEATLOGS_API_KEY")
        self.workflow_name = workflow_name
        self.endpoint = _neatlogs_base_url(os.getenv("NEATLOGS_ENDPOINT"))
        self.enabled = os.getenv("NEATLOGS_ENABLED", "1").lower() not in {
            "0",
            "false",
            "no",
        }
        self._sdk_initialized = False
        self._ensure_sdk_init()

    @property
    def is_configured(self) -> bool:
        return bool(
            self.enabled and self.api_key and self.api_key.strip() and SDK_AVAILABLE
        )

    def _ensure_sdk_init(self) -> bool:
        if self._sdk_initialized:
            return True

        self.api_key = self.api_key or os.getenv("NEATLOGS_API_KEY")
        if not self.enabled or not self.api_key or not self.api_key.strip() or not SDK_AVAILABLE:
            return False

        try:
            neatlogs.init(
                api_key=self.api_key,
                endpoint=self.endpoint,
                workflow_name=self.workflow_name,
                instrumentations=["pydantic_ai"],
                capture_logs=True,
                register_shutdown_handlers=False,
            )
            self._sdk_initialized = True
        except Exception:
            logger.exception("Neatlogs SDK initialization failed")
        return self._sdk_initialized

    @staticmethod
    def _attribute_value(value: Any) -> str | int | float | bool:
        if isinstance(value, (str, int, float, bool)):
            return value
        return json.dumps(value, sort_keys=True)

    def _emit(self, trace_id: str, span_name: str, payload: dict[str, Any]) -> None:
        event = {
            "neatlogs_version": "1.0",
            "workflow": self.workflow_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "trace_id": trace_id,
            "span_name": span_name,
            "payload": payload,
        }
        logger.info("SHORTPAY_TRACE %s", json.dumps(event, sort_keys=True))

        if not self._ensure_sdk_init():
            return

        try:
            kind = "WORKFLOW" if span_name == "match_evidence" else "CHAIN"
            with neatlogs.trace(span_name, kind=kind) as span:
                span.set_attribute("shortpay.trace_id", trace_id)
                for key, value in payload.items():
                    span.set_attribute(
                        f"shortpay.{key}", self._attribute_value(value)
                    )
                input_value, output_value = self._dashboard_values(span_name, payload)
                span.set_attribute("input.value", json.dumps(input_value, sort_keys=True))
                span.set_attribute("output.value", json.dumps(output_value, sort_keys=True))
        except Exception:
            # Observability must never stop invoice auditing, but failures remain visible.
            logger.exception("Neatlogs span export failed for %s", span_name)

    @staticmethod
    def _dashboard_values(
        span_name: str, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if span_name == "extract_billed":
            return (
                {
                    "invoice_id": payload["invoice_id"],
                    "provider": payload["provider"],
                    "model": payload["model"],
                },
                {
                    "billed_cents": payload["billed_total_cents"],
                    "lines_count": payload["lines_count"],
                },
            )
        if span_name == "ingest_fact":
            return (
                {
                    "fact_type": payload["fact_type"],
                    "record_id": payload["record_id"],
                    "source": payload["source"],
                },
                {"status": "ingested"},
            )
        if span_name == "match_evidence":
            return (
                {
                    "invoice_id": payload["invoice_id"],
                    "shipment_id": payload["shipment_id"],
                    "rules_fired": payload["rules_fired"],
                },
                {
                    "expected_cents": payload["expected_total_cents"],
                    "dispute_cents": payload["dispute_total_cents"],
                },
            )
        return (
            {
                "invoice_id": payload["invoice_id"],
                "shipment_id": payload["shipment_id"],
                "action": payload["action_type"],
            },
            {
                "disposition": payload["disposition_type"],
                "payable_cents": payload["payable_cents"],
            },
        )

    @contextmanager
    def workflow(
        self,
        name: str,
        *,
        trace_id: str,
        input_value: dict[str, Any],
    ):
        """Create one root row and nest all Shortpay operation spans beneath it."""
        if not self._ensure_sdk_init():
            yield WorkflowTrace()
            return

        try:
            with neatlogs.trace(name, kind="WORKFLOW") as span:
                span.set_attribute("shortpay.trace_id", trace_id)
                span.set_attribute("input.value", json.dumps(input_value, sort_keys=True))
                yield WorkflowTrace(span)
        finally:
            self.flush()

    def flush(self) -> None:
        if self._sdk_initialized:
            neatlogs.flush()

    def shutdown(self) -> None:
        if self._sdk_initialized:
            neatlogs.flush()
            neatlogs.shutdown()

    def trace_ingest(
        self,
        *,
        trace_id: str,
        fact_type: str,
        record_id: str,
        source: str,
    ) -> None:
        self._emit(
            trace_id,
            "ingest_fact",
            {"fact_type": fact_type, "record_id": record_id, "source": source},
        )

    def trace_extraction(
        self,
        trace_id: str,
        invoice_id: str,
        provider: str,
        lines_count: int,
        billed_total_cents: int,
        model_name: str,
    ) -> None:
        self._emit(
            trace_id,
            "extract_billed",
            {
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
        rules_fired: list[str],
        evidence_hash: str,
    ) -> None:
        self._emit(
            trace_id,
            "match_evidence",
            {
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
    ) -> None:
        self._emit(
            trace_id,
            "decide",
            {
                "invoice_id": invoice_id,
                "shipment_id": shipment_id,
                "action_type": action_type,
                "disposition_type": disposition_type,
                "payable_cents": payable_cents,
            },
        )


tracer = NeatlogsTracer()
