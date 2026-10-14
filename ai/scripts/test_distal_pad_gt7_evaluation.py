"""Synthetic annotation-status, empty-negative and integrity regression tests."""
import json,tempfile,unittest
from pathlib import Path
import numpy as np
from PIL import Image
from evaluate_distal_pad_gt7 import validate_annotation,mask_metrics,digest

class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'fixture.jpg';Image.new('RGB',(30,20),'gray').save(self.source);self.folder=self.root/'GT';self.folder.mkdir();self.mask=np.zeros((20,30),np.uint8);self.mask[5:15,5:15]=255
    def tearDown(self):self.temp.cleanup()
    def write(self,status=None,mask=True):
        m=dict(source_filename='fixture.jpg',source_sha256=digest(self.source),human_annotation=True,annotation_type='human_reviewed_fingerprint_pad',coordinate_system='encoded_original_pixels',image_width=30,image_height=20,exif_orientation=1,polygon_count=1)
        if status is not None:m['annotation_status']=status
        if mask:Image.fromarray(self.mask).save(self.folder/'ground_truth_mask.png');m['mask_sha256']=digest(self.folder/'ground_truth_mask.png')
        (self.folder/'source.json').write_text(json.dumps(m))
    def test_absent_status_nonempty_human_legacy(self):
        self.write();_,m=validate_annotation(self.folder,self.source);self.assertEqual(m['status'],'valid_positive');self.assertIsNone(m['declared_annotation_status'])
    def test_ambiguous_nonempty_never_forced_positive(self):
        self.write('ambiguous_unusable');_,m=validate_annotation(self.folder,self.source);self.assertEqual(m['status'],'ambiguous_unusable')
    def test_ambiguous_missing_mask_allowed(self):
        self.write('ambiguous_unusable',False);mask,m=validate_annotation(self.folder,self.source);self.assertIsNone(mask);self.assertEqual(m['status'],'ambiguous_unusable')
    def test_non_target_empty_allowed(self):
        self.mask[:]=0;self.write('non-target');mask,m=validate_annotation(self.folder,self.source);self.assertFalse(mask.any());self.assertEqual(m['status'],'non_target')
    def test_non_target_nonempty_fails(self):
        self.write('non-target')
        with self.assertRaises(ValueError):validate_annotation(self.folder,self.source)
    def test_empty_missing_status_unresolved(self):
        self.mask[:]=0;self.write();_,m=validate_annotation(self.folder,self.source);self.assertEqual(m['status'],'unresolved_status')
    def test_nonbinary_fails(self):
        self.mask[0,0]=42;self.write()
        with self.assertRaises(ValueError):validate_annotation(self.folder,self.source)
    def test_source_sha_mismatch(self):
        self.write();m=json.loads((self.folder/'source.json').read_text());m['source_sha256']='0'*64;(self.folder/'source.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError):validate_annotation(self.folder,self.source)
    def test_empty_negative_metrics_defined(self):
        zero=np.zeros((10,10),bool);m=mask_metrics(zero,zero);self.assertEqual(m['false_positive_components'],0);self.assertIsNone(m['recall']);self.assertEqual(m['iou'],1.)
    def test_false_component_on_empty_negative(self):
        pred=np.zeros((10,10),bool);pred[3:5,3:5]=True;m=mask_metrics(pred,np.zeros_like(pred));self.assertEqual(m['false_positive_components'],1);self.assertEqual(m['predicted_outside_GT_ratio'],1.)
