"""Synthetic contracts; stub rendering never establishes protection efficacy."""
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

import photo_region_pipeline_v1 as pipeline
from photo_coarse_adapter_v2 import orient


def parent(mask, axis=(1., 0.), body_component=1):
    return dict(mask=mask, major_axis_yx=axis, working_scale=1., component=body_component,
                metadata_coordinate_system='working_image_pixels', reject_reason=None)


class CoordinateTests(unittest.TestCase):
    def test_axis_matches_pixel_permutation_for_all_exif_orientations(self):
        image = np.zeros((11, 13), np.uint8)
        image[3, 4], image[7, 9] = 1, 2
        for exif in range(1, 9):
            with self.subTest(exif=exif):
                transformed = orient(image, exif)
                p = np.argwhere(transformed == 1)[0]
                q = np.argwhere(transformed == 2)[0]
                expected = (q-p)/np.linalg.norm(q-p)
                np.testing.assert_allclose(pipeline.orient_axis([4, 5], exif), expected)

    def test_axis_accounts_for_actual_rounded_resize_ratios(self):
        mask = np.ones((101, 203), bool)
        metadata = parent(mask, (1, 1)) | dict(working_scale=.5)
        axis = pipeline.associate_axis(mask, [metadata])['axis_native_yx']
        expected = np.array([101/50, 203/102])
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(axis, expected)
        working = pipeline.orient_axis(axis, 6, [37/203, 19/101])
        expected = np.array([axis[1]*37/203, -axis[0]*19/101])
        np.testing.assert_allclose(working, expected/np.linalg.norm(expected))

    def test_watershed_parents_do_not_associate_by_shared_body_id(self):
        left = np.zeros((32, 32), bool); left[5:20, 3:12] = True
        right = np.zeros_like(left); right[5:20, 12:25] = True
        self.assertEqual(pipeline.associate_axis(left, [parent(left), parent(right)])['estimator_region_index'], 1)
        with self.assertRaisesRegex(ValueError, 'parent_ambiguous'):
            pipeline.associate_axis(left | right, [parent(left), parent(right)])
        with self.assertRaisesRegex(ValueError, 'parent_unavailable'):
            pipeline.associate_axis(left, [parent(right)])
        with self.assertRaisesRegex(ValueError, 'crosses_parent'):
            pipeline.associate_axis(left | right, [parent(left)])

    def test_invalid_axis_contract(self):
        for axis, exif, scale in [([0,0],1,[1,1]), ([np.nan,1],1,[1,1]),
                                 ([1,0],9,[1,1]), ([1,0],True,[1,1]), ([1,0],1,[1,0])]:
            with self.assertRaises(ValueError):pipeline.orient_axis(axis, exif, scale)


class ObserverIsolationTests(unittest.TestCase):
    def test_width_observer_uses_expected_seed_and_restores_on_exception(self):
        import fingerprint_structure_check as structure
        old = structure.estimate_finger_width
        artifact = dict(regions=[dict(working_seed=[10,10,50,50])])
        image = np.zeros((64,64,3), np.uint8)
        seen = []
        def renderer(rgb, artifact):
            structure.estimate_finger_width(rgb, [10,10,50,50])
            with self.assertRaisesRegex(ValueError, 'seed_contract'):
                structure.estimate_finger_width(rgb, [11,10,51,50])
            raise RuntimeError('renderer_error')
        def observe(rgb, box, axis):
            seen.append(axis); return dict(status='estimated', width=400)
        with patch.object(pipeline.renderer_binding, 'transform', renderer), patch.object(pipeline, 'estimate_finger_width_axis', observe):
            with self.assertRaisesRegex(RuntimeError, 'renderer_error'):
                pipeline.render_region(image, artifact, [0,1])
        self.assertIs(structure.estimate_finger_width, old)
        self.assertEqual(seen, [[0,1]])

    def test_default_adapter_lock_sees_restored_observer_after_experiment(self):
        import fingerprint_structure_check as structure
        old = structure.estimate_finger_width
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        observed, errors = [], []
        def renderer(rgb, artifact):
            entered.set()
            if not release.wait(5):raise RuntimeError('test_deadline')
            return rgb, dict(regions=[])
        def experiment():
            try:pipeline.render_region(np.zeros((64,64,3),np.uint8), dict(regions=[dict(working_seed=[10,10,50,50])]), [1,0])
            except Exception as error:errors.append(error)
        def default_call():
            waiting.set()
            with pipeline.renderer_binding._LOCK:observed.append(structure.estimate_finger_width)
        with patch.object(pipeline.renderer_binding, 'transform', renderer):
            first = threading.Thread(target=experiment); second = threading.Thread(target=default_call)
            first.start()
            try:
                self.assertTrue(entered.wait(5)); second.start(); self.assertTrue(waiting.wait(5))
                self.assertEqual(observed, [])
            finally:
                release.set(); first.join(5)
                if second.ident is not None:second.join(5)
        self.assertEqual(errors, []); self.assertEqual(observed, [old])
        self.assertIs(structure.estimate_finger_width, old)


