# 2026-10-20 visibility support correction and spatial comparison

- Started clean at c33743e on main. Fetched origin: ahead 31 / behind 3. Remote
  changes concern Android/README; fast-forward is impossible with diverged history.
  Preserved all commits and unrelated work. No merge, reset, force push or upload.
- Audited the one V4 negative disagreement and all ten remaining visible misses.
  Each miss contains accepted patches but only 1-3 connected windows. Examined
  native raw profiles to distinguish too few peaks, proposal mismatch, spacing
  variation and spectral direction rejection. Human labels were not changed.
- Found and reproduced a real numerical bug: AREA-resizing all-one float masks
  can yield values slightly below one, so comparison to 1-1e-12 deletes valid
  interior support. Added outside-indicator footprint logic and a separate V5
  probe with unchanged V4 evidence math. Historical V2/V3/V4 code/results remain.
- Added separate V6 four-strip spatial confirmation, using the same profile
  frequency/peak/spacing/correlation constants instead of the global axial gate.
  This is a diagnostic experiment, not a production threshold change.
- Development evaluation: V4/V5 observe 34/44 human-visible regions and disagree
  with 1/6 human-negative regions. V6 observes 28/44 and disagrees with 0/6: no
  positive gains, six losses. Reject promotion of V6; do not hide tradeoffs with
  a posthoc union or a sample-specific method choice. All seven uncertain regions
  in development remain unobserved.
- Validation: 7 new tests plus 72 existing regressions passed (79 distinct).
  Covers integer footprint oracle, positive interior preservation, outside leakage,
  resized positive detection, native V4/V5 equality, rotated weak curved patterns,
  noise/sparse creases and diagnostic-only output semantics.
- Private comparisons verify cached source/mask binding, original V4 result
  identities and unchanged human review state. V5 native measurements are reused
  only under exact identity checks; resized V5 levels and all V6 levels execute.
- Keep V5 as the corrected diagnostic baseline. Existing launcher, frozen V4,
  scanner and V19 paths do not import the new diagnostic modules and are unchanged.
  The false-positive and ten missed regions are not claimed resolved. New data is
  unavailable; independent capture validation and production connection remain
  deferred, without asking to redo existing labels.
- Details: [support fix and spatial experiment](../../ai/docs/PHOTO_VISIBILITY_SUPPORT_SPATIAL_20261020.md).
- Full 30-photo/67-region replay completed: V4/V5 43/53 visible observations,
  V6 37/53; negatives 1/6 versus 0/6, uncertain 0/8 throughout. V5 restored
  eligible windows in 31 of 35 resized stages; 67 identical native stages reused.
  V6 ran all 102 stages. Combined diagnostic time was approximately 1,000 seconds.
- Final artifact verification passed: original result hashes, all cached inputs,
  native equivalence, output contracts and local report references. Normalized
  Windows separators when looking up old manifest keys; no input/result changed.
