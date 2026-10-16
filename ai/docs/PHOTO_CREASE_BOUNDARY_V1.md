# Opt-in distal silhouette and joint-crease boundary

`protect_photo_rounded_native_v1.py --crease-boundary` first verifies the cached
rounded detector inputs, then derives a new native-coordinate permission. The
old CLI default and frozen renderer remain available without this flag.

The original round cap is an anchor, not the final outline:

1. Refine only the bounded uncertain RGB band around an already anchored
   distal BODY contour using deterministic-seed GrabCut. No new finger is
   discovered; distant pixels remain unchanged.
2. Preserve the original semantic files. Write a separate `RGB_REFINED_BODY_V1`
   record with hashes and the original source record. Derived BODY is explicitly
   **not raw COLFISPOOF class output** and is forbidden as a training source.
3. Restore rasterization gaps next to split estimator owners only when exactly
   one owner reaches a pixel within one estimator-pixel diagonal. Ambiguous
   or distant pixels remain unresolved. Existing assignments do not change.
4. Search near the approximate IP/DIP cut for a transverse dark crease in
   source RGB. Fit offset, slope and curvature in finger-width units. Follow
   the resulting cut and the observed BODY silhouette, retaining the component
   containing the anchored TIP. This does not estimate ridge pitch.
5. Use that exact permission for the unchanged V12 native structure gate and
   `natural_auto_04` / `boundaryblend_02` renderer. Save `protected.png` as the
   actual renderer return; `covered.png` separately fills quality-rejected
   permission pixels with solid black.

Unavailable crease evidence retains the previous cap within its owner and is
marked for review. Unanchored candidates and unassigned detached fragments are
explicitly excluded and counted; they are not proved false positives. The
method cannot assert that all fingers were detected or that a crease is the
correct anatomical boundary. Search ranges, RGB band widths and curvature
limits are experimental geometry parameters, not a replacement for human GT.

The six development photographs were inspected while designing this method.
They are not a pristine test set. No GT, sample IDs or filename conditions are
used in inference. Check all fingertips at full resolution for residual skin
strips, adjacent fingers, background spill and excessive proximal coverage.
Small overcoverage near creases remains possible without human boundary labels.

Verification includes curved synthetic creases amid fine ridge texture,
rotation, malformed geometry, blank-image rejection, disconnected fragments,
bounded RGB refinement, repeatability, owner ambiguity, derived-asset tampering,
training exclusion and the existing source/mask/native-output regressions.
Original input files, EXIF/ICC metadata and RGB outside the exact permission must
remain unchanged. Native rejection counts must never be reported as successful
fingerprint transforms or privacy validation.

Development rerun (six photographs): 16 anchored, crease-observed permissions,
compared with 104 previous connected permission fragments. Native transforms
were rejected for all 16: 11 feature-gate failures and 5 unobserved local-pitch
failures. Separate solid-redaction outputs were produced for all six images.
The 141-test contract/regression suite passed. Native source snapshots stayed
constant during each run. Four frozen protection-source hashes were preserved.
An additional local curve-tracing experiment introduced protruding proximal
edges and was not promoted. Small crease-end errors remain a review limitation;
these development images do not establish zero omission or overcoverage.
