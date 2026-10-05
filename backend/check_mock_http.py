"""실행 중인 Mock 서버에 합성 이미지를 보내 실제 HTTP 입출력을 확인한다."""

import argparse
import base64
import io
import json
import sys

import httpx
from PIL import Image


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def synthetic_image(image_format: str) -> bytes:
    image = Image.new("RGB", (48, 32))
    for y in range(image.height):
        for x in range(image.width):
            image.putpixel((x, y), ((x * 5) % 256, (y * 7) % 256, (x + y) % 256))
    output = io.BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def check_image(client: httpx.Client, image_format: str) -> None:
    original_bytes = synthetic_image(image_format)
    request_id = f"http-mock-{image_format.lower()}"
    regions = [{"x": 0, "y": 0, "width": 1, "height": 1}]
    response = client.post(
        "/v1/protect",
        data={"request_id": request_id, "method": "gaussian_blur",
              "strength": "0.5", "regions": json.dumps(regions)},
        files={"image": (f"synthetic.{image_format.lower()}", original_bytes,
                         "image/png" if image_format == "PNG" else "image/jpeg")},
    )
    require(response.status_code == 200, f"{image_format}: HTTP {response.status_code}")
    body = response.json()
    require(body.get("request_id") == request_id, "request_id 불일치")
    require(body.get("status") == "succeeded", "정상 처리 상태가 아님")
    require(body.get("result_kind") == "mock", "Mock 서버가 아님")
    require(body.get("warnings") == ["MOCK_NO_PROTECTION"], "Mock 경고 누락")
    require(body.get("mime_type") == "image/png", "출력 MIME 타입 불일치")
    require(body.get("applied_regions") == regions, "전달 영역 불일치")
    result_bytes = base64.b64decode(body["image_base64"], validate=True)
    with Image.open(io.BytesIO(original_bytes)) as original, Image.open(io.BytesIO(result_bytes)) as result:
        original.load()
        result.load()
        require(result.format == "PNG", "출력 이미지가 PNG가 아님")
        require(result.size == original.size, "이미지 크기 변경됨")
        require(result.mode == original.mode, "이미지 색상 모드 변경됨")
        require(result.tobytes() == original.tobytes(), "디코딩된 픽셀 변경됨")
    print(f"PASS {image_format} -> PNG: 48x32, pixels unchanged, result_kind=mock")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=5.0, trust_env=False) as client:
            response = client.get("/")
            require(response.status_code == 200, "서버 실행 확인 실패")
            require(response.json() == {"message": "BlurFing backend is running"}, "서버 응답 불일치")
            print("PASS GET /: server running")
            response = client.get("/ready")
            require(response.status_code == 200, "처리기 연결 확인 실패")
            require(response.json() == {"status": "ready"}, "준비 상태 응답 불일치")
            print("PASS GET /ready: processor connected")
            for image_format in ("PNG", "JPEG"):
                check_image(client, image_format)
        print("PASS: 4 live HTTP checks completed; no image files saved")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
