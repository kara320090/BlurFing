"""Synthetic process/cache tests; no real hand or photo model inference."""
from concurrent.futures import Future
import hashlib
import json
from pathlib import Path
import sys
import time
import queue
import tempfile
import unittest
from unittest.mock import patch,Mock
import numpy as np
from PIL import Image


class FastResourcesTests(unittest.TestCase):
    def client(self,root,mode='valid'):
        from photo_resident_resources_v29 import ModelClient
        script=root/'worker.py'
        script.write_text('''import json,sys,pathlib,time
print(json.dumps({'status':'ready','protocol':'synthetic-model-test'}),flush=True)
for line in sys.stdin:
    job=json.loads(line)
    if MODE=='slow':time.sleep(20)
    value=pathlib.Path(job['input']).read_text()
    pathlib.Path(job['output']).write_text(value+' '+job['id'])
    print(json.dumps({'status':'ok','id':job['id'] if MODE=='valid' else 'wrong'}),flush=True)
'''.replace('MODE',repr(mode)),encoding='utf-8')
        return ModelClient([sys.executable,str(script)],'synthetic-model-test')

    def test_resident_client_two_fresh_inputs_and_correlated_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);client=self.client(root)
            try:
                pid=client.process.pid;ids=[]
                for number in range(2):
                    source=root/f'{number}.txt';source.write_text(str(number));target=root/f'{number}.out'
                    with client.job(source,target) as job:ids.append(job.sequence);job.finish()
                    self.assertEqual(target.read_text(),str(number)+' '+ids[-1])
                    self.assertEqual(client.process.pid,pid)
                self.assertNotEqual(*ids)
            finally:client.close()
            self.assertIsNotNone(client.process.poll())

    def test_bad_id_or_unconsumed_job_stops_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.write_text('synthetic')
            for mode,consume in [('wrong',True),('valid',False)]:
                client=self.client(root,mode)
                with self.assertRaises(ValueError):
                    with client.job(source,root/(mode+'.out')) as job:
                        if consume:job.finish()
                self.assertIsNotNone(client.process.poll())

    def test_deadline_includes_work_between_launch_and_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);client=self.client(root,'slow');source=root/'source';source.write_text('synthetic')
            client.timeout=.01
            try:
                with self.assertRaises(queue.Empty):
                    with client.job(source,root/'result') as job:
                        time.sleep(.03)
                        job.finish()
                self.assertIsNotNone(client.process.poll())
            finally:client.close()

    def test_partial_startup_failure_closes_other_successful_resources(self):
        import photo_resident_resources_v29 as module
        hand=Mock();pool=Mock();models=Mock()
        def completed(*args):
            future=Future();future.set_result(1);return future
        pool.submit.side_effect=completed
        env={name:'synthetic' for name in ('BLURFING_COLFISPOOF_PYTHON','BLURFING_COLFISPOOF_SOURCE',
            'BLURFING_COLFISPOOF_MODEL','BLURFING_HAND_PYTHON','BLURFING_HAND_MODEL')}
        with (patch.dict(module.os.environ,env),patch.object(module,'SemanticClient',side_effect=RuntimeError('startup')),
                patch.object(module,'HandClient',return_value=hand),patch.object(module,'ProcessPoolExecutor',return_value=pool),
                patch('photo_resident_model_v31.Models',return_value=models)):
            with self.assertRaisesRegex(RuntimeError,'startup'):module.Resources()
        hand.close.assert_called_once();pool.shutdown.assert_called_once();models.close.assert_called_once()

    def test_coarse_cache_is_content_bound_and_returned_masks_are_independent(self):
        import photo_coarse_cache_v31 as module
        from photo_lossless_io_v29 import lossless_io
        y,x=np.mgrid[:100,:100];body=((x-50)/20)**2+((y-50)/42)**2<1
        tip=body&(y<23)
        expected=module.original(body,tip,preserve_candidates=True)
        with lossless_io() as state,patch.object(module,'original',wraps=module.original) as original:
            first=module.estimate(body,tip,preserve_candidates=True)
            first['mask'][:]=False
            for row in first['regions']:
                if 'body_mask' in row:row['body_mask'][:]=False
            again=module.estimate(body.copy(),tip.copy(),preserve_candidates=True)
            np.testing.assert_array_equal(again['mask'],expected['mask'])
            for actual,wanted in zip(again['regions'],expected['regions']):
                if 'body_mask' in wanted:np.testing.assert_array_equal(actual['body_mask'],wanted['body_mask'])
            self.assertEqual(original.call_count,1);self.assertEqual(state.coarse_hits,1)
            altered=tip.copy();altered[50,50]=True
            module.estimate(body,altered,preserve_candidates=True)
            self.assertEqual(original.call_count,2)
        self.assertFalse(state.coarse);self.assertEqual(state.coarse_bytes,0)


class AutomaticArrayTests(unittest.TestCase):
    def test_array_route_matches_public_pixels_and_leaves_final_transport_to_caller(self):
        import photo_automatic_v23 as module
        from photo_visibility_reviewed_apply_v1 import pixels
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
        from experimental_photo_transport_v2 import UploadedPhoto,validate_transport
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';rgb=np.full((80,96,3),140,np.uint8)
            Image.fromarray(rgb).save(source);registry=root/'registry.json';registry.write_text('{}')
            model=root/'model';model.mkdir();(model/'final_config.private.json').write_text('{}')
            (model/'final_context_whole_pad.pt').write_bytes(b'synthetic-unused-weight')
            mask=np.zeros(rgb.shape[:2],bool);mask[12:30,20:38]=True
            returned=rgb.copy();returned[mask]=[135,139,141]
            report=dict(regions=[dict(region_id=1,status='synthetic_applied_unverified',reason_code='TRANSFORMED')])
            def propose(src,model,registry,folder,**kwargs):
                for name in ('proposal.png','boundary_refined_mask.png'):
                    Image.fromarray(mask.astype(np.uint8)*255).save(folder/name)
                (folder/'proposal.private.json').write_text(json.dumps(dict(
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    candidate_selection=dict(proposal_pixel_sha256=pixels(mask)),partial_pose=None)))
            options=dict(photo_model=model,consumed_registry=registry,request_id='array-contract')
            with (patch('pad_refinement_tiles_v3.validate_registry'),patch('photo_new_input_v23.propose',side_effect=propose),
                    patch('fingerprint_input_router.route_input',return_value=dict(input_type='PHOTO')),
                    patch.object(module,'recover_proposal',side_effect=lambda rgb,m,b,p:(m,b,{})),
                    patch.object(module,'apply_candidates',return_value=(returned,mask,report))):
                target=module.run(source,root/'public',**options)
                wire=json.loads(target.read_text());validate_transport(wire,UploadedPhoto.decode(source.read_bytes()),
                    request_id='array-contract',engine='synthetic_v23')
                with patch.object(module,'transport',side_effect=AssertionError('intermediate wire should not be encoded')):
                    arrays=module.run(source,root/'arrays',array_result=True,**options)
            np.testing.assert_array_equal(arrays.returned,np.array(Image.open(target.parent/'returned.png')))
            np.testing.assert_array_equal(arrays.applied,mask)
            np.testing.assert_array_equal(arrays.labels,mask.astype(np.uint16))
            self.assertEqual(arrays.source_sha256,wire['source_sha256'])
            for name in ('returned.png','applied_mask.png','result.transport.json','INCOMPLETE.txt'):
                self.assertFalse((root/'arrays'/name).exists())
            self.assertTrue((root/'arrays/result.private.json').is_file())


if __name__=='__main__':unittest.main()
