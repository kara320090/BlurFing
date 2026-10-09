import asyncio
import base64
import io
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from mock_processor import MockProcessor


def read_positive_float_env(name: str, default: float) -> float:
    message = f"{name} must be a finite number greater than zero."
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(message) from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(message)
    return value


def read_positive_int_env(name: str, default: int) -> int:
    message = f"{name} must be an integer greater than zero."
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(message) from exc
    if value <= 0:
        raise ValueError(message)
    return value


app = FastAPI(title="BlurFing Backend")
app.state.protection_processor = None

MAX_IMAGE_SIZE_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
PROCESSOR_TIMEOUT_SECONDS = read_positive_float_env("BLURFING_PROCESSOR_TIMEOUT_SECONDS", 30.0)
MAX_PENDING_PROCESSOR_REQUESTS = read_positive_int_env("BLURFING_MAX_PENDING_PROCESSOR_REQUESTS", 4)
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png"}
SUPPORTED_METHODS = {"gaussian_blur"}
IN_FLIGHT_REQUEST_IDS: set[str] = set()
IN_FLIGHT_REQUEST_IDS_LOCK = threading.Lock()
PROCESSOR_EXECUTOR = ThreadPoolExecutor(thread_name_prefix="blurfing-processor")


class RegionResponse(BaseModel):
    x: float
    y: float
    width: float
    height: float


class ProtectionResponse(BaseModel):
    request_id: str
    status: Literal["succeeded", "no_regions"]
    result_kind: Literal["real", "mock"]
    image_base64: str | None
    mime_type: Literal["image/png"]
    applied_regions: list[RegionResponse]
    processing_ms: int
    warnings: list[str]


class ErrorResponse(BaseModel):
    request_id: str
    code: str
    message: str
    retryable: bool


PROTECT_ERROR_RESPONSES = {
    400: {"model": ErrorResponse, "description": "요청 값 또는 이미지가 올바르지 않음"},
    409: {"model": ErrorResponse, "description": "같은 요청 ID가 이미 처리 중임"},
    413: {"model": ErrorResponse, "description": "이미지 용량 또는 해상도 제한 초과"},
    415: {"model": ErrorResponse, "description": "지원하지 않는 이미지 형식"},
    500: {"model": ErrorResponse, "description": "AI 처리 결과 검증 실패"},
    503: {"model": ErrorResponse, "description": "AI 처리 모듈 미연결 또는 작업 접수 한도 초과"},
    504: {"model": ErrorResponse, "description": "AI 처리 제한 시간 초과"},
}


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


@app.get("/ready")
def readiness_check():
    if not callable(app.state.protection_processor):
        return error_response("", 503, "PROCESSOR_UNAVAILABLE", "보호 처리 모듈을 사용할 수 없습니다.", True)
    return {"status": "ready"}


def parse_strength(value: str) -> float:
    try:
        strength = float(value)
    except ValueError as exc:
        raise ValueError("strength는 0.1에서 1.0 사이의 숫자여야 합니다.") from exc

    if not math.isfinite(strength) or not 0.1 <= strength <= 1.0:
        raise ValueError("strength는 0.1에서 1.0 사이의 숫자여야 합니다.")
    return strength


def claim_request_id(request_id: str) -> Literal["accepted", "duplicate", "busy"]:
    with IN_FLIGHT_REQUEST_IDS_LOCK:
        if request_id in IN_FLIGHT_REQUEST_IDS:
            return "duplicate"
        if len(IN_FLIGHT_REQUEST_IDS) >= MAX_PENDING_PROCESSOR_REQUESTS:
            return "busy"
        IN_FLIGHT_REQUEST_IDS.add(request_id)
        return "accepted"


def release_request_id(request_id: str) -> None:
    with IN_FLIGHT_REQUEST_IDS_LOCK:
        IN_FLIGHT_REQUEST_IDS.discard(request_id)


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


