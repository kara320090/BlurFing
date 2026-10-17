"""Read-only preflight and explicit Linux AI timing; never starts an HTTP server.

The measurement uses the existing V2 child runtime and its strict image/result
validation. No mock, alternate engine, image conversion, or dependency install
is performed. Run only with an authorized development input and an idle GPU.
"""
import argparse
import asyncio
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import time
import uuid


BACKEND = Path(__file__).resolve().parent
ENGINES = ("native_v12", "distal_v13", "pose_v14")
V2_FILES = (
    "experimental_photo_main.py", "experimental_photo_transport_v2.py",
    "native_photo_result_contract_v1.py", "requirements-photo-v2.txt",
)
PACKAGES = ("fastapi", "starlette", "numpy", "pillow", "python-multipart", "uvicorn")
SAFE_SERVICE_CODES = {
    "PROCESSOR_UNAVAILABLE", "DUPLICATE_REQUEST_ID", "PROCESSOR_BUSY",
    "PROCESSOR_TIMEOUT", "PROCESSOR_FAILED", "INVALID_PROCESSOR_RESULT",
}


class MeasurementError(Exception):
    """Only a fixed, public code may be supplied, never a private exception."""


def emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False), flush=True)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def revision(backend):
    try:
        result = subprocess.run(
            ["git", "-C", str(backend), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        value = result.stdout.strip()
        return value if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def package_versions():
    result = {}
    for name in PACKAGES:
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def path_state(value, *, directory=False):
    if not value.strip():
        return "unset"
    try:
        path = Path(value.strip())
        if not path.exists():
            return "missing"
        return "present" if (path.is_dir() if directory else path.is_file()) else "wrong_type"
    except (OSError, ValueError):
        return "inaccessible"


def preflight(backend=BACKEND):
    """Inspect existence/metadata only; do not import the AI or read its registry."""
    settings = {
        name: path_state(os.environ.get(name, ""), directory=directory)
        for name, directory in (
            ("BLURFING_PHOTO_PYTHON", False), ("BLURFING_PHOTO_BRIDGE", False),
            ("BLURFING_PHOTO_CONSUMED_REGISTRY", False),
            ("BLURFING_PHOTO_MODEL", True), ("BLURFING_PHOTO_TEMP_ROOT", True),
        )
    }
    return {
        "kind": "preflight", "checked_at_utc": utc_now(),
        "system": platform.system(), "python": platform.python_version(),
        "architecture": platform.machine(), "cpu_count": os.cpu_count(),
        "repository_head": revision(backend),
        "v2_files": {name: (backend / name).is_file() for name in V2_FILES},
        "server_python_packages": package_versions(),
        "commands_available": {name: shutil.which(name) is not None for name in
                               ("docker", "nginx", "cloudflared", "nvidia-smi")},
        "configured_paths": settings,
        "ai_executed": False, "readiness_verified": False,
    }


def prepare_measurement(args):
    # Preflight works with the standard library even on an older checkout.
    # Defer V2/numpy/FastAPI imports until an explicit real measurement request.
    if platform.system() != "Linux":
        raise MeasurementError("LINUX_REQUIRED")
    try:
        from experimental_photo_main import PhotoRuntimeConfig, PhotoSubprocessRuntime
        from experimental_photo_transport_v2 import MAX_IMAGE_BYTES, UploadedPhoto
    except Exception:
        raise MeasurementError("V2_RUNTIME_IMPORT_FAILED") from None
    config = PhotoRuntimeConfig.from_environment()
    if config is None:
        raise MeasurementError("PHOTO_RUNTIME_NOT_CONFIGURED")
    if args.engine not in config.engines:
        raise MeasurementError("ENGINE_NOT_CONFIGURED")
    started = time.monotonic()
    try:
        if not args.image.is_file():
            raise MeasurementError("INPUT_NOT_READABLE")
        with args.image.open("rb") as stream:
            content = stream.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        raise MeasurementError("INPUT_NOT_READABLE") from None
    if len(content) > MAX_IMAGE_BYTES:
        raise MeasurementError("INPUT_TOO_LARGE")
    try:
        upload = UploadedPhoto.decode(content)
    except Exception:
        raise MeasurementError("INPUT_NOT_CANONICAL_PNG") from None
    input_ms = round((time.monotonic() - started) * 1000, 3)
    return PhotoSubprocessRuntime(config), upload, input_ms


async def measure_one(runtime, upload, engine, index):
    request_id = "timing-" + uuid.uuid4().hex
    started = time.monotonic()
    record = {"kind": "run", "index": index, "started_at_utc": utc_now()}
    claimed = False
    try:
        runtime.claim(request_id)
        claimed = True
        result = await runtime.run(upload, request_id, engine, started + runtime.config.timeout_seconds)
        # The runtime has already independently validated the full transport.
        # Do not copy images, hashes, paths, warnings or arbitrary result fields.
        status, bridge_ms = result["status"], result["processing_ms"]
        if (status not in ("success", "partial_success", "rejected") or
                type(bridge_ms) is not int or not 0 <= bridge_ms <= 2**63 - 1):
            raise MeasurementError("INVALID_PROCESSOR_RESULT")
        record.update(outcome="validated_transport", result_status=status,
                      bridge_processing_ms=bridge_ms)
    except Exception as exc:
        code = getattr(exc, "code", None)
        record.update(outcome="error", code=code if isinstance(code, str) and code in SAFE_SERVICE_CODES
                      else "MEASUREMENT_FAILED")
    finally:
        # CancelledError is deliberately not converted into a successful result.
        # runtime.run finishes child termination/cleanup before this release.
        if claimed:
            runtime.release(request_id)
    record["wall_ms"] = round((time.monotonic() - started) * 1000, 3)
    return record


async def collect_measurements(runtime, upload, *, engine, runs, concurrency, output=emit):
    if engine not in ENGINES or not 1 <= runs <= 10 or concurrency not in (1, 2):
        raise MeasurementError("INVALID_MEASUREMENT_OPTIONS")
    records = []

    async def run_and_report(index):
        record = await measure_one(runtime, upload, engine, index)
        output(record)
        return record

    for first in range(1, runs + 1, concurrency):
        batch = await asyncio.gather(*(run_and_report(index) for index in
                                     range(first, min(first + concurrency, runs + 1))))
        records.extend(batch)
        if any(record["outcome"] == "error" for record in batch):
            break  # Do not repeat expensive failures automatically.
    valid = [record for record in records if record["outcome"] == "validated_transport"]
    elapsed = [record["wall_ms"] for record in valid]
    summary = {
        "kind": "summary", "finished_at_utc": utc_now(),
        "requested_runs": runs, "attempted_runs": len(records),
        "validated_transport_count": len(valid), "error_count": len(records) - len(valid),
        "completed": len(valid) == runs,
        "wall_ms_min": min(elapsed) if elapsed else None,
        "wall_ms_median": statistics.median(elapsed) if elapsed else None,
        "wall_ms_max": max(elapsed) if elapsed else None,
        "result_status_counts": {status: sum(record["result_status"] == status for record in valid)
                                 for status in ("success", "partial_success", "rejected")},
        "http_measured": False, "protection_performance_verified": False,
    }
    output(summary)
    return summary


def run_count(value):
    try:
        result = int(value)
        if 1 <= result <= 10:
            return result
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("runs must be an integer from 1 to 10")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight", help="inspect only; never execute the AI")
    measurement = commands.add_parser("measure", help="explicitly execute the real Linux V2 child runtime")
    measurement.add_argument("--image", type=Path, required=True)
    measurement.add_argument("--input-kind", choices=("development-photo", "synthetic"), required=True)
    measurement.add_argument("--engine", choices=ENGINES, required=True)
    measurement.add_argument("--runs", type=run_count, default=1)
    measurement.add_argument("--concurrency", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            emit(preflight())
            return 0
        runtime, upload, input_ms = prepare_measurement(args)
        height, width = upload.rgb.shape[:2]
        emit({
            "kind": "measurement", "started_at_utc": utc_now(),
            "system": platform.system(), "repository_head": revision(BACKEND),
            "python": platform.python_version(), "server_python_packages": package_versions(),
            "engine": args.engine, "input_kind": args.input_kind,
            "input_width": width, "input_height": height, "input_bytes": len(upload.content),
            "input_read_validate_ms": input_ms, "runs": args.runs, "concurrency": args.concurrency,
            "timeout_seconds": runtime.config.timeout_seconds,
            "development_replay": runtime.config.development_replay,
            "process_lifecycle": "fresh_child_each_request",
            "wall_scope": "queue_child_startup_processing_result_validation_cleanup",
            "http_measured": False, "protection_performance_verified": False,
        })
        result = asyncio.run(collect_measurements(
            runtime, upload, engine=args.engine, runs=args.runs, concurrency=args.concurrency))
        return 0 if result["completed"] else 1
    except KeyboardInterrupt:
        emit({"kind": "error", "code": "INTERRUPTED", "completed": False})
        return 130
    except MeasurementError as exc:
        emit({"kind": "error", "code": str(exc), "completed": False})
        return 2
    except Exception:
        # Never print private configuration values or exception/traceback text.
        emit({"kind": "error", "code": "MEASUREMENT_FAILED", "completed": False})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
