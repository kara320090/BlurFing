import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageCms
from photo_synthetic_replacement_v1 import render
from replace_photo_synthetic_v1 import run
from photo_source_rgb_v1 import canonical_rgb
from photo_rejection_resolution_v1 import pixel_hash


class SyntheticReplacementTests(unittest.TestCase):
    def fixture(self):
        yy, xx = np.mgrid[:100, :120]
        mask = ((xx-60)/37)**2+((yy-50)/43)**2 < 1
        rgb = np.full((100, 120, 3), [168, 128, 108], np.uint8)
        rgb[mask] += ((xx[mask] % 5)*3).astype(np.uint8)[:, None]
        return rgb, mask, mask.astype(np.uint16)

    def test_source_texture_permutation_has_no_effect_including_boundary(self):
        rgb, mask, labels = self.fixture()
        permuted = rgb.copy()
        permuted[mask] = rgb[mask][np.random.default_rng(20).permutation(mask.sum())]
        self.assertFalse(np.array_equal(rgb[mask], permuted[mask]))
        a, report = render(rgb, mask, labels, seed=27)
        b, _ = render(permuted, mask, labels, seed=27)
        np.testing.assert_array_equal(a[mask], b[mask])
        np.testing.assert_array_equal(a[~mask], rgb[~mask])
        self.assertEqual(report['source_alpha_inside_mask'], 0.)
        self.assertEqual(report['replaced_pixels'], int(mask.sum()))
        self.assertFalse(report['privacy_validated'])

    def test_seed_replay_and_independent_seeds(self):
        rgb, mask, labels = self.fixture()
        original = rgb.copy()
        a, _ = render(rgb, mask, labels, seed=7)
        b, _ = render(rgb, mask, labels, seed=7)
        c, _ = render(rgb, mask, labels, seed=8)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a[mask], c[mask]))
        np.testing.assert_array_equal(rgb, original)
        with patch('photo_synthetic_replacement_v1.secrets.randbits', return_value=35) as random:
            _, report = render(rgb, mask, labels)
        random.assert_called_once_with(128)
        self.assertEqual(report['seed'], 35)

    def test_no_candidates_and_holes(self):
        rgb, mask, _ = self.fixture()
        empty = np.zeros_like(mask)
        result, report = render(rgb, empty, empty.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(result, rgb)
        self.assertEqual(report['replacement_regions'], 0)
        mask[48:53, 58:63] = False
        result, _ = render(rgb, mask, mask.astype(np.uint16), seed=0)
        np.testing.assert_array_equal(result[~mask], rgb[~mask])

    def test_invalid_contracts_fail(self):
        rgb, mask, labels = self.fixture()
        for bad in (-1, 2**128, float('nan'), 1.5, True, '7'):
            with self.subTest(seed=bad), self.assertRaises(ValueError):
                render(rgb, mask, labels, seed=bad)
        for image, selection, regions in ((rgb.astype(float), mask, labels),
                (rgb, mask.astype(np.uint8), labels), (rgb, mask[:-1], labels),
                (rgb, mask, labels.astype(np.int64)), (rgb, mask, np.zeros_like(labels))):
            with self.assertRaises(ValueError):
                render(image, selection, regions, seed=0)

    def test_disconnected_region_is_not_silently_associated(self):
        rgb, mask, labels = self.fixture()
        labels[1, 1] = 1
        mask[1, 1] = True
        with self.assertRaisesRegex(ValueError, 'connected'):
            render(rgb, mask, labels, seed=0)

    def test_region_memory_guard_before_geometry(self):
        rgb, mask, labels = self.fixture()
        with patch('photo_synthetic_replacement_v1.MAX_REGION_PIXELS', 10):
            with self.assertRaisesRegex(ValueError, 'pixel_limit'):
                render(rgb, mask, labels, seed=0)

    def cached(self, folder, *, accepted=False):
        rgb, mask, labels = self.fixture()
        source = folder/'input.png'
        exif = Image.Exif(); exif[274] = 6
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        Image.fromarray(rgb).save(source, exif=exif, icc_profile=profile)
        rgb, identity = canonical_rgb(source)
        cache = folder/'cache'; cache.mkdir()
        labels[70:80, 60:70] = 2
        applied = labels == 2 if accepted else np.zeros_like(mask)
        native = rgb.copy(); native[applied] = [190, 140, 120]
        rows = []
        for i in (1, 2):
            part = labels == i
            transformed = bool(accepted and i == 2)
            rows.append(dict(region_id=i, mask_pixels=int(part.sum()), mask_pixel_sha256=pixel_hash(part),
                status='transformed' if transformed else 'rejected', reason=None if transformed else 'insufficient_features',
                renderer_details=dict(regions=[dict(applied=True, returned_RGB_structure_check=dict(structure_change_passed=True))]) if transformed else {}))
        report = dict(input_type='PHOTO', input_identity=identity, regions=rows,
            status='partial_success' if accepted else 'rejected',
            fingerprints_transformed=int(accepted), fingerprints_rejected=2-int(accepted),
            prediction_pixel_sha256=pixel_hash(mask), returned_RGB_sha256=pixel_hash(native))
        (cache/'result.private.json').write_text(json.dumps(report), encoding='utf-8')
        for name, array in [('permission_mask', mask), ('accepted_mask', applied), ('fallback_mask', mask & ~applied)]:
            Image.fromarray(array.astype(np.uint8)*255).save(cache/(name+'.png'))
        Image.fromarray(labels).save(cache/'region_labels.png')
        Image.fromarray(native).save(cache/'returned.png')
        return source, cache, rgb, mask, applied, native, report, profile

    def test_real_file_roundtrip_native_preservation_exif_and_ICC(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, cache, rgb, mask, applied, native, old, profile = self.cached(root, accepted=True)
            before = source.read_bytes()
            result, report = run(source, cache, root/'out', seed=123)
            self.assertEqual(report['replacement_regions'], 1)
            self.assertEqual(report['native_transformed_regions'], 1)
            self.assertEqual(report['native_rejected_regions'], 1)
            self.assertFalse(report['rejected_native_counted_as_native_success'])
            np.testing.assert_array_equal(result[applied], native[applied])
            np.testing.assert_array_equal(result[~mask], rgb[~mask])
            with Image.open(root/'out/synthetic.png') as image:
                np.testing.assert_array_equal(np.asarray(image), result)
                self.assertEqual(image.getexif()[274], 6)
                self.assertEqual(image.info['icc_profile'], profile)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(json.loads((cache/'result.private.json').read_text()), old)
            with self.assertRaises(FileExistsError):
                run(source, cache, root/'out', seed=123)

    def test_artifact_tampering_or_wrong_source_rejected(self):
        for target in ('source', 'permission', 'fallback', 'native', 'runtime_error'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, cache, rgb, mask, applied, native, old, _ = self.cached(root)
                if target == 'source':
                    rgb[1, 1] = 0; Image.fromarray(rgb).save(source)
                elif target in ('permission', 'fallback'):
                    a = mask.copy(); a[0, 0] = True
                    Image.fromarray(a.astype(np.uint8)*255).save(cache/(target+'_mask.png'))
                elif target == 'native':
                    native[1, 1] = 0; Image.fromarray(native).save(cache/'returned.png')
                else:
                    old['regions'][0]['error'] = 'extractor_crash'
                    (cache/'result.private.json').write_text(json.dumps(old))
                with self.assertRaises(ValueError):
                    run(source, cache, root/'out', seed=123)
                self.assertFalse((root/'out/result.private.json').exists())


if __name__ == '__main__':
    unittest.main()
