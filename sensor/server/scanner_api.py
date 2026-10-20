"""Separate, single-worker scanner comparison API. Existing V1/PHOTO APIs stay intact."""
import asyncio
import base64
import hashlib
import io
import json
import math
import os
import re
import signal
import subprocess
import tempfile
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from PIL import Image

MAX_IMAGE = 4 * 1024 * 1024
MAX_PIXELS = 4_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def gray_image(data):
    if not 0 < len(data) <= MAX_IMAGE:
        raise ValueError("INVALID_SCANNER_IMAGE")
    with Image.open(io.BytesIO(data)) as check:
        if check.format != "PNG" or check.mode not in ("L", "RGB", "P") or check.width * check.height > MAX_PIXELS:
            raise ValueError("INVALID_SCANNER_IMAGE")
        if getattr(check, "n_frames", 1) != 1 or "transparency" in check.info:
            raise ValueError("INVALID_SCANNER_IMAGE")
        check.verify()
    with Image.open(io.BytesIO(data)) as image:
        if image.getexif().get(274, 1) != 1:
            raise ValueError("INVALID_SCANNER_IMAGE")
        rgb = image.convert("RGB")
        r, g, b = rgb.split()
        if r.tobytes() != g.tobytes() or r.tobytes() != b.tobytes():
            raise ValueError("GRAYSCALE_SCANNER_REQUIRED")
        return r.copy()


@dataclass(frozen=True)
class Config:
    python: str = ""
    ai_root: str = ""
    timeout: float = 600
    temp_root: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 3600:
            raise ValueError("SCANNER_TIMEOUT must be within (0, 3600]")

    def configured(self):
        return bool(self.python and Path(self.python).is_file() and self.ai_root and
                    (Path(self.ai_root) / "scripts/protect_fingerprint.py").is_file() and
                    (Path(self.ai_root) / "scripts/sourceafis_matcher.py").is_file())


