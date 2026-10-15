# Experimental desktop PHOTO validation — 2026-10-16

The unified library, JSON CLI, Windows launcher and development GUI now accept
an explicit `native_v12` or `distal_v13` PHOTO engine. The legacy default and
scanner route are preserved. See [configuration](PHOTO_EXPLICIT_ENGINE_INTEGRATION.md).

Native V12 uses the existing V6 learned permissions and the actual returned
RGB decision gate. Distal V13 uses existing COLFISPOOF distal geometry with the
same gate. Neither engine has production approval or independent privacy
validation. V13 is a boundary-review experiment, not an automatic fallback.

## Executed checks

- AI scripts: **563 tests passed**, no failures, errors or skips.
- Windows GUI: **16 tests passed**, no failures, errors or skips.
- Actual hidden Tk process and save: one fresh COLFISPOOF/V6/V12 run through
  the unified JSON CLI. The returned full-resolution RGB matched the saved
  V12 baseline exactly; the saved PNG matched the generated PNG. Original
  source and EXIF were preserved. This was an actual configured runtime run,
  not an injected processing result.
- Synthetic integration checks include explicit engine selection, strict
  consumed-source defaults, RGBA/EXIF dispatch, stale GUI jobs, source changes
  between routing and execution, malformed returned RGB, fresh output and
  actual PowerShell argument transport.

These checks validate contracts and this Windows configuration. They do not
establish Linux equivalence, Android integration or detector accuracy.

## Additional development photos

The user identified seven additional photos as belonging to an existing
capture. They are development data, not an independent final test. All seven
originals, private models and consumed registries were preserved.

| Explicit engine | Photos with actual RGB changes | Applied candidate components | Changed pixels |
| --- | ---: | ---: | ---: |
| Native V12 | 5 / 7 | 8 | 999,782 |
| Distal V13 | 5 / 7 | 8 | 1,074,224 |

Candidate components are not anatomical fingers. Rejected regions and pixels
outside accepted permissions were unchanged. The V12 run performed fresh
segmentation and model inference; V13 reused saved prepared semantics and
coarse masks, so their durations are not comparable benchmarks.

Actual NBIS and SourceAFIS evaluation used 16 unfiltered coarse ROIs from all
seven photos, with the same original-coordinate ROI and canonicalization for
original and both returned outputs. Some unprocessed ROIs retained the same
positive self/returned scores. Other scores fell, but extraction failure,
insufficient original features or zero scores were not counted as proof of
protection. Coarse ROIs can include several fingers and palm; these results
are not per-finger success rates.

## Remaining algorithm limitations

Visual review found missed thumb permissions in full-hand photos, holes and
proximal over-expansion. Two photos remained unchanged because existing
permission-local pitch evidence could not be established. Width, EXIF and
coordinate reconstruction were verified for these rejections; weakening the
gate would not fix a missing or inaccurate permission mask.

A global replacement by the coarse detector was rejected: on thirteen
existing human-reviewed training images its static micro IoU was 0.5628,
versus 0.8804 for V6, and all thirteen image IoUs regressed. These are training
fit diagnostics, not independent accuracy estimates. A wider pitch research
proposal also produced harmonic ambiguity and was not adopted.

No frozen renderer/compositor mathematics, numeric quality thresholds,
private inputs, human annotations or Linux references were changed.
Backend/Android partial-rejection transport, new human boundary review,
independent capture validation and actual Linux runtime verification remain
separate work. A changed image alone does not establish complete fingerprint
protection.
