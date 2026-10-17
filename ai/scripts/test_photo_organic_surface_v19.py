import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cv2,numpy as np
from scipy import ndimage
from skimage.morphology import skeletonize
from PIL import Image
from photo_organic_surface_v19 import irregular_coordinates,interrupted_profile,contour_continuation,guard_contour_correction


class OrganicSurfaceTests(unittest.TestCase):
    def test_local_coordinate_map_stays_unfolded(self):
        dy,dx,meta=irregular_coordinates((512,512),8.,91)
        ay,ax=np.gradient(dy);by,bx=np.gradient(dx)
        norm=np.sqrt(ay*ay+ax*ax+by*by+bx*bx)
        self.assertLessEqual(float(norm.max()),.320001)
        determinant=(1+ay)*(1+bx)-ax*by
        self.assertGreater(float(determinant.min()),.45)
        self.assertGreater(float(np.std(ax)),.01)
        json.dumps(meta)

    def test_generated_ridge_endings_increase_without_source_or_donor(self):
        y,x=np.mgrid[:512,:512];profile=np.cos(y*2*np.pi/8).astype(np.float32)
        mask=np.ones(profile.shape,bool)
        a,meta=interrupted_profile(profile,mask,8.,31)
        b,_=interrupted_profile(profile,mask,8.,31)
        np.testing.assert_array_equal(a,b)
        def endings(field):
            skeleton=skeletonize(field>0);neighbors=ndimage.convolve(skeleton.astype(np.uint8),np.ones((3,3),np.uint8))-skeleton
            return int((skeleton & (neighbors==1))[32:-32,32:-32].sum())
        self.assertGreater(endings(a),endings(profile)+8)
        self.assertGreater(meta['generated_interruptions'],5)
        self.assertFalse(meta['original_ridge_phase_input']);self.assertFalse(meta['other_finger_donor'])

    def test_coarse_contour_correction_reduces_known_seam_without_overshoot(self):
        y,x=np.mgrid[:224,:256];local=np.ones(x.shape,bool)
        truth=np.column_stack([160+.04*x.ravel(),130+.03*x.ravel(),120+.02*x.ravel()])
        source=np.clip(truth+3*np.sin(y.ravel()*2*np.pi/9)[:,None],0,255).astype(np.uint8)
        generated=truth+np.array([9.,7.,5.])+2*np.sin(x.ravel()*2*np.pi/11)[:,None]
        corrected,meta=contour_continuation(generated,source,local,224.)
        d=ndimage.distance_transform_edt(np.pad(local,1))[1:-1,1:-1].ravel()
        edge=d<=3;deep=d>=meta['transition_width']+2
        self.assertTrue(meta['applied']);self.assertFalse(meta['source_outside_permission_used'])
        self.assertLess(np.abs(corrected[edge]-truth[edge]).mean(),np.abs(generated[edge]-truth[edge]).mean()*.5)
        self.assertLessEqual(float(np.abs(corrected-generated).max()),16.00001)
        np.testing.assert_array_equal(corrected[deep],generated[deep]);json.dumps(meta)

    def test_actual_saved_RGB_accepted_native_seed_and_fresh_output(self):
        from replace_photo_synthetic_v1 import run
        from test_photo_synthetic_replacement_v1 import SyntheticReplacementTests
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            source,cache,rgb,mask,accepted,native,_,icc=SyntheticReplacementTests().cached(root,accepted=True)
            a,meta=run(source,cache,root/'v19',renderer='v19',seed=71)
            b,_=run(source,cache,root/'replay',renderer='v19',seed=71)
            np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(a[accepted],native[accepted])
            np.testing.assert_array_equal(a[~mask],rgb[~mask])
            with Image.open(root/'v19/synthetic.png') as im:
                np.testing.assert_array_equal(a,np.array(im));self.assertEqual(im.info['icc_profile'],icc)
                self.assertEqual(im.getexif()[274],6)
            self.assertEqual(meta['synthetic_renderer'],'v19');self.assertFalse(meta['production_approved'])
            with self.assertRaises(FileExistsError):run(source,cache,root/'v19',renderer='v19')

    def test_boundary_guard_rejects_a_worse_coarse_mixture_after_RGB8_rounding(self):
        y,x=np.mgrid[:160,:192];local=np.ones(x.shape,bool)
        source=np.repeat(np.where((x.ravel()+y.ravel())%2,180.,120.)[:,None],3,axis=1)
        generated=np.full(source.shape,150.)
        chosen,meta=guard_contour_correction(generated,generated+10,source,local)
        np.testing.assert_array_equal(chosen,generated);self.assertFalse(meta['accepted'])
        self.assertGreater(meta['proposed_RGB_error'],meta['before_RGB_error'])
        self.assertTrue(meta['actual_RGB8_rounding_used'])
        _,rounding=guard_contour_correction(generated,generated+.3,source,local)
        self.assertFalse(rounding['accepted'])

    def test_translation_and_background_do_not_change_generated_mask(self):
        from photo_synthetic_replacement_v19 import render
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture();a,_=render(rgb,mask,labels,seed=91)
        shifted=np.pad(rgb,((9,0),(19,0),(0,0)));m=np.pad(mask,((9,0),(19,0)))
        shifted[~m]=[0,255,0];b,_=render(shifted,m,m.astype(np.uint16),seed=91)
        np.testing.assert_array_equal(a[mask],b[m]);np.testing.assert_array_equal(b[~m],shifted[~m])

    def test_fixed_coarse_observers_do_not_hide_original_RGB_residual(self):
        import photo_synthetic_replacement_v19 as module
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb,mask,labels,_=SyntheticV2Tests().fixture();changed=rgb.copy()
        changed[mask]=np.random.default_rng(8).integers(0,256,(mask.sum(),3),dtype=np.uint8)
        base=np.full((mask.sum(),3),150.)
        with patch.object(module,'photographic_skin',return_value=(base,{'macro_creases':{'curves':[]}})), \
             patch.object(module,'boundary_ribbon',side_effect=lambda base,*args:(base,{})), \
             patch('photo_synthetic_replacement_v10.native_style',return_value=(np.ones((1,1,4)),{})), \
             patch.object(module,'observe',return_value=(np.ones((1,1,4)),{})), \
             patch.object(module,'contour_continuation',side_effect=lambda values,*args:(values,{})):
            a,_=module.render(rgb,mask,labels,seed=91);b,_=module.render(changed,mask,labels,seed=91)
        np.testing.assert_array_equal(a[mask],b[mask])

    def test_resource_and_nonfinite_errors_fail_before_filtering(self):
        huge=np.broadcast_to(np.bool_(True),(8192,8192))
        with patch('photo_organic_surface_v19.ndimage.distance_transform_edt',side_effect=AssertionError('allocation')):
            with self.assertRaises(ValueError):contour_continuation(np.ones((1,3)),np.ones((1,3)),huge,1.)
        with self.assertRaises(ValueError):interrupted_profile(np.full((512,512),np.nan),np.ones((512,512),bool),8.,1)

    def test_empty_mask_keeps_RGB_and_does_not_claim_naturalness(self):
        from photo_synthetic_replacement_v19 import render
        rgb=np.full((40,40,3),150,np.uint8);mask=np.zeros((40,40),bool)
        result,meta=render(rgb,mask,mask.astype(np.uint16),seed=71)
        np.testing.assert_array_equal(result,rgb);self.assertEqual(meta['replacement_regions'],0)
        self.assertFalse(meta['natural_appearance_validated'])


if __name__=='__main__':
    cv2.setNumThreads(4);unittest.main()
