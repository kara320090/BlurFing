# Validation

The development tables below are existing Linux results. They were not rerun on Windows and are not independent holdout results.

## NBIS

| Sample | Original features | Transformed features | Self | Original→Transformed |
|---|---:|---:|---:|---:|
| DEV-01 | 39 | 34 | 320 | 4 |
| DEV-02-R1 | 49 | 37 | 499 | 7 |
| DEV-02-R3 | 58 | 26 | 499 | 9 |

## SourceAFIS

| Sample | Original features | Transformed features | Self | Original→Transformed |
|---|---:|---:|---:|---:|
| DEV-01 | 31 | 20 | 373.5211 | 1.3059 |
| DEV-02-R1 | 34 | 15 | 408.4964 | 1.2415 |
| DEV-02-R3 | 33 | 13 | 396.8380 | 0 |

세 development ROI에서 두 matcher 모두 original→transformed score가 self-match보다 크게 낮았습니다.

NBIS와 SourceAFIS score scale은 다르므로 직접 비교하지 않습니다. 작은 development sample의 결과이며 일반적 보호 성능이나 식별 불가능성·보안을 보장하지 않습니다. insufficient_features/추출 실패는 보호 성공으로 집계하지 않습니다.

FINAL_INDEPENDENT_VALIDATION_COMPLETE=false

## Windows execution checks (2026-10-12)

NBIS 5.0.0 libraries, mindtct/bozorth3/dwsq and the Windows bridge built with MinGW-w64 GCC/G++ 16.2.0, MSYS2 make 4.4.1 and CMake 4.4.4. MSYSTEM=MINGW64 and CMAKE_POLICY_VERSION_MINIMUM=3.5 were used; the final build was serial. Official source and algorithm logic were not patched. The first new build failed with exit 2 due to omitted PNG/OpenJPEG dependencies; a second new build failed with exit 2 because the task-applied -j4 raced legacy zlib archive/export targets. After fixing the Windows build orchestration, a third new build completed with exit 0. Failed directories/logs were retained. CMake deprecation and bridge IGNORE/SC_SIZE macro warnings remained in the logs.

The bridge is PE x86-64, hash-pinned by a UTF-8 runtime JSON: SHA-256 `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`. With the MinGW runtime DLL directory on the process PATH, the Windows facade/adapter actually extracted 65 minutiae from the synthetic ridge image and returned self-match `375 65 65`. A blank image produced 0 minutiae and `insufficient_features`; it was not accepted as a protection success. Unicode/space input and output paths worked. Invalid numeric input, short RAW, missing XYT and over-1000-row XYT returned nonzero. Linux rejected the PE runtime, and the Windows adapter used no Linux fallback. dwsq -version and setup_windows.ps1 passed. These checks do not substitute for the public fixture or a full pipeline test.

SourceAFIS 3.18.1 ran through the shared Java wrapper and Windows adapter using the 15 hash-checked JARs and Temurin 25.0.1. The wrapper was compiled with `javac --release 11` in a fresh temporary job. A synthetic ridge image produced 5 minutiae and self-match 41.88229363871244. A duplicate image reused the template cache and produced the same score. An invalid image and its pair remained `failed`, with no score. Unicode and space-containing input paths worked. These are execution smoke checks, not biometric accuracy or protection measurements.

Python syntax checks passed for 39 files under scripts/ and platform/. Both Linux and Windows adapters imported and dispatched correctly; unsupported OS and missing NBIS runtime configurations failed. Windows rejected an ELF runtime. The 40 tracked shared/Linux source files matched HEAD after line-ending normalization. A synthetic blank-image/zero-strength check preserved the input, retained unverified status, failed closed when transformation was required, and restored the renderer after exceptions. A rendered transform's mask-exterior preservation and Linux native execution were not rerun.

## Final Windows public fixture validation

The final Windows validator audit was reviewed after the user completed the official `a011p_03.wsq` validation. It records `status=complete`, `WINDOWS_BRIDGE_FIXTURE_VALIDATED=true`, `raw_features=87`, `self_match="499 87 87"`, `retry_count=0` and `windows_full_equivalence_verified=false`. All three decode/RAW/MATCH commands exited 0 with empty stderr. Runtime SHA-256 matches the native bridge above.

The fixture SHA-256 is `10b952aa4c00be8af38076001d306b9446a5db97653c2cc6be8bd779e6db528b`. Decode dimensions 336x512, depth 8, RAW size 172032 bytes, MINDTCT 87 minutiae, reference XYT byte identity and BOZORTH3 self-match `499 87 87` all passed. The audit records RAW SHA-256 `eeee7fb0ba69b9372aee1f7adad98eb687b611b15ed60fb1eeaa9252d02f0256` and XYT SHA-256 `041efee9edde41146f18f9a610db93881610d2efdd4553e3e705ee59af74399d`. This supersedes the earlier fixture-missing state. Private fixture/audit/runtime files are not included in Git.

```text
WINDOWS_NBIS_NATIVE_BUILD_SUCCESS=true
WINDOWS_NBIS_FIXTURE_VALIDATED=true
WINDOWS_SOURCEAFIS_RUNTIME_VALIDATED=true
WINDOWS_RUNTIME_VALIDATED=true
windows_full_equivalence_verified=false
WINDOWS_CROSS_BUILD_SUCCESS=false
LINUX_REGRESSION_OK=true
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```

WINDOWS_RUNTIME_VALIDATED covers the native NBIS build, official bridge fixture and actual Windows SourceAFIS execution. It does not establish Windows/Linux full pipeline equivalence, rendered-transform mask-exterior preservation, Windows development ROI reproduction, independent installation without the MinGW DLL PATH, actual timeout scenarios, or independent holdout protection performance. Those remain unverified. LINUX_REGRESSION_OK covers syntax/import/config/dispatch and source preservation only; Linux native execution was not rerun. WINDOWS_CROSS_BUILD_SUCCESS remains false because Windows native compilation is not a Linux-to-Windows cross-build. Existing Linux development results and independent/project completion states remain unchanged.
