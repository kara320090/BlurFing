# Windows parity runtime compatibility

Use the core `.venv` installed from `ai/requirements.txt` for the shared API,
validator and GUI. Use a separate Python 3.10 environment for the TensorFlow
worker, installed from `platform/windows/requirements_colfispoof.txt`.
Do not run the whole pipeline in the legacy TensorFlow environment: its NumPy
and OpenCV versions differ from the evaluated core environment.

The raw model adapter accepts either an external COLFISPOOF checkout root or
its `pre-processing` directory. Both resolve to the same external
`Segmentation/DeepLabModel.py`. This only normalizes the loader path. Archive
hash validation, graph loading, INPUT_SIZE=4608, four rotations, encoded pixel
coordinates, resizing and consensus remain unchanged. Upstream code and model
weights are not edited or bundled.

The evaluated model runtime used Pillow 9.3.0. Newer Pillow removes the
`Image.ANTIALIAS` attribute used by the external loader. Pin the worker's Pillow
to 9.3.0 rather than editing the upstream source or substituting interpolation.
Keep core Pillow at the version in `ai/requirements.txt`.

Example, with externally supplied runtime paths:

```powershell
.\ai\platform\windows\run_unified.ps1 `
  -ColfispoofPython 'C:\model-env\Scripts\python.exe' `
  -ColfispoofSource 'C:\external\COLFISPOOF' `
  -ColfispoofModel 'C:\external\COLFISPOOF\pre-processing\Segmentation\model\deeplab_model.tar.gz' `
  -Gui
```

For CLI processing, replace `-Gui` with `-InputImage` and a fresh
`-OutputDirectory`. The launcher sets process-local runtime paths, selects the
project core interpreter and enables UTF-8. It does not install packages,
change user-wide environment variables, or duplicate pipeline logic.

The thin unified GUI reads CLI JSON as UTF-8 and starts its subprocess without
a separate Windows console. Unicode transport and child-error propagation have
regression tests. Synthetic presentation tests cover success, partial_success,
rejected, reason text, preview construction, output copying and source preservation;
these tests do not simulate or establish biometric performance.

## Diagnostic findings

The previous PHOTO mismatch occurred before semantic inference: the worker
could not resolve the supplied checkout root, and direct inference with the
preprocessing path failed on `Image.ANTIALIAS`. The fail-closed API returned
original pixels, explaining a misleading pixel-only match for rejected inputs
and a large pixel discrepancy for the development transform case.

The legacy scientific environment reproduced the prior scanner error exactly:
three RGB pixels differed by one intensity level. The masks, canonical pitch,
angle, grayscale and distance weights matched, but float32 ridge-field values
differed and the synthetic intensity expression used float32 in the legacy
runtime versus float64 in the core runtime. The discrepancy already existed in
memory before PNG encoding. The configured core runtime produced the exact
Linux returned RGB without renderer or rounding changes. These observations
identify a dependency/runtime mismatch; they do not isolate each library's
contribution to the floating-point field differences.

Private diagnostics must retain source/model identities, decoded RGB, model
input, raw class histograms, body/tip consensus, coarse components, adapter
metadata, renderer inputs/outputs and returned RGB signatures. Linux references
in the supplied kit have no raw semantic intermediates, so equality of every
raw Linux tensor cannot be asserted from those references. Compare all
available region hashes, outcomes and returned RGB directly.

Run model inference serially during the final matrix to avoid overlapping
large model allocations. A worker timeout is an operational failure, not a
numerical mismatch. Preserve failed runs and rerun with fresh output; never
rewrite a failed report as PASS.

The private case matrix and native GUI checks are independent evidence. A
single-case validator intentionally leaves full equivalence false. No threshold,
detector, frozen renderer, scanner algorithm, matcher meaning, private input,
Linux reference or equivalence criterion is changed by this compatibility work.

## Validation on 2026-10-14

The final serial private matrix passed all eight holdouts, the development
transform case and the scanner reference, including exact native RGB equality.
An earlier matrix retained one operational timeout; a separate retry and the
complete final serial matrix both passed. No timeout limit was modified.

Actual Windows GUI interaction verified image selection, PHOTO rejection and
success, scanner success, previews, reason text and saving. Saved images were
compared with the corresponding CLI output and Linux reference. No real partial
PHOTO case is supplied; partial presentation was checked with the explicitly
synthetic UI fixture above. Full-equivalence evidence is limited to this supplied
case matrix and configured runtimes, not all inputs or matcher-score equivalence.

Core unit tests: 156 run, 153 passed, three optional PyTorch tests skipped.
GUI regression tests: three passed. Python source syntax: 111 files passed.
Both configured environments passed `pip check`. Existing NBIS decoded public
fixture extraction/self-match also ran; no new decoder execution or cross-platform
matcher-score equivalence was inferred from that smoke check.
