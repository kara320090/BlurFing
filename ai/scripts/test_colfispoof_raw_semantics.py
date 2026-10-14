"""Geometry/consensus tests require neither TensorFlow nor private inputs."""
import ast,unittest
import numpy as np
import cv2
from colfispoof_raw_semantics import prepare,restore,vote_masks,FINGERTIP_CLASS

class RawSemanticTests(unittest.TestCase):
    def test_class_id(self):self.assertEqual(FINGERTIP_CLASS,2)
    def test_all_rotations_full_foreground_and_background(self):
        rgb=np.zeros((97,143,3),np.uint8)
        for k in range(4):
            padded,g=prepare(np.rot90(rgb,-k),128)
            for v in [0,2]:
                labels=np.full((256,256),v,np.uint8);mask=restore(labels,g,k)
                self.assertEqual(mask.shape,rgb.shape[:2]);self.assertEqual(bool(mask.all()),v==2)
    def test_odd_padding(self):
        p,g=prepare(np.zeros((5,10,3),np.uint8),11)
        self.assertEqual(p.shape[:2],(10,11));self.assertEqual(g['scaled_height'],6);self.assertEqual(g['top'],2)
    def test_rotation_inverse_pixel_locations(self):
        # No resize/padding needed in this exact-resolution geometry fixture.
        expected=np.zeros((20,30),bool);expected[2:7,19:27]=True
        for k in range(4):
            rot=np.rot90(expected,-k);h,w=rot.shape
            g=dict(native_width=w,native_height=h,padded_width=w,padded_height=h,scaled_width=w,scaled_height=h,left=0,top=0)
            self.assertTrue(np.array_equal(restore(rot.astype(np.uint8)*2,g,k),expected))
    def test_upstream_positional_resize_semantics(self):
        rgb=np.random.default_rng(0).integers(0,256,(300,400,3),dtype=np.uint8)
        padded,g=prepare(rgb,128)
        expected=cv2.resize(rgb,(128,96),cv2.INTER_AREA)
        self.assertTrue(np.array_equal(padded[16:112],expected))
        self.assertTrue(np.array_equal(expected,cv2.resize(rgb,(128,96),interpolation=cv2.INTER_LINEAR)))
    def test_fixed_two_votes(self):
        masks=[np.array([[1,1,1,1]],bool),np.array([[0,1,1,1]],bool),np.array([[0,0,1,1]],bool),np.array([[0,0,0,1]],bool)]
        self.assertTrue(np.array_equal(vote_masks(masks),[[False,True,True,True]]))
        self.assertTrue(np.array_equal(vote_masks(masks,4),[[False,False,False,True]]))
    def test_class_one_excluded(self):
        _,g=prepare(np.zeros((32,32,3),np.uint8),32)
        self.assertFalse(restore(np.ones((32,32),np.uint8),g,0).any())
    def test_inference_worker_rejects_GT_metadata_before_runtime(self):
        from run_colfispoof_raw import run
        with self.assertRaisesRegex(ValueError,'no_GT_metadata'):
            run([dict(sample_id='TEST',source='unused',source_sha256='unused',GT_folder='forbidden')],None,None,None)
    def test_shape_contract(self):
        with self.assertRaises(ValueError):vote_masks([np.zeros((1,1))]*3)
        with self.assertRaises(ValueError):vote_masks([np.zeros((1,1))]*3+[np.zeros((2,1))])

if __name__=='__main__':unittest.main()
