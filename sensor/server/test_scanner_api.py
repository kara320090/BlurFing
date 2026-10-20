"""Synthetic transport, lifecycle, resource and subprocess checks. No biometric data."""
import asyncio
import base64
import io
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from scanner_api import ApiError, Config, MAX_IMAGE, child_runner, create_app, digest, gray_image, validate_result


def png(color=40, mode="L", size=(12, 16)):
    output = io.BytesIO()
    Image.new(mode, size, color).save(output, format="PNG")
    return output.getvalue()


def result(source, dpi, change=True):
    image = gray_image(source.read_bytes())
    if change:
        image.putpixel((0, 0), 99)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    encoded = stream.getvalue()
    return dict(processed_image_base64=base64.b64encode(encoded).decode(), processed_sha256=digest(encoded),
        width=image.width, height=image.height, protection_status="success" if change else "rejected",
        protection_engine="blurfing-scanner-experimental", changed_pixels=int(change),
        match=dict(status="unavailable", score=None, engine="SourceAFIS", engine_version=None, dpi=dpi,
            probe_minutiae=None, candidate_minutiae=None, measured_at=None))


@pytest.fixture
def setup(tmp_path):
    scripts = tmp_path / "ai" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("protect_fingerprint.py", "sourceafis_matcher.py"):
        (scripts / name).write_text("# synthetic runtime fixture", encoding="utf-8")
    (scripts / "fingerprint_input_router.py").write_text("def route_input(rgb):return {'input_type':'FINGERPRINT_IMAGE'}", encoding="utf-8")
    temporary = tmp_path / "jobs"
    temporary.mkdir()
    config = Config(sys.executable, str(scripts.parent), temp_root=str(temporary))
    roots = []
    async def runner(config, source, output, dpi, request):
        roots.append(source.parent)
        return result(source, dpi)
    return config, roots, runner


def post(client, image=None, dpi="500", request_id="synthetic-request"):
    return client.post("/v1/scanner/compare", data={"request_id": request_id, "dpi": dpi},
        files={"image": ("scanner.png", png() if image is None else image, "image/png")})


def test_missing_runtime_is_explicit_and_does_not_expose_paths():
    with TestClient(create_app(Config())) as client:
        assert client.get("/ready").status_code == 503
        response = post(client)
        assert response.status_code == 503
        assert response.json()["code"] == "SCANNER_NOT_CONFIGURED"
        assert response.headers["cache-control"] == "no-store"


def test_ready_only_reports_configuration_not_inference(setup):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["inference_checked"] is False
        assert roots == []


def test_request_identity_pixels_and_cleanup_are_bound_to_this_result(setup):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        response = post(client)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source_sha256"] == digest(png())
        assert data["source_pixel_sha256"] == digest(bytes([40]) * 192)
        assert data["request_id"] == "synthetic-request"
        assert data["changed_pixels"] == 1
        assert data["match"]["score"] is None
        assert all(not folder.exists() for folder in roots)
        assert not list(Path(config.temp_root).iterdir())


@pytest.mark.parametrize("image", [b"invalid", png((50, 60, 70), "RGB"), png((0, 0, 0, 0), "RGBA")])
def test_invalid_color_or_transparent_inputs_never_reach_worker(setup, image):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        assert post(client, image).status_code == 422
        assert roots == []


@pytest.mark.parametrize("dpi", ["99", "2001", "NaN", "500.0"])
def test_invalid_dpi_is_not_silently_reinterpreted(setup, dpi):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        assert post(client, dpi=dpi).status_code == 422
        assert roots == []


def test_upload_envelope_and_file_limit(setup):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        assert post(client, b"x" * (MAX_IMAGE + 1)).status_code == 413
        assert post(client, b"x" * (MAX_IMAGE + 100_000)).status_code == 413
        assert roots == []


def test_duplicate_fields_and_path_like_request_ids_are_rejected(setup):
    config, roots, runner = setup
    with TestClient(create_app(config, runner)) as client:
        response = client.post("/v1/scanner/compare", files=[("image", ("a.png", png(), "image/png")),
            ("request_id", (None, "one")), ("request_id", (None, "two")), ("dpi", (None, "500"))])
        assert response.status_code == 422
        response = post(client, request_id="../private/person")
        assert response.status_code == 422
        assert response.json()["request_id"] == ""
        assert roots == []


@pytest.mark.parametrize("kind", ["hash", "changed", "rejected_changed", "invented_score", "no_features", "negative", "nan", "private_extra", "private_match_extra"])
def test_worker_image_or_score_mismatch_is_not_displayable(setup, kind):
    config, roots, _ = setup
    async def invalid(config, source, output, dpi, request):
        roots.append(source.parent)
        data = result(source, dpi)
        if kind == "hash": data["processed_sha256"] = "0" * 64
        if kind == "changed": data["changed_pixels"] = 2
        if kind == "rejected_changed": data["protection_status"] = "rejected"
        if kind == "invented_score": data["match"]["score"] = 99.9
        if kind == "private_extra": data["private_path"] = "PRIVATE_PATH_DO_NOT_TRANSMIT"
        if kind == "private_match_extra": data["match"]["template"] = "PRIVATE_TEMPLATE_DO_NOT_TRANSMIT"
        if kind in ("no_features", "negative", "nan"):
            data["match"].update(status="measured", score={"negative": -1, "nan": float("nan")}.get(kind, 12),
                engine_version="contract-fixture", measured_at="2026-10-20T00:00:00+00:00", probe_minutiae=0, candidate_minutiae=5)
        return data
    with TestClient(create_app(config, invalid)) as client:
        response = post(client)
        assert response.status_code == 502
        assert response.json()["code"] == "INVALID_SCANNER_RESULT"
        assert all(not folder.exists() for folder in roots)


