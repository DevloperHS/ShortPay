# 3. Pydantic AI & Sponsor Tool Integration (TensorMux + Groq Fallback)

- **Status**: Accepted
- **Date**: 2026-09-06

## Context
For the "Syndicate by Maximor" hackathon (Track 2: Autonomous Office of the CFO), invoice extraction requires structured Pydantic AI output over LLM inference APIs. 

To ensure maximum reliability, we need a 2-tier LLM inference strategy:
1. **TensorMux** (Primary Inference Gateway).
2. **Groq** (Secondary Free-Tier Fallback at `https://api.groq.com/openai/v1`).

If both TensorMux and Groq fail (e.g. invalid keys or network errors), the system must raise an explicit `ExtractionError`.

## Decision
1. **Pydantic Models for Schemas & FastAPI**: Use Pydantic `BaseModel` across `shortpay.evidence`, `shortpay.case`, and `shortpay.ledgers`.
2. **2-Tier Resilient Extraction in `invoice_extract.py`**:
   - **Primary**: Send invoice extraction to the TensorMux OpenAI-compatible endpoint using Pydantic AI's `OpenAIChatModel` and `OpenAIProvider`, returning a validated `InvoiceFact`.
   - **Fallback**: If TensorMux fails or its key is missing, fall back automatically to Groq (`https://api.groq.com/openai/v1`, model `qwen/qwen3.8-27b`, key `GROQ_API_KEY`).
   - **Failure Handling**: If both fail, raise `ExtractionError("Both TensorMux and Groq extraction failed")`.
3. **Neatlogs Observability**: Wrap `AuditOffice` operations (`ingest`, `match`, `decide`) and adapter calls with Neatlogs spans (`trace-freight-shp-88220`).
4. **Pure Core Preservation**: The `match_evidence` function remains a pure mathematical function that operates on validated Pydantic facts without any LLM calls or I/O.
5. **Sponsor Rate Guardrail**: Apply a process-local rolling-window limit of 60 outbound HTTP attempts per 60 seconds to each inference provider. Enforce it in the HTTP transport hook so SDK retries and concurrent requests are counted, and block attempt 61 before transmission.

## Consequences
- High resilience: Automatically switches to Groq if TensorMux encounters rate limits or errors.
- Strict error reporting when both LLM providers fail.
