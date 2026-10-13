# Thin development GUI

`python ai/app/windows/unified_gui.py` calls the shared routed CLI in separate
processes. Configure scientific Python, isolated COLFISPOOF and native/Java
runtimes first; see ../../docs/WINDOWS_SETUP.md. No images/models are bundled.
PHOTO quality rejection is normal; detector and production approval remain false.
The GUI implementation has syntax validation only on the current Linux host.
Actual Windows execution and full-equivalence validation are required.