class ApiError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class BoundedRequest:
    """Bound actual ASGI bytes before the multipart parser can create spool files."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [(b"cache-control", b"no-store")]
            await send(message)
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] != "POST":
            return await self.app(scope, receive, private_send)
        body = bytearray()
        try:
            async with asyncio.timeout(60):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > MAX_IMAGE + 65536:
                        raise ApiError(413, "IMAGE_TOO_LARGE")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except (ApiError, TimeoutError) as error:
            code = error.code if isinstance(error, ApiError) else "UPLOAD_TIMEOUT"
            status = error.status if isinstance(error, ApiError) else 408
            return await JSONResponse(dict(request_id="", code=code, retryable=False), status_code=status)(scope, receive, private_send)
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return dict(type="http.request", body=bytes(body), more_body=False)
            return await receive()
        await self.app(scope, replay, private_send)


async def stop_tree(process):
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(process.pid), "/T", "/F",
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await killer.wait()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def child_runner(config, source, output, dpi, request):
    env = dict(os.environ, TMPDIR=str(source.parent), TEMP=str(source.parent), TMP=str(source.parent))
    process = await asyncio.create_subprocess_exec(config.python, str(Path(__file__).with_name("scanner_worker.py")),
        "--input", str(source), "--output", str(output), "--ai-root", config.ai_root, "--dpi", str(dpi),
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}))
    wait = asyncio.create_task(process.wait())
    try:
        deadline = time.monotonic() + config.timeout
        while not wait.done():
            if time.monotonic() >= deadline:
                raise ApiError(504, "SCANNER_TIMEOUT")
            if await request.is_disconnected():
                raise ApiError(499, "CLIENT_DISCONNECTED")
            await asyncio.wait({wait}, timeout=.1)
        if wait.result() == 3:
            raise ApiError(422, "SCANNER_INPUT_REQUIRED")
        if wait.result() != 0:
            raise ApiError(503, "SCANNER_PROCESSOR_FAILED")
        transport = output / "transport.json"
        if not transport.is_file() or transport.stat().st_size > 8 * 1024 * 1024:
            raise ApiError(502, "INVALID_SCANNER_RESULT")
        return json.loads(transport.read_text(encoding="utf-8"))
    finally:
        await asyncio.shield(stop_tree(process))
        if not wait.done():
            wait.cancel()


def validate_result(payload, original, dpi):
    fields = {"processed_image_base64", "processed_sha256", "width", "height", "protection_status", "protection_engine", "changed_pixels", "match"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("INVALID_SCANNER_RESULT")
    if payload.get("protection_engine") != "blurfing-scanner-experimental" or payload.get("protection_status") not in ("success", "partial_success", "rejected"):
        raise ValueError("INVALID_SCANNER_RESULT")
    png = base64.b64decode(payload["processed_image_base64"], validate=True)
    processed = gray_image(png)
    if processed.size != original.size or type(payload["width"]) is not int or type(payload["height"]) is not int or payload["width"] != original.width or payload["height"] != original.height or digest(png) != payload["processed_sha256"]:
        raise ValueError("INVALID_SCANNER_RESULT")
    changed = sum(a != b for a, b in zip(original.tobytes(), processed.tobytes()))
    if type(payload["changed_pixels"]) is not int or payload["changed_pixels"] != changed:
        raise ValueError("INVALID_SCANNER_RESULT")
    if (payload["protection_status"] == "rejected" and changed) or (payload["protection_status"] != "rejected" and not changed):
        raise ValueError("INVALID_SCANNER_RESULT")
    match = payload["match"]
    match_fields = {"status", "score", "engine", "engine_version", "dpi", "probe_minutiae", "candidate_minutiae", "measured_at"}
    if not isinstance(match, dict) or set(match) != match_fields:
        raise ValueError("INVALID_MATCH_RESULT")
    if match.get("engine") != "SourceAFIS" or match.get("dpi") != dpi or match.get("status") not in ("measured", "unmeasurable", "unavailable"):
        raise ValueError("INVALID_MATCH_RESULT")
    if match["status"] == "measured":
        score = match.get("score")
        if type(score) not in (int, float) or not math.isfinite(score) or score < 0 or not match.get("engine_version") or not match.get("measured_at"):
            raise ValueError("INVALID_MATCH_RESULT")
        if any(type(match.get(k)) is not int or match[k] <= 0 for k in ("probe_minutiae", "candidate_minutiae")):
            raise ValueError("INVALID_MATCH_RESULT")
        if not isinstance(match["engine_version"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", match["engine_version"]) or datetime.fromisoformat(match["measured_at"]).tzinfo is None:
            raise ValueError("INVALID_MATCH_RESULT")
    elif match.get("score") is not None or match.get("measured_at") is not None:
        raise ValueError("INVALID_MATCH_RESULT")
    return payload


def create_app(config=None, runner=child_runner):
    config = config or Config(os.environ.get("BLURFING_SCANNER_PYTHON", ""), os.environ.get("BLURFING_SCANNER_AI_ROOT", ""))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BoundedRequest)
    slot = asyncio.Lock()

    @app.get("/ready")
    async def ready():
        configured = config.configured()
        return JSONResponse(dict(schema_version="scanner-comparison-v1", configured=configured,
            processing="experimental_scanner", matcher="SourceAFIS", inference_checked=False), status_code=200 if configured else 503)

    @app.post("/v1/scanner/compare")
    async def compare(request: Request):
        request_id = ""
        try:
            if not config.configured():
                raise ApiError(503, "SCANNER_NOT_CONFIGURED")
            if slot.locked():
                raise ApiError(429, "PROCESSOR_BUSY")
            async with slot:
                started = time.monotonic()
                async with request.form(max_files=1, max_fields=2) as form:
                    if sorted(k for k, _ in form.multi_items()) != ["dpi", "image", "request_id"]:
                        raise ApiError(422, "INVALID_SCANNER_REQUEST")
                    request_id = form.get("request_id")
                    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
                        request_id = ""
                        raise ApiError(422, "INVALID_SCANNER_REQUEST")
                    if not isinstance(form.get("dpi"), str) or not re.fullmatch(r"[0-9]{3,4}", form["dpi"]):
                        raise ApiError(422, "INVALID_DPI")
                    dpi = int(form["dpi"])
                    if not 100 <= dpi <= 2000 or not hasattr(form["image"], "read"):
                        raise ApiError(422, "INVALID_SCANNER_REQUEST")
                    uploaded = await form["image"].read(MAX_IMAGE + 1)
                    if len(uploaded) > MAX_IMAGE:
                        raise ApiError(413, "IMAGE_TOO_LARGE")
                original = gray_image(uploaded)
                with tempfile.TemporaryDirectory(prefix="blurfing_scanner_", dir=config.temp_root) as directory:
                    root = Path(directory)
                    source = root / "source.png"
                    original.save(source)
                    raw = await runner(config, source, root / "output", dpi, request)
                    try:
                        payload = validate_result(raw, original, dpi)
                    except Exception:
                        raise ApiError(502, "INVALID_SCANNER_RESULT") from None
                    return dict(schema_version="scanner-comparison-v1", request_id=request_id,
                        source_sha256=digest(uploaded), source_pixel_sha256=digest(original.tobytes()),
                        processing_ms=round((time.monotonic() - started) * 1000), **payload)
        except ApiError as error:
            return JSONResponse(dict(request_id=request_id, code=error.code, retryable=error.status in (429, 503, 504)), status_code=error.status)
        except Exception:
            return JSONResponse(dict(request_id=request_id, code="INVALID_SCANNER_DATA", retryable=False), status_code=422)
    return app


app = create_app()
