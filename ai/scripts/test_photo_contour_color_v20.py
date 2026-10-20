import unittest
from unittest.mock import patch
import numpy as np
from scipy import ndimage
from photo_contour_color_v20 import contour_color
from photo_organic_surface_v19 import contour_continuation


class ContourColorTests(unittest.TestCase):
    def fixture(self):
        y,x=np.mgrid[:224,:256]
        mask=np.ones(x.shape,bool)
        truth=np.column_stack([170+.03*x.ravel(),140+.02*x.ravel(),130+.01*x.ravel()])
        source=np.floor(truth+2*np.cos(y.ravel()*2*np.pi/9)[:,None]).astype(np.uint8)
        generated=truth-np.array([58.,43.,32.])+2*np.sin(x.ravel()*2*np.pi/11)[:,None]
        return mask,truth,source,generated

    def test_fixed_cap_prevents_coarse_recovery_candidate_recovers(self):
        mask,truth,source,generated=self.fixture()
        old,old_meta=contour_continuation(generated,source,mask,224.)
        new,meta=contour_color(generated,source,mask,224.)
        d=ndimage.distance_transform_edt(np.pad(mask,1))[1:-1,1:-1].ravel()
        self.assertTrue(meta['applied'])
        self.assertGreater(meta['observed_maximum_absolute_correction'],40)
        self.assertLess(abs(new[d<=3]-truth[d<=3]).mean(),abs(old[d<=3]-truth[d<=3]).mean()*.25)
        np.testing.assert_array_equal(new[d>meta['transition_width']+1],generated[d>meta['transition_width']+1])
        self.assertFalse(meta['mask_geometry_changed'])

    def test_deterministic_and_input_immutable(self):
        mask,truth,source,generated=self.fixture()
        original=[x.copy() for x in (mask,source,generated)]
        a,ma=contour_color(generated,source,mask,224.)
        b,mb=contour_color(generated,source,mask,224.)
        np.testing.assert_array_equal(a,b);self.assertEqual(ma,mb)
        for before,after in zip(original,(mask,source,generated)):np.testing.assert_array_equal(before,after)
        self.assertGreaterEqual(a.min(),0);self.assertLessEqual(a.max(),255)

    def test_no_new_correction_when_coarse_color_is_already_right(self):
        mask,truth,source,generated=self.fixture()
        result,meta=contour_color(source.astype(float),source,mask,224.)
        np.testing.assert_array_equal(result,source)
        self.assertFalse(meta['applied'])

    def test_small_support_and_invalid_geometry(self):
        result,meta=contour_color(np.full((16,3),150.),np.full((16,3),160,np.uint8),np.ones((4,4),bool),4.)
        self.assertFalse(meta['applied']);self.assertEqual(meta['reason'],'insufficient_coarse_support')
        huge=np.broadcast_to(True,(8192,8192))
        with patch('photo_contour_color_v20.ndimage.distance_transform_edt',side_effect=AssertionError('allocation')):
            with self.assertRaises(ValueError):contour_color(np.ones((1,3)),np.ones((1,3)),huge,1.)
        with self.assertRaises(ValueError):contour_color(np.full((16,3),np.nan),np.ones((16,3)),np.ones((4,4),bool),4.)


if __name__=='__main__':unittest.main()
