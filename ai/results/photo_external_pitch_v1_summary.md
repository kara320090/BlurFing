# External observed pitch v1 development diagnostic

Frozen v4/natural_auto_04/boundaryblend_02 and coarse detector remain unchanged. New opt-in entrypoint uses unchanged lower-level whole_pad_skin_relief code, not baseline-output equivalence. Detector/production approval remain false. Rules were fixed before photo inference; no GT mask or threshold tuning.

## Observers and gates

All pitches below are working-image pixels. `null` means no approved pitch, not zero. Cue medians may exist when insufficient patch count or cross-patch instability prevents acceptance.

| Sample/pad | Frozen pitch | ACF | FFT | Accepted patches | Relative IQR | External status | V1 outcome |
|---|---:|---:|---:|---:|---:|---|---|
| DET-01/1 | 9.4824 | 7.2590 | 7.7158 | 8 | 0.1826 | cue_disagreement | cue_disagreement |
| DET-01/2 | 9.9175 | 8.9338 | 9.1434 | 8 | 0.0956 | accepted | original_width_unavailable |
| DET-03/1 | 9.4847 | 10.0546 | 10.1073 | 10 | 0.0595 | accepted | applied |
| DET-04/1 | null | 10.6246 | 11.0003 | 2 | 0.0401 | insufficient_patches | insufficient_patches |
| DET-04/2 | 7.7979 | 6.9034 | 7.2322 | 6 | 0.1477 | accepted | applied |
| DET-04/3 | 9.4133 | 8.9292 | 8.6421 | 10 | 0.1173 | accepted | insufficient_features |
| DET-05/1 | 10.9338 | 11.0712 | 11.1963 | 14 | 0.1692 | cue_disagreement | cue_disagreement |
| CAP-016/1 | null | null | null | 0 | null | unstable_orientation | unstable_orientation |
| CAP-042/1 | 7.8208 | 9.2291 | 9.5063 | 12 | 0.1609 | cue_disagreement | cue_disagreement |
| CAP-054/1 | null | null | null | 0 | null | no_periodicity | no_periodicity |

CAP-016: no accepted oriented periodic patches; CAP-054: no accepted periodic evidence. No default pitch generated. DET-01 remains blocked by existing width estimator. DET-04/3: existing structure gate counts 2→3, below ten. DET-05 rejects at external multi-patch agreement first; its older feature failure remains unresolved and was not bypassed.

## Actual returned RGB matcher observations

Same Canonical 512px grayscale letterbox from original and native returned RGB; adapter default 500 DPI, unknown physical DPI. This differs from width-normalized frozen structure-check frames. No thresholds or matcher logic changed.

| Sample/pad | NBIS features | NBIS self → returned | NBIS comparison status | SourceAFIS features | SourceAFIS self → returned |
|---|---|---|---|---|---|
| DET-03/1 | 23 → 30 | 114 → 3 | ok | 2 → 0 | 16.5869 → 0.0000 |
| DET-04/2 | 8 → 4 | 0 → 0 | insufficient_features | 0 → 0 | 0.0000 → 0.0000 |

DET-03 has a comparable NBIS extraction pair and a lower development score. Other low-feature or zero-score observations do not prove privacy/protection. No generalization claim.

## CPU benchmark

DET-03, one excluded warm-up and ten repeated successful runs. Evidence, returned RGB and matcher-input hashes identical. Cache-based consumer includes internal observer diagnostic, external observer, coarse adaptation, rendering/compositing, original structure checks and matchers. COLFISPOOF inference is excluded.

| Stage seconds | Mean | Median | Min | Max | Std | p95 |
|---|---:|---:|---:|---:|---:|---:|
| consumer | 4.3734 | 4.3107 | 4.2702 | 4.6942 | 0.1294 | 4.6242 |
| NBIS | 0.0563 | 0.0570 | 0.0494 | 0.0653 | 0.0055 | 0.0637 |
| SourceAFIS | 0.9138 | 0.8995 | 0.8935 | 0.9945 | 0.0303 | 0.9717 |
| total | 5.5868 | 5.5140 | 5.4829 | 5.8917 | 0.1353 | 5.8415 |

Separate observer / renderer-structure microbenchmark (same warm-up and ten repeats):
- observer: mean 0.0204s, median 0.0200s, p95 0.0234s.
- renderer_structure: mean 1.5235s, median 1.5141s, p95 1.5635s.
- total: mean 1.5440s, median 1.5335s, p95 1.5831s.

## Tests and preservation

Evidence schema, source/mask/pixel/space mismatch, insufficient patches, ACF/FFT disagreement, invalid pitch/no clamp, multi-patch spread, conversion, flat-input rejection, determinism and unchanged gate/global-binding tests pass. Full public suite: 131 pass, three optional Torch tests skipped. V4 seven-image byte regression and scanner fixture pixel regression pass. Checkpoint 303/303 and captures 55/55 preserved, frozen code/model/runtime hashes retained; unrelated data changes untouched.

All per-image evidence, original/returned images, mask artifacts and detailed audits remain private. No weights or private data are committed. See [contract and usage](../docs/PHOTO_EXTERNAL_PITCH_V1.md).
