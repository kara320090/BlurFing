# COLFISPOOF raw semantic GT7 evaluation

Primary policy was fixed before evaluation: fingertip **label ID 2**, four CW rotations 0/90/180/270, encoded-original coordinate inverse mapping, pixel votes >=2/4, no component cleanup. GT was used only after predictions were saved. Official `segment()` and its contour, convex-hull, crop and black-area rejection were never invoked. The official 1024 letterbox preprocessing and DeepLab `run()` were retained.

The official PASCAL colormap maps IDs 0/1/2 to black/red/green; `segmentation.py` includes IDs 1+2 for finger area and only ID 2 for fingertip. Actual model outputs contain IDs 0, 1 and 2. Selection uses integer semantic labels, not rendered colors.

## Fixed primary result

| Sample | IoU | Dice | Precision | Recall | Leakage | Coverage | Unmatched predictions | Missed pads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.8631 | 0.9265 | 0.9611 | 0.8944 | 0.0389 | 2/2 | 0 | 0 |
| DET-03 | 0.0000 | 0.0000 | undefined (empty prediction) | 0.0000 | undefined (empty prediction) | 0/1 | 0 | 1 |
| DET-04 | 0.7495 | 0.8568 | 0.9961 | 0.7517 | 0.0039 | 3/3 | 0 | 0 |
| DET-05 | 0.2873 | 0.4463 | 1.0000 | 0.2873 | 0.0000 | 0/1 | 1 | 1 |
| CAP-016 | 0.0490 | 0.0934 | 0.9916 | 0.0490 | 0.0084 | 0/1 | 1 | 1 |
| CAP-042 | 0.7129 | 0.8324 | 0.9993 | 0.7132 | 0.0007 | 1/1 | 0 | 0 |
| CAP-054 | 0.8197 | 0.9009 | 0.9978 | 0.8212 | 0.0022 | 1/1 | 0 | 0 |

Macro IoU: **0.4973** versus legacy **0.4913** (delta +0.0061); coverage **7/10**, unchanged from legacy. Unmatched predictions decreased from 4 to 2; missed pads remain 3.

The two unmatched predictions are small real-fingertip subsets in DET-05 and CAP-016 failing the fixed IoU>=0.5 matching criterion. They are not two wrist/background detections. Private overlay inspection found no severe wrist, keyboard or background selection. DET-01 retains both visible fingertips; DET-04 retains three. CAP-042 recovers the real fingertip and CAP-054 avoids background selection. DET-03 has zero class-2 pixels in every rotation although finger-body class 1 is present. This is a semantic fingertip localization failure on a close-up, not a renderer or official postprocess failure. DET-05 and CAP-016 terminate the pad too early.

`COLFISPOOF_RAW_FRONTEND_PROMISING=false`: coverage does not improve and macro IoU gains only about 0.0061. `PHOTO_DETECTOR_APPROVED=false`: macro IoU<0.85 and coverage<90%. Structural false-positive reduction is useful evidence but insufficient for primary adoption. No Canonical ROI adapter was integrated and no PHOTO protection or matcher evaluation ran.

## Rotation diagnostics

Rotation choices were never selected by GT. The following are diagnostics only, not alternative final scores.

| Sample | Raw components (0/90/180/270 CW) | Consensus components | Union IoU | 3/4 IoU | Intersection IoU |
|---|---|---:|---:|---:|---:|
| DET-01 | 2/2/2/2 | 2 | 0.8453 | 0.8263 | 0.6983 |
| DET-03 | 0/0/0/0 | 0 | 0.0000 | 0.0000 | 0.0000 |
| DET-04 | 3/3/3/3 | 3 | 0.8078 | 0.6549 | 0.5252 |
| DET-05 | 1/1/1/1 | 1 | 0.4294 | 0.2132 | 0.1361 |
| CAP-016 | 1/2/1/0 | 1 | 0.2244 | 0.0000 | 0.0000 |
| CAP-042 | 1/1/1/1 | 1 | 0.8613 | 0.6288 | 0.4203 |
| CAP-054 | 1/1/1/1 | 1 | 0.8649 | 0.7608 | 0.6358 |

