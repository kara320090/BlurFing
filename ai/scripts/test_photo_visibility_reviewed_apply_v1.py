import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageOps
import photo_visibility_reviewed_apply_v1 as module
from test_photo_visibility_v1 import fixture
from photo_visibility_annotation_v1 import component_map


class ReviewedApplyTests(unittest.TestCase):
    def test_explicit_appearance_keeps_review_decisions_and_default(self):
        rgb,labels,review=self.fixture()
        old,mask,old_report=module.apply_reviewed(rgb,labels,review,seed=42)
        new,new_mask,report=module.apply_reviewed(rgb,labels,review,seed=42,appearance='silhouette_v21')
        self.assertEqual(old_report['appearance'],'v19')
        self.assertEqual(report['appearance'],'silhouette_v21')
        np.testing.assert_array_equal(mask,new_mask)
        np.testing.assert_array_equal(new[~mask],rgb[~mask])
        self.assertEqual(report['applied_region_count'],old_report['applied_region_count'])
        self.assertEqual(report['review_required_count'],old_report['review_required_count'])
        self.assertTrue(all(r['region_id']==1 for r in report['appearance_report']['regions']))
        self.assertFalse(report['production_approved'])
        material,material_mask,material_report=module.apply_reviewed(rgb,labels,review,seed=42,appearance='material_v22')
        np.testing.assert_array_equal(mask,material_mask)
        np.testing.assert_array_equal(material[~mask],rgb[~mask])
        self.assertEqual(material_report['applied_region_count'],old_report['applied_region_count'])
        self.assertEqual(material_report['appearance_report']['version'],'generated_envelope_and_material_v22')
        with self.assertRaises(ValueError):module.apply_reviewed(rgb,labels,review,appearance='automatic')

    def fixture(self):
        y,x=np.indices((128,270));rgb=np.zeros((128,270,3),np.uint8)
        rgb[:]=[180,137,110];rgb=np.clip(rgb.astype(float)+3*np.sin(x*2*np.pi/8)[:,:,None],0,255).astype(np.uint8)
        labels=np.zeros((128,270),np.uint16)
        for i in range(3):labels[12:116,12+i*85:77+i*85]=i+1
        review=dict(version='explicit_visibility_review_v1',review_origin='human_confirmed',all_regions_reviewed=True,
                    coordinate_system='upright_native_pixels',RGB_sha256=module.pixels(rgb),labels_sha256=module.pixels(labels),
                    regions=[dict(region_id=i+1,decision=d) for i,d in enumerate(('visible','not_observed','uncertain'))])
        return rgb,labels,review

    def test_real_renderer_only_human_visible_whole_pad_and_determinism(self):
        rgb,labels,review=self.fixture();original=rgb.copy()
        a,mask,report=module.apply_reviewed(rgb,labels,review,seed=42)
        b,_,_=module.apply_reviewed(rgb,labels,review,seed=42)
        np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(rgb,original)
        np.testing.assert_array_equal(mask,labels==1);np.testing.assert_array_equal(a[~mask],rgb[~mask])
        self.assertGreater(np.any(a[mask]!=rgb[mask],axis=1).mean(),.5)
        self.assertEqual(report['applied_region_count'],1);self.assertEqual(report['review_required_count'],1)
        self.assertFalse(report['privacy_validated']);self.assertFalse(report['automatic_visibility_approved'])

    def test_no_visible_never_calls_renderer_for_nonempty_regions(self):
        rgb,labels,review=self.fixture()
        review['regions'][0]['decision']='uncertain'
        a,mask,report=module.apply_reviewed(rgb,labels,review,seed=42)
        np.testing.assert_array_equal(a,rgb);self.assertFalse(mask.any());self.assertEqual(report['applied_region_count'],0)

    def test_model_signal_cannot_authorize_and_binding_or_partition_changes_rejected(self):
        rgb,labels,review=self.fixture()
        bad=[]
        for key,value in [('review_origin','model_prediction'),('all_regions_reviewed',False),('RGB_sha256','0'*64),('labels_sha256','0'*64),('coordinate_system','encoded_original_pixels')]:
            r=copy.deepcopy(review);r[key]=value;bad.append(r)
        for values in [review['regions'][:-1],[review['regions'][0]]*3]:
            r=copy.deepcopy(review);r['regions']=values;bad.append(r)
        r=copy.deepcopy(review);r['regions'][0]['region_id']=True;bad.append(r)
        for r in bad:
            with self.assertRaises(ValueError):module.apply_reviewed(rgb,labels,r)

    def test_unresolved_component_rolls_back_entire_review_region(self):
        rgb,labels,review=self.fixture()
        def fake(rgb,mask,parts,seed=None):
            out=rgb.copy();out[mask]=0
            return out,dict(regions=[dict(region_id=1,fingerprint_texture_resolved=False)])
        with patch.object(module,'render',fake):a,mask,report=module.apply_reviewed(rgb,labels,review)
        np.testing.assert_array_equal(a,rgb);self.assertFalse(mask.any())
        self.assertEqual(report['regions'][0]['status'],'review_required_renderer_unresolved')

    def test_bad_renderer_cannot_change_outside_permission(self):
        rgb,labels,review=self.fixture()
        def fake(rgb,mask,parts,seed=None):return np.zeros_like(rgb),dict(regions=[])
        with patch.object(module,'render',fake),self.assertRaisesRegex(RuntimeError,'preservation'):
            module.apply_reviewed(rgb,labels,review)

    def test_diagonal_components_get_separate_renderer_labels(self):
        rgb,labels,review=self.fixture();labels[:]=0;labels[10:40,10:40]=1;labels[40:70,40:70]=1
        review['regions']=review['regions'][:1];review['labels_sha256']=module.pixels(labels)
        a,mask,report=module.apply_reviewed(rgb,labels,review,seed=11)
        self.assertEqual(report['render_component_to_review_region'],{1:1,2:1})
        np.testing.assert_array_equal(mask,labels==1)

    def test_singleton_completion_uses_only_adjacent_generated_same_owner(self):
        generated=np.zeros((8,8,3),np.uint8);parts=np.zeros((8,8),np.uint16)
        parts[2:4,2:4]=1;generated[parts==1]=[101,81,61];parts[4,4]=2;parts[6,6]=3
        parts[2,5]=4;parts[2,6]=5;generated[parts==4]=255
        renderer=dict(regions=[dict(region_id=i,fingerprint_texture_resolved=i in (1,4)) for i in range(1,6)])
        result,completed=module.complete_singletons(generated,parts,renderer,{1:10,2:10,3:10,4:20,5:10})
        self.assertEqual(set(completed),{2});np.testing.assert_array_equal(result[4,4],[101,81,61])
        self.assertEqual(renderer['regions'][1]['fingerprint_texture_resolved'],False)
        self.assertTrue(np.all(result[parts==3]==0));self.assertTrue(np.all(result[parts==5]==0))

    def test_one_diagonal_pixel_does_not_roll_back_entire_real_render(self):
        rgb,labels,review=self.fixture();labels[:]=0;labels[12:116,12:77]=1;labels[116,77]=1
        review['regions']=review['regions'][:1];review['labels_sha256']=module.pixels(labels)
        returned,mask,report=module.apply_reviewed(rgb,labels,review,seed=11)
        np.testing.assert_array_equal(mask,labels==1);np.testing.assert_array_equal(returned[~mask],rgb[~mask])
        self.assertEqual(report['applied_region_count'],1)
        self.assertEqual(report['regions'][0]['generated_singleton_completion_pixels'],1)
        self.assertEqual(report['renderer']['unresolved_texture_regions'],1)

    def reviewed_project(self,root,orientation):
        # Synthetic pixels under the human-contract role test serialization only;
        # this is not a real human-label or biometric performance fixture.
        p=fixture(root,orientation,role='diagnostic_development');rgb,mask=p.arrays('SYNTH-001')
        labels,_=component_map(mask);y,x=np.where(labels==1)
        box=[int(x.min()+3),int(y.min()+3),int(x.min()+13),int(y.min()+13)]
        p.save('SYNTH-001',dict(base_revision=0,status='reviewed',attest_original_reviewed=True,
            attest_grouping_reviewed=True,groups=[dict(component_ids=[1],label='visible',reasons=[],evidence_box=box),
            dict(component_ids=[2],label='uncertain',reasons=['blur'],evidence_box=None)]))
        return p

    def test_all_exif_saved_RGB_registration_and_no_state_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            for orientation in range(1,9):
                root=Path(temp)/str(orientation);p=self.reviewed_project(root,orientation)
                before={str(f):f.read_bytes() for f in p.state.rglob('*.json')};rgb,mask=p.arrays('SYNTH-001');labels,_=component_map(mask)
                report=module.run(p.roster_path,p.state,'SYNTH-001',root/'out',seed=31)
                with Image.open(root/'out/returned.png') as image:
                    self.assertEqual(image.getexif()[274],orientation);saved=np.asarray(ImageOps.exif_transpose(image))
                np.testing.assert_array_equal(saved[labels!=1],rgb[labels!=1])
                self.assertEqual(module.pixels(saved),report['output_RGB_sha256'])
                self.assertEqual(before,{str(f):f.read_bytes() for f in p.state.rglob('*.json')})
                with self.assertRaises(FileExistsError):module.run(p.roster_path,p.state,'SYNTH-001',root/'out')

    def test_draft_and_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=fixture(root/'draft',role='diagnostic_development')
            with self.assertRaisesRegex(ValueError,'completed_human'):module.run(p.roster_path,p.state,'SYNTH-001',root/'no')
            self.assertFalse((root/'no').exists())
            p=self.reviewed_project(root/'changed',1);source=Path(p.sources['SYNTH-001']['source_path']);source.write_bytes(source.read_bytes()+b'changed')
            with self.assertRaises(ValueError):module.run(p.roster_path,p.state,'SYNTH-001',root/'no')

    def test_reused_project_bound_to_roster_and_files_rechecked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=self.reviewed_project(root/'one',1);other=self.reviewed_project(root/'two',1)
            with self.assertRaisesRegex(ValueError,'binding_mismatch'):
                module.run(p.roster_path,p.state,'SYNTH-001',root/'no',project=other)
            original=p.roster_path.read_bytes();p.roster_path.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'roster_changed'):
                module.run(p.roster_path,p.state,'SYNTH-001',root/'no',project=p)
            p.roster_path.write_bytes(original)
            report=module.run(p.roster_path,p.state,'SYNTH-001',root/'yes',project=p,seed=51)
            self.assertEqual(report['applied_region_count'],1)

    def test_batch_completion_marker_and_duplicate_ids(self):
        from photo_visibility_reviewed_batch_v1 import run_batch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=self.reviewed_project(root/'one',1)
            with self.assertRaisesRegex(ValueError,'unique_known'):
                run_batch(p.roster_path,p.state,root/'no',source_ids=['SYNTH-001']*2)
            report=run_batch(p.roster_path,p.state,root/'batch',seed=9)
            self.assertEqual(report['applied_regions'],1);self.assertFalse((root/'batch/INCOMPLETE.txt').exists())
            with patch('photo_visibility_reviewed_batch_v1.run',side_effect=RuntimeError('injected_failure')):
                with self.assertRaisesRegex(RuntimeError,'injected_failure'):run_batch(p.roster_path,p.state,root/'failed')
            self.assertTrue((root/'failed/INCOMPLETE.txt').exists());self.assertFalse((root/'failed/batch.private.json').exists())

    def test_merged_human_group_rolls_back_as_one_permission_unit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=self.reviewed_project(root/'fixture',1)
            old=p.current('SYNTH-001');group=dict(old['groups'][0]);group['component_ids']=[1,2]
            p.save('SYNTH-001',dict(base_revision=old['revision'],status='reviewed',attest_original_reviewed=True,
                attest_grouping_reviewed=True,groups=[group]))
            def fake(rgb,mask,labels,seed=None):
                out=rgb.copy();out[mask]=0
                return out,dict(regions=[dict(region_id=i,fingerprint_texture_resolved=i==1) for i in (1,2)])
            with patch.object(module,'render',fake):
                result=module.run(p.roster_path,p.state,'SYNTH-001',root/'result',project=p)
            self.assertEqual(result['selected_region_count'],1);self.assertEqual(result['applied_region_count'],0)
            self.assertEqual(result['review_group_components'],{1:[1,2]})

    def test_batch_changed_review_or_roster_or_source_never_publishes_completion(self):
        import photo_visibility_reviewed_batch_v1 as batch
        with tempfile.TemporaryDirectory() as temp:
            for kind in ('review','roster','source'):
                with self.subTest(kind=kind):
                    root=Path(temp)/kind;root.mkdir();p=self.reviewed_project(root/'fixture',1);original=batch.run
                    def changed(*args,**kwargs):
                        result=original(*args,**kwargs)
                        if kind=='review':
                            current=p.current('SYNTH-001')
                            p.save('SYNTH-001',dict(base_revision=current['revision'],status='reviewed',attest_original_reviewed=True,
                                attest_grouping_reviewed=True,groups=current['groups']))
                        else:
                            path=p.roster_path if kind=='roster' else Path(p.sources['SYNTH-001']['source_path'])
                            path.write_bytes(path.read_bytes()+b' ')
                        return result
                    with patch.object(batch,'run',changed),self.assertRaises(ValueError):
                        batch.run_batch(p.roster_path,p.state,root/'result',seed=6)
                    self.assertTrue((root/'result/INCOMPLETE.txt').exists())
                    self.assertFalse((root/'result/batch.private.json').exists())


if __name__=='__main__':unittest.main()
