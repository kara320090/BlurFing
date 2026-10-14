import unittest
import numpy as np
from ridge_evidence_frontend import axial_summary,ridge_evidence


def axis_error(a,b):return abs(((a-b+np.pi/2)%np.pi)-np.pi/2)


class AxialTests(unittest.TestCase):
    def test_wrapped_axes_and_cancellation(self):
        summary=axial_summary(np.deg2rad(np.array([89.,-89.])))
        self.assertLess(axis_error(summary['orientation'],np.pi/2),1e-10)
        for dtype in [np.float32,np.float64]:
            cancelled=axial_summary(np.array([0,np.pi/2],dtype=dtype))
            self.assertIsNone(cancelled['orientation'])
        for bad in [[],[np.nan],[np.inf],[1j]]:
            with self.assertRaises(ValueError):axial_summary(bad)
        for value in [1e308,np.finfo(float).max]:
            with self.assertRaisesRegex(ValueError,'axial_angle_numeric_overflow'):axial_summary([value])

    def test_near_horizontal_ridges_report_near_vertical_normal(self):
        y,x=np.indices((128,128));gray=np.rint(127+70*np.cos(2*np.pi*(y+.02*np.abs(x-63.5))/8)).astype(np.uint8)
        support,quality=ridge_evidence(gray)
        self.assertTrue(support.all());self.assertEqual(quality['credible_windows'],49)
        self.assertEqual(quality['pitch_native'],8.);self.assertEqual(quality['status'],'ridge_observed')
        self.assertLess(axis_error(quality['orientation'],np.pi/2),.01)
        self.assertEqual(quality['orientation_units'],'radians')

    def test_quarter_turn_preserves_mask_pitch_and_rotates_axis(self):
        y,x=np.indices((128,128));gray=np.rint(127+70*np.cos(2*np.pi*(y+.02*np.abs(x-63.5))/8)).astype(np.uint8)
        mask,q=ridge_evidence(gray);rotated,qr=ridge_evidence(np.rot90(gray).copy())
        np.testing.assert_array_equal(mask,np.rot90(rotated,-1))
        self.assertEqual(q['credible_windows'],qr['credible_windows']);self.assertEqual(q['pitch_native'],qr['pitch_native'])
        self.assertLess(axis_error(qr['orientation'],q['orientation']+np.pi/2),.01)


if __name__=='__main__':unittest.main()
