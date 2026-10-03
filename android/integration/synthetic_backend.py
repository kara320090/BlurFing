"""Local integration fixture. Replaces pixels with red; NOT an AI protection algorithm."""
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.main import app
from PIL import Image


def synthetic_red_image(image_bytes, method, strength, regions):
    with Image.open(io.BytesIO(image_bytes)) as source:
        result = Image.new('RGB', source.size, (255, 0, 0))
    output = io.BytesIO()
    result.save(output, format='PNG')
    return output.getvalue()


app.state.protection_processor = synthetic_red_image
