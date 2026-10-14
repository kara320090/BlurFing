import copy,hashlib,unittest
from unittest.mock import patch
import cv2,numpy as np
import photo_learned_pad_pipeline_v5 as pipeline
from photo_native_body_scale_v1 import observe_width
from photo_region_pipeline_v1 import orient


class SharedAnchorTests(unittest.TestCase):
    def test_each_observation_site_has_own_scale_and_render_not_used_for_selection(self):
        body=np.ones((100,100),bool);mask=body.copy();rgb=np.zeros((100,100,3),np.uint8)
        proposals=[dict(center_yx=[30,30]),dict(center_yx=[60,60]),dict(center_yx=[70,70])]
        calls=[];rendered=[]
        def prepare(*args,**kw):
            observation=kw['_observer'](mask,body,[1.,0.]);calls.append(observation['anchor_native_yx'])
            artifact=None if len(calls)==1 else dict(region=True)
            return artifact,dict(reject_reason='pitch_unobserved' if artifact is None else None),{},lambda axis:rendered.append(axis)
        with patch.object(pipeline,'seeds',return_value=proposals),patch.object(pipeline,'prepare_body_scale',side_effect=prepare):
            artifact,geometry,_,render=pipeline.prepare_scoped_region(rgb,np.zeros((100,100),np.uint8),mask,body,1,'0'*64,dict(component=1),dict(axis_native_yx=[1.,0.]))
        self.assertEqual(calls,[[30,30],[60,60]]);self.assertTrue(artifact);self.assertEqual(rendered,[])
        self.assertFalse(geometry['seed_selection_uses_rendered_features'])

    def test_point_transform_matches_all_exact_EXIF_permutations(self):
        image=np.arange(17*29,dtype=np.int32).reshape(17,29)
        for orientation in range(1,9):
            transformed=orient(image,orientation)
            for point in [[0,0],[16,28],[4,21]]:
                mapped=pipeline.orient_point(point,image.shape,orientation)
                self.assertEqual(transformed[mapped],image[tuple(point)])

    def test_native_width_is_measured_at_explicit_predicted_seed(self):
        body=np.zeros((301,401),bool);body[10:150,140:260]=True;body[150:291,40:360]=True
        pad=np.zeros_like(body);pad[70:73,190:193]=True;pad[180:220,180:220]=True
        original=observe_width(pad,body,[1.,0.]);seed=observe_width(pad,body,[1.,0.],anchor_yx=[71,191])
        self.assertEqual(original['observed_native_body_width'],320);self.assertEqual(seed['observed_native_body_width'],120)
        for anchor in [[-1,0],[0,0],[71.,191],None]:
            if anchor is None:continue
            with self.assertRaisesRegex(ValueError,'anchor_contract'):observe_width(pad,body,[1.,0.],anchor_yx=anchor)

    def test_pinned_seed_center_uses_actual_rounded_resize_and_same_predicted_pixel(self):
        body=np.zeros((301,401),bool);body[10:291,80:320]=True;mask=np.zeros_like(body);mask[120:161,180:221]=True
        for orientation in range(1,9):
            target=[487,391] if orientation<5 else [391,487]
            allowed=cv2.resize(orient(mask.astype(np.uint8),orientation),(target[1],target[0]),interpolation=cv2.INTER_NEAREST)>0
            owner=cv2.resize(orient(body.astype(np.uint8),orientation),(target[1],target[0]),interpolation=cv2.INTER_NEAREST)>0
            rows=pipeline.pinned_proposal(allowed,owner,body.shape,orientation,target,dict(normalization_anchor_local_yx=[140,200]))
            self.assertEqual(len(rows),1);y,x=rows[0]['center_yx'];self.assertTrue(allowed[y,x])
            a,b,c,d=rows[0]['box'];self.assertTrue(owner[b:d,a:c].all())

    def test_insufficient_existing_ROI_size_and_lost_resize_anchor_reject(self):
        body=np.zeros((100,100),bool);body[10:90,40:60]=True;mask=body.copy()
        self.assertEqual(pipeline.pinned_proposal(mask,body,body.shape,1,body.shape,dict(normalization_anchor_local_yx=[50,50])),[])
        mask[:]=False
        self.assertEqual(pipeline.pinned_proposal(mask,body,body.shape,1,body.shape,dict(normalization_anchor_local_yx=[50,50])),[])


class ReturnedRGBTests(unittest.TestCase):
    def setUp(self):
        self.original=np.zeros((80,100,3),np.uint8);self.candidate=self.original.copy();self.candidate[20:60,30:70]=100
        self.artifact=dict(working_shape=[160,200],working_scale=2.,exif_orientation=1,body=np.ones((80,100),bool),
            regions=[dict(working_seed=[50,30,150,130],padding=dict(bottom=0,right=0))])
        self.report=dict(regions=[dict(applied=True,structure_check=dict(structure_change_passed=True))],transformed_pad_count=1,
            applied=True,transformation_function_passed=True,transformed_candidate_count=1,all_detected_candidates_transformed=True)

    def test_native_return_is_reprojected_for_check_and_failed_output_is_rolled_back(self):
        import fingerprint_structure_check as structure
        previous=structure.estimate_finger_width,structure.OUT,structure.run_matcher_job
        for passed in [True,False]:
            def check(before,after,seed):
                np.testing.assert_array_equal(after,cv2.resize(self.candidate,(200,160),interpolation=cv2.INTER_CUBIC))
                np.testing.assert_array_equal(before,cv2.resize(self.original,(200,160),interpolation=cv2.INTER_CUBIC))
                return dict(structure_change_passed=passed,reason='changed_structure_observed' if passed else 'insufficient_features')
            report=copy.deepcopy(self.report)
            with patch.object(structure,'check_structure_change',side_effect=check):
                out,result=pipeline.returned_structure_check(self.original,self.candidate,self.artifact,[1.,0.],report)
            self.assertEqual(result['regions'][0]['applied'],passed)
            np.testing.assert_array_equal(out,self.candidate if passed else self.original)
            self.assertEqual((structure.estimate_finger_width,structure.OUT,structure.run_matcher_job),previous)
            if not passed:
                self.assertEqual(result['changed_pixels'],0);self.assertEqual(result['transformed_pad_count'],0)
                self.assertFalse(result['applied']);self.assertFalse(result['transformation_function_passed'])
                self.assertFalse(result['all_detected_candidates_transformed']);self.assertEqual(result['transformed_candidate_count'],0)

    def test_rejected_output_does_not_enter_extractor_and_observer_restores_on_error(self):
        import fingerprint_structure_check as structure
        previous=structure.estimate_finger_width,structure.OUT,structure.run_matcher_job
        with patch.object(structure,'check_structure_change',side_effect=RuntimeError('extractor unavailable')) as check:
            report=copy.deepcopy(self.report);report['regions'][0]['applied']=False
            pipeline.returned_structure_check(self.original,self.original,self.artifact,[1.,0.],report);check.assert_not_called()
            with self.assertRaisesRegex(RuntimeError,'extractor unavailable'):
                pipeline.returned_structure_check(self.original,self.candidate,self.artifact,[1.,0.],copy.deepcopy(self.report))
        self.assertEqual((structure.estimate_finger_width,structure.OUT,structure.run_matcher_job),previous)


if __name__=='__main__':unittest.main()
