import copy,unittest
from unittest.mock import patch
import numpy as np
import photo_whole_region_structure_v1 as guard
import photo_learned_pad_pipeline_v7 as pipeline


class WholeRegionTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((300,300,3),120,np.uint8);self.mask=np.zeros((300,300),bool);self.mask[20:220,20:120]=True
        self.out=self.rgb.copy();self.out[self.mask]=140
        self.before=np.zeros((512,512),bool);self.before[200:210,100:150]=True

    def result(self,original,modified):
        return dict(images=[dict(key=k,status='ok',template=dict(width=400,height=400,
            positionsX=[p[0] for p in rows],positionsY=[p[1] for p in rows],types=['E']*len(rows)))
            for k,rows in [('Original',original),('Modified',modified)]])

    def check(self,first,second,skel2):
        result=self.result(first,second)
        with (patch.object(guard,'prepare_fingerprint',side_effect=[({'skeleton_full':self.before.copy()},None,None),({'skeleton_full':skel2},None,None)]),
              patch.object(guard,'run_matcher_job',return_value=result)):
            return guard.assess(self.rgb,self.out,[20,20,220,220],self.mask,dict(status='estimated',width=200.))

    def test_external_features_and_skeleton_changes_cannot_authorize_transform(self):
        points=[(20+i,100) for i in range(10)];outside=[(300+i,100) for i in range(20)]
        second=self.before.copy();second[300:350,400:450]=True
        result=self.check(points,points+outside,second)
        self.assertFalse(result['structure_change_passed']);self.assertEqual(result['skeleton_changed_fraction'],0.)
        self.assertEqual(result['counts']['Modified']['inside_permission'],10)
        self.assertEqual(result['counts']['Modified']['outside_permission'],20)

    def test_only_points_inside_permission_count_towards_normal_features(self):
        outside=[(300+i,100) for i in range(20)];second=np.zeros_like(self.before);second[200:210,170:200]=True
        result=self.check(outside,outside,second)
        self.assertEqual(result['minutiae']['before_count'],0);self.assertEqual(result['reason'],'insufficient_features')

    def test_real_mask_domain_change_uses_same_frozen_predicate_and_is_marked(self):
        first=[(20+i*2,100) for i in range(12)];second=[(80+i*2,140) for i in range(12)]
        skeleton=np.zeros_like(self.before);skeleton[200:210,170:200]=True
        before=self.rgb.copy();result=self.check(first,second,skeleton)
        self.assertTrue(result['structure_change_passed']);self.assertFalse(result['frozen_gate_equivalence'])
        self.assertTrue(result['feature_scope_changed_from_frozen_seed']);np.testing.assert_array_equal(self.rgb,before)

    def test_exterior_leak_and_scope_pixel_loss_reject(self):
        leaked=self.out.copy();leaked[0,0]=0
        with self.assertRaisesRegex(ValueError,'permission_contract'):
            guard.assess(self.rgb,leaked,[20,20,220,220],self.mask,dict(status='estimated',width=200.))
        with self.assertRaisesRegex(ValueError,'drops_permission'):
            guard.assess(self.rgb,self.out,[20,20,120,120],self.mask,dict(status='estimated',width=200.))


class ScopedGateTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((100,100,3),120,np.uint8);self.mask=np.zeros((100,100),bool);self.mask[30:70,30:70]=True
        self.artifact=dict(working_shape=[100,100],working_scale=1.,exif_orientation=1,body=np.ones((100,100),bool),coarse_mask=self.mask,
            regions=[dict(working_seed=[30,30,70,70],working_scope=[20,20,80,80],padding=dict(bottom=0,right=0))])

    def test_alias_restored_on_error_and_native_gate_rolls_back_all_success_flags(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        original=frozen.check_structure_change
        with patch.object(pipeline,'render_candidate_region',side_effect=RuntimeError('source failure')):
            with self.assertRaisesRegex(RuntimeError,'source failure'):pipeline.render(self.rgb,self.artifact,[1.,0.])
        self.assertIs(frozen.check_structure_change,original)

    def test_projection_spill_is_isolated_without_changing_returned_native_pixels(self):
        self.artifact['working_shape']=[75,75];self.artifact['working_scale']=.75
        self.artifact['regions'][0]['working_seed']=[20,20,52,52]
        self.artifact['regions'][0]['working_scope']=[15,15,60,60]
        candidate=self.rgb.copy();candidate[self.mask]=180
        def render(*args):
            return candidate.copy(),dict(regions=[dict(applied=True,structure_check=dict(structure_change_passed=True))])
        def check(first,last,scope,allowed,width):
            np.testing.assert_array_equal(first[~allowed],last[~allowed]);return dict(structure_change_passed=True)
        with (patch.object(pipeline,'render_candidate_region',side_effect=render),
              patch.object(pipeline,'estimate_finger_width_body',return_value=dict(status='estimated',width=400.)),
              patch.object(pipeline,'assess',side_effect=check)):
            out,report=pipeline.render(self.rgb,self.artifact,[1.,0.])
        np.testing.assert_array_equal(out,candidate);self.assertTrue(report['reprojection_exterior_context_restored'])

    def test_native_gate_rolls_back_all_success_flags(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        original=frozen.check_structure_change
        def render(rgb,*unused):
            out=rgb.copy();out[self.mask]=180
            return out,dict(regions=[dict(applied=True,structure_check=dict(structure_change_passed=True))],
                applied=True,transformation_function_passed=True,transformed_pad_count=1,transformed_candidate_count=1,all_detected_candidates_transformed=True)
        with (patch.object(pipeline,'render_candidate_region',side_effect=render),
              patch.object(pipeline,'estimate_finger_width_body',return_value=dict(status='estimated',width=400.)),
              patch.object(pipeline,'assess',return_value=dict(structure_change_passed=False,reason='insufficient_features'))):
            out,report=pipeline.render(self.rgb,self.artifact,[1.,0.])
        np.testing.assert_array_equal(out,self.rgb);self.assertFalse(report['applied']);self.assertFalse(report['regions'][0]['applied'])
        self.assertEqual(report['changed_pixels'],0);self.assertEqual(report['transformed_candidate_count'],0)
        self.assertIs(frozen.check_structure_change,original)


if __name__=='__main__':unittest.main()
