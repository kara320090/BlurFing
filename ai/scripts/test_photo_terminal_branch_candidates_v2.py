import unittest
import numpy as np
import photo_terminal_branch_candidates_v1 as v1
import photo_terminal_branch_candidates_v2 as v2
from test_photo_terminal_branch_candidates_v1 import hand, finger


class PixelOwnershipTests(unittest.TestCase):
    def test_overlap_pixels_unowned_both_unique_owners_preserved(self):
        a = np.zeros((20, 20), bool); a[3:12, 3:10] = True
        b = np.zeros_like(a); b[3:12, 9:16] = True
        before = a.copy(), b.copy(); overlap = a & b
        rows, count = v2.resolve_pixel_ownership([dict(mask=a, reject_reason=None),
                                                  dict(mask=b, reject_reason=None)], a.shape)
        self.assertEqual(count, 9)
        self.assertTrue(all(r['ambiguous_working_pixels'] == 9 for r in rows))
        self.assertTrue(all(r['topology_candidate_working_pixels'] == 63 for r in rows))
        self.assertTrue(all(r['reject_reason'] is None for r in rows))
        self.assertFalse(np.any(rows[0]['mask'] & rows[1]['mask']))
        self.assertFalse(np.any((rows[0]['mask'] | rows[1]['mask']) & overlap))
        np.testing.assert_array_equal(rows[0]['mask'], a & ~overlap)
        np.testing.assert_array_equal(rows[1]['mask'], b & ~overlap)
        np.testing.assert_array_equal(a, before[0]); np.testing.assert_array_equal(b, before[1])

    def test_identical_candidate_support_rejects_both_owners(self):
        mask = np.ones((10, 10), bool)
        rows, count = v2.resolve_pixel_ownership([dict(mask=mask, reject_reason=None),
                                                  dict(mask=mask.copy(), reject_reason=None)], mask.shape)
        self.assertEqual(count, 100)
        self.assertTrue(all(r['reject_reason'] == 'terminal_unique_support_unavailable' for r in rows))
        self.assertTrue(all('mask' not in r for r in rows))

    def test_invalid_mask_shape_or_dtype_rejected(self):
        for mask in [np.ones((5, 5), bool), np.ones((10, 10), np.uint8), [[True]], 1]:
            with self.assertRaisesRegex(ValueError, 'terminal_ownership_mask_contract_mismatch'):
                v2.resolve_pixel_ownership([dict(mask=mask)], (10, 10))

    def test_topology_rejected_region_is_not_revived(self):
        rejected = dict(reject_reason='terminal_truncated_by_image_frame')
        rows, count = v2.resolve_pixel_ownership([rejected], (10, 10))
        self.assertEqual(rows, [rejected]); self.assertEqual(count, 0)

    def test_both_versions_stay_opt_in_and_v1_not_mutated(self):
        body = hand(); before = v1.estimate(body, body)
        result = v2.estimate(body, body); after = v1.estimate(body, body)
        np.testing.assert_array_equal(before['mask'], after['mask'])
        np.testing.assert_array_equal(body, hand())
        self.assertFalse(result['approved_for_use']); self.assertFalse(result['renderer_binding_allowed'])
        self.assertFalse(result['protection_of_ambiguous_pixels_allowed'])
        self.assertFalse(np.any(result['mask'] & ~body))
        seen = np.zeros_like(body)
        for row in result['regions']:
            if row.get('mask') is not None:
                self.assertFalse(np.any(seen & row['mask'])); seen |= row['mask']
        np.testing.assert_array_equal(seen, result['mask'])

    def test_simple_single_finger_geometry_is_identical_across_versions(self):
        body = finger(); a = v1.estimate(body, body); b = v2.estimate(body, body)
        np.testing.assert_array_equal(a['mask'], b['mask'])
        self.assertEqual([r['reject_reason'] for r in a['regions']], [r['reject_reason'] for r in b['regions']])


if __name__ == '__main__':unittest.main()
