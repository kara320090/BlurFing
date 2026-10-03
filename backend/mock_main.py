"""개발용 실행: uvicorn mock_main:app --reload"""

from main import app
from mock_processor import mock_processor

app.state.protection_processor = mock_processor
