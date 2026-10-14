# Proximal boundary observation: development result

**Blocker unresolved, detector approval false.** All four masks and GT metrics remain unchanged. Geometry fallback is diagnostic-only and cannot authorize protection. No transform, NBIS or SourceAFIS was run. Four annotations remain development data, not independent validation.

## Observed signals and decision

RGB-only longitudinal PCA axis, scanline width and its derivative, distance-transform internal width, axial grayscale gradient, transverse dark-valley response, ridge texture energy, gradient orientation coherence and local spectral frequency were measured. Support occupancy and RGB chroma margin are recorded as uncalibrated foreground proxies, not probabilities or true skin/background labels. Frequency is a diagnostic spectral peak, not renderer pitch acceptance.

Crease transects include small slopes -0.2,-0.1,0,0.1,0.2 to tolerate oblique valleys. A boundary requires transverse crease evidence together with an independent energy/coherence transition. Width and distance-transform geometry are correlated and cannot alone approve it. Confidence expresses cue agreement, not a trained posterior.

DET-03's search range is analysis rows 459–761. Width-derivative maxima occur at 724/645/538; distance-width changes at 620/572/687; grayscale-gradient maxima at 577/652; weak valley maxima at 758/490; energy changes at 743/502/667; coherence changes at 744/548/599; spectral-frequency changes at 542/755/482. None becomes an adequately supported transverse crease candidate, including tilted transects. End-of-mask energy/coherence changes near rows 743–744 do not establish a fingerprint-pad boundary. The current 3826px geometric fallback lies near this endpoint; it remains geometry, not observation.

Decision: `proximal_boundary_unobserved`, accepted-boundary confidence 0. No GT-derived coordinate, sample-specific condition, learned threshold optimization or forced crop was used. Diagnostic weak peaks were not relabeled as accepted evidence just because a coordinate could improve IoU.

## Before/after (identical)

| Sample | IoU | Dice | Precision | Recall | Outside GT / predicted | Coverage | Boundary source |
|---|---:|---:|---:|---:|---:|---:|---|
| DET-01 | 0.9318 | 0.9647 | 0.9679 | 0.9616 | 3.21% | 2/2 | legacy_observed_crease, legacy_observed_crease |
| DET-03 | 0.8462 | 0.9167 | 0.8584 | 0.9835 | 14.16% | 1/1 | geometry_fallback_diagnostic_only |
| DET-04 | 0.9251 | 0.9611 | 0.9579 | 0.9643 | 4.21% | 3/3 | legacy_observed_crease, legacy_observed_crease, legacy_observed_crease |
| DET-05 | 0.9173 | 0.9569 | 0.9338 | 0.9811 | 6.62% | 1/1 | legacy_observed_crease |

Macro IoU 0.9051 and coverage 7/7 satisfy the numeric conditions, but DET-03 image-observed proximal boundary does not. Its 14.16% outside-GT area includes proximal non-pad skin, so leakage is not newly certified as safe. Old masks are retained only as review diagnostics.

## Runtime and regression

DET-03 CPU saved-mask detector, one warm-up excluded and ten measured runs; no SAM model inference. All repeated signatures match.

| Stage | Mean ms | Median ms | p95 ms |
|---|---:|---:|---:|
| SAM_mask_loading_postprocess | 107.98 | 108.09 | 116.19 |
| axis_pad_boundary | 511.04 | 506.80 | 533.47 |
| total_detector | 619.03 | 612.09 | 646.89 |

56 regression tests pass, including uniform-image rejection, crease-only rejection, synthetic multi-cue acceptance, deterministic finite signals, source/mask artifact validation and exception-time renderer-binding restoration. All four output masks remain byte-identical to the foreground-refinement baseline; subset leakage remains zero. Python syntax passes. Checkpoint 303/303 and canonical 55 originals are retained, and unrelated data edits remain unstaged.

## Private evidence and remaining work

Private diagnostics contain per-row CSV, signal plots with the geometric fallback marked, full axis/width/quality metadata and overlays. No originals, masks, previews, weights or private paths are committed. The analysis measures the absence of reliable evidence under this detector; it does not prove that a crease can never be detected at native resolution. Higher-resolution curved-line evidence or a separately validated boundary observer is the next development route. Renderer scope/long-pad/pitch issues remain separate and were not modified or executed.
