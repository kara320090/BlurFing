import unittest
import numpy as np
from scipy.ndimage import gaussian_filter
from photo_visibility_separated_probe_v7 import probe_level, bounded_agreement


class SeparatedTests(unittest.TestCase):
    def test_weak_curved_rotated_and_crossed_profiles(self):
        y, x = np.indices((128, 160)); mask = np.ones(x.shape, bool)
        for period in (3.5, 5.5, 8, 12):
            for angle in (0, 30, 75, 120):
                a = np.radians(angle)
                normal = x*np.cos(a)+y*np.sin(a)
                tangent = -x*np.sin(a)+y*np.cos(a)-64
                phase = normal+.0008*tangent*tangent
                gray = np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*phase/period)-35*np.exp(-((y-64)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(gray,mask,512)['candidate_signal_observed'],(period,angle))

    def test_bounded_alignment_cannot_skip_cycle(self):
        x = np.arange(56); a = np.sin(2*np.pi*x/8)
        b = np.sin(2*np.pi*(x+1)/8)
        r = bounded_agreement(a,b,8,16,64)
        self.assertGreater(r['correlation'],.99)
        self.assertEqual(abs(r['lag_pixels']),1)
        self.assertEqual(r['common_length'],55)
        self.assertLess(r['max_lag_pixels'],8/4)
        self.assertEqual(bounded_agreement(a,a,4,8,32)['max_lag_pixels'],0)

    def test_noise_sparse_creases_and_quantization(self):
        y,x=np.indices((128,160));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<80,90,170),
                  128-40*np.exp(-((x-80)/4)**2),128-40*np.exp(-((x-80)/12)**2),
                  128-30*np.exp(-((x-50)/3)**2)-25*np.exp(-((x-110)/7)**2)]
        for seed in range(16):
            noise=np.random.default_rng(seed).normal(0,6,x.shape)
            controls.extend([128+noise,128+gaussian_filter(noise,.8)])
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_mask_safety_resize_determinism_and_no_protection(self):
        y,x=np.indices((199,273));m=np.ones(x.shape,bool)
        g=(128+10*np.sin(2*np.pi*x/14)).astype(np.uint8)
        self.assertTrue(probe_level(g,m,137)['candidate_signal_observed'])
        m[:]=False;m[20:180,30:240]=True;g[m]=128;before=g.copy()
        for side in (512,137,91):
            r=probe_level(g,m,side)
            self.assertFalse(r['candidate_signal_observed']);self.assertFalse(r['used_by_protection'])
            self.assertFalse(r['renderer_binding_allowed']);self.assertEqual(r['automatic_visibility'],'uncertain')
            self.assertFalse(r['absence_inferred_from_failure'])
        np.testing.assert_array_equal(g,before)
        self.assertEqual(probe_level(g,m,137),probe_level(g,m,137))
        for side in (True,0,-1,3.5):
            with self.assertRaises(ValueError):probe_level(g,m,side)


if __name__=='__main__':unittest.main()
