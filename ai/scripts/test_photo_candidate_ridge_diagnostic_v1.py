"""Synthetic diagnostic/GT-isolation tests; no claimed protection performance."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import numpy as np
from PIL import Image
import photo_candidate_ridge_diagnostic_v1 as diagnostic
from test_photo_candidate_context_v1 import parent


class CoordinateTests(unittest.TestCase):
    def test_actual_anisotropic_scale_normal_conversion(self):
        convert=diagnostic.native_normal_pitch
        self.assertAlmostEqual(convert(8.,0.,[.5,.25]),32.)
        self.assertAlmostEqual(convert(8.,90.,[.5,.25]),16.)
        self.assertAlmostEqual(convert(8.,45.,[.5,.25]),8/np.hypot(.25/np.sqrt(2),.5/np.sqrt(2)))
        for angle in [0.,35.,90.,145.]:self.assertAlmostEqual(convert(8.,angle,[.5,.5]),16.)

    def test_invalid_pitch_coordinate_values(self):
        for pitch,angle,ratio in [(0.,0.,[1.,1.]),(np.nan,0.,[1.,1.]),
                                  (8.,np.inf,[1.,1.]),(8.,0.,[0.,1.]),
                                  (True,0.,[1.,1.]),(8.,0.,[1.])]:
            with self.assertRaises(ValueError):diagnostic.native_normal_pitch(pitch,angle,ratio)

    def test_resolution_dedup_no_upscale_and_exact_ratios(self):
        small=diagnostic.resolution_plans((400,300))
        self.assertEqual(len(small),1)
        self.assertEqual(small[0]['requested_resolutions'],[512,1024,2048,'native'])
        self.assertTrue(small[0]['native_resolution'])
        large=diagnostic.resolution_plans((2049,1003))
        self.assertEqual(len(large),4)
        for plan in large:
            self.assertLessEqual(plan['nominal_scale'],1.)
            self.assertEqual(plan['actual_resize_yx'],[plan['shape'][0]/2049,plan['shape'][1]/1003])
        self.assertEqual(large[-1]['shape'],[2049,1003])

    def test_resource_plan_rejection_without_allocating_large_image(self):
        plans=diagnostic.resolution_plans((40000,40000))
        self.assertEqual(plans[-1]['status'],'rejected')
        self.assertEqual(plans[-1]['reject_reason'],'adapter_memory_limit_exceeded')
        for invalid in [(0,5),(True,5),(1.5,5),[5],None]:
            with self.assertRaises(ValueError):diagnostic.resolution_plans(invalid)


class ObservationTests(unittest.TestCase):
    def fixture(self):
        y,x=np.indices((512,512));gray=(128+60*np.sin(2*np.pi*x/8)).astype(np.uint8)
        rgb=np.repeat(gray[:,:,None],3,axis=2)
        body=np.ones(gray.shape,bool);pad=body.copy();pad[:,:256]=False
        return rgb,body,pad

    def test_ridge_outside_pad_is_diagnostic_only_and_native_pitch_observed(self):
        rgb,body,pad=self.fixture();snapshots=[a.copy() for a in [rgb,body,pad]]
        result=diagnostic.observe_candidate(rgb,body,pad,'0'*64)
        self.assertEqual(len(result['levels']),1);level=result['levels'][0]
        self.assertGreater(level['support_inside_pad_pixels'],0)
        self.assertGreater(level['support_outside_pad_pixels'],0)
        self.assertEqual(level['pitch']['status'],'observed')
        self.assertAlmostEqual(level['pitch']['evidence']['pitch_value'],8.,delta=.2)
        self.assertFalse(level['pitch']['renderer_binding_allowed'])
        self.assertFalse(result['protection_mask_changed']);self.assertFalse(result['used_by_protection'])
        for a,b in zip([rgb,body,pad],snapshots):np.testing.assert_array_equal(a,b)

    def test_nonperiodic_image_never_generates_default_pitch(self):
        rgb,body,pad=self.fixture();rgb[:]=128
        result=diagnostic.observe_candidate(rgb,body,pad,'0'*64)
        pitch=result['levels'][0]['pitch']
        self.assertEqual(pitch['status'],'unobserved');self.assertIsNone(pitch['evidence']['pitch_value'])
        self.assertFalse(result['default_pitch_generated'])

    def test_native_patch_centers_include_crop_origin(self):
        rgb,body,pad=self.fixture()
        body[:16]=False;body[:,:16]=False;pad&=body
        result=diagnostic.observe_candidate(rgb,body,pad,'0'*64)
        level=result['levels'][0];evidence=level['pitch']['evidence']
        accepted=[p for p in evidence['cue_results']['patches'] if p['accepted']]
        converted=level['pitch']['patch_native_coordinates']
        self.assertTrue(converted)
        self.assertEqual(result['bbox_encoded_source_xyxy'][:2],[16,16])
        for before,after in zip(accepted,converted):
            self.assertEqual(after['center_encoded_source_xy'],[before['x']+16,before['y']+16])

    def test_input_contract_and_support_outside_body_rejected(self):
        rgb,body,pad=self.fixture()
        for image,b,p in [(rgb.astype(float),body,pad),(rgb,body.astype('uint8'),pad),
                          (rgb,body,np.zeros_like(pad)),(rgb,~body,pad)]:
            with self.assertRaises(ValueError):diagnostic.observe_candidate(image,b,p,'0'*64)
        body[:10]=False;pad&=body
        body[50,50]=False;pad&=body
        with patch.object(diagnostic,'ridge_evidence',return_value=(np.ones((502,512),bool),{})):
            with self.assertRaisesRegex(ValueError,'coordinate_contract'):
                diagnostic.observe_candidate(rgb,body,pad,'0'*64)
        with patch.object(diagnostic,'ridge_evidence',return_value=(np.zeros((502,512),np.uint8),{})):
            with self.assertRaisesRegex(ValueError,'coordinate_contract'):
                diagnostic.observe_candidate(rgb,body,pad,'0'*64)


class FileContracts(unittest.TestCase):
    def fixture(self,root,exif=1):
        rgb,body,pad=ObservationTests().fixture()
        source=root/'synthetic.png';tag=Image.Exif();tag[274]=exif
        Image.fromarray(rgb).save(source,exif=tag)
        annotation=root/'annotation';annotation.mkdir()
        gt=np.ones(body.shape,bool)
        Image.fromarray(gt.astype(np.uint8)*255).save(annotation/'ground_truth_mask.png')
        metadata=dict(source_sha256=diagnostic.shared.digest(source),human_annotation=True,
            annotation_type='human_reviewed_fingerprint_pad',coordinate_system='encoded_original_pixels',
            image_width=512,image_height=512,exif_orientation=exif,annotation_status='valid_positive',
            mask_sha256=diagnostic.shared.digest(annotation/'ground_truth_mask.png'))
        (annotation/'source.json').write_text(json.dumps(metadata))
        return source,rgb,body,pad,annotation

    def run_diagnostic(self,source,body,pad,output,annotation=None):
        with patch.object(diagnostic.shared,'load_semantics',return_value=(body,np.zeros_like(body),0.)), \
             patch.object(diagnostic,'estimate',return_value=dict(mask=pad,regions=[parent(pad,body)])):
            return diagnostic.diagnose(source,output,photo_semantics=source.parent,annotation_folder=annotation)

    def test_human_gt_only_changes_metrics_not_observations_and_source_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,body,pad,annotation=self.fixture(root,6)
            original=source.read_bytes();meta=(annotation/'source.json').read_bytes()
            without=self.run_diagnostic(source,body,pad,root/'without')
            with_gt=self.run_diagnostic(source,body,pad,root/'with',annotation)
            self.assertEqual(without['regions'],with_gt['regions'])
            self.assertIsNone(without['human_GT_mask_metrics'])
            self.assertEqual(with_gt['human_GT_mask_metrics']['recall'],.5)
            self.assertFalse(with_gt['GT_used_by_observer']);self.assertFalse(with_gt['protection_applied'])
            self.assertEqual(with_gt['source_exif_orientation'],6)
            self.assertEqual(with_gt['coordinate_system'],'encoded_original_pixels')
            self.assertEqual(source.read_bytes(),original);self.assertEqual((annotation/'source.json').read_bytes(),meta)
            self.assertEqual(json.loads((root/'with/diagnostic.private.json').read_text()),with_gt)
            level=with_gt['regions'][0]['observations']['levels'][0]
            support_path=root/'with'/level['support_path']
            self.assertEqual(diagnostic.shared.digest(support_path),level['support_file_sha256'])

    def test_model_segmentation_cannot_be_claimed_as_human_gt(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,body,pad,annotation=self.fixture(root)
            metadata=json.loads((annotation/'source.json').read_text());metadata['human_annotation']=False
            (annotation/'source.json').write_text(json.dumps(metadata))
            with self.assertRaisesRegex(ValueError,'GT_not_human'):
                self.run_diagnostic(source,body,pad,root/'result',annotation)

    def test_fresh_output_exif_rgba_and_decode_resource_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,body,pad,annotation=self.fixture(root)
            (root/'occupied').mkdir();(root/'occupied/keep').write_text('keep')
            with self.assertRaises(FileExistsError):diagnostic.diagnose(source,root/'occupied')
            Image.new('RGBA',(10,10)).save(root/'rgba.png')
            with self.assertRaisesRegex(ValueError,'RGB/L'):diagnostic.diagnose(root/'rgba.png',root/'rgba-result')
            tag=Image.Exif();tag[274]=0;Image.fromarray(rgb).save(root/'invalid.png',exif=tag)
            with self.assertRaisesRegex(ValueError,'invalid_source_exif'):
                diagnostic.diagnose(root/'invalid.png',root/'invalid-result')
            fake=MagicMock();fake.mode='RGB';fake.height=40000;fake.width=40000;fake.getexif.return_value={274:1}
            opened=MagicMock();opened.__enter__.return_value=fake
            with patch.object(diagnostic.Image,'open',return_value=opened):
                with self.assertRaisesRegex(ValueError,'adapter_memory_limit_exceeded'):
                    diagnostic.diagnose(source,root/'large')
            fake.convert.assert_not_called()


if __name__=='__main__':unittest.main()
