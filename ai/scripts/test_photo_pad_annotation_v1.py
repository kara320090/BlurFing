import hashlib,io,json,tempfile,threading,unittest,urllib.request,urllib.error,zipfile
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from unittest.mock import patch
import photo_pad_annotation_v1 as annotation
from photo_pad_annotation_v1 import Project,make_server,inverse_mask,digest


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.image=self.root/'source.png';exif=Image.Exif();exif[274]=6
        data=np.zeros((60,90,3),np.uint8);data[10:40,20:50]=[180,110,80];Image.fromarray(data).save(self.image,exif=exif)
        self.roster=self.root/'roster.json';self.make_roster('synthetic_fixture')
        self.project=Project(self.roster,self.root/'private-state')

    def make_roster(self,role):
        self.roster.write_text(json.dumps(dict(version='whole_pad_annotation_roster_v1',data_role=role,sources=[dict(source_id='SYNTH-001',
            source_path=str(self.image),source_sha256=digest(self.image.read_bytes()),width=90,height=60,exif_orientation=6)])),encoding='utf-8')

    def payload(self,**kw):
        return dict(expected_revision=0,reviewed=False,attestation=False,label='valid_positive',
            ops=[dict(mode='add',points=[[5,5],[30,5],[30,50],[5,50]])],pending_points=[],notes='',acquisition_group='',**kw)

    def test_non_square_EXIF_1_to_8_masks_roundtrip_exactly(self):
        for orientation in range(1,9):
            native=Image.new('L',(90,60));native.putpixel((13,21),255);native.putpixel((80,45),255)
            exif=Image.Exif();exif[274]=orientation;native.info['exif']=exif.tobytes()
            upright=ImageOps.exif_transpose(native)
            np.testing.assert_array_equal(np.asarray(inverse_mask(upright,orientation)),np.asarray(native))

    def test_draft_never_creates_GT_and_reload_keeps_open_polygon(self):
        p=self.payload();p['pending_points']=[[12,12],[13,16]];p['pending_mode']='erase'
        record=self.project.save('SYNTH-001',p)
        self.assertFalse(record['human_annotation']);self.assertEqual(record['status'],'draft')
        self.assertFalse(list(self.project.state.rglob('ground_truth_mask.png')))
        recovered=Project(self.roster,self.project.state).current('SYNTH-001')
        self.assertEqual(recovered['pending_points'],p['pending_points'])
        self.assertEqual(recovered['pending_mode'],'erase')
        with self.assertRaisesRegex(ValueError,'no_explicitly_reviewed'):self.project.export()

    def test_explicit_human_attestation_required_and_synthetic_review_never_claims_human(self):
        p=self.payload();p['reviewed']=True
        with self.assertRaisesRegex(ValueError,'explicit_human'):self.project.save('SYNTH-001',p)
        p['attestation']='true'
        with self.assertRaisesRegex(ValueError,'explicit_human'):self.project.save('SYNTH-001',p)
        p['attestation']=True;result=self.project.save('SYNTH-001',p)
        self.assertFalse(result['human_annotation'])
        folder=self.project.folder('SYNTH-001')/'rev-000001'
        meta=json.loads((folder/'source.json').read_text(encoding='utf-8'))
        self.assertFalse(meta['human_annotation']);self.assertEqual(meta['annotation_type'],'synthetic_test_annotation')
        with Image.open(folder/'ground_truth_mask.png') as mask:self.assertEqual(mask.mode,'L');self.assertEqual(mask.size,(90,60))

    def test_empty_positive_nonempty_negative_and_ambiguous_without_reason_are_rejected(self):
        for label,ops in [('valid_positive',[]),('non_target',self.payload()['ops']),('ambiguous_unusable',[])]:
            p=self.payload();p.update(reviewed=True,attestation=True,label=label,ops=ops)
            with self.assertRaises(ValueError):self.project.save('SYNTH-001',p)
        p=self.payload();p.update(reviewed=True,attestation=True,label='non_target',ops=[])
        self.project.save('SYNTH-001',p)
        with Image.open(self.project.folder('SYNTH-001')/'rev-000001/ground_truth_mask.png') as mask:self.assertIsNone(mask.getbbox())

    def test_revision_conflict_preserves_review_and_edit_creates_separate_draft(self):
        p=self.payload();p.update(reviewed=True,attestation=True)
        self.project.save('SYNTH-001',p)
        with self.assertRaisesRegex(ValueError,'revision_conflict'):self.project.save('SYNTH-001',p)
        p.update(expected_revision=1,reviewed=False,attestation=False)
        self.project.save('SYNTH-001',p)
        self.assertEqual(self.project.current('SYNTH-001')['status'],'draft')
        self.assertTrue((self.project.folder('SYNTH-001')/'rev-000001/ground_truth_mask.png').exists())
        self.assertFalse((self.project.folder('SYNTH-001')/'rev-000002/ground_truth_mask.png').exists())

    def test_outside_nan_bool_points_and_unclosed_review_are_rejected(self):
        for point in [[60,10],[4,float('nan')],[True,10]]:
            p=self.payload();p['ops'][0]['points'][0]=point
            with self.assertRaises(ValueError):self.project.save('SYNTH-001',p)
        p=self.payload();p.update(reviewed=True,attestation=True,pending_points=[[2,3]])
        with self.assertRaisesRegex(ValueError,'open_polygon'):self.project.save('SYNTH-001',p)

    def test_interrupted_pointer_publish_preserves_orphan_and_allows_retry(self):
        p=self.payload();self.project.save('SYNTH-001',p);p['expected_revision']=1
        original=annotation.write_json
        def interrupt(path,data):
            if Path(path).name=='latest.json':raise OSError('simulated pointer interruption')
            return original(path,data)
        with patch.object(annotation,'write_json',side_effect=interrupt):
            with self.assertRaisesRegex(OSError,'simulated pointer'):self.project.save('SYNTH-001',p)
        folder=self.project.folder('SYNTH-001');orphan=(folder/'rev-000002/annotation.json').read_bytes()
        resumed=Project(self.roster,self.project.state)
        self.assertEqual(resumed.current('SYNTH-001')['revision'],1)
        result=resumed.save('SYNTH-001',p)
        self.assertEqual(result['revision'],3)
        self.assertEqual((folder/'rev-000002/annotation.json').read_bytes(),orphan)
        self.assertEqual(resumed.current('SYNTH-001')['revision'],3)

    def test_erase_and_encoded_export_are_binary_and_export_checksums_match(self):
        before=self.image.read_bytes();p=self.payload();p.update(reviewed=True,attestation=True)
        p['ops'].append(dict(mode='erase',points=[[10,10],[20,10],[20,20],[10,20]]))
        self.project.save('SYNTH-001',p);export=self.project.export();path=self.project.state/'exports'/export['filename']
        with zipfile.ZipFile(path) as z:
            checks=json.loads(z.read('files.sha256.json'))
            self.assertTrue(all(digest(z.read(n))==s for n,s in checks.items()))
            with Image.open(io.BytesIO(z.read('ground_truth_training/SYNTH-001/ground_truth_mask.png'))) as mask:
                self.assertEqual(mask.size,(90,60));self.assertTrue(set(np.unique(mask))<={0,255})
                mask.info['exif']=Image.Exif().tobytes()
                upright=mask.transpose(Image.Transpose.ROTATE_270)
                self.assertEqual(upright.getpixel((15,15)),0);self.assertEqual(upright.getpixel((8,8)),255)
        self.assertEqual(self.image.read_bytes(),before);self.assertEqual(digest(path.read_bytes()),export['sha256'])

    def test_source_and_review_asset_tamper_are_not_silently_signed(self):
        p=self.payload();p.update(reviewed=True,attestation=True);self.project.save('SYNTH-001',p)
        mask=self.project.folder('SYNTH-001')/'rev-000001/ground_truth_mask.png';mask.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):self.project.export()
        self.image.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.project.image('SYNTH-001')

    def test_changed_roster_cannot_reuse_another_annotation_project(self):
        self.make_roster('diagnostic_development')
        with self.assertRaisesRegex(ValueError,'roster_mismatch'):Project(self.roster,self.project.state)

    def test_loopback_HTTP_requires_session_host_and_origin_for_writes(self):
        server,url=make_server(self.project);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        with urllib.request.urlopen(url+'api/project') as response:self.assertEqual(json.load(response)['reviewed'],0)
        origin=url.split('/s/')[0]
        for target,headers in [(origin+'/api/project',{}),(url+'api/project',{'Host':'evil.invalid'}),(url+'api/save/SYNTH-001',{'Content-Type':'application/json'})]:
            request=urllib.request.Request(target,data=json.dumps(self.payload()).encode() if 'save' in target else None,headers=headers)
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request)
        request=urllib.request.Request(url+'api/save/SYNTH-001',data=json.dumps(self.payload()).encode(),headers={'Content-Type':'application/json','Origin':origin})
        with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['status'],'draft')


if __name__=='__main__':unittest.main()
