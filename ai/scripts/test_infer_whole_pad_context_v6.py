import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import torch
import infer_whole_pad_context_v6 as inference
from whole_pad_context_model_v6 import encoder_identity


class ContextCheckpointContracts(unittest.TestCase):
    def config(self,model):
        return dict(training_complete=True,development_only=True,approved_for_inference=False,independent_final_test=False,
            protocol=dict(inference.PROTOCOL),protocol_sha256=inference.PROTOCOL_SHA256,
            source_code_sha256={'declared_code':'frozen'},threshold=.5,model_sha256='a'*64,
            context_encoder_sha256=encoder_identity(model.context_encoder))

    def test_matching_config_uses_exact_context_checkpoint_and_determinism(self):
        model=SimpleNamespace(context_encoder=torch.nn.Identity())
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);cfg=self.config(model);(folder/'final_config.private.json').write_text(json.dumps(cfg))
            with patch.object(inference,'code_hashes',return_value={'declared_code':'frozen'}),patch.object(inference,'load_checkpoint',return_value=model) as load,patch.object(inference,'seed_all') as seed:
                actual,read=inference.load_model(folder)
            self.assertIs(actual,model);self.assertEqual(read,cfg)
            load.assert_called_once_with(folder/'final_context_whole_pad.pt','a'*64)
            seed.assert_called_once_with(inference.PROTOCOL['seed'])

    def test_old_model_incomplete_code_or_encoder_mismatch_reject(self):
        model=SimpleNamespace(context_encoder=torch.nn.Identity())
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);path=folder/'final_config.private.json'
            for update in [dict(training_complete=False),dict(approved_for_inference=True),dict(protocol={'version':'V4'}),dict(source_code_sha256={'different':'code'})]:
                cfg=self.config(model)|update;path.write_text(json.dumps(cfg))
                with patch.object(inference,'code_hashes',return_value={'declared_code':'frozen'}),patch.object(inference,'load_checkpoint') as load:
                    with self.assertRaisesRegex(ValueError,'completed_whole_pad_context_V6'): inference.load_model(folder)
                    load.assert_not_called()
            cfg=self.config(model)|dict(context_encoder_sha256='0'*64);path.write_text(json.dumps(cfg))
            with patch.object(inference,'code_hashes',return_value={'declared_code':'frozen'}),patch.object(inference,'load_checkpoint',return_value=model):
                with self.assertRaisesRegex(ValueError,'encoder_mismatch'): inference.load_model(folder)

    def test_truthy_detect_only_rejects_before_prediction_or_outputs(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(inference,'run') as run:
            out=Path(tmp)/'new'
            with self.assertRaisesRegex(ValueError,'must_be_boolean'): inference.protect_bundle('.', '.',out,detect_only='false')
            run.assert_not_called();self.assertFalse(out.exists())


if __name__=='__main__': unittest.main()
