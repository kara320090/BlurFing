# Whole-pad targets: reviewed development data and V4 model experiment

The PHOTO target is the entire visible palmar distal pad, including less clear
ridge areas inside a confidently identified anatomical boundary. Evidence may
be measured in a clear interior patch, but a small clear patch must not silently
become the entire permission mask. Candidate outlines and changed RGB are not
proof of complete fingerprint protection.

## Verified human annotations

`import_whole_pad_annotations_v1.py` imports exports from the local whole-pad
annotation tool. It makes a bounded private ZIP snapshot while checking the
expected SHA-256, verifies the member allowlist and hashes, human attestations,
source/encoded/upright identities, metadata, group consistency, and binary PNG
mask dimensions. It re-rasterizes reviewed polygons and applies inverse EXIF;
the stored encoded-coordinate mask must match exactly. Synthetic reviews cannot
be imported as human GT. Output must be fresh; source ZIP and originals remain
unchanged. The imported data and generated reports must stay private.

```powershell
python ai/scripts/import_whole_pad_annotations_v1.py --zip <private.zip> --sha256 <verified-SHA256> --output <fresh-private-folder>
```

In the reviewed 13-photo development cohort, the frozen earlier model has macro
IoU **0.552632**, recall **0.567548**, and precision **0.960793**. The observed
body covers **0.981958** of GT on average, so the body intersection also places
an upper bound on detector coverage. These scores use full human GT; GT is not
clipped to body for training labels or evaluation. The earlier V8 output changes
RGB in 3 photos and 8.773% of total GT area. This is an area diagnostic, not a
protection success rate. The 1,297 changed pixels outside GT require boundary
review; they cannot all be called definite anatomical false positives.

Four/eight-connected raster components and the number of additive polygons are
not anatomical finger counts. A diagonal pixel can create a 4-connected fragment;
an overlapping corrective polygon can belong to an existing pad.

## V4 data and training contract

`pad_whole_target_training_v4.py` preserves the V3 GT-free native-body tile plan,
input crop bytes, geometry, architecture, numeric loss/optimizer settings,
probability merge, and 0.5 prediction threshold. A separate V4 training manifest
attaches new whole-pad GT with exact source/mask/metadata hashes. Training RGB and
coarse inputs must equal the separate zero-label inference assets, and labels
must equal the original GT through the already frozen bbox/letterbox operation.

Legacy GT10 retains its historical unspecified pad-boundary policy; it is not
retroactively certified under the new first-crease definition. Legacy and new
policy metrics must be reported separately.

The new 13 photos form one conservative archive cluster, with acquisition and
person independence explicitly unverified. Together with the two historical
acquisition groups, this produces three leave-group-out **development** folds.
Photos and fingers are not split into independent groups. Group evidence is
hash-bound, and splits are recomputed rather than accepted from arbitrary lists.
The cohort has already been inspected and cannot be a pristine final test.

`train_whole_pad_target_v4.py` initializes every fold from the official ImageNet
encoder, never from the old GT10 final model. This avoids heldout GT10 leakage.
It reuses V3 per-source weighting, aligned augmentation, BCE+Dice, optimizer,
batch size, seed, early stopping, and final-epoch rule. Prediction uses verified
immutable GT-free input snapshots with the same V3 forward/merge operations;
numeric equivalence is tested. Original files, all crop assets, GT, grouping
evidence, configuration, and dependent code remain hash-bound through final
checkpoint publication. Changed assets prevent a completed config.

```powershell
python ai/scripts/train_whole_pad_target_v4.py --dataset <private-v4-dataset> --encoder-weights <official-weights> --output <fresh-private-model-folder>
```

OOF results have participated in early stopping and are developmental. Final
all-source training-fit scores must be distinguished from OOF and final
independent validation. V4 model weights are private and remain unapproved.

## V4 inference and optional spatial observation

`infer_whole_pad_target_v4.py` loads only a completed matching V4 development
config, verifies checkpoint/protocol/dependent code, applies the declared CPU
determinism, and consumes the existing GT-free V3 inference contract. It does
not require GT at inference. V3 checkpoints cannot be relabeled as V4.

`protect_photo_whole_pad_v2.py` is a separate opt-in single-photo entry point:

```powershell
python ai/scripts/protect_photo_whole_pad_v2.py --input <photo> --model <private-V4-folder> --consumed-registry <private-registry.json> --output <fresh-private-output>
```

It uses V8 component-local evidence by default. Optional
`--experimental-spatial-observation` selects V9. The original unified/default
and learned-V1 entry points, V3 weights, V8 source, frozen renderer math, and
quality thresholds are preserved.

V8 usually proposes only one observation position per connected permission.
V9 retains that complete seed prefix and adds geometry-only positions nearest
fixed quarter/center grid targets, with the same body-supported square-size rule
and total budget of at most eight. The first accepted pitch wins. Feature or
renderer results cannot select another seed. Real profile footprints remain
inside the same permission component, and renderer remeasurement must match the
selected seed, source RGB, pitch and measurement. Ownership accuracy remains
unverified. The allocation limit is a planning bound, not a measured RSS claim.

Neither path falls back to a fabricated pitch, weakens a gate, expands permission
to another finger, or treats an unchanged rejected image as successful protection.
Photo detector and production protection approval remain false pending suitable
independent validation.

