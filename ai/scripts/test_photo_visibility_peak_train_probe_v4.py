import unittest
import numpy as np
from photo_visibility_peak_train_probe_v4 import probe_level,peak_train


class PeakTrainTests(unittest.TestCase):
    def test_weak_rotated_fractional_ridges_and_macro_crease(self):
        y,x=np.indices((160,192));m=np.ones(x.shape,bool)
        for period in (3.5,5.5,8,12):
            for angle in (0,30,75,120):
                a=np.radians(angle);phase=x*np.cos(a)+y*np.sin(a)
                g=np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*phase/period)-35*np.exp(-((y-80)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(g,m,512)['candidate_signal_observed'],(period,angle))

    def test_variable_spacing_raw_profile(self):
        # Local frequencies .0802..1682 stay inside the declared .065..30 band.
        x=np.arange(56);phase=x/8+.0008*(x-28)**2
        r=peak_train(128+5*np.sin(2*np.pi*phase),8)
        self.assertIsNotNone(r);self.assertGreaterEqual(r['peak_count'],4)
        # This much stronger chirp spans .041..206 (24..5 px periods), outside
        # the contract and inconsistent with a single proposed 8 px period.
        extreme=x/8+.0015*(x-28)**2
        self.assertIsNone(peak_train(128+5*np.sin(2*np.pi*extreme),8))

    def test_nonperiodic_and_blurred_noise_controls(self):
        from scipy.ndimage import gaussian_filter
        y,x=np.indices((160,192));m=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<96,90,170),
                  128-40*np.exp(-((x-96)/4)**2),128-40*np.exp(-((x-96)/12)**2),
                  128-30*np.exp(-((x-64)/3)**2)-25*np.exp(-((x-127)/7)**2)]
        for seed in range(16):
            noise=np.random.default_rng(seed).normal(0,6,x.shape)
            controls.extend([128+noise,128+gaussian_filter(noise,.8)])
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),m,512)['candidate_signal_observed'],i)

    def test_mask_resize_determinism_and_observation_only(self):
        y,x=np.indices((199,273));g=(128+40*np.sin(2*np.pi*x/8)).astype(np.uint8);m=np.zeros(g.shape,bool);m[13:185,29:247]=True;g[m]=128
        copy=g.copy()
        for side in (512,137,91):
            r=probe_level(g,m,side);self.assertFalse(r['candidate_signal_observed']);self.assertFalse(r['used_by_protection'])
            self.assertFalse(r['renderer_binding_allowed']);self.assertEqual(r['automatic_visibility'],'uncertain')
        np.testing.assert_array_equal(g,copy);self.assertEqual(probe_level(g,m,137),probe_level(g,m,137))
        with self.assertRaises(ValueError):probe_level(g,m,0)


if __name__=='__main__':unittest.main()
