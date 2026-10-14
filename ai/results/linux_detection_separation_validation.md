# Separation and crease development experiment: not approved

The frozen natural_auto_04 renderer, boundaryblend_02 compositor, matcher settings and original data are unchanged. This follow-up changes localization only. Human GT is loaded only by the evaluator, never by the detector. No filenames, identities or sample-specific parameters are used.

## Changes and iterations

1. Add a conservative red-chroma proposal view alongside the unchanged skin view, with deterministic cross-view NMS. This prevents a wood-colored background connected to the original skin mask from hiding cap peaks in one positive example. It does not establish skin-tone generalization. Seed-centered contiguous scanline runs, robust width medians and broad-run rejection separate distal fingers from the shared palm.
2. A slope-constrained dynamic-programming dark-valley trace observes an oblique crease when a single horizontal scanline fails. Existing absolute response 1.5, coverage 0.65 and width-prior disagreement 0.2 gates remain. It is not an anatomy classifier, and can still choose an early line.
3. Local centerline-based rotation was evaluated on all four GT inputs and produced no metric improvement. It was removed rather than promoted or retuned. Arbitrary oblique and small-finger handling remain unvalidated.
4. Keep only the seed-connected native four-neighbor component after erosion/resizing, matching the consumer contract. This removes a detached speck; it does not use GT to clip pixels. The existing close-up foreground remains byte-identical.

## Foreground proposal metrics (not approved masks)

| Sample | Before IoU | After IoU | Precision | Recall | Prediction outside GT | matched GT regions |
|---|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.0000 | 0.4477 | 0.9694 | 0.4541 | 0.0306 | 1/2 |
| DET-03 | 0.9668 | 0.9668 | 0.9821 | 0.9841 | 0.0179 | 1/1 |
| DET-04 | 0.0000 | 0.5556 | 0.9920 | 0.5581 | 0.0080 | 2/3 |
| DET-05 | 0.0000 | 0.6273 | 0.9824 | 0.6345 | 0.0176 | 1/1 |

Raw macro IoU: 0.2417 → 0.6493. Foreground proposals exist in 4/4 rather than 1/4. Approved artifacts remain empty: **0 → 0 approved regions**, IoU/recall 0 for every approved output. One-to-one component matching is evaluation-only and does not select render candidates. Connected GT regions are not independently confirmed anatomical finger identities.

DET-01 still misses one of two GT pads. DET-04 recovers two of three pads (matched-component IoU approximately 0.92/0.89), but the tilted third remains absent. DET-05 still terminates too early: recall approximately 0.63 despite high precision. Private overlays also expose localized extra pixels. Prediction outside GT measures pad disagreement; it is not a separately annotated background/neighbor metric. No severe-background-leakage clearance is claimed.

## Long-pad scope contract

The close-up mask is preserved byte-identically. Two square scopes can cover every foreground pixel with uncovered_pixels=0, and no crop is used to remove GT area. This is a geometry-only plan, not an accepted artifact. The frozen transform rejects overlapping application masks. A disjoint partition adds internal compositor borders; each square is rendered with its own normalized coordinate system and seed/phase. The existing API has no cross-tile phase-continuity guarantee. Do not authorize a two-tile protection mask without a reviewed joint-rendering/composition contract. This experiment does not change frozen core mathematics to bypass that limitation.

## Regression and decision

- 28 synthetic tests PASS; 47 Python syntax checks PASS.
- Four real generated artifacts pass hash/EXIF/shape validation and return identical RGB when rejected. This is rejected pass-through, not applied protection.
- Existing sole legacy boundary remains pixel-identical.
- 20-photo regression: five provisional non-target examples produce no pad regions; all new masks remain review-gated. These negative labels are provisional, not expert negative segmentation.
- Source JPG and human GT hashes retained; checkpoint 303/303. Unrelated data changes are preserved.

**DETECTOR_APPROVED_FOR_USE=false.** Partial foreground improvements are retained as experimental source, not deployment approval. Transform, NBIS and SourceAFIS development evaluation are NOT RUN after this approval gate. Previous control matcher results are not substituted. New positive GT is available, but neither full multi-finger coverage nor long-pad seamless renderer compatibility is established.

## Timing: detector only

Warmup 1, measured 10, same representative private positive input; all raw-mask and region signatures deterministic. No concurrent heavy evaluation was run during this benchmark. This is not a ten-run applied-protection benchmark.

| Stage | mean s | median s | min s | max s | std s | p95 s |
|---|---:|---:|---:|---:|---:|---:|
| detection | 0.4746 | 0.4711 | 0.4673 | 0.4930 | 0.0082 | 0.4896 |
| boundary | 1.6724 | 1.6729 | 1.6655 | 1.6786 | 0.0042 | 1.6783 |
| detector_total | 2.1472 | 2.1446 | 2.1362 | 2.1699 | 0.0106 | 2.1674 |

Transform, NBIS, SourceAFIS and end-to-end protection times: NOT RUN, not zero.

## Reproduction

```sh
python ai/scripts/evaluate_detector_ground_truth.py --ground-truth-root /path/to/private/ground_truth --input-root /path/to/private/captures --output /path/to/new/private/evaluation
python ai/scripts/benchmark_detector_only.py --input /path/to/private/input.jpg --output /path/to/new/private/benchmark --repeats 10
python ai/scripts/test_boundary_separation.py
python ai/scripts/test_detector_ground_truth_metrics.py
python ai/scripts/test_detection_artifact.py
```

Private artifacts retain encoded masks, source/GT hashes, bboxes, scopes, component assignments and overlays. Public results contain anonymous numerical summaries only. No source image, GT mask, overlay, runtime or personal path is included.

FINAL_INDEPENDENT_VALIDATION_COMPLETE=false; PROJECT_COMPLETE=false. General fingerprint protection has not been demonstrated.

## Additional frozen pitch blocker
A read-only observation of the close-up automatic seed gives pitch_native=52.22992649627122. The frozen renderer and artifact validation require 2..50. Thus square coverage alone does not make this input transformable. The value was not clamped, the pitch guard was not widened, and no seed search was performed to force a passing measurement. Accepting this observation requires a separately authorized and validated frozen rendering-contract change; NBIS/SourceAFIS calculations remain untouched.
