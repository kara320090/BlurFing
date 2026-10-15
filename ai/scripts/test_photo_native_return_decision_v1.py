import copy,unittest
from unittest.mock import patch
import cv2,numpy as np
from PIL import Image
import photo_native_return_decision_v1 as decision
import photo_learned_pad_pipeline_v12 as pipeline
import photo_learned_pad_pipeline_v7 as v7
import fingerprint_structure_check as structure


def evidence(after,passed=None):
    before=[dict(x=i*20,y=20,type='ending') for i in range(13)]
    changed=[dict(x=i*20,y=80,type='ending') for i in range(after)]
    result=structure.assess_structure(before,changed,.8)
    if passed is not None:assert result['structure_change_passed']==passed
    return result


class NativeDecisionTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((100,100,3),120,np.uint8);self.mask=np.zeros((100,100),bool);self.mask[30:70,30:70]=True
        self.artifact=dict(working_shape=[100,100],working_scale=1.,exif_orientation=1,body=np.ones_like(self.mask),coarse_mask=self.mask,
            regions=[dict(working_seed=[30,30,70,70],working_scope=[20,20,80,80],padding=dict(bottom=0,right=0))])
        self.proposal=self.rgb.copy();self.proposal[self.mask]=190;self.callback_results=[]

    def renderer(self,local,artifact,axis):
        import transform_automatic_fingerprint_poc_v4 as frozen
        result=frozen.check_structure_change(local,self.proposal,[30,30,70,70]);self.callback_results.append(copy.deepcopy(result))
        passed=result['structure_change_passed'];output=self.proposal.copy() if passed else local.copy()
        return output,dict(regions=[dict(candidate_id='coarse-1',applied=passed,structure_check=result)],applied=passed,
            transformation_function_passed=passed,changed_pixels=int(np.any(output!=local,axis=2).sum()))

    def run_case(self,checks):
        with (patch.object(decision,'render_candidate_region',side_effect=self.renderer),
              patch.object(decision,'assess',side_effect=checks),
              patch.object(structure,'estimate_finger_width',return_value=dict(status='estimated',width=400)),
              patch.object(decision,'estimate_finger_width_body',return_value=dict(status='estimated',width=400))):
            return decision.render(self.rgb,self.artifact,[1.,0.])

    def test_working_rejection_remains_false_and_only_actual_native_pass_authorizes_output(self):
        before=self.rgb.copy();out,report=self.run_case([evidence(9,False),evidence(12,True)])
        self.assertFalse(self.callback_results[0]['structure_change_passed'])
        np.testing.assert_array_equal(out,self.proposal);np.testing.assert_array_equal(self.rgb,before)
        self.assertFalse(report['working_candidate_passed']);self.assertTrue(report['structure_checked_on_actual_native_return'])
        self.assertEqual(report['proposal_count'],1);self.assertEqual(report['proposal_seed_scale_or_renderer_retries'],0)
        self.assertFalse(report['regions'][0]['working_renderer_structure_check']['structure_change_passed'])
        self.assertEqual(report['regions'][0]['returned_RGB_structure_check']['minutiae']['after_count'],12)
        self.assertTrue(report['regions'][0]['applied']);self.assertFalse(report['frozen_gate_equivalence'])

    def test_previously_accepted_candidate_retains_exact_native_RGB(self):
        out,report=self.run_case([evidence(12,True),evidence(12,True)])
        np.testing.assert_array_equal(out,self.proposal);self.assertTrue(report['working_candidate_passed'])

    def test_final_feature_loss_zero_or_below_ten_never_passes(self):
        for count in [0,6,9]:
            out,report=self.run_case([evidence(9,False),evidence(count,False)])
            np.testing.assert_array_equal(out,self.rgb);self.assertFalse(report['applied'])
            self.assertEqual(report['changed_pixels'],0);self.assertEqual(report['transformed_candidate_count'],0)

    def test_native_failure_rolls_back_even_when_working_passed(self):
        out,report=self.run_case([evidence(12,True),evidence(9,False)])
        np.testing.assert_array_equal(out,self.rgb);self.assertFalse(report['regions'][0]['applied'])
        self.assertFalse(report['transformation_function_passed']);self.assertFalse(report['all_detected_candidates_transformed'])

    def test_native_insufficient_original_features_also_reject(self):
        check=structure.assess_structure([],[],.99)
        out,report=self.run_case([check,check]);np.testing.assert_array_equal(out,self.rgb)
        self.assertFalse(report['applied'])

    def test_working_extractor_exception_does_not_become_a_candidate_or_success(self):
        def renderer(local,*args):
            import transform_automatic_fingerprint_poc_v4 as frozen
            with self.assertRaisesRegex(RuntimeError,'extractor'):frozen.check_structure_change(local,self.proposal,[30,30,70,70])
            return local.copy(),dict(regions=[dict(applied=False,status='structure_inspection_failed_unchanged')],applied=False)
        with patch.object(decision,'render_candidate_region',side_effect=renderer),patch.object(decision,'assess',side_effect=RuntimeError('extractor')) as assess,patch.object(structure,'estimate_finger_width',return_value={}):
            out,report=decision.render(self.rgb,self.artifact,[1.,0.])
        assess.assert_called_once();np.testing.assert_array_equal(out,self.rgb)
        self.assertFalse(report['structure_checked_on_actual_native_return'])

    def test_native_extractor_error_restores_binding_and_does_not_return_success(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        before=frozen.check_structure_change;source=self.rgb.copy()
        with self.assertRaisesRegex(RuntimeError,'native extractor'):self.run_case([evidence(9,False),RuntimeError('native extractor')])
        self.assertIs(frozen.check_structure_change,before);np.testing.assert_array_equal(self.rgb,source)

    def test_missing_width_or_missing_candidate_is_not_retried(self):
        check=dict(structure_change_passed=False,reason='original_width_unavailable')
        out,report=self.run_case([check]);np.testing.assert_array_equal(out,self.rgb)
        self.assertFalse(report['structure_checked_on_actual_native_return'])
        with patch.object(decision,'render_candidate_region',return_value=(self.rgb.copy(),{'regions':[{'applied':False}]})),patch.object(decision,'assess') as assess:
            out,report=decision.render(self.rgb,self.artifact,[1.,0.]);assess.assert_not_called()

    def test_observation_frame_mismatch_cannot_be_projected_and_alias_restores(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        before=frozen.check_structure_change
        def wrong(local,*args):return frozen.check_structure_change(local,self.proposal,[31,30,71,70])
        with patch.object(decision,'render_candidate_region',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'source_contract'):decision.render(self.rgb,self.artifact,[1.,0.])
        self.assertIs(frozen.check_structure_change,before)

    def test_projection_rejects_wrong_shape_dtype_or_exterior_changes(self):
        leaked=self.proposal.copy();leaked[0,0]=0
        for proposal in [self.proposal.astype(np.float32),self.proposal[:80],leaked]:
            with self.assertRaisesRegex(ValueError,'RGB_contract'):decision.project_proposal(self.rgb,self.artifact,proposal)

    def test_native_width_cannot_be_reestimated_from_another_source_or_candidate(self):
        with (patch.object(decision,'render_candidate_region',side_effect=self.renderer),
              patch.object(decision,'assess',return_value=evidence(9,False)) as assess,
              patch.object(structure,'estimate_finger_width',return_value=dict(status='estimated',width=400)),
              patch.object(decision,'estimate_finger_width_body',return_value=dict(status='estimated',width=390))):
            with self.assertRaisesRegex(ValueError,'width_mismatch'):decision.render(self.rgb,self.artifact,[1.,0.])
        assess.assert_called_once()

    def test_renderer_cannot_claim_success_without_any_gate_callback(self):
        for output,report in [(self.proposal,dict(regions=[dict(applied=False)],applied=False)),
                              (self.rgb,dict(regions=[dict(applied=True)],applied=True)),
                              (self.rgb,dict(regions=[dict(applied=False)],applied=False,changed_pixels=10))]:
            with patch.object(decision,'render_candidate_region',return_value=(output.copy(),copy.deepcopy(report))):
                with self.assertRaisesRegex(ValueError,'uninspected_renderer_success'):decision.render(self.rgb,self.artifact,[1.,0.])

    def test_unsupported_working_evidence_cannot_authorize_a_changed_return(self):
        check=dict(structure_change_passed=True,reason='original_width_unavailable')
        with self.assertRaisesRegex(ValueError,'uninspected_renderer_success'):self.run_case([check])

    def test_EXIF_and_fractional_projection_match_independent_PIL_permutations(self):
        rng=np.random.default_rng(72);rgb=rng.integers(0,256,(91,123,3),np.uint8);mask=np.zeros((91,123),bool);mask[10:65,30:95]=True
        ops={1:None,2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,4:Image.Transpose.FLIP_TOP_BOTTOM,
             5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
        inverse={1:1,2:2,3:3,4:4,5:5,6:8,7:7,8:6}
        for orientation in range(1,9):
            upright=Image.fromarray(rgb);upright=upright if orientation==1 else upright.transpose(ops[orientation])
            shape=[round(upright.height*.83),round(upright.width*.83)]
            artifact=dict(working_shape=shape,working_scale=.83,exif_orientation=orientation,body=np.ones_like(mask),coarse_mask=mask,
                regions=[dict(padding=dict(bottom=5,right=3))])
            first,_,allowed=v7.working_views(rgb,artifact);proposal=first.copy();proposal[allowed]=190
            out=decision.project_proposal(rgb,artifact,proposal)
            back=Image.fromarray(cv2.resize(proposal[:shape[0],:shape[1]],upright.size,interpolation=cv2.INTER_CUBIC))
            if orientation!=1:back=back.transpose(ops[inverse[orientation]])
            expected=rgb.copy();expected[mask]=np.asarray(back)[mask]
            np.testing.assert_array_equal(out,expected);np.testing.assert_array_equal(out[~mask],rgb[~mask])


class ScopeBindingTests(unittest.TestCase):
    def test_legacy_preparation_rejection_does_not_invoke_native_renderer(self):
        original=(None,{}, {},None)
        with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=original),patch.object(pipeline,'render') as render:
            self.assertEqual(pipeline.prepare_scoped_region(),original);render.assert_not_called()

    def test_both_observation_closures_use_native_renderer_and_restore_on_error(self):
        for module in [pipeline.v10,pipeline.legacy]:
            before=(pipeline.v10.render,pipeline.legacy.render)
            def scoped(axis):return module.render('local','artifact',axis)
            first=({}, {}, {},scoped)
            with patch.object(pipeline.legacy,'prepare_scoped_region',return_value=first),patch.object(pipeline,'render',side_effect=RuntimeError('injected')) as render:
                prepared=pipeline.prepare_scoped_region()
                with self.assertRaisesRegex(RuntimeError,'injected'):prepared[3]([1.,0.])
                render.assert_called_once_with('local','artifact',[1.,0.])
            self.assertEqual((pipeline.v10.render,pipeline.legacy.render),before)

    def test_parallel_scoped_bindings_restore_both_legacy_renderers(self):
        from concurrent.futures import ThreadPoolExecutor
        before=pipeline.v10.render,pipeline.legacy.render
        def prepare(value):
            module=pipeline.v10 if value==100 else pipeline.legacy
            return {}, {}, {},lambda axis:module.render(value,'artifact',axis)
        def render(value,artifact,axis):return np.full((2,2,3),value,np.uint8),{}
        with patch.object(pipeline.legacy,'prepare_scoped_region',side_effect=prepare),patch.object(pipeline,'render',side_effect=render):
            functions=[pipeline.prepare_scoped_region(value)[3] for value in [100,180]]
            with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda f:f([1.,0.])[0],functions))
        for value,result in zip([100,180],results):self.assertTrue(np.all(result==value))
        self.assertEqual((pipeline.v10.render,pipeline.legacy.render),before)


if __name__=='__main__':unittest.main()
