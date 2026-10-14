# Coarse PHOTO experimental development integration

Detector remains unapproved; production readiness remains false. Frozen cores and gates were not changed. Rejected refinement is not used. No GT/parameter tuning.

An explicit common working-canvas width normalization targets the existing 400px width convention using only mask geometry. Full-pad square scopes retain all mask pixels. Pitch is measured again and never clamped. Only applied pad masks are inverse-mapped and composited. Native exterior is pixel-identical. This input adaptation is not established as equivalent to native-resolution rendering.

## Samples

| Sample | Detected | Canonical | Applied | Native changed pixels | Exterior |
|---|---:|---:|---:|---:|---|
| DET-01 | 2 | 2 | 0 | 0 | PASS |
| DET-03 | 1 | 1 | 1 | 3857780 | PASS |
| DET-04 | 3 | 2 | 1 | 250124 | PASS |
| DET-05 | 1 | 1 | 0 | 0 | PASS |
| CAP-016 | 1 | 0 | 0 | 0 | PASS |
| CAP-042 | 1 | 1 | 1 | 196810 | PASS |
| CAP-054 | 1 | 0 | 0 | 0 | PASS |

DET-01: original width unavailable. DET-04: one pitch unobserved, one transformed, one insufficient-feature rejection. DET-05: insufficient features. CAP-016/CAP-054: pitch unobserved. These remain unchanged; no failed component is counted as transformed.

## Matcher comparison

Inputs use the existing Canonical 512px grayscale letterbox, generated from the actual native returned RGB; same original mask/geometry for both images. Existing adapter DPI default is 500. This differs from historical structure-check seed normalization.

| Sample | NBIS features | NBIS self → returned | NBIS status | SourceAFIS features | SourceAFIS self → returned |
|---|---|---|---|---|---|
| DET-03 | 23 → 8 | 114 → 0 | insufficient_features | 2 → 0 | 16.5869 → 0.0000 |
| DET-04 | 8 → 5 | 0 → 0 | insufficient_features | 0 → 0 | 0.0000 → 0.0000 |
| CAP-042 | 0 → 3 | 0 → 0 | insufficient_features | 0 → 0 | 0.0000 → 0.0000 |

All transformed NBIS comparisons have insufficient features. SourceAFIS returned ROI has no minutiae. This is a limitation of these development matcher inputs, not protection success. Matcher score scales are different. The historical accepted structure-check frames contain different information; do not conflate these protocols.

## CPU complete pipeline benchmark

DET-03: excluded one warm-up; ten successful sequential full runs through a persistent isolated TensorFlow worker, coarse estimator, adapter, frozen transformation/structure gate and both matchers. All repeated detection-mask/native RGB/matcher-input hashes identical.

| Stage (seconds) | Mean | Median | Min | Max | Std | p95 |
|---|---:|---:|---:|---:|---:|---:|
| COLFISPOOF | 1.9308 | 1.9156 | 1.8255 | 2.1112 | 0.0805 | 2.0670 |
| worker_roundtrip | 2.0205 | 2.0059 | 1.9145 | 2.2000 | 0.0802 | 2.1556 |
| coarse_and_canonical | 0.8574 | 0.8576 | 0.8306 | 0.8869 | 0.0143 | 0.8801 |
| renderer_and_structure | 1.9393 | 1.9353 | 1.8956 | 1.9879 | 0.0345 | 1.9839 |
| matcher_preparation | 0.0789 | 0.0797 | 0.0752 | 0.0812 | 0.0022 | 0.0811 |
| NBIS | 0.0496 | 0.0489 | 0.0404 | 0.0617 | 0.0055 | 0.0586 |
| SourceAFIS | 0.9495 | 0.9497 | 0.8947 | 1.0024 | 0.0386 | 1.0006 |
| end_to_end | 6.5775 | 6.5757 | 6.4821 | 6.8002 | 0.0944 | 6.7294 |

Renderer, compositing and frozen structure checking are timed together. Routing is explicit PHOTO opt-in rather than a new classifier. End-to-end is measured wall-clock, not the sum of overlapping timing columns. Worker startup is in excluded warm-up. Failed sample timings are not mixed into successful benchmark results.

## Regression and preservation

117 public-source tests passed; three optional Torch tests skipped in the scientific environment, six refinement tests passed separately in the Torch environment. All Python syntax passed. Scanner fixture returned pixels are identical to the preserved reference. Checkpoint 303/303, captures 55/55, frozen code/coarse detector and runtime hashes retained; unrelated data changes preserved.

The unmodified coarse GT7 baseline remains macro IoU 0.7529 / coverage 10/10. No detector improvement or independent validation is claimed. Native-resolution matcher sampling and visual assessment of resampling boundaries remain future experimental work; no default pipeline promotion.

See [usage and contract](../docs/PHOTO_COARSE_EXPERIMENTAL.md). Private photos, masks, cache, detailed audits, weights and runtime files are excluded.

All seven samples additionally repeated with source-bound semantic caches: native mask/RGB hashes identical and exterior preserved. Real CLI smoke returned valid JSON without child-process progress contamination and pixel-identical output.
