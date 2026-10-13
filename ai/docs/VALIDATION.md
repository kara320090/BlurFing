# 검증 기록

아래 개발용 결과 표는 기존 Linux 결과입니다. Windows에서 다시 실행한 결과가 아니며, 독립 검증용 보류 자료(holdout)의 결과도 아닙니다.

## NBIS

| 시료 | 원본 특징점 수 | 변환본 특징점 수 | 동일 지문 매칭 점수 | 원본→변환본 점수 |
|---|---:|---:|---:|---:|
| DEV-01 | 39 | 34 | 320 | 4 |
| DEV-02-R1 | 49 | 37 | 499 | 7 |
| DEV-02-R3 | 58 | 26 | 499 | 9 |

## SourceAFIS

| 시료 | 원본 특징점 수 | 변환본 특징점 수 | 동일 지문 매칭 점수 | 원본→변환본 점수 |
|---|---:|---:|---:|---:|
| DEV-01 | 31 | 20 | 373.5211 | 1.3059 |
| DEV-02-R1 | 34 | 15 | 408.4964 | 1.2415 |
| DEV-02-R3 | 33 | 13 | 396.8380 | 0 |

개발용 관심 영역 3개에서 두 매칭 엔진 모두 원본→변환본 점수가 동일 지문 매칭 점수보다 크게 낮았습니다.

NBIS와 SourceAFIS의 점수 척도는 다르므로 직접 비교하지 않습니다. 소수의 개발용 시료 결과이며 일반적 보호 성능이나 식별 불가능성·보안을 보장하지 않습니다. insufficient_features 상태나 추출 실패는 보호 성공으로 집계하지 않습니다.

FINAL_INDEPENDENT_VALIDATION_COMPLETE=false

## Windows 실행 검사 (2026-10-12)

MinGW-w64 GCC/G++ 16.2.0, MSYS2 make 4.4.1, CMake 4.4.4로 NBIS 5.0.0 라이브러리, mindtct/bozorth3/dwsq 및 Windows 브리지를 빌드했습니다. MSYSTEM=MINGW64와 CMAKE_POLICY_VERSION_MINIMUM=3.5를 사용했으며 최종 빌드는 순차 실행했습니다. 공식 소스와 알고리즘 로직은 수정하지 않았습니다. 첫 번째 새 빌드는 PNG/OpenJPEG 의존성 누락으로 종료 코드 2를 반환했습니다. 두 번째 새 빌드는 작업 중 적용한 -j4가 기존 zlib 압축 라이브러리 생성·내보내기 대상의 실행 순서를 경합시켜 종료 코드 2를 반환했습니다. Windows 빌드 절차를 수정한 뒤 세 번째 새 빌드는 종료 코드 0으로 완료됐습니다. 실패한 디렉터리와 로그는 보존했습니다. CMake 사용 중단 경고와 브리지의 IGNORE/SC_SIZE 매크로 경고는 로그에 남겼습니다.

브리지는 PE x86-64 형식이며 UTF-8 실행 환경 JSON에 SHA-256 `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`을 고정했습니다. 프로세스 PATH에 MinGW 실행 DLL 디렉터리를 지정한 상태에서 Windows 공통 인터페이스와 어댑터가 합성 능선 이미지에서 실제로 특징점 65개를 추출하고 동일 지문 매칭 결과 `375 65 65`를 반환했습니다. 빈 이미지에서는 특징점 0개와 insufficient_features 상태를 반환했으며 보호 성공으로 인정하지 않았습니다. 유니코드·공백을 포함한 입출력 경로도 동작했습니다. 잘못된 숫자 입력, 길이가 짧은 RAW, 누락된 XYT, 1000행을 초과한 XYT는 0이 아닌 종료 코드를 반환했습니다. Linux는 PE 실행 파일을 거부했고 Windows 어댑터는 Linux 대체 경로를 사용하지 않았습니다. dwsq -version 및 setup_windows.ps1도 통과했습니다. 이 검사는 공개 검증용 자료 확인이나 전체 파이프라인 시험을 대신하지 않습니다.

