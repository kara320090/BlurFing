"""Synthetic transport/process/HTTP tests. No AI inference or privacy scores."""
import base64
import asyncio
import copy
import hashlib
import io
import inspect
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time
import zlib
from concurrent.futures import ThreadPoolExecutor

import httpx
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
import starlette.formparsers

from experimental_photo_main import PhotoRuntimeConfig, create_app, positive_timeout
from experimental_photo_transport_v2 import (
    ENGINE_METHODS, MAX_IMAGE_BYTES, RESPONSE_KEYS, TransportValidationError,
    UploadedPhoto, array_digest, digest, validate_transport, warnings_for,
)


def png(array, orientation=1):
    stream = io.BytesIO()
    exif = Image.Exif()
    exif[274] = orientation
    Image.fromarray(array).save(stream, format="PNG", exif=exif)
    return stream.getvalue()


def encoded_mask(mask):
    content = png(mask.astype(np.uint8) * 255)
    return {"encoding": "png_uint8_0_255", "image_base64": base64.b64encode(content).decode("ascii"),
            "png_sha256": digest(content), "boolean_pixel_sha256": array_digest(mask), "pixels": int(mask.sum())}


def synthetic_payload(content, request_id, engine="native_v12", *, all_rejected=False):
    """Declared fake component evidence, solely for strict HTTP transport tests."""
    source = UploadedPhoto.decode(content)
    height, width = source.rgb.shape[:2]
    returned = source.rgb.copy()
    accepted = np.zeros((height, width), bool)
    refused = np.zeros_like(accepted)
    accepted[0, 0] = not all_rejected
    refused[-1, -1] = True
    if all_rejected:
        refused[0, 0] = True
    else:
        returned[0, 0, 0] ^= np.uint8(1)
    rows = []
    for region_id, y, x, transformed in ((1, 0, 0, not all_rejected), (2, height - 1, width - 1, False)):
        mask = np.zeros_like(accepted)
        mask[y, x] = True
        rows.append({"region_id": region_id, "status": "transformed" if transformed else "rejected",
                     "reason_code": "TRANSFORMED" if transformed else "REJECT_PITCH_UNOBSERVED",
                     "mask_pixels": 1, "changed_RGB_pixels": int(transformed),
                     "permission_boolean_sha256": array_digest(mask), "x": x / width, "y": y / height,
                     "width": 1 / width, "height": 1 / height, "bounds_are_not_filled_permission": True})
    return {"contract_version": "photo-experimental-v2", "request_id": request_id, "result_kind": "experimental",
            "method": ENGINE_METHODS[engine], "photo_engine": engine,
            "status": "rejected" if all_rejected else "partial_success",
            "image_base64": base64.b64encode(png(returned)).decode("ascii"), "mime_type": "image/png",
            "image_width": width, "image_height": height, "source_exif_orientation": 1,
            "coordinate_system": "encoded_original_pixels", "source_sha256": source.source_sha256,
            "source_RGB_sha256": source.rgb_sha256, "returned_RGB_sha256": array_digest(returned),
            "candidate_components": 2, "transformed_components": 0 if all_rejected else 1,
            "rejected_components": 2 if all_rejected else 1, "changed_RGB_pixels": 0 if all_rejected else 1,
            "accepted_permission_mask": encoded_mask(accepted), "rejected_permission_mask": encoded_mask(refused),
            "region_display_bounds": rows, "bounds_are_not_filled_permission": True, "processing_ms": 7,
            "warnings": warnings_for(engine, 2 if all_rejected else 1), "privacy_validated": False,
            "production_approved": False, "complete_photo_protection_verified": False,
            "independent_final_test": False, "evaluation": None}


@pytest.fixture
def content():
    return png(np.full((12, 16, 3), 120, np.uint8))


