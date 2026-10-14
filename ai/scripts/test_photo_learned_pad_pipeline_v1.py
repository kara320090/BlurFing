import copy,hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import photo_learned_pad_pipeline_v1 as pipeline


def context(body,pad,index=1,reason=None):
    parent=dict(mask=pad if reason is None else None,body_mask=body,reject_reason=reason,component=index,watershed_part=1,
                metadata_coordinate_system='working_image_pixels',working_scale=.5,major_axis_yx=[.6,.8],distal_endpoint_source='observed')
    return dict(parent=parent,body=body,pad=parent['mask'],reject_reason=reason,
                estimator_region_index=index,candidate_id=f'body-{index:04d}-part-0001')


class LearnedAssociationTests(unittest.TestCase):
    def setUp(self):
        self.body=np.ones((9,13),bool);self.pad=np.zeros((9,13),bool);self.pad[1:3,1:4]=True
        self.learned=self.pad.copy();self.learned[2:5,2:7]=True
        self.owner=context(self.body,self.pad)

    def test_expanded_learned_pad_uses_unique_body_and_exact_rounded_axis(self):
        association,owner=pipeline.associate_learned_body_axis(self.learned,[self.owner])
        r=np.array([round(9*.5)/9,round(13*.5)/13]);axis=np.array([.6,.8])/r;axis/=np.linalg.norm(axis)
        np.testing.assert_allclose(association['axis_native_yx'],axis)
        self.assertIs(owner,self.body);self.assertFalse(association['coarse_subset_required'])

    def test_invalid_overlapping_owner_cannot_be_ignored(self):
        invalid=context(self.body,self.pad,2,'axis_unavailable')
        with self.assertRaisesRegex(ValueError,'ambiguous'):pipeline.associate_learned_body_axis(self.learned,[self.owner,invalid])

    def test_crosses_owner_and_missing_axis_rejected(self):
        owner=copy.deepcopy(self.owner);owner['body'][4:]=False
        with self.assertRaisesRegex(ValueError,'crosses'):pipeline.associate_learned_body_axis(self.learned,[owner])
        owner=self.owner|dict(reject_reason='axis_unavailable')
        with self.assertRaisesRegex(ValueError,'axis_unavailable'):pipeline.associate_learned_body_axis(self.learned,[owner])

    def test_missing_or_nonfinite_axis_is_controlled_rejection(self):
        for axis in ['missing',None,[float('nan'),1.],[0.,0.]]:
            owner=copy.deepcopy(self.owner)
            if axis=='missing':del owner['parent']['major_axis_yx']
            else:owner['parent']['major_axis_yx']=axis
            with self.assertRaisesRegex(ValueError,'axis_metadata'):pipeline.associate_learned_body_axis(self.learned,[owner])


