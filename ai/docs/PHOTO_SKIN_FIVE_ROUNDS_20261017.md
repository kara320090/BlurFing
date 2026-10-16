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
preservation. Independent appearance review is recorded after the batch.
