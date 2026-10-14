import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import protect_photo_learned_v1 as pipeline


class PhotoEntryTests(unittest.TestCase):
    def test_truthy_gate_strings_cannot_change_feature_domain(self):
        with self.assertRaisesRegex(ValueError,'flag_must_be_boolean'):
            pipeline.run('unused.png','unused','unused','unused',experimental_whole_region_gate='false')

    def test_RGB_L_RGBA_canonicalization_preserves_original_and_EXIF(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ['RGB','L','RGBA']:
                path=Path(tmp)/(mode+'.png');exif=Image.Exif();exif[274]=6
                if mode=='RGBA':data=np.array([[[10,80,150,255],[10,80,150,128],[100,0,0,0]]],np.uint8)
                elif mode=='L':data=np.array([[10,80,150]],np.uint8)
                else:data=np.array([[[10,80,150],[50,90,150],[200,80,150]]],np.uint8)
                Image.fromarray(data).save(path,exif=exif);before=path.read_bytes()
                rgb,identity=pipeline.canonical_rgb(path)
                self.assertEqual(path.read_bytes(),before);self.assertEqual(rgb.shape,(1,3,3));self.assertEqual(identity['source_exif_orientation'],6)
                if mode=='RGBA':np.testing.assert_array_equal(rgb,np.array([[[10,80,150],[132,167,202],[255,255,255]]],np.uint8))
                elif mode=='RGB':np.testing.assert_array_equal(rgb,data)
                else:np.testing.assert_array_equal(rgb,np.repeat(data[:,:,None],3,axis=2))

    def test_unsupported_depth_and_invalid_EXIF_reject_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.png';Image.fromarray(np.zeros((10,10),np.uint16)).save(path)
            with self.assertRaisesRegex(ValueError,'source_mode'):pipeline.canonical_rgb(path)
            exif=Image.Exif();exif[274]=9;Image.new('RGB',(10,10)).save(path,exif=exif)
            with self.assertRaisesRegex(ValueError,'exif'):pipeline.canonical_rgb(path)

    def test_existing_output_and_checkpoint_registry_mismatch_stop_before_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source=folder/'source.png';Image.new('RGB',(20,20),(200,130,110)).save(source)
            registry=folder/'registry.json';registry.write_text('[]')
            with self.assertRaises(FileExistsError):pipeline.run(source,folder/'model',registry,folder)
            out=folder/'new-output'
            with (patch.object(pipeline,'validate_registry'),patch.object(pipeline,'exclude_consumed'),
                  patch.object(pipeline.shared,'route_input',return_value=dict(input_type='PHOTO')),
                  patch.object(pipeline,'load_model',return_value=(object(),dict(consumed_registry_sha256='wrong'))),
                  patch.object(pipeline.subprocess,'run') as worker):
                with self.assertRaisesRegex(ValueError,'registry_mismatch'):pipeline.run(source,folder/'model',registry,out)
            self.assertFalse(out.exists());worker.assert_not_called()


if __name__=='__main__':unittest.main()
