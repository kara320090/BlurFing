# Unified fail-closed Linux development completion

PHOTO production/detector approval remains false. This is safe containment/rejection/control-flow readiness, not universal fingerprint protection. Frozen v4/natural_auto_04/boundaryblend_02, scanner numerical core, detector masks, runtimes and training data were not changed.

## PHOTO regression

| Sample | Status | Detected | Transformed | Rejected | Exterior / repeat |
|---|---|---:|---:|---:|---|
| DET-01 | rejected | 2 | 0 | 2 | PASS |
| DET-03 | success | 1 | 1 | 0 | PASS |
| DET-04 | partial_success | 3 | 1 | 2 | PASS |
| DET-05 | rejected | 1 | 0 | 1 | PASS |
| CAP-016 | rejected | 1 | 0 | 1 | PASS |
| CAP-042 | success | 1 | 1 | 0 | PASS |
| CAP-054 | rejected | 1 | 0 | 1 | PASS |

Total: 10 detected pads, 3 transformed, 7 rejected. Reasons: {'REJECT_WIDTH_UNAVAILABLE': 2, 'REJECT_PITCH_UNOBSERVED': 3, 'REJECT_INSUFFICIENT_FEATURES': 2}.

All returned pixels match the previously verified experimental coarse/frozen path. All seven source-bound cache runs repeat byte-identically. Rejected pad and exterior assertions pass. No GT mask is used for inference. Coarse IoU remains 0.7529 / coverage 10/10; no tuning or new accuracy claim.

## Scanner and common API

Scanner public fixture returned pixels match the preserved reference; existing 21-fixture development evidence remains historical and was not relabeled as new independent testing. Full CLI and protect_image() API perform content routing. UNKNOWN returns original; corrupt/missing input yields JSON error. PHOTO missing runtime is an explicit rejected runtime state, not proof of no fingerprints. success/partial_success/rejected are processing outcomes, not security outcomes.

## CPU benchmark

One warm-up excluded, ten full calls each for PHOTO and scanner. PHOTO includes actual isolated COLFISPOOF inference with per-request startup, not semantic-cache-only inference. Measurements include profiling overhead; nested phase columns must not be summed. Optional identity matcher score comparisons are excluded; SourceAFIS feature extraction required by existing structure guard is included. Prior dedicated NBIS/SourceAFIS observation timings remain in photo_coarse_experimental_summary.md.

### PHOTO

| Stage seconds | Mean | Median | Min | Max | Std | p95 |
|---|---:|---:|---:|---:|---:|---:|
| routing | 0.0132 | 0.0145 | 0.0108 | 0.0151 | 0.0018 | 0.0149 |
| PHOTO_renderer_composite | 0.3952 | 0.3904 | 0.3877 | 0.4222 | 0.0106 | 0.4156 |
| PHOTO_quality_gate_inclusive | 12.9143 | 12.9198 | 12.7199 | 13.2263 | 0.1383 | 13.1144 |
| pitch_observer | 0.7726 | 0.7616 | 0.7505 | 0.8829 | 0.0371 | 0.8314 |
| structure_validation | 1.4827 | 1.4832 | 1.4081 | 1.6104 | 0.0587 | 1.5732 |
| coarse_estimator | 0.2877 | 0.2872 | 0.2825 | 0.2914 | 0.0024 | 0.2912 |
| total | 14.3549 | 14.3499 | 14.1474 | 14.6624 | 0.1402 | 14.5595 |
| COLFISPOOF_subprocess_including_startup | 8.6308 | 8.6877 | 8.4638 | 8.7671 | 0.1048 | 8.7446 |

### SCANNER

| Stage seconds | Mean | Median | Min | Max | Std | p95 |
|---|---:|---:|---:|---:|---:|---:|
| scanner_transform | 0.1543 | 0.1542 | 0.1521 | 0.1571 | 0.0016 | 0.1568 |
| ridge_validation | 0.1827 | 0.1822 | 0.1788 | 0.1866 | 0.0019 | 0.1856 |
| routing | 0.0963 | 0.0961 | 0.0933 | 0.0997 | 0.0019 | 0.0991 |
| scanner_segmentation_and_ridge | 0.0922 | 0.0920 | 0.0907 | 0.0936 | 0.0008 | 0.0934 |
| scanner_structure_validation | 1.7381 | 1.7384 | 1.6845 | 1.7978 | 0.0343 | 1.7952 |
| total | 2.1147 | 2.1107 | 2.0668 | 2.1780 | 0.0329 | 2.1737 |
| COLFISPOOF_subprocess_including_startup | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Tests and preservation

141 pass, three optional Torch tests skipped; Python syntax passes including new GUI. Common CLI missing argument, nonexistent input and UNKNOWN probes return valid JSON. Actual-photo per-pad rejection/exterior/repeat checks and scanner pixel regression pass. Checkpoint 303/303, captures 55/55, frozen/runtime hashes and unrelated data changes preserved.

## Explicit blockers

STOP_A: no objectively eligible new independent PHOTO capture/provenance is available; old GT7/training/55 captures are not promoted. Evaluator, deny-hash index mechanism, optional GT metrics and manifest schema are ready. No-GT evaluation does not compute accuracy and catastrophic-FP visual review stays pending.

STOP_L: host is Linux. A new thin Tk GUI calls the shared CLI; original existing GUI source was not present in this working clone and no external user GUI files were overwritten. Actual Windows GUI/runtime/equivalence testing remains unperformed. The prepared parity probe reports only single-case evidence and never enables full equivalence by itself.

FUNCTIONAL_IMPLEMENTATION_COMPLETE=false because the stated global criteria require actual Windows regression/equivalence. FINAL_INDEPENDENT_VALIDATION_COMPLETE=false and PROJECT_COMPLETE=false. Linux readiness is not falsely promoted to global completion.

See [architecture, setup, GUI, evaluator and limits](../docs/FAIL_CLOSED_SYSTEM.md). No photos, masks, private manifests, runtimes or models are committed.
