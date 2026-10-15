# Final native RGB decision: V12 experiment

V11 recovered development source 006's pitch but returned its original image.
The working proposal had 13 original / 9 candidate SourceAFIS features inside
its permission component. The frozen functional check correctly rejected that
working representation. V7 then skipped native projection/inspection because
the working result was not applied.

A read-only reproduction captured exactly that proposal while returning the
original false check to frozen code. Its seed, observed pitch, normalization,
mask and renderer were fixed. Exact adapter native projection and the existing
V7 final-RGB observational reprojection produced 13 / 12 features, same-coordinate
Dice 0 and skeleton XOR/union 0.8820035102: the unchanged final predicate passed.
The source feature frame and template hashes were identical across both jobs.
Independent pixel/coordinate reconstruction confirmed both outcomes. The two
features excluded at the working stage were tens of pixels outside permission;
including them would be incorrect.

Interpolation changes the actual RGB and extractor response. This was a
decision-order limitation of the previous **working AND native** policy, not a
coordinate typo or a justification to reduce 10 to 9. V12 changes the decision
policy to the actual native candidate. Numeric criteria and renderer math stay
unchanged; frozen-gate behavior equivalence is explicitly false.

## Implementation

`photo_native_return_decision_v1.py` records the single working proposal inside
the existing scoped callback, runs the real working check and returns its true
result unchanged to frozen code. It never inserts a fake pass. The captured
proposal, rather than the old rejected/original return, is projected by the exact
adapter procedure: trim padding, INTER_CUBIC to original upright size, inverse
EXIF, then copy only the native permission component onto original RGB.

The actual native candidate is reprojected with the existing V7 `working_views`.
Original observational context outside working permission is restored only after
native exterior equality is checked. The width must equal the original working
measurement. The same `photo_whole_region_structure_v1.assess` and
`fingerprint_structure_check.assess_structure` then decide the final result:

- Both original and candidate require at least 10 features inside permission.
- Same-coordinate/type Dice must be at most 0.9, with at least two point changes.
- Skeleton XOR/union must be at least 0.05.
- Extraction failures, zero/insufficient features, contract failures and failed
  final evidence cannot produce a successful output.

There is one candidate, one observed seed/scale and one final native evaluation.
There is no seed, scale, renderer or threshold search after failure. Working
evidence remains visible even when it rejects and native evidence passes.
Previously accepted outputs must exactly match the old adapter's native RGB.
Source RGB and exterior pixels remain unchanged. No callback, unsupported working
evidence or inconsistent legacy success flags cannot authorize an uninspected
changed return. All aliases are scoped with the shared RLock and restored on
exceptions. A preliminary validation run was stopped and preserved when this
last fail-closed guard was added; completed results use a fresh output directory.

`photo_learned_pad_pipeline_v12.py` retains V10/V11 preparation and exact pitch
remeasurement closures. Only their scoped renderer is bound to the new decision
adapter. The strict V6 detector, weights, training, masks, ownership, memory
planning, observations and frozen source files are unchanged. Historical V11
artifacts and the standard GUI/unified defaults stay intact.

## Explicit single-photo execution

```powershell
python ai/scripts/protect_photo_whole_pad_context_native_v1.py --input <photo> --model <private-V6-model> --consumed-registry <private-registry.json> --output <fresh-private-output>
```

The new entry includes all V12/V11 observer/decision sources in its runtime hash
binding. It preserves GT-free COLFISPOOF/model inference, RGB/L and explicit RGBA
canonicalization, source-bound semantics, encoded EXIF coordinates, fresh output
and JSON stdout. This is opt-in, development-only and not production approved.

### Repeating a previously evaluated photo

The CLI remains strict by default: `consumed_source_or_decoded_pixels_forbidden`
means that the source bytes or decoded appearance match a previously consumed
GT7/holdout registry entry. This is an evaluation data safeguard, not a protection
algorithm failure. For a deliberate development retest, append
`--development-replay` to the command above. The local Windows Native Test
launcher uses that explicit development mode; its `-StrictEvaluation` switch
retains strict rejection.

Replay binds the complete identity triples of the original file and the actual
persisted canonical RGB PNG. A new scoped adapter calls the unchanged exclusion
validator and permits only its exact consumed-input reason for those declared
identities, the original registry hash and the owning process/thread. All other
errors propagate. Other threads remain strict, enabled scopes cannot nest, and
the original function is restored even on failure. RGB/L semantics caches remain
bound to their original source bytes. No registry row, checkpoint metadata,
training/input source, detector setting or renderer is edited.

The GT-free input manifest and protection reports explicitly record
`development_replay=true`, `data_role=development_replay` and
`independent_final_test=false`. Matches record their consumed registry roles.
Replay results cannot be counted as new independent performance evidence, even
when a particular replay input does not match the exclusion registry.

Actual Windows CMD runs verified both cases after this launcher fix. A consumed
GT7 photo reached full inference/protection and saved its returned image, with
all five components rejected (one insufficient features, four pitch unobserved)
and zero changed pixels. This is successful execution, not successful protection.
Source 006 returned a transformed component with 219,571 changed pixels and
exact RGB equality to its previously verified V12 output. Both runs are labeled
development replay; model, registry, input and EXIF bindings were preserved.

## Completed Windows development checks

All 539 AI unit tests passed without failures, errors or skips. An actual fresh
COLFISPOOF Windows launcher run with a Unicode/space JPEG path produced the same
V6 mask and exactly the independently reconstructed fixed native candidate for
006. EXIF 6 and source bytes were preserved. The actual 219,571 changed pixels
were all inside accepted permission. Of those pixels, 218,896 were inside the
reviewed target and 675 outside. Its accepted component overlaps 236,756 target
pixels; this does not cover every target pixel or establish ridge removal.

The same saved V6 predictions for all 13 training photos completed actual V12:

| Same-model training-fit cohort | V11 | V12 |
| --- | ---: | ---: |
| Photos with actual RGB changes | 9/13 | 10/13 |
| Accepted permission / full target | 56.2086% | 62.4100% |
| Changed RGB overlap / full target | 53.0009% | 58.7344% |
| Changed pixels outside target | 16,214 | 16,889 |

Only 006 gained an applied component. Every previously accepted V11 region
retained exact RGB; rejected regions and pixels outside accepted permission
remained original, with `changed ⊆ accepted ⊆ predicted`. Sources 001, 007 and
008 remain unmodified. The masks and detector coverage did not change. The
working 13/9 rejection is still recorded alongside the final 13/12 pass, with
one proposal and no seed/scale/renderer retries. Functional point loss or failed
extraction still cannot authorize a changed final image.

Completed actual-photo, unit and independent pixel checks are recorded in
`PHOTO_NATIVE_RETURN_DECISION_V1_STATUS.json`. The cohort consists of 13 training
photos, not a new independent acquisition group. Changed pixels, functional
features or successful transformation are not general privacy/security proof.
The detector can miss pad pixels and the unchanged compositor retains original
detail in transition areas. New-path Linux parity, independent detection,
complete ridge coverage and real protection evaluation remain separate work.
