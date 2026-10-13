import unittest,tempfile,json,hashlib
from pathlib import Path
from PIL import Image
from evaluate_independent_photo import validate_manifest
class HoldoutTests(unittest.TestCase):
    def prepare(self,p,denied=None):
        Image.new('RGB',(10,10),(160,100,80)).save(p/'source.png');sha=hashlib.sha256((p/'source.png').read_bytes()).hexdigest();record=dict(sample_id='NEW-01',source=str(p/'source.png'),source_sha256=sha,capture_date='2026-10-14',participant_alias='NEW-01',not_used_for_training_or_tuning=True,independence_confirmed_by_provider=True);(p/'manifest.json').write_text(json.dumps(dict(schema_version='independent-photo-v1',samples=[record])));(p/'denied.json').write_text(json.dumps(dict(source_sha256=denied or ['a'*64])));return record,sha
    def test_valid(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.prepare(p);self.assertEqual(len(validate_manifest(p/'manifest.json',p/'denied.json')['samples']),1)
    def test_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);_,sha=self.prepare(p);(p/'denied.json').write_text(json.dumps(dict(source_sha256=[sha])))
            with self.assertRaises(ValueError):validate_manifest(p/'manifest.json',p/'denied.json')
    def test_no_provider_declaration_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);r,_=self.prepare(p);r['independence_confirmed_by_provider']=False;(p/'manifest.json').write_text(json.dumps(dict(schema_version='independent-photo-v1',samples=[r])))
            with self.assertRaises(ValueError):validate_manifest(p/'manifest.json',p/'denied.json')
if __name__=='__main__':unittest.main()
