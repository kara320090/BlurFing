import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import photo_pose_permissions_v1 as pose
from photo_resize_safety_v1 import ResizeSafetyError


def fixture():
    body=np.ones((60,100),bool);points=np.zeros((21,2),np.float64)
    for i,(tip,dip) in enumerate(pose.PAIRS):
        points[tip]=[10+20*i,5];points[dip]=[10+20*i,20]
    return body,points


class PosePermissionTests(unittest.TestCase):
    def test_fixed_digit_labels_exact_BODY_partition_and_subsets(self):
        body,points=fixture();body[40:45,40:46]=False
        bcopy=body.copy();pcopy=points.copy();body.setflags(write=False);points.setflags(write=False)
        result=pose.pose_permissions(body,points)
        owners=result['owner_labels'];proposed=result['proposed_labels'];bound=result['permission_labels'];rejected=result['rejected_labels']
        np.testing.assert_array_equal(owners>0,body)
        np.testing.assert_array_equal((bound>0)|(rejected>0),proposed>0)
        self.assertFalse(((bound>0)&(rejected>0)).any())
        self.assertTrue(np.all((proposed==0)|(proposed==owners)))
        for label,(tip,dip) in enumerate(pose.PAIRS,1):
            x,y=points[tip].astype(int);self.assertEqual(bound[y,x],label)
        self.assertEqual(owners[10,20],1) # Exact symmetric tie keeps fixed lower label.
        self.assertEqual([r['digit'] for r in result['axes']],list(pose.DIGITS))
        self.assertFalse(result['metadata']['approved_for_protection'])
        np.testing.assert_array_equal(body,bcopy);np.testing.assert_array_equal(points,pcopy)

    def test_detached_large_neighbor_is_rejected_not_largest_component(self):
        mask=np.zeros((20,30),bool);mask[2:5,2:5]=True;mask[7:18,12:28]=True;before=mask.copy()
        bound,rejected,meta=pose.tip_connected_component(mask,[3.,3.])
        self.assertEqual(int(bound.sum()),9);self.assertTrue(rejected[10,20]);self.assertEqual(meta['connected_components'],2)
        np.testing.assert_array_equal(mask,before)

    def test_connected_neighbor_bridge_is_a_documented_counterexample(self):
        mask=np.zeros((20,30),bool);mask[2:5,2:5]=True;mask[7:18,12:28]=True
        mask[3,4:13]=True;mask[3:9,12]=True
        bound,rejected,_=pose.tip_connected_component(mask,[3.,3.])
        self.assertTrue(bound[10,20]);self.assertFalse(rejected.any())

    def test_diagonal_contact_does_not_bind_neighbor(self):
        mask=np.zeros((8,8),bool);mask[1:3,1:3]=True;mask[3:5,3:5]=True
        bound,rejected,_=pose.tip_connected_component(mask,[1.,1.])
        self.assertFalse(bound[3,3]);self.assertTrue(rejected[3,3])

    def test_invalid_axes_and_observation_membership_reject(self):
        for change,reason in [('zero','positive_finite_axis'),('outside','endpoint_out_of_frame'),
                              ('midpoint','midpoint_outside_BODY'),('tip','tip_outside_BODY')]:
            with self.subTest(change=change):
                body,points=fixture()
                if change=='zero':points[4]=points[3]
                elif change=='outside':points[4]=[-.1,5]
                elif change=='midpoint':body[13,10]=False
                else:body[5,10]=False
                with self.assertRaisesRegex(ValueError,reason):pose.pose_permissions(body,points)

    def test_invalid_numeric_points_BODY_and_tip_do_not_silently_coerce(self):
        body,points=fixture()
        for p in [np.full((21,2),np.nan),np.full((21,2),np.inf),np.ones((20,2)),np.ones((21,2),bool),np.full((21,2),'5')]:
            with self.subTest(dtype=p.dtype,shape=p.shape):
                with self.assertRaisesRegex(ValueError,'finite_numeric'):pose.pose_permissions(body,p)
        for b in [body.astype(np.uint8),body[...,None],np.zeros_like(body),np.zeros((0,2),bool)]:
            with self.subTest(shape=b.shape):
                with self.assertRaises(ValueError):pose.pose_permissions(b,points)
        for tip in [[float('nan'),3],[-1,3],[True,False],[70.,70.]]:
            with self.subTest(tip=tip):
                with self.assertRaises(ValueError):pose.tip_connected_component(body,tip)

    def test_missing_tip_never_selects_nearest_component(self):
        mask=np.zeros((10,10),bool);mask[2:4,2:4]=True
        with self.assertRaisesRegex(ValueError,'tip_not_inside_permission'):pose.tip_connected_component(mask,[6.,6.])

    def test_resource_guard_precedes_raster_scan_or_output_allocation(self):
        huge=np.broadcast_to(np.ones((1,1),bool),(8192,8192))
        _,points=fixture()
        with (patch.object(pose.np,'nonzero',side_effect=AssertionError('must reject before scan')),
                patch.object(pose.np,'zeros',side_effect=AssertionError('must reject before allocation'))):
            with self.assertRaises(ResizeSafetyError):pose.pose_permissions(huge,points)
        with self.assertRaises(ResizeSafetyError):pose.normalized_landmarks_to_native(np.zeros((21,2)),(32769,1),1)

    def test_normalized_all_EXIF_actual_PIL_pixel_ID_and_RGB_mapping(self):
        height,width=7,11;ids=np.arange(height*width,dtype=np.int32).reshape(height,width)
        rgb=np.stack([ids,ids+80,ids+160],axis=2).astype(np.uint8)
        transforms={1:None,2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,
            4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,6:Image.Transpose.ROTATE_270,
            7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}
        for exif,operation in transforms.items():
            with self.subTest(EXIF=exif):
                image=Image.fromarray(ids);color=Image.fromarray(rgb)
                if operation is not None:image=image.transpose(operation);color=color.transpose(operation)
                upright=np.asarray(image);up_rgb=np.asarray(color);uh,uw=upright.shape
                # Use independently rotated pixel IDs at edges and interior,
                # then compare every converted point to its actual source pixel.
                probes=[(0,0),(uw-1,0),(0,uh-1),(uw-1,uh-1),(uw//2,uh//2),(1,1),(uw-2,uh-2)]*3
                normalized=np.array([[(u+.5)/uw,(v+.5)/uh] for u,v in probes])
                actual=pose.normalized_landmarks_to_native(normalized,(height,width),exif)
                for (u,v),(x,y) in zip(probes,actual):
                    expected=int(upright[v,u]);ex,ey=expected%width,expected//width
                    np.testing.assert_allclose([x,y],[ex,ey],atol=1e-14,rtol=0)
                    np.testing.assert_array_equal(up_rgb[v,u],rgb[ey,ex])

    def test_finite_out_of_frame_non_axis_model_point_is_retained(self):
        normalized=np.full((21,2),.5);normalized[0]=[-.2,1.2];before=normalized.copy()
        native=pose.normalized_landmarks_to_native(normalized,(60,100),1)
        self.assertLess(native[0,0],0);self.assertGreater(native[0,1],59)
        np.testing.assert_array_equal(normalized,before)
        body,points=fixture();points[0]=[-20,90]
        self.assertEqual(len(pose.pose_permissions(body,points)['axes']),5)

    def test_normalized_contract_NaN_overflow_shapes_and_EXIF_types(self):
        points=np.zeros((21,2))
        for shape in [(0,5),(1.5,5),(True,5),(5,),[5,5,5]]:
            with self.subTest(shape=shape):
                with self.assertRaises(ValueError):pose.normalized_landmarks_to_native(points,shape)
        for exif in [0,9,True,6.0,'6']:
            with self.subTest(EXIF=exif):
                with self.assertRaises(ValueError):pose.normalized_landmarks_to_native(points,(10,20),exif)
        for bad in [np.full((21,2),np.nan),np.full((21,2),np.finfo(np.float64).max),np.zeros((21,3))]:
            with self.subTest(shape=bad.shape):
                with self.assertRaises(ValueError):pose.normalized_landmarks_to_native(bad,(10,20))


if __name__=='__main__':unittest.main()
