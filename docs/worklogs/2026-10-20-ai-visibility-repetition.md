# 2026-10-20 visibility repetition experiments

- Started clean at 237c707 on main; fetched origin. Local/remote histories diverge
  29/3 before this commit; the three remote commits concern Android. No reset,
  merge, force push or upload was performed.
- Added separate V2 raw-profile recurrence diagnostic and V3 fractional ACF
  variant. Synthetic controls exposed integer lag rejecting clean fractional
  periods; parabolic peak interpolation fixes that failure without altering
  existing pipeline thresholds or generating missing pitch.
- Ran two fixed, hash-bound comparisons on all 30 photos / 67 human-reviewed
  regions. Visible observations: baseline 24/53, prior plane-only 27/53,
  integer V2 18/53, fractional V3 25/53. V3 gains 9 but loses 8 versus baseline;
  development-only count remains 17/44. Do not promote either new experiment.
- Sources/masks/RGB verified; existing annotations unchanged. Private images,
  detailed diagnostics, scripts and HTML reports remain outside the repository.
  Older comparison outputs were preserved. Representative raw crops reviewed.
- Added metadata readiness audit. Human negatives occupy one capture group, so
  training/calibration/test class separation requires more groups. Exclude GT7,
  do not treat uncertain as negative, and do not split same-photo patches to
  manufacture independent samples. Prepared private new-capture instructions
  and metadata template; actual new photos and final labels require the user.
- Validation: 57 existing+V2 tests, 4 V3 tests, 5 data-readiness tests, all passed
  (66 distinct tests). No frozen V4, V19, scanner, runtime launcher or production
  acceptance rule edits. New diagnostic modules are not imported by those paths.
- Remaining: receive genuinely new capture groups with both visibility classes,
  preserve a separate evaluation group before fitting, perform human review and
  group-aware learning/calibration. Current numbers are development observations,
  not independent classification accuracy or protection proof.
- User confirmed additional photos are unavailable for now. New data collection
  and independent validation are deferred; no request to redo existing labels.
  Keep the current operational behavior and all experimental versions intact.
