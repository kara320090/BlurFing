"""Synthetic unit/rotation tests of the current PHOTO observer, no tuning."""
import unittest
import numpy as np
from contactless_ridge_pitch import estimate_ridge_pitch
from protect_visible_pad_checked_v2 import observed_seed_pitch


def stripes(side,period):
    y,x=np.indices((side,side))
    return np.rint(128+55*np.cos(2*np.pi*x/period)).astype(np.uint8)


class PitchCoordinateTests(unittest.TestCase):
    def test_seed_normalization_returns_caller_pixels_not_512_pixels(self):
        for side,period in [(256,8),(512,16),(768,24)]:
            image=np.repeat(stripes(side,period)[:,:,None],3,axis=2);before=image.copy()
            pitch,evidence,raw=observed_seed_pitch(image,[0,0,side,side])
            self.assertIsNotNone(pitch);self.assertAlmostEqual(pitch,period,delta=.15)
            self.assertAlmostEqual(evidence['pitch512'],16.,delta=.15)
            self.assertEqual(raw.shape,(512,512));np.testing.assert_array_equal(image,before)

    def test_acf_supported_periods_preserve_quarter_turns(self):
        support=np.ones((512,512),bool)
        for period in [6,10,16,22]:
            for turn in [0,1]:
                observed=estimate_ridge_pitch(np.rot90(stripes(512,period),turn).copy(),support)
                self.assertEqual(observed['status'],'estimated')
                self.assertAlmostEqual(observed['pitch'],period,delta=.5)
                self.assertFalse(observed['physical_dpi_known'])

    def test_out_of_band_or_empty_support_has_no_default_pitch(self):
        support=np.ones((512,512),bool)
        for period in [30,40]:
            observed=estimate_ridge_pitch(stripes(512,period),support)
            self.assertIsNone(observed['pitch'])
        observed=estimate_ridge_pitch(stripes(512,10),np.zeros((512,512),bool))
        self.assertIsNone(observed['pitch']);self.assertEqual(observed['count'],0)


if __name__=='__main__':unittest.main()
