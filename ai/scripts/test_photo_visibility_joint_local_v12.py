import unittest
from unittest.mock import patch
import numpy as np
import test_photo_visibility_raw_witness_probe_v9 as fixtures
import photo_visibility_joint_witness_v11 as v11
import photo_visibility_local_direction_v12 as v12


class JointWitnessTests(fixtures.RawWitnessTests):
    module = v11

    def setUp(self):
        self.binding = patch.object(fixtures, 'probe_level', self.module.probe_level)
        self.binding.start()
        self.addCleanup(self.binding.stop)

    def test_monotonic_wavy_ramp_is_not_four_raw_crests(self):
        x = np.arange(56, dtype=float)
        raw = 30 + 1.05 * 2 * np.pi * .8 / 4 * x + .8 * np.sin(2 * np.pi * x / 4)
        self.assertTrue(np.all(np.diff(raw) > 0))
        self.assertIsNone(v11.joint_train(raw, raw, 4))
        raw = 70 + .2 * x + 4 * np.sin(2 * np.pi * x / 8)
        self.assertIsNotNone(v11.joint_train(raw, raw, 8))

    def test_actual_local_train_and_minimum_cycles(self):
        x = np.arange(56, dtype=float)
        def crests(centers):
            return 128 + sum(6 * np.exp(-((x - c) / 1.2) ** 2) for c in centers)
        raw = crests((8, 16, 24, 32, 48, 53))
        r = v11.joint_train(raw, raw, 8)
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r['matched_crest_count'], 4)
        self.assertIsNone(v11.joint_train(crests((8, 16, 24, 32)), crests((24, 32, 40, 48)), 8))
        self.assertIsNone(v11.joint_train(crests((8, 16, 24)), crests((8, 16, 24)), 8))

    def test_half_cycle_is_not_same_crests(self):
        x = np.arange(56, dtype=float)
        a = 128 + 8 * np.cos(2 * np.pi * x / 8)
        b = 128 - 8 * np.cos(2 * np.pi * x / 8)
        self.assertIsNone(v11.joint_train(a, b, 8))

    def test_direction_uses_actual_local_support(self):
        y, x = np.indices((64, 64), dtype=float)
        ridge = 128 + 8 * np.cos(2 * np.pi * x / 8)
        r = v12.local_direction(ridge, 0., [8, 40])
        self.assertGreater(r['local_direction_alignment'], .99)
        self.assertLess(v12.local_direction(ridge.T, 0., [8, 40])['local_direction_alignment'], -.99)
        changed = ridge.copy(); changed[y < 20] += 60 * np.sin(y[y < 20])
        self.assertEqual(r, v12.local_direction(changed, 0., [8, 40]))


class LocalDirectionTests(JointWitnessTests):
    module = v12


if __name__ == '__main__':
    unittest.main()
