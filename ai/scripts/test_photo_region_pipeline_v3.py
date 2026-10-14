"""Candidate identity/composite wiring; synthetic rendering is not efficacy."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_region_pipeline_v3 as v3
import photo_region_pipeline_v1 as shared
from test_photo_candidate_context_v1 import parent


class V3WiringTests(unittest.TestCase):
    def test_rgb_array_mutation_is_detected_and_source_file_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,parents=self.fixture(root);original=source.read_bytes()
            def render(image,artifact,axis):
                output,details=self.render(image,artifact,axis);image[0,0]=0
                return output,details
            with self.assertRaisesRegex(RuntimeError,'source_or_exterior_changed'):
                self.evaluate(source,parents,render)
            self.assertEqual(source.read_bytes(),original)

    def test_context_memory_failure_is_normal_rejection_with_audit(self):
        from photo_resize_safety_v1 import ResizeSafetyError
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,parents=self.fixture(root)
            body=parents[0]['body_mask']|parents[1]['body_mask']
            with patch.object(shared,'load_semantics',return_value=(body,np.zeros_like(body),0.)), \
                 patch.object(v3,'estimate',side_effect=ResizeSafetyError('candidate_context_memory_limit_exceeded',dict(estimated_total_bytes=10))):
                returned,_,report=v3.evaluate_regions(source,root)
            np.testing.assert_array_equal(returned,rgb)
            self.assertEqual(report['reject_reason'],'candidate_context_memory_limit_exceeded')
            self.assertEqual(report['resource_audit']['estimated_total_bytes'],10)

    def fixture(self,root,orientation=1):
        rgb=np.full((512,640,3),[180,100,85],np.uint8)
        source=root/'synthetic.png';exif=Image.Exif();exif[274]=orientation
        Image.fromarray(rgb).save(source,exif=exif)
        first=np.zeros(rgb.shape[:2],bool);first[150:350,120:320]=True
        second=np.zeros_like(first);second[150:350,320:520]=True
        body1=np.zeros_like(first);body1[:,100:320]=True
        body2=np.zeros_like(first);body2[:,320:540]=True
        return source,rgb,[parent(first,body1),parent(second,body2,2)]

    def evaluate(self,source,parents,renderer,output=None):
        shape=parents[0]['body_mask'].shape;body=np.zeros(shape,bool);union=body.copy()
        for p in parents:
            body|=p['body_mask']
            if p.get('mask') is not None:union|=p['mask']
        with patch.object(shared,'load_semantics',return_value=(body,np.zeros_like(body),0.)), \
             patch.object(v3,'estimate',return_value=dict(mask=union,regions=parents)) as estimator, \
             patch.object(shared,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
             patch.object(shared,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))), \
             patch.object(v3,'render_candidate_region',renderer):
            if output is None:result=v3.evaluate_regions(source,source.parent)
            else:result=v3.protect_photo_regions(source,output,photo_semantics=source.parent)
        self.assertTrue(estimator.call_args.kwargs['preserve_candidates'])
        return result

    def render(self,rgb,artifact,axis):
        index=artifact['regions'][0]['component'];native=artifact['coarse_mask']
        self.assertFalse(np.any(native&~artifact['body']))
        output=rgb.copy();output[native]=[index,2,3]
        return output,dict(regions=[dict(candidate_id=f'coarse-{index}',applied=True,
            structure_check=dict(structure_change_passed=True))])

    def test_touching_ids_masks_and_full_body_saved_independently_all_exif(self):
        for orientation in range(1,9):
            with self.subTest(orientation=orientation),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source,rgb,parents=self.fixture(root,orientation)
                original=source.read_bytes();seen=[]
                def render(image,artifact,axis):
                    index=artifact['regions'][0]['component'];seen.append(index)
                    np.testing.assert_array_equal(artifact['body'],parents[index-1]['body_mask'])
                    np.testing.assert_array_equal(image,rgb)
                    return self.render(image,artifact,axis)
                returned,report=self.evaluate(source,parents,render,root/'output')
                self.assertEqual(report['fingerprints_transformed'],2);self.assertEqual(seen,[1,2])
                self.assertEqual([r['candidate_id'] for r in report['regions']],[p['candidate_id'] for p in parents])
                for p,r in zip(parents,report['regions']):
                    np.testing.assert_array_equal(np.asarray(Image.open(root/'output'/r['mask_path']))>0,p['mask'])
                    np.testing.assert_array_equal(np.asarray(Image.open(root/'output'/r['body_path']))>0,p['body_mask'])
                union=parents[0]['mask']|parents[1]['mask']
                np.testing.assert_array_equal(returned[~union],rgb[~union])
                with Image.open(root/'output/returned.png') as image:self.assertEqual(image.getexif()[274],orientation)
                self.assertEqual(source.read_bytes(),original)
                self.assertEqual(json.loads((root/'output/result.json').read_text()),report)

    def test_fragmented_candidate_is_not_relabelled_or_dropped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,parents=self.fixture(root)
            parents=parents[:1];parents[0]['mask'][10,150]=True
            returned,union,report=self.evaluate(source,parents,self.render)
            self.assertEqual(report['fingerprints_detected'],1)
            self.assertEqual(report['regions'][0]['scale_plan']['native_fragment_count'],2)
            np.testing.assert_array_equal(union,parents[0]['mask'])
            self.assertTrue(np.any(returned[10,150]!=rgb[10,150]))

    def test_overlap_rejected_before_render_and_unrelated_candidate_can_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,parents=self.fixture(root)
            parents[1]['mask'][:,319]|=parents[0]['mask'][:,319]
            parents[1]['body_mask'][:,319]=parents[0]['body_mask'][:,319]
            third=np.zeros(rgb.shape[:2],bool);third[150:350,0:90]=True
            parents.append(parent(third,third,3))
            seen=[]
            def render(image,artifact,axis):
                seen.append(artifact['regions'][0]['component']);return self.render(image,artifact,axis)
            returned,_,report=self.evaluate(source,parents,render)
            self.assertEqual(seen,[3]);self.assertEqual(report['status'],'partial_success')
            for row,p in zip(report['regions'][:2],parents[:2]):
                self.assertEqual(row['reason'],'candidate_pad_ownership_overlap')
                np.testing.assert_array_equal(returned[p['mask']],rgb[p['mask']])

    def test_renderer_identity_guard_exterior_and_feature_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,parents=self.fixture(root);parents=parents[:1]
            for kind,reason in [('identity','region_renderer_identity_contract_mismatch'),
                                ('guard','region_structure_guard_contract_mismatch'),
                                ('exterior','region_renderer_output_contract_mismatch'),
                                ('feature','insufficient_features')]:
                def render(image,artifact,axis):
                    output,details=self.render(image,artifact,axis);row=details['regions'][0]
                    if kind=='identity':row['candidate_id']='coarse-99'
                    elif kind=='guard':row['structure_check']={}
                    elif kind=='exterior':output[0,0]=0
                    else:row.update(applied=False,structure_check=dict(reason='insufficient_features'))
                    return output,details
                returned,_,report=self.evaluate(source,parents,render)
                np.testing.assert_array_equal(returned,rgb)
                self.assertEqual(report['regions'][0]['reason'],reason)

    def test_invalid_exif_rgba_fresh_output_and_strength_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,_=self.fixture(root,0)
            with patch.object(shared,'load_semantics',side_effect=AssertionError('must not run')):
                returned,report=v3.protect_photo_regions(source,root/'output')
            np.testing.assert_array_equal(returned,rgb)
            self.assertEqual(report['reject_reason'],'invalid_source_exif_orientation')
            with Image.open(root/'output/returned.png') as image:self.assertEqual(image.getexif()[274],1)
            with self.assertRaises(FileExistsError):v3.protect_photo_regions(source,root/'output')
            for strength in [True,.7]:
                with self.assertRaises(ValueError):v3.protect_photo_regions(source,root/'other',strength=strength)
            Image.new('RGBA',(32,32)).save(root/'rgba.png')
            with self.assertRaisesRegex(ValueError,'RGB/L'):v3.evaluate_regions(root/'rgba.png')

    def test_body_observer_frozen_binding_and_restore_all_exif(self):
        from test_photo_region_pipeline_v2 import V2WiringTests
        import fingerprint_structure_check as structure
        old=structure.estimate_finger_width
        helper=V2WiringTests()
        body=np.zeros((512,640),bool);body[:,100:500]=True
        pad=np.zeros_like(body);pad[170:370,150:350]=True
        rgb=np.full((512,640,3),[170,120,95],np.uint8);rgb[body]=[180,100,85]
        for orientation in range(1,9):
            artifact,geometry,_=helper.artifact(rgb,body,pad,orientation)
            with patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',helper.stub_renderer(800)):
                returned,details=v3.render_candidate_region(rgb,artifact,geometry['axis_working_yx'])
            np.testing.assert_array_equal(returned[~pad],rgb[~pad])
            self.assertEqual(details['width_observations'][0]['observed_unpadded_image_shape'],list(artifact['working_shape']))
            self.assertIs(structure.estimate_finger_width,old)
        with patch.object(v3,'estimate_finger_width_body',side_effect=ValueError('synthetic_failure')), \
             patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',helper.stub_renderer(800)):
            with self.assertRaisesRegex(ValueError,'synthetic_failure'):
                v3.render_candidate_region(rgb,artifact,geometry['axis_working_yx'])
        self.assertIs(structure.estimate_finger_width,old)


if __name__=='__main__':unittest.main()
