"""이미지 입출력 연동용 Mock. 실제 보호 처리는 수행하지 않는다."""

import io
import math
import time

from PIL import Image


class MockProcessor:
    """선택한 시간만큼 대기한 뒤 PNG를 반환하는 개발용 처리기."""

    def __init__(self, delay_seconds: float = 0.0):
        if not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise ValueError("Mock 지연 시간은 0 이상의 유한한 숫자여야 합니다.")
        self.delay_seconds = delay_seconds

    def __call__(
        self,
        image_bytes: bytes,
        method: str,
        strength: float,
        regions: list[dict[str, float]],
    ) -> bytes:
        """크기·픽셀 유지. method, strength, regions는 적용하지 않는다."""
        time.sleep(self.delay_seconds)
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.load()
            output = io.BytesIO()
            source.save(output, format="PNG")
            return output.getvalue()


mock_processor = MockProcessor()
