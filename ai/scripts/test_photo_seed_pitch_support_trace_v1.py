import sys,unittest
import cv2,numpy as np
from photo_seed_pitch_support_trace_v1 import SeedPitchTrace,profile_roi_weights,fixed_map_controls,seed_inside_working_pad
from contactless_ridge_pitch import estimate_ridge_pitch
from protect_visible_pad_checked_v2 import observed_seed_pitch


class TraceTests(unittest.TestCase):
    def test_nearest_full_support_can_still_read_unobserved_bilinear_neighbor(self):
        roi=np.zeros((10,10),bool);roi[:,1:]=True
        mx=np.full((1,2),.75,np.float32);my=np.full((1,2),3.5,np.float32)
        result=profile_roi_weights(roi,mx,my)
        self.assertEqual(result['nearest_coverage'],1.)
        self.assertEqual(result['mean_supported_bilinear_weight'],.75)
        self.assertEqual(result['samples_with_unsupported_neighbors'],2)

    def test_isolated_estimator_maps_and_actual_return_preserved(self):
        y,x=np.indices((512,512));roi=np.zeros((512,512),bool)
        for cy in [96,240]:
            for cx in [96,240,384]:roi[cy-24:cy+24,cx-24:cx+24]=True
        gray=np.rint(128+90*np.cos(2*np.pi*x/8)).astype(np.uint8);gray[roi]=128
        original=estimate_ridge_pitch(gray,roi);before=gray.copy(),roi.copy()
        with SeedPitchTrace() as trace:actual=estimate_ridge_pitch(gray,roi)
        self.assertEqual(actual,original);self.assertFalse(trace.errors)
        self.assertEqual(len(trace.estimates),1)
        periodic=[p for p in trace.estimates[0]['profiles'] if p['periodic_measurement']]
        self.assertEqual(len(periodic),6)
        for p in periodic:
            self.assertEqual(p['support']['mean_supported_bilinear_weight'],.75)
            controls=fixed_map_controls(gray,roi,p['mx'],p['my'])
            self.assertTrue(any(r['max_profile_change']>0 for r in controls))
        np.testing.assert_array_equal(gray,before[0]);np.testing.assert_array_equal(roi,before[1])

    def test_exact_frozen_seed_call_no_alias_rebinding(self):
        y,x=np.indices((512,512));gray=np.rint(128+70*np.cos(2*np.pi*x/16)).astype(np.uint8)
        rgb=np.repeat(gray[...,None],3,axis=2);box=[0,0,512,512]
        original=observed_seed_pitch(rgb,box);code=observed_seed_pitch.__code__
        with SeedPitchTrace() as trace:actual=observed_seed_pitch(rgb,box)
        self.assertIs(observed_seed_pitch.__code__,code);self.assertFalse(trace.errors)
        self.assertEqual(actual[:2],original[:2]);np.testing.assert_array_equal(actual[2],original[2])
        self.assertEqual(len(trace.seeds),1);self.assertTrue(trace.seeds[0]['completed'])
        self.assertTrue(trace.estimates)

    def test_profiler_restored_on_exception_and_existing_profiler_not_overwritten(self):
        previous=sys.getprofile()
        with self.assertRaisesRegex(RuntimeError,'test failure'):
            with SeedPitchTrace():raise RuntimeError('test failure')
        self.assertIs(sys.getprofile(),previous)
        existing=lambda *args:None
        try:
            sys.setprofile(existing)
            with self.assertRaisesRegex(RuntimeError,'existing_profiler_active'):
                with SeedPitchTrace():pass
            self.assertIs(sys.getprofile(),existing)
        finally:sys.setprofile(previous)

    def test_invalid_and_nonfinite_maps_rejected(self):
        roi=np.ones((10,10),bool);m=np.full((1,2),1,np.float32)
        with self.assertRaises(ValueError):profile_roi_weights(roi,m.astype(float),m)
        with self.assertRaises(ValueError):profile_roi_weights(roi,np.full_like(m,np.nan),m)
        image=np.zeros((10,10,3),np.uint8)
        self.assertTrue(seed_inside_working_pad(image,[0,0,10,10],roi))
        for box in [[10,0,12,2],[-2,0,2,2],[2,2,2,4],[False,0,2,2]]:
            self.assertIsNone(seed_inside_working_pad(image,box,roi))
        self.assertIsNone(seed_inside_working_pad(image,[0,0,2,2],roi.astype(np.uint8)))


if __name__=='__main__':unittest.main()
