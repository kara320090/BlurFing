# SAM-to-pad development evaluation

Development-only: four human-annotated samples, seven pad components. No independent validation or general protection claim. GT is read only after inference.

| Sample | Prior rule IoU | SAM-to-pad IoU | Dice | Precision | Recall | Outside GT / predicted | Coverage (IoU >= 0.5) |
|---|---:|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.4477 | 0.9318 | 0.9647 | 0.9679 | 0.9616 | 3.21% | 2/2 |
| DET-03 | 0.9668 | 0.6089 | 0.7569 | 0.6133 | 0.9883 | 38.67% | 1/1 |
| DET-04 | 0.5556 | 0.9251 | 0.9611 | 0.9579 | 0.9643 | 4.21% | 3/3 |
| DET-05 | 0.6273 | 0.9173 | 0.9569 | 0.9338 | 0.9811 | 6.62% | 1/1 |

Macro pad IoU: **0.8458**; component coverage: **7/7**. The previous rule detector macro IoU was 0.6493. This comparison changes both foreground inputs and pad extraction; it does not isolate a model improvement. DET-03 regresses from 0.9668 to 0.6089 and has substantial background contamination in the private overlay.

Approval: **false**. Fixed gate: macro IoU >= 0.70; coverage >= 6/7 with one-to-one component IoU >= 0.5; maximum per-sample outside-GT/predicted <= 5%; outside input finger mask = 0; repeat determinism; nonempty samples; observed crease and unambiguous tip for active proposals. DET-03 (38.67%) and DET-05 (6.62%) fail the outside-GT condition. Outside-GT includes non-pad skin and is not a pure background classification metric.

Foreground metrics in JSON compare whole finger support with pad GT, not finger-level ground truth. Only pad annotations exist. Pad masks never expand outside their SAM masks; this does not certify that the SAM masks themselves exclude background. An extra DET-04 hand-like proposal is rejected for unstable axis and contributes no pad pixels.

The geometry-only tip-sign fallback produced macro IoU 0.5763. Propagating the existing independent RGB cap proposal as a tip hint resolved axis sign ambiguity, yielding 0.8458 with exactly the same SAM masks. Neither tip hints nor inference read GT. Two CPU SAM generation runs produced identical mask hashes. Fixed-mask pad benchmark signatures were identical across warm-up and ten measured runs.

## Renderer compatibility (separate B2)

Frozen square scope and pitch 2–50 px remain unchanged. DET-03 fails scope/pitch checks. One active DET-04 pad has invalid pitch; an additional zero-mask proposal is rejected. Other regions pass only geometry/pitch screening; structure checks were not run. No clamp, destructive pad crop, renderer modification, transform, NBIS or SourceAFIS evaluation was performed. Downstream status: **NOT_RUN** because the detector gate failed.

## CPU detector-only benchmark

Saved-mask loading and postprocessing, then axis/pad estimation; neural SAM generation is excluded. Representative DET-05, one warm-up excluded, ten measured runs.

| Stage | Mean ms | Median ms | p95 ms |
|---|---:|---:|---:|
| SAM_mask_loading_postprocess | 125.64 | 126.48 | 132.67 |
| axis_pad_boundary | 122.39 | 122.48 | 125.11 |
| total_detector | 248.04 | 247.76 | 256.99 |

Full mean/median/min/max/std/p95 and per-component matching are in sam_pad_status.json. Private overlays and detailed native-coordinate artifacts are excluded from Git.
