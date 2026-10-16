import unittest
import numpy as np
from photo_raw_profile_pitch_v2 import observe


class RawProfilePitchTests(unittest.TestCase):
    def fixture(self,period=8.,degrees=0):
        y,x=np.indices((512,512));angle=np.deg2rad(degrees)
        raw=np.clip(128+60*np.cos(2*np.pi*(-x*np.sin(angle)+y*np.cos(angle))/period),0,255).astype(np.uint8)
        return raw,np.ones(raw.shape,bool),np.full(raw.shape,angle,np.float64)

    def test_known_periods_use_image_units_across_sampling_rates(self):
        for period in [3.2,8.,26.4]:
            result=observe(*self.fixture(period))
            self.assertEqual(result['status'],'diagnostic_observed_periodicity')
            self.assertLess(abs(result['period_image_pixels']-period)/period,.03)
            self.assertFalse(result['default_pitch_generated']);self.assertFalse(result['renderer_gate_modified'])

    def test_oblique_reference_and_quarter_turn_keep_period_units(self):
        arrays=self.fixture(12.5,37);first=observe(*arrays)
        moved=[np.rot90(a).copy() for a in arrays];moved[2]-=np.pi/2
        second=observe(*moved)
        self.assertIsNotNone(first['period_image_pixels']);self.assertIsNotNone(second['period_image_pixels'])
        self.assertLess(abs(first['period_image_pixels']-second['period_image_pixels'])/12.5,.03)

    def test_flat_and_noise_never_receive_default_pitch(self):
        raw,mask,angle=self.fixture()
        for value in [np.full_like(raw,128),np.random.default_rng(82).integers(0,256,raw.shape,np.uint8)]:
            result=observe(value,mask,angle);self.assertIsNone(result['period_image_pixels'])

    def test_unsupported_permission_rejects_and_inputs_stay_exact(self):
        raw,mask,angle=self.fixture();mask[:]=False;mask[240:256,240:256]=True
        before=[a.copy() for a in (raw,mask,angle)];result=observe(raw,mask,angle)
        self.assertIsNone(result['period_image_pixels'])
        for value,expected in zip((raw,mask,angle),before):np.testing.assert_array_equal(value,expected)

    def test_shape_dtype_and_nonfinite_orientation_contracts(self):
        raw,mask,angle=self.fixture()
        for arrays in [(raw[:32],mask,angle),(raw,mask.astype(float),angle),(raw,mask,np.full_like(angle,np.nan))]:
            with self.assertRaises(ValueError):observe(*arrays)


if __name__=='__main__':unittest.main()
