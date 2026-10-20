"""Both available PNG decoders obey the same canonical transport boundary."""
import io
from unittest.mock import patch
import numpy as np
from PIL import Image
import pytest
import experimental_photo_transport_v2 as wire


@pytest.mark.parametrize('mode',['RGB','L'])
@pytest.mark.parametrize('orientation',[None,1])
def test_opencv_matches_pillow_without_orientation_or_channel_changes(mode,orientation):
    if wire.cv2 is None:pytest.skip('optional OpenCV unavailable')
    rng=np.random.default_rng(59)
    array=rng.integers(0,256,(51,67,3) if mode=='RGB' else (51,67),dtype=np.uint8)
    target=io.BytesIO();exif=Image.Exif()
    if orientation is not None:exif[274]=orientation
    Image.fromarray(array).save(target,format='PNG',**(dict(exif=exif) if orientation is not None else {}))
    fast=wire.decode_png(target.getvalue(),mode=mode)
    with patch.object(wire,'cv2',None):fallback=wire.decode_png(target.getvalue(),mode=mode)
    np.testing.assert_array_equal(fast,array);np.testing.assert_array_equal(fallback,array)


def test_invalid_orientation_fails_before_native_decoder_allocation():
    target=io.BytesIO();exif=Image.Exif();exif[274]=6
    Image.new('RGB',(3,4)).save(target,format='PNG',exif=exif)
    with patch.object(wire,'cv2') as decoder:
        with pytest.raises(wire.TransportValidationError):wire.decode_png(target.getvalue(),mode='RGB')
        decoder.imdecode.assert_not_called()
