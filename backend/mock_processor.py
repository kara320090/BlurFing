"""이미지 입출력 연동용 Mock. 실제 보호 처리는 수행하지 않는다."""

import io

from PIL import Image


def mock_processor(
    image_bytes: bytes,
    method: str,
    strength: float,
    regions: list[dict[str, float]],
) -> bytes:
    """AI 함수와 같은 입력을 받고 크기·픽셀을 유지한 PNG를 반환한다.

    method, strength, regions는 연결 계약을 맞추기 위한 인자이며 적용하지 않는다.
    파일을 저장하지 않고 메모리에서만 변환한다.
    """
    with Image.open(io.BytesIO(image_bytes)) as source:
        source.load()
        output = io.BytesIO()
        source.save(output, format="PNG")
        return output.getvalue()
