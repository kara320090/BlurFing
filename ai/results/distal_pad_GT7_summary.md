# Unmodified crease-optional estimator: seven-annotation evaluation

**Development approval: false.** Estimator code and policy were unchanged from commit 059fd32. No renderer, protection or matcher execution was permitted.

## Annotation integrity and status

All seven source JSONs, source SHA-256, EXIF/native shape, mask SHA-256, PNG/L/0–255 values and component/polygon counts pass. Four images are 4000×3000; additional CAP-016 is 4000×3000 and CAP-042/CAP-054 are 4032×3024. All files lack an explicit `annotation_status`; all contain human-reviewed nonempty pad annotations, so they are evaluated as positives under the documented legacy convention. None is silently relabeled ambiguous or non-target. Annotation files remain unchanged.

Valid positives: 7; ambiguous: 0; non-target: 0. Thus ambiguous/negative fail-closed behavior was not empirically tested here. The evaluator separately supports ambiguous samples (even without a mask), verified empty non-target masks, and unresolved status; synthetic tests verify these branches. Ambiguous samples are excluded from IoU aggregates and review candidates/actual protection approval are reported separately. Empty unclassified masks are not converted to negatives.

## Metrics

Component matching is one-to-one with IoU >=0.5, in encoded source coordinates. Leakage is predicted-outside-GT/predicted, which includes non-pad skin as well as background. Empty predictions have undefined precision/leakage, not a fabricated zero leakage success.

| Sample | Candidates | Pads | IoU | Dice | Precision | Recall | Outside GT | Matched/GT | FP components | Missed |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DET-01 | 2 | 2 | 0.9318 | 0.9647 | 0.9679 | 0.9616 | 3.21% | 2/2 | 0 | 0 |
| DET-03 | 1 | 0 | 0.0000 | 0.0000 | N/A | 0.0000 | N/A | 0/1 | 0 | 1 |
| DET-04 | 4 | 3 | 0.9251 | 0.9611 | 0.9579 | 0.9643 | 4.21% | 3/3 | 0 | 0 |
| DET-05 | 1 | 1 | 0.9173 | 0.9569 | 0.9338 | 0.9811 | 6.62% | 1/1 | 0 | 0 |
| CAP-016 | 2 | 1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 100.00% | 0/1 | 1 | 1 |
| CAP-042 | 5 | 2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 100.00% | 0/1 | 2 | 1 |
| CAP-054 | 4 | 2 | 0.6645 | 0.7985 | 0.6751 | 0.9770 | 32.49% | 1/1 | 1 | 0 |

Positive macro IoU **0.4913**, coverage **7/10 (70%)**. Both fail the requested 0.85/90% minimums. The existing four-image experimental baseline is unchanged (macro 0.6936, coverage 6/7): DET-01/04/05 masks are byte-identical; DET-03 remains rejected. Its earlier diagnostic 0.8462 is not an accepted estimator prediction.

## Structural evidence and blockers

Private overlays show CAP-016 predicts a wrist region instead of the annotated thumb pad. CAP-042 predicts background keyboard regions while missing the annotated central fingertip. CAP-054 covers the target but also predicts background and extends below the annotated pad. CAP-016/CAP-042 have precision 0 and outside-GT ratio 100%; CAP-054 outside-GT ratio is 32.49%. Cue confidence 0.75 can therefore occur on anatomically wrong regions. This is not fixed by selecting a more favorable GT threshold.

All outputs remain review-only, with actual protection approval false. Positive numeric gates, structural/leakage safety and target-component coverage fail. No additional annotation is required now: existing evidence already demonstrates failure. The next blocker is RGB/SAM target-component association and rejection of non-pad anatomy/background before interpreting distal cue agreement. Frozen scope/pitch problems remain separate.

## CPU timing

Representative CAP-042, one warm-up excluded, ten measured runs. Saved-mask detector includes non-mutating SAM component-cleanup preflight; the unchanged estimator also performs its internal cleanup, charged to the pad stage. No model inference in this table.

| Stage | Mean s | Median s | Min s | Max s | Std s | p95 s |
|---|---:|---:|---:|---:|---:|---:|
| SAM_loading_validation_preflight_postprocess | 0.3304 | 0.3275 | 0.3031 | 0.4163 | 0.0313 | 0.3831 |
| pad_estimator | 1.2621 | 1.2520 | 1.2468 | 1.3173 | 0.0203 | 1.2970 |
| total_detector | 1.5925 | 1.5786 | 1.5545 | 1.7336 | 0.0494 | 1.6755 |

Actual SAM inference was also run on CPU with four torch threads, warm-up one plus ten runs. Producer timing includes preprocessing, inference, native-mask mapping and disk/hash I/O; model/environment startup is excluded. Warm SAM producer mean 3.5018s; separately measured consumer mean 1.5394s; matched-run stage sums mean 5.0412s, p95 5.1368s. These sums are not a continuous wall-clock protection pipeline benchmark. SAM mask hashes and consumer mask hashes repeat exactly.

## Regression, privacy and preservation

73 tests pass, including ambiguous/non-target semantics, integrity rejection, empty-mask metrics, source/mask artifact validation and exception-time renderer-binding restoration. Python syntax passes. Checkpoint 303/303, canonical 55 captures, frozen renderer/compositor and runtime checks are preserved. Unrelated data edits remain unstaged. GT, originals, private overlays, SAM weights and runtime binaries are not committed. These seven annotations are development-only, not independent final validation.
