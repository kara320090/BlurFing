"""Synthetic topology/ownership tests, not anatomical accuracy evidence."""
import unittest
from unittest.mock import patch
import cv2
import numpy as np
from photo_terminal_branch_candidates_v1 import (estimate, skeleton_graph, terminal_paths,
                                               prune_junction_contained_spurs, working_candidates)


def finger():
    body = np.zeros((240, 120), np.uint8)
    cv2.rectangle(body, (40, 65), (80, 239), 1, -1)
    cv2.ellipse(body, (60, 65), (20, 30), 0, 0, 360, 1, -1)
    return body.astype(bool)


def hand():
    body = np.zeros((320, 320), np.uint8)
    body[170:235, 45:275] = 1
    body[230:, 135:186] = 1
    for x, y in [(75, 45), (155, 25), (235, 65)]:
        cv2.rectangle(body, (x-15, y), (x+15, 180), 1, -1)
        cv2.circle(body, (x, y), 15, 1, -1)
    return body.astype(bool)


class GraphTests(unittest.TestCase):
    def test_grid_corner_has_no_diagonal_shortcut(self):
        skeleton = np.zeros((5, 5), bool)
        skeleton[1, 2] = skeleton[2, 2] = skeleton[2, 3] = True
        coords, neighbors = skeleton_graph(skeleton)
        self.assertEqual(sorted(map(len, neighbors)), [1, 1, 2])
        self.assertEqual(len(terminal_paths(coords, neighbors)), 2)
        for i, adjacent in enumerate(neighbors):
            self.assertTrue(all(i in neighbors[j] for j in adjacent))

    def test_cycle_does_not_invent_endpoint(self):
        skeleton = np.zeros((7, 7), bool)
        skeleton[1:6, 1] = skeleton[1:6, 5] = True
        skeleton[1, 1:6] = skeleton[5, 1:6] = True
        coords, graph = skeleton_graph(skeleton)
        self.assertEqual(terminal_paths(coords, graph), [])

    def test_junction_contained_spur_removed_but_long_branches_preserved(self):
        skeleton = np.zeros((25, 30), bool)
        skeleton[5:20, 15] = True; skeleton[10, 15:18] = True
        before = skeleton.copy(); distance = np.full(skeleton.shape, 4., np.float32)
        pruned, audit = prune_junction_contained_spurs(skeleton, distance)
        np.testing.assert_array_equal(skeleton, before)
        self.assertTrue(pruned[5:20, 15].all()); self.assertFalse(pruned[10, 16:].any())
        self.assertEqual(audit['internal_spur_pixels_removed'], 2)
        coords, graph = skeleton_graph(pruned)
        self.assertEqual(len(terminal_paths(coords, graph)), 2)


