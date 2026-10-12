# Windows setup

Windows runtime validation is complete: NBIS native build, the official NBIS bridge fixture and actual SourceAFIS Windows execution passed. WINDOWS_RUNTIME_VALIDATED=true, while windows_full_equivalence_verified=false: full Windows/Linux pipeline equivalence remains unverified. Do not tune frozen parameters or thresholds. See VALIDATION.md for the scope of actual checks.

## 1. Python and venv
Install Python >=3.10 and expose python on PATH. In PowerShell, from the repository root:
```powershell
python --version
python -m venv ai/.venv
. ai/.venv/Scripts/Activate.ps1
python -m pip install -r ai/requirements.txt
python ai/scripts/reproduce_frozen_pipeline.py --check
```
Follow your organization's PowerShell execution policy; these scripts never change it automatically.

## 2. Java and SourceAFIS
Prepare JDK >=11 and the 15 JAR artifacts listed in docs/sourceafis_runtime.json. Check SHA-256 and put the artifacts under lib/ in your private SourceAFIS folder.
```powershell
java -version
javac -version
$env:BLURFING_SOURCEAFIS_HOME = 'C:/path/to/sourceafis'
```
No JARs/classes are bundled. The adapter compiles the shared Java source in a fresh system temporary folder when needed. Windows classpath uses semicolon; Linux uses colon.

## 3. NBIS native build
Prepare official NBIS 5.0.0 source and a compatible MinGW-w64/MSYS gcc/g++/make environment. Read the official INSTALL_WINDOWS.txt. NBIS libraries and the bridge must use the same toolchain and architecture. Do not link Linux libraries or old unrelated MinGW objects.
```powershell
$env:MSYSTEM = 'MINGW64'
$env:CMAKE_POLICY_VERSION_MINIMUM = '3.5' # For the bundled old OpenJPEG CMake project with CMake 4.x.
$env:PATH = 'C:/msys64/mingw64/bin;C:/msys64/usr/bin;' + $env:PATH
& ai/platform/windows/build_nbis_windows.ps1 `
  -NbisSource 'C:/path/to/Rel_5.0.0' `
  -BuildDir 'C:/nbis_build_new' `
  -Bash 'C:/msys64/usr/bin/bash.exe' -Compiler 'C:/msys64/mingw64/bin/g++.exe'
```
BuildDir must be new and use a simple ASCII drive path without spaces. Source is copied before official --MSYS --64 setup/config/header/libs/bins commands, including PNG/OpenJPEG headers and libraries enabled by that configuration. The bridge is built with -municode. The original NBIS source is untouched. Builds are serial because legacy PNG/zlib export targets lack parallel prerequisites. Native stdout/stderr are retained as log text; a nonzero exit code stops the script before runtime config creation. PowerShell 5.1 parsing and stderr/exit-code behavior were tested on Windows. No automatic retries or official source patches are performed; investigate a failed log before starting another new build directory.

## 4. Runtime config and prerequisites
A successful build writes nbis_windows.runtime.json with the actual exe path and SHA-256. config/nbis_windows.example.json is only a placeholder.
```powershell
$env:BLURFING_NBIS_CONFIG = 'C:/path/to/nbis_windows.runtime.json'
& ai/platform/windows/setup_windows.ps1
python ai/scripts/check_platform_runtime.py --require-all
```
The adapter checks PE/x86-64 and hash. Inspect dependencies with the toolchain's objdump -p and provide required MinGW runtime DLLs. Build success alone is not runtime validation.

The 2026-10-12 native build produced a PE x86-64 bridge and runtime JSON in private/nbis_build_win_20261012_03. Bridge SHA-256: `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`. Real RAW/MATCH smoke checks and setup/prerequisites passed with C:/msys64/mingw64/bin on the validation process PATH. No Linux fallback was used. MinGW DLLs were not bundled into the build folder; an independent installation without this toolchain PATH was not tested.

## 5. Public fixture validation
Provide public a011p_03.wsq, reference a011p_03.xyt, and dwsq.exe from the same official build. No fixture files are bundled.
```powershell
python ai/platform/windows/validate_windows_runtime.py `
  --config $env:BLURFING_NBIS_CONFIG `
  --wsq 'C:/path/to/a011p_03.wsq' `
  --decoder 'C:/path/to/dwsq.exe' `
  --reference-xyt 'C:/path/to/a011p_03.xyt'
```
Expected: 336x512, depth 8, raw 172032 bytes; RAW 87 rows; reference XYT byte-identical; self-match 499 87 87. The validator decodes a temporary copy and records exit/stdout/stderr and input/runtime hash preservation. WINDOWS_BRIDGE_FIXTURE_VALIDATED covers the bridge fixture only, not full pipeline or Windows equivalence.

Final validator audit: status=complete, WINDOWS_BRIDGE_FIXTURE_VALIDATED=true, raw_features=87, self_match="499 87 87", retry_count=0. Fixture SHA-256, 336x512/8-bit decode, RAW 172032 bytes and reference XYT byte identity all passed against bridge SHA-256 `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`. WINDOWS_NBIS_FIXTURE_VALIDATED=true supersedes the earlier fixture-missing result. The audit retains windows_full_equivalence_verified=false; this fixture result does not verify the full Windows/Linux transform/evaluation pipeline.

## 6. Transform
```powershell
python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input 'C:/path/to/input.jpg'
```
Use consented private data; do not add it to the public tree. Results go to a new system temporary folder.

## 7. NBIS evaluation
Use scripts/nbis_matcher.py run_nbis_job(images, pairs, run_name=...) with the existing width-normalized original and returned RGB frames. Pairs are original self and original-to-transformed. Follow the LINUX_SETUP.md API contract; do not invent new crops or thresholds. Keep insufficient_features separate from protection success.

## 8. SourceAFIS evaluation and full pipeline equivalence
Use scripts/sourceafis_matcher.py run_matcher_job on exactly the same pairs. Record raw scores separately: matcher scales differ. Runtime validation covers the native NBIS build, official bridge fixture and actual SourceAFIS execution. Full Windows/Linux pipeline equivalence separately requires matching transform/evaluation inputs and comparison criteria, rendered-transform mask-exterior preservation, development ROI reproduction and remaining failure/timeout scenarios. Keep windows_full_equivalence_verified=false until that evidence exists. Independent final validation still requires new person/different-date non-development captures; FINAL_INDEPENDENT_VALIDATION_COMPLETE=false and PROJECT_COMPLETE=false remain unchanged.

The 2026-10-12 SourceAFIS execution check used synthetic ridges, a duplicate image and an invalid image. It verified real wrapper compilation/extraction/matching, duplicate-template cache reuse, failure status and Unicode/space input paths. It is not a development ROI rerun or protection validation. Windows native build results do not change WINDOWS_CROSS_BUILD_SUCCESS=false.
