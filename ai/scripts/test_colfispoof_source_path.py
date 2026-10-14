"""External loader path contracts; no model or private inputs required."""
import tempfile
import unittest
from pathlib import Path
from colfispoof_raw_semantics import resolve_preprocessing


class SourcePathTests(unittest.TestCase):
    def test_checkout_and_preprocessing_resolve_same_loader(self):
        with tempfile.TemporaryDirectory(prefix='colfispoof path ') as folder:
            root=Path(folder);pre=root/'pre-processing'
            loader=pre/'Segmentation'/'DeepLabModel.py'
            loader.parent.mkdir(parents=True);loader.write_text('# synthetic loader')
            self.assertEqual(resolve_preprocessing(root),pre)
            self.assertEqual(resolve_preprocessing(pre),pre)
            self.assertEqual(loader.read_text(),'# synthetic loader')

    def test_missing_loader_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):resolve_preprocessing(folder)

    def test_explicit_preprocessing_is_preferred(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for path in [root/'Segmentation'/'DeepLabModel.py',root/'pre-processing'/'Segmentation'/'DeepLabModel.py']:
                path.parent.mkdir(parents=True);path.write_text('# synthetic loader')
            self.assertEqual(resolve_preprocessing(root),root)


if __name__=='__main__':unittest.main()