@pytest.fixture
def configured(tmp_path):
    backend_dir = Path(__file__).resolve().parent
    bridge = tmp_path / "synthetic_bridge.py"
    # All output artifacts remain under the fixture's private directory.
    bridge.write_text("""import argparse,json,pathlib,sys,time,os
sys.path.insert(0, BACKEND_DIR)
p=argparse.ArgumentParser()
for key in ('input','output','photo-engine','consumed-registry','request-id','photo-model'):p.add_argument('--'+key)
p.add_argument('--development-replay',action='store_true')
a=p.parse_args();root=pathlib.Path(__file__).parent
with (root/'started.jsonl').open('a') as f:f.write(json.dumps({'id':a.request_id,'pid':os.getpid(),'output':a.output})+'\\n')
mode=(root/'mode').read_text() if (root/'mode').exists() else 'valid'
if mode=='sleep':time.sleep(20)
if mode=='fail':print('PRIVATE PATH SHOULD NEVER APPEAR',file=sys.stderr);sys.exit(3)
import base64,io,numpy as np
from PIL import Image
from experimental_photo_transport_v2 import UploadedPhoto,ENGINE_METHODS,array_digest,digest,warnings_for
SYNTHETIC_HELPERS
out=pathlib.Path(a.output);out.mkdir()
if mode=='missing':sys.exit(0)
if mode=='oversize':(out/'result.transport.json').write_bytes(b' '* (64*1024*1024+1));sys.exit(0)
data=synthetic_payload(pathlib.Path(a.input).read_bytes(),a.request_id,a.photo_engine,all_rejected=mode=='rejected')
if mode=='wrong_id':data['request_id']='stale-other-id'
if mode=='private_extra':data['private_path']='SECRET_INPUT_PATH'
if mode=='wrong_source':data['source_sha256']='0'*64
if mode=='bad_json':(out/'result.transport.json').write_text('{invalid');sys.exit(0)
(out/'result.transport.json').write_text(json.dumps(data))
""".replace("BACKEND_DIR", repr(str(backend_dir))).replace("SYNTHETIC_HELPERS", "\n".join(
        inspect.getsource(helper) for helper in (png, encoded_mask, synthetic_payload))), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    model = tmp_path / "synthetic-model-directory"
    model.mkdir()
    (model / "final_config.private.json").write_text("{}")
    (model / "final_context_whole_pad.pt").write_bytes(b"never-loaded")
    temp_root = tmp_path / "private-temporary"
    temp_root.mkdir()
    config = PhotoRuntimeConfig(Path(sys.executable), bridge, registry, model,
                                engines=tuple(ENGINE_METHODS), timeout_seconds=15, temp_root=temp_root)
    return config, tmp_path


def request(client, content, request_id="synthetic-request", *, engine="native_v12", data=None, files=None):
    options = {"request_id": request_id, "method": ENGINE_METHODS[engine], "scope": "automatic_photo", "strength": "0.5"}
    if data is not None:
        options.update(data)
    return client.post("/v2/photo/protect", data=options,
                       files=files or {"image": ("synthetic.png", content, "image/png")})


def wait_started(root, expected=1):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        path = root / "started.jsonl"
        if path.exists():
            lines = path.read_text().splitlines()
            if len(lines) >= expected:
                return [json.loads(line) for line in lines]
        time.sleep(0.03)
    raise AssertionError("Synthetic child did not start.")


@pytest.mark.parametrize("value", [True, False, 0, -1, float("nan"), float("inf"), "600", None, 3601])
def test_timeout_rejects_bool_nonfinite_and_invalid_bounds(value):
    with pytest.raises(ValueError):
        positive_timeout(value)


def test_runtime_config_explicit_paths_and_typed_engine_settings(configured):
    config, _ = configured
    assert config.timeout_seconds == 15
    with pytest.raises(ValueError):
        PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, engines=("native_v12",))
    with pytest.raises(ValueError):
        PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, config.model, development_replay=1)
    with pytest.raises(ValueError):
        PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, config.model, engines=("native_v12", "native_v12"))


