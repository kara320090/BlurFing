# Five preserved photographic skin experiments — 2026-10-17

These opt-in versions continue V12 without deleting or editing the V1–V12
renderer modules or previous private results. Defaults, native math, detector
and native pitch/feature gates remain unchanged. Each round uses the same six
development photos, sixteen permission regions and fixed per-photo seed.
Every generated PNG is read back and checked against original hashes, exact
outside RGB, EXIF/ICC and the existing native acceptance/fallback contract.
Cached native runs are not represented as newly executed native processing.

Source-dependent coarse RGB, long crease descriptors and isotropic energies
are retained. No source RGB residual or original ridge phase is blended back.
This restriction is not general biometric protection or naturalness approval.

## V13 — crease-coupled material

Macro and independently generated secondary folds share coordinate
deformation, ridge attenuation and surface lighting. The physical-coordinate
Jacobian includes the aspect ratio and has displacement norm <=0.22, so its
minimum singular-value lower bound is 0.78. The initial incomplete diagnostic
run is preserved; comparisons use the corrected final snapshot.

Two initial behavioral tests passed, including actual saved RGB/native and
metadata binding. All six photos / sixteen regions were rendered and reviewed.
Folds connect better in supported locations, but regular engraving and smooth
skin remain; the overall strict naturalness decision is false.

## V14 — summarized C1 boundary correction

Boundary mixture means and inward slope corrections are joined to the
generated base with cubic Hermite weights. Correction and its derivative
vanish at the inner join; original pixels are never feathered into output.
The known synthetic shading fixture improves edge RGB RMSE from 0.842 to
0.534. The six-photo fixed coarse-cell boundary diagnostic improves on two
photos and worsens on four; it is not a naturalness score. All sixteen region
previews were reviewed. Some rims improve while others become brighter.
This experiment is retained for comparison; its boundary rule is not adopted
in subsequent versions. Strict naturalness acceptance remains false.

## V15 — pores in the generated height field

Pores use exclusion-spaced centers on newly generated ridge crests, three
radius groups and nonuniform depths. Their heights enter lighting before
rendering. The separate bright-dot layer is replaced with quiet independent
fine roughness. The V12 boundary rule is reused after V14's mixed results.
Tests confirm seed replay, crest placement and actual PNG/native/EXIF/ICC
preservation. Review of all sixteen development regions finds fewer detached
white specks but excessively smooth skin. This is not an overall appearance
improvement over V12 and does not pass strict naturalness review.

## V16 — pad-scaled flow and varying ridge cross sections

Independent flow geometry follows the pad aspect ratio. Spatially changing
width bias, shoulder shape and sharpness replace the uniform ridge profile.
Pores remain part of the generated height field. A known periodic fixture
exhibits local ridge duty-cycle standard deviation 0.0426; that test checks
width variation, not realism. All six photos / sixteen regions were reviewed.
Flow variation is visible, but the smooth engraved appearance remains. V16
does not establish an overall naturalness gain over V12.

## V17 — bounded crease depth and surface response

Each observed macro crease uses at most 96 scalar cross-section medians in
a robust three-coefficient depth fit, with depth bounded to 0–24 RGB levels.
The original coarse crease width is retained. An experimental width search
was rejected after its known shading fixture regressed. The bounded-depth
test recovers known synthetic crease depth from an incorrect starting depth.

Generated ridges, pores and folds share approximate diffuse/specular normal
response with independently generated roughness. This is an appearance model,
not a calibrated physical camera or skin model. Original ridge orientation,
phase and RGB residuals are not transferred. Coarse source appearance remains
source dependent, so this restriction is not a biometric privacy proof.

All six images / sixteen regions were reviewed in context, enlarged region
previews and original-pixel crops. Smooth skin, overly regular ridges and
joint-boundary differences remain. The five experiments are preserved, but
none establishes overall naturalness superiority to V12. V12 remains the
appearance comparison reference; no renderer is declared production ready.

## Final validation and publication scope

The final selected regression suite passes 77 distinct tests: 53 earlier
synthetic/appearance/residual checks, 11 V10–V12 material checks and 13 new
checks. All five batches complete six photos / sixteen regions each, replacing
4,703,163 authorized pixels per version. Original hashes, outside-mask RGB,
actual PNG readback and source metadata contracts pass. The real-photo V17
CLI also returns clean JSON and a verified saved PNG using a hash-bound cache.
The Windows launcher parses with new opt-in choices and keeps its existing
default. A fresh model/native GUI run, matcher evaluation and independent
naturalness/protection evaluation were not rerun for these appearance changes.

The 330 recorded previous renderer/output files retain their SHA256 values.
Final source snapshots remain immutable for reproducibility. Public delivery
contains code, tests, this description and anonymous aggregate findings.
Private photos, masks, source identities, comparisons, runtime copies and
weights are excluded. GitHub preparation is separate from actual publication.
The existing public geometry workflow now includes the same 77 synthetic
appearance contracts with bounded OpenCV threads. Its Linux Python 3.10/3.11
jobs are prepared for a future push; hosted CI was not executed locally.

## Reproduce an opt-in render

Use the existing hash-bound rounded native result for this exact input. It
must contain its source identity, native result and validated fallback masks.
An arbitrary mask directory is not a valid `--protection-run`. From the
repository root, with the existing AI dependencies installed:

```powershell
python ai/scripts/replace_photo_synthetic_v1.py --input "photo.png" --protection-run "native-run" --output "new-v17-run" --renderer v17 --seed 91
```

Choose `v13`, `v14`, `v15`, `v16` or `v17` to compare preserved versions.
The output directory must be fresh. The actual saved result is
`new-v17-run/synthetic.png`; `result.private.json` records the applied version,
source binding and limitations. Accepted native pixels are preserved and
only authorized fallback regions receive synthetic replacement. Outside-mask
RGB, input files and existing outputs are preserved. The CLI default remains
V1; no experimental version is automatically promoted.
