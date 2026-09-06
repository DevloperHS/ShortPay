import os
from pathlib import Path

from dotenv import load_dotenv
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live-sponsors",
        action="store_true",
        default=False,
        help="run tests that call the configured TensorMux, Groq, and Neatlogs endpoints",
    )


def pytest_configure(config):
    if config.getoption("--live-sponsors"):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    else:
        os.environ["NEATLOGS_ENABLED"] = "0"


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live-sponsors"):
        return

    skip_live = pytest.mark.skip(reason="requires --live-sponsors")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_live)


def pytest_sessionfinish(session, exitstatus):
    if not session.config.getoption("--live-sponsors"):
        return

    from shortpay.neatlogs import tracer

    tracer.shutdown()
