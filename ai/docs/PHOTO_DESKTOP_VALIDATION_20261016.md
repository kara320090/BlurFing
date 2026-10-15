# Experimental desktop PHOTO validation — 2026-10-16

The unified library, JSON CLI, Windows launcher and development GUI now accept
an explicit `native_v12`, `distal_v13` or `pose_v14` PHOTO engine. The legacy
default and scanner route are preserved. See [configuration](PHOTO_EXPLICIT_ENGINE_INTEGRATION.md).

Native V12 uses the existing V6 learned permissions and the actual returned
RGB decision gate. Distal V13 uses existing COLFISPOOF distal geometry with the
same gate. Pose V14 uses observed hand geometry with that gate. All three
remain experimental, without production approval or independent privacy
validation. V13/V14 require boundary review and are not automatic fallbacks.

## Final integration checks — 2026-10-16

AI scripts **665**, Windows GUI **22**, Android unit **170** and emulator UI
**11** tests passed. The older counts below describe earlier stages.
Actual configured inference also passed these local integration checks:

| Path | Applied / rejected candidate components | Changed RGB pixels |
| --- | ---: | ---: |
| PC canonical sRGB → HTTP → native V12 | 4 / 92 | 271,567 |
| Android Repository → loopback HTTP → pose V14 → MediaStore readback | 4 / 3 | 438,554 |

Both observations use the same development photo, not seven independent
photos or anatomical finger counts. Rejected permissions and pixels outside
accepted permissions were unchanged. Android saved PNG bytes matched the
response exactly; canonical upload RGB and original source file bytes were
preserved, and server temporary
files were cleaned. Actual HTTP inference and save/readback do not establish
complete detection or protection; rejected fingerprints remain exposed.

Desktop PHOTO serialization preserves valid original RGB ICC while keeping
returned RGB samples unchanged; GUI sRGB conversion is display-only. HTTP
uses client-normalized sRGB/EXIF1 canonical PNG without color/ancillary chunks.
The source file is never overwritten. Private models, frozen protection math
and thresholds were preserved. Independent human-GT performance, new-engine
Linux equivalence and general privacy protection remain unverified.

## Earlier desktop checks

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

These earlier checks validated contracts and this Windows configuration.
Android integration was verified later as described above; neither stage
establishes Linux equivalence or detector accuracy.

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
Backend/Android partial-rejection transport now has the local integration
checks above. New human boundary review, independent capture validation,
external deployment and actual Linux runtime verification remain separate
work. A changed image alone does not establish complete fingerprint
protection.

The full PHOTO pipeline showed rotation sensitivity in development diagnostics,
not an accuracy/IoU measurement; the first divergent stage, including raw body
segmentation, remains unresolved and is not attributed to V6 alone.
Static ROI/grid-coordinate review found no confirmed error; whole-image joint
augmentation and tile-rotation consistency evaluation are candidates for the
next version, not adopted fixes.
