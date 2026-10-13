# Unified fingerprint front-end: Linux development validation

The new public API routes content into PHOTO / FINGERPRINT_IMAGE / UNKNOWN and produces native-coordinate CanonicalFingerprintROI. Legacy rule/SAM modules and evaluations, natural_auto_04 and boundaryblend_02 are preserved. The new PHOTO branch is implemented but **not runtime-evaluated or approved**. The scanner branch is approved only for development on the tested fixtures.

## External code/model availability

[COLFISPOOF](https://github.com/dasec/COLFISPOOF) README describes fingertip preprocessing and requires publication acknowledgment. Its executable preprocessing code could not be retrieved locally because DNS resolution fails; no redistribution license was verified. No COLFISPOOF code was copied, executed or guessed. External use remains blocked pending code and license verification.

[MediaPipe Hand Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python) specifies the package, task model and IMAGE-mode inference. The [MediaPipe source license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) is Apache-2.0. Our adapter uses TIP/DIP/PIP-derived prompts and SAM Predictor, never AutomaticMaskGenerator. MediaPipe and the task model are absent locally; no cached copy was found and PyPI/model-host DNS fails. Thus no real MediaPipe+SAM inference or model-specific GT7 metrics are claimed. Torch/SAM checkpoint reuse is configured externally. GPU execution was unavailable because the NVIDIA driver did not respond.

## Photo GT7 and 55-image scan

All 55 existing captures route PHOTO; the absent primary runtime fails closed, producing no accepted photo protection masks. This is an availability check, not a detection accuracy measurement or proof that keyboard/wrist false positives are solved. Unannotated images are not used as an accuracy denominator.

| GT sample | Legacy crease-optional IoU | New primary execution | New IoU / coverage |
|---|---:|---|---|
| DET-01 | 0.9318 | blocked: model/runtime unavailable | NOT_EVALUATED |
| DET-03 | 0.0000 | blocked: model/runtime unavailable | NOT_EVALUATED |
| DET-04 | 0.9251 | blocked: model/runtime unavailable | NOT_EVALUATED |
| DET-05 | 0.9173 | blocked: model/runtime unavailable | NOT_EVALUATED |
| CAP-016 | 0.0000 | blocked: model/runtime unavailable | NOT_EVALUATED |
| CAP-042 | 0.0000 | blocked: model/runtime unavailable | NOT_EVALUATED |
| CAP-054 | 0.6645 | blocked: model/runtime unavailable | NOT_EVALUATED |

Legacy GT7 macro IoU 0.4913 / coverage 70% remains the comparison baseline. We did not replace its metrics with zero-mask availability results or claim improvement by abstention. Anatomical prompt construction/EXIF inverse mapping are tested with synthetic injected runtimes only. PHOTO protection remains gated until actual GT7 and structure/renderer checks pass. A legacy fallback can provide review diagnostics after landmark failure, but cannot automatically authorize protection.

## Scanner fixtures and transform

21 existing NBIS test-resource WSQ fixtures were decoded with the already verified official dwsq into private temporary files. All 21 route FINGERPRINT_IMAGE and produce a validated nonempty native ROI with ridge evidence. The scanner detector uses no hand detector or SAM. Multi-resolution analysis prevents ridge aliasing on larger scans; relative border/foreground evidence handles off-white cropped scans. Initial three router rejections exposed coarse-resolution loss and an overly absolute white-background assumption; no per-file rule was introduced.

Representative a011p_03: 336×512, measured pitch 8.8752 native px, ROI bbox [32,48,320,480]. The experimental scanner renderer reuses only the independent shared synthetic field generator, not the photo renderer/skin compositor. Source intensity statistics and edge blend are retained; source ridge orientation, skeleton and phase are not generator inputs. Existing structure criteria are reused unchanged through a scanner adapter: both point counts >=10, same-coordinate Dice <=0.9, at least two point changes, skeleton XOR/union >=0.05.

Actual structure check passes: SourceAFIS points 62→100, same-coordinate Dice 0.1728, skeleton change 0.6690. Returned output changes 95,930 pixels, preserves dimensions/dtype, and preserves every pixel outside the mask. Failed/unconfigured structure checks return the original. No scanner-specific threshold relaxation was performed.

| Matcher | Original features | Modified features | Self score | Original→Modified |
|---|---:|---:|---:|---:|
| NBIS | 87 | 182 raw / 150 pruned | 499 | 36 |
| SourceAFIS | 62 | 100 | 734.9330 | 3.1857 |

NBIS and SourceAFIS scales are different. Features remain extractable. These are one public-fixture development observations, not a general privacy proof, Windows equivalence or independent final validation. All 21 detection fixtures have no newly annotated foreground GT; foreground accuracy, multiple-print completeness and non-fingerprint periodic textures remain unverified.

## CPU benchmark

Representative scanner fixture: warm-up one excluded, ten measured applied runs. Includes real structure extraction, NBIS and SourceAFIS. All returned pixel hashes match. Routing includes an initial ridge probe, so subsequent ridge-validation timing includes a repeated probe; stages are not hidden or double-subtracted.

| Stage | Mean s | Median s | p95 s |
|---|---:|---:|---:|
| routing | 0.0564 | 0.0579 | 0.0604 |
| ridge_validation | 0.0452 | 0.0453 | 0.0462 |
| foreground_segmentation | 0.0015 | 0.0015 | 0.0015 |
| transform | 0.1583 | 0.1578 | 0.1608 |
| structure_check | 1.4576 | 1.4639 | 1.4920 |
| NBIS | 0.0793 | 0.0798 | 0.0883 |
| SourceAFIS | 1.0150 | 1.0037 | 1.0745 |
| total | 2.8447 | 2.8371 | 2.9044 |

Full min/max/std are in unified_frontend_status.json. PHOTO hand localization, SAM and transformation benchmarking was NOT_RUN. No GPU timing is claimed.

## Regression and preservation

93 tests and Python syntax checks pass. Tests cover unknown routing, grayscale scanner, colored-photo routing, source/mask/shape contracts, empty/nonbinary mask rejection, anatomical prompt construction, synthetic EXIF mapping, strength zero, structure failure original return, output collision rejection, legacy artifact/runtime dispatch and binding restoration. Legacy and frozen sources are unchanged. Canonical originals, checkpoint and runtime integrity were checked. Public code/docs/metrics only; no WSQ/JPG/PNG, GT, model weights, binaries or private paths are committed.
