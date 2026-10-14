# Independent holdout and actual Windows parity

The PHOTO detector remains unapproved for production. Independent photographs without masks can test functional execution, fail-closed rejection, exterior preservation and determinism; they cannot establish detector accuracy or a privacy guarantee.

The Linux evaluation uses the unchanged unified API twice per source, with a source-hash development denylist and an unchanged configuration snapshot. No input is removed after observing its result. Photos, metadata, result images and masks remain private.

## Actual Windows execution

Use the same public AI source version and install the runtimes described in WINDOWS_SETUP.md. Configure the COLFISPOOF Python interpreter, source directory and official model through the documented environment variables. Keep the rejected refinement model disabled. The thin GUI is `app/windows/unified_gui.py`; it invokes the common CLI rather than duplicating the algorithms.

Privately transfer each exact source file and its Linux `result.json` and `returned.png`. In PowerShell, from the AI directory:

```powershell
python platform/windows/validate_unified_case.py --input "C:\private\holdout_001.jpg" --reference-json "C:\private\linux\0_first\result.json" --reference-image "C:\private\linux\0_first\returned.png" --output "C:\private\windows\holdout_001"
```

Repeat for all eight cases, and for the scanner reference and existing successful PHOTO development cases. The holdout alone may contain only rejected cases, which does not test successful Windows PHOTO rendering. Verify the GUI selection, preview and save behavior separately. Do not upload these private files.

The checker compares source hash, routing, status, counts, region signatures and returned pixels. It reports a single-case measurement, never full equivalence by itself. Actual Windows execution is required; Linux syntax checks cannot substitute for it. Keep `WINDOWS_FULL_EQUIVALENCE_VERIFIED=false` until the complete runtime and GUI matrix passes.
