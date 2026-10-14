# Whole-permission-region PHOTO structure experiment

The seed square measures pitch/photometry but can omit most of the transformed fingerprint pad. A controlled diagnostic kept baseline output unchanged and compared the generated candidate in both domains: two rejected seed crops had before/after counts 14/4 and 7/17, while their complete permission masks had 66/56 and 77/91. Points and skeleton pixels outside permission were excluded. This establishes a sampling-domain limitation, not privacy/security proof.

`photo_learned_pad_pipeline_v7.py` is a separate, opt-in experiment. It retains V4 detection, native body geometry, masks, resource/width/pitch rules and original frozen renderer mathematics. The existing functional predicate still requires both >=10 extracted points, same-coordinate/type Dice <=0.9, >=2 point changes and skeleton XOR/union >=0.05. **Its feature ROI and coordinate domain change to the whole permission square normalized to 512 pixels; frozen-gate behavior equivalence is false.** The numeric 6-pixel matching distance now refers to this different 512-pixel domain. Default unified/GUI and default learned V4 entry remain intact.

The working candidate and actual native returned RGB must both pass the whole-region gate. Only template points inside the resized permission mask and skeleton pixels inside its 512-pixel mask count. Native mask exterior must be identical. Native RGB reprojected for observation can spill across a nearest-neighbor working mask edge; original observational context is restored outside that working mask after native exterior equality is checked. No returned pixels are changed by that context restoration. A failed gate restores original RGB and clears every applied/success/count flag.

```text
python ai/scripts/protect_photo_learned_v1.py --input PHOTO.jpg --model PRIVATE_COMPLETED_TRAINING --consumed-registry PRIVATE_REGISTRY.json --output FRESH_PRIVATE_OUTPUT --experimental-whole-region-gate
```

## Development results

- All 38 available unlabelled development photos, excluding GT10 and consumed GT7/old-holdout identities, completed V4 single-photo worker/model execution without pipeline errors. V4 transformed 2/38.
- The SAME saved final-model masks and semantic inputs ran through V7: 5/38 transformed their complete predicted groups, including both previous successes and three previously rejected sources. Actual returned RGB, rejected pixels and every exterior were checked. Human pad GT and previously unseen provenance are unavailable; detector accuracy, complete pad coverage and independent final validation are unverified.
- On saved group-heldout GT10 masks, V4 transformed 1/10 and V7 2/10. Source-macro GT coverage by actually applied masks increased from 0.013561 to 0.084594. This remains far below useful complete-photo coverage; the model is not adopted.
- V6 original-feature preflight/spatial coverage did not improve first-14 developmental source transform count (2/14 before and after); it is not the current recommended experiment. V5 shared-anchor normalization also remains unadopted.
- Read-only existing strict ACF/FFT observation on remaining pitch failures in the first 14 photos found no case with six agreeing patches centered inside permission and valid native spacing. One body-only observation was accepted but had only one accepted permission-centered patch. Body context cannot silently substitute unrelated evidence for predicted pad evidence.

One initial V7 comparison was retained as a failed run because reprojection context triggered the exterior contract. The repaired run used a fresh output folder and completed separately. Frozen files, training/network code, checkpoint, consumed references and original inputs are unchanged. Private photos, masks, templates, failed runs and weights stay outside Git.

Remaining limits are unavailable ridge evidence, missed/fragmented pad predictions, uncertain body anatomy, and unavailable fresh human annotations / final validation. New-path Linux execution is unverified. Functional feature changes/extraction failures are never a general privacy proof.
