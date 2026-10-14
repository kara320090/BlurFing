# Human ground-truth evaluation: detector not approved

Four human-reviewed positive development masks were verified against source SHA-256, mask SHA-256, binary values, EXIF metadata and encoded 4000×3000 dimensions. Automatic artifacts stay in upright EXIF coordinates; prediction masks were inverse-transformed for comparison. Original images and human annotations were read-only.

| Sample | GT polygons | Raw candidates | Approved regions | IoU | Precision | Recall | Area / GT | Main failure |
|---|---:|---:|---:|---:|---|---:|---:|---|
| DET-01 | 2 | 0 | 0 | 0 | undefined | 0 | 0 | no fingertip |
| DET-03 | 1 | 1 | 0 | 0 | undefined | 0 | 0 | frozen square scope incompatible |
| DET-04 | 3 | 2 | 0 | 0 | undefined | 0 | 0 | crease missing / neighbor connection |
| DET-05 | 1 | 1 | 0 | 0 | undefined | 0 | 0 | neighbor connection |

Approved-mask IoU, recall and area ratio mean/median/min/max are all 0. Precision and leakage fraction are undefined for all four empty masks, not perfect scores. False-positive rate is 0 because every mask is empty; **this is not evidence of usable leakage-safe detection**. Baseline and current approved usable regions remain 0/4.

## Rejected foreground diagnostic, not a protection mask

DET-03 has one raw foreground proposal before square-scope rejection: IoU 0.966772, precision 0.982131, recall 0.984081, leakage fraction 0.017869, negative-pixel FPR 0.022102, area/GT 1.001986. Encoded bbox delta relative to GT is [24,14,83,28] pixels. Its upright pad extent is 2460×3335 in an image of width 3000; a full containing square cannot fit without changing renderer geometry or silently truncating the pad.

Private overlay inspection shows broad agreement with the human close-up pad, with residual differences at the lower termination and sides. GT-exterior pixels are not automatically background: this metric measures disagreement with the chosen pad, including nearby skin. No background-negative annotation distinguishes these cases. The raw mask is retained privately, **not selected using matcher scores or promoted by its high IoU**.

No finger is selected for transformation. DET-01's two and DET-04's three annotated polygons remain missed by the approved output; candidate counts do not establish one-to-one finger correspondence. No proposal mask is available for the other three inputs, so their localization cannot be scored as a successful boundary.

## Decision and gate

**DETECTOR_APPROVED_FOR_USE=false.** The decision is based on absent usable masks in three positive inputs and scope incompatibility in the close-up, not a newly tuned IoU threshold. No mask is authorized, consumer policy is unchanged, and no transform/matcher/ten-run benchmark is rerun. Those checks are NOT RUN under the requested approval gate; previous separate developer-control results are not substituted.

Background leakage, multi-finger separation, rotated and small-input safety are not demonstrated. Positive masks alone do not validate non-target rejection. A new independent holdout is still absent; general fingerprint protection remains unproven.

## Reproduction and private evidence

```sh
python ai/scripts/evaluate_detector_ground_truth.py \
  --ground-truth-root /path/to/private/ground_truth \
  --input-root /path/to/private/captures \
  --output /path/to/new/private/evaluation
python ai/scripts/test_detector_ground_truth_metrics.py
python ai/scripts/test_detection_artifact.py
```

Each private sample folder contains the original detector artifact, encoded automatic mask, approved-overlay preview, raw-proposal masks/overlays when available, raw-union overlay and detailed metrics JSON including bboxes/scopes. No GT mask, input photograph, source identity/hash, personal path or preview is published. Approved union is scored separately from every unapproved proposal; no best-IoU oracle selection is used. Green=overlap, red=prediction-only, blue=GT-only.

Tests: 17 artifact tests + 4 metric/EXIF tests PASS. These are contract tests, not evidence of detector deployment readiness. Single-run detection times are recorded; a ten-run benchmark was intentionally not performed after approval failed. Frozen renderer, compositor and runtimes are unchanged; checkpoint 303/303 matches.

Next work: improve per-finger proposal/width isolation for the three failed positive inputs, retaining this GT set as development references and requiring negative/control validation before approval. Do not alter the frozen renderer just to make the close-up pass.