@pytest.mark.parametrize("missing", ["final_config.private.json", "final_context_whole_pad.pt"])
def test_native_model_directory_requires_both_actual_runtime_files(configured, missing):
    config, root = configured
    invalid = root / "incomplete-model"
    invalid.mkdir()
    for name in ("final_config.private.json", "final_context_whole_pad.pt"):
        if name != missing:
            (invalid / name).write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="model directory"):
        PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, invalid)


def test_unconfigured_is_unavailable_and_never_echoes_image(content):
    with TestClient(create_app()) as client:
        assert client.get("/ready").status_code == 503
        response = request(client, content)
        assert response.status_code == 503
        assert "image_base64" not in response.json()
        assert client.post("/v1/protect").status_code == 404


@pytest.mark.parametrize("engine", list(ENGINE_METHODS))
def test_actual_subprocess_returns_validated_partial_and_exact_schema(configured, content, engine):
    config, root = configured
    with TestClient(create_app(config)) as client:
        assert client.get("/ready").json()["production_approved"] is False
        response = request(client, content, engine=engine)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == RESPONSE_KEYS
    assert payload["status"] == "partial_success"
    assert payload["changed_RGB_pixels"] == 1
    assert payload["processing_ms"] >= 7
    assert payload["photo_engine"] == engine
    assert payload["accepted_permission_mask"]["pixels"] == 1
    assert payload["rejected_permission_mask"]["pixels"] == 1
    assert not list(config.temp_root.iterdir())
    assert "PRIVATE" not in response.text and "applied_regions" not in payload
    assert len(wait_started(root)) == 1


def test_rejected_result_is_explicit_original_and_empty_accepted_mask(configured, content):
    config, root = configured
    (root / "mode").write_text("rejected")
    with TestClient(create_app(config)) as client:
        response = request(client, content)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["transformed_components"] == 0
    assert payload["accepted_permission_mask"]["pixels"] == 0
    np.testing.assert_array_equal(UploadedPhoto.decode(base64.b64decode(payload["image_base64"])).rgb,
                                  UploadedPhoto.decode(content).rgb)


@pytest.mark.parametrize("data", [
    {"scope": "manual_regions"}, {"strength": "0.6"}, {"strength": "NaN"}, {"strength": "true"},
    {"method": "gaussian_blur"}, {"request_id": ""}, {"request_id": "../unsafe"}, {"regions": "[]"},
    {"photo_engine": "native_v12"},
])
def test_unsupported_or_extra_options_do_not_run_any_processor(configured, content, data):
    config, root = configured
    with TestClient(create_app(config)) as client:
        response = request(client, content, data=data)
    assert 400 <= response.status_code < 500
    assert not (root / "started.jsonl").exists()
    assert "image_base64" not in response.json()


def test_repeated_multipart_field_is_rejected(configured, content):
    config, root = configured
    fields = [("image", ("synthetic.png", content, "image/png"))] + [
        (name, (None, value)) for name, value in (
            ("request_id", "repeated"), ("method", ENGINE_METHODS["native_v12"]),
            ("scope", "automatic_photo"), ("strength", "0.5"), ("strength", "0.5"))]
    with TestClient(create_app(config)) as client:
        response = client.post("/v2/photo/protect", files=fields)
    assert response.status_code == 400
    assert not (root / "started.jsonl").exists()


@pytest.mark.parametrize("mode,orientation", [("RGBA", 1), ("L", 1), ("RGB", 6)])
def test_noncanonical_png_is_rejected_before_execution(configured, mode, orientation):
    config, root = configured
    dimensions = (12, 16, 4) if mode == "RGBA" else (12, 16) if mode == "L" else (12, 16, 3)
    content = png(np.zeros(dimensions, np.uint8), orientation)
    with TestClient(create_app(config)) as client:
        response = request(client, content)
    assert response.status_code == 415
    assert not (root / "started.jsonl").exists()