All seven consensus mask pixel hashes and PNG hashes were identical across three complete inference repeats. The ten measured benchmark runs were also identical. This establishes semantic-mask determinism in this CPU environment, not floating-point logit equivalence on other hardware.

## Separate ridge-validation result

The unchanged shared BlurFing ridge validator was applied per raw component crop, with its default thresholds. Macro IoU: **0.0623**, coverage **0/10**. Its sparse masks are a separate diagnostic and are not mixed into the primary result. No threshold was tuned to GT. This evidence rejects immediate integration of the current raw-plus-ridge chain.

## CPU benchmark

TensorFlow 2.10.0 / OpenCV 4.6.0 / NumPy 1.21.6 / Pillow 9.3.0. CUDA 11 runtime libraries are unavailable; no GPU repair was attempted. Representative input: DET-01, one warm-up excluded, ten measurements, eight intra-op threads.

| Stage | Mean seconds | Median | p95 |
|---|---:|---:|---:|
| preprocessing | 0.1223 | 0.1185 | 0.1392 |
| one_rotation_inference | 0.3897 | 0.3964 | 0.4312 |
| four_rotation_inference | 1.5586 | 1.5855 | 1.7250 |
| inverse_mapping | 0.0647 | 0.0706 | 0.0827 |
| consensus | 0.0442 | 0.0432 | 0.0487 |
| total | 2.2532 | 2.2681 | 2.4294 |

One-rotation inference is the average of four individually timed sequential rotations in each measured run. Inference includes the model's PIL resize. Total includes semantic label histogram bookkeeping; it excludes graph loading, source decoding and output PNG writes. Hence stage sums need not equal total.

## Mapping validation and implementation correction

Encoded JPG pixels are decoded without EXIF transposition. Each explicit rotation is inversely mapped. Semantic labels are resized by nearest-neighbor to the exact letterbox shape; recorded padding is removed; native rotated size is restored; rotation is inverted. Shapes and synthetic landmark positions were tested.

The initial compatibility implementation incorrectly interpreted upstream's third positional `cv.resize` argument as interpolation. Pixel-equivalence testing showed that it is actually the optional `dst` parameter, so upstream uses default LINEAR interpolation. The wrapper was corrected and **all 21 GT7 inference runs and all benchmark runs were rerun**. Initial outputs are excluded. Final preprocessing matched the extracted upstream `crop_to_size` function pixel-for-pixel on landscape, portrait, odd-padding and already-1024 cases. This was an upstream compatibility correction, not GT score tuning.

## Tests and preservation

102 unit tests passed, including all existing tests and nine new semantic/geometry/consensus/GT-isolation tests. The unchanged scanner smoke returned pixels identical to its previous public-fixture output, transformed one ROI, changed 95,930 pixels and preserved exterior pixels. Frozen transform, legacy detector, scanner core, source images, GT and matcher runtime were not edited. Checkpoint and 55 canonical capture hash preservation were separately checked.

## Provenance and scope

External model archive SHA-256: `f58d510ac9e83c4b5398f580446aef6028890993da052cacab048f434888b60f`, 461,852,540 bytes. No external source or weight is vendored. Source mapping and model runner hashes are recorded in the status JSON/private provenance record. See [COLFISPOOF](https://github.com/dasec/COLFISPOOF). Acknowledge J. Kolberg, J. Priesnitz, C. Rathgeb and C. Busch, “COLFISPOOF: A new Database for Contactless Fingerprint Presentation Attack Detection Research,” WACV 2023. The upstream README requires this acknowledgment; weight/code redistribution permission is not assumed.

GT7 is a development evaluation set, not a training set or independent final holdout. General fingerprint protection, Windows full equivalence and project completion are not established. The next blocker is fingertip-class undercoverage, especially no close-up fingertip class in DET-03. Do not substitute class 1 or change voting based on GT scores.
