# Windows setup

Windows implementation is ready; real Windows build/runtime validation is pending. Do not tune frozen parameters or thresholds.

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
& ai/platform/windows/build_nbis_windows.ps1 `
  -NbisSource 'C:/path/to/Rel_5.0.0' `
  -BuildDir 'C:/nbis_build_new' -Bash bash -Compiler g++
```
BuildDir must be new and use a simple ASCII drive path without spaces. Source is copied before official --MSYS --64 setup/config/header/libs/bins commands. The bridge is built with -municode. The original NBIS source is untouched. Any build failure stops with logs; no source patches/retries are performed. Official NBIS may require environment-specific preparation. This PowerShell script was reviewed but not parsed/executed because PowerShell was unavailable in the Linux workstation.

## 4. Runtime config and prerequisites
A successful build writes nbis_windows.runtime.json with the actual exe path and SHA-256. config/nbis_windows.example.json is only a placeholder.
```powershell
$env:BLURFING_NBIS_CONFIG = 'C:/path/to/nbis_windows.runtime.json'
& ai/platform/windows/setup_windows.ps1
python ai/scripts/check_platform_runtime.py --require-all
```
The adapter checks PE/x86-64 and hash. Inspect dependencies with the toolchain's objdump -p and provide required MinGW runtime DLLs. Build success alone is not runtime validation.

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

## 6. Transform
```powershell
python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input 'C:/path/to/input.jpg'
```
Use consented private data; do not add it to the public tree. Results go to a new system temporary folder.

## 7. NBIS evaluation
Use scripts/nbis_matcher.py run_nbis_job(images, pairs, run_name=...) with the existing width-normalized original and returned RGB frames. Pairs are original self and original-to-transformed. Follow the LINUX_SETUP.md API contract; do not invent new crops or thresholds. Keep insufficient_features separate from protection success.

## 8. SourceAFIS evaluation and completion
Use scripts/sourceafis_matcher.py run_matcher_job on exactly the same pairs. Record raw scores separately: matcher scales differ. On real Windows, verify SourceAFIS extraction/match, native fixture, Unicode/space paths, failure return, mask-exterior preservation, and NBIS insufficient_features/timeout/process errors. Only then update Windows validation status with its actual scope. Independent final validation still requires new person/different-date non-development captures.
