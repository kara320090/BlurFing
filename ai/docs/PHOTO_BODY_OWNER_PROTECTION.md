# Experimental body-owner PHOTO protection

The original PHOTO connection rejected all ten saved group-heldout developmental predictions. Two implementation contracts caused many failures: a predicted fragment's inscribed diameter was treated as finger width, and disconnected prediction fragments were treated as separate fingers. Native body edges could also disappear during 512-pixel geometry down/up sampling. These failures are separate from the model's recall loss and unavailable ridge evidence.

The later [whole-region gate experiment](PHOTO_WHOLE_REGION_GATE_V1.md) addresses the feature sampling domain in a separate explicit flag. V4 remains the default learned experimental connection; V7 is not frozen-gate behavior equivalence or production approval.

`photo_learned_pad_pipeline_v4.py` is the current opt-in experimental connection. The default unified API/GUI and frozen `natural_auto_04` / `boundaryblend_02` remain unchanged. V4 is **not production approved**.

- Measure a native body cross-section using an observed axis; normalize that body width to the existing 400-pixel reference. Never use fragment thickness as body width, clamp scale, or remove fragments. Missing source-frame boundaries reject before resampling.
- Recover original semantic body coverage only when a native connected body and estimator owner have an exact one-to-one overlap relation. Split/merged bodies, multiple watershed owners and invalid axes are retained without reassignment. This restores observed edge pixels, not missing anatomical evidence.
- Partition every predicted pixel by its unique observed owner. All fragments belonging to that owner remain together. Unowned and multiply owned pixels get explicit rejected groups. Connected fragments crossing owners are partitioned by exact ownership, without nearest/largest-overlap decisions.
- Observation squares have predicted-pixel centers and lie completely inside that same observed body. At most eight deterministic squares are tested with the unchanged frozen pitch observer. Observation support can exceed the output permission mask; permission pixels are never expanded.
- Retain complete real-source body crops, actual rounded resize ratios, exact EXIF axes, virtual/source hashes and coordinate provenance. Keep resource guards and existing width/pitch/feature/structure criteria.
- Reproject the actual native returned RGB into the same working geometry and repeat the unchanged structure check. Failure restores original pixels. A renderer success flag with identical native RGB is rejected. PNG is decoded and checked after saving.

Width normalization and observation geometry are not equivalent to the historical full-photo resize. A separate V5 shared-anchor experiment gives each pre-render observation site its own normalization. It selects sites only from source RGB/geometry, never generated features or matcher scores. Its initial developmental runs transformed 0/10 and it is **not adopted** as the current connection.

## Single-photo execution

Use the isolated CPU Torch environment and configured external COLFISPOOF / SourceAFIS runtimes. Model, exclusion registry, sources and outputs are private. No human target mask is required for inference.

```text
python ai/scripts/protect_photo_learned_v1.py --input PHOTO.jpg --model PRIVATE_COMPLETED_TRAINING --consumed-registry PRIVATE_REGISTRY.json --output FRESH_PRIVATE_OUTPUT
```

The entry point validates the completed V3 model, registry and original identity before running the configured segmentation worker, preparing GT-free tiles and executing V4 protection. It records model/protection code hashes and checks source/registry/code preservation. Optional `--photo-semantics` accepts an existing hash-bound cache for original RGB/L inputs. Consumed GT7/old holdout appearances are rejected and cannot become new evaluation data.

RGB and L inputs preserve decoded RGB. RGBA inputs explicitly composite over opaque white using integer nearest rounding; original bytes and encoded axes remain intact. Mask/exterior equality then refers to canonical RGB. Invalid EXIF and unsupported bit depth/modes reject. Worker/native logs go to stderr; stdout is one JSON result.

`returned.png` may contain rejected original regions. Counts refer to semantic owner groups and rejected portions, not anatomical finger counts. A `success` result means all predicted groups passed functional checks; it does not prove complete pad detection or privacy. Read `regions`, `status`, `complete_photo_protection_verified=false`, and production-approval flags.

## Measured limits

Saved developmental OOF V4 predictions transformed 1/10 sources, with one applied group and 33 rejected groups from 145 original fragments. Rejections were 19 unavailable body-supported pitches, four insufficient features, eight unavailable owners and two unavailable widths. Actual returned RGB passed the structure check (47 original / 30 returned extracted points, four same-coordinate/type matches). Source-macro GT coverage by applied masks was only 0.013561. This is inadequate complete-photo coverage, not a privacy or independent-validation result.

The single-photo entry point also executed configured COLFISPOOF, the final model and real SourceAFIS on five additional unlabelled local photos selected by sorted path after excluding GT10 and consumed identities. One source transformed its complete predicted group; two rejected for insufficient features and two for unavailable pitch. The five calls returned valid JSON without pipeline errors, and original/exterior/rejected pixels were preserved. No human GT exists for these five; their unseen provenance and detector accuracy are unverified. This is functional development evidence, not a fresh independent test or whole-photo privacy result.

Read-only native/working ACF/FFT diagnostics found low orientation coherence, insufficient periodic patches and conflicting local spacings in many rejected bodies. Three of four feature-rejected developmental regions had fewer than ten original extracted points. Lowering gates cannot recover missing observed ridge detail. Existing 512-pixel seed measurement also has a restricted observable lag range and can report a harmonic on synthetic 3-pixel spacing; its frozen mathematics were not edited.

Model precision/recall, fragment false positives and anatomy uncertainty remain performance limitations. Additional human pad annotations from new acquisition groups and a fresh final validation set are still required before model adoption. Prior GT7/holdout were not rerun or tuned. Windows functional evidence does not establish execution parity of this new experimental path on Linux.

Public synthetic regressions cover native cross-sections, EXIF points/axes, fragments, one-to-one ownership, preserved permissions, returned-RGB rollback and original-preserving RGB/RGBA/L decode. See the anonymized [status](../results/photo_body_owner_protection_status.json) for the final measured runs.
