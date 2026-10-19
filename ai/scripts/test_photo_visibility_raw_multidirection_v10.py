import unittest
import numpy as np
from scipy.ndimage import gaussian_filter
from photo_visibility_raw_multidirection_v10 import peak_train,probe_level
from photo_visibility_local_run_probe_v8 import peak_train as residual_train


class RawMultidirectionTests(unittest.TestCase):
    def test_monotonic_wavy_ramp_is_not_four_raw_crests(self):
        x=np.arange(56,dtype=float)
        period=4.;amplitude=.8;slope=1.05*2*np.pi*amplitude/period
        raw=30+slope*x+amplitude*np.sin(2*np.pi*x/period)
        self.assertTrue(np.all(np.diff(raw)>0))
        self.assertIsNotNone(residual_train(raw,period));self.assertIsNone(peak_train(raw,period))
        self.assertIsNotNone(peak_train(70+.2*x+4*np.sin(2*np.pi*x/8),8))

    def test_actual_local_train_and_minimum_cycles(self):
        x=np.arange(56,dtype=float)
        raw=128+sum(6*np.exp(-((x-c)/1.2)**2) for c in (8,16,24,32,48,53))
        result=peak_train(raw,8)
        self.assertIsNotNone(result);self.assertGreaterEqual(result['peak_count'],4)
        self.assertFalse(result['whole_profile_train'])
        for centers in ((8,16,24),(8,24,40)):
            self.assertIsNone(peak_train(128+sum(6*np.exp(-((x-c)/1.2)**2) for c in centers),8))

    def test_weak_curved_rotated_with_crossing_crease(self):
        y,x=np.indices((128,160));mask=np.ones(x.shape,bool)
        for period in (3.5,5.5,8,12):
            for angle in (0,30,75,120):
                a=np.radians(angle);u=x*np.cos(a)+y*np.sin(a);v=-x*np.sin(a)+y*np.cos(a)-64
                gray=np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*(u+.0008*v*v)/period)-35*np.exp(-((y-64)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(gray,mask,512)['candidate_signal_observed'],(period,angle))

    def test_noise_and_nonperiodic_controls(self):
        y,x=np.indices((128,160));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<80,90,170),
                  128-40*np.exp(-((x-80)/4)**2),128-40*np.exp(-((x-80)/12)**2),
                  128-30*np.exp(-((x-50)/3)**2)-25*np.exp(-((x-110)/7)**2)]
        for seed in range(16):
            noise=np.random.default_rng(seed).normal(0,6,x.shape)
            controls.extend([128+noise,128+gaussian_filter(noise,.8)])
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_mask_resize_determinism_and_observation_only(self):
        y,x=np.indices((199,273));m=np.ones(x.shape,bool);g=(128+10*np.sin(2*np.pi*x/14)).astype(np.uint8)
        self.assertTrue(probe_level(g,m,137)['candidate_signal_observed'])
        m[:]=False;m[20:180,30:240]=True;g[m]=128;before=g.copy()
        for side in (512,137,91):
            r=probe_level(g,m,side);self.assertFalse(r['candidate_signal_observed'])
            self.assertFalse(r['used_by_protection']);self.assertFalse(r['renderer_binding_allowed'])
            self.assertEqual(r['automatic_visibility'],'uncertain');self.assertFalse(r['absence_inferred_from_failure'])
        np.testing.assert_array_equal(g,before)
        self.assertEqual(probe_level(g,m,137),probe_level(g,m,137))
        for invalid in (False,0,-1,3.5):
            with self.assertRaises(ValueError):probe_level(g,m,invalid)

if __name__=='__main__':unittest.main()
