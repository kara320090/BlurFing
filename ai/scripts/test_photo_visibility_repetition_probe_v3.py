import unittest
import numpy as np
from photo_visibility_fractional_recurrence_v3 import profile_recurrence
from photo_visibility_repetition_probe_v3 import probe_level
from photo_visibility_repetition_probe_v2 import _profile_recurrence as integer_recurrence


class FractionalRepetitionTests(unittest.TestCase):
    def test_fractional_periods_and_integer_regression(self):
        x=np.arange(56)
        for period in (3.3,3.5,3.7,4,4.5,5.5,6,8,12):
            for phase in (0,.7,1.5):
                p=128+5*np.sin(2*np.pi*x/period+phase)
                r=profile_recurrence(p,period)
                self.assertIsNotNone(r,(period,phase))
                self.assertLess(abs(r['period_pixels']-period)/period,.06)
        self.assertIsNone(integer_recurrence(128+5*np.sin(2*np.pi*x/3.5),3.5))

    def test_fractional_image_periods_rotated_with_macro_crease(self):
        y,x=np.indices((160,192));mask=np.ones(x.shape,bool)
        for period in (3.5,4.5,5.5,8):
            for angle in (0,30,75,120):
                a=np.radians(angle);phase=x*np.cos(a)+y*np.sin(a)
                g=np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*phase/period)
                          -35*np.exp(-((y-80)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(g,mask,512)['candidate_signal_observed'],(period,angle))

    def test_noise_edges_and_sparse_creases(self):
        y,x=np.indices((160,192));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<96,90,170),
                  128-40*np.exp(-((x-96)/4)**2),128-40*np.exp(-((x-96)/12)**2),
                  128-30*np.exp(-((x-64)/3)**2)-25*np.exp(-((x-127)/7)**2)]
        controls.extend(128+np.random.default_rng(seed).normal(0,6,x.shape) for seed in range(16))
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_resize_mask_and_output_contract(self):
        y,x=np.indices((199,273));g=(128+40*np.sin(2*np.pi*x/8)).astype(np.uint8)
        m=np.zeros(g.shape,bool);m[13:185,29:247]=True;g[m]=128;copy=g.copy()
        for side in (512,137,91):
            r=probe_level(g,m,side)
            self.assertFalse(r['candidate_signal_observed']);self.assertFalse(r['used_by_protection'])
            self.assertFalse(r['renderer_binding_allowed']);self.assertEqual(r['automatic_visibility'],'uncertain')
        np.testing.assert_array_equal(copy,g)
        self.assertEqual(probe_level(g,m,137),probe_level(g,m,137))


if __name__=='__main__':unittest.main()
