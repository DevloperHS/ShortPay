import os
import json
from typing import Tuple, Optional
from dotenv import load_dotenv
from shortpay.evidence import InvoiceFact, InvoiceLine, ChargeType
from shortpay.neatlogs import tracer

# Load backend/.env
load_dotenv()

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    PYDANTIC_AI_AVAILABLE = True
except ImportError:
    PYDANTIC_AI_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_SDK_AVAILABLE = True
except ImportError:
    OPENAI_SDK_AVAILABLE = False


class ExtractionError(Exception):
    """Raised when both TensorMux and Groq extraction fail."""
    pass


def parse_invoice_json(filepath: str) -> InvoiceFact:
    """
    Local JSON Fixture Parser (Used by backend ingest).
    Parses JSON fixture into domain InvoiceFact with integer cents.
    """
    with open(filepath, mode="r", encoding="utf-8") as f:
        data = json.load(f)

    lines: list[InvoiceLine] = []
    for raw in data.get("line_items", []):
        ctype_str = raw["charge_type"].upper()
        try:
            ctype_enum = ChargeType[ctype_str]
        except KeyError:
            ctype_enum = ChargeType.OTHER

        lines.append(
            InvoiceLine(
                charge_type=ctype_enum,
                amount_cents=raw["amount_cents"],
                billed_minutes=raw.get("billed_minutes"),
                description=raw.get("description"),
            )
        )

    return InvoiceFact(
        invoice_id=data["invoice_number"],
        shipment_id=data["shipment_id"],
        carrier_name=data["carrier_name"],
        bill_of_lading=data["bill_of_lading"],
        lines=tuple(lines),
    )


def _call_openai_compatible_json(
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
) -> InvoiceFact:
    """
    Calls OpenAI-compatible endpoint (TensorMux or Groq) using Pydantic AI or OpenAI SDK.
    """
    system_prompt = (
        "Extract carrier invoice data into valid JSON matching this structure:\n"
        "{\n"
        '  "invoice_number": "INV-FRT-2026-09",\n'
        '  "shipment_id": "SHP-88220",\n'
        '  "carrier_name": "FedEx Freight",\n'
        '  "bill_of_lading": "BOL-US-99121",\n'
        '  "line_items": [\n'
        '    {"charge_type": "BASE_FREIGHT", "amount_cents": 85000, "description": "Freight"},\n'
        '    {"charge_type": "DETENTION", "amount_cents": 17500, "billed_minutes": 60},\n'
        '    {"charge_type": "LIFTGATE", "amount_cents": 9500}\n'
        "  ]\n"
        "}"
    )

    if PYDANTIC_AI_AVAILABLE:
        tm_model = OpenAIModel(model_name, base_url=base_url, api_key=api_key)
        tm_agent = Agent(tm_model, output_type=InvoiceFact)
        res = tm_agent.run_sync(prompt)
        if res and res.data:
            return res.data

    if OPENAI_SDK_AVAILABLE:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = response.choices[0].message.content
        data = json.loads(content)

        lines = []
        for raw in data.get("line_items", []):
            ctype_str = str(raw["charge_type"]).upper()
            try:
                ctype_enum = ChargeType[ctype_str]
            except KeyError:
                ctype_enum = ChargeType.OTHER
            lines.append(
                InvoiceLine(
                    charge_type=ctype_enum,
                    amount_cents=int(raw["amount_cents"]),
                    billed_minutes=raw.get("billed_minutes"),
                    description=raw.get("description"),
                )
            )

        return InvoiceFact(
            invoice_id=data.get("invoice_number", data.get("invoice_id", "INV-UNKNOWN")),
            shipment_id=data.get("shipment_id", "SHP-UNKNOWN"),
            carrier_name=data.get("carrier_name", "UNKNOWN"),
            bill_of_lading=data.get("bill_of_lading", "BOL-UNKNOWN"),
            lines=tuple(lines),
        )

    raise ExtractionError("Neither pydantic_ai nor openai package is available")


def extract_invoice_with_fallback(
    raw_text_or_json: str,
    tensormux_model: str = "glm-4-7-flash",
    groq_model: str = "qwen/qwen3.6-27b",
) -> InvoiceFact:
    """
    2-Tier Resilient Invoice Extractor:
    1. Try Primary: TensorMux Inference Gateway ('glm-4-7-flash')
    2. Try Fallback: Groq Free Tier API ('qwen/qwen3.6-27b')
    3. If both fail -> Raise ExtractionError
    """
    # Tier 1: TensorMux
    tensormux_key = os.getenv("TENSORMUX_API_KEY")
    tensormux_base_url = os.getenv("TENSORMUX_BASE_URL", "https://api.tensormux.com/v1")

    if tensormux_key and tensormux_key.strip():
        try:
            fact = _call_openai_compatible_json(
                base_url=tensormux_base_url,
                api_key=tensormux_key,
                model_name=tensormux_model,
                prompt=raw_text_or_json,
            )
            tracer.trace_extraction(
                trace_id=f"trace-freight-{fact.shipment_id.lower()}",
                invoice_id=fact.invoice_id,
                provider="TensorMux",
                lines_count=len(fact.lines),
                billed_total_cents=fact.billed_total_cents,
                model_name=tensormux_model,
            )
            return fact
        except Exception as e:
            print(f"[TensorMux Warning] Extraction failed: {e}. Trying Groq fallback...")

    # Tier 2: Groq Fallback
    groq_key = os.getenv("GROQ_API_KEY")
    groq_base_url = "https://api.groq.com/openai/v1"

    if groq_key and groq_key.strip():
        try:
            fact = _call_openai_compatible_json(
                base_url=groq_base_url,
                api_key=groq_key,
                model_name=groq_model,
                prompt=raw_text_or_json,
            )
            tracer.trace_extraction(
                trace_id=f"trace-freight-{fact.shipment_id.lower()}",
                invoice_id=fact.invoice_id,
                provider="Groq",
                lines_count=len(fact.lines),
                billed_total_cents=fact.billed_total_cents,
                model_name=groq_model,
            )
            return fact
        except Exception as e:
            print(f"[Groq Warning] Extraction failed: {e}.")

    raise ExtractionError("Both TensorMux and Groq extraction failed or API keys were missing.")

