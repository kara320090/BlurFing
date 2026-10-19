import unittest

import numpy as np

from photo_visibility_spectral_probe_v1 import probe_level
from ridge_evidence_frontend import ridge_evidence


class SpectralProbeTests(unittest.TestCase):
    def test_low_contrast_periodic_signal_with_illumination_and_rotations(self):
        y,x=np.indices((160,192)); mask=np.ones(x.shape,bool)
        for angle in [0,30,75,120]:
            a=np.radians(angle); phase=x*np.cos(a)+y*np.sin(a)
            gray=np.clip(100+.1*x+.08*y+4*np.sin(2*np.pi*phase/8),0,255).astype(np.uint8)
            snapshot=gray.copy(); r=probe_level(gray,mask,512)
            self.assertTrue(r['candidate_signal_observed'],angle)
            self.assertEqual(r['automatic_visibility'],'uncertain')
            self.assertFalse(r['used_by_protection'])
            self.assertFalse(r['renderer_binding_allowed'])
            np.testing.assert_array_equal(gray,snapshot)
            self.assertEqual(ridge_evidence(gray,mask)[1]['status'],'ridge_evidence_insufficient')

    def test_flat_ramps_step_edge_and_noise_controls(self):
        y,x=np.indices((160,192));mask=np.ones(x.shape,bool)
        controls=[np.full(x.shape,128),70+.3*x+.2*y,np.where(x<96,90,170),
                  128+25*np.exp(-((x-96)/4)**2)]
        for seed in range(12):
            controls.append(128+np.random.default_rng(seed).normal(0,6,x.shape))
        for index,gray in enumerate(controls):
            image=np.clip(gray,0,255).astype(np.uint8)
            self.assertFalse(probe_level(image,mask,512)['candidate_signal_observed'],index)

    def test_outside_mask_stripes_and_tiny_roi_cannot_create_signal(self):
        y,x=np.indices((120,144));g=(128+40*np.sin(2*np.pi*x/8)).astype(np.uint8)
        mask=np.zeros(g.shape,bool);mask[32:90,48:100]=True;g[mask]=128
        self.assertFalse(probe_level(g,mask,512)['candidate_signal_observed'])
        self.assertFalse(probe_level(np.full((16,16),128,np.uint8),np.ones((16,16),bool),512)['candidate_signal_observed'])

    def test_deterministic_and_allocation_input_contract(self):
        y,x=np.indices((96,96));g=(128+4*np.sin(2*np.pi*x/8)).astype(np.uint8);m=np.ones(g.shape,bool)
        self.assertEqual(probe_level(g,m,512),probe_level(g,m,512))
        with self.assertRaises(ValueError):probe_level(g,m[:-1],512)
        with self.assertRaises(ValueError):probe_level(g,m,0)


if __name__=='__main__':unittest.main()
