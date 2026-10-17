"""Synthetic orchestration tests; these do not measure or validate real AI."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import measure_photo_ai as timing


class ServiceError(Exception):
    def __init__(self, code):
        super().__init__("private path or image details must not escape")
        self.code = code


class FakeRuntime:
    def __init__(self, error=None):
        self.config = SimpleNamespace(timeout_seconds=2, development_replay=False)
        self.error = error
        self.active = set()
        self.claimed = []
        self.released = []
        self.maximum_active = 0
        self.deadlines = []

    def claim(self, request_id):
        self.claimed.append(request_id)
        self.active.add(request_id)
        self.maximum_active = max(self.maximum_active, len(self.active))

    def release(self, request_id):
        self.active.remove(request_id)
        self.released.append(request_id)

    async def run(self, upload, request_id, engine, deadline):
        self.deadlines.append(deadline)
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return {"status": "rejected", "processing_ms": 12, "image_base64": "PRIVATE_IMAGE",
                "source_sha256": "PRIVATE_HASH", "private_path": "PRIVATE_PATH"}


def test_preflight_works_without_importing_ai_or_exposing_configured_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("BLURFING_PHOTO_PYTHON", str(Path(__file__)))
    monkeypatch.setenv("BLURFING_PHOTO_BRIDGE", str(tmp_path / "PRIVATE_MISSING_FILE"))
    monkeypatch.setenv("BLURFING_PHOTO_CONSUMED_REGISTRY", "")
    monkeypatch.setenv("BLURFING_PHOTO_MODEL", str(tmp_path))
    monkeypatch.setenv("BLURFING_PHOTO_TEMP_ROOT", str(Path(__file__)))
    monkeypatch.setattr(timing, "revision", lambda _: None)
    monkeypatch.setattr(timing, "package_versions", lambda: {})
    monkeypatch.setattr(timing.shutil, "which", lambda _: None)
    report = timing.preflight(tmp_path)
    assert report["configured_paths"] == {
        "BLURFING_PHOTO_PYTHON": "present", "BLURFING_PHOTO_BRIDGE": "missing",
        "BLURFING_PHOTO_CONSUMED_REGISTRY": "unset", "BLURFING_PHOTO_MODEL": "present",
        "BLURFING_PHOTO_TEMP_ROOT": "wrong_type",
    }
    assert not any(report["v2_files"].values())
    assert report["ai_executed"] is False
    assert report["readiness_verified"] is False
    assert "PRIVATE_MISSING_FILE" not in json.dumps(report)
    assert str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize("value", ["0", "11", "-1", "1.5", "secret"])
def test_run_count_is_bounded(value):
    with pytest.raises(timing.argparse.ArgumentTypeError):
        timing.run_count(value)


@pytest.mark.parametrize("concurrency, maximum", [(1, 1), (2, 2)])
def test_measurement_reuses_runtime_limits_and_reports_only_safe_fields(concurrency, maximum):
    runtime = FakeRuntime()
    output = []
    report = asyncio.run(timing.collect_measurements(
        runtime, object(), engine="native_v12", runs=3, concurrency=concurrency, output=output.append))
    assert runtime.maximum_active == maximum
    assert len(set(runtime.claimed)) == 3
    assert set(runtime.claimed) == set(runtime.released)
    assert not runtime.active
    assert all(deadline > 0 for deadline in runtime.deadlines)
    assert report["completed"] is True
    assert report["validated_transport_count"] == 3
    assert report["result_status_counts"]["rejected"] == 3
    assert report["http_measured"] is False
    assert report["protection_performance_verified"] is False
    assert len(output) == 4
    assert "PRIVATE_" not in json.dumps(output)
    assert all(record["bridge_processing_ms"] == 12 for record in output[:-1])


@pytest.mark.parametrize("code, expected", [
    ("PROCESSOR_TIMEOUT", "PROCESSOR_TIMEOUT"),
    ("PROCESSOR_UNAVAILABLE", "PROCESSOR_UNAVAILABLE"),
    ("PRIVATE_EXCEPTION", "MEASUREMENT_FAILED"),
])
def test_failure_stops_later_batches_and_releases_request(code, expected):
    runtime = FakeRuntime(ServiceError(code))
    output = []
    report = asyncio.run(timing.collect_measurements(
        runtime, object(), engine="native_v12", runs=3, concurrency=1, output=output.append))
    assert report["completed"] is False
    assert report["attempted_runs"] == 1
    assert report["wall_ms_median"] is None
    assert output[0]["code"] == expected
    assert runtime.released == runtime.claimed
    assert "private path" not in json.dumps(output)
    assert "PRIVATE_EXCEPTION" not in json.dumps(output)


def test_failed_claim_is_not_released():
    runtime = FakeRuntime()

    def reject(_):
        raise ServiceError("PROCESSOR_BUSY")

    runtime.claim = reject
    record = asyncio.run(timing.measure_one(runtime, object(), "native_v12", 1))
    assert record["code"] == "PROCESSOR_BUSY"
    assert runtime.released == []


def test_cancellation_waits_for_runtime_cleanup_before_releasing_id():
    events = []
    runtime = FakeRuntime()

    async def scenario():
        started = asyncio.Event()

        async def run(*_):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                events.append("cleanup")

        original_release = runtime.release

        def release(request_id):
            events.append("release")
            original_release(request_id)

        runtime.run, runtime.release = run, release
        job = asyncio.create_task(timing.measure_one(runtime, object(), "native_v12", 1))
        await started.wait()
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job

    asyncio.run(scenario())
    assert events == ["cleanup", "release"]
    assert not runtime.active


def test_non_linux_measurement_is_rejected_before_loading_model(monkeypatch, capsys):
    monkeypatch.setattr(timing.platform, "system", lambda: "Windows")
    code = timing.main(["measure", "--image", "PRIVATE.png", "--engine", "native_v12",
                        "--input-kind", "development-photo"])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["code"] == "LINUX_REQUIRED"


def test_entrypoint_does_not_expose_unexpected_exception(monkeypatch, capsys):
    def fail(_):
        raise RuntimeError("PRIVATE_PATH PRIVATE_MODEL")

    monkeypatch.setattr(timing, "prepare_measurement", fail)
    assert timing.main(["measure", "--image", "PRIVATE.png", "--engine", "native_v12",
                        "--input-kind", "synthetic"]) == 2
    output = capsys.readouterr().out
    assert "PRIVATE" not in output
    assert json.loads(output)["code"] == "MEASUREMENT_FAILED"


@pytest.fixture
def fake_v2(monkeypatch):
    """Exercise preparation boundaries without a model or the latest V2 checkout."""
    config = SimpleNamespace(engines=("native_v12",))
    decoded = []

    def decode(content):
        decoded.append(content)
        if content != b"valid":
            raise ValueError("PRIVATE decoder failure")
        return SimpleNamespace(content=content)

    api = SimpleNamespace(
        PhotoRuntimeConfig=SimpleNamespace(from_environment=lambda: config),
        PhotoSubprocessRuntime=lambda value: SimpleNamespace(config=value),
    )
    transport = SimpleNamespace(MAX_IMAGE_BYTES=8, UploadedPhoto=SimpleNamespace(decode=decode))
    monkeypatch.setitem(sys.modules, "experimental_photo_main", api)
    monkeypatch.setitem(sys.modules, "experimental_photo_transport_v2", transport)
    monkeypatch.setattr(timing.platform, "system", lambda: "Linux")
    return api, config, decoded


def test_preparation_delegates_input_validation_and_preserves_config(fake_v2, tmp_path):
    _, config, decoded = fake_v2
    path = tmp_path / "synthetic.bin"
    path.write_bytes(b"valid")
    runtime, upload, elapsed = timing.prepare_measurement(SimpleNamespace(image=path, engine="native_v12"))
    assert decoded == [b"valid"]
    assert upload.content == b"valid"
    assert runtime.config is config
    assert elapsed >= 0


@pytest.mark.parametrize("content, expected, decode_called", [
    (b"x" * 9, "INPUT_TOO_LARGE", False),
    (b"bad", "INPUT_NOT_CANONICAL_PNG", True),
    (b"", "INPUT_NOT_CANONICAL_PNG", True),
])
def test_bad_input_never_reaches_ai(fake_v2, tmp_path, content, expected, decode_called):
    api, _, decoded = fake_v2
    api.PhotoSubprocessRuntime = lambda _: pytest.fail("No AI runtime may be created for bad input")
    path = tmp_path / "synthetic.bin"
    path.write_bytes(content)
    with pytest.raises(timing.MeasurementError, match=expected):
        timing.prepare_measurement(SimpleNamespace(image=path, engine="native_v12"))
    assert bool(decoded) is decode_called


@pytest.mark.parametrize("case, expected", [
    ("missing_config", "PHOTO_RUNTIME_NOT_CONFIGURED"),
    ("other_engine", "ENGINE_NOT_CONFIGURED"),
    ("missing_input", "INPUT_NOT_READABLE"),
])
def test_preparation_fails_closed_without_fallback(fake_v2, tmp_path, case, expected):
    api, _, decoded = fake_v2
    if case == "missing_config":
        api.PhotoRuntimeConfig.from_environment = lambda: None
    args = SimpleNamespace(image=tmp_path / "PRIVATE_MISSING.png",
                           engine="pose_v14" if case == "other_engine" else "native_v12")
    with pytest.raises(timing.MeasurementError, match=expected):
        timing.prepare_measurement(args)
    assert not decoded