@pytest.mark.parametrize("mutation", ["tRNS", "CRC", "trailing"])
def test_transparency_crc_or_trailing_PNG_reject_before_child(configured, content, mutation):
    config, root = configured
    if mutation == "tRNS":
        stream = io.BytesIO()
        Image.new("RGB", (16, 12), (120, 120, 120)).save(stream, format="PNG", transparency=(120, 120, 120))
        content = stream.getvalue()
    elif mutation == "CRC":
        corrupt = bytearray(content)
        corrupt[29] ^= 1
        content = bytes(corrupt)
    else:
        content += b"private-trailing-data"
    with TestClient(create_app(config)) as client:
        assert request(client, content).status_code == 415
    assert not (root / "started.jsonl").exists()


@pytest.mark.parametrize("depth,color,interlace", [(16, 2, 0), (8, 2, 1), (8, 6, 0)])
def test_IHDR_rejects_16bit_RGB_interlace_and_alpha_before_decode(configured, content, depth, color, interlace):
    config, root = configured
    header = bytearray(content)
    header[24], header[25], header[28] = depth, color, interlace
    header[29:33] = struct.pack(">I", zlib.crc32(header[12:29]) & 0xffffffff)
    with TestClient(create_app(config)) as client:
        assert request(client, bytes(header)).status_code == 415
    assert not (root / "started.jsonl").exists()


def test_APNG_chunk_is_rejected_before_child(configured, content):
    config, root = configured
    chunk = b"acTL" + struct.pack(">II", 1, 0)
    animated = content[:33] + struct.pack(">I", 8) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xffffffff) + content[33:]
    with TestClient(create_app(config)) as client:
        assert request(client, animated).status_code == 415
    assert not (root / "started.jsonl").exists()


def mutate_png_chunks(content, mutation):
    chunks = []
    position = 8
    while position < len(content):
        length = struct.unpack(">I", content[position:position + 4])[0]
        chunks.append((content[position + 4:position + 8], content[position + 8:position + length + 8]))
        position += length + 12
    index = next(index for index, (kind, _data) in enumerate(chunks) if kind == b"IDAT")
    if mutation == "duplicate_late_EXIF":
        with Image.open(io.BytesIO(content)) as image:
            orientation6 = png(np.asarray(image), 6)
        cursor = 8
        while orientation6[cursor + 4:cursor + 8] != b"eXIf":
            cursor += struct.unpack(">I", orientation6[cursor:cursor + 4])[0] + 12
        length = struct.unpack(">I", orientation6[cursor:cursor + 4])[0]
        chunks.insert(-1, (b"eXIf", orientation6[cursor + 8:cursor + 8 + length]))
    elif mutation == "unknown_critical":
        chunks.insert(index, (b"ABCD", b""))
    elif mutation == "PLTE":
        chunks.insert(index, (b"PLTE", b"\x00\x00\x00"))
    elif mutation == "nonconsecutive_IDAT":
        chunks.insert(index + 1, (b"tEXt", b"keyword\x00synthetic"))
        chunks.insert(index + 2, (b"IDAT", b""))
    elif mutation == "zlib_EOS_trailing":
        chunks[index] = (b"IDAT", chunks[index][1] + b"trailing-compressed-stream-junk")
    else:
        raise AssertionError(mutation)
    result = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, data in chunks:
        result += struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return bytes(result)


@pytest.mark.parametrize("mutation", ["duplicate_late_EXIF", "unknown_critical", "nonconsecutive_IDAT", "zlib_EOS_trailing", "PLTE"])
def test_ambiguous_or_noncanonical_chunks_fail_for_request_and_result(configured, content, mutation):
    config, root = configured
    with TestClient(create_app(config)) as client:
        assert request(client, mutate_png_chunks(content, mutation)).status_code == 415
    assert not (root / "started.jsonl").exists()
    payload = synthetic_payload(content, "invalid-PNG-result")
    returned = base64.b64decode(payload["image_base64"])
    payload["image_base64"] = base64.b64encode(mutate_png_chunks(returned, mutation)).decode("ascii")
    with pytest.raises(TransportValidationError):
        validate_transport(payload, UploadedPhoto.decode(content), request_id="invalid-PNG-result", engine="native_v12")


