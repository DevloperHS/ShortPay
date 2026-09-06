"""Render the demo carrier invoices in pdf/.

Run:
    UV_NO_CONFIG=1 uv run --with reportlab python pdf/generate.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

PURPLE = HexColor("#4D148C")
ORANGE = HexColor("#FF6200")
INK = HexColor("#1C1C1C")
MUTED = HexColor("#5E5A54")
RULE = HexColor("#D8D2C8")
WELL = HexColor("#F6F3EE")
ROW = HexColor("#FBFAF7")
LAVENDER = HexColor("#E8DFF3")

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class InvoiceLine:
    charge_type: str
    description: str
    qty: str
    amount_cents: int


@dataclass(frozen=True)
class DemoInvoice:
    invoice_id: str
    shipment_id: str
    bill_of_lading: str
    carrier_name: str
    invoice_date: str
    mode: str
    tracking: str
    origin: str
    destination: str
    service: str
    remit_city: str
    lines: tuple[InvoiceLine, ...]
    note: str = ""
    bill_to_name: str = "Shortpay Logistics AP"
    bill_to_lines: tuple[str, ...] = (
        "1200 Dockside Ave, Suite 400",
        "Chicago, IL 60607",
    )
    remit_extra: tuple[str, ...] = field(default_factory=tuple)

    @property
    def filename(self) -> str:
        return f"{self.invoice_id}.pdf"

    @property
    def base_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines if line.charge_type == "BASE_FREIGHT")

    @property
    def total_cents(self) -> int:
        return sum(line.amount_cents for line in self.lines)

    @property
    def accessorial_cents(self) -> int:
        return self.total_cents - self.base_cents

    @property
    def charge_types(self) -> str:
        return "  ·  ".join(dict.fromkeys(line.charge_type for line in self.lines))

    @property
    def detention_minutes(self) -> str | None:
        for line in self.lines:
            if line.charge_type == "DETENTION":
                digits = "".join(ch for ch in line.qty if ch.isdigit())
                return digits or None
        return None


def money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def label(c: canvas.Canvas, x: float, y: float, text: str, size: float = 7) -> None:
    c.setFillColor(MUTED)
    c.setFont("Helvetica", size)
    c.drawString(x, y, text.upper())


def value(c: canvas.Canvas, x: float, y: float, text: str, size: float = 10, bold: bool = False) -> None:
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(x, y, text)


def draw_wordmark(c: canvas.Canvas, x: float, y: float, carrier: str) -> None:
    c.setFont("Helvetica-Bold", 22)
    first, _, rest = carrier.partition(" ")
    if first.lower() == "fedex" and rest:
        c.setFillColor(white)
        c.drawString(x, y, first)
        c.setFillColor(ORANGE)
        c.drawString(x + c.stringWidth(first, "Helvetica-Bold", 22) + 4, y, rest)
        return
    c.setFillColor(white)
    c.drawString(x, y, carrier)


def draw_invoice(path: Path, invoice: DemoInvoice) -> None:
    width, height = letter
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setTitle(f"{invoice.carrier_name} Invoice {invoice.invoice_id}")
    c.setAuthor(invoice.carrier_name)
    c.setSubject(f"Shipment {invoice.shipment_id} / {invoice.bill_of_lading}")

    c.setFillColor(PURPLE)
    c.rect(0, height - 86, width, 86, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(0, height - 90, width, 4, fill=1, stroke=0)

    draw_wordmark(c, 40, height - 42, invoice.carrier_name)
    c.setFillColor(LAVENDER)
    c.setFont("Helvetica", 9)
    c.drawString(40, height - 62, "Carrier freight invoice")

    c.setFillColor(white)
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 40, height - 32, "INVOICE NUMBER")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(width - 40, height - 50, invoice.invoice_id)
    c.setFont("Helvetica", 8)
    c.drawRightString(width - 40, height - 66, f"Invoice date  {invoice.invoice_date}")

    y = height - 128
    c.setFillColor(WELL)
    c.roundRect(40, y - 8, width - 80, 38, 4, fill=1, stroke=0)
    facts = [
        (48, "Shipment ID", invoice.shipment_id),
        (210, "Bill of lading", invoice.bill_of_lading),
        (372, "Mode", invoice.mode),
        (470, "PRO / tracking", invoice.tracking),
    ]
    for x, key, val in facts:
        label(c, x, y + 16, key)
        value(c, x, y + 2, val, bold=True)

    y = height - 210
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.roundRect(40, y, 250, 72, 4, fill=0, stroke=1)
    c.roundRect(322, y, 250, 72, 4, fill=0, stroke=1)
    label(c, 52, y + 56, "Bill to")
    value(c, 52, y + 40, invoice.bill_to_name, bold=True, size=9)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(52, y + 26, invoice.bill_to_lines[0])
    c.drawString(52, y + 14, invoice.bill_to_lines[1])
    label(c, 334, y + 56, "Remit to")
    value(c, 334, y + 40, invoice.carrier_name, bold=True, size=9)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    remit = invoice.remit_extra or ("Accounts receivable", invoice.remit_city)
    c.drawString(334, y + 26, remit[0])
    c.drawString(334, y + 14, remit[1])

    y = height - 268
    label(c, 40, y + 14, "Origin")
    value(c, 40, y - 2, invoice.origin)
    label(c, 250, y + 14, "Destination")
    value(c, 250, y - 2, invoice.destination)
    label(c, 470, y + 14, "Service")
    value(c, 470, y - 2, invoice.service)

    table_top = height - 300
    c.setFillColor(PURPLE)
    c.roundRect(40, table_top - 22, 532, 26, 3, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(52, table_top - 13, "TYPE")
    c.drawString(126, table_top - 13, "DESCRIPTION")
    c.drawString(346, table_top - 13, "QTY / TIME")
    c.drawRightString(560, table_top - 13, "AMOUNT")

    row_h = 28
    for i, line in enumerate(invoice.lines):
        top = table_top - 22 - (i + 1) * row_h
        if i % 2 == 0:
            c.setFillColor(ROW)
            c.rect(40, top, 532, row_h, fill=1, stroke=0)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.4)
        c.line(40, top, 572, top)
        c.setFillColor(PURPLE)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawString(52, top + 11, line.charge_type)
        c.setFillColor(INK)
        c.setFont("Helvetica", 9)
        c.drawString(126, top + 10, line.description)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(346, top + 10, line.qty)
        c.setFillColor(INK)
        c.setFont("Helvetica", 9)
        c.drawRightString(560, top + 10, money(line.amount_cents))

    body_bottom = table_top - 22 - len(invoice.lines) * row_h
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(40, body_bottom, 572, body_bottom)

    totals_top = body_bottom - 18
    c.setFillColor(WELL)
    c.roundRect(330, totals_top - 78, 242, 90, 5, fill=1, stroke=0)
    pairs = [
        ("Line haul", money(invoice.base_cents)),
        ("Accessorials", money(invoice.accessorial_cents)),
        ("Total billed", money(invoice.total_cents)),
    ]
    for i, (key, amount) in enumerate(pairs):
        yy = totals_top - 8 - i * 22
        c.setFillColor(INK if i == 2 else MUTED)
        c.setFont("Helvetica-Bold" if i == 2 else "Helvetica", 9 if i == 2 else 8)
        c.drawString(346, yy, key.upper() if i == 2 else key)
        c.setFillColor(ORANGE if i == 2 else INK)
        c.setFont("Helvetica-Bold" if i == 2 else "Helvetica", 11 if i == 2 else 9)
        c.drawRightString(556, yy, amount)

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(40, totals_top - 8, "Charge types are printed as billed:")
    c.setFillColor(INK)
    c.setFont("Helvetica", 8)
    c.drawString(40, totals_top - 22, invoice.charge_types)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    note_y = totals_top - 40
    if invoice.detention_minutes:
        c.drawString(40, note_y, f"Detention billed minutes: {invoice.detention_minutes}")
        note_y -= 14
    if invoice.note:
        c.drawString(40, note_y, invoice.note)
        note_y -= 14
    c.drawString(40, note_y, "Do not pay from this copy until AP audit is complete.")

    c.setFillColor(PURPLE)
    c.rect(0, 0, width, 36, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.rect(0, 36, width, 3, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica", 8)
    c.drawString(40, 16, f"{invoice.carrier_name}  ·  {invoice.invoice_id}  ·  {invoice.shipment_id}")
    c.drawRightString(width - 40, 16, "Page 1 of 1")

    c.showPage()
    c.save()


DEMO_INVOICES = (
    DemoInvoice(
        invoice_id="INV-FRT-2026-09",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="09 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("DETENTION", "Driver detention fee", "60 mins billed", 17500),
            InvoiceLine("LIFTGATE", "Liftgate delivery service", "1 service", 9500),
        ),
        note="Hero case. Billed $1,120.00 against authorized $925.00.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-10",
        shipment_id="SHP-88221",
        bill_of_lading="BOL-US-99122",
        carrier_name="FedEx Freight",
        invoice_date="10 Sep 2026",
        mode="LTL",
        tracking="88221-99122",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("LIFTGATE", "Liftgate delivery service", "1 service", 3800),
        ),
        note="Small liftgate overbill. Policy auto-close territory after a prior approval.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-12",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="12 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("DETENTION", "Driver detention fee", "60 mins billed", 17500),
            InvoiceLine("LIFTGATE", "Liftgate delivery service", "1 service", 9500),
        ),
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-13",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="13 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Economy LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),),
        note="Clean bill. Line haul only.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-14",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="14 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("LIFTGATE", "Liftgate delivery service", "1 service", 9500),
        ),
        note="Liftgate billed at a dock door.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-15",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="15 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("DETENTION", "Driver detention fee", "60 mins billed", 17500),
        ),
        note="Detention only. No liftgate line.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-16",
        shipment_id="SHP-88220",
        bill_of_lading="BOL-US-99121",
        carrier_name="FedEx Freight",
        invoice_date="16 Sep 2026",
        mode="LTL",
        tracking="88220-99121",
        origin="Memphis, TN  38118",
        destination="Chicago, IL  60607  ·  dock present",
        service="Priority LTL",
        remit_city="Memphis, TN 38110",
        remit_extra=("P.O. Box 10306", "Memphis, TN 38110"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 85000),
            InvoiceLine("OTHER", "Reweigh / inspection surcharge", "1 charge", 4000),
        ),
        note="Unexplained OTHER line. Extractor must not invent a payable.",
    ),
    DemoInvoice(
        invoice_id="INV-OCN-2026-01",
        shipment_id="SHP-88219",
        bill_of_lading="BOL-US-99120",
        carrier_name="Maersk",
        invoice_date="08 Sep 2026",
        mode="OCEAN",
        tracking="MAEU-99120",
        origin="Rotterdam, NL",
        destination="Newark, NJ  07114  ·  terminal",
        service="Ocean FCL",
        remit_city="Copenhagen, DK",
        remit_extra=("Esplanaden 50", "Copenhagen, DK"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Ocean freight", "1 container", 420000),
            InvoiceLine("DETENTION", "Terminal detention", "120 mins billed", 15000),
        ),
        note="Ocean row. v1 should skip as out of scope once matched.",
    ),
    DemoInvoice(
        invoice_id="INV-FRT-2026-18",
        shipment_id="SHP-88222",
        bill_of_lading="BOL-US-99123",
        carrier_name="XPO Logistics",
        invoice_date="18 Sep 2026",
        mode="LTL",
        tracking="XPO-88222",
        origin="Atlanta, GA  30318",
        destination="Nashville, TN  37210  ·  dock present",
        service="Standard LTL",
        remit_city="Greenwich, CT 06831",
        remit_extra=("Five American Lane", "Greenwich, CT 06831"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Standard LTL transit", "1 shipment", 64000),
            InvoiceLine("LIFTGATE", "Liftgate delivery service", "1 service", 12500),
            InvoiceLine("DETENTION", "Driver detention fee", "90 mins billed", 22500),
        ),
    ),
    DemoInvoice(
        invoice_id="INV-TL-2026-01",
        shipment_id="SHP-88223",
        bill_of_lading="BOL-US-99124",
        carrier_name="Old Dominion",
        invoice_date="19 Sep 2026",
        mode="TL",
        tracking="ODFL-99124",
        origin="Richmond, VA  23230",
        destination="Charlotte, NC  28208  ·  dock present",
        service="Truckload",
        remit_city="Thomasville, NC 27360",
        remit_extra=("500 Old Dominion Way", "Thomasville, NC 27360"),
        lines=(
            InvoiceLine("BASE_FREIGHT", "Truckload line haul", "1 load", 210000),
            InvoiceLine("DETENTION", "Driver detention fee", "180 mins billed", 22500),
        ),
        note="Truckload detention. Same extract schema as LTL.",
    ),
)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for invoice in DEMO_INVOICES:
        dest = ROOT / invoice.filename
        draw_invoice(dest, invoice)
        print(dest)


if __name__ == "__main__":
    main()
