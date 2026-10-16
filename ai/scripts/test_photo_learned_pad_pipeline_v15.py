"""Integration of experimental owner repair with unchanged final-RGB rollback."""
import contextlib,unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import photo_learned_pad_pipeline_v1 as base
import photo_learned_pad_pipeline_v12 as v12
import photo_learned_pad_pipeline_v15 as experiment
from test_photo_learned_pad_pipeline_v1 import context


class BoundaryPipelineTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((40,60,3),50,np.uint8)
        self.mask=np.zeros((40,60),bool)
        self.mask[2:18,2:20]=True;self.mask[22:38,35:55]=True
        self.body=np.ones(self.mask.shape,bool);self.owner=self.body.copy()
        self.owner[2:4,2:8]=False
        self.source=dict(source_id='SYNTH',source_path='unused.png',source_sha256='0'*64,
            source_RGB_sha256=base.pixel_hash(self.rgb),source_exif_orientation=1,height=40,width=60,
            coordinate_system='encoded_original_pixels',tip_path='unused.png',tip_sha256='0'*64)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        for name,options in [
            ('verify_source',dict(return_value=None)),('read_source_rgb',dict(side_effect=lambda *a:self.rgb.copy())),
            ('read_body',dict(return_value=self.body)),('read_mask',dict(return_value=np.zeros_like(self.body))),
            ('estimate',dict(return_value={})),('candidate_contexts',dict(return_value=[context(self.owner,self.mask)]))]:
            self.stack.enter_context(patch.object(base,name,**options))
        self.stack.enter_context(patch.object(base.shared,'route_input',return_value=dict(input_type='PHOTO')))
        self.stack.enter_context(patch.object(experiment,'restore_contexts',side_effect=lambda rows,body:rows))
        self.calls=[]

    def prepare(self,rgb,gray,native,owner,orientation,sha,plan,association):
        self.calls.append(dict(native=native.copy(),owner=owner.copy()))
        def render(axis):
            output=rgb.copy();applied=plan['component']==1
            if applied:output[native]=80
            return output,dict(regions=[dict(candidate_id=f"coarse-{plan['component']}",applied=applied,
                structure_check=dict(structure_change_passed=applied,reason=None if applied else 'pitch_unobserved'))])
        return (dict(regions=[dict(roi=SimpleNamespace())]),dict(reject_reason=None,axis_working_yx=[1.,0.]),plan,render)

    def evaluate(self,**kwargs):
        return experiment.evaluate_learned_mask(self.source,self.mask,base.pixel_hash(self.mask),**kwargs)

    def test_adapter_is_unchanged_v12_and_partial_output_preserves_rejected_pixels(self):
        self.assertIs(experiment.prepare_scoped_region,v12.prepare_scoped_region)
        original=self.mask.copy();owner=self.owner.copy()
        with patch.object(experiment,'prepare_scoped_region',side_effect=self.prepare):output,report=self.evaluate()
        self.assertEqual(report['status'],'partial_success');self.assertEqual(report['fingerprints_transformed'],1)
        self.assertEqual(report['boundary_association_audit'][0]['restored_pixels'],12)
        np.testing.assert_array_equal(output[~self.mask],self.rgb[~self.mask])
        np.testing.assert_array_equal(output[22:38,35:55],self.rgb[22:38,35:55])
        np.testing.assert_array_equal(self.mask,original);np.testing.assert_array_equal(self.owner,owner)
        self.assertTrue(all(not report[k] for k in ['default_pipeline_enabled','approved_for_protection','privacy_validated']))

    def test_exterior_leak_or_false_structure_flag_rolls_back_candidate(self):
        for leak in [False,True]:
            def prepare(*args):
                artifact,geometry,plan,_=self.prepare(*args);native=args[2]
                def render(axis):
                    output=self.rgb.copy()
                    if leak:output[:]=80
                    else:output[native]=80
                    return output,dict(regions=[dict(candidate_id=f"coarse-{plan['component']}",applied=True,
                        structure_check=dict(structure_change_passed=leak))])
                return artifact,geometry,plan,render
            with patch.object(experiment,'prepare_scoped_region',side_effect=prepare):output,report=self.evaluate()
            np.testing.assert_array_equal(output,self.rgb)
            self.assertEqual(report['fingerprints_transformed'],0)

    def test_detect_only_does_not_run_transform(self):
        def prepare(*args):
            artifact,geometry,plan,_=self.prepare(*args)
            return artifact,geometry,plan,lambda axis:self.fail('detect-only renderer invoked')
        with patch.object(experiment,'prepare_scoped_region',side_effect=prepare):output,report=self.evaluate(detect_only=True)
        np.testing.assert_array_equal(output,self.rgb);self.assertEqual(report['fingerprints_transformed'],0)

    def test_inference_target_fields_and_wrong_hash_fail_before_repair(self):
        with patch.object(experiment,'repair_contexts') as repair:
            with self.assertRaisesRegex(ValueError,'GT_fields'):
                experiment.evaluate_learned_mask(self.source|dict(GT_folder='forbidden'),self.mask,base.pixel_hash(self.mask))
            with self.assertRaisesRegex(ValueError,'prediction_mask_contract'):
                experiment.evaluate_learned_mask(self.source,self.mask,'0'*64)
        repair.assert_not_called()

    def test_ambiguous_boundary_stays_rejected_without_permission_pixel_loss(self):
        left=self.body.copy();left[:,7:]=False
        right=self.body.copy();right[:,:8]=False
        with patch.object(base,'candidate_contexts',return_value=[context(left,self.mask),context(right,self.mask,2)]):
            with patch.object(experiment,'prepare_scoped_region',side_effect=self.prepare):output,report=self.evaluate()
        self.assertEqual(report['boundary_association_audit'][0]['restored_pixels'],0)
        rows=report['regions'];self.assertTrue(any(r['reason']=='learned_body_owner_unavailable' for r in rows))
        self.assertEqual(sum(r['mask_pixels'] for r in rows),int(self.mask.sum()))
        unassigned=self.mask&~left&~right
        np.testing.assert_array_equal(output[unassigned],self.rgb[unassigned])


if __name__=='__main__':unittest.main()
