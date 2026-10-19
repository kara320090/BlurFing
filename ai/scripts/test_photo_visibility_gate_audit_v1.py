import unittest

import numpy as np

from photo_visibility_gate_audit_v1 import audit_ridge_level, audit_pitch_sampling
from ridge_evidence_frontend import ridge_evidence


class AuditTests(unittest.TestCase):
    def test_exact_frozen_decisions_across_contrast_noise_and_scale(self):
        y, x = np.indices((181, 237)); rng = np.random.default_rng(7)
        support = ((x-118)/110)**2 + ((y-90)/82)**2 < 1
        for amplitude in [0, 4, 22]:
            g = np.clip(128+amplitude*np.sin(2*np.pi*(x+.3*y)/8)+rng.normal(0, 2, x.shape), 0, 255).astype(np.uint8)
            before = g.copy()
            for size in [96, 512]:
                result = audit_ridge_level(g, support, size)
                _, frozen = ridge_evidence(g, support, max_side=size)
                for key in ['credible_windows', 'eligible_windows', 'status']:
                    self.assertEqual(result[key], frozen[key])
                self.assertEqual(sum(result['failure_combinations'].values()), result['eligible_windows'])
                self.assertTrue(all(n >= result['credible_windows'] for n in result['credible_windows_if_one_gate_removed'].values()))
            np.testing.assert_array_equal(before, g)

    def test_low_amplitude_periodic_pattern_rejected_by_absolute_contrast(self):
        _, x = np.indices((160, 160)); g = (128+4*np.sin(2*np.pi*x/8)).astype(np.uint8)
        result = audit_ridge_level(g, np.ones(g.shape, bool), 512)
        self.assertEqual(result['credible_windows'], 0)
        self.assertGreater(result['credible_windows_if_one_gate_removed']['contrast'], 4)

    def test_small_roi_is_sampling_failure_not_negative(self):
        g = np.full((120, 140), 128, np.uint8)
        result = audit_pitch_sampling(g, np.ones(g.shape, bool))
        self.assertEqual(result['grid_centers'], 0)
        self.assertTrue(result['geometry_cannot_reach_required_patches'])
        self.assertTrue(result['no_periodicity_is_not_absence'])

    def test_linear_illumination_leakage_isolated_without_gate_changes(self):
        _, x = np.indices((64, 64))
        g = (25+3*x+12*np.sin(2*np.pi*x/8)).astype(np.uint8)
        result = audit_ridge_level(g, np.ones(g.shape, bool), 512)
        self.assertEqual(result['credible_windows'], 0)
        self.assertEqual(result['failure_combinations'], {'radial_concentration':9})
        self.assertEqual(result['planar_detrended_credible_windows'], 9)
        self.assertEqual(result['status'], 'ridge_evidence_insufficient')

    def test_shape_and_dtype_validation(self):
        g = np.zeros((32, 32), np.uint8)
        for mask in [np.ones((31, 32), bool), np.ones(g.shape, np.uint8), np.zeros(g.shape, bool)]:
            with self.assertRaises(ValueError): audit_ridge_level(g, mask, 512)
        for size in [0, -1, float('inf'), True]:
            with self.assertRaises(ValueError): audit_ridge_level(g, np.ones(g.shape, bool), size)


if __name__ == '__main__': unittest.main()
