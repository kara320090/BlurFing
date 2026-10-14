"""Private-data-free contract and restoration regressions."""
import hashlib
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from photo_coarse_adapter import orient,seed_square,square_scope
from photo_coarse_renderer_adapter_v1 import transform

class CoarseAdapterTests(unittest.TestCase):
    def test_EXIF_permutations_match_explicit_pixel_positions(self):
        from photo_coarse_adapter_v2 import orient as orient_v2
        rgb=np.arange(7*11*3,dtype=np.uint8).reshape(7,11,3)
        transposed=rgb.transpose(1,0,2)
        expected={1:rgb,2:rgb[:,::-1],3:rgb[::-1,::-1],4:rgb[::-1],
                  5:transposed,6:np.rot90(rgb,-1),7:transposed[::-1,::-1],8:np.rot90(rgb)}
        for adapter in [orient,orient_v2]:
            for orientation,pixels in expected.items():
                np.testing.assert_array_equal(adapter(rgb,orientation),pixels)
    def test_all_EXIF_permutations_roundtrip(self):
        rgb=np.arange(7*11*3,dtype=np.uint8).reshape(7,11,3)
        for orientation in range(1,9):np.testing.assert_array_equal(orient(orient(rgb,orientation),orientation,True),rgb)
    def test_square_padding_keeps_complete_long_mask(self):
        mask=np.zeros((50,20),bool);mask[2:48,3:18]=True
        (a,b,c,d),pad=square_scope(mask)
        self.assertEqual(c-a,d-b);self.assertGreater(pad['right'],0)
        y,x=np.where(mask);self.assertTrue((x>=a).all() and (x<c).all() and (y>=b).all() and (y<d).all())
    def test_seed_is_deterministic_and_inside_mask(self):
        mask=np.zeros((100,80),bool);mask[10:90,20:60]=True
        box=seed_square(mask);self.assertEqual(box,seed_square(mask));a,b,c,d=box;self.assertTrue(mask[b:d,a:c].all())
    def test_empty_or_tiny_seed_reject(self):
        with self.assertRaises(ValueError):seed_square(np.zeros((20,20),bool))
    def artifact(self,rgb):
        return dict(source_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),source_sha256='0'*64,exif_orientation=1,working_scale=1.,working_shape=rgb.shape[:2],regions=[],coarse_mask=np.zeros(rgb.shape[:2],bool))
    def test_source_RGB_hash_mismatch(self):
        rgb=np.zeros((20,20,3),np.uint8);a=self.artifact(rgb);a['source_rgb_sha256']='1'*64
        with self.assertRaises(ValueError):transform(rgb,a)
    def test_renderer_exception_restores_all_bindings(self):
        import transform_automatic_fingerprint_poc_v4 as f
        import whole_pad_skin_relief as r
        import fingerprint_structure_check as s
        rgb=np.zeros((20,20,3),np.uint8);old=(f.detect_fingertips,f.propose_visible_pad,r.propose_visible_pad,s.OUT,s.run_matcher_job)
        with patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):transform(rgb,self.artifact(rgb))
        self.assertEqual(old,(f.detect_fingertips,f.propose_visible_pad,r.propose_visible_pad,s.OUT,s.run_matcher_job))
    def test_strength_zero_keeps_native_pixels(self):
        rgb=np.full((30,20,3),80,np.uint8);out,d=transform(rgb,self.artifact(rgb),0);np.testing.assert_array_equal(out,rgb);self.assertFalse(d['applied'])

if __name__=='__main__':unittest.main()
