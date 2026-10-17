# V18: camera-scale texture loss diagnosis and bounded material correction

V1–V17 renderer modules and previous private images are preserved. V18 is
opt-in and does not change native detection, pitch/feature gates, frozen
protection mathematics or the CLI default. This is an appearance experiment.

## Diagnosis before changing the renderer

On six development photos / sixteen regions, source-pixel multiband MAD
contrast was measured after reading the actual saved RGB. The median ratios
to original contrast, for Gaussian bands 0.65–1.4, 1.4–3.2, 3.2–7 and 7–15
source pixels, were:

| Renderer | Finest band | Second band | Third band | Broadest band |
|---|---:|---:|---:|---:|
| V12 | 1.117 | 0.906 | 0.590 | 0.481 |
| V17 | 0.893 | 0.684 | 0.455 | 0.429 |
| V18 final | 1.145 | 1.000 | 0.809 | 0.572 |

These are band-contrast ratios, not naturalness or protection scores.
The principal measured deficit is medium-scale relief, not missing finest
noise. Reconstructed coarse RGB intentionally discards source ridge phase;
the generated material did not compensate its medium-scale contrast loss.
Its amplitude formula was not calibrated against actual saved-band contrast.

Two fixed-seed component ablations confirm that disabling final softening or
restoring legacy white flecks mainly changes the finest band. For one photo,
V17's third/broadest contrast was 0.341/0.415; disabling softening gives
0.351/0.416. On another it changes 0.356/0.305 to 0.357/0.305. Raising latent
resolution is also not a fix for these photos: their material grids already
fit below the existing 1536-pixel limit. Mean observed softening weight was
only 0.055 across coarse cells.

An additional, separate measurement issue exists: the legacy style observer
resizes before measuring camera-pixel frequencies and floors its scaled
sigmas. A fixed four-pixel-period floating fixture changes finest contrast
from 3.046 to 2.610 when its bbox grows from 1024 to 2048. Source frequency is
unchanged. This is a resolution-dependent measurement bias, not evidence that
the photographed skin became smoother.

## Implemented correction

`photo_native_texture_stats_v1.observe` filters source pixels without resize.
Finite separable kernels use a 60-pixel halo around 256-pixel tiles, with a
maximum filtered tile dimension of 376. Fixed random subsampling avoids a
regular sampling lattice aliasing periodic ridges. At most 4096 samples per
cell become four scalar MADs in at most 6×8 cells. Source filtered maps,
ridge orientation and phase do not leave this observer. Unsupported cells
do not fabricate a nonzero contrast observation.

V18 reconstructs V17's same coarse base, subtracts it from the generated RGB,
and equalizes only that generated material. This residual is **generated RGB
minus reconstructed base**, not original RGB minus a filtered source image.
Coarse contrast ratios drive nonnegative band gains, each bounded to two
additional units. Already excessive bands receive no extra gain. Generated
tails and the contour transition remain bounded; original pixels are never
feathered back and masks do not expand.

An initial independent Gaussian-band completion pilot recovered contrast but
looked mottled/noisy. It was rejected and retained privately, along with its
immutable source snapshot. The final path strengthens coherent generated
ridges and skin relief instead of treating every deficit as independent
noise. Kernel transfer, tile continuity and actual RGB8 behavior are tested.

The old observer remains inside preserved V17 replay; the corrected observer
measures both the real input and the actual generated result before applying
the new correction. No legacy module is silently changed.

## Reproduce

From the repository root with existing public AI dependencies installed:

```powershell
python ai/scripts/replace_photo_synthetic_v1.py --input "photo.png" --protection-run "bound-native-run" --output "fresh-v18-output" --renderer v18 --seed 91
```

Use the exact source bound to the validated native result. Arbitrary mask
folders are rejected. The output directory must be new. Read back
`synthetic.png` and inspect `result.private.json`; its per-region
`camera_band_completion` records target, before, after and actual bounded
gains. Accepted native RGB and outside-permission RGB remain preserved.

The coarse color, macro-crease and contrast summaries remain source dependent.
This is neither a proof of biometric removal nor a calibrated skin/camera
model. No new independent dataset, matcher or native model run is implied.

## Final checks and limits

All six photos / sixteen permission regions complete, replacing 4,703,163
pixels. Original-file hashes, outside-permission RGB, actual PNG readback and
EXIF/ICC checks pass. A real two-region photo through the CLI produces clean
JSON and RGB identical to its fixed-seed API result. The final regression
suite passes 87 distinct tests (77 preserved contracts plus 10 new checks).
The public workflow includes the same suite; hosted Linux CI is prepared,
not executed here. The local launcher parses with V18 as an additional
explicit choice; its previous default stays unchanged. GUI model detection
and native processing were not rerun; the experiments use validated caches.

The 425 pinned prior renderer/output files are unchanged. The only expected
change among 426 pins is the version-selection dispatcher registration.
Both rejected and final immutable source capsules remain available privately.

In context, enlarged regions and sixteen original-pixel crops, V18 reduces
V17's overly smooth appearance. The rejected isotropic-noise pilot's rough
mottling is avoided by equalizing generated structure instead. Medium-scale
contrast still falls short in the broadest band, and regular generated flow
and joint-boundary tone/crease mismatch remain. Strict naturalness and
production acceptance remain false. V12 and V17 remain comparison references;
no old image or renderer is overwritten and no default is promoted.