@app.post(
    "/v1/protect",
    response_model=ProtectionResponse,
    responses=PROTECT_ERROR_RESPONSES,
)
async def protect_image(
    image: UploadFile | None = File(None),
    request_id: str | None = Form(None),
    method: str | None = Form(None),
    strength: str | None = Form(None),
    regions: str | None = Form(None),
):
    started = time.monotonic()
    request_id = (request_id or "").strip()
    if not request_id:
        return error_response("", 400, "INVALID_REQUEST_ID", "request_id를 입력해야 합니다.")

    missing_fields = [
        field_name
        for field_name, field_value in (
            ("image", image),
            ("method", method),
            ("strength", strength),
        )
        if field_value is None
    ]
    if missing_fields:
        return error_response(
            request_id,
            400,
            "INVALID_REQUEST",
            f"필수 입력값이 누락되었습니다: {', '.join(missing_fields)}",
        )

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
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return error_response(request_id, 400, "INVALID_IMAGE", "이미지 파일을 읽을 수 없습니다.")

    processor = app.state.protection_processor
    is_mock = isinstance(processor, MockProcessor)
    if not validated_regions:
        return {
            "request_id": request_id,
            "status": "no_regions",
            "result_kind": "mock" if is_mock else "real",
            "image_base64": None,
            "mime_type": "image/png",
            "applied_regions": [],
            "processing_ms": round((time.monotonic() - started) * 1000),
            "warnings": ["NO_REGIONS", "MOCK_NO_PROTECTION"] if is_mock else ["NO_REGIONS"],
        }

    if not callable(processor):
        return error_response(request_id, 503, "PROCESSOR_UNAVAILABLE", "보호 처리 모듈을 사용할 수 없습니다.", True)

    admission = claim_request_id(request_id)
    if admission == "duplicate":
        return error_response(
            request_id,
            409,
            "REQUEST_IN_PROGRESS",
            "같은 request_id의 요청이 이미 처리 중입니다.",
            True,
        )
    if admission == "busy":
        return error_response(
            request_id,
            503,
            "SERVER_BUSY",
            "서버가 처리 중인 요청이 많습니다. 잠시 후 다시 시도해 주세요.",
            True,
        )

    worker = None
    try:
        try:
            # 완료 콜백은 요청 이벤트 루프가 끝나도 실제 작업 종료 시 ID를 해제한다.
            worker = PROCESSOR_EXECUTOR.submit(
                processor, image_bytes, method, validated_strength, validated_regions
            )
            worker.add_done_callback(lambda _: release_request_id(request_id))
            pending_result = asyncio.wrap_future(worker)
            # 시간 초과 후 늦게 발생한 예외도 회수한다.
            pending_result.add_done_callback(
                lambda future: future.exception() if not future.cancelled() else None
            )
            result_bytes = await asyncio.wait_for(
                asyncio.shield(pending_result), timeout=PROCESSOR_TIMEOUT_SECONDS
            )
            with Image.open(io.BytesIO(result_bytes)) as result:
                if result.format != "PNG" or result.size != (width, height):
                    raise ValueError("처리 결과의 형식 또는 크기가 올바르지 않습니다.")
                result.load()
        except TimeoutError:
            return error_response(
                request_id,
                504,
                "PROCESSING_TIMEOUT",
                "보호 처리 시간이 제한을 초과했습니다.",
                True,
            )
        except Exception:
            return error_response(request_id, 500, "PROCESSING_FAILED", "보호 처리 결과를 확인할 수 없습니다.", True)

        return {
            "request_id": request_id,
            "status": "succeeded",
            "result_kind": "mock" if is_mock else "real",
            "image_base64": base64.b64encode(result_bytes).decode("ascii"),
            "mime_type": "image/png",
            "applied_regions": validated_regions,
            "processing_ms": round((time.monotonic() - started) * 1000),
            "warnings": ["MOCK_NO_PROTECTION"] if is_mock else [],
        }
    finally:
        # 작업 제출 자체가 실패했을 때만 여기서 해제한다.
        if worker is None:
            release_request_id(request_id)
