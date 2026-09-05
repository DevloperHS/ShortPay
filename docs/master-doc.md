📝 Product Requirements Document (PRD)

Product Name: Parakh (formerly Audit-Swarm)
Date: September 2026
Target Event: Syndicate by Maximor Hackathon (Track 2: Autonomous CFO)

1. Product Overview

Parakh (Hindi for "scrutiny/examination") is an autonomous, multi-agent defense system designed to eliminate the manual bottleneck of external financial audits. Built natively on the AO (Agent Orchestrator) framework and leveraging TensorMux for routing, it autonomously gathers, extracts, and reconciles the "PBC (Provided By Client)" transaction list required by auditors, routing only major discrepancies to the CFO for 1-click resolution.

2. Target Persona & The Trigger

Primary User: The Corporate Controller.

The Pain Point: It is "Audit Week." The external auditors (e.g., Deloitte/KPMG) have just requested proof for 50 random ledger transactions. Historically, this meant 40+ hours of manually searching through ERPs, hunting for PDF invoices in emails, and matching amounts.

The Trigger: The Controller logs into Parakh and uploads the auditor's request as a simple CSV file.

3. Core Features & Capabilities

Feature 1: The Agentic Swarm (Backend)

Description: The moment the CSV is uploaded, our AO-based workflow initiates.

Sub-Agents:

The Hunter: Scans the mock corporate Google Drive to find the exact PDF invoice matching the ledger entry.

The Extractor: Routes the PDF through TensorMux to a multimodal LLM to parse the line items and total amounts.

The Matcher: A deterministic calculator that checks the extracted amount against the ERP baseline.

Feature 2: The Real-Time Kanban Board (Frontend)

Description: A calming, cream-and-white workspace where the Controller monitors the swarm's progress.

Columns: Scanning, Minor Variances (Auto-Resolved), Major Exceptions (Needs Review).

Requirement: The board must feel "alive." Cards should glide between columns automatically via a 2-second polling loop as the backend agents finish their tasks.

Feature 3: Proactive AI Exception Handling

Description: When a major exception occurs (e.g., a $15 variance), the AI doesn't just flag it—it acts as an assistant and prepares a solution.

Capabilities: The Action Modal will present the Controller with:

The highlighted math variance.

An AI-Drafted Vendor Email asking for clarification on the discrepancy.

A pre-filled ledger adjustment form.

1-Click buttons to execute these proposed solutions.

Feature 4: Immutable Evidence Trail (Sponsor USP)

Description: The system must satisfy strict corporate governance.

Requirement: Every time the AI extracts data or calculates a variance, it pushes a log to Neatlogs. The Action Modal will contain a discrete "View AI Audit Trail" link that allows the Controller (and eventually the external auditor) to see the exact deterministic and LLM logic used to approve the transaction.

4. The 3-Minute Hackathon Demo Script (The "Golden Path")

The Upload: The presenter acting as the Controller uploads a CSV of 5 transactions.

The Swarm Works: The UI shifts to the Kanban board. The judges watch 3 cards automatically glide from "Scanning" to "Auto-Resolved", proving the TensorMux backend extraction is working.

The Intercept: One card lands in "Major Exceptions."

The Action: The presenter clicks the card. The modal pops up. The presenter says, "The AI didn't just find the $15 error; it already drafted the email to the vendor to fix it." They click "Send AI Drafted Email."

The Climax: The Kanban board completely clears out. A beautiful Framer Motion confetti animation triggers. The screen transitions to a dashboard reading "Compliance Score: 100% - Ledger Fully Reconciled." A glowing badge confirms "Audit Evidence Securely Locked via Neatlogs."

5. Out of Scope (Do NOT build during the 30 hours)

Real integrations with NetSuite, SAP, or QuickBooks (use a local SQLite DB or JSON).

Real integrations with Gmail or Outlook (use a local mock_drive folder).

User Authentication / Login screens (waste of time for a 3-minute demo).

