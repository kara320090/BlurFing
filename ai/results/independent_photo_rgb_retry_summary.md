# Protocol-amended independent PHOTO evaluation

protocol-amended evaluation after provider RGB/JPEG format normalization; not pristine untouched one-shot validation. Original inputs and the earlier attempt are preserved. The previously completed inputs 001, 002, 003 and 006 were not rerun or altered. Only the provider-derived copies 004, 005, 007 and 008 were evaluated twice.

Original files 004/005/007/008 decode as PNG/RGBA despite JPG extensions. Derived copies decode as JPEG/RGB with unchanged dimensions. Their decoded RGB pixels differ from a direct RGB conversion of the originals; this is not a lossless representation-only equivalence claim. Both source hashes, modes, formats and the native returned RGB hashes are retained in the private provenance audit.

| Input | Route | Detected | Transformed | Rejected | Status | Reasons | Changed pixels | Exterior | Determinism |
|---|---|---:|---:|---:|---|---|---:|---|---|
| holdout_001.jpg | photo | 3 | 0 | 3 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved | 0 | True | True |
| holdout_002.jpg | photo | 4 | 0 | 4 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved, pitch_unobserved | 0 | True | True |
| holdout_003.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, pitch_unobserved | 0 | True | True |
| holdout_004.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, original_width_unavailable | 0 | True | True |
| holdout_005.jpg | photo | 0 | 0 | 0 | rejected |  | 0 | True | True |
| holdout_006.jpg | photo | 1 | 0 | 1 | rejected | pitch_unobserved | 0 | True | True |
| holdout_007.jpg | photo | None | None | None | adapter_runtime_error | adapter_working_resize_memory_failure | None | NOT_RUN | same_adapter_error_twice |
| holdout_008.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, pitch_unobserved | 0 | True | True |

```json
{
  "protocol": "protocol-amended evaluation after provider RGB/JPEG format normalization; not pristine untouched one-shot validation",
  "INDEPENDENT_HOLDOUT_IMAGE_COUNT": 8,
  "INDEPENDENT_HASH_OVERLAP_COUNT": 0,
  "INDEPENDENT_PHOTO_EVALUATION_COMPLETE": false,
  "HOLDOUT_SUCCESS_COUNT": 0,
  "HOLDOUT_PARTIAL_SUCCESS_COUNT": 0,
  "HOLDOUT_REJECTED_COUNT": 7,
  "HOLDOUT_DETECTED_PAD_COUNT": 14,
  "HOLDOUT_TRANSFORMED_PAD_COUNT": 0,
  "HOLDOUT_REJECTED_PAD_COUNT": 14,
  "INDEPENDENT_EXTERIOR_PRESERVED": "PASS_EXECUTED_SUBSET",
  "INDEPENDENT_DETERMINISTIC_OUTPUT_OK": "PASS_EXECUTED_SUBSET",
  "INDEPENDENT_FAIL_CLOSED_OK": "INCOMPLETE_ADAPTER_ERROR",
  "PHOTO_DETECTOR_APPROVED": false,
  "PHOTO_PROTECTION_PRODUCTION_READY": false,
  "WINDOWS_FULL_EQUIVALENCE_VERIFIED": false,
  "PROJECT_COMPLETE": false,
  "FINAL_INDEPENDENT_VALIDATION_COMPLETE": false,
  "functional_independent_pipeline_checks": "INCOMPLETE",
  "operational_error_count": 1,
  "operational_error": "holdout_007 adapter working resize requests 75097440000 bytes; no inference code change permitted",
  "counts_scope": "successfully executed inputs only; failed input counts unknown",
  "limitation": "No annotated accuracy, no successful holdout transformation; actual Windows parity pending."
}
```

No GT was provided, so no detector accuracy, IoU, Dice, precision or recall is claimed. Mechanical checks pass for completed inputs only; the full evaluation is blocked by an adapter memory allocation error on holdout_007. The existing width normalization is 400 / median component diameter; the requested buffer is consistent with 200x scaling of the 726x862 source. No scale cap, detector cleanup or width substitution was introduced. This failure is an operational error, not a normal quality rejection; low-quality rejection is not protection efficacy. Final comprehensive independent validation remains false because successful holdout rendering and detector correctness are not established. No detector/quality/renderer/threshold code was modified.

Regression: 144 tests (141 pass, 3 optional-dependency skips); scanner reference pixels identical; frozen files unchanged; checkpoint 303/303 and captures 55/55 unchanged; unrelated data modifications preserved. Existing benchmark retained, no forced matcher evaluation.

Actual Windows execution is pending. A private parity kit with exact input bytes, Linux reference results and returned images is prepared; see ../docs/INDEPENDENT_HOLDOUT_WINDOWS.md. Include a successful PHOTO development case and scanner case when validating Windows, since this holdout exercises rejection only.
