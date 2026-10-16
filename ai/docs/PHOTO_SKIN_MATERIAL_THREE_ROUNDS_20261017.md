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

## Round 3 — V12

The ridge field uses a bounded cylindrical/dome projection. New dry-skin
flecks and smaller mesoscale irregularities replace V11's stronger pigment
blotches. A bounded isotropic energy ratio controls softening of generated
texture only; it is not a calibrated focus/depth measurement. Tiny inputs are
not magnified into subpixel synthetic design pitches.

The boundary is reconstructed from at most 256 inside-contour RGB median and
inward slope summaries. This is an opaque generated ribbon; no original RGB
alpha blending or source data outside the permission is used. The exact mask
is retained. On a known synthetic shading fixture, edge RGB RMSE changes from
1.844 to 0.842. This is a fixture-specific reconstruction check, not a general
naturalness improvement or privacy score.

An initial V12 visual check found dark arcs near the tip. Source diagnostics
showed that silhouette-adjacent shading had supported false macro-crease
proposals. V12 now requires both sides of crease evidence to have interior
coarse-cell support; the V11 default is preserved. On the first development
case, three proposed curves become one and the false distal arcs disappear.
The initial batch is retained separately; final comparisons use a fresh final
batch. All eleven new material tests passed, including contour shading,
interior crease support, tiny inputs, translation, fixed-summary/no-hidden-RGB
data flow, and saved PNG/native/EXIF/ICC preservation. The 53 selected existing
synthetic/regression/audit tests also passed: **64 distinct tests**, not the
sum of repeated runs.

## Final review and limits

Each round was run on the same six development photos, the same sixteen
permission regions, and the same per-photo seed. V12 final replaced all
4,703,163 candidate pixels and passed saved-PNG readback, metadata, original
hash and outside-RGB checks. Every fingertip comparison and every V12 native
pixel center crop was visually inspected. V12 is the selected comparison
experiment: it balances texture and pigmentation better than V10/V11, but
regular ridges, synthetic light flecks, some smooth areas, silhouette errors
and proximal joint seams remain. **All three strict naturalness acceptance
decisions are false.** This requested three-round development cycle is done;
the naturalness goal is not declared achieved. Defaults remain unchanged.

Counterevidence is retained: the fixed coarse boundary-cell RGB mean-error
diagnostic improves on two photos and worsens on four versus V9. It is
affected by silhouette/background mixture and is not a naturalness metric;
the synthetic shading-fixture improvement must not be generalized to all real
edges. Accurate coverage still needs human ground truth.

A final same-position high-pass copy diagnostic inspected 318 usable windows
and 28 insufficient-detail windows over 16 regions: zero review flags and
maximum absolute correlation 0.1525. Its existing 0.65 development review
threshold is unchanged and uncalibrated. This is not general protection proof
and does not test shifted/rotated matches or all biometric source summaries.
NBIS/SourceAFIS matcher evaluation was not repeated for these appearance-only
rounds; the earlier V9 matcher limitations remain limitations, not evidence of
V12 success. No independent naturalness or production approval is claimed.

Private local comparisons and original photographs stay outside Git. The
comparison page uses the final V12 batch, not its retained initial prototype.
Future work should address skin-material structure and crease continuity;
additional undirected noise/contrast tuning is unlikely to resolve the
remaining visual gap.

The separate local V12 CMD launcher was actually invoked with one development
JPEG: fresh detection/native processing, synthetic replacement and final PNG
save/readback completed. Native processing rejected its one region; V12
separately replaced 620,040 pixels. Native rejection is not reclassified as
native success. The new output preserves outside RGB, source hash, EXIF/ICC
and the same permission used for comparison. The interactive picker was not
retested. The original launcher's V6 default remains unchanged; V12 has its
own explicit experimental launcher. Full native startup/detection was slow
on this CPU run; this is a functionality smoke test, not a latency claim.
