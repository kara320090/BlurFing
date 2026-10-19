# 2026-10-20 visibility local failure audit and peak-train probe

- Started at d229c06 on main with a clean tree. Fetched origin: ahead 30 / behind 3;
  remote changes concern Android/README, not these AI files. No destructive Git
  operation, merge, push or private upload performed.
- Inspected all 26 human-visible regions missed by the prior plane-only diagnostic
  using unenhanced native crops and context. Added separate measurements for raw
  contrast, orientation dispersion, spectral concentration and clipping. Physical
  blur/glare causes are observations, not automatically assigned ground truth.
- Every missed region has inspection windows within its human evidence box. In
  12 regions, all such windows fall below the old contrast threshold. Boundary
  failure alone cannot explain this GT-assisted observation experiment.
- Added separate peak-train V4 diagnostic. Fixed its code/config after synthetic
  controls, then evaluated development first and consumed GT7 last. V4 observes
  34/44 development-visible and 43/53 total-visible regions, versus plane-only
  19/44 and 27/53; no old plane observations lost. Human-negative disagreement
  increases from 0/6 to 1/6. Uncertain observations remain 0/8.
- Reviewed the negative disagreement and representative gains/failures in raw
  crops. Weak repeated skin texture can pass, so do not promote V4 to an automatic
  visibility/protection decision. Human labels remain unchanged. New captures
  are unavailable; independent training/calibration/evaluation remains deferred.
- Verified 60 source/mask files and decoded RGB when creating the private cache;
  comparison rechecked all 67 cache identities and preserved annotation state.
  Private reports and images live outside the repository; prior versions retained.
- Tests: 6 new local/V4 tests and 66 existing regression tests passed (72 distinct).
  One initial chirp test used out-of-band frequencies: corrected the positive
  fixture and retained the original as a rejection case, without changing gates.
- No frozen V4, V19, scanner, existing launchers or production thresholds changed.
  No renderer pitch binding and no invisibility inference from observation failure.
- Details: [V4 audit and comparison](../../ai/docs/PHOTO_VISIBILITY_PEAK_TRAIN_V4_20261020.md).
