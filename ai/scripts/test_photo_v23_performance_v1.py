import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_junction_fit_runtime_v1 as runtime
from photo_junction_appearance_v23 import cell_grid, design, fit_patch, refine


class PerformanceParityTests(unittest.TestCase):
    def assert_models_equal(self, expected, actual):
        self.assertEqual(len(expected), len(actual))
        for a, b in zip(expected, actual):
            if a is None:
                self.assertIsNone(b)
                continue
            self.assertEqual(a.keys(), b.keys())
            for key in a:
                if isinstance(a[key], np.ndarray):
                    np.testing.assert_array_equal(a[key], b[key])
                else:
                    self.assertEqual(a[key], b[key])

    def test_real_fits_exact_order_and_worker_exception_cleanup(self):
        cells = cell_grid(32.)
        q = np.array([.45, 2., 1.3, 1.8, -1., 8.])
        coeff = np.array([[60,70,75],[1,1,1],[0,0,0],[115,65,40],[1,1,1],
                          [0,0,0],[-12,-16,-18],[2,2,2],[-2,-2,-2],[-18,-16,-14]])
        means = (design(cells, q, 32.)[0] @ coeff).mean(axis=1)
        tasks = [(means, cells, 32.), (np.full((169, 3), 150.), cells, 32.)]
        expected = runtime.fit_patches(tasks, fit_patch)
        self.assertIsNotNone(expected[0])
        self.assertIsNone(expected[1])
        with runtime.fit_session(2):
            self.assert_models_equal(expected, runtime.fit_patches(tasks, fit_patch))
            self.assert_models_equal(expected, runtime.fit_patches(tasks, fit_patch))
        with self.assertRaisesRegex(ValueError, 'junction_cell_contract'):
            with runtime.fit_session(2):
                runtime.fit_patches([(means[:1], cells, 32.)] * 2, fit_patch)
        self.assertIsNone(runtime._session.get())
        with runtime.fit_session(1):
            self.assert_models_equal(expected, runtime.fit_patches(tasks, fit_patch))

    def test_parallel_final_pixels_and_metadata_exact_with_unsupported_nodes(self):
        from test_photo_junction_appearance_v23 import JunctionTests
        source, generated, mask = JunctionTests.scene()
        # A translated crop also places some measured patches outside the frame.
        for cut in (0, 60):
            src, gen, allowed = source[:, cut:], generated[:, cut:], mask[:, cut:]
            expected, meta = refine(src, gen, allowed, 147.)
            with runtime.fit_session(2):
                actual, actual_meta = refine(src, gen, allowed, 147.)
            np.testing.assert_array_equal(expected, actual)
            self.assertEqual(meta, actual_meta)
            np.testing.assert_array_equal(actual[~allowed], gen[~allowed])

    def test_pool_is_lazy_bounded_and_restored_after_failure(self):
        with patch.object(runtime, 'ProcessPoolExecutor', side_effect=AssertionError('unexpected pool')):
            with runtime.fit_session():
                self.assertEqual([], runtime.fit_patches([], fit_patch))
            with runtime.fit_session(1):
                self.assertEqual([3, 7], runtime.fit_patches([(1,2), (3,4)], lambda a,b:a+b))
        for value in (0, 9, True, 1.5):
            with self.assertRaisesRegex(ValueError, 'junction_worker_limit'):
                with runtime.fit_session(value):
                    pass
        with runtime.fit_session(1):
            with self.assertRaisesRegex(ValueError, 'already_active'):
                with runtime.fit_session(1):
                    pass
        self.assertIsNone(runtime._session.get())
        with self.assertRaisesRegex(ValueError, 'junction_task_limit'):
            runtime.fit_patches([None]*97, fit_patch)

    def test_base_reuse_matches_uncached_multiple_components_and_memory_fallback(self):
        import photo_synthetic_replacement_v19 as module
        from test_photo_synthetic_replacement_v2 import SyntheticV2Tests
        rgb, mask, _, _ = SyntheticV2Tests().fixture()
        labels = mask.astype(np.uint16)
        y, x = np.nonzero(mask)
        labels[y[x > np.median(x)], x[x > np.median(x)]] = 3
        old_rgb, old_labels = rgb.copy(), labels.copy()
        with patch.object(module, 'MAX_REUSED_BASE_BYTES', 0):
            expected, meta = module.render(rgb, mask, labels, seed=91)
        # Partial caching and full caching exercise association and fallback.
        for budget in (int((labels == 1).sum())*3*8, 64*1024*1024):
            with patch.object(module, 'MAX_REUSED_BASE_BYTES', budget):
                actual, actual_meta = module.render(rgb, mask, labels, seed=91)
            np.testing.assert_array_equal(expected, actual)
            self.assertEqual(meta, actual_meta)
        np.testing.assert_array_equal(old_rgb, rgb)
        np.testing.assert_array_equal(old_labels, labels)
        np.testing.assert_array_equal(actual[~mask], rgb[~mask])

    def test_candidate_artifacts_are_masks_and_never_protected_RGB(self):
        from protect_photo_pitch_free_v1 import candidate_artifacts, run
        rgb = np.full((32, 48, 3), 150, np.uint8)
        mask = np.zeros(rgb.shape[:2], bool); mask[8:24, 12:36] = True
        before = mask.copy(); before[25, 12:36] = True
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report, _ = candidate_artifacts(rgb, mask, before, folder, True)
            self.assertFalse(report['protection_applied'])
            self.assertEqual(report['status'], 'candidates_only_no_protection')
            self.assertEqual({p.name for p in folder.iterdir()},
                             {'redacted_mask.png', 'before_rounding_mask.png'})
            for name, expected in [('redacted_mask.png', mask), ('before_rounding_mask.png', before)]:
                with Image.open(folder/name) as image:
                    np.testing.assert_array_equal(np.asarray(image)>0, expected)
            with self.assertRaisesRegex(ValueError, 'candidate_artifact_geometry'):
                candidate_artifacts(rgb, mask[:1], before, folder, True)
            with self.assertRaisesRegex(ValueError, 'candidate_only_flag_must_be_boolean'):
                run(folder/'x', folder/'model', folder/'registry', folder/'out', candidate_only=1)


if __name__ == '__main__':
    unittest.main()
