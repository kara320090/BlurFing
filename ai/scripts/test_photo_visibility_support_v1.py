import unittest
import cv2
import numpy as np
from photo_visibility_support_v1 import full_area_support
from photo_visibility_peak_train_probe_v4 import probe_level as old_probe
from photo_visibility_peak_train_probe_v5 import probe_level


class AreaSupportTests(unittest.TestCase):
    def test_uniform_interior_survives_fractional_resize(self):
        for shape, size in [((558, 285), (262, 512)), ((199, 273), (137, 100)), ((81, 79), (43, 41))]:
            mask = np.ones(shape, bool)
            self.assertTrue(full_area_support(mask, size).all())
            self.assertFalse(full_area_support(~mask, size).any())
        # Reproduces the previous numerical assumption without making the test
        # depend on a particular OpenCV release exhibiting that rounding error.
        m = np.ones((558, 285), bool)
        legacy = cv2.resize(m.astype(np.float64), (262, 512), interpolation=cv2.INTER_AREA)
        self.assertLess(float(np.max(np.abs(legacy-1))), 1e-5)

    def test_true_source_footprint_and_outside_pixel_never_enters(self):
        rng = np.random.default_rng(37)
        for h, w, dh, dw in [(29, 31, 17, 19), (80, 91, 41, 47), (96, 128, 48, 64)]:
            mask = rng.random((h, w)) > .08
            actual = full_area_support(mask, (dw, dh))
            oracle = np.zeros((dh, dw), bool)
            for y in range(dh):
                for x in range(dw):
                    y0 = y*h//dh; y1 = ((y+1)*h+dh-1)//dh
                    x0 = x*w//dw; x1 = ((x+1)*w+dw-1)//dw
                    oracle[y, x] = mask[y0:y1, x0:x1].all()
            np.testing.assert_array_equal(actual, oracle)
            outside_signal = cv2.resize((~mask).astype(np.float64)*255, (dw, dh), interpolation=cv2.INTER_AREA)
            self.assertTrue((outside_signal[actual] == 0).all())

    def test_resized_positive_is_observed_and_native_math_unchanged(self):
        y, x = np.indices((199, 273)); gray = (128+10*np.sin(2*np.pi*x/14)).astype(np.uint8)
        mask = np.ones(gray.shape, bool); before = gray.copy()
        result = probe_level(gray, mask, 137)
        self.assertTrue(result['candidate_signal_observed'])
        self.assertGreater(sum(s['eligible_windows'] for s in result['scales']), 0)
        a = old_probe(gray, mask, 512); b = probe_level(gray, mask, 512)
        self.assertEqual(a['scales'], b['scales'])
        self.assertEqual(b['automatic_visibility'], 'uncertain'); self.assertFalse(b['used_by_protection'])
        np.testing.assert_array_equal(gray, before)

    def test_support_contract_and_no_upsampling(self):
        m = np.ones((80, 90), bool)
        for size in [(0, 10), (91, 80), (90, 81), (10., 10), (True, 10)]:
            with self.assertRaises(ValueError): full_area_support(m, size)
        with self.assertRaises(ValueError): full_area_support(m.astype(np.uint8), (45, 40))


if __name__ == '__main__': unittest.main()
