import unittest
import numpy as np
from scipy.ndimage import gaussian_filter
from photo_visibility_spatial_probe_v6 import probe_level


class SpatialTests(unittest.TestCase):
    def test_rotated_weak_curved_ridges_with_crossing_crease(self):
        y, x = np.indices((160, 192)); mask = np.ones(x.shape, bool)
        for period in (3.5, 5.5, 8, 12):
            for angle in (0, 30, 75, 120):
                a = np.radians(angle)
                normal = x*np.cos(a)+y*np.sin(a)
                tangent = -x*np.sin(a)+y*np.cos(a)-80
                phase = normal+.0008*tangent*tangent
                image = np.clip(90+.2*x+.1*y+4*np.sin(2*np.pi*phase/period)-35*np.exp(-((y-80)/7)**2),0,255).astype(np.uint8)
                self.assertTrue(probe_level(image, mask, 512)['candidate_signal_observed'], (period, angle))

    def test_noise_edges_sparse_creases_do_not_supply_four_trains(self):
        y, x = np.indices((128, 160)); mask = np.ones(x.shape, bool)
        controls = [np.full(x.shape, 128), 60+.4*x+.2*y, np.where(x<80, 90, 170),
                    128-40*np.exp(-((x-80)/4)**2), 128-40*np.exp(-((x-80)/12)**2),
                    128-30*np.exp(-((x-50)/3)**2)-25*np.exp(-((x-110)/7)**2)]
        for seed in range(16):
            noise = np.random.default_rng(seed).normal(0,6,x.shape)
            controls.extend([128+noise, 128+gaussian_filter(noise,.8)])
        for i,g in enumerate(controls):
            self.assertFalse(probe_level(np.clip(g,0,255).astype(np.uint8),mask,512)['candidate_signal_observed'],i)

    def test_inside_positive_and_outside_texture_fractional_resize(self):
        y,x = np.indices((199,273)); mask = np.ones(x.shape,bool)
        gray = (128+10*np.sin(2*np.pi*x/14)).astype(np.uint8)
        self.assertTrue(probe_level(gray,mask,137)['candidate_signal_observed'])
        mask[:] = False; mask[20:180,30:240]=True; gray[mask]=128
        before=gray.copy()
        for side in (512,137,91):
            r=probe_level(gray,mask,side)
            self.assertFalse(r['candidate_signal_observed']); self.assertFalse(r['renderer_binding_allowed'])
            self.assertEqual(r['automatic_visibility'],'uncertain'); self.assertFalse(r['used_by_protection'])
        np.testing.assert_array_equal(gray,before)
        self.assertEqual(probe_level(gray,mask,137),probe_level(gray,mask,137))


if __name__ == '__main__': unittest.main()