class PipelineContracts(unittest.TestCase):
    def fixture(self, root, exif=1):
        rgb = np.full((512,640,3), [180,100,85], np.uint8)
        source = root/'source.png'; tag = Image.Exif(); tag[274] = exif
        Image.fromarray(rgb).save(source, exif=tag)
        large = np.zeros((512,640), bool); large[170:370,150:350] = True
        mask = large.copy(); mask[10,10] = True
        return source, rgb, large, mask

    def compositor_stub(self, working, strength, return_details):
        """Exercise real binding/resize/composite; deliberately no efficacy test."""
        import transform_automatic_fingerprint_poc_v4 as frozen
        candidate = frozen.detect_fingertips(working)['candidates'][0]
        scope, local, _ = frozen.propose_visible_pad(working, candidate['seed_roi'])
        a,b,c,d = scope
        returned = working.copy()
        returned[b:d,a:c][local] = [1,2,3]
        return returned, dict(regions=[dict(candidate_id=candidate['candidate_id'], applied=True,
                                           structure_check=dict(structure_change_passed=True))],
                              changed_pixels=int(np.any(returned != working, axis=2).sum()))

    def test_native_composite_and_rejected_pixels_all_exif(self):
        with tempfile.TemporaryDirectory() as directory:
            for exif in range(1,9):
                root = Path(directory)/str(exif); root.mkdir()
                source,rgb,large,mask = self.fixture(root,exif)
                sha = hashlib.sha256(source.read_bytes()).hexdigest()
                with patch.object(pipeline,'load_semantics',return_value=(mask,np.zeros_like(mask),0.)), \
                     patch.object(pipeline,'estimate',return_value=dict(mask=mask,regions=[parent(mask)])), \
                     patch.object(pipeline,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
                     patch.object(pipeline,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))), \
                     patch('transform_automatic_fingerprint_poc_v4_boundaryblend_02.transform_fingerprint_photo',self.compositor_stub):
                    returned,report = pipeline.protect_photo_regions(source,root/'output',photo_semantics=root)
                self.assertEqual(report['status'],'partial_success')
                self.assertEqual(report['fingerprints_transformed'],1)
                self.assertEqual(report['fingerprints_rejected'],1)
                self.assertEqual(report['regions'][0]['reason'],'adapter_memory_limit_exceeded')
                np.testing.assert_array_equal(returned[~large],rgb[~large])
                self.assertTrue(np.any(returned[large] != rgb[large]))
                self.assertEqual(sha,hashlib.sha256(source.read_bytes()).hexdigest())
                with Image.open(root/'output/returned.png') as image:
                    self.assertEqual(image.getexif()[274],exif)
                    np.testing.assert_array_equal(np.asarray(image),returned)
                saved=json.loads((root/'output/result.json').read_text())
                self.assertFalse(saved['default_pipeline_enabled'])
                self.assertFalse(saved['PHOTO_PROTECTION_PRODUCTION_READY'])

    def test_feature_rejection_keeps_native_region_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,large,mask=self.fixture(root)
            mask=large
            def reject(rgb,artifact,axis):
                return rgb,dict(regions=[dict(candidate_id='coarse-1',applied=False,status='structure_check_failed',
                    structure_check=dict(reason='insufficient_features',minutiae=dict(before=13,after=6)))])
            with patch.object(pipeline,'load_semantics',return_value=(mask,np.zeros_like(mask),0.)), \
                 patch.object(pipeline,'estimate',return_value=dict(mask=mask,regions=[parent(mask)])), \
                 patch.object(pipeline,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
                 patch.object(pipeline,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))), \
                 patch.object(pipeline,'render_region',reject):
                returned,_,report=pipeline.evaluate_regions(source,root)
            np.testing.assert_array_equal(returned,rgb)
            self.assertEqual(report['regions'][0]['quality_status'],'REJECT_INSUFFICIENT_FEATURES')

    def test_bad_semantics_fail_closed_without_loading_masks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,rgb,_,_=self.fixture(root)
            (root/'semantics.json').write_text(json.dumps(dict(coordinate_system='upright_pixels')))
            with patch.object(pipeline,'read_binary',side_effect=AssertionError('mask loading must not run')):
                returned,_,report=pipeline.evaluate_regions(source,root)
            np.testing.assert_array_equal(returned,rgb)
            self.assertEqual(report['reject_reason'],'semantic_coordinate_contract_mismatch')

    def test_applied_flag_without_structure_guard_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source,rgb,mask,_=self.fixture(root)
            def missing_guard(rgb,artifact,axis):
                return rgb,dict(regions=[dict(candidate_id='coarse-1',applied=True)])
            with patch.object(pipeline,'load_semantics',return_value=(mask,np.zeros_like(mask),0.)), \
                 patch.object(pipeline,'estimate',return_value=dict(mask=mask,regions=[parent(mask)])), \
                 patch.object(pipeline,'observed_seed_pitch',return_value=(10.,dict(attempts=[]),None)), \
                 patch.object(pipeline,'ridge_evidence',return_value=(None,dict(credible_fraction=1.))), \
                 patch.object(pipeline,'render_region',missing_guard):
                returned,_,report=pipeline.evaluate_regions(source,root)
            np.testing.assert_array_equal(returned,rgb)
            self.assertEqual(report['regions'][0]['reason'],'region_structure_guard_contract_mismatch')

    def test_output_and_alpha_contracts_reject_before_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'rgba.png'; Image.new('RGBA',(32,32)).save(source)
            with self.assertRaisesRegex(ValueError,'RGB/L'):pipeline.evaluate_regions(source,root)
            (root/'occupied').mkdir(); (root/'occupied/keep.txt').write_text('preserved')
            with patch.object(pipeline,'evaluate_regions',side_effect=AssertionError('must not run')):
                with self.assertRaisesRegex(FileExistsError,'fresh output'):pipeline.protect_photo_regions(source,root/'occupied')
            self.assertEqual((root/'occupied/keep.txt').read_text(),'preserved')


if __name__ == '__main__':unittest.main()
