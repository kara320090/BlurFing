# Thin development GUI

`python ai/app/windows/unified_gui.py` calls the shared routed CLI in separate
processes. Configure scientific Python, isolated COLFISPOOF and native/Java
runtimes first; see ../../docs/WINDOWS_SETUP.md. No images/models are bundled.
PHOTO quality rejection is normal; detector and production approval remain false.
Actual Windows image selection, PHOTO rejection/success, scanner success,
preview and saving were tested on 2026-10-14. Saved outputs matched Linux
references exactly. Partial-success presentation has a synthetic UI regression
test; no real partial PHOTO case was supplied. See
../../docs/WINDOWS_PARITY_COMPATIBILITY.md for the exact validation scope.
