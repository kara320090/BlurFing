import json

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def protect_request(**overrides):
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
        files={"image": ("synthetic.png", b"synthetic-image", "image/png")},
    )


def test_valid_request_reaches_processing_boundary():
    response = protect_request()

    assert response.status_code == 501
    assert response.json() == {
        "request_id": "synthetic-request-001",
        "code": "PROCESSING_NOT_IMPLEMENTED",
        "message": "요청 검증은 완료되었지만 이미지 보호 처리는 아직 구현되지 않았습니다.",
        "retryable": False,
    }


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
