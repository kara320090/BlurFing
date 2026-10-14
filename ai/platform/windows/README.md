# Windows 실행 환경 검증

Windows 실행 환경 검증을 완료했습니다. NBIS 네이티브 빌드와 공식 검증용 자료 확인(336x512, 8비트, RAW 172032바이트, 특징점 87개, 참조 XYT 바이트 일치, 동일 지문 매칭 결과 499 87 87), SourceAFIS 실제 실행이 모두 통과했습니다. 최종 검증 도구는 status=complete, retry_count=0이며 기존 PowerShell 표준 오류·종료 코드 처리 수정사항은 유지합니다. [Windows 설치 안내](../../docs/WINDOWS_SETUP.md)와 [검증 기록](../../docs/VALIDATION.md)의 검증 범위를 따르세요.

```text
WINDOWS_NBIS_NATIVE_BUILD_SUCCESS=true
WINDOWS_NBIS_FIXTURE_VALIDATED=true
WINDOWS_SOURCEAFIS_RUNTIME_VALIDATED=true
WINDOWS_RUNTIME_VALIDATED=true
windows_full_equivalence_verified=true
WINDOWS_EQUIVALENCE_SCOPE=provided_10_case_unified_matrix_and_actual_GUI_smoke
WINDOWS_CROSS_BUILD_SUCCESS=false
LINUX_REGRESSION_OK=true
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```

실행 환경 검증은 Windows/Linux 전체 변환·평가 파이프라인 동등성 검증과 구분합니다. 제공된 10-case unified matrix의 outcome·region·native RGB와 실제 GUI smoke는 exact PASS입니다. 임의 입력과 matcher score 동등성, 최종 독립 보호 성능은 이 결과로 입증하지 않습니다. [현재 parity 기록](../../docs/WINDOWS_PARITY_COMPATIBILITY.md)을 따르세요. Linux 회귀 검사는 구문·가져오기·설정·호출 분기 및 소스 보존 검사이며 네이티브 실행을 재검증하지 않았습니다. Windows 네이티브 빌드는 Linux에서 Windows용으로 수행하는 교차 빌드 성공을 의미하지 않습니다.
