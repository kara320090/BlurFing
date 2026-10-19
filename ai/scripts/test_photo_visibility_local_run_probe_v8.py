import unittest
import numpy as np
from scipy.ndimage import gaussian_filter
from photo_visibility_local_run_probe_v8 import peak_train,probe_level
from photo_visibility_peak_train_probe_v4 import peak_train as old_train


class LocalRunTests(unittest.TestCase):
    def test_peripheral_irregularities_do_not_erase_local_four_crests(self):
        x=np.arange(56,dtype=float)
        profile=128+sum(6*np.exp(-((x-c)/1.2)**2) for c in (8,16,24,32,48,53))
        self.assertIsNone(old_train(profile,8))
        result=peak_train(profile,8)
        self.assertIsNotNone(result);self.assertGreaterEqual(result['peak_count'],4)
        self.assertFalse(result['whole_profile_train'])
        for centers in ((8,16,24),(8,24,40)):
            p=128+sum(6*np.exp(-((x-c)/1.2)**2) for c in centers)
            self.assertIsNone(peak_train(p,8))

    def test_already_valid_raw_train_unchanged(self):
        x=np.arange(56,dtype=float)
        for period in (3.5,5.5,8,12):
            for phase in (0.,.6,1.4):
                p=128+5*np.sin(2*np.pi*x/period+phase)
                old=old_train(p,period);new=peak_train(p,period)
                self.assertIsNotNone(old);self.assertIsNotNone(new)
                for key in ('period_pixels','peak_count','spacing_cv'):self.assertEqual(old[key],new[key])
                np.testing.assert_array_equal(old['residual'],new['residual'])
                self.assertTrue(new['whole_profile_train'])

    def test_noise_edges_and_sparse_creases(self):
        y,x=np.indices((128,160));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<80,90,170),
                  128-40*np.exp(-((x-80)/4)**2),128-40*np.exp(-((x-80)/12)**2),
                  128-30*np.exp(-((x-50)/3)**2)-25*np.exp(-((x-110)/7)**2)]
        for seed in range(16):
            noise=np.random.default_rng(seed).normal(0,6,x.shape)
            controls.extend([128+noise,128+gaussian_filter(noise,.8)])
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_weak_rotated_ridges(self):
        y,x=np.indices((128,160));mask=np.ones(x.shape,bool)
        for period in (3.5,5.5,8,12):
            for angle in (0,30,75,120):
                a=np.radians(angle);u=x*np.cos(a)+y*np.sin(a);v=-x*np.sin(a)+y*np.cos(a)-64
                g=np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*(u+.0008*v*v)/period)-35*np.exp(-((y-64)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(g,mask,512)['candidate_signal_observed'],(period,angle))

    def test_outside_pixels_resize_and_diagnostic_contract(self):
        y,x=np.indices((199,273));m=np.ones(x.shape,bool);g=(128+10*np.sin(2*np.pi*x/14)).astype(np.uint8)
        self.assertTrue(probe_level(g,m,137)['candidate_signal_observed'])
        m[:]=False;m[20:180,30:240]=True;g[m]=128;before=g.copy()
        for side in (512,137,91):
            r=probe_level(g,m,side);self.assertFalse(r['candidate_signal_observed'])
            self.assertFalse(r['used_by_protection']);self.assertFalse(r['renderer_binding_allowed'])
            self.assertEqual(r['automatic_visibility'],'uncertain');self.assertFalse(r['absence_inferred_from_failure'])
        np.testing.assert_array_equal(g,before)
        self.assertEqual(probe_level(g,m,137),probe_level(g,m,137))
        with self.assertRaises(ValueError):probe_level(g,m,False)


if __name__=='__main__':unittest.main()
