import unittest
from unittest.mock import patch
import cv2,numpy as np
import photo_body_observation_seed_v1 as old
import photo_spatial_observation_seeds_v1 as spatial
import photo_learned_pad_pipeline_v9 as pipeline
import photo_region_pipeline_v1 as shared
import test_photo_component_local_evidence_v1 as bindings


class SpatialSeedsTests(unittest.TestCase):
    def fixture(self):
        mask=np.zeros((200,160),bool);mask[30:150,40:120]=True;body=np.zeros_like(mask);body[10:190,20:140]=True
        return mask,body

    def test_prefix_budget_geometry_and_determinism(self):
        mask,body=self.fixture();before=mask.copy();original=old.seeds(mask,body);first=spatial.proposals(mask,body)
        self.assertEqual(first[:len(original)],original);self.assertGreater(len(first),len(original));self.assertLessEqual(len(first),8)
        self.assertEqual(first,spatial.proposals(mask,body));self.assertEqual(len({tuple(p['box']) for p in first}),len(first))
        for row in first:
            y,x=row['center_yx'];a,b,c,d=row['box'];self.assertTrue(mask[y,x]);self.assertTrue(body[b:d,a:c].all())
            self.assertEqual(c-a,d-b);self.assertGreaterEqual(c-a,8)
        np.testing.assert_array_equal(mask,before)

    def test_no_new_proposal_when_no_eligible_body_support(self):
        mask=np.zeros((30,30),bool);mask[2,2]=True
        self.assertEqual(spatial.proposals(mask,mask),[])
        with self.assertRaises(ValueError):spatial.proposals(mask.astype(np.uint8),mask)

    def test_first_success_keeps_original_seed_and_does_not_try_more(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8);calls=[]
        def observer(frame,box,allowed):calls.append(box);return 8.,{'scope':'same'},None
        with patch.object(pipeline,'observed_component_pitch',side_effect=observer),patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
            artifact,geometry=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,1,'0'*64,dict(working_scale=1.,component=1),dict(axis_native_yx=[1.,0.]))
        self.assertEqual(len(calls),1);self.assertEqual(artifact['regions'][0]['working_seed'],old.seeds(mask,body)[0]['box'])

    def test_retry_uses_second_seed_and_same_EXIF_fractional_permission(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8)
        for orientation in range(1,9):
            calls=[]
            def observer(frame,box,allowed):
                calls.append((list(box),allowed.copy()));return (None,{},None) if len(calls)==1 else (8.,{'selected':'second'},None)
            with patch.object(pipeline,'observed_component_pitch',side_effect=observer),patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
                artifact,geometry=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,orientation,'0'*64,dict(working_scale=1.17,component=1),dict(axis_native_yx=[1.,0.]))
            h,w=geometry['working_shape'];expected=cv2.resize(shared.orient(mask.astype(np.uint8),orientation),(w,h),interpolation=cv2.INTER_NEAREST)>0
            self.assertEqual(len(calls),2);self.assertEqual(artifact['regions'][0]['working_seed'],calls[1][0])
            self.assertEqual(artifact['regions'][0]['pitch_measurement'],{'selected':'second'})
            for _,allowed in calls:np.testing.assert_array_equal(allowed,expected)

    def test_all_failures_keep_rejection_and_do_not_expand_permission(self):
        mask,body=self.fixture();rgb=np.full((*mask.shape,3),120,np.uint8);calls=[]
        def observer(frame,box,allowed):calls.append(box);return None,{},None
        with patch.object(pipeline,'observed_component_pitch',side_effect=observer):
            artifact,geometry=pipeline.prepare_local(rgb,rgb[:,:,0],mask,body,1,'0'*64,dict(working_scale=1.,component=1),dict(axis_native_yx=[1.,0.]))
        self.assertIsNone(artifact);self.assertEqual(geometry['reject_reason'],'component_local_pitch_unobserved')
        self.assertLessEqual(len(calls),8);self.assertFalse(geometry['permission_mask_expanded'])


class SpatialRendererBindings(bindings.RendererBindingTests):
    def setUp(self):
        replacement=patch.object(bindings,'pipeline',pipeline);replacement.start();self.addCleanup(replacement.stop)


if __name__=='__main__':unittest.main()
