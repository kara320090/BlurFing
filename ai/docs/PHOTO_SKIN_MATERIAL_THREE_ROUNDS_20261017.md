# Photographic skin material experiments — 2026-10-17

The requested goal is natural-looking synthetic fingerprint skin rather than
a smooth cap. These are opt-in appearance experiments; the default renderer,
frozen native math, detectors and native quality decisions remain unchanged.
All original files and accepted native pixels are preserved. Source-dependent
coarse appearance information is retained: this is not a biometric privacy proof.

## Round 1 — V10

Native-scale bounded material (maximum 1536px) couples new ridges, ridge pores,
short folds, roughness and broad illumination. A maximum 1024px style observer
exports at most 48 four-band isotropic MAD vectors; no filtered source raster,
source ridge phase or source ridge orientation is supplied to the generator.
This addresses the old 512px material resolution and overly limited contrast.

Four behavioral tests passed: actual saved PNG/native-accepted preservation,
EXIF/ICC and fresh-output binding, deterministic seeds and translation,
resource/nonfinite guards, scalar style and independent material data flow.
Six development photos / 16 regions / 4,703,163 permission pixels were actually
replaced and saved/read back; original hashes and outside RGB remained exact.

Visual review of all 16 region crops: stronger ridges are evident but the
uniform embossing and smooth skin still look artificial. Large source creases
are underrepresented. **Strict naturalness acceptance: rejected.** No source
mask, native gate or matcher threshold was tuned to manufacture a pass.

## Round 2 — V11

Long oblique macro grooves are fitted as at most ten quadratic descriptors
from supported coarse-cell median residuals. Independent mesoscale roughness
and albedo variation interrupt the uniform embossing. Source-derived macro
crease information is retained and must not be described as zero-information
privacy. No source ridge residual is blended into output.

A known synthetic two-crease fixture improves reconstruction RMSE from 1.717
to 1.358; flat inputs produce no macro-crease descriptors. Six material tests
passed, including actual V11 PNG/native preservation and metadata. All six
development photos / 16 regions were processed and saved/read back with exact
outside RGB and original hashes. Visual review of every region: skin looks
less smooth, but coarse mottling can resemble grit and proximal cut seams
remain. **Strict naturalness acceptance: rejected.** This motivates less
pigment mottling and a better generated boundary/curved material in round 3.
