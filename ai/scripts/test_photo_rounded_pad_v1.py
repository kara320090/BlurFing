import unittest
from unittest.mock import patch
import numpy as np
from scipy import ndimage
import photo_rounded_pad_v1 as geometry


def finger(shape=(180, 140), x=70, top=20, radius=22):
    yy, xx = np.indices(shape)
    return ((np.abs(xx-x) <= radius) & (yy >= top+radius) & (yy < 160)) | (((xx-x)**2+(yy-top-radius)**2 <= radius**2) & (yy < top+radius))


class RoundedPadTests(unittest.TestCase):
    def test_distal_round_cap_cuts_shaft_and_keeps_tip(self):
        body = finger(); before = body.copy()
        cap, info = geometry.round_cap(body, [70, 100], [70, 32])
        self.assertTrue(cap[32, 70]); self.assertFalse(cap[120, 70])
        self.assertFalse(np.any(cap & ~body)); self.assertEqual(ndimage.label(cap)[1], 1)
        self.assertFalse(cap[20, 48]); self.assertTrue(cap[43, 70])
        self.assertGreater(info['reference_width'], 40); self.assertTrue(np.array_equal(before, body))

    def test_quarter_turns_and_reflection_use_the_same_geometry(self):
        body = finger(); base, _ = geometry.round_cap(body, [70, 100], [70, 32])
        rotated, _ = geometry.round_cap(np.rot90(body), [100, 139-70], [32, 139-70])
        self.assertTrue(np.array_equal(rotated, np.rot90(base)))
        reflected, _ = geometry.round_cap(np.fliplr(body), [139-70, 100], [139-70, 32])
        self.assertTrue(np.array_equal(reflected, np.fliplr(base)))

    def test_remote_blob_does_not_change_local_width(self):
        body = finger(); base, a = geometry.round_cap(body, [70, 100], [70, 32])
        body[5:155, 3:18] = True
        result, b = geometry.round_cap(body, [70, 100], [70, 32])
        self.assertTrue(np.array_equal(base, result)); self.assertEqual(a['reference_width'], b['reference_width'])

    def test_connected_lateral_spur_in_one_section_does_not_widen_cap(self):
        body = finger(); base, a = geometry.round_cap(body, [70, 100], [70, 32])
        body[81:86, 70:135] = True
        result, b = geometry.round_cap(body, [70, 100], [70, 32])
        self.assertEqual(a['reference_width'], b['reference_width'])
        self.assertFalse(result[:, 100:].any())

    def test_invalid_points_and_clipped_boundary_rejected(self):
        body = finger()
        for point in ([float('nan'), 32], [1e100, 32], [True, False], [1, 2, 3]):
            with self.assertRaises(ValueError): geometry.round_cap(body, [70, 100], point)
        with self.assertRaisesRegex(ValueError, 'positive_axis'): geometry.round_cap(body, [70, 32], [70, 32])
        with self.assertRaisesRegex(ValueError, 'outside_owner'): geometry.round_cap(body, [10, 100], [10, 32])
        with self.assertRaisesRegex(ValueError, 'clipped_by_frame'): geometry.round_cap(np.ones((180, 140), bool), [70, 100], [70, 32])

    def test_shape_dtype_and_memory_guard_precede_fit(self):
        with self.assertRaises(ValueError): geometry.round_cap(np.ones((20, 20), np.uint8), [10, 15], [10, 5])
        huge = np.broadcast_to(np.array(True), (100000, 100000))
        with patch.object(geometry, '_ray') as ray:
            with self.assertRaises(ValueError): geometry.round_cap(huge, [20, 40], [20, 20])
            ray.assert_not_called()

    def test_pose_partition_caps_replace_holes_without_reintersecting_base(self):
        shape=(180, 700);body=np.zeros(shape,bool);owners=np.zeros(shape,np.uint8);axes=[]
        for i in range(5):
            x=70+i*140;f=finger(shape,x=x);body|=f;owners[f]=i+1
            axes.append(dict(label=i+1,digit=str(i),tip_native_xy=[x,32],DIP_or_IP_native_xy=[x,100]))
        base=body.copy();base[20:70,:]=False
        result,info=geometry.rounded_pads(base,body,body,np.zeros_like(body),pose_geometry=dict(owner_labels=owners,axes=axes))
        self.assertEqual(info['applied_caps'],5);self.assertEqual(ndimage.label(result)[1],5)
        self.assertEqual(info['unresolved_candidates'],0);self.assertTrue(result[32,70]);self.assertFalse(result[120,70])
        self.assertFalse(info['learned_mask_intersection']);self.assertFalse(info['whole_photo_protection_verified'])

    def test_unresolved_pose_owner_retains_base_and_is_reported(self):
        body=np.ones((180,700),bool);owners=np.repeat(np.arange(1,6,dtype=np.uint8),140)[None].repeat(180,0)
        axes=[dict(label=i+1,digit=str(i),tip_native_xy=[70+i*140,32],DIP_or_IP_native_xy=[70+i*140,100]) for i in range(5)]
        base=np.zeros_like(body);base[10:20,10:20]=True
        result,info=geometry.rounded_pads(base,body,body,body,pose_geometry=dict(owner_labels=owners,axes=axes))
        self.assertTrue(np.array_equal(result,base));self.assertEqual(info['unresolved_candidates'],5)

    def test_binding_and_shape_mismatch_are_not_silently_repaired(self):
        body=finger();zero=np.zeros_like(body)
        with self.assertRaisesRegex(ValueError,'binding'):geometry.rounded_pads(zero,zero,body,body & (np.indices(body.shape)[0]<45))
        with self.assertRaisesRegex(ValueError,'shape_mismatch'):geometry.rounded_pads(zero,zero[:5],body,zero)
        outside=zero.copy();outside[0,0]=True
        with self.assertRaisesRegex(ValueError,'outside_body'):geometry.rounded_pads(outside,zero,body,zero)

    def test_no_pose_never_shrinks_previously_protected_pixels(self):
        body=finger();tip=body & (np.indices(body.shape)[0] < 45)
        from finger_body_distal_estimator import estimate
        coarse=estimate(body,tip)['mask']
        base=body & (np.indices(body.shape)[0] < 110)
        result,info=geometry.rounded_pads(base,coarse,body,tip)
        self.assertFalse(np.any(base & ~result));self.assertEqual(info['removed_pixels'],0)
        self.assertGreater(info['applied_caps'],0)


if __name__=='__main__':unittest.main()
