"""V2 observer/composite wiring with a synthetic renderer, not efficacy data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
from PIL import Image
import photo_region_pipeline_v1 as v1
import photo_region_pipeline_v2 as v2
from photo_region_scale_plan_v1 import plan_region_scales


def parent(mask):
    return dict(mask=mask,component=1,major_axis_yx=[1,0],working_scale=1.,
                metadata_coordinate_system='working_image_pixels',reject_reason=None)


class V2WiringTests(unittest.TestCase):
    def test_undefined_source_exif_is_normal_rejection_before_worker(self):
        for version in [v1,v2]:
            for orientation in [0,9]:
                with tempfile.TemporaryDirectory() as directory:
                    root=Path(directory);source=root/'synthetic.png'
                    rgb=np.full((64,64,3),[180,100,85],np.uint8)
                    exif=Image.Exif();exif[274]=orientation
                    Image.fromarray(rgb).save(source,exif=exif);before=source.read_bytes()
                    with patch.object(v1,'load_semantics',side_effect=AssertionError('worker must not run')):
                        returned,report=version.protect_photo_regions(source,root/'result')
                    self.assertEqual(report['status'],'rejected')
                    self.assertEqual(report['reject_reason'],'invalid_source_exif_orientation')
                    self.assertEqual(report['source_exif_orientation'],orientation)
                    self.assertEqual(report['output_exif_orientation'],1)
                    with Image.open(root/'result/returned.png') as image:
                        self.assertEqual(image.getexif()[274],1)
                        np.testing.assert_array_equal(np.asarray(image),rgb)
                    np.testing.assert_array_equal(returned,rgb)
                    self.assertEqual(source.read_bytes(),before)

    def stub_renderer(self, expected_width):
        def render(image,strength,return_details):
            import transform_automatic_fingerprint_poc_v4 as frozen
            import fingerprint_structure_check as structure
            candidate=frozen.detect_fingertips(image)['candidates'][0]
            seed=candidate['seed_roi']
            measurement=structure.estimate_finger_width(image,seed)
            self.assertEqual(measurement['status'],'estimated')
            self.assertEqual(measurement['width'],expected_width)
            before=[dict(x=20+i*20,y=40,type='ending') for i in range(10)]
            after=[p|dict(x=p['x']+8) for p in before]
            guard=structure.assess_structure(before,after,.5)
            self.assertTrue(guard['structure_change_passed'])
            (a,b,c,d),mask,_=frozen.propose_visible_pad(image,seed)
            output=image.copy();output[b:d,a:c][mask]=[1,2,3]
            return output,dict(regions=[dict(candidate_id=candidate['candidate_id'],applied=True,
                structure_check=guard)],changed_pixels=int(np.any(output!=image,axis=2).sum()))
        return render

    def artifact(self, rgb,body,pad,exif):
        association=v1.associate_axis(pad,[parent(pad)])
        plan=plan_region_scales(pad)['regions'][0]
        with patch.object(v1,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
             patch.object(v1,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))):
            artifact,geometry=v1.prepare_region(rgb,cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),pad,
                body,exif,'0'*64,plan,association)
        return artifact,geometry,association

    def test_body_coordinates_and_native_composite_all_exif(self):
        body=np.zeros((512,640),bool);body[:,100:500]=True
        pad=np.zeros_like(body);pad[170:370,150:350]=True
        rgb=np.full((512,640,3),[170,120,95],np.uint8);rgb[body]=[180,100,85]
        snapshot=rgb.copy()
        for exif in range(1,9):
            with self.subTest(exif=exif):
                artifact,geometry,association=self.artifact(rgb,body,pad,exif)
                with patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',self.stub_renderer(800)):
                    returned,details=v2.render_body_region(rgb,artifact,geometry['axis_working_yx'],association,[parent(pad)])
                np.testing.assert_array_equal(returned[~pad],rgb[~pad])
                self.assertTrue(np.any(returned[pad]!=rgb[pad]))
                self.assertEqual(details['body_width_association']['native_body_pixels'],int(body.sum()))
                self.assertEqual(details['width_observations'][0]['version'],'contactless_finger_width_body_v1_experimental')
        np.testing.assert_array_equal(rgb,snapshot)

    def test_square_padding_does_not_create_semantic_body(self):
        body=np.zeros((512,320),bool);body[:,60:260]=True
        pad=np.zeros_like(body);pad[100:500,80:240]=True
        rgb=np.full((512,320,3),[170,120,95],np.uint8);rgb[body]=[180,100,85]
        for exif in [1,6]:
            artifact,geometry,association=self.artifact(rgb,body,pad,exif)
            self.assertGreater(sum(artifact['regions'][0]['padding'].values()),0)
            with patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',self.stub_renderer(500)):
                returned,details=v2.render_body_region(rgb,artifact,geometry['axis_working_yx'],association,[parent(pad)])
            np.testing.assert_array_equal(returned[~pad],rgb[~pad])
            self.assertEqual(len(details['width_observations'][0]['samples']),7)

    def test_custom_observer_exception_restores_structure_binding(self):
        import fingerprint_structure_check as structure
        previous=structure.estimate_finger_width
        body=np.zeros((512,640),bool);body[:,100:500]=True
        pad=np.zeros_like(body);pad[170:370,150:350]=True
        rgb=np.full((512,640,3),[180,100,85],np.uint8)
        artifact,geometry,association=self.artifact(rgb,body,pad,1)
        with patch.object(v2,'estimate_finger_width_body',side_effect=ValueError('synthetic_observer_failure')), \
             patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',self.stub_renderer(800)):
            with self.assertRaisesRegex(ValueError,'synthetic_observer_failure'):
                v2.render_body_region(rgb,artifact,geometry['axis_working_yx'],association,[parent(pad)])
        self.assertIs(structure.estimate_finger_width,previous)

    def test_padded_renderer_still_rejects_body_at_actual_frame_edge(self):
        body=np.zeros((512,320),bool);body[:,60:]=True
        pad=np.zeros_like(body);pad[100:500,80:240]=True
        rgb=np.full((512,320,3),[170,120,95],np.uint8);rgb[body]=[180,100,85]
        artifact,geometry,association=self.artifact(rgb,body,pad,1)
        self.assertGreater(artifact['regions'][0]['padding']['right'],0)
        def reject(image,strength,return_details):
            import transform_automatic_fingerprint_poc_v4 as frozen
            import fingerprint_structure_check as structure
            candidate=frozen.detect_fingertips(image)['candidates'][0]
            measurement=structure.estimate_finger_width(image,candidate['seed_roi'])
            self.assertIsNone(measurement['width'])
            return image,dict(regions=[dict(candidate_id=candidate['candidate_id'],applied=False,
                structure_check=dict(structure_change_passed=False,reason='original_width_unavailable'))],changed_pixels=0)
        with patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',reject):
            returned,details=v2.render_body_region(rgb,artifact,geometry['axis_working_yx'],association,[parent(pad)])
        np.testing.assert_array_equal(returned,rgb)
        self.assertEqual(details['width_observations'][0]['observed_unpadded_image_shape'],list(artifact['working_shape']))

    def test_ambiguous_body_is_rejected_through_api_without_rendering(self):
        body=np.ones((512,640),bool)
        first=np.zeros_like(body);first[150:350,80:280]=True
        second=np.zeros_like(body);second[150:350,360:560]=True
        pad=first|second;rgb=np.full((512,640,3),[180,100,85],np.uint8)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'synthetic.png';Image.fromarray(rgb).save(source)
            with patch.object(v1,'load_semantics',return_value=(body,np.zeros_like(body),0.)), \
                 patch.object(v1,'estimate',return_value=dict(mask=pad,regions=[parent(first),parent(second)])), \
                 patch.object(v1,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
                 patch.object(v1,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))), \
                 patch.object(v1,'render_region',side_effect=AssertionError('must reject before rendering')):
                returned,report=v2.protect_photo_regions(source,root/'result',photo_semantics=root)
        np.testing.assert_array_equal(returned,rgb)
        self.assertEqual(report['fingerprints_rejected'],2)
        self.assertTrue(all(r['reason']=='native_body_has_multiple_or_unmatched_distal_parents' for r in report['regions']))
        self.assertEqual(report['quality_gate_version'],v2.VERSION)
        self.assertFalse(report['default_pipeline_enabled'])


if __name__=='__main__':unittest.main()
