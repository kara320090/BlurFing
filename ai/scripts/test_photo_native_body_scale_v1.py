import math,unittest
import numpy as np
from photo_native_body_scale_v1 import observe_width,plan_scale


class NativeBodyScaleTests(unittest.TestCase):
    def test_exact_rectangle_cross_sections_and_rotation(self):
        for degrees in [0,15,45,80,90]:
            theta=math.radians(degrees);axis=np.array([math.cos(theta),math.sin(theta)]);normal=np.array([-axis[1],axis[0]])
            yy,xx=np.mgrid[:201,:201];points=np.stack([yy-100,xx-100],axis=-1)
            body=(np.abs(points@axis)<=80)&(np.abs(points@normal)<20);pad=np.zeros_like(body);pad[100,100]=True
            result=observe_width(pad,body,axis);self.assertFalse(result['boundary_unobserved']);self.assertAlmostEqual(result['observed_native_body_width'],40,delta=1.5)
            rotated=observe_width(np.rot90(pad),np.rot90(body),[-axis[1],axis[0]])
            self.assertAlmostEqual(result['observed_native_body_width'],rotated['observed_native_body_width'],places=9)

    def test_fragment_thickness_does_not_set_finger_scale(self):
        body=np.zeros((201,201),bool);body[10:191,80:120]=True
        widths=[]
        for side in [1,3,11]:
            pad=np.zeros_like(body);pad[100:100+side,90:90+side]=True
            result=plan_scale(pad,body,[1.,0.],1);self.assertEqual(result['status'],'planned');widths.append(result['working_scale'])
        self.assertEqual(widths,[10.,10.,10.])

    def test_source_clipping_and_missing_body_do_not_invent_width(self):
        body=np.ones((40,40),bool);pad=np.zeros_like(body);pad[20,20]=True
        plan=plan_scale(pad,body,[1.,0.],1);self.assertEqual(plan['reject_reason'],'native_body_width_boundary_unobserved')
        with self.assertRaisesRegex(ValueError,'native_pad_body'):observe_width(pad,np.zeros_like(body),[1.,0.])

    def test_bad_axis_is_controlled_rejection_and_inputs_unchanged(self):
        body=np.zeros((50,60),bool);body[5:45,10:50]=True;pad=np.zeros_like(body);pad[25,30]=True;before=pad.copy()
        for axis in [[0,0],[float('nan'),1],[1],None]:
            with self.assertRaisesRegex(ValueError,'axis_contract'):observe_width(pad,body,axis)
        np.testing.assert_array_equal(pad,before)


if __name__=='__main__':unittest.main()
