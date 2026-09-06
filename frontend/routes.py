from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for

from frontend.services.shortpay_api import ShortpayAPIError


dashboard = Blueprint("dashboard", __name__)


MAX_PDF_BYTES = 15 * 1024 * 1024


def _api():
    return current_app.extensions["shortpay_api"]


def _api_error(exc: ShortpayAPIError, *, not_found: int = 502):
    status = exc.status_code
    if status == 404:
        return jsonify({"detail": str(exc)}), not_found
    if status in {400, 422, 502}:
        return jsonify({"detail": str(exc)}), status
    return jsonify({"detail": str(exc)}), 502


def _wants_json() -> bool:
    return "application/json" in (request.headers.get("Accept") or "")


def _ingest_fail(message: str, status: int):
    if _wants_json():
        return jsonify({"error": message, "detail": message}), status
    flash(message, "error")
    return redirect(url_for("dashboard.board"))


@dashboard.get("/", endpoint="board")
@dashboard.get("/cases/<invoice_id>", endpoint="case_detail")
def app(invoice_id: str | None = None):
    return render_template("app.html")


@dashboard.get("/api/ui/cases")
def list_cases():
    try:
        return jsonify(_api().list_cases())
    except ShortpayAPIError as exc:
        return _api_error(exc)


@dashboard.get("/api/ui/cases/<invoice_id>")
def get_case(invoice_id: str):
    try:
        return jsonify(_api().get_case(invoice_id))
    except ShortpayAPIError as exc:
        return _api_error(exc, not_found=404)


@dashboard.post("/api/ui/cases/<invoice_id>/decide")
def decide(invoice_id: str):
    payload = request.get_json(silent=True) or {}
    action = payload.get("action_type", "")
    override_reason = str(payload.get("override_reason", "")).strip()

    if action not in {"ApproveShortPay", "OverridePayAsBilled"}:
        return jsonify({"detail": "Choose a valid case action."}), 400
    if action == "OverridePayAsBilled" and not override_reason:
        return jsonify({"detail": "A reason is required to pay the invoice as billed."}), 400

    expected_payable_cents = payload.get("expected_payable_cents")
    if action == "ApproveShortPay":
        if not isinstance(expected_payable_cents, int) or isinstance(expected_payable_cents, bool):
            return jsonify({"detail": "Approve short-pay using the displayed payable."}), 400

    try:
        case = _api().get_case(invoice_id)
        result = _api().decide(
            {
                "invoice_id": invoice_id,
                "shipment_id": case["shipment_id"],
                "action_type": action,
                "expected_payable_cents": expected_payable_cents or 0,
                "override_reason": override_reason,
            }
        )
    except (KeyError, ShortpayAPIError) as exc:
        if isinstance(exc, ShortpayAPIError):
            return _api_error(exc)
        return jsonify({"detail": f"Decision failed: {exc}"}), 502

    return jsonify(result)


@dashboard.post("/api/ui/ingest")
def ingest_invoice():
    invoice_text = (request.get_json(silent=True) or {}).get("invoice_text", "").strip()
    if not invoice_text:
        return jsonify({"detail": "Paste invoice text before running extraction."}), 400

    try:
        result = _api().ingest_invoice(invoice_text)
    except ShortpayAPIError as exc:
        return _api_error(exc)

    return jsonify(result), 201


@dashboard.post("/ingest/pdf")
@dashboard.post("/api/ui/ingest/pdf")
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
