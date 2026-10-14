import unittest
from photo_resize_safety_v1 import validate_resize,clip_bbox,ResizeSafetyError
class ResizeSafetyTests(unittest.TestCase):
    def reject(self,*args):
        with self.assertRaises(ResizeSafetyError):validate_resize(*args)
    def test_normal(self):
        shape,a=validate_resize(3000,4000,1.4356465141058579);self.assertEqual(shape,(4307,5743));self.assertEqual(a['requested_array_bytes'],4307*5743*3)
    def test_nan_inf(self):
        for v in [float('nan'),float('inf'),-float('inf')]:self.reject(100,100,v)
    def test_zero_negative(self):
        for h,w,s in [(0,100,1),(100,0,1),(-1,100,1),(100,100,0),(100,100,-1)]:self.reject(h,w,s)
    def test_huge_integer_and_estimate(self):
        self.reject(2**100,2**100,1);self.reject(2**1024,1,1);self.reject(862,726,200)
    def test_extreme_aspect(self):self.reject(1,1000000,1)
    def test_clipped_bbox(self):self.assertEqual(clip_bbox([-3,-4,120,110],100,80),[0,0,100,80])
    def test_invalid_bbox(self):
        with self.assertRaises(ValueError):clip_bbox([4,3,2,1],100,80)
    def test_determinism(self):
        reasons=[]
        for _ in range(3):
            try:validate_resize(862,726,200)
            except ResizeSafetyError as e:reasons.append((e.reason,e.audit))
        self.assertEqual(reasons[0],reasons[1]);self.assertEqual(reasons[1],reasons[2]);self.assertEqual(reasons[0][1]['requested_array_bytes'],75097440000)
if __name__=='__main__':unittest.main()
