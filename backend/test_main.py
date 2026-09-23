import base64
import io
import json

from fastapi.testclient import TestClient
from PIL import Image

from main import app


client = TestClient(app)


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


def test_blur_changes_only_selected_region_and_preserves_size():
    original_bytes = synthetic_image()
    response = protect_request(image_bytes=original_bytes, strength="1")

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "synthetic-request-001"
    assert body["status"] == "succeeded"
    assert body["result_kind"] == "real"
    assert body["mime_type"] == "image/png"
    assert body["applied_regions"] == [{"x": 0.2, "y": 0.1, "width": 0.1, "height": 0.2}]
    with Image.open(io.BytesIO(original_bytes)) as original, Image.open(io.BytesIO(base64.b64decode(body["image_base64"]))) as result:
        assert result.size == original.size
        assert result.getpixel((0, 0)) == original.getpixel((0, 0))
        assert result.getpixel((10, 10)) != original.getpixel((10, 10))


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
