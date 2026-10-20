import io
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
from photo_lossless_io_v29 import lossless_io
from photo_experimental_transport_v1 import verify_wire_png


class LosslessIOTests(unittest.TestCase):
    def test_opencv_RGB_and_mask_keep_samples_orientation_and_wire_contract(self):
        rng=np.random.default_rng(42)
        for mode,shape,kind in [('RGB',(48,71,3),2),('L',(48,71),0)]:
            rgb=rng.integers(0,256,shape,dtype=np.uint8);exif=Image.Exif();exif[274]=1
            with lossless_io() as state:
                stream=io.BytesIO();Image.fromarray(rgb).save(stream,format='PNG',exif=exif)
                verify_wire_png(stream.getvalue(),rgb,mode,kind,1)
                self.assertEqual(state.encodes,1)
                for _ in range(2):
                    with Image.open(io.BytesIO(stream.getvalue())) as image:
                        self.assertEqual(image.format,'PNG');self.assertEqual(image.getexif().get(274),1)
                        np.testing.assert_array_equal(np.asarray(image),rgb)
                self.assertGreater(state.hits,0)
            self.assertEqual(state.bytes,0);self.assertFalse(state.cache)

    def test_changed_bytes_in_same_path_never_return_stale_pixels(self):
        with tempfile.TemporaryDirectory() as td,lossless_io():
            path=Path(td)/'input.png'
            for value in (30,90,30):
                Image.fromarray(np.full((24,32,3),value,np.uint8)).save(path)
                with Image.open(path) as image:self.assertTrue((np.asarray(image)==value).all())

    def test_cached_images_are_independent_and_exception_clears_cache(self):
        stream=io.BytesIO();Image.new('RGB',(40,30),'pink').save(stream,format='PNG')
        with self.assertRaisesRegex(RuntimeError,'job'):
            with lossless_io() as state:
                first=Image.open(io.BytesIO(stream.getvalue()));first.putpixel((0,0),(0,0,0))
                second=Image.open(io.BytesIO(stream.getvalue()))
                self.assertNotEqual(second.getpixel((0,0)),(0,0,0))
                raise RuntimeError('job')
        self.assertEqual(state.bytes,0);self.assertFalse(state.cache)

    def test_metadata_fallback_preserves_ICC_and_hooks_are_inert_outside_request(self):
        original=Image.new('RGB',(40,30),'pink');stream=io.BytesIO();original.save(stream,format='PNG')
        expected=stream.getvalue()
        with lossless_io() as state:
            im=Image.new('RGB',(40,30),'pink');im.info['icc_profile']=b'fixture-profile'
            data=io.BytesIO();im.save(data,format='PNG',icc_profile=im.info['icc_profile'])
            with Image.open(io.BytesIO(data.getvalue())) as decoded:self.assertEqual(decoded.info['icc_profile'],b'fixture-profile')
            self.assertEqual(state.encodes,0)
        after=io.BytesIO();original.save(after,format='PNG');self.assertEqual(after.getvalue(),expected)

    def test_file_snapshots_are_rehashed_before_publishing_and_cleared(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'input.json';path.write_bytes(b'initial')
            with self.assertRaisesRegex(ValueError,'snapshot_changed'):
                with lossless_io() as state:
                    self.assertEqual(path.read_bytes(),b'initial')
                    self.assertEqual(path.read_bytes(),b'initial')
                    self.assertEqual(state.file_hits,1)
                    path.write_bytes(b'modified without another read')
            self.assertFalse(state.files);self.assertFalse(state.pins)

    def test_binary_asset_stream_reuses_bytes_but_keeps_SHA_checks_and_file_descriptor(self):
        from pad_refinement_data_contract_v2 import checked_bytes
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'weights.pt';content=b'fresh synthetic weights'
            path.write_bytes(content);expected=hashlib.sha256(content).hexdigest()
            with lossless_io() as state:
                for _ in range(2):self.assertEqual(checked_bytes(path,expected),content)
                self.assertGreaterEqual(state.file_hits,1)
                with path.open('rb') as stream:
                    self.assertEqual(os.fstat(stream.fileno()).st_size,len(content))
                    self.assertEqual(stream.read(5),content[:5]);stream.seek(0)
                    self.assertEqual(stream.read(),content)
                with self.assertRaisesRegex(ValueError,'asset_hash_mismatch'):
                    checked_bytes(path,'0'*64)
            self.assertFalse(state.files);self.assertFalse(state.pins)
            path.write_bytes(b'changed');self.assertEqual(path.read_bytes(),b'changed')

    def test_binary_stream_snapshot_cannot_hide_later_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'asset.npz';path.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError,'snapshot_changed'):
                with lossless_io():
                    with path.open('rb') as stream:self.assertEqual(stream.read(),b'original')
                    path.write_bytes(b'modified')

    def test_repeated_samples_share_encoding_but_EXIF_remains_per_output(self):
        image=Image.new('RGB',(48,32),'pink');exif=Image.Exif();exif[274]=1
        with lossless_io() as state:
            first=io.BytesIO();image.save(first,format='PNG',exif=exif)
            second=io.BytesIO();image.copy().save(second,format='PNG')
            self.assertEqual(state.encodes,1);self.assertEqual(state.encode_hits,1)
            self.assertNotEqual(first.getvalue(),second.getvalue())
            with Image.open(io.BytesIO(first.getvalue())) as a,Image.open(io.BytesIO(second.getvalue())) as b:
                self.assertEqual(a.getexif().get(274),1);self.assertNotIn(274,b.getexif())
                np.testing.assert_array_equal(np.array(a),np.array(b))
        self.assertFalse(state.encoded);self.assertEqual(state.encoded_bytes,0)


if __name__=='__main__':unittest.main()
