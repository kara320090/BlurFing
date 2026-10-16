import unittest
import numpy as np
from photo_pitch_free_redaction_v1 import redact,pixel_hash


class PitchFreeRedactionTests(unittest.TestCase):
    def fixture(self):
        rgb=np.random.default_rng(37).integers(0,256,(41,63,3),np.uint8)
        mask=np.zeros(rgb.shape[:2],bool);mask[3:17,6:21]=True;mask[27:37,41:59]=True
        return rgb,mask

    def test_exact_solid_fill_and_exterior_preservation_for_disconnected_regions(self):
        rgb,mask=self.fixture();before=rgb.copy();oldmask=mask.copy()
        result,report=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask))
        self.assertFalse(np.any(result[mask]));np.testing.assert_array_equal(result[~mask],rgb[~mask])
        np.testing.assert_array_equal(rgb,before);np.testing.assert_array_equal(mask,oldmask)
        self.assertEqual(report['status'],'redacted_unverified_scope');self.assertFalse(report['whole_photo_protection_verified'])
        self.assertFalse(report['pitch_estimation_required']);self.assertFalse(report['frozen_renderer_used'])

    def test_empty_mask_returns_original_without_coverage_claim(self):
        rgb,mask=self.fixture();mask[:]=False;result,report=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask))
        np.testing.assert_array_equal(result,rgb);self.assertEqual(report['status'],'no_mask_original_returned')
        self.assertFalse(report['anatomical_mask_coverage_verified'])

    def test_filled_RGB_does_not_depend_on_any_original_masked_RGB(self):
        rgb,mask=self.fixture();second=rgb.copy();second[mask]=255-rgb[mask]
        a,_=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask));b,_=redact(second,mask,pixel_hash(second),pixel_hash(mask))
        np.testing.assert_array_equal(a,b)

    def test_quarter_turn_and_already_black_region(self):
        rgb,mask=self.fixture();expected,_=redact(rgb,mask,pixel_hash(rgb),pixel_hash(mask))
        for k in range(4):
            a,b=np.rot90(rgb,k).copy(),np.rot90(mask,k).copy();result,_=redact(a,b,pixel_hash(a),pixel_hash(b))
            np.testing.assert_array_equal(result,np.rot90(expected,k))
        result,report=redact(expected,mask,pixel_hash(expected),pixel_hash(mask))
        self.assertEqual(report['changed_RGB_pixels'],0);self.assertTrue(report['source_RGB_removed_inside_provided_mask'])

    def test_hash_dtype_and_shape_contracts(self):
        rgb,mask=self.fixture()
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):redact(rgb,mask,'0'*64,pixel_hash(mask))
        for a,b in [(rgb.astype(float),mask),(rgb,mask.astype(np.uint8)),(rgb,mask[:2])]:
            with self.assertRaises(ValueError):redact(a,b,pixel_hash(a),pixel_hash(b))
        with self.assertRaisesRegex(ValueError,'hash_contract'):redact(rgb,mask,None,pixel_hash(mask))


if __name__=='__main__':unittest.main()
