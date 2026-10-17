"""Deployment entrypoint; legacy main:app and mock_main:app stay supported."""
import os

from mock_processor import MockProcessor

mode = os.environ.get("BLURFING_DEPLOY_MODE", "mock").strip()
if mode not in {"mock", "real"}:
    raise ValueError("BLURFING_DEPLOY_MODE must be mock or real.")
if mode == "mock" and os.environ.get("BLURFING_PROCESSOR", "").strip():
    raise ValueError("Mock deployment must not configure a real processor.")

from main import app  # noqa: E402: validate the mode before importing a configured plugin.

if mode == "mock":
    app.state.protection_processor = MockProcessor(float(os.environ.get("BLURFING_MOCK_DELAY_SECONDS", "0")))
elif isinstance(app.state.protection_processor, MockProcessor):
    raise ValueError("Real deployment must not use MockProcessor.")


@app.get("/info")
def deployment_info():
    return {
        "service": "BlurFing", "mode": mode, "mock_no_protection": mode == "mock",
        "v1_processor_connected": callable(app.state.protection_processor),
        "production_approved": False,
    }
