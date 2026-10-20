import hashlib
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import Mock
import numpy as np
import torch
from photo_resident_model_v31 import Models,verified_checkpoint


class VerifiedModelTests(unittest.TestCase):
    def test_model_reuse_keeps_post_construction_rng_and_scopes_are_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'weights.pt';path.write_bytes(b'synthetic-checkpoint')
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            def load(path,sha):
                random.random();np.random.random();return torch.nn.Linear(3,2).eval()
            loader=Mock(side_effect=load)
            models=Models()
            try:
                def obtain():
                    random.seed(17);np.random.seed(17);torch.manual_seed(17)
                    return verified_checkpoint(path,sha,loader=loader)
                first=obtain();expected=(random.random(),np.random.random(),torch.rand(1).item())
                second=obtain();actual=(random.random(),np.random.random(),torch.rand(1).item())
                self.assertIs(first,second);self.assertEqual(expected,actual)
                self.assertEqual(loader.call_count,1);models.verify()
            finally:models.close()
            third=verified_checkpoint(path,sha,loader=loader)
            self.assertIsNot(first,third);self.assertEqual(loader.call_count,2)

    def test_mutated_checkpoint_or_resident_parameters_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'weights.pt';path.write_bytes(b'original')
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            models=Models()
            try:
                model=verified_checkpoint(path,sha,loader=lambda *_:torch.nn.Linear(2,1).eval())
                path.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'asset_hash_mismatch'):
                    verified_checkpoint(path,sha,loader=lambda *_:None)
                path.write_bytes(b'original')
                with torch.no_grad():model.weight.add_(1)
                with self.assertRaisesRegex(ValueError,'resident_model_state_changed'):models.verify()
                with self.assertRaisesRegex(ValueError,'resident_model_state_changed'):
                    verified_checkpoint(path,sha,loader=lambda *_:None)
            finally:models.close()


if __name__=='__main__':unittest.main()