def ancillary_png(content, kind, data):
    """Synthetic chunk with correct CRC, inserted before IDAT, never a real photo."""
    at = 8
    while content[at + 4:at + 8] != b"IDAT":
        at += struct.unpack(">I", content[at:at + 4])[0] + 12
    chunk = struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return content[:at] + chunk + content[at:]


COLOR_AND_METADATA_CHUNKS = [
    (b"iCCP", b"synthetic-profile\x00\x00" + zlib.compress(b"synthetic, not an ICC profile")),
    (b"sRGB", b"\x00"),
    (b"gAMA", struct.pack(">I", 45455)),
    (b"cHRM", struct.pack(">8I", 31270, 32900, 64000, 33000, 30000, 60000, 15000, 6000)),
    (b"sBIT", b"\x08\x08\x08"),
    (b"pHYs", struct.pack(">IIB", 1000, 1000, 1)),
    (b"tEXt", b"synthetic\x00metadata"),
]


@pytest.mark.parametrize("kind,data", COLOR_AND_METADATA_CHUNKS)
def test_HTTP_rejects_color_or_metadata_chunks_before_any_AI_child(configured, content, kind, data):
    config, root = configured
    with TestClient(create_app(config)) as client:
        response = request(client, ancillary_png(content, kind, data), "canonical-color-boundary")
    assert response.status_code == 415, response.text
    assert response.json()["request_id"] == "canonical-color-boundary"
    assert "image_base64" not in response.json()
    assert not (root / "started.jsonl").exists()


@pytest.mark.parametrize("kind,data", COLOR_AND_METADATA_CHUNKS)
@pytest.mark.parametrize("target", ["image_base64", "accepted_permission_mask", "rejected_permission_mask"])
def test_returned_RGB_and_each_binary_mask_reject_color_or_metadata_without_stripping(content, kind, data, target):
    payload = synthetic_payload(content, "canonical-result-color")
    original = payload[target] if target == "image_base64" else payload[target]["image_base64"]
    modified = ancillary_png(base64.b64decode(original), kind, data)
    if target == "image_base64":
        payload[target] = base64.b64encode(modified).decode("ascii")
    else:
        payload[target]["image_base64"] = base64.b64encode(modified).decode("ascii")
        payload[target]["png_sha256"] = digest(modified)
    with pytest.raises(TransportValidationError):
        validate_transport(payload, UploadedPhoto.decode(content), request_id="canonical-result-color", engine="native_v12")


@pytest.mark.parametrize("extra", ["additional_tag", "nonzero_next_IFD", "trailing_EXIF_bytes"])
def test_HTTP_rejects_nonminimal_EXIF_even_if_orientation_is_one(configured, content, extra):
    config, root = configured
    if extra == "additional_tag":
        stream = io.BytesIO()
        exif = Image.Exif()
        exif[274] = 1
        exif[271] = "Synthetic camera metadata"
        Image.fromarray(UploadedPhoto.decode(content).rgb).save(stream, format="PNG", exif=exif)
        invalid = stream.getvalue()
    else:
        position = 8
        chunks = []
        while position < len(content):
            size = struct.unpack(">I", content[position:position + 4])[0]
            kind = content[position + 4:position + 8]
            data = content[position + 8:position + size + 8]
            if kind == b"eXIf":
                if extra == "nonzero_next_IFD":
                    order = "little" if data[:2] == b"II" else "big"
                    data = data[:-4] + (1).to_bytes(4, order)
                else:
                    data += b"synthetic-metadata-tail"
            chunks.append((kind, data))
            position += size + 12
        invalid = b"\x89PNG\r\n\x1a\n" + b"".join(
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
            for kind, data in chunks)
    with TestClient(create_app(config)) as client:
        assert request(client, invalid).status_code == 415
    assert not (root / "started.jsonl").exists()


