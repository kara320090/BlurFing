"""개발용 실행: uvicorn mock_main:app --reload"""

import os

from main import app
from mock_processor import MockProcessor, mock_processor

delay_seconds = float(os.environ.get("BLURFING_MOCK_DELAY_SECONDS", "0"))
app.state.protection_processor = (
    mock_processor if delay_seconds == 0 else MockProcessor(delay_seconds)
)