SourceAFIS 3.18.1은 해시를 확인한 JAR 15개와 Temurin 25.0.1을 사용하여 공통 Java 래퍼 및 Windows 어댑터를 통해 실행했습니다. 래퍼는 새 임시 작업 디렉터리에서 `javac --release 11`로 컴파일했습니다. 합성 능선 이미지에서는 특징점 5개와 동일 지문 매칭 점수 41.88229363871244를 얻었습니다. 동일한 복제 이미지는 템플릿 캐시를 재사용하고 같은 점수를 반환했습니다. 잘못된 이미지와 그 매칭 쌍은 failed 상태를 유지했으며 점수를 반환하지 않았습니다. 유니코드·공백을 포함한 입력 경로도 동작했습니다. 이는 실행 동작 확인이며 생체인식 정확도나 보호 성능 측정이 아닙니다.

scripts/와 platform/ 아래 Python 파일 39개의 구문 검사가 통과했습니다. Linux와 Windows 어댑터의 가져오기와 호출 분기가 올바르게 동작했고 지원하지 않는 운영체제 및 누락된 NBIS 실행 환경 설정은 실패로 처리했습니다. Windows는 ELF 실행 파일을 거부했습니다. 추적 중인 공통·Linux 소스 40개는 줄바꿈을 정규화한 뒤 HEAD와 일치했습니다. 합성 빈 이미지·강도 0 검사에서는 입력과 미검증 상태를 보존했고, 필수 변환을 수행할 수 없으면 실패로 처리했으며 예외 후 렌더러를 복원했습니다. 실제 렌더링 변환의 마스크 밖 픽셀 보존과 Linux 네이티브 실행은 다시 검사하지 않았습니다.

## Windows 공식 공개 자료 최종 검증

사용자가 공식 `a011p_03.wsq` 검증을 완료한 뒤 최종 Windows 검증 도구의 감사 기록을 확인했습니다. 기록에는 `status=complete`, `WINDOWS_BRIDGE_FIXTURE_VALIDATED=true`, `raw_features=87`, `self_match="499 87 87"`, `retry_count=0`, `windows_full_equivalence_verified=false`가 명시되어 있습니다. 디코딩·RAW·MATCH 명령 3개는 모두 종료 코드 0을 반환했으며 표준 오류 출력은 비어 있었습니다. 실행 파일 SHA-256은 위 네이티브 브리지와 일치합니다.

검증용 자료의 SHA-256은 `10b952aa4c00be8af38076001d306b9446a5db97653c2cc6be8bd779e6db528b`입니다. 디코딩 크기 336x512, 깊이 8비트, RAW 크기 172032바이트, MINDTCT 특징점 87개, 참조 XYT 바이트 일치 및 BOZORTH3 동일 지문 매칭 결과 `499 87 87`이 모두 통과했습니다. 감사 기록의 RAW SHA-256은 `eeee7fb0ba69b9372aee1f7adad98eb687b611b15ed60fb1eeaa9252d02f0256`, XYT SHA-256은 `041efee9edde41146f18f9a610db93881610d2efdd4553e3e705ee59af74399d`입니다. 이 최종 결과는 앞서 기록한 검증용 자료 누락 상태를 대체합니다. 비공개 검증용 자료·감사 기록·실행 파일은 Git에 포함하지 않습니다.

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

WINDOWS_RUNTIME_VALIDATED는 네이티브 NBIS 빌드, 공식 브리지 검증용 자료 확인 및 실제 Windows SourceAFIS 실행을 포함합니다. Windows/Linux 전체 파이프라인 동등성, 실제 렌더링 변환의 마스크 밖 픽셀 보존, Windows 개발용 관심 영역 결과 재현, MinGW DLL PATH 없이 수행하는 독립 설치, 실제 시간 초과 상황, 독립 보류 자료의 보호 성능은 아직 검증하지 않았습니다. LINUX_REGRESSION_OK는 구문·가져오기·설정·호출 분기 및 소스 보존만 의미하며 Linux 네이티브 실행은 다시 검사하지 않았습니다. Windows 네이티브 컴파일은 Linux에서 Windows용으로 수행하는 교차 빌드가 아니므로 WINDOWS_CROSS_BUILD_SUCCESS=false를 유지합니다. 기존 Linux 개발용 결과와 독립 검증·프로젝트 완료 상태도 그대로 유지합니다.
