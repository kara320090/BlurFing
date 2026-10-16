import unittest
from unittest.mock import patch
import numpy as np
from photo_synthetic_residual_audit_v1 import inspect_region


class ResidualAuditTests(unittest.TestCase):
    def test_retained_and_independent_ridges_are_distinguished(self):
        yy, xx = np.mgrid[:300, :300]
        mask = ((yy-150)**2+(xx-150)**2) < 130**2
        source = np.repeat((170+8*np.sin(yy*2*np.pi/8))[:, :, None], 3, axis=2).astype(np.uint8)
        other = np.repeat((170+8*np.sin(xx*2*np.pi/11))[:, :, None], 3, axis=2).astype(np.uint8)
        copied = inspect_region(source, source.copy(), mask)
        replaced = inspect_region(source, other, mask)
        self.assertGreater(copied['review_flags'], 10)
        self.assertEqual(replaced['review_flags'], 0)
        self.assertFalse(replaced['privacy_validated'])
        self.assertFalse(replaced['coverage_verified'])

    def test_constant_texture_is_inconclusive_and_outside_is_ignored(self):
        image = np.full((200, 200, 3), 150, np.uint8); mask = np.zeros((200, 200), bool)
        mask[20:180, 20:180] = True
        a = inspect_region(image, image, mask)
        self.assertEqual(a['usable_windows'], 0)
        self.assertGreater(a['insufficient_detail_windows'], 0)
        other = image.copy(); other[~mask] = [0, 255, 0]
        self.assertEqual(a, inspect_region(image, other, mask))
        with self.assertRaises(ValueError): inspect_region(image.astype(float), image, mask)
        huge = np.broadcast_to(np.uint8(0), (8192, 4097, 3))
        huge_mask = np.broadcast_to(np.bool_(True), huge.shape[:2])
        with patch('photo_synthetic_residual_audit_v1.np.nonzero', side_effect=AssertionError('allocation before guard')):
            with self.assertRaisesRegex(ValueError, 'raster_limit'):
                inspect_region(huge, huge, huge_mask)


if __name__ == '__main__':
    unittest.main()
