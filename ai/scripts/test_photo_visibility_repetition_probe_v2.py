import unittest
import numpy as np
from photo_visibility_repetition_probe_v2 import probe_level


class RepetitionProbeTests(unittest.TestCase):
    def test_low_contrast_ridges_across_illumination_and_macro_crease(self):
        y,x=np.indices((160,192));mask=np.ones(x.shape,bool)
        for period in (4,8,12):
            for angle in (0,30,75,120):
                a=np.radians(angle);phase=x*np.cos(a)+y*np.sin(a)
                g=np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*phase/period)
                          -35*np.exp(-((y-80)/7)**2),0,255).astype(np.uint8)
                result=probe_level(g,mask,512)
                self.assertTrue(result['candidate_signal_observed'],(period,angle))
                self.assertEqual(result['automatic_visibility'],'uncertain')
                self.assertFalse(result['renderer_binding_allowed'])

    def test_nonperiodic_controls(self):
        y,x=np.indices((160,192));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),60+.4*x+.2*y,np.where(x<96,90,170),
                  128-40*np.exp(-((x-96)/4)**2),128-40*np.exp(-((x-96)/12)**2),
                  128-30*np.exp(-((x-64)/3)**2)-25*np.exp(-((x-127)/7)**2)]
        controls.extend(128+np.random.default_rng(seed).normal(0,6,x.shape) for seed in range(16))
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_background_does_not_supply_recurrence_during_resize(self):
        y,x=np.indices((199,273));g=(128+40*np.sin(2*np.pi*x/8)).astype(np.uint8)
        mask=np.zeros(g.shape,bool);mask[13:185,29:247]=True;g[mask]=128
        for side in (512,137,91):
            self.assertFalse(probe_level(g,mask,side)['candidate_signal_observed'])

    def test_inputs_reproducibility_small_roi_and_no_mutation(self):
        y,x=np.indices((96,112));g=(128+4*np.sin(2*np.pi*x/8)).astype(np.uint8);m=np.ones(g.shape,bool)
        original=g.copy();r=probe_level(g,m,512)
        self.assertEqual(r,probe_level(g,m,512));np.testing.assert_array_equal(g,original)
        self.assertFalse(probe_level(g[:16,:16],m[:16,:16],512)['candidate_signal_observed'])
        self.assertFalse(r['used_by_protection']);self.assertFalse(r['absence_inferred_from_failure'])
        with self.assertRaises(ValueError):probe_level(g,m[:-1],512)
        with self.assertRaises(ValueError):probe_level(g,m,False)


if __name__=='__main__':unittest.main()
