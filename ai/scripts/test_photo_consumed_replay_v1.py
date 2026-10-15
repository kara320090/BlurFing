import copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
import pad_refinement_tiles_v3 as tiles
from photo_consumed_replay_v1 import development_replay,consumed_roles
from test_pad_refinement_tiles_v3 import TileFixture


class ConsumedReplayTests(TileFixture):
    def setUp(self):
        super().setUp()
        self.identity=tiles.image_identity(self.inputs[0]['source_path'])
        self.registry[0].update(self.identity)
        self.original=tiles.exclude_consumed
        self.before=json.dumps(self.registry,sort_keys=True)

    def test_default_and_post_scope_remain_strict(self):
        self.assertEqual(consumed_roles(self.identity,self.registry),['consumed_GT7'])
        with development_replay(self.registry,[self.identity]):
            with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.exclude_consumed(self.identity,self.registry)
        with development_replay(self.registry,[self.identity],enabled=True):
            tiles.exclude_consumed(self.identity,self.registry)
        self.assertIs(tiles.exclude_consumed,self.original)
        self.assertEqual(json.dumps(self.registry,sort_keys=True),self.before)
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.exclude_consumed(self.identity,self.registry)

    def test_reencoding_is_blocked_unless_its_full_identity_is_declared(self):
        path=self.root/'reencoded.png'
        with Image.open(self.inputs[0]['source_path']) as im:im.save(path,compress_level=0)
        alias=tiles.image_identity(path)
        self.assertNotEqual(alias,self.identity)
        self.assertEqual(consumed_roles(alias,self.registry),['consumed_GT7'])
        with development_replay(self.registry,[self.identity],enabled=True):
            with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.exclude_consumed(alias,self.registry)
        with development_replay(self.registry,[self.identity,alias],enabled=True):tiles.exclude_consumed(alias,self.registry)

    def test_registry_change_cannot_hide_consumed_input(self):
        changed=copy.deepcopy(self.registry);changed[0]['source_sha256']='a'*64
        changed[0]['encoded_RGB_sha256']='b'*64;changed[0]['upright_RGB_sha256']='c'*64
        with development_replay(self.registry,[self.identity],enabled=True):
            with self.assertRaisesRegex(ValueError,'frozen_registry'):tiles.exclude_consumed(self.identity,changed)

    def test_invalid_registry_or_identity_and_nonboolean_are_not_bypassed(self):
        for flag in ['false',1,None]:
            with self.assertRaisesRegex(ValueError,'boolean'):
                with development_replay(self.registry,[self.identity],enabled=flag):pass
        with self.assertRaisesRegex(ValueError,'exact_identity'):
            with development_replay(self.registry,[{'source_sha256':'0'*64}],enabled=True):pass
        with development_replay(self.registry,[self.identity],enabled=True):
            with self.assertRaises(ValueError):tiles.exclude_consumed(self.identity,[])
        self.assertIs(tiles.exclude_consumed,self.original)

    def test_other_threads_keep_strict_exclusion(self):
        results=[]
        def other():
            try:tiles.exclude_consumed(self.identity,self.registry)
            except ValueError as e:results.append(str(e))
        with development_replay(self.registry,[self.identity],enabled=True):
            worker=threading.Thread(target=other);worker.start();worker.join(timeout=5)
            self.assertFalse(worker.is_alive());tiles.exclude_consumed(self.identity,self.registry)
        self.assertEqual(results,['consumed_source_or_decoded_pixels_forbidden'])

    def test_exception_restores_strict_alias(self):
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with development_replay(self.registry,[self.identity],enabled=True):raise RuntimeError('injected')
        self.assertIs(tiles.exclude_consumed,self.original)

    def test_nested_replay_cannot_broaden_exact_allowlist(self):
        other=tiles.image_identity(self.inputs[1]['source_path'])
        with development_replay(self.registry,[self.identity],enabled=True):
            with self.assertRaisesRegex(ValueError,'nested_development_replay_forbidden'):
                with development_replay(self.registry,[other],enabled=True):pass
            tiles.exclude_consumed(self.identity,self.registry)
        self.assertIs(tiles.exclude_consumed,self.original)

    def test_GT_free_prepare_and_all_frozen_checks_accept_only_during_replay(self):
        row={k:v for k,v in self.inputs[0].items() if k!='GT_folder'}
        row.update(acquisition_group='unknown',group_provenance='user_input_unverified')
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.prepare([row],self.registry,self.output,'inference')
        self.assertFalse(self.output.exists())
        with (patch.object(tiles,'read_gt',side_effect=AssertionError('GT touched')),
              development_replay(self.registry,[self.identity],enabled=True)):
            view=tiles.prepare([row],self.registry,self.output,'inference')
            tiles.check_tiles(self.output,view,'inference')
            tiles.check_input_source(self.output,view['sources'][0],view['crops'],self.registry)
        self.assertFalse(view['GT_present']);self.assertFalse(view['independent_final_test'])
        self.assertFalse(any(k.startswith('GT') for s in view['sources'] for k in s))
        self.assertEqual(view['consumed_registry'],self.registry)
        with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.check_tiles(self.output,view,'inference')

    def test_RGBA_historical_and_persisted_canonical_identities_are_distinct(self):
        from protect_photo_whole_pad_context_native_v1 import canonical_rgb
        rgba=np.zeros((6,8,4),np.uint8);rgba[:,:,:3]=123;rgba[:,:,3]=128
        source=self.root/'alpha.png';Image.fromarray(rgba).save(source)
        original=tiles.image_identity(source);rgb,_=canonical_rgb(source)
        canonical=self.root/'canonical.png';Image.fromarray(rgb).save(canonical)
        derived=tiles.image_identity(canonical);self.assertNotEqual(original['encoded_RGB_sha256'],derived['encoded_RGB_sha256'])
        self.registry[0].update(derived)
        self.assertEqual(consumed_roles(original,self.registry),[])
        self.assertEqual(consumed_roles(derived,self.registry),['consumed_GT7'])
        with development_replay(self.registry,[original],enabled=True):
            with self.assertRaisesRegex(ValueError,'decoded_pixels'):tiles.exclude_consumed(derived,self.registry)
        with development_replay(self.registry,[original,derived],enabled=True):tiles.exclude_consumed(derived,self.registry)


if __name__=='__main__':unittest.main()
