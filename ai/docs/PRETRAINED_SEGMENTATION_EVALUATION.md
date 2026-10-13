# Pretrained fingerphoto segmentation evaluation: blocked, not completed

No pretrained inference, benchmark, model approval or protection adapter connection was performed. Model comparison cells are **N/A**, not zero. No training/fine-tuning or threshold optimization used the four human development masks.

## Verified research and unresolved availability

- [mobiofp](https://github.com/rotiroti/mobiofp) advertises `fingertip-seg-amd64.h5`. Its [software license](https://github.com/rotiroti/mobiofp/blob/main/LICENSE.md) is MIT. The [models directory](https://github.com/rotiroti/mobiofp/tree/main/models) listing does not bundle the advertised segmentation H5. External download target, actual weight SHA-256 and weight-specific terms remain unverified.
- [Segmentation source](https://raw.githubusercontent.com/rotiroti/mobiofp/main/mobiofp/segmentation.py) defines a 256×256×3 U-Net and single sigmoid channel. Training uses RGB and division by 255. Prediction uses INTER_AREA resize and division by 255, then `>0.5`, binary resizing and morphology. The source loads weights via `load_weights`, not an assumed full-model H5 loader. The predictor itself does not convert channels: caller color order must be checked. [Requirements](https://github.com/rotiroti/mobiofp/blob/main/requirements.txt) do not pin TensorFlow; the checkpoint's actual compatible Keras/TensorFlow version is unknown.
- [TransResUNet repository](https://github.com/Kaplesh12/Fingerprint-Segmentation-) describes a Keras/TensorFlow residual UNet with transformer blocks and links ISPFDv1. Its [notebook](https://github.com/Kaplesh12/Fingerprint-Segmentation-/blob/main/CFSeg%20TransResUNet.ipynb) is listed as 52 MB; the browser cannot display its content. The extensionless `Transresunet` entry is a file, not a confirmed model directory. Its content, a pretrained contactless checkpoint, license, input/output and ISPFDv1/v2 preprocessing remain unverified. **Do not infer checkpoint absence from this incomplete inspection.**

These are primary upstream browser/cache observations, not a downloaded pinned checkout. Direct repository/raw/API requests include cache misses, 404, timeout and 429. Some cached pages remain readable even though this workstation cannot resolve GitHub. Do not interpret failed retrieval as proof that the upstream project was deleted.

## Local blockers

All three requested GitHub host lookups fail; curl reports DNS resolution failure. No relevant H5/Keras checkpoint or repository cache was found in the inspected local paths. DNS, firewall and VPN settings were not changed. `resolvectl` status cannot access the system bus here. GPU execution is unavailable because nvidia-smi cannot communicate with the driver; GPU hardware absence is not asserted.

A separate temporary Python 3.10 venv was created. Package download produced no TensorFlow wheel; no dependency was installed. The existing project venv is untouched. CPU inference remains a plan, not a measurement.

## Honest comparison baseline

The existing masks are **unapproved foreground proposals**, not accepted protection artifacts.

| Sample | Existing IoU | Existing Dice | Recall | matched/GT regions | mobiofp | TransResUNet |
|---|---:|---:|---:|---:|---|---|
| DET-01 | 0.4477 | 0.6185 | 0.4541 | 1/2 | N/A | N/A |
| DET-03 | 0.9668 | 0.9831 | 0.9841 | 1/1 | N/A | N/A |
| DET-04 | 0.5556 | 0.7143 | 0.5581 | 2/3 | N/A | N/A |
| DET-05 | 0.6273 | 0.7710 | 0.6345 | 1/1 | N/A | N/A |

Baseline macro IoU is 0.6493; pooled nonzero-overlap component recall is 5/7. Four original/GT source contracts were checked again (encoded 4000×3000, 8-bit binary PNG, matching hashes and EXIF). Human masks and original JPGs remain private and read-only. No generated segmentation is passed off as pretrained output.

## What was implemented locally

`evaluate_model_segmentation_masks.py` evaluates external raw/safe prediction masks and their local weight/provenance checksums. It reports IoU, Dice, precision, recall, outside-GT fraction, missed-GT fraction, area ratio and one-to-one component assignments. Empty prediction precision is undefined. A merged component cannot claim multiple GT components. Nonzero-overlap matching is a diagnostic and is insufficient alone for model approval.

The optional probability-to-native helper explicitly interpolates probabilities before thresholding and undoing EXIF. That is an **alternative evaluation mapping**, not equivalence to mobiofp's binary-before-resize pipeline. The actual upstream raw pipeline must be recorded separately when checkpoint inference becomes available. Its largest-contour ROI helper must not discard other fingers; evaluation keeps all components. Default primary threshold remains 0.5. No GT-optimal threshold is selected.

No `model_fingerprint_detector` is connected because there is no measured winning model. No segmentation mask is emitted as an accepted v1 protection artifact. Frozen square-scope and pitch 2..50 constraints remain a separate renderer issue, including the observed long-pad pitch 52.2299.

Tests: 8 new synthetic tests + 28 existing contract tests PASS; all 49 Python files pass syntax checks. These test geometry/metrics/integrity, **not pretrained inference or model determinism**. No private output, weight, dataset or runtime is committed.

## Resume prerequisites

Restore ordinary repository/package download access without changing project algorithms. Retrieve the real upstream trained H5 and source revision, record SHA-256 and confirm its terms/framework compatibility. Inspect exact inference callsite/color order and TransResUNet checkpoint/terms. Then run original JPG-only inference, fixed primary 0.5 threshold, raw versus declared safe postprocessing, four-mask evaluation, deterministic repeats and warmup+10 CPU/GPU benchmark. Only measured improvement and leakage evidence can justify a detector adapter; renderer blockers must not be relabeled as model segmentation failure.

PRETRAINED_MODEL_EVALUATION_COMPLETE=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
