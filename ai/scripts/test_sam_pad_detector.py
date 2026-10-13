"""Synthetic input, subset, geometry and signature tests; no human annotation."""
import unittest
import tempfile,json
from pathlib import Path
import numpy as np
from PIL import Image
from sam_pad_detector import clean_mask,extract_pad_candidates,load_finger_masks,digest
from evaluate_sam_pad import signature


def finger(shape=(180,160),center=50):
    y,x=np.indices(shape);return (((x-center)/18)**2+((y-85)/72)**2<=1)&(y<145)

class PadTests(unittest.TestCase):
    def test_empty_rejected(self):
        p,q=clean_mask(np.zeros((20,20),bool));self.assertIsNone(p);self.assertEqual(q['reject_reason'],'empty_finger_mask')
    def test_multi_component_rejected(self):
        m=np.zeros((20,40),bool);m[2:10,2:10]=True;m[2:10,25:33]=True;p,q=clean_mask(m);self.assertIsNone(p)
    def test_tiny_detached_speck_cleaned(self):
        m=finger();m[0,0]=True;p,q=clean_mask(m);self.assertFalse(p[0,0]);self.assertTrue((p&~m).sum()==0)
    def test_native_shape_and_subset(self):
        m=finger();rgb=np.full((*m.shape,3),160,np.uint8);r=extract_pad_candidates(rgb,[m]);self.assertEqual(r['mask'].shape,m.shape);self.assertTrue(r['mask'].any());self.assertFalse((r['mask']&~m).any());self.assertFalse(r['approved_for_use'])
    def test_multiple_fingers(self):
        a=finger(center=40);b=finger(center=110);r=extract_pad_candidates(np.full((180,160,3),160,np.uint8),[a,b]);self.assertEqual(len(r['regions']),2);self.assertFalse((r['mask']&~(a|b)).any())
    def test_rotated_coordinate_geometry(self):
        m=np.rot90(finger());rgb=np.full((*m.shape,3),160,np.uint8);r=extract_pad_candidates(rgb,[m]);self.assertTrue(r['mask'].any());self.assertFalse((r['mask']&~m).any())
    def test_repeat_signature(self):
        m=finger();rgb=np.full((*m.shape,3),160,np.uint8);self.assertEqual(signature(extract_pad_candidates(rgb,[m])),signature(extract_pad_candidates(rgb,[m])))
    def test_wrong_shape(self):
        with self.assertRaisesRegex(ValueError,'shape_mismatch'):extract_pad_candidates(np.zeros((50,50,3),np.uint8),[np.zeros((49,50),bool)])
    def test_nonboolean_rejected(self):
        with self.assertRaises(ValueError):extract_pad_candidates(np.zeros((50,50,3),np.uint8),[np.zeros((50,50),np.uint8)])
    def test_source_mask_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'synthetic.png';Image.fromarray(np.full((180,160,3),160,np.uint8)).save(source);mask=root/'finger.png';Image.fromarray(finger().astype(np.uint8)*255).save(mask)
            data=dict(schema_version='sam-finger-input-v1',source_sha256=digest(source),coordinate_system='encoded_original_pixels',image_width=160,image_height=180,masks=[dict(mask_path='finger.png',mask_sha256=digest(mask))]);manifest=root/'sam.json';manifest.write_text(json.dumps(data));rgb,masks,_=load_finger_masks(source,manifest);self.assertEqual(len(masks),1)
            data['source_sha256']='0'*64;manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):load_finger_masks(source,manifest)

    def test_rgb_hint_resolves_axis_sign(self):
        m=finger();rgb=np.full((*m.shape,3),160,np.uint8)
        r=extract_pad_candidates(rgb,[m],tip_hints=[[50,14]])
        self.assertTrue(r['regions'][0]['quality']['RGB_tip_hint_used']);self.assertGreater(r['regions'][0]['axis_xy'][1],0)
        r=extract_pad_candidates(rgb,[m],tip_hints=[[50,140]])
        self.assertTrue(r['regions'][0]['quality']['RGB_tip_hint_used']);self.assertLess(r['regions'][0]['axis_xy'][1],0)
    def test_bad_hint_rejected(self):
        m=finger();rgb=np.full((*m.shape,3),160,np.uint8)
        with self.assertRaisesRegex(ValueError,'invalid_RGB_tip_hint'):extract_pad_candidates(rgb,[m],tip_hints=[[10000,0]])
    def test_tip_metadata_in_bounds(self):
        m=finger();r=extract_pad_candidates(np.full((*m.shape,3),160,np.uint8),[m]);x,y=r['regions'][0]['tip_xy'];self.assertTrue(0<=x<m.shape[1] and 0<=y<m.shape[0])

if __name__=='__main__':unittest.main()

class ForegroundRefinementTests(unittest.TestCase):
    def test_contaminated_frame_refined_to_rgb_foreground(self):
        from sam_pad_detector import refine_edge_connected_foreground
        rgb=np.full((240,320,3),100,np.uint8);rgb[30:210,25:290]=[180,110,90]
        mask=np.ones((240,320),bool)
        refined,meta=refine_edge_connected_foreground(rgb,mask)
        self.assertTrue(meta['applied']);self.assertFalse((refined&~mask).any())
        self.assertTrue(refined[100,100]);self.assertFalse(refined[2,2])
        repeat,other=refine_edge_connected_foreground(rgb,mask)
        np.testing.assert_array_equal(refined,repeat);self.assertEqual(meta,other)

    def test_localized_foreground_left_unchanged(self):
        from sam_pad_detector import refine_edge_connected_foreground
        mask=finger();rgb=np.full((*mask.shape,3),100,np.uint8)
        refined,meta=refine_edge_connected_foreground(rgb,mask)
        np.testing.assert_array_equal(refined,mask);self.assertFalse(meta['applied'])

    def test_uniform_full_frame_does_not_invent_skin(self):
        from sam_pad_detector import refine_edge_connected_foreground
        rgb=np.full((100,100,3),100,np.uint8);mask=np.ones((100,100),bool)
        refined,meta=refine_edge_connected_foreground(rgb,mask)
        np.testing.assert_array_equal(refined,mask);self.assertFalse(meta['applied'])
