"""V2 deployment liveness is separate from model readiness."""
from experimental_photo_main import app


@app.get("/health")
def health():
    return {"status": "alive"}