class LearnedProtectionTests(unittest.TestCase):
    def setUp(self):
        self.rgb=np.full((40,60,3),50,np.uint8);self.mask=np.zeros((40,60),bool)
        self.mask[2:18,2:20]=True;self.mask[22:38,35:55]=True
        self.body=np.ones((40,60),bool)
        self.source=dict(source_id='SYNTH',source_path='unused.png',source_sha256='0'*64,
            source_RGB_sha256=pipeline.pixel_hash(self.rgb),source_exif_orientation=1,height=40,width=60,
            coordinate_system='encoded_original_pixels',tip_path='unused_tip.png',tip_sha256='0'*64)
        self.context=context(self.body,self.mask)
        self.stack=__import__('contextlib').ExitStack();self.addCleanup(self.stack.close)
        for name,kwargs in [
            ('verify_source',dict(return_value=None)),('read_source_rgb',dict(side_effect=lambda *a:self.rgb.copy())),
            ('read_body',dict(return_value=self.body)),('read_mask',dict(return_value=np.zeros_like(self.body))),
            ('estimate',dict(return_value={})),('candidate_contexts',dict(return_value=[self.context]))]:
            self.stack.enter_context(patch.object(pipeline,name,**kwargs))
        self.stack.enter_context(patch.object(pipeline.shared,'route_input',return_value={'input_type':'PHOTO'}))
        def prepare(rgb,gray,native,body,orientation,sha,plan,assoc):
            roi=SimpleNamespace(validate=lambda *a:None)
            return dict(native=native,component=plan['component'],regions=[dict(roi=roi)]),dict(reject_reason=None,axis_working_yx=[1.,0.])
        self.stack.enter_context(patch.object(pipeline.shared,'prepare_region',side_effect=prepare))

    def evaluate(self):return pipeline.evaluate_learned_mask(self.source,self.mask,pipeline.pixel_hash(self.mask))

    def test_partial_success_preserves_rejected_and_exterior_pixels(self):
        def render(rgb,artifact,axis):
            n=artifact['component'];out=rgb.copy();applied=n==1
            if applied:out[artifact['native']]=80
            return out,dict(regions=[dict(candidate_id=f'coarse-{n}',applied=applied,
                structure_check=dict(structure_change_passed=applied,reason=None if applied else 'insufficient_features'))])
        with patch.object(pipeline,'render_candidate_region',side_effect=render):out,report=self.evaluate()
        self.assertEqual(report['status'],'partial_success');self.assertEqual(report['fingerprints_transformed'],1)
        np.testing.assert_array_equal(out[~self.mask],self.rgb[~self.mask]);np.testing.assert_array_equal(out[22:38,35:55],self.rgb[22:38,35:55])
        self.assertFalse(report['PHOTO_FAIL_CLOSED_PIPELINE_READY'])
        with tempfile.TemporaryDirectory() as tmp:pipeline.save_result(Path(tmp)/'saved',out,report)

    def test_applied_without_structure_guard_and_exterior_leak_rejected(self):
        for structure in [False,True]:
            def render(rgb,artifact,axis):
                out=rgb.copy();out[:]=100
                return out,dict(regions=[dict(candidate_id=f"coarse-{artifact['component']}",applied=True,
                    structure_check=dict(structure_change_passed=structure))])
            with patch.object(pipeline,'render_candidate_region',side_effect=render):out,report=self.evaluate()
            np.testing.assert_array_equal(out,self.rgb);self.assertEqual(report['fingerprints_transformed'],0)

    def test_component_resource_limit_rejects_before_renderer(self):
        with patch.object(pipeline,'render_candidate_region') as render:
            with patch.object(pipeline,'MAX_COMPONENTS',1):out,report=self.evaluate()
        render.assert_not_called()
        np.testing.assert_array_equal(out,self.rgb);self.assertEqual(report['reject_reason'],'learned_component_resource_limit')

    def test_truthy_nonboolean_renderer_success_is_rejected(self):
        def render(rgb,artifact,axis):
            out=rgb.copy();out[artifact['native']]=80
            return out,dict(regions=[dict(candidate_id=f"coarse-{artifact['component']}",applied='false',
                structure_check=dict(structure_change_passed=True))])
        with patch.object(pipeline,'render_candidate_region',side_effect=render):out,report=self.evaluate()
        np.testing.assert_array_equal(out,self.rgb);self.assertEqual(report['fingerprints_transformed'],0)

    def test_applied_identical_native_RGB_is_not_success(self):
        def render(rgb,artifact,axis):
            return rgb.copy(),dict(regions=[dict(candidate_id=f"coarse-{artifact['component']}",applied=True,
                structure_check=dict(structure_change_passed=True))])
        with patch.object(pipeline,'render_candidate_region',side_effect=render):out,report=self.evaluate()
        np.testing.assert_array_equal(out,self.rgb);self.assertEqual(report['fingerprints_transformed'],0)
        self.assertTrue(all(r['reason']=='renderer_success_without_native_RGB_change' for r in report['regions']))

    def test_target_fields_and_mask_outside_body_fail_before_renderer(self):
        with self.assertRaisesRegex(ValueError,'GT_fields'):
            pipeline.evaluate_learned_mask(self.source|dict(GT_folder='forbidden'),self.mask,pipeline.pixel_hash(self.mask))
        self.body[:]=False
        with self.assertRaisesRegex(ValueError,'outside'):self.evaluate()


if __name__=='__main__':unittest.main()
