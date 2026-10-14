# Post-holdout adapter safety validation

This is PROTOCOL_AMENDED_OPERATIONAL_VALIDATION, not pristine independent testing. Historical independent and RGB-retry reports remain unchanged. No detector, pitch, feature or frozen-renderer parameters were tuned.

Root cause: 11 unchanged coarse components (one large region plus ten tiny fragments) have measured diameters [346.7687683105469, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2]. Median=2; scale=400/2=200; source 726x862; requested 145200x172400 RGB uint8 = 25,032,480,000 pixels = 75,097,440,000 bytes. No shape swap or integer overflow.

V2 retains those masks and the calculation, but rejects before resize with adapter_memory_limit_exceeded. It does not shrink the input to force success. The computed request remains the same; allocated working RGB bytes for that rejected request are zero. The entire source RGB is returned unchanged. All 11 semantic fragments are reported as rejected components, not asserted to be 11 actual fingerprints.

| Input | Routing | Detected components | Transformed | Rejected | Status | Reasons | Exterior | Determinism |
|---|---|---:|---:|---:|---|---|---|---|
| holdout_001.jpg | photo | 3 | 0 | 3 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved | True | True |
| holdout_002.jpg | photo | 4 | 0 | 4 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved, pitch_unobserved | True | True |
| holdout_003.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, pitch_unobserved | True | True |
| holdout_004.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, original_width_unavailable | True | True |
| holdout_005.jpg | photo | 0 | 0 | 0 | rejected | no_pad_candidates | True | True |
| holdout_006.jpg | photo | 1 | 0 | 1 | rejected | pitch_unobserved | True | True |
| holdout_007.jpg | photo | 11 | 0 | 11 | rejected | adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded, adapter_memory_limit_exceeded | True | True |
| holdout_008.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, pitch_unobserved | True | True |

```json
{
  "validation_type": "PROTOCOL_AMENDED_OPERATIONAL_VALIDATION / POST_HOLDOUT_ADAPTER_FIX",
  "ADAPTER_MEMORY_SAFETY_FIXED": true,
  "NEW_ADAPTER_VERSION": "photo_coarse_adapter_v2",
  "HOLDOUT007_RUNTIME_CRASH_RESOLVED": true,
  "PROTOCOL_AMENDED_OPERATIONAL_VALIDATION_COMPLETE": true,
  "PROTOCOL_AMENDED_IMAGE_COUNT": 8,
  "PROTOCOL_AMENDED_OPERATIONAL_ERROR_COUNT": 0,
  "PROTOCOL_AMENDED_DETECTED_PAD_COUNT": 25,
  "PROTOCOL_AMENDED_TRANSFORMED_PAD_COUNT": 0,
  "PROTOCOL_AMENDED_REJECTED_PAD_COUNT": 25,
  "EXTERIOR_PRESERVED": true,
  "DETERMINISTIC_OUTPUT_OK": true,
  "ORIGINAL_INDEPENDENT_EVALUATION_COMPLETE": false,
  "FINAL_INDEPENDENT_VALIDATION_COMPLETE": false,
  "PHOTO_DETECTOR_APPROVED": false,
  "PHOTO_PROTECTION_PRODUCTION_READY": false,
  "WINDOWS_FULL_EQUIVALENCE_VERIFIED": false,
  "FUNCTIONAL_IMPLEMENTATION_COMPLETE": false,
  "PROJECT_COMPLETE": false
}
```

Seven previously executed holdout cases retain identical routing/counts/status and returned pixels. Eight inputs are evaluated twice with actual COLFISPOOF inference. Previous seven PHOTO development reference images and scanner reference remain pixel-identical. Source/capture/GT/checkpoint/runtime preservation is verified. 153 tests: 150 passed, 3 optional-dependency skips. Syntax and frozen read-only reproduction checks pass.

No GT accuracy or protection efficacy is inferred. Zero transformed holdout components means no new matcher comparison is applicable. Memory bounds are implementation limits, not quality thresholds; see ../docs/PHOTO_ADAPTER_MEMORY_SAFETY.md.

Actual Windows runtime and GUI validation remain pending. A new private kit contains the eight new Linux references plus a successful PHOTO development and scanner reference. Run its PowerShell script on Windows with configured runtimes. Do not upload the kit or runtime/model files.