def test_oversize_upload_and_large_IHDR_reject_before_allocation(configured, content):
    config, root = configured
    header = bytearray(content)
    header[16:24] = struct.pack(">II", 5000, 5000)
    with TestClient(create_app(config)) as client:
        response = request(client, bytes(header))
        assert response.status_code == 413
        response = request(client, b"x" * (MAX_IMAGE_BYTES + 1))
        assert response.status_code == 413
    assert not (root / "started.jsonl").exists()


@pytest.mark.parametrize("declared", [None, b"1"])
def test_actual_receive_bound_for_chunked_or_false_length_closes_parser_spool(configured, monkeypatch, declared):
    config, root = configured
    spools = []
    original = starlette.formparsers.SpooledTemporaryFile

    def record_spool(*args, **kwargs):
        spool = original(*args, **kwargs)
        spools.append(spool)
        return spool

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", record_spool)
    headers = [(b"content-type", b"multipart/form-data; boundary=bound")]
    if declared is not None:
        headers.append((b"content-length", declared))
    chunks = [b'--bound\r\nContent-Disposition: form-data; name="image"; filename="synthetic.png"\r\nContent-Type: image/png\r\n\r\n']
    chunks.extend([b"x" * (1024 * 1024)] * 17)
    received = []
    sent = []

    async def receive():
        chunk = chunks.pop(0)
        received.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
             "path": "/v2/photo/protect", "raw_path": b"/v2/photo/protect", "query_string": b"",
             "root_path": "", "headers": headers, "client": ("127.0.0.1", 12345), "server": ("127.0.0.1", 80)}
    asyncio.run(create_app(config)(scope, receive, send))
    assert next(item["status"] for item in sent if item["type"] == "http.response.start") == 413
    assert chunks, "Receive bound must stop reading the untrusted stream."
    assert sum(received) < 17 * 1024 * 1024
    assert spools and all(spool.closed for spool in spools)
    assert not (root / "started.jsonl").exists()


def test_socket_disconnect_terminates_running_child_and_cleans_private_temp(configured, content):
    config, root = configured
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment.update(BLURFING_PHOTO_PYTHON=str(config.python), BLURFING_PHOTO_BRIDGE=str(config.bridge),
                       BLURFING_PHOTO_CONSUMED_REGISTRY=str(config.consumed_registry),
                       BLURFING_PHOTO_MODEL=str(config.model), BLURFING_PHOTO_TEMP_ROOT=str(config.temp_root),
                       BLURFING_PHOTO_ENGINES="native_v12", BLURFING_PHOTO_TIMEOUT_SECONDS="15")
    (root / "mode").write_text("sleep")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "experimental_photo_main:app", "--host", "127.0.0.1",
                                "--port", str(port), "--log-level", "error"], cwd=Path(__file__).resolve().parent,
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 10
        with httpx.Client(base_url=f"http://127.0.0.1:{port}") as client:
            while time.monotonic() < deadline:
                try:
                    if client.get("/ready").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            build = client.build_request("POST", "/v2/photo/protect", data={
                "request_id": "disconnect", "method": ENGINE_METHODS["native_v12"],
                "scope": "automatic_photo", "strength": "0.5"}, files={"image": ("synthetic.png", content, "image/png")})
            body = build.read()
            headers = "\r\n".join(f"{key}: {value}" for key, value in build.headers.items())
            connection = socket.create_connection(("127.0.0.1", port), timeout=5)
            connection.sendall(f"POST /v2/photo/protect HTTP/1.1\r\n{headers}\r\n\r\n".encode() + body)
            call = wait_started(root)[0]
            connection.close()
            deadline = time.monotonic() + 5
            while list(config.temp_root.iterdir()) and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not Path(call["output"]).parent.exists()
            assert not list(config.temp_root.iterdir())
            (root / "mode").write_text("valid")
            assert request(client, content, "disconnect").status_code == 200
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.parametrize("mode", ["fail", "missing", "wrong_id", "private_extra", "wrong_source", "bad_json", "oversize"])
def test_failed_or_stale_child_never_returns_success_and_same_id_can_retry_fresh(configured, content, mode):
    config, root = configured
    (root / "mode").write_text(mode)
    with TestClient(create_app(config)) as client:
        failed = request(client, content)
        assert failed.status_code == 500
        assert set(failed.json()) == {"request_id", "code", "message", "retryable"}
        assert "PRIVATE" not in failed.text and "SECRET" not in failed.text
        (root / "mode").write_text("valid")
        success = request(client, content)
        assert success.status_code == 200, success.text
    calls = wait_started(root, 2)
    assert calls[0]["output"] != calls[1]["output"]
    assert not list(config.temp_root.iterdir())


def test_timeout_kills_child_cleans_outputs_and_releases_request_id(configured, content):
    config, root = configured
    config = PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, config.model,
                                timeout_seconds=5, temp_root=config.temp_root)
    (root / "mode").write_text("sleep")
    with TestClient(create_app(config)) as client:
        response = request(client, content)
        assert response.status_code == 504, response.text
        started = wait_started(root)
        assert not Path(started[0]["output"]).parent.exists()
        (root / "mode").write_text("valid")
        assert request(client, content).status_code == 200
    assert not list(config.temp_root.iterdir())


def test_running_plus_one_waiter_duplicate_and_overload_then_no_stale_success(configured, content):
    config, root = configured
    config = PhotoRuntimeConfig(config.python, config.bridge, config.consumed_registry, config.model,
                                timeout_seconds=6, temp_root=config.temp_root)
    (root / "mode").write_text("sleep")
    with TestClient(create_app(config)) as client, ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(request, client, content, "running")
        wait_started(root)
        assert request(client, content, "running").status_code == 409
        second = executor.submit(request, client, content, "waiting")
        deadline = time.monotonic() + 2
        while len(client.app.state.photo_runtime._inflight) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        overloaded = request(client, content, "overloaded")
        assert overloaded.status_code == 429
        assert first.result(timeout=10).status_code == 504
        assert second.result(timeout=10).status_code == 504
        assert len(wait_started(root)) <= 2
        (root / "mode").write_text("valid")
        assert request(client, content, "overloaded").status_code == 200
    assert not list(config.temp_root.iterdir())


@pytest.mark.parametrize("key,value", [
    ("candidate_components", True), ("changed_RGB_pixels", True), ("production_approved", True),
    ("processing_ms", float("inf")), ("evaluation", {"score": 99}), ("source_exif_orientation", True),
    ("status", "success"), ("request_id", "stale"), ("private_path", "SECRET"),
])
def test_wire_contract_rejects_typed_identity_flags_and_extra_fields(content, key, value):
    payload = synthetic_payload(content, "test")
    payload[key] = value
    with pytest.raises(TransportValidationError):
        validate_transport(payload, UploadedPhoto.decode(content), request_id="test", engine="native_v12")


def test_wire_rejects_changed_bounding_box_hole_and_overlapping_masks(content):
    payload = synthetic_payload(content, "test")
    rgb = UploadedPhoto.decode(base64.b64decode(payload["image_base64"])).rgb
    rgb[2, 2] ^= np.uint8(1)
    payload["image_base64"] = base64.b64encode(png(rgb)).decode("ascii")
    payload["returned_RGB_sha256"] = array_digest(rgb)
    with pytest.raises(TransportValidationError, match="partition"):
        validate_transport(payload, UploadedPhoto.decode(content), request_id="test", engine="native_v12")
    payload = synthetic_payload(content, "test")
    payload["rejected_permission_mask"] = copy.deepcopy(payload["accepted_permission_mask"])
    with pytest.raises(TransportValidationError, match="partition"):
        validate_transport(payload, UploadedPhoto.decode(content), request_id="test", engine="native_v12")


def test_fixed_schema_and_synthetic_example_match_actual_response_contract():
    contracts = Path(__file__).resolve().parent.parent / "contracts"
    schema = json.loads((contracts / "photo-experimental-v2.schema.json").read_text())
    example = json.loads((contracts / "photo-experimental-v2.synthetic.json").read_text())
    assert set(schema["properties"]) == RESPONSE_KEYS == set(schema["required"])
    assert schema["additionalProperties"] is False
    assert schema["properties"]["photo_engine"]["enum"] == list(ENGINE_METHODS)
    source = png(np.full((12, 16, 3), 120, np.uint8))
    validate_transport(example, UploadedPhoto.decode(source), request_id="synthetic-contract-example", engine="native_v12")


@pytest.mark.parametrize("engine", list(ENGINE_METHODS))
def test_real_core_response_and_independent_server_validator_have_identical_contract(engine):
    from native_photo_result_contract_v1 import ENTRYPOINTS
    from test_native_photo_result_contract_v1 import ExperimentalPhotoContractTests
    fixture = ExperimentalPhotoContractTests()
    fixture.setUp()
    source = png(fixture.rgb)
    upload = UploadedPhoto.decode(source)
    fixture.source_sha = upload.source_sha256
    fixture.report["input_identity"]["original_source_sha256"] = upload.source_sha256
    fixture.report["single_photo_entrypoint"] = ENTRYPOINTS[engine]
    wire = fixture.validate(engine=engine).response("core-to-wire", 1)
    validate_transport(wire, upload, request_id="core-to-wire", engine=engine)


def test_zero_candidate_pose_result_returns_original_with_empty_fullsize_masks(content):
    payload = synthetic_payload(content, "empty-pose", "pose_v14", all_rejected=True)
    shape = UploadedPhoto.decode(content).rgb.shape[:2]
    payload.update(candidate_components=0, transformed_components=0, rejected_components=0, region_display_bounds=[],
                   accepted_permission_mask=encoded_mask(np.zeros(shape, bool)),
                   rejected_permission_mask=encoded_mask(np.zeros(shape, bool)), warnings=warnings_for("pose_v14", 0))
    validate_transport(payload, UploadedPhoto.decode(content), request_id="empty-pose", engine="pose_v14")


def test_returned_PNG_limit_accepts_exact_boundary_and_rejects_next_byte_without_reencoding(content, monkeypatch):
    import experimental_photo_transport_v2 as transport
    payload = synthetic_payload(content, "size")
    returned_bytes = base64.b64decode(payload["image_base64"])
    upload = UploadedPhoto.decode(content)
    monkeypatch.setattr(transport, "MAX_IMAGE_BYTES", len(returned_bytes))
    validate_transport(payload, upload, request_id="size", engine="native_v12")
    monkeypatch.setattr(transport, "MAX_IMAGE_BYTES", len(returned_bytes) - 1)
    with pytest.raises(TransportValidationError):
        validate_transport(payload, upload, request_id="size", engine="native_v12")


def test_actual_http_server_real_subprocess_transport_probe(configured, content):
    config, root = configured
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment.update(BLURFING_PHOTO_PYTHON=str(config.python), BLURFING_PHOTO_BRIDGE=str(config.bridge),
                       BLURFING_PHOTO_CONSUMED_REGISTRY=str(config.consumed_registry),
                       BLURFING_PHOTO_MODEL=str(config.model), BLURFING_PHOTO_ENGINES="native_v12,distal_v13,pose_v14",
                       BLURFING_PHOTO_TEMP_ROOT=str(config.temp_root), PYTHONDONTWRITEBYTECODE="1")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "experimental_photo_main:app", "--host", "127.0.0.1",
                                "--port", str(port), "--log-level", "error"], cwd=Path(__file__).resolve().parent,
                               env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(base_url=base, timeout=20) as client:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    if client.get("/ready").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            response = request(client, content, engine="pose_v14")
            assert response.status_code == 200, response.text
            wire = response.json()
            assert wire["photo_engine"] == "pose_v14" and wire["status"] == "partial_success"
            validate_transport(wire, UploadedPhoto.decode(content), request_id="synthetic-request", engine="pose_v14")
    finally:
        process.terminate()
        process.wait(timeout=10)
    assert not list(config.temp_root.iterdir())
