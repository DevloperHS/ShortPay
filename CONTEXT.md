# Shortpay Domain Context & Glossary

## Domain Vocabulary

- **Shortpay**: The AP (Accounts Payable) process of paying an authorized payable amount while disputing the unauthorized variance (overbill) directly with the freight carrier.
- **Authorized Payable**: The calculated amount in integer cents that the shipper legitimately owes based on contract terms, facility features, and dock dwell timestamps.
- **Dispute Amount**: The difference (`billed_cents - expected_cents`) attached to a dispute notice with evidence (e.g. dock log receipt).
- **Accessorials**: Ancillary charges on freight bills (e.g., Liftgate fee, Driver Detention fee, Residential delivery fee, Fuel surcharge).
- **Integer Cents**: All monetary amounts represented strictly as integers (e.g., $925.00 is `92500` cents) to avoid IEEE float rounding bugs.
- **Dock Dwell**: Duration in minutes between arrival timestamp and departure timestamp at a facility.
- **Free Time**: Contractually agreed dwell duration (e.g., 30 minutes) before driver detention charges begin accruing.
- **Completed Hours**: Integer floor division (`dwell // 60`) for detention billing per contract terms.

## Technology Stack & Sponsor Integrations

- **Backend**: Python (FastAPI + Pydantic v2 / Pydantic AI + Pure Math Matcher).
- **Extraction Adapter**: 2-tier resilient extraction: Primary TensorMux $\rightarrow$ Secondary Groq API (`https://api.groq.com/openai/v1`).
- **Observability**: Neatlogs venue/observability tracing for case traces (`trace-freight-shp-88220`).
- **Frontend**: Next.js Web Application in `frontend/` (managed separately by Shubhu).
