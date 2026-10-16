import tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from photo_source_rgb_v1 import canonical_rgb,source_diagnostic


class SourceRGBTests(unittest.TestCase):
    def test_RGB_L_RGBA_all_EXIF_orientations_preserve_encoded_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'source.png'
            for mode in ['RGB','RGBA','L']:
                shape=(7,11) if mode=='L' else (7,11,4 if mode=='RGBA' else 3)
                data=np.arange(np.prod(shape),dtype=np.uint8).reshape(shape)
                for orientation in range(1,9):
                    exif=Image.Exif();exif[274]=orientation;Image.fromarray(data).save(p,exif=exif);before=p.read_bytes()
                    rgb,identity=canonical_rgb(p)
                    if mode=='RGBA':
                        alpha=data[:,:,3:4].astype(np.uint32);expected=((data[:,:,:3].astype(np.uint32)*alpha+255*(255-alpha)+127)//255).astype(np.uint8)
                    elif mode=='L':expected=np.repeat(data[:,:,None],3,axis=2)
                    else:expected=data
                    np.testing.assert_array_equal(rgb,expected);self.assertEqual(identity['source_exif_orientation'],orientation)
                    self.assertEqual(p.read_bytes(),before)

    def test_missing_EXIF_defaults_one_but_invalid_value_is_never_guessed(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'source.png';Image.new('L',(8,8),100).save(p)
            _,identity=canonical_rgb(p);self.assertEqual(identity['source_exif_orientation'],1)
            for value in [0,9]:
                exif=Image.Exif();exif[274]=value;Image.new('RGB',(8,8)).save(p,exif=exif)
                with self.assertRaisesRegex(ValueError,'invalid_source_exif'):canonical_rgb(p)
                self.assertEqual(source_diagnostic(p)['EXIF_orientation_repr'],str(value))


if __name__=='__main__':unittest.main()
