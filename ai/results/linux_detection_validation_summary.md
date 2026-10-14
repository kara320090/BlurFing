# Linux automatic detection validation: incomplete

Baseline reproduction: 20 images, candidate photos 10, candidates 17, accepted boundaries 1.

After: 27 multiview geometric proposals (different counting contract), one legacy boundary retained exactly, zero approved transformation regions in the 20-image set. Most rejects are missing crease evidence or unstable/merged widths. New graph-cut boundaries remain review-gated. Close-up foreground exceeds the frozen square-scope geometry.

Four inputs have prior human-reviewed ridge-positive ROIs; 11 are ambiguous and 5 provisional non-targets. These are not segmentation ground truth. Background leakage is **unmeasured**, not zero.

Artifact contract tests: 17 PASS. A separate existing baseline control has 10/10 applied transforms, unchanged exterior, NBIS features 39→34/self 320/changed 4 and SourceAFIS 31→20/self 373.5211/changed 1.3059. Those results are not 20-image detector improvements.

See the JSON for timing and per-sample reject reasons. Private images, masks, previews and raw matcher templates are excluded.

BLOCKER: expert whole-pad boundary/negative references before promoting any new mask. GitHub fetch also fails due DNS; remote state is unverified. No commit/push is claimed.

Automatic detection/boundary deployment readiness is **false**. FINAL_INDEPENDENT_VALIDATION_COMPLETE=false; PROJECT_COMPLETE=false.

Follow-up: [human GT evaluation](linux_detection_gt_evaluation.md) completed on four positives; 0/4 usable approvals. The missing-positive-mask blocker is resolved, but proposal/width isolation, scope compatibility and negative/control validation remain blockers.
