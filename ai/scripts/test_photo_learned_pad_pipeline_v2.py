import unittest
from unittest.mock import patch
import cv2
import numpy as np
import photo_learned_pad_pipeline_v2 as local
from photo_region_scale_plan_v1 import plan_region_scales


class BodyLocalTests(unittest.TestCase):
    def setUp(self):
        y,x=np.indices((90,120));self.rgb=np.stack([y+x,y*2,x],2).astype(np.uint8)
        self.owner=np.zeros((90,120),bool);self.owner[20:75,30:90]=True
        self.mask=np.zeros_like(self.owner);self.mask[25:45,40:65]=True
        self.gray=cv2.cvtColor(self.rgb,cv2.COLOR_RGB2GRAY);self.sha='0'*64
        self.association=dict(axis_native_yx=[.6,.8],candidate_id='body-0001-part-0001')

    def test_complete_body_real_context_and_parent_coordinate_mapping(self):
        rgb,mask,body,identity=local.body_crop(self.rgb,self.mask,self.owner,6,self.sha)
        a,b,c,d=identity['bbox_encoded_original']
        np.testing.assert_array_equal(rgb,self.rgb[b:d,a:c]);self.assertEqual(body.sum(),self.owner.sum())
        self.assertEqual(mask.sum(),self.mask.sum());self.assertFalse(body[0].any());self.assertFalse(body[-1].any())
        restored=np.zeros_like(self.mask);restored[b:d,a:c]=mask;np.testing.assert_array_equal(restored,self.mask)
        self.assertNotEqual(identity['virtual_source_sha256'],self.sha);self.assertEqual(identity['context_halo_native'],2)

    def test_source_frame_clipping_never_invents_body_context(self):
        owner=self.owner.copy();owner[:21,30:90]=True
        rgb,mask,body,identity=local.body_crop(self.rgb,self.mask,owner,1,self.sha)
        self.assertEqual(identity['bbox_encoded_original'][1],0);self.assertTrue(identity['source_frame_clipped'])
        self.assertTrue(body[0].any());np.testing.assert_array_equal(rgb[0],self.rgb[0,28:92])

    def test_downscale_retains_real_source_context_in_working_pixels(self):
        rgb,mask,body,identity=local.body_crop(self.rgb,self.mask,self.owner,1,self.sha,.25)
        self.assertEqual(identity['context_halo_native'],8)
        resized=cv2.resize(body.astype(np.uint8),(round(body.shape[1]*.25),round(body.shape[0]*.25)),interpolation=cv2.INTER_NEAREST)
        self.assertFalse(resized[0].any());self.assertFalse(resized[-1].any());self.assertFalse(resized[:,0].any())

    def test_full_photo_resource_reject_can_have_bounded_complete_body_plan(self):
        rgb=np.zeros((2048,2048,3),np.uint8);owner=np.zeros((2048,2048),bool);owner[700:1000,800:1000]=True
        mask=np.zeros_like(owner);mask[730:850,840:940]=True;gray=np.zeros(mask.shape,np.uint8)
        full=plan_region_scales(mask)['regions'][0];self.assertEqual(full['status'],'rejected')
        with patch.object(local.base.shared,'prepare_region',return_value=(None,dict(reject_reason='pitch_unobserved'))):
            artifact,geometry,plan,render=local.prepare_scoped_region(rgb,gray,mask,owner,1,self.sha,full,self.association)
        self.assertEqual(plan['status'],'planned');self.assertEqual(plan['observed_native_diameter'],full['observed_native_diameter'])
        self.assertLess(np.prod(plan['working_shape']),32*1024**2);self.assertIsNone(artifact)

    def scoped(self,orientation):
        full=plan_region_scales(self.mask)['regions'][0]
        with (patch.object(local.base.shared,'observed_seed_pitch',return_value=(8.,{},None)),
              patch.object(local.base.shared,'ridge_evidence',return_value=(None,dict(credible_fraction=.5)))):
            return local.prepare_scoped_region(self.rgb,self.gray,self.mask,self.owner,orientation,self.sha,full,self.association)

    def test_all_EXIF_axes_and_global_reconstruction_preserve_exterior(self):
        for orientation in range(1,9):
            artifact,geometry,plan,render=self.scoped(orientation)
            identity=geometry['scope'];a,b,c,d=identity['bbox_encoded_original'];crop=self.rgb[b:d,a:c];native=self.mask[b:d,a:c]
            upright=local.base.shared.orient(crop,orientation);shape=artifact['working_shape']
            expected=local.base.shared.orient_axis(self.association['axis_native_yx'],orientation,
                [shape[0]/upright.shape[0],shape[1]/upright.shape[1]])
            np.testing.assert_allclose(geometry['axis_working_yx'],expected)
            self.assertEqual(artifact['source_sha256'],identity['virtual_source_sha256'])
            metadata=geometry['virtual_ROI_metadata'];self.assertEqual(metadata['coordinate_system'],'encoded_virtual_crop_pixels')
            self.assertEqual(metadata['bbox_parent_encoded_original'],[40,25,65,45])
            def fake(rgb,artifact,axis):
                out=rgb.copy();out[native]=77
                return out,dict(regions=[dict(candidate_id='coarse-1',applied=True,structure_check=dict(structure_change_passed=True))])
            with patch.object(local,'render_candidate_region',side_effect=fake):out,report=render(expected)
            np.testing.assert_array_equal(out[~self.mask],self.rgb[~self.mask]);self.assertTrue((out[self.mask]==77).all())
            self.assertEqual(report['virtual_crop_provenance']['coordinate_system'],'encoded_virtual_crop_pixels')

    def test_local_exterior_leak_rejected_before_global_composite(self):
        artifact,geometry,plan,render=self.scoped(1)
        def fake(rgb,*args):return np.zeros_like(rgb),dict(regions=[])
        before=self.rgb.copy()
        with patch.object(local,'render_candidate_region',side_effect=fake):
            with self.assertRaisesRegex(ValueError,'local_renderer_output'):render(geometry['axis_working_yx'])
        np.testing.assert_array_equal(self.rgb,before)


if __name__=='__main__':unittest.main()