class CandidateTests(unittest.TestCase):
    def test_frame_cut_root_excluded_and_free_tip_is_subset(self):
        body = finger(); result = estimate(body, np.zeros_like(body))
        valid = [r for r in result['regions'] if r['reject_reason'] is None]
        self.assertEqual(len(valid), 1)
        self.assertTrue(any(r['reject_reason'] == 'terminal_truncated_by_image_frame' for r in result['regions']))
        self.assertTrue(result['mask'][50:85].any())
        self.assertFalse(result['mask'][140:].any())
        self.assertFalse(np.any(result['mask'] & ~body))
        self.assertFalse(result['approved_for_use']); self.assertFalse(result['renderer_binding_allowed'])

    def test_multi_finger_body_has_separate_terminal_candidates(self):
        body = hand(); result = estimate(body, np.zeros_like(body))
        valid = [r for r in result['regions'] if r['reject_reason'] is None]
        self.assertGreaterEqual(len(valid), 3)
        for x, y in [(75, 45), (155, 25), (235, 65)]:
            self.assertTrue(result['mask'][y-8:y+8, x-8:x+8].any())
        self.assertFalse(result['mask'][235:].any())
        self.assertLess(int(result['mask'].sum()), int(body.sum())/2)
        self.assertEqual(len({r['candidate_id'] for r in result['regions']}), len(result['regions']))
        seen = np.zeros_like(body)
        for row in valid:
            self.assertFalse(np.any(seen & row['mask'])); seen |= row['mask']
        np.testing.assert_array_equal(seen, result['mask'])

    def test_overbroad_semantic_tip_does_not_union_hand_back_into_pad(self):
        body = hand(); snapshots = body.copy(), body.copy()
        absent = estimate(body, np.zeros_like(body)); broad = estimate(body, body)
        np.testing.assert_array_equal(absent['mask'], broad['mask'])
        self.assertFalse(broad['semantic_tip_used_for_selection'])
        self.assertFalse(broad['semantic_tip_union_applied'])
        np.testing.assert_array_equal(body, snapshots[0])

    def test_repeated_masks_ids_and_decisions_are_exact(self):
        body = hand(); first = estimate(body, np.zeros_like(body)); second = estimate(body, np.zeros_like(body))
        np.testing.assert_array_equal(first['mask'], second['mask'])
        self.assertEqual([(r['candidate_id'], r['reject_reason']) for r in first['regions']],
                         [(r['candidate_id'], r['reject_reason']) for r in second['regions']])

    def test_native_rounding_keeps_observed_source_support(self):
        canvas = np.zeros((240, 200), np.uint8); canvas[:, 40:160] = finger()
        body = cv2.resize(canvas, (803, 1003), interpolation=cv2.INTER_NEAREST) > 0
        result = estimate(body, np.zeros_like(body))
        self.assertEqual(result['mask'].shape, body.shape)
        self.assertTrue(result['mask'].any()); self.assertFalse(np.any(result['mask'] & ~body))
        self.assertEqual(result['working_shape'], [512, 410])

    def test_resized_cap_spurs_do_not_create_extra_body_owners(self):
        # Deformation/nearest resize creates tiny internal skeleton branches.
        # The pruning audit records their removal without changing semantics.
        body = cv2.resize(finger().astype(np.uint8), (803, 1003), interpolation=cv2.INTER_NEAREST) > 0
        before = body.copy()
        result = estimate(body, np.zeros_like(body))
        self.assertEqual(sum(r['reject_reason'] is None for r in result['regions']), 1)
        self.assertGreater(result['components'][0]['internal_spur_pixels_removed'], 0)
        self.assertFalse(np.any(result['mask'] & ~body)); np.testing.assert_array_equal(body, before)
        self.assertFalse(result['approved_for_use'])

    def test_ambiguous_nearest_support_rejects_both_terminal_owners(self):
        component = np.zeros((100, 100), bool); component[15:85, 30:70] = True
        skeleton = np.zeros_like(component); skeleton[35:65, 50] = True
        with patch('photo_terminal_branch_candidates_v1.skeletonize', return_value=skeleton):
            rows, _ = working_candidates(component)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['reject_reason'] == 'terminal_nearest_support_ambiguous' for r in rows))
        self.assertTrue(all('mask' not in r for r in rows))

    def test_quarter_turns_preserve_tip_region(self):
        body = finger(); expected = estimate(body, np.zeros_like(body))['mask']
        for k in [1, 2, 3]:
            rotated = np.rot90(body, k).copy()
            back = np.rot90(estimate(rotated, np.zeros_like(rotated))['mask'], -k)
            self.assertGreater(float((back & expected).sum()/(back | expected).sum()), .95)

    def test_empty_and_endpointless_inputs_do_not_fallback_to_body(self):
        body = np.zeros((100, 100), bool)
        self.assertFalse(estimate(body, body)['mask'].any())
        body[50, 50] = True
        self.assertFalse(estimate(body, np.zeros_like(body))['mask'].any())

    def test_contracts_and_allocation_rejected_before_topology(self):
        body = finger()
        with self.assertRaisesRegex(ValueError, 'boolean_semantic_masks_required'):
            estimate(body.astype(np.float32), body)
        tip = body.copy(); tip[0, 0] = True
        with self.assertRaisesRegex(ValueError, 'tip_outside_finger_body'): estimate(body, tip)
        huge = np.broadcast_to(np.array(True), (40000, 1))
        with patch('photo_terminal_branch_candidates_v1.skeletonize', side_effect=AssertionError('preflight required')), \
             patch('photo_terminal_branch_candidates_v1.np.any', side_effect=AssertionError('preflight before mask temporaries')):
            with self.assertRaisesRegex(ValueError, 'adapter_memory_limit_exceeded'):
                estimate(huge, huge)


if __name__ == '__main__':
    unittest.main()
