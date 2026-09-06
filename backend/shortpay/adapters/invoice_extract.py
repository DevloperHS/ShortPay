import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from dotenv import load_dotenv

from shortpay.evidence import ChargeType, InvoiceFact, InvoiceLine
from shortpay.neatlogs import tracer


load_dotenv(Path(__file__).resolve().parents[2] / ".env")
logger = logging.getLogger(__name__)

try:
    from httpx2 import AsyncClient
    from openai import AsyncOpenAI
    from pydantic_ai import Agent, PromptedOutput
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False


ProviderName = Literal["TensorMux", "Groq"]


class ExtractionError(RuntimeError):
    """Raised when no configured inference provider can extract an invoice."""


class SponsorRequestLimitError(ExtractionError):
    """Raised before a sponsor request would exceed the rolling rate limit."""


@dataclass(frozen=True)
class ExtractionOutcome:
    fact: InvoiceFact
    provider: ProviderName
    model_name: str


EXTRACTION_INSTRUCTIONS = """
You extract billed facts from a carrier freight invoice.

Return only facts present in the supplied invoice. Monetary values must be integer
cents. Map base transportation to BASE_FREIGHT, detention or driver waiting time
to DETENTION, and liftgate service to LIFTGATE. Use OTHER for an unknown charge.
Do not calculate an authorized payable, dispute amount, or policy decision.
The invoice identifier belongs in invoice_id and line items belong in lines.
""".strip()


class ProviderRequestLimiter:
    """Thread-safe rolling-window limiter applied to actual outbound HTTP attempts."""

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1 or max_requests > 60:
            raise ValueError("max_requests must be between 1 and 60")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._requests: dict[ProviderName, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def acquire(self, provider: ProviderName) -> None:
        now = self._clock()
        with self._lock:
            requests = self._requests[provider]
            cutoff = now - self.window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()

            if len(requests) >= self.max_requests:
                raise SponsorRequestLimitError(
                    f"{provider} request blocked: maximum {self.max_requests} "
                    f"requests per {self.window_seconds:g} seconds reached"
                )
            requests.append(now)

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()


provider_request_limiter = ProviderRequestLimiter()


def _request_limit_hook(provider: ProviderName):
    async def enforce_request_limit(_request) -> None:
        provider_request_limiter.acquire(provider)

    return enforce_request_limit


def parse_invoice_json(filepath: str | Path) -> InvoiceFact:
    """Parse a deterministic local fixture into the public invoice domain type."""
    with Path(filepath).open(mode="r", encoding="utf-8") as invoice_file:
        data = json.load(invoice_file)

    lines: list[InvoiceLine] = []
    for raw in data.get("line_items", data.get("lines", [])):
        charge_name = str(raw["charge_type"]).upper()
        try:
            charge_type = ChargeType[charge_name]
        except KeyError:
            charge_type = ChargeType.OTHER

        lines.append(
            InvoiceLine(
                charge_type=charge_type,
                amount_cents=int(raw["amount_cents"]),
                billed_minutes=raw.get("billed_minutes"),
                description=raw.get("description"),
            )
        )

    return InvoiceFact(
        invoice_id=data.get("invoice_id", data.get("invoice_number")),
        shipment_id=data["shipment_id"],
        carrier_name=data["carrier_name"],
        bill_of_lading=data["bill_of_lading"],
        lines=tuple(lines),
    )


def _call_openai_compatible(
    *,
    provider_name: ProviderName,
    base_url: str,
    api_key: str,
    model_name: str,
    invoice_text: str,
) -> InvoiceFact:
    """Call one OpenAI-compatible sponsor endpoint through Pydantic AI."""
    if not PYDANTIC_AI_AVAILABLE:
        raise ExtractionError("pydantic-ai is not installed")

    http_client = AsyncClient(
        timeout=30.0,
        event_hooks={"request": [_request_limit_hook(provider_name)]},
    )
    openai_client = AsyncOpenAI(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        http_client=http_client,
    )
    model = OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(openai_client=openai_client),
    )
    agent = Agent(
        model,
        instructions=EXTRACTION_INSTRUCTIONS,
        output_type=PromptedOutput(InvoiceFact),
        model_settings={"max_tokens": 768, "temperature": 0.0},
        retries=2,
    )
    result = agent.run_sync(invoice_text)
    return result.output


def extract_invoice_with_fallback_details(
    raw_text_or_json: str,
    tensormux_model: str | None = None,
    groq_model: str | None = None,
) -> ExtractionOutcome:
    """Extract with TensorMux first, then use Groq only if the primary fails."""
    if not raw_text_or_json.strip():
        raise ExtractionError("Invoice text cannot be empty")

    provider_configs: tuple[tuple[ProviderName, str | None, str, str], ...] = (
        (
            "TensorMux",
            os.getenv("TENSORMUX_API_KEY"),
            os.getenv("TENSORMUX_BASE_URL", "https://api.tensormux.com/v1"),
            tensormux_model or os.getenv("TENSORMUX_MODEL", "glm-4-7-flash"),
        ),
        (
            "Groq",
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            groq_model or os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
        ),
    )

    failures: list[str] = []
    for provider, api_key, base_url, model_name in provider_configs:
        if not api_key or not api_key.strip():
            failures.append(f"{provider}: API key missing")
            continue

        try:
            fact = _call_openai_compatible(
                provider_name=provider,
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                invoice_text=raw_text_or_json,
            )
        except Exception as exc:
            failures.append(f"{provider}: {type(exc).__name__}: {exc}")
            logger.warning("%s invoice extraction failed; trying fallback", provider)
            continue

        tracer.trace_extraction(
            trace_id=f"trace-freight-{fact.shipment_id.lower()}",
            invoice_id=fact.invoice_id,
            provider=provider,
            lines_count=len(fact.lines),
            billed_total_cents=fact.total_billed_cents,
            model_name=model_name,
        )
        return ExtractionOutcome(fact=fact, provider=provider, model_name=model_name)

    raise ExtractionError("Invoice extraction failed. " + " | ".join(failures))


def extract_invoice_with_fallback(
    raw_text_or_json: str,
    tensormux_model: str | None = None,
    groq_model: str | None = None,
) -> InvoiceFact:
    """Backward-compatible API returning only the validated invoice fact."""
    return extract_invoice_with_fallback_details(
        raw_text_or_json,
        tensormux_model=tensormux_model,
        groq_model=groq_model,
    ).fact
