import unittest
from unittest.mock import patch
import numpy as np
import photo_local_periodicity_v1 as local


def waves(shape=(196,250),period=16,angle=0):
    y,x=np.indices(shape);theta=np.deg2rad(angle)
    return np.rint(127+70*np.cos(2*np.pi*(x*np.cos(theta)+y*np.sin(theta))/period)).astype(np.uint8)


class PeriodicityTests(unittest.TestCase):
    def test_small_ROI_period_and_five_directions(self):
        for angle in [0,30,45,90,135]:
            gray=waves(angle=angle);result=local.observe(gray,np.ones_like(gray,bool))
            self.assertEqual(result['status'],'observed_local_periodicity')
            self.assertGreaterEqual(result['accepted_patch_count'],6)
            self.assertAlmostEqual(result['periodic_spacing_native_pixels'],16.,delta=.5)
            self.assertFalse(result['renderer_binding_allowed']);self.assertEqual(result['anatomy_classification'],'unknown')

    def test_flat_noise_and_tiny_geometry_do_not_generate_spacing(self):
        rng=np.random.default_rng(8)
        for gray in [np.full((196,250),128,np.uint8),rng.integers(0,256,(196,250),dtype=np.uint8),waves((30,60))]:
            result=local.observe(gray,np.ones_like(gray,bool))
            self.assertIsNone(result['periodic_spacing_native_pixels'])
            self.assertFalse(result['support_mask'].any())
        self.assertEqual(local.observe(waves((30,60)),np.ones((30,60),bool))['status'],'not_testable_geometry')

    def test_missing_profile_support_does_not_read_background_as_target(self):
        mask=np.zeros((512,512),bool)
        for y in [100,228]:
            for x in [100,228,356]:mask[y-24:y+24,x-24:x+24]=True
        for period in [6,8]:
            gray=waves(mask.shape,period=period);gray[mask]=128
            result=local.observe(gray,mask)
            self.assertEqual(result['stage_counts']['central_mask'],6)
            self.assertEqual(result['stage_counts']['orientation'],6)
            self.assertEqual(result['stage_counts']['profile_mask'],0)
            self.assertIsNone(result['periodic_spacing_native_pixels']);self.assertFalse(result['support_mask'].any())

    def test_two_scales_remain_local_without_inventing_global_pitch(self):
        gray=waves((196,500),period=8);gray[:,250:]=waves((196,250),period=16)
        result=local.observe(gray,np.ones_like(gray,bool))
        self.assertGreaterEqual(result['accepted_patch_count'],6)
        self.assertEqual(result['status'],'local_periodicity_unstable')
        self.assertIsNone(result['periodic_spacing_native_pixels']);self.assertFalse(result['global_orientation_assumed'])

    def test_repeat_and_input_mask_preservation(self):
        gray=waves();mask=np.ones_like(gray,bool);mask[:20]=False;before=gray.copy(),mask.copy()
        a=local.observe(gray,mask);b=local.observe(gray,mask)
        np.testing.assert_array_equal(a['support_mask'],b['support_mask'])
        self.assertEqual({k:v for k,v in a.items() if k!='support_mask'},{k:v for k,v in b.items() if k!='support_mask'})
        self.assertFalse((a['support_mask']&~mask).any())
        np.testing.assert_array_equal(gray,before[0]);np.testing.assert_array_equal(mask,before[1])

    def test_input_and_resource_preflight(self):
        gray=waves();mask=np.ones_like(gray,bool)
        with self.assertRaises(ValueError):local.observe(gray.astype(float),mask)
        with self.assertRaises(ValueError):local.observe(gray,mask.astype(np.uint8))
        huge=np.broadcast_to(np.array(128,np.uint8),(40000,1))
        with patch.object(local.hashlib,'sha256',side_effect=AssertionError('preflight first')):
            with self.assertRaisesRegex(ValueError,'adapter_memory_limit_exceeded'):
                local.observe(huge,np.ones((40000,1),bool))


if __name__=='__main__':unittest.main()
