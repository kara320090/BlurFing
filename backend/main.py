import base64
import io
import json
import math
import time
from typing import Any

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, ImageFilter, UnidentifiedImageError

app = FastAPI(title="BlurFing Backend")

MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png"}
SUPPORTED_METHODS = {"gaussian_blur"}


@app.get("/")
def health_check():
    return {"message": "BlurFing backend is running"}


def error_response(
    request_id: str,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "request_id": request_id,
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    )


def parse_strength(value: str) -> float:
    try:
        strength = float(value)
    except ValueError as exc:
        raise ValueError("strength는 0에서 1 사이의 숫자여야 합니다.") from exc

    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError("strength는 0에서 1 사이의 숫자여야 합니다.")
    return strength


def parse_regions(value: str | None) -> list[dict[str, float]] | None:
    if value is None:
        return None

    try:
        regions: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("regions는 JSON 배열이어야 합니다.") from exc

    if not isinstance(regions, list):
        raise ValueError("regions는 JSON 배열이어야 합니다.")

    validated_regions: list[dict[str, float]] = []
    required_keys = {"x", "y", "width", "height"}
    for region in regions:
        if not isinstance(region, dict) or set(region) != required_keys:
            raise ValueError("각 영역에는 x, y, width, height만 있어야 합니다.")

        coordinates: dict[str, float] = {}
        for key in required_keys:
            value = region[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("영역 좌표는 숫자여야 합니다.")
            coordinate = float(value)
            if not math.isfinite(coordinate):
                raise ValueError("영역 좌표는 유한한 숫자여야 합니다.")
            coordinates[key] = coordinate

        if coordinates["width"] <= 0 or coordinates["height"] <= 0:
            raise ValueError("영역의 width와 height는 0보다 커야 합니다.")
        if coordinates["x"] < 0 or coordinates["y"] < 0:
            raise ValueError("영역의 x와 y는 0 이상이어야 합니다.")
        if coordinates["x"] + coordinates["width"] > 1:
            raise ValueError("영역의 x + width는 1 이하여야 합니다.")
        if coordinates["y"] + coordinates["height"] > 1:
            raise ValueError("영역의 y + height는 1 이하여야 합니다.")

        validated_regions.append(coordinates)

    return validated_regions


def blur_regions(image: Image.Image, regions: list[dict[str, float]], strength: float) -> Image.Image:
    width, height = image.size
    radius = 1 + 19 * strength
    for region in regions:
        left = max(0, min(width - 1, math.floor(region["x"] * width)))
        top = max(0, min(height - 1, math.floor(region["y"] * height)))
        right = max(left + 1, min(width, math.ceil((region["x"] + region["width"]) * width)))
        bottom = max(top + 1, min(height, math.ceil((region["y"] + region["height"]) * height)))
        box = (left, top, right, bottom)
        image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(radius)), box)
    return image


@app.post("/v1/protect")
async def protect_image(
    image: UploadFile = File(...),
    request_id: str = Form(...),
    method: str = Form(...),
    strength: str = Form(...),
    regions: str | None = Form(None),
):
    started = time.monotonic()
    request_id = request_id.strip()
    if not request_id:
        return error_response("", 400, "INVALID_REQUEST_ID", "request_id를 입력해야 합니다.")

    if method not in SUPPORTED_METHODS:
        return error_response(
            request_id,
            400,
            "UNSUPPORTED_METHOD",
            "지원하지 않는 보호 방식입니다.",
        )

    try:
        validated_strength = parse_strength(strength)
        validated_regions = parse_regions(regions)
    except ValueError as exc:
        return error_response(request_id, 400, "INVALID_REQUEST", str(exc))

    if image.content_type not in SUPPORTED_IMAGE_TYPES:
        await image.close()
        return error_response(
            request_id,
            415,
            "UNSUPPORTED_IMAGE_TYPE",
            "PNG 또는 JPEG 이미지만 전송할 수 있습니다.",
        )

    image_bytes = await image.read(MAX_IMAGE_SIZE_BYTES + 1)
    await image.close()
    if not image_bytes:
        return error_response(request_id, 400, "EMPTY_IMAGE", "이미지 파일이 비어 있습니다.")
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return error_response(
            request_id,
            413,
            "IMAGE_TOO_LARGE",
            "이미지는 최대 15MB까지 전송할 수 있습니다.",
        )

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.format not in {"PNG", "JPEG"}:
                raise ValueError("PNG 또는 JPEG 이미지가 아닙니다.")
            width, height = source.size
            if width * height > MAX_IMAGE_PIXELS:
                return error_response(request_id, 413, "IMAGE_TOO_LARGE", "이미지 해상도가 너무 큽니다.")
            source.load()
            decoded = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return error_response(request_id, 400, "INVALID_IMAGE", "이미지 파일을 읽을 수 없습니다.")

    if not validated_regions:
        return {
            "request_id": request_id,
            "status": "no_regions",
            "result_kind": "real",
            "image_base64": None,
            "mime_type": "image/png",
            "applied_regions": [],
            "processing_ms": round((time.monotonic() - started) * 1000),
            "warnings": ["NO_REGIONS"],
        }

    result = blur_regions(decoded, validated_regions, validated_strength)
    output = io.BytesIO()
    result.save(output, format="PNG")
    return {
        "request_id": request_id,
        "status": "succeeded",
        "result_kind": "real",
        "image_base64": base64.b64encode(output.getvalue()).decode("ascii"),
        "mime_type": "image/png",
        "applied_regions": validated_regions,
        "processing_ms": round((time.monotonic() - started) * 1000),
        "warnings": [],
    }
