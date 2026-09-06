from contextlib import contextmanager

from shortpay import neatlogs as neatlogs_module


class FakeSpan:
    def __init__(self, name, kind, parent):
        self.name = name
        self.kind = kind
        self.parent = parent
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class FakeNeatlogsSDK:
    def __init__(self):
        self.spans = []
        self.stack = []
        self.flush_calls = 0

    def init(self, **_kwargs):
        return None

    @contextmanager
    def trace(self, name, kind):
        span = FakeSpan(name, kind, self.stack[-1].name if self.stack else None)
        self.spans.append(span)
        self.stack.append(span)
        try:
            yield span
        finally:
            self.stack.pop()

    def flush(self, *_args, **_kwargs):
        self.flush_calls += 1
        return True

    def shutdown(self, *_args, **_kwargs):
        return None


def test_workflow_groups_match_and_populates_dashboard_fields(monkeypatch):
    sdk = FakeNeatlogsSDK()
    monkeypatch.setattr(neatlogs_module, "neatlogs", sdk)
    monkeypatch.setattr(neatlogs_module, "SDK_AVAILABLE", True)
    monkeypatch.setenv("NEATLOGS_ENABLED", "1")

    tracer = neatlogs_module.NeatlogsTracer(api_key="test-key")
    with tracer.workflow(
        "invoice_audit",
        trace_id="trace-freight-shp-88220",
        input_value={"invoice_id": "INV-FRT-2026-09"},
    ) as workflow:
        tracer.trace_match(
            trace_id="trace-freight-shp-88220",
            invoice_id="INV-FRT-2026-09",
            shipment_id="SHP-88220",
            expected_total_cents=92500,
            dispute_total_cents=19500,
            rules_fired=["DETENTION_OVERBILL", "LIFTGATE_OVERBILL"],
            evidence_hash="abc123",
        )
        workflow.set_output({"expected_cents": 92500, "dispute_cents": 19500})

    root, match = sdk.spans
    assert root.name == "invoice_audit"
    assert root.kind == "WORKFLOW"
    assert root.parent is None
    assert root.attributes["shortpay.trace_id"] == "trace-freight-shp-88220"
    assert match.name == "match_evidence"
    assert match.kind == "WORKFLOW"
    assert match.parent == "invoice_audit"
    assert match.attributes["shortpay.trace_id"] == "trace-freight-shp-88220"
    assert '"expected_cents": 92500' in match.attributes["output.value"]
    assert '"dispute_cents": 19500' in match.attributes["output.value"]
    assert sdk.flush_calls == 1


def test_fixture_startup_suppresses_observability_noise(monkeypatch):
    import main

    calls = []

    class RecordingOffice:
        def ingest(self, _facts, **kwargs):
            calls.append(("ingest", kwargs))

        def match(self, _case_key, **kwargs):
            calls.append(("match", kwargs))

    monkeypatch.setattr(main, "office", RecordingOffice())
    main.auto_ingest_fixtures()

    assert calls
    assert all(call[1]["emit_trace"] is False for call in calls)
