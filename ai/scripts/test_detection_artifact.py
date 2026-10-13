"""Synthetic contract tests: never use or publish biometric inputs."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from detection_artifact import SCHEMA,digest,read_input,validate_artifact,transform_artifact,write_detection

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.folder=Path(tempfile.mkdtemp(prefix='blurfing_artifact_contract_'));self.source=self.folder/'input.png';Image.new('RGB',(128,128),(160,120,100)).save(self.source);rgb,h,exif=read_input(self.source)
        self.mask=np.zeros((128,128),bool);self.mask[35:85,35:85]=True;Image.fromarray(self.mask.astype(np.uint8)*255).save(self.folder/'mask.png')
        self.data=dict(schema_version=SCHEMA,source_sha256=h,decoded_rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),image_width=128,image_height=128,exif_orientation_applied=exif,status='accepted',mask_path='mask.png',mask_sha256=digest(self.folder/'mask.png'),regions=[dict(roi_xyxy=[24,24,104,104],seed_roi=[40,40,80,80],pitch_native=8.,mask_path='mask.png',mask_sha256=digest(self.folder/'mask.png'),region_id='test',quality={})])
        self.path=self.folder/'detection.json';self.save()
    def save(self):self.path.write_text(json.dumps(self.data))
    def invalid(self):
        self.save()
        with self.assertRaises((ValueError,OSError)):validate_artifact(self.source,self.path)
    def test_valid(self):self.assertEqual(validate_artifact(self.source,self.path)[2].sum(),2500)
    def test_source_hash(self):self.data['source_sha256']='0'*64;self.invalid()
    def test_shape(self):self.data['image_width']=127;self.invalid()
    def test_corrupt_mask(self):self.data['mask_sha256']='0'*64;self.invalid()
    def test_empty_mask(self):Image.new('L',(128,128),0).save(self.folder/'mask.png');self.data['mask_sha256']=digest(self.folder/'mask.png');self.invalid()
    def test_outside_roi(self):self.data['regions'][0]['roi_xyxy']=[40,40,100,100];self.invalid()
    def test_roi_outside_image(self):self.data['regions'][0]['roi_xyxy']=[-1,0,80,81];self.invalid()
    def test_nonbinary(self):Image.new('L',(128,128),127).save(self.folder/'mask.png');self.data['mask_sha256']=digest(self.folder/'mask.png');self.invalid()
    def test_path_escape(self):self.data['mask_path']='../mask.png';self.invalid()
    def test_seed_outside_mask(self):self.data['regions'][0]['seed_roi']=[0,0,20,20];self.invalid()
    def test_windows_path_escape(self):self.data['mask_path']='C:'+chr(92)+'mask.png';self.invalid()
    def test_invalid_pitch(self):self.data['regions'][0]['pitch_native']=float('nan');self.invalid()
    def test_strength_zero(self):rgb,_,_=read_input(self.source);out,d=transform_artifact(self.source,self.path,0.);self.assertTrue(np.array_equal(rgb,out));self.assertFalse(d['applied'])
    def test_rejected_return(self):self.data['status']='rejected';self.data['regions']=[];Image.new('L',(128,128),0).save(self.folder/'mask.png');self.data['mask_sha256']=digest(self.folder/'mask.png');self.save();rgb,_,_=read_input(self.source);out,d=transform_artifact(self.source,self.path);self.assertTrue(np.array_equal(rgb,out))
    def test_exif(self):
        p=self.folder/'orientation.jpg';exif=Image.Exif();exif[274]=6;Image.new('RGB',(80,120),(160,120,100)).save(p,exif=exif);rgb,h,applied=read_input(p);self.assertEqual(rgb.shape,(80,120,3));self.assertTrue(applied)
    def test_exception_restores_renderer_and_bindings(self):
        import transform_automatic_fingerprint_poc_v4 as frozen
        import whole_pad_skin_relief as renderer
        import fingerprint_structure_check as structure
        old=(frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job,frozen.render_whole_pad_candidate)
        with patch('protect_visible_pad_checked_v2.observed_seed_pitch',return_value=(8.,{},np.zeros((512,512),np.uint8))),patch.object(frozen,'transform_fingerprint_photo',side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):transform_artifact(self.source,self.path)
        now=(frozen.detect_fingertips,frozen.propose_visible_pad,renderer.propose_visible_pad,structure.OUT,structure.run_matcher_job,frozen.render_whole_pad_candidate)
        self.assertEqual(old,now)

    def test_deterministic_rejected_artifact(self):
        result=dict(detector_version='synthetic-test',regions=[],rejected=[],detection_seconds=0.)
        with patch('detection_artifact.detect_boundaries',return_value=result):
            a=write_detection(self.source,self.folder/'a');b=write_detection(self.source,self.folder/'b')
        ja=json.loads(a.read_text());jb=json.loads(b.read_text());ja.pop('timing',None);jb.pop('timing',None);self.assertEqual(ja,jb);self.assertEqual(a.read_bytes(),b.read_bytes());self.assertEqual((a.parent/'fingerprint_mask.png').read_bytes(),(b.parent/'fingerprint_mask.png').read_bytes())

if __name__=='__main__':unittest.main()