Settings pages or complex user profile management.

🏆 Master Blueprint: Autonomous Audit Responder (Parakh)

📂 1. Project Context (context.md)

The Solution Architecture

We are building a multi-agent swarm acting as an autonomous audit defense team.

Mandatory Hackathon Stack & Partners:

Agent Orchestrator (AO): The core operating framework. We will build our multi-agent logic directly using AO to spawn parallel workers that hunt for documents and reconcile them.

TensorMux (Inference Partner): Our open-source L7 routing gateway. All LLM API calls will point to the local TensorMux endpoint (http://localhost:8080/v1) to route tabular data extraction to fast local models and messy PDF vision tasks to heavy models.

Neatlogs (Venue Partner & Observability): An AI debugging platform that captures traces and spans. We will use Neatlogs as our "Immutable Evidence Trail" feature.

The Agent Swarm Logic (Built on AO)

Ledger Agent: Reads the auditor's target transaction (e.g., Txn #4992) and extracts the baseline amount from the ERP database.

Hunter Agent: Scans a mock local directory (representing email/Drive) and retrieves the raw PDF invoice.

Recon Agent: Uses TensorMux to extract text from the PDF. Calculates the variance.

If variance == 0: Mark as "Audit Ready."

If variance < $10: Auto-resolve as minor variance.

If variance > $10: Halt the process and push to the Human-in-the-Loop (HITL) exception dashboard.

🎨 2. Design System & UI Specs (design.md)

Core Aesthetic & Vibe

Theme: Premium, calming, high-trust financial workspace. Anti-ERP (no sterile grays or dense data grids).

Shapes: Soft, rounded corners ("bubbles") for all containers. No sharp edges.

Color Palette (Tailwind Reference):

Background (The Canvas): Soft Cream #F9F7F1 (A warm, paper-like off-white).

Containers (The Bubbles): Pure White #FFFFFF with a very subtle, soft drop-shadow (shadow-sm to shadow-md on hover) so they appear to float gently above the cream background.

Primary Text: Deep Crisp Black #111111 for maximum readability.

Secondary Text (Metadata): Soft Gray #71717A (Muted, but accessible).

Variance / Status Colors: Mint Green #E6F4EA (Match), Soft Rose #FCE8E6 (Exception), Soft Blue #E8F0FE (Processing).

Typography

Font Family: Modern, clean Sans-Serif (Inter, SF Pro, or standard system-ui).

Hierarchy: Board Headers (Bold, 18px), Card Vendor Names (Semi-bold, 16px), Card Amounts (Medium, 20px), Status Tags (Medium, 12px uppercase).

Layout Structure: The Kanban Board

Columns: 3 vertical columns (Scanning, Minor Variances, Major Exceptions).

Column Styling: Columns should not have harsh borders. They should be implied by the vertical alignment of the cards and a simple, bold Header text at the top.

UI Components

The Minimalist Card (White Bubble): rounded-2xl, pure white. Shows Vendor Name, Status Pill (e.g., [Missing PO] in Soft Rose), and Invoice Amount. Soft hover lift (hover:-translate-y-1).

The Analytical Action Modal (Popup): Blurs the background (backdrop-blur-sm). A large white bubble (rounded-2xl) showing a clean 2-column grid of Expected (ERP) vs. Actual (Extracted), the Variance Highlight pill, Agent Confidence bar, and 1-Click Action Buttons (Approve, Reject, Draft Email).

The Audit Link: A subtle gray text link at the absolute bottom center of the modal: "🔍 View AI Audit Trail (Neatlogs)".

Animations (The Wow-Factor)

Card Movement: Cards glide smoothly between columns (using Framer Motion) when polling detects a state change, proving the AI is working asynchronously.

Modal Opening: Scales up slightly (scale-95 to scale-100) and fades in quickly.

⚙️ 3. Technical Specification (spec.md)

System Architecture

Frontend (Dashboard): Next.js (TypeScript, App Router) styled with Tailwind CSS. Uses SWR/React Query to poll the backend every 2000ms.

Backend (Agent Swarm): Python 3.12+ with FastAPI. Built using the AO framework to orchestrate the worker logic.

State Management: Local SQLite database using SQLModel or SQLAlchemy to persist audit jobs.

LLM Inference: TensorMux running locally via Docker. OpenAI/Anthropic SDKs configured to use TensorMux base URL.

Observability: neatlogs.init(...) instrumented in the Python backend to capture all tool calls and logic spans.

Repository Structure (Monorepo)

parakh/
├── README.md
├── frontend/                # Next.js Application
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx     # Kanban Board View
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── KanbanColumn.tsx
│   │   │   ├── AuditCard.tsx      
│   │   │   └── ActionModal.tsx    
│   │   └── hooks/
│   │       └── useAuditPolling.ts # 2-second REST polling
│
└── backend/                 # Python FastAPI Application
    ├── main.py              # FastAPI server & routes
    ├── database.py          # SQLite & SQLModel setup
    ├── data/                
    │   ├── mock_drive/      # PDF invoices
    │   └── mock_db.sqlite   # Auto-generated SQLite DB
    ├── agents/
    │   ├── orchestrator.py  # Core AO logic & swarm definitions
    │   ├── hunter.py        
    │   ├── extractor.py     # Hits TensorMux
    │   └── matcher.py       
    └── utils/
        └── audit_logger.py  # Neatlogs trace wrappers


Database Schema (SQLite / SQLModel)

class AuditJob(SQLModel, table=True):
    id: str = Field(primary_key=True)
    vendor_name: str
    erp_expected_amount: float
    status: str # "SCANNING" | "MINOR_VARIANCE" | "MAJOR_EXCEPTION" | "APPROVED"
    extracted_amount: float | None = None
    variance_amount: float | None = None
    neatlogs_trace_url: str | None = None


The Data Flow

Next.js triggers POST /api/start-audit.

Backend creates 5 AuditJob rows in SQLite with status SCANNING.

Our AO script triggers the agent swarm. The Hunter finds the PDF, Extractor runs vision inference via TensorMux, and Matcher calculates the variance.

Python updates SQLite with the new state (MAJOR_EXCEPTION or APPROVED) and logs the decision via Neatlogs.

The Next.js frontend polls GET /api/audit-jobs and seamlessly animates the cards to their new columns.

🚨 4. Real-World Edge Cases & Failure Handling

The "Messy Drive" Failure (Hunter Agent): If the exact file match isn't found via simple metadata, the agent uses semantic fuzzy search. If genuinely missing, it creates a "Missing Documentation" exception and auto-drafts an email to the specific internal employee who made the transaction, asking them to upload the receipt.

The "Blurry Scan" Failure (Extractor Agent): We implement a TensorMux Retry Cascade. If the fast/cheap vision model (e.g., Llama Vision) returns a low confidence score on a blurry invoice, the agent automatically uses TensorMux to route the PDF to a heavier, more capable model (e.g., GPT-4o) for a second pass. Only if the heavy model fails does it push the item to the HITL Exception column.

⏱️ 5. Hackathon Execution Pacing (30 Hours)

Hour 1-6 (Data & Mock Silos): Set up the decoupled monorepo. Create the mock SQLite ERP data and generate the fake PDF invoices. Do not build live API integrations.

Hour 7-18 (Backend & Agents): Spin up TensorMux. Write the FastAPI routes. Build the AO workflow to orchestrate the Hunter and Extractor agents. Instrument every function with neatlogs.init.

Hour 19-26 (Frontend & UI): Build the Next.js Kanban board. Implement the 2-second SWR polling loop. Style the cards and the Action Modal according to the design specs.

Hour 27-30 (Pitch & Polish): Record the demo video. Make sure to explicitly open the Neatlogs dashboard on screen and show the TensorMux terminal logs to prove you satisfied all sponsor requirements.