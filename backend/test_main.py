import base64
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import main as backend_main
from main import MAX_IMAGE_SIZE_BYTES, app
from mock_processor import mock_processor


client = TestClient(app)


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_mock_returns_png_with_original_pixels(image_format, monkeypatch):
    output = io.BytesIO()
    Image.new("RGB", (40, 40), (24, 120, 230)).save(output, format=image_format)
    image_bytes = output.getvalue()
    monkeypatch.setattr(app.state, "protection_processor", mock_processor)
    response = client.post(
        "/v1/protect",
        data={"request_id": "mock-image", "method": "gaussian_blur", "strength": "1",
              "regions": json.dumps([{"x": 0, "y": 0, "width": 1, "height": 1}])},
        files={"image": ("synthetic", image_bytes, "image/png" if image_format == "PNG" else "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["result_kind"] == "mock"
    assert body["warnings"] == ["MOCK_NO_PROTECTION"]
    assert body["mime_type"] == "image/png"
    with Image.open(io.BytesIO(image_bytes)) as original, Image.open(
        io.BytesIO(base64.b64decode(body["image_base64"]))
    ) as result:
        assert result.format == "PNG"
        assert result.size == original.size
        assert result.tobytes() == original.tobytes()


def test_mock_without_regions_is_marked_as_mock(monkeypatch):
    monkeypatch.setattr(app.state, "protection_processor", mock_processor)
    body = protect_request(regions="[]").json()
    assert body["status"] == "no_regions"
    assert body["result_kind"] == "mock"
    assert body["image_base64"] is None
    assert body["warnings"] == ["NO_REGIONS", "MOCK_NO_PROTECTION"]


def test_mock_entrypoint_connects_processor(monkeypatch):
    import importlib

    monkeypatch.setattr(app.state, "protection_processor", None)
    mock_app = importlib.import_module("mock_main").app
    assert mock_app is app
    assert mock_app.state.protection_processor is mock_processor
    assert client.get("/ready").json() == {"status": "ready"}
    assert protect_request().json()["result_kind"] == "mock"


def test_root_reports_server_running_without_processor():
    app.state.protection_processor = None

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "BlurFing backend is running"}


def test_ready_reports_unavailable_without_processor():
    app.state.protection_processor = None

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "request_id": "",
        "code": "PROCESSOR_UNAVAILABLE",
        "message": "보호 처리 모듈을 사용할 수 없습니다.",
        "retryable": True,
    }


def test_ready_reports_connected_processor():
    app.state.protection_processor = lambda *_: b"synthetic-result"
    try:
        response = client.get("/ready")
    finally:
        app.state.protection_processor = None

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_changes_to_available_after_processor_connection():
    app.state.protection_processor = None
    assert client.get("/ready").status_code == 503

    app.state.protection_processor = lambda *_: b"synthetic-result"
    try:
        response = client.get("/ready")
    finally:
        app.state.protection_processor = None

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_changes_to_unavailable_after_processor_disconnection():
    app.state.protection_processor = lambda *_: b"synthetic-result"
    try:
        assert client.get("/ready").status_code == 200
    finally:
        app.state.protection_processor = None

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "PROCESSOR_UNAVAILABLE"


def synthetic_image():
    image = Image.new("RGB", (40, 40), "white")
    for x in range(10, 30):
        for y in range(10, 30):
            image.putpixel((x, y), (255, 0, 0) if (x + y) % 2 else (0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def protect_request(image_bytes=None, **overrides):
    data = {
        "request_id": "synthetic-request-001",
        "method": "gaussian_blur",
        "strength": "0.5",
        "regions": json.dumps(
            [{"x": 0.2, "y": 0.1, "width": 0.1, "height": 0.2}]
        ),
    }
    data.update(overrides)
    return client.post(
        "/v1/protect",
        data=data,
        files={"image": ("synthetic.png", image_bytes if image_bytes is not None else synthetic_image(), "image/png")},
    )


def test_forwards_request_to_processor_and_returns_result():
    original_bytes = synthetic_image()
    calls = []

    def processor(image_bytes, method, strength, regions):
        calls.append((image_bytes, method, strength, regions))
        image = Image.new("RGB", (40, 40), "black")
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    app.state.protection_processor = processor
    try:
        response = protect_request(image_bytes=original_bytes, strength="1")
    finally:
        app.state.protection_processor = None

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "synthetic-request-001"
    assert body["status"] == "succeeded"
    assert body["result_kind"] == "real"
    assert body["mime_type"] == "image/png"
    assert body["applied_regions"] == [{"x": 0.2, "y": 0.1, "width": 0.1, "height": 0.2}]
    assert calls == [(original_bytes, "gaussian_blur", 1.0, body["applied_regions"])]
    with Image.open(io.BytesIO(original_bytes)) as original, Image.open(io.BytesIO(base64.b64decode(body["image_base64"]))) as result:
        assert result.size == original.size
        assert result.getpixel((0, 0)) == (0, 0, 0)


def test_unconnected_processor_is_unavailable():
    response = protect_request()

    assert response.status_code == 503
    assert response.json()["code"] == "PROCESSOR_UNAVAILABLE"


def test_rejects_invalid_processor_output():
    app.state.protection_processor = lambda *_: b"not an image"
    try:
        response = protect_request()
    finally:
        app.state.protection_processor = None

    assert response.status_code == 500
    assert response.json()["code"] == "PROCESSING_FAILED"


def test_rejects_processor_output_with_different_dimensions():
    def processor(*_):
        output = io.BytesIO()
        Image.new("RGB", (20, 20), "black").save(output, format="PNG")
        return output.getvalue()

    app.state.protection_processor = processor
    try:
        response = protect_request()
    finally:
        app.state.protection_processor = None

    assert response.status_code == 500
    assert response.json() == {
        "request_id": "synthetic-request-001",
        "code": "PROCESSING_FAILED",
        "message": "보호 처리 결과를 확인할 수 없습니다.",
        "retryable": True,
    }


def test_processor_failure_returns_server_error():
    def processor(*_):
        raise RuntimeError("internal processor detail")

    app.state.protection_processor = processor
    try:
        response = protect_request()
    finally:
        app.state.protection_processor = None

    assert response.status_code == 500
    assert response.json()["code"] == "PROCESSING_FAILED"
    assert "internal processor detail" not in response.text


def test_processor_timeout_returns_retryable_gateway_timeout(monkeypatch):
    def processor(*_):
        time.sleep(0.05)
        return synthetic_image()

    monkeypatch.setattr(backend_main, "PROCESSOR_TIMEOUT_SECONDS", 0.01)
    app.state.protection_processor = processor
    try:
        response = protect_request()
    finally:
        app.state.protection_processor = None

    assert response.status_code == 504
    assert response.json() == {
        "request_id": "synthetic-request-001",
        "code": "PROCESSING_TIMEOUT",
        "message": "보호 처리 시간이 제한을 초과했습니다.",
        "retryable": True,
    }


def test_duplicate_request_id_is_rejected_while_first_request_is_processing():
    processor_started = Event()
    allow_processor_to_finish = Event()

    def processor(*_):
        processor_started.set()
        if not allow_processor_to_finish.wait(timeout=2):
            raise RuntimeError("test processor did not resume")
        return synthetic_image()

    app.state.protection_processor = processor
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            first_request = executor.submit(protect_request)
            assert processor_started.wait(timeout=2)
            duplicate_response = protect_request()
            allow_processor_to_finish.set()
            first_response = first_request.result(timeout=2)
    finally:
        allow_processor_to_finish.set()
        app.state.protection_processor = None

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 409
    assert duplicate_response.json() == {
        "request_id": "synthetic-request-001",
        "code": "REQUEST_IN_PROGRESS",
        "message": "같은 request_id의 요청이 이미 처리 중입니다.",
        "retryable": True,
    }


@pytest.mark.parametrize("first_outcome", ["success", "failure", "timeout"])
def test_request_id_is_reusable_after_processing_finishes(first_outcome, monkeypatch):
    if first_outcome == "success":
        first_processor = lambda *_: synthetic_image()
        expected_status = 200
    elif first_outcome == "failure":
        def first_processor(*_):
            raise RuntimeError("synthetic failure")

        expected_status = 500
    else:
        def first_processor(*_):
            time.sleep(0.05)
            return synthetic_image()

        monkeypatch.setattr(backend_main, "PROCESSOR_TIMEOUT_SECONDS", 0.01)
        expected_status = 504

    app.state.protection_processor = first_processor
    try:
        first_response = protect_request()
        if first_outcome == "timeout":
            monkeypatch.setattr(backend_main, "PROCESSOR_TIMEOUT_SECONDS", 1.0)
        app.state.protection_processor = lambda *_: synthetic_image()
        retry_response = protect_request()
    finally:
        app.state.protection_processor = None

    assert first_response.status_code == expected_status
    assert retry_response.status_code == 200


def test_empty_regions_do_not_claim_success():
    response = protect_request(regions="[]")

    assert response.status_code == 200
    assert response.json()["status"] == "no_regions"
    assert response.json()["image_base64"] is None


def test_invalid_image_is_rejected():
    response = protect_request(image_bytes=b"not a png")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IMAGE"


def test_rejects_strength_outside_supported_range():
    response = protect_request(strength="1.1")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


def test_rejects_region_outside_image_bounds():
    response = protect_request(
        regions=json.dumps(
            [{"x": 0.9, "y": 0.1, "width": 0.2, "height": 0.2}]
        )
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    "regions",
    [
        "not-json",
        json.dumps([{"x": -0.1, "y": 0.1, "width": 0.2, "height": 0.2}]),
        json.dumps([{"x": 0.1, "y": 0.1, "width": 0, "height": 0.2}]),
        json.dumps([{"x": 0.1, "y": 0.1, "width": 0.2, "height": float("nan")}]),
    ],
)
def test_rejects_invalid_region_values(regions):
    response = protect_request(regions=regions)

    assert response.status_code == 400
    assert response.json()["request_id"] == "synthetic-request-001"
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["retryable"] is False


def test_rejects_image_over_15mb_before_processing():
    processor_calls = []
    app.state.protection_processor = lambda *_: processor_calls.append(True)
    try:
        response = protect_request(image_bytes=b"x" * (MAX_IMAGE_SIZE_BYTES + 1))
    finally:
        app.state.protection_processor = None

    assert response.status_code == 413
    assert response.json()["request_id"] == "synthetic-request-001"
    assert response.json()["code"] == "IMAGE_TOO_LARGE"
    assert response.json()["retryable"] is False
    assert processor_calls == []


def test_rejects_unsupported_method():
    response = protect_request(method="unknown")

    assert response.status_code == 400
    assert response.json()["code"] == "UNSUPPORTED_METHOD"


def test_rejects_unsupported_image_type():
    response = client.post(
        "/v1/protect",
        data={
            "request_id": "synthetic-request-002",
            "method": "gaussian_blur",
            "strength": "0.5",
        },
        files={"image": ("synthetic.gif", b"synthetic-image", "image/gif")},
    )

    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_IMAGE_TYPE"


@pytest.mark.parametrize("missing_field", ["image", "method", "strength"])
def test_missing_required_input_uses_common_error_response(missing_field):
    data = {
        "request_id": "synthetic-request-003",
        "method": "gaussian_blur",
        "strength": "0.5",
    }
    files = {"image": ("synthetic.png", synthetic_image(), "image/png")}
    if missing_field == "image":
        files = None
    else:
        data.pop(missing_field)

    response = client.post("/v1/protect", data=data, files=files)

    assert response.status_code == 400
    assert response.json() == {
        "request_id": "synthetic-request-003",
        "code": "INVALID_REQUEST",
        "message": f"필수 입력값이 누락되었습니다: {missing_field}",
        "retryable": False,
    }


def test_missing_request_id_uses_common_error_response():
    response = client.post(
        "/v1/protect",
        data={"method": "gaussian_blur", "strength": "0.5"},
        files={"image": ("synthetic.png", synthetic_image(), "image/png")},
    )

    assert response.status_code == 400
    assert response.json() == {
        "request_id": "",
        "code": "INVALID_REQUEST_ID",
        "message": "request_id를 입력해야 합니다.",
        "retryable": False,
    }


def test_openapi_defines_protection_success_and_error_responses():
    operation = client.get("/openapi.json").json()["paths"]["/v1/protect"]["post"]
    responses = operation["responses"]

    assert {"200", "400", "409", "413", "415", "500", "503", "504"} <= set(responses)
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProtectionResponse"
    }
    for status_code in ("400", "409", "413", "415", "500", "503", "504"):
        assert responses[status_code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
