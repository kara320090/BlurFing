# V19: irregular generated ridge detail and inside-contour skin continuation

V19 is a separate opt-in appearance renderer. V1–V18 modules and previous
private results are preserved. Native detection, pitch/feature gates, frozen
protection math, permission geometry and default selections do not change.

## Generated ridge detail

The existing independently seeded arch/loop/whorl field and V18 camera-band
correction remain. A new two-scale coordinate map adds local changes to the
generated flow. Its displacement Jacobian Frobenius norm is bounded to 0.32;
the local map's minimum singular value is therefore at least 0.68. This bound
describes this additional map, not the entire composition of earlier warps.

Up to 48 sparse tapered interruptions use crest locations and the structure
tensor of the generated field. Their centers are at least four canonical
ridge periods apart and avoid the geometric field boundary. They make new
ridge endings rather than overlaying image noise or copying donor minutiae.
No original ridge phase, orientation or second person's fingerprint enters
this operation. Added microstructure alone is not a naturalness guarantee.

## Contour continuation

Inside the same permission mask, up to 192 contour nodes observe separate
source/generated RGB means in three depth bands. Each band requires at
least 24 pixels. Only these coarse color differences enter shape-preserving
PCHIP interpolation; source RGB residual rasters are never transferred.
Positive interpolation weights and a 16-level RGB correction bound limit
overshoot. The correction and its derivative vanish at the inner join.
Unsupported nodes are skipped. No source pixels outside permission are read
by this observer, no original alpha is feathered back and masks do not expand.

The initial median-based prototype worsened an independently partitioned
coarse boundary color diagnostic in four of the six development photos.
Medians discarded some antialiased skin/background mixtures. The revised
observer uses means and checks the proposed correction after actual RGB8
rounding in a different coarse color-cell partition. It applies a correction
only when that region's supported inside-edge mean RGB error strictly
decreases relative to its own uncorrected generated field. Otherwise that
field is retained. This is an appearance nonregression guard, not a detector,
pitch, feature, privacy or naturalness acceptance threshold. The initial
prototype and its images remain preserved privately.

This also differs from the rejected V14 Hermite slope experiment: source
slopes are not extrapolated. The new ribbon cannot create polynomial color
overshoot outside its bounded control values. Whether a crease actually
looks continuous still requires image review; coarse color agreement is
not an anatomical joint detector or an independent naturalness score.

## Run and inspect

```powershell
python ai/scripts/replace_photo_synthetic_v1.py --input "photo.png" --protection-run "hash-bound-native-run" --output "fresh-v19-result" --renderer v19 --seed 91
```

Use the original input bound to a validated cached native result. Arbitrary
mask folders are rejected and the output directory must be new. Inspect the
actual `synthetic.png` and per-region `contour_continuation`,
`skin_surface.ridge_surface.irregularity` and `camera_band_completion` in
`result.private.json`. Accepted native pixels remain preserved. Runtime
errors and native rejection are not reclassified as native success.

The synthetic tests cover nonfolding maps, increased generated ridge endings,
known coarse seam recovery, bounded/no-overshoot contour corrections,
unchanged inner RGB, translation/background independence, fixed-summary
source isolation, RGB8 boundary nonregression, saved PNG/native/EXIF/ICC
binding, replay and fresh output.
These contracts do not substitute for visual review or biometric validation.

## Development observations

The revised renderer was applied to six existing development photos with
16 permission regions (4,703,163 pixels), using the same masks and seeds as
the V18 comparison. Actual saved RGB, source files, pixels outside permission,
EXIF orientation and ICC profiles were checked. The appearance regression
suite passed 96 distinct tests; the nine V19 tests also passed after the final
descriptive metadata correction. A real-photo CLI result matched the API's
saved RGB. These are cached-native replacement runs, not fresh end-to-end
detector, matcher or GUI model-pipeline validation.

The RGB8 guard accepted 15 region corrections and retained the uncorrected
generated field for one region. Against V18, the fixed coarse boundary RGB
diagnostic decreased in five photos. The remaining photo increased by about
0.0074 RGB levels because its independently generated field also changed;
the guard compares each proposed correction with its own pre-correction
field, not with V18. This diagnostic is neither a naturalness nor a privacy
success rate, and the repeatedly reviewed development photos are not holdout
evidence.

Review of six context images, 16 native-resolution region centers and 32
axis-end crops found small line-detail and some boundary improvements, with
no large overall naturalness gain over V18. Some regular flow, smoothed
skin and joint seams remain. V19 stays opt-in; strict naturalness and
production/privacy approval remain false. Further work should address the
material and anatomical crease model rather than equating a lower coarse
color error with a convincing result.
