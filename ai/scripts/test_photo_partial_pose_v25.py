import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from scipy import ndimage
from PIL import Image

from photo_partial_pose_v25 import partial_permissions, geometry_from_worker, partition_candidates
from photo_pose_permissions_v1 import pose_permissions
from photo_rounded_pad_v1 import rounded_pads
from photo_automatic_v23 import apply_candidates, recover_proposal
from photo_new_input_v23 import read_raw_v6_support


class PartialPoseTests(unittest.TestCase):
    def scene(self):
        y, x = np.indices((240, 240))
        body = (((x >= 42) & (x <= 86) & (y >= 22) & (y <= 220)) |
                ((x >= 148) & (x <= 192) & (y >= 22) & (y <= 220)) |
                ((y >= 180) & (y <= 225) & (x >= 35) & (x <= 200)))
        tip = body & (y <= 85)
        points = np.full((21, 2), -10.)
        points[8], points[7] = [64, 45], [64, 105]
        points[12], points[11] = [170, 45], [170, 105]
        return body, tip, points

    def test_folded_digits_do_not_abort_two_visible_digits(self):
        body, tip, points = self.scene()
        with self.assertRaisesRegex(ValueError, 'out_of_frame'):
            pose_permissions(body, points)
        geometry, detail = partial_permissions(body, tip, points)
        self.assertEqual(detail['selected_digits'], ['index', 'middle'])
        self.assertEqual(len(detail['skipped_digits']), 3)
        np.testing.assert_array_equal(geometry['owner_labels'] > 0, body)
        self.assertEqual({a['label'] for a in geometry['axes']}, {2, 3})
        self.assertFalse(np.any((geometry['permission_labels'] > 0) & ~body))
        caps, info = rounded_pads(np.zeros_like(body), tip, body, tip, pose_geometry=geometry)
        self.assertEqual(info['applied_caps'], 2)
        self.assertEqual(ndimage.label(caps)[1], 2)
        self.assertFalse(caps[180:].any())

    def test_one_bad_digit_is_local_and_missing_semantic_tip_is_not_fabricated(self):
        body, tip, points = self.scene()
        points[12] = [100, 45]  # no BODY here; index remains usable
        geometry, detail = partial_permissions(body, tip, points)
        self.assertEqual(detail['selected_digits'], ['index'])
        self.assertTrue(any(r['digit'] == 'middle' for r in detail['skipped_digits']))
        geometry, detail = partial_permissions(body, np.zeros_like(tip), points)
        self.assertIsNone(geometry)
        self.assertFalse(detail['selected_digits'])
        self.assertFalse(detail['privacy_validated'])

    def test_empty_semantic_tip_can_use_connected_raw_V6_at_both_distal_points(self):
        body, learned, points = self.scene()
        geometry, detail = partial_permissions(body, np.zeros_like(learned), points,
                                               learned_support=learned)
        self.assertEqual(detail['selected_digits'], ['index', 'middle'])
        self.assertEqual(detail['learned_support_boolean_sha256'],
                         hashlib.sha256(learned.tobytes()).hexdigest())
        self.assertEqual({a['support_source'] for a in geometry['axes']},
                         {'V6_native_distal_tip_midpoint'})
        self.assertFalse(any(a['semantic_TIP_at_observed_TIP'] for a in geometry['axes']))
        caps, info = rounded_pads(np.zeros_like(body), learned, body, np.zeros_like(body),
                                  pose_geometry=geometry)
        self.assertEqual(info['applied_caps'], 2)
        self.assertEqual(ndimage.label(caps)[1], 2)

    def test_single_endpoint_or_disconnected_V6_never_authorizes_a_digit(self):
        body, tip, points = self.scene()
        for rows in ([45], [75], [45, 75]):
            learned = np.zeros_like(body)
            for y in rows:
                learned[y, [64, 170]] = True
            geometry, detail = partial_permissions(body, np.zeros_like(tip), points,
                                                   learned_support=learned)
            self.assertIsNone(geometry)
            self.assertFalse(detail['selected_digits'])
        # A diagonal-only connection is insufficient under the four-neighbour
        # component rule, even though the two observations are both positive.
        points[8], points[7] = [64, 45], [84, 65]
        learned = np.zeros_like(body)
        learned[np.arange(45, 56), np.arange(64, 75)] = True
        geometry, _ = partial_permissions(body, np.zeros_like(tip), points, learned_support=learned)
        self.assertIsNone(geometry)

    def test_raw_V6_shape_dtype_and_BODY_exterior_remain_fatal(self):
        body, tip, points = self.scene()
        invalid = tip.copy(); invalid[0, 0] = True
        for mask in (invalid, tip.astype(np.uint8), tip[:-1]):
            with self.assertRaisesRegex(ValueError, 'learned_support_contract'):
                partial_permissions(body, tip, points, learned_support=mask)

    def test_raw_prediction_reloaded_with_manifest_source_model_and_pixel_binding(self):
        body, learned, _ = self.scene()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); private = root / 'private'
            (private / 'dataset').mkdir(parents=True); (private / 'predictions').mkdir()
            source = dict(source_id='INPUT', source_sha256='1'*64, height=240, width=240,
                          coordinate_system='encoded_original_pixels')
            manifest = private / 'dataset/manifest.input.private.json'
            manifest.write_text(json.dumps(dict(sources=[source])), encoding='utf-8')
            target = private / 'predictions/INPUT.png'
            Image.fromarray(learned.astype(np.uint8)*255).save(target)
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            prediction = dict(model_sha256='2'*64, input_manifest_sha256=sha(manifest), rows=[
                dict(source_id='INPUT', source_sha256='1'*64, native_shape=[240, 240], prediction_sha256=sha(target))])
            report = private / 'predictions/inference.private.json'
            report.write_text(json.dumps(prediction), encoding='utf-8')
            np.testing.assert_array_equal(read_raw_v6_support(root, source, '2'*64), learned)
            with self.assertRaisesRegex(ValueError, 'binding_mismatch'):
                read_raw_v6_support(root, source, '3'*64)
            with self.assertRaisesRegex(ValueError, 'binding_mismatch'):
                read_raw_v6_support(root, dict(source, source_sha256='4'*64), '2'*64)
            Image.fromarray(np.zeros_like(body, np.uint8)).save(target)
            with self.assertRaises(ValueError):
                read_raw_v6_support(root, source, '2'*64)
            Image.fromarray(learned.astype(np.uint8)*255).save(target)
            manifest.write_text(json.dumps(dict(sources=[dict(source, width=241)])), encoding='utf-8')
            with self.assertRaises(ValueError):
                read_raw_v6_support(root, source, '2'*64)

    def test_quarter_turns_and_mirror_keep_digit_permissions(self):
        body, tip, points = self.scene()
        original, _ = partial_permissions(body, tip, points)
        rotated_points = np.stack([points[:, 1], body.shape[1] - 1 - points[:, 0]], axis=1)
        rotated, _ = partial_permissions(np.rot90(body).copy(), np.rot90(tip).copy(), rotated_points)
        np.testing.assert_array_equal(rotated['permission_labels'], np.rot90(original['permission_labels']))
        mirror = points.copy(); mirror[:, 0] = body.shape[1] - 1 - mirror[:, 0]
        reflected, _ = partial_permissions(np.fliplr(body).copy(), np.fliplr(tip).copy(), mirror)
        np.testing.assert_array_equal(reflected['permission_labels'], np.fliplr(original['permission_labels']))

    def test_two_caps_actual_render_and_outside_RGB_preservation(self):
        body, tip, points = self.scene()
        # Give the unchanged raw-ridge policy enough native samples to witness
        # four connected windows; do not weaken it for undersized fixtures.
        body = body.repeat(2, axis=0).repeat(2, axis=1)
        tip = tip.repeat(2, axis=0).repeat(2, axis=1)
        points = (points + .5) * 2 - .5
        geometry, _ = partial_permissions(body, tip, points)
        cap, _ = rounded_pads(np.zeros_like(body), tip, body, tip, pose_geometry=geometry)
        labels, count = ndimage.label(cap)
        self.assertEqual(count, 2)
        y, x = np.indices(body.shape)
        values = (150 + 18 * np.cos(2 * np.pi * x / 8)).astype(np.uint8)
        rgb = np.repeat(values[:, :, None], 3, axis=2)
        result, applied, report = apply_candidates(rgb, labels.astype(np.uint16), cap, seed=20)
        self.assertEqual(report['applied_region_count'], 2)
        np.testing.assert_array_equal(result[~applied], rgb[~applied])
        for rid in (1, 2):
            self.assertTrue(np.any(result[labels == rid] != rgb[labels == rid]))

    def test_malformed_arrays_and_foreign_worker_remain_errors(self):
        body, tip, points = self.scene()
        invalid = tip.copy(); invalid[0, 0] = True
        with self.assertRaisesRegex(ValueError, 'semantic_tip_contract'):
            partial_permissions(body, invalid, points)
        with self.assertRaises(ValueError):
            partial_permissions(body.astype(np.uint8), tip, points)
        points[0, 0] = np.nan
        with self.assertRaises(ValueError):
            partial_permissions(body, tip, points)
        with patch('photo_pose_native_pipeline_v1.verify_worker', side_effect=ValueError('pose_worker_binding_mismatch')):
            with self.assertRaisesRegex(ValueError, 'binding_mismatch'):
                geometry_from_worker({}, np.zeros((*body.shape, 3), np.uint8), {})

    def test_unknown_subset_pose_contract_stays_rejected(self):
        body, tip, points = self.scene()
        geometry, _ = partial_permissions(body, tip, points)
        geometry['metadata']['version'] = 'unrecognised'
        with self.assertRaisesRegex(ValueError, 'digit_contract'):
            rounded_pads(tip, tip, body, tip, pose_geometry=geometry)

    def test_unselected_digit_domain_preserves_its_existing_model_proposal(self):
        body, tip, points = self.scene()
        tip[:, 140:] = False  # middle remains a geometric reservation only
        geometry, detail = partial_permissions(body, tip, points)
        self.assertEqual(detail['selected_digits'], ['index'])
        self.assertTrue(np.any(geometry['owner_labels'] == 3))
        base = body & (np.indices(body.shape)[0] < 95)
        result, _ = rounded_pads(base, base, body, tip, pose_geometry=geometry)
        inactive = geometry['owner_labels'] == 3
        np.testing.assert_array_equal(result[inactive], base[inactive])

    def test_touching_digits_and_unselected_suggestions_remain_separate(self):
        mask = np.ones((80, 120), bool)
        owners = np.repeat(np.array([2, 3, 4], np.uint8), 40)[None, :].repeat(80, axis=0)
        labels, count = partition_candidates(mask, owners, [2, 3])
        self.assertEqual(count, 3)
        self.assertTrue(np.all(labels[:, :40] == 1))
        self.assertTrue(np.all(labels[:, 40:80] == 2))
        self.assertTrue(np.all(labels[:, 80:] == 3))
        np.testing.assert_array_equal(labels > 0, mask)
        with self.assertRaisesRegex(ValueError, 'candidate_limit'):
            partition_candidates(mask, owners, [2, 3], maximum=2)
        with self.assertRaisesRegex(ValueError, 'contract'):
            partition_candidates(mask, owners.astype(np.int16), [2, 3])

    def test_unresolved_pose_owner_never_looks_up_estimator_owner(self):
        body, _, _ = self.scene(); rgb = np.full((*body.shape, 3), 140, np.uint8)
        mask = body.copy(); boundary = np.zeros_like(mask)
        metadata = dict(axis_source='observed_pose_IP_DIP_to_TIP', candidates=[
            dict(candidate_id='pose-ring', unanchored_candidate_excluded=True)])
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'boundary.private.json').write_text(json.dumps(metadata), encoding='utf-8')
            with patch('finger_body_distal_estimator.estimate', side_effect=AssertionError('foreign owner lookup')):
                result, allowed, report = recover_proposal(rgb, mask, boundary, folder)
            np.testing.assert_array_equal(result, mask)
            np.testing.assert_array_equal(allowed, boundary)
            self.assertFalse(report['regions'][0]['recovered'])
            self.assertEqual(report['regions'][0]['reason'], 'observed_pose_boundary_unresolved')


if __name__ == '__main__':
    unittest.main()
