# Experimental distal pad estimator (crease optional)

Shared SAM extraction and frozen renderer are unchanged. New wrapper evaluates tip/major axis, width-distance profiles, ridge energy/coherence and optional crease. No GT inputs exist in the estimator. Fixed engineering policy uses cue-group agreement >=0.75; it is not calibrated safety confidence. Geometry alone cannot authorize a proposal. Crease-free proposals require stable tip-axis, appearance transition and corroborating width/distance changes. Existing observed-crease masks are retained only as review candidates.

## Existing GT4 regression

DET-01/04/05 masks remain byte-identical. DET-03 has insufficient cue agreement (diagnostic confidence 0.5) and is rejected, so its actual prediction is empty: IoU/recall 0 and one component missed. Diagnostic geometry masks are saved separately and never counted as accepted prediction. Overall experimental macro IoU is 0.6936, coverage 6/7, rather than falsely reporting the diagnostic baseline 0.9051 and 7/7. Full detector approval remains false.

## Existing capture scan (not an independent holdout)

55 canonical images were inspected through RGB-only proposal generation. SAM inference ran on 49; six had no RGB proposal. 147 regional outputs: 78 existing observed-crease review candidates, three new crease-free multi-cue review candidates, 41 low-confidence rejects, 25 unstable/mixed-foreground rejects. Confidence distribution: 0.75:81; 0.5:13; 0.25:25; 0:28. These are candidate counts, not correct detection counts.

Automatic obvious geometry failures are rejected; palmar-vs-nail/occluded semantic safety is not established. An occluded/object-holding image produces a crease-free 0.75 candidate. Therefore the confidence threshold cannot be considered validated. The three new crease-free cases are CAP-016, CAP-042 and CAP-054. They have no current pad GT and require human annotations of all visible pads (including an empty mask if the human judges the image non-target). Three annotations are the minimum for the next branch-specific development evaluation, not enough to establish general safety.

## Repeatability and timing

GT4 masks reproduce; synthetic optional-crease tests pass. Preloaded RGB/SAM estimator benchmark on DET-03: one warm-up excluded, ten runs, mean 556.97ms, median 555.32ms, p95 571.40ms. All mask hashes are equal; this excludes model inference/loading. 63 regression tests pass. No protection transform or matcher executed.

## Private artifacts

Source-path roster, SAM masks, full candidate metadata, contact sheet, previews and annotation shortlist are private and excluded from Git. The shortlist's original source hashes were checked against the current GT4 sources to ensure these are additional annotation images, not duplicate GT entries. B/D classifications were not promoted to final holdout. Renderer scope and pitch contracts are untouched.
