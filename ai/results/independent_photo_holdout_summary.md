# Independent PHOTO holdout evaluation

Eight declared independent inputs passed decoding and source-hash exclusion against the 55 development sources, including GT and training annotations. The provider declared no prior training, tuning or GT use. No image was excluded or replaced after observing results. Configuration and thresholds remained unchanged.

Evaluation is incomplete: four files bearing JPG names decode as RGBA and the frozen API explicitly rejects alpha inputs. These are operational input-contract errors, not successful quality rejections. Changing preprocessing during this test was prohibited. Each supported input was executed twice; each unsupported input was attempted twice.

| Input | Route | Detected | Transformed | Rejected | Status | Reason | Exterior | Determinism |
|---|---|---:|---:|---:|---|---|---|---|
| holdout_001.jpg | photo | 3 | 0 | 3 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved | True | True |
| holdout_002.jpg | photo | 4 | 0 | 4 | rejected | pitch_unobserved, pitch_unobserved, pitch_unobserved, pitch_unobserved | True | True |
| holdout_003.jpg | photo | 2 | 0 | 2 | rejected | pitch_unobserved, pitch_unobserved | True | True |
| holdout_004.jpg | NOT_RUN | None | None | None | input_contract_error | unsupported_RGBA_input | NOT_RUN | same_input_error_twice |
| holdout_005.jpg | NOT_RUN | None | None | None | input_contract_error | unsupported_RGBA_input | NOT_RUN | same_input_error_twice |
| holdout_006.jpg | photo | 1 | 0 | 1 | rejected | pitch_unobserved | True | True |
| holdout_007.jpg | NOT_RUN | None | None | None | input_contract_error | unsupported_RGBA_input | NOT_RUN | same_input_error_twice |
| holdout_008.jpg | NOT_RUN | None | None | None | input_contract_error | unsupported_RGBA_input | NOT_RUN | same_input_error_twice |

No GT masks were supplied: no IoU, Dice, precision, recall or detector accuracy is reported. PHOTO approval and production readiness remain false. Supported cases preserve exterior and rejected-pad pixels; unsupported cases return no transformed image. No protection effectiveness claim follows from rejection.

Regression: 144 tests, 141 passed and 3 optional-dependency skips. Existing seven PHOTO development outputs and scanner reference are pixel-identical. Checkpoint 303/303 and capture 55/55 hashes are preserved, as are frozen source, runtime/model hashes and four unrelated data modifications.

The existing CPU benchmark is retained; no redundant holdout benchmark or forced matcher evaluation was performed. Actual Windows runtime/GUI parity remains unverified; see ../docs/INDEPENDENT_HOLDOUT_WINDOWS.md.

Next input action: provide RGB copies of holdout_004, holdout_005, holdout_007 and holdout_008, preserving the original files. This is a representation-contract correction, not detector tuning. Retain this failed attempt and the original hashes in the private audit.