An additional `--experimental-multiscale-observation` option selects V10; it
cannot be combined with the V9 flag. V10 preserves the complete V9 proposal
prefix, then appends the maximal axis-aligned body-contained square at each
existing center and the integer geometric midpoint between its old and maximal
half-size. Bboxes are deduplicated, with at most 24 sequential observations.
The body crop, halo, working raster, permission and all quality criteria remain
unchanged. Actual body slices, including holes and raster edges, determine
containment. No RGB, GT, pitch or renderer outcome selects the geometry.

This addresses a confirmed geometric limitation: every observation is resized
to 512 pixels, so the unchanged 4--24 normalized pitch band represents different
native periods when crop size changes. Improving a pad boundary can otherwise
move useful evidence out of that band. The first accepted pitch still wins;
feature/renderer failure does not trigger another seed search. Larger context
is not independent of permission-exterior preprocessing, and anatomical body
ownership remains unverified. More attempts can increase CPU cost. Same-input,
same-mask prefix success is preserved; success monotonicity across different
masks/models is not claimed.

In the fixed earlier-model 13-photo comparison, V9 changes 4 photos versus V8's
3, with all previously changed RGB pixels identical. GT-intersecting changed
pixels increase from 334,949 to 439,418; changed pixels outside GT increase from
1,297 to 1,378. One newly accepted component requires the seventh observation
attempt. This isolates a real single-position usability limit, but does not
establish full-pad detection or production safety.

V10 changes 6/13 of these same earlier-model photos, versus 3/13 with V8 and
4/13 with V9. GT-intersecting changed pixels are 665,907/3,817,798 (17.442%),
versus 334,949 with V8; changed pixels outside GT are 1,565. Every previously
changed V9 pixel remains identical, and no prediction-exterior pixel changes.
These are actual returned RGB comparisons on consumed development data, not
independent protection success rates or a complete-pad guarantee.

Using the same full-GT pixel denominator, detector permission covers 46.991%
for all three versions. Gate-accepted component area covers 9.527% (V8),
12.494% (V9), and 18.911% (V10). Actual changed GT area covers 8.773%,
11.510%, and 17.442%, respectively. These area-weighted fractions differ from
the earlier per-photo macro recall. Replay checks verify changed pixels are a
subset of accepted components, accepted components are a subset of permission,
and every rejected component and permission exterior retains original RGB.

An oracle-permission diagnostic explicitly uses human GT intersected with the
observed body and is never an inference result. One selected pad's changed area
increases from about 42% to 94% of full GT, whereas other selected photos still
reject for unobserved pitch even with this target permission. This separates
detector undercoverage from downstream observation/quality limitations.

Using V10 in that same explicitly GT-assisted oracle diagnostic, two previously
pitch-rejected single-pad photos change about 93% of full GT; a multi-finger
photo remains rejected. This confirms an observation-geometry limitation in
those examples without establishing autonomous whole-pad detection accuracy.

## Completed group-development validation

Three fresh-initialization folds select epochs 19, 2 and 12; the fixed final
training rule selects 12 epochs. Native OOF source-macro IoU is 0.552743 and
equal-group macro IoU is 0.500480. Legacy-policy GT10 macro IoU is 0.395225;
new whole-pad GT13 macro IoU is 0.673910. The new-cohort fold trains only on the
legacy ten and uses all 13 new photos for developmental early stopping. Its
score is not evidence of learning from the new labels or an independent final
test. Final all-23-source training-fit results are a separate measurement.

The completed V4 final fit is 0.574985 on new GT13 and 0.205768 on legacy
GT10; it is not adopted as an improvement. A separate
[V5 class-balance experiment](PHOTO_WHOLE_PAD_BALANCED_V5.md) tests the training
objective hypothesis while retaining this run and its failures as evidence.

V4 final + V10 on consumed GT13 training-fit data changes 6/13 photos:
permission/GT 48.525%, accepted/GT 20.105%, and changed/GT 18.352%
(700,634/3,817,798 pixels), with 646 changed pixels outside GT. This is still
far from complete-pad coverage. Its difference from the earlier model + V10's
17.442% changed area is not an independent validation result. Full-GT A/P/C
checks and exterior/rejected RGB preservation pass for all 13 photos.

The actual V4 single-photo CLI also matches batch prediction and returned RGB
exactly with original-JPG cached semantics. A Windows PowerShell launcher test
using a Unicode/space filename and a fresh COLFISPOOF worker matches the same
mask/RGB, preserves EXIF and the source, and consumes no GT at inference. These
are integration checks and do not approve the model's detection performance.

## Training balance observation

The 23-source dataset has 657 tiles, including 478 empty-target tiles (72.75%).
Under the unchanged per-source weighting, empty tiles contribute 73.78% and
foreground pixels 6.965% before augmentation. Source weighting does not balance
foreground/background classes. Empty-target smoothed Dice can have high scalar
loss despite background probabilities already being below the binary threshold;
scalar loss is not evidence of pad accuracy. This is an improvement hypothesis,
not proof of the sole cause. A future separately frozen objective could balance
classes using train-fold statistics and distinguish positive-target Dice from
empty-target BCE while preserving negative examples for nail/background errors.
