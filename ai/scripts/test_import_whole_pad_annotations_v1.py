import io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import numpy as np
from photo_pad_annotation_v1 import Project,digest
from import_whole_pad_annotations_v1 import import_archive,verify_archive,snapshot


class ReviewedImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        image=self.root/'fixture.png';exif=Image.Exif();exif[274]=6
        rgb=np.arange(30*40*3,dtype=np.uint8).reshape(30,40,3);Image.fromarray(rgb).save(image,exif=exif)
        upright=Image.fromarray(rgb).transpose(Image.Transpose.ROTATE_270)
        row=dict(source_id='SYNTH-UNIT',source_path=str(image),source_sha256=digest(image.read_bytes()),
            width=40,height=30,exif_orientation=6,encoded_RGB_sha256=digest(rgb.tobytes()),upright_RGB_sha256=digest(np.asarray(upright).tobytes()))
        roster=self.root/'roster.json';roster.write_text(json.dumps(dict(version='whole_pad_annotation_roster_v1',
            data_role='diagnostic_development',sources=[row])),encoding='utf-8')
        project=Project(roster,self.root/'state')
        # Simulate a human review only for this generated unit-test raster.
        project.save(row['source_id'],dict(expected_revision=0,reviewed=True,attestation=True,label='valid_positive',
            ops=[dict(mode='add',points=[[4,4],[20,4],[20,28],[4,28]])],pending_points=[],notes='',acquisition_group=''))
        exported=project.export();self.archive=project.state/'exports'/exported['filename'];self.sha=exported['sha256']

    def rewritten(self,changes=None,extra=None):
        with zipfile.ZipFile(self.archive) as z:assets={n:z.read(n) for n in z.namelist()}
        if changes:changes(assets)
        hashes={n:digest(v) for n,v in assets.items() if n!='files.sha256.json'}
        assets['files.sha256.json']=json.dumps(hashes).encode()
        if extra:assets.update(extra)
        path=self.root/'rewritten.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in assets.items():z.writestr(name,data)
        return path,digest(path.read_bytes())

    def test_exact_reviewed_export_import_preserves_all_member_bytes(self):
        before=self.archive.read_bytes();output=self.root/'imported';report=import_archive(self.archive,self.sha,output)
        self.assertEqual(report['source_count'],1);self.assertTrue(report['polygon_mask_exact'])
        with zipfile.ZipFile(self.archive) as z:
            for name in z.namelist():self.assertEqual((output/name).read_bytes(),z.read(name))
        self.assertEqual(self.archive.read_bytes(),before)
        with self.assertRaises(FileExistsError):import_archive(self.archive,self.sha,output)

    def test_wrong_archive_hash_leaves_no_published_dataset(self):
        output=self.root/'bad'
        with self.assertRaisesRegex(ValueError,'archive_hash'):import_archive(self.archive,'0'*64,output)
        self.assertFalse(output.exists());self.assertFalse(list(self.root.glob('.whole-pad-import-*')))

    def test_unsafe_member_is_rejected_even_with_matching_outer_hash(self):
        path,sha=self.rewritten(extra={'../escaped.txt':b'bad'})
        with self.assertRaisesRegex(ValueError,'member_contract'):verify_archive(path,sha)
        self.assertFalse((self.root.parent/'escaped.txt').exists())

    def test_group_provenance_disagreement_is_rejected(self):
        def change(assets):
            name='annotation_roster.private.json';roster=json.loads(assets[name]);roster['sources'][0]['acquisition_group']='invented-group';assets[name]=json.dumps(roster).encode()
        path,sha=self.rewritten(change)
        with self.assertRaisesRegex(ValueError,'group_binding'):verify_archive(path,sha)

    def test_synthetic_not_accepted_as_human_GT(self):
        def change(assets):
            name='annotation_roster.private.json';roster=json.loads(assets[name]);roster['data_role']='synthetic_fixture';assets[name]=json.dumps(roster).encode()
        path,sha=self.rewritten(change)
        with self.assertRaisesRegex(ValueError,'human_development'):verify_archive(path,sha)

    def test_rehashed_raster_that_differs_from_reviewed_polygon_is_rejected(self):
        def change(assets):
            folder='ground_truth_training/SYNTH-UNIT/';name=folder+'ground_truth_mask.png'
            im=Image.open(io.BytesIO(assets[name]));im.putpixel((0,0),255);stream=io.BytesIO();im.save(stream,format='PNG');assets[name]=stream.getvalue()
            meta=json.loads(assets[folder+'source.json']);meta['mask_sha256']=digest(assets[name]);assets[folder+'source.json']=json.dumps(meta).encode()
            record=json.loads(assets[folder+'annotation.json']);record['review_assets']={n:digest(assets[folder+n]) for n in record['review_assets']};assets[folder+'annotation.json']=json.dumps(record).encode()
        path,sha=self.rewritten(change)
        with self.assertRaisesRegex(ValueError,'polygon_mask'):verify_archive(path,sha)

    def test_snapshot_remains_bound_when_original_path_is_replaced(self):
        target=self.root/'snapshot.zip';snapshot(self.archive,self.sha,target)
        self.archive.write_bytes(b'replaced after snapshot')
        report=verify_archive(target,self.sha);self.assertEqual(report['source_count'],1)


if __name__=='__main__':unittest.main()