def test_a_second_request_cannot_enter_a_busy_processor(setup):
    config, _, _ = setup
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()
        async def runner(config, source, output, dpi, request):
            entered.set()
            await release.wait()
            return result(source, dpi)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(config, runner)), base_url="http://test") as client:
            def args(id): return dict(data={"request_id": id, "dpi": "500"}, files={"image": ("a.png", png(), "image/png")})
            first = asyncio.create_task(client.post("/v1/scanner/compare", **args("one")))
            await asyncio.wait_for(entered.wait(), 5)
            second = await client.post("/v1/scanner/compare", **args("two"))
            assert second.status_code == 429
            release.set()
            assert (await first).status_code == 200
    asyncio.run(check())


def test_actual_child_adapter_with_controlled_synthetic_ai_and_matcher(setup):
    config, _, _ = setup
    scripts = Path(config.ai_root) / "scripts"
    (scripts / "protect_fingerprint.py").write_text('''from PIL import Image
import numpy as np
def protect_image(source, output):
    a=np.asarray(Image.open(source).convert("RGB")).copy();a[0,0,:]=99
    return a,dict(input_type="fingerprint_image",status="success")
''', encoding="utf-8")
    (scripts / "sourceafis_matcher.py").write_text('''def run_matcher_job(*args,**kwargs):
    return dict(sourceafis_version="synthetic-contract-fixture",pairs=[dict(status="ok",score=123.5,probe_minutiae=8,candidate_minutiae=7)])
''', encoding="utf-8")
    with TestClient(create_app(config)) as client:
        response = post(client)
        assert response.status_code == 200, response.text
        assert response.json()["match"]["score"] == 123.5  # Unbounded raw score, not 100%.
        assert response.json()["match"]["engine_version"] == "synthetic-contract-fixture"
        assert not list(Path(config.temp_root).iterdir())


def test_child_failure_has_no_internal_path_or_raw_stderr(setup):
    config, _, _ = setup
    (Path(config.ai_root) / "scripts/protect_fingerprint.py").write_text("raise RuntimeError('SECRET_PRIVATE_PATH')", encoding="utf-8")
    with TestClient(create_app(config)) as client:
        response = post(client)
        assert response.status_code == 503
        assert "SECRET_PRIVATE_PATH" not in response.text
        assert not list(Path(config.temp_root).iterdir())


def test_actual_child_timeout_stops_process_and_cleans_private_job(setup):
    config, _, _ = setup
    (Path(config.ai_root) / "scripts/protect_fingerprint.py").write_text("import time;time.sleep(30)", encoding="utf-8")
    timed = Config(config.python, config.ai_root, timeout=.2, temp_root=config.temp_root)
    with TestClient(create_app(timed)) as client:
        response = post(client)
        assert response.status_code == 504
        assert not list(Path(config.temp_root).iterdir())


def test_cancelled_http_job_releases_slot_and_removes_private_input(setup):
    config, roots, _ = setup
    async def check():
        entered = asyncio.Event()
        calls = 0
        async def runner(config, source, output, dpi, request):
            nonlocal calls
            calls += 1
            roots.append(source.parent)
            if calls == 1:
                entered.set()
                await asyncio.sleep(30)
            return result(source, dpi)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(config, runner)), base_url="http://test") as client:
            kwargs = dict(data={"request_id": "cancelled", "dpi": "500"}, files={"image": ("a.png", png(), "image/png")})
            work = asyncio.create_task(client.post("/v1/scanner/compare", **kwargs))
            await asyncio.wait_for(entered.wait(), 5)
            work.cancel()
            with pytest.raises(asyncio.CancelledError):
                await work
            assert all(not folder.exists() for folder in roots)
            assert (await client.post("/v1/scanner/compare", **kwargs)).status_code == 200
    asyncio.run(check())


def test_disconnected_request_stops_real_child(setup, tmp_path):
    config, _, _ = setup
    (Path(config.ai_root) / "scripts/protect_fingerprint.py").write_text("import time;time.sleep(30)", encoding="utf-8")
    source = tmp_path / "source.png"
    source.write_bytes(png())
    class Disconnected:
        async def is_disconnected(self): return True
    async def check():
        with pytest.raises(ApiError) as error:
            await child_runner(config, source, tmp_path / "output", 500, Disconnected())
        assert error.value.status == 499
    asyncio.run(check())


def test_photo_route_never_enters_a_protection_or_photo_fallback(setup):
    config, _, _ = setup
    scripts = Path(config.ai_root) / "scripts"
    marker = scripts / "protection_was_called.txt"
    (scripts / "fingerprint_input_router.py").write_text("def route_input(rgb):return {'input_type':'PHOTO'}", encoding="utf-8")
    (scripts / "protect_fingerprint.py").write_text("from pathlib import Path\nPath(__file__).with_name('protection_was_called.txt').write_text('called')", encoding="utf-8")
    with TestClient(create_app(config)) as client:
        response = post(client)
        assert response.status_code == 422
        assert response.json()["code"] == "SCANNER_INPUT_REQUIRED"
        assert not marker.exists()
