from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from frontend.services.shortpay_api import ShortpayAPIError


dashboard = Blueprint("dashboard", __name__)

COLUMNS = (
    "Out of scope",
    "Auto-closed",
    "Major exceptions",
    "Short-paid",
    "Paid as billed",
)


MAX_PDF_BYTES = 15 * 1024 * 1024


def _api():
    return current_app.extensions["shortpay_api"]


def _wants_json() -> bool:
    return "application/json" in (request.headers.get("Accept") or "")


def _ingest_fail(message: str, status: int):
    if _wants_json():
        return jsonify({"error": message}), status
    flash(message, "error")
    return redirect(url_for("dashboard.board"))


@dashboard.get("/")
def board():
    grouped = {column: [] for column in COLUMNS}
    try:
        cases = _api().list_cases()
        for case in cases:
            column = case.get("kanban", {}).get("column", "Out of scope")
            grouped.setdefault(column, []).append(case)
    except ShortpayAPIError as exc:
        flash(str(exc), "error")

    return render_template("board.html", columns=COLUMNS, grouped=grouped)


@dashboard.get("/cases/<invoice_id>")
def case_detail(invoice_id: str):
    try:
        case = _api().get_case(invoice_id)
    except ShortpayAPIError as exc:
        flash(str(exc), "error")
        return redirect(url_for("dashboard.board"))
    return render_template("case_detail.html", case=case)


@dashboard.post("/cases/<invoice_id>/decide")
def decide(invoice_id: str):
    action = request.form.get("action_type", "")
    shipment_id = request.form.get("shipment_id", "")
    override_reason = request.form.get("override_reason", "").strip()

    if action not in {"ApproveShortPay", "OverridePayAsBilled"}:
        flash("Choose a valid case action.", "error")
        return redirect(url_for("dashboard.case_detail", invoice_id=invoice_id))
    if action == "OverridePayAsBilled" and not override_reason:
        flash("A reason is required to pay the invoice as billed.", "error")
        return redirect(url_for("dashboard.case_detail", invoice_id=invoice_id))

    try:
        case = _api().get_case(invoice_id)
        payload = {
            "invoice_id": invoice_id,
            "shipment_id": shipment_id,
            "action_type": action,
            "expected_payable_cents": case["expected_cents"],
            "override_reason": override_reason,
        }
        result = _api().decide(payload)
    except (KeyError, ShortpayAPIError) as exc:
        flash(f"Decision failed: {exc}", "error")
        return redirect(url_for("dashboard.case_detail", invoice_id=invoice_id))

    flash(f"Case moved to {result['new_disposition']}.", "success")
    return redirect(url_for("dashboard.board"))


@dashboard.post("/ingest")
def ingest_invoice():
    invoice_text = request.form.get("invoice_text", "").strip()
    if not invoice_text:
        flash("Paste invoice text before running extraction.", "error")
        return redirect(url_for("dashboard.board"))

    try:
        result = _api().ingest_invoice(invoice_text)
    except ShortpayAPIError as exc:
        flash(str(exc), "error")
        return redirect(url_for("dashboard.board"))

    flash(
        f"{result['invoice_id']} extracted through {result['provider']} and matched.",
        "success",
    )
    return redirect(url_for("dashboard.case_detail", invoice_id=result["invoice_id"]))


@dashboard.post("/ingest/pdf")
def ingest_invoice_pdf():
    uploaded = request.files.get("invoice_pdf")
    if uploaded is None or not uploaded.filename:
        return _ingest_fail("Choose a carrier PDF before extracting.", 400)

    filename = uploaded.filename
    if not filename.lower().endswith(".pdf"):
        return _ingest_fail("PDF only.", 400)

    file_bytes = uploaded.read()
    if not file_bytes:
        return _ingest_fail("PDF is empty.", 400)
    if len(file_bytes) > MAX_PDF_BYTES:
        return _ingest_fail("PDF exceeds 15 MB.", 400)

    try:
        result = _api().ingest_invoice_pdf(filename, file_bytes, uploaded.mimetype)
    except ShortpayAPIError as exc:
        return _ingest_fail(str(exc), 502)

    message = f"{result['invoice_id']} extracted through {result['provider']} and matched."
    redirect_to = url_for("dashboard.case_detail", invoice_id=result["invoice_id"])
    if _wants_json():
        return jsonify({**result, "redirect": redirect_to, "message": message})
    flash(message, "success")
    return redirect(redirect_to)


@dashboard.get("/healthz")
def healthcheck():
    return {"status": "ok", "service": "shortpay-frontend"}
