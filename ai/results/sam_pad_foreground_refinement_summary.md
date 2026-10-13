# SAM pad foreground separation development follow-up

Four existing human pad annotations; development-only. No model/renderer/runtime changes, no GT in inference. Only RGB inference precedes evaluation.

## Evidence and cause

Private DET-03 overlays show prediction-only pixels on the surrounding background (top, bottom and tip-side image border), plus the proximal finger body beyond the annotated pad. There is no clear adjacent finger or palm in this image. Before refinement, the SAM mask covers nearly the whole frame. The estimated width is 2894px and axis length 4289px; an apparent distal crease at 4233px comes from contaminated foreground. Simply shortening a distal ratio would retain side background and miss genuine ridge area.

The generic correction activates only when a SAM component occupies at least 75% of the frame and approaches at least three image edges within a 1%-of-short-side band. It applies deterministic Otsu separation of RGB red-minus-green chroma at quarter resolution, closes small holes, restores native coordinates, intersects with SAM, then retains the dominant connected component. Uncertain or overly small partitions remain unchanged for review. This is an image/geometry rule, not a filename/person special case. It is not a universal skin-color classifier.

DET-03 Otsu threshold is 24 (computed from RGB, not selected by GT). 3,095,371 input foreground pixels are removed. Width becomes 2126px, axis length 3893px and fallback lower extent 3826px. The former apparent crease is no longer detected: quality correctly reports `crease_not_observed_geometry_fallback` rather than falsely claiming an observed boundary.

## Before and after

| Sample | Before IoU | After IoU | Dice | Precision | Recall | Outside GT / predicted | Coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| DET-01 | 0.9318 | 0.9318 | 0.9647 | 0.9679 | 0.9616 | 3.21% | 2/2 |
| DET-03 | 0.6089 | 0.8462 | 0.9167 | 0.8584 | 0.9835 | 14.16% | 1/1 |
| DET-04 | 0.9251 | 0.9251 | 0.9611 | 0.9579 | 0.9643 | 4.21% | 3/3 |
| DET-05 | 0.9173 | 0.9173 | 0.9569 | 0.9338 | 0.9811 | 6.62% | 1/1 |

Macro IoU rises 0.8458 → **0.9051**; coverage stays **7/7**. DET-03 outside-GT fraction falls 38.67% → **14.16%**, a **63.39% relative reduction**. Recall falls by only **0.48 percentage points**. DET-01/04/05 metrics and masks are unchanged. All pad masks remain subsets of SAM support.

These meet the requested comparative quantitative goals (macro >= 0.80, seven matched components, substantial DET-03 leakage reduction, no other-sample regression). **Foreground refinement is retained as a development improvement, but full detector approval remains false**: the overlay still shows proximal non-pad skin, and no observed or otherwise verified lower boundary replaces the fallback. The prior absolute <=5% leakage safety gate also remains unmet; we do not redefine that as having passed. Outside-GT fraction includes non-pad skin and is not a pure background rate. A comparative improvement must not silently authorize a boundary still known to be incorrect.

One additional crease-free texture-transition experiment (local before/after ridge-energy drop) found no supported transition and changed no mask; it was not retained. An initial exact-image-edge trigger did not fire because the contaminated mask was inset a few pixels; the final documented border band handles this rasterization issue. No GT-based threshold optimization was performed.

## Benchmark and regression

Representative DET-03, CPU saved SAM masks → pad only, warm-up one, ten measured runs. SAM neural inference is excluded.

| Stage | Mean ms | Median ms | p95 ms |
|---|---:|---:|---:|
| SAM_mask_loading_postprocess | 108.79 | 106.89 | 117.92 |
| axis_pad_boundary | 316.74 | 318.17 | 325.86 |
| total_detector | 425.54 | 426.45 | 437.52 |

All repeat signatures match. 52 regression tests pass, including contaminated-frame separation, localized masks unchanged, uniform-frame uncertainty, native shape/subset/hash and existing artifact checks. Python syntax passes. Private overlays and detailed metadata are retained separately and excluded from Git.

## Downstream and next blocker

No consumer/protection/matcher execution. The next detector task is a supported proximal boundary, not shortening masks to fit GT. Frozen square scope and 2–50px pitch contracts remain separate blockers, not detector metrics. Experimental rectangular/tiled adapters require explicit seam/continuity validation before any renderer adoption; no frozen math or core files were modified here.
