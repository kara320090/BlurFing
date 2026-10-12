# Windows runtime checks

Windows runtime 검증을 완료했습니다: NBIS native build와 공식 fixture(336x512, 8-bit, RAW 172032 bytes, 87 minutiae, reference XYT byte-identical, self-match 499 87 87), SourceAFIS 실제 실행이 PASS입니다. 최종 validator는 status=complete, retry_count=0이며 기존 PowerShell stderr/exit-code 수정사항은 유지합니다. ../../docs/WINDOWS_SETUP.md와 ../../docs/VALIDATION.md의 검증 범위를 따르세요.

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

Runtime 검증은 Windows/Linux 전체 transform/evaluation pipeline 동등성 검증과 구분합니다. 전체 동등성과 독립 holdout 보호 성능은 미검증입니다. Linux 회귀는 syntax/import/config/dispatch와 소스 보존 검사이며 native 실행을 재검증하지 않았습니다. Windows native build는 Linux-to-Windows cross-build 성공을 의미하지 않습니다.
