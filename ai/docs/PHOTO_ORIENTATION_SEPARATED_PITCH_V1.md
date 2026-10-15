# Orientation noise and original-profile pitch: V11 opt-in experiment

This is a new observer experiment using the existing V6 whole-pad detector and
unchanged natural_auto_04 / boundaryblend_02 renderer. V6 weights, training,
detector threshold, historical reports, unified PHOTO and GUI defaults remain
unchanged. It is not approved for production or complete-photo protection.

## Reproduced failure

The third image on comparison page 2 is development source 006. Its main
connected permission component was found; the full predicted pad has IoU
0.95246 and recall 0.95658 against its reviewed training target. Failure to
observe pitch was not caused by a missing pad or swapped coordinate axes.

All 24 existing V10 observation attempts were replayed with exact original
measurements. Across overlapping windows and preprocessing branches, 6,512 of
7,128 patch examinations failed orientation coherence before pitch measurement;
556 failed ROI support, 43 ACF, and 12 contrast checks. These are repeated patch
examinations, not independent samples. Five periodic candidates remained; only
one met the existing strict credible-periodic criteria. The original observer therefore correctly reported
insufficient evidence under its current measurement method.

Direction and source/working/512 pitch units were checked independently on
known-period synthetic images. Fine texture in the original orientation input
can obscure ridge direction. Paired locations in the recovered observation
window had raw coherence 0.218–0.412, compared with 0.671–0.781 after orientation
reference filtering, while actual periodic profiles remained from original raw
pixels. This supports a measurement-method limitation; it does not establish a
camera fault or a ground-truth physical ridge spacing.

## New, separate measurement path

`photo_orientation_separated_pitch_v1.py` uses fixed Gaussian sigma 2 and 4
references on the canonical 512-pixel image solely for direction/coherence.
It samples and measures the original, unfiltered raw profiles. Both references
must satisfy the existing ROI/coherence/contrast/ACF, minimum credible patch,
relative-IQR, pitch-range and relative-agreement numeric criteria. Direct profile
sampling must remain within the same connected permission component. No default
pitch is generated and no thresholds are lowered.

The two references share the original image and ACF procedure; they are not
independent biometric evidence. Orientation/ROI preprocessing can use surrounding
context, so preprocessing-context independence is not claimed. This method
changes evidence acceptance and is explicitly not frozen-gate equivalence.

`photo_learned_pad_pipeline_v11.py` runs the complete original V10 preparation
first. An existing accepted observation/renderer is returned directly. Only an
exhausted `component_local_pitch_unobserved` result permits the new observer.
Width, allocation, ownership and feature-gate failures cannot trigger it. A
failed rendered candidate is not retried to search for a passing feature count.

The renderer must reobserve the same raw frame, seed and connected permission
and reproduce the entire preflight measurement. Scoped binding is locked and
restored on exceptions. Output is copied only into its native permission
component; rejected and exterior RGB remain original.

## Measurement and remaining rejection

Development source 006 recovered pitch 16.668908 at 512 resolution, or 10.743632
working pixels / 10.689011 encoded native pixels. The two reference medians were
16.658063 and 16.679754 with 3 and 5 credible patches and relative disagreement
0.001301. This is observed image periodicity, not physical DPI or independent
annotation of actual ridge spacing.

The unchanged subsequent structure check then rejected that rendered candidate:
SourceAFIS extraction succeeded for both images, with 13 original and 9 candidate
features inside the permission mask. The existing prototype predicate requires
at least 10 in both. Skeleton change and same-coordinate feature difference
passed, but they cannot override insufficient features. Returned RGB therefore
remains original. This additional rejection is a functional-gate policy, not
evidence of a pitch, extraction or coordinate error, and feature scarcity is not
treated as protection success.

An independently replayed fixed synthetic set contained 90 known-period signals
and 38 nonperiodic controls. The new observer accepted 54/90 signals, all within
10% of known pitch, and accepted 0/38 controls. Noise standard deviations 0/20/40
gave acceptance 21/30, 15/30 and 18/30; respective maximum absolute accepted
errors were 0.05586, 0.06584 and 0.12027 pixels. Public implementation exactly
matched all 128 stored private input/measurement records. This small synthetic
set is not a general false-acceptance or security validation. Known clean edge
periods can still reject; the method is a fallback, not a replacement.

The full same-model 13-photo training-fit cohort was run through actual V11,
without target input to detection or protection. Two connected components in
sources 006 and 011 recovered observations. Source 011 also passed the unchanged
structure check (93 original / 45 returned-candidate features inside permission).
Its accepted component covered 144,188 target pixels out of 145,327 permission
pixels. Of 132,882 changed pixels, 132,348 were inside the target and 534 outside.
This is conditional overlap with the reviewed target, not validated protection.

| Same V6 detector, development photos | V10 | V11 |
| --- | ---: | ---: |
| Photos with actual returned RGB changes | 8/13 | 9/13 |
| Accepted mask overlap / full target | 52.4319% | 56.2086% |
| Changed RGB overlap / full target | 49.5343% | 53.0009% |
| Changed pixels outside target | 15,680 | 16,214 |

Every previously accepted V10 region retained exact returned RGB. Every rejected
region and pixel outside accepted permission remained original, with
`changed ⊆ accepted ⊆ predicted`. Sources 001, 006, 007 and 008 remain unmodified.
The unchanged prediction covers 90.1453% of the full target union. Accepted-mask
coverage and changed-pixel coverage are distinct, and neither proves that all
ridge information inside those pixels was removed. New group generalization
and a new Linux execution of V11 are not verified.

All 506 AI unit tests passed. Actual Windows launcher execution with a fresh
COLFISPOOF worker, Unicode/space source path and EXIF 6 reproduced a prior
success's mask and RGB exactly. The final CLI metadata separates rejected
candidate presence from RGB preservation; the final cached-semantics CLI also
passed its actual JSON/output/input-preservation checks.

## Boundary-only processing

Existing V10/V11 already observes pitch in a supported subwindow and renders
the entire connected permission component after its checks. It does not require
a separate reliable pitch for every pixel in the pad. Observing an anatomical
boundary alone cannot supply the ridge period used by the current natural
renderer's synthesis, low-pass separation and blend widths.

A separately specified opaque redaction can replace all pixels within a mask
without pitch. It has a different appearance and verification contract. Blur or
mosaic strength cannot be justified by a guessed ridge period. All such methods
still depend on finding the full pad; this example's predicted mask misses
10,747 target pixels. No boundary-only fallback is silently enabled here.

## Explicit execution

```powershell
python ai/scripts/protect_photo_whole_pad_context_noise_v1.py --input <photo> --model <private-V6-model> --consumed-registry <private-registry.json> --output <fresh-private-output>
```

This entry invokes configured COLFISPOOF, strict V6 checkpoint loading and the
separate V11 pipeline without human-mask input. RGB/L and white-composited RGBA,
encoded EXIF coordinates, source-bound semantics, fresh output, input/model/code
hashes and JSON stdout retain the previous contracts. Source images, targets,
weights, cached maps and per-source diagnostics remain private.

See `PHOTO_ORIENTATION_SEPARATED_PITCH_V1_STATUS.json` for completed verification
and same-model cohort results. These 13 photos were used in model training and
development. Their outcomes cannot establish performance on a new acquisition
group, complete ridge removal, matcher resistance or general privacy.
