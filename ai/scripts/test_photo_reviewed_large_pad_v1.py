import unittest
from unittest.mock import patch
import numpy as np
import photo_reviewed_large_pad_v1 as large
import photo_visibility_reviewed_apply_v1 as reviewed


class LargePadTests(unittest.TestCase):
    def test_working_shape_is_integer_bounded_and_never_upscales(self):
        for h,w in ((3000,4000),(7,10000),(3001,4001),(100,100)):
            shape,divisor=large.working_shape(h,w)
            self.assertLessEqual(shape[0]*shape[1],large.MAX_REGION_PIXELS)
            self.assertLessEqual(shape[0],h);self.assertLessEqual(shape[1],w)
            self.assertEqual(divisor & (divisor-1),0)
        with self.assertRaises(ValueError):large.working_shape(40000,1)

    def test_resize_never_samples_unpermitted_pixels_in_either_direction(self):
        y,x=np.indices((131,169));mask=((x-83)**2+(y-64)**2)<58**2
        a=np.zeros((*mask.shape,3),np.uint8);a[mask]=[185,123,90]
        b=a.copy();b[~mask]=255
        down,coverage=large.normalized_resize(a,mask,(66,85))
        other,_=large.normalized_resize(b,mask,(66,85))
        np.testing.assert_array_equal(down,other)
        changed=down.copy();changed[coverage==0]=[0,255,71]
        up,weights=large.normalized_resize(down,coverage>0,mask.shape)
        altered,_=large.normalized_resize(changed,coverage>0,mask.shape)
        np.testing.assert_array_equal(up,altered)
        self.assertTrue(np.all(weights[mask]>0))
        np.testing.assert_array_equal(up[mask],np.broadcast_to([185,123,90],up[mask].shape))

    def test_real_V19_scaled_roundtrip_determinism_and_native_permission(self):
        y,x=np.indices((320,320));mask=((x-160)/110)**2+((y-160)/140)**2<1
        rgb=np.clip(np.array([182,132,110])[None,None,:]+3*np.sin(x[:,:,None]*2*np.pi/8),0,255).astype(np.uint8)
        labels=mask.astype(np.uint16)
        review=dict(version='explicit_visibility_review_v1',review_origin='human_confirmed',all_regions_reviewed=True,
            coordinate_system='upright_native_pixels',RGB_sha256=reviewed.pixels(rgb),labels_sha256=reviewed.pixels(labels),
            regions=[dict(region_id=1,decision='visible')])
        with patch.object(reviewed,'MAX_REGION_PIXELS',30000),patch.object(large,'MAX_REGION_PIXELS',30000):
            a,applied,report=reviewed.apply_reviewed(rgb,labels,review,seed=51)
            b,_,_=reviewed.apply_reviewed(rgb,labels,review,seed=51)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(applied,mask)
        np.testing.assert_array_equal(a[~mask],rgb[~mask])
        self.assertEqual(report['applied_region_count'],1)
        self.assertEqual(report['working_resolution_render_region_count'],1)
        region=report['renderer']['regions'][0]
        self.assertEqual(region['pixels'],int(mask.sum()))
        self.assertLess(region['working_pixels'],region['pixels'])
        self.assertFalse(region['working_resolution_adapter']['native_texture_resolution_verified'])
        self.assertFalse(report['privacy_validated'])


if __name__=='__main__':unittest.main()
