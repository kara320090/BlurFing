# Windows 설치 및 실행

Windows 실행 환경 검증을 완료했습니다. NBIS 네이티브 빌드, 공식 NBIS 브리지 검증용 자료 확인 및 실제 SourceAFIS Windows 실행이 통과했습니다. WINDOWS_RUNTIME_VALIDATED=true이며, 제공된 10-case unified PHOTO/scanner matrix와 실제 GUI smoke는 exact parity 검증을 완료했습니다. windows_full_equivalence_verified=true의 범위는 해당 입력·설정 runtime이며 일반 입력이나 matcher score 동등성을 뜻하지 않습니다. [현재 parity 범위](WINDOWS_PARITY_COMPATIBILITY.md)를 확인하세요. 고정한 파라미터나 임계값을 조정하지 마세요. 실제 검사 범위는 [검증 기록](VALIDATION.md)을 확인하세요.

## 1. Python 및 가상 환경
Python >=3.10을 설치하고 PATH에서 python을 실행할 수 있도록 설정합니다. 저장소 최상위 디렉터리에서 PowerShell로 실행합니다.

```powershell
python --version
python -m venv ai/.venv
. ai/.venv/Scripts/Activate.ps1
python -m pip install -r ai/requirements.txt
python ai/scripts/reproduce_frozen_pipeline.py --check
```
소속 조직의 PowerShell 실행 정책을 따르세요. 이 스크립트는 실행 정책을 자동으로 변경하지 않습니다.

## 2. Java 및 SourceAFIS
JDK >=11과 docs/sourceafis_runtime.json에 명시된 JAR 15개를 준비합니다. SHA-256을 확인하고 비공개 SourceAFIS 폴더의 lib/ 아래에 배치합니다.

```powershell
java -version
javac -version
$env:BLURFING_SOURCEAFIS_HOME = 'C:/path/to/sourceafis'
```
JAR과 클래스 파일은 포함하지 않습니다. 필요한 경우 어댑터가 새 시스템 임시 폴더에서 공통 Java 소스를 컴파일합니다. Windows 클래스 경로 구분자는 세미콜론이고 Linux는 콜론입니다.

## 3. NBIS 네이티브 빌드
공식 NBIS 5.0.0 소스와 호환되는 MinGW-w64/MSYS gcc/g++/make 환경을 준비합니다. 공식 INSTALL_WINDOWS.txt를 읽으세요. NBIS 라이브러리와 브리지는 동일한 도구 체인 및 아키텍처를 사용해야 합니다. Linux 라이브러리나 관계없는 기존 MinGW 오브젝트를 링크하지 마세요.

```powershell
$env:MSYSTEM = 'MINGW64'
$env:CMAKE_POLICY_VERSION_MINIMUM = '3.5' # CMake 4.x에서 포함된 구형 OpenJPEG 프로젝트를 빌드하기 위한 설정.
$env:PATH = 'C:/msys64/mingw64/bin;C:/msys64/usr/bin;' + $env:PATH
& ai/platform/windows/build_nbis_windows.ps1 `
  -NbisSource 'C:/path/to/Rel_5.0.0' `
  -BuildDir 'C:/nbis_build_new' `
  -Bash 'C:/msys64/usr/bin/bash.exe' -Compiler 'C:/msys64/mingw64/bin/g++.exe'
```
위 CMAKE_POLICY_VERSION_MINIMUM 설정은 CMake 4.x에서 NBIS에 포함된 구형 OpenJPEG CMake 프로젝트를 빌드하기 위한 설정입니다.

BuildDir는 새 디렉터리여야 하며 공백이 없는 간단한 ASCII 드라이브 경로를 사용해야 합니다. 소스를 복사한 뒤 공식 --MSYS --64 설정, 구성, 헤더 복사, 라이브러리 및 실행 파일 빌드 명령을 수행합니다. 해당 구성에서 활성화한 PNG/OpenJPEG 헤더와 라이브러리도 포함합니다. 브리지는 -municode로 빌드하며 원본 NBIS 소스는 수정하지 않습니다. 기존 PNG/zlib 내보내기 대상에는 병렬 실행에 필요한 선행 조건이 없어 빌드를 순차 실행합니다. 네이티브 표준 출력·표준 오류는 로그 텍스트로 보존하고, 0이 아닌 종료 코드를 받으면 실행 환경 설정을 생성하기 전에 스크립트를 중단합니다. Windows에서 PowerShell 5.1 구문 및 표준 오류·종료 코드 처리를 검증했습니다. 자동 재시도나 공식 소스 수정은 수행하지 않습니다. 다른 새 빌드 디렉터리에서 다시 시작하기 전에 실패 로그를 조사하세요.

## 4. 실행 환경 설정 및 사전 요구사항
빌드가 성공하면 실제 exe 경로와 SHA-256을 담은 nbis_windows.runtime.json을 생성합니다. config/nbis_windows.example.json은 설정 예시일 뿐입니다.

```powershell
$env:BLURFING_NBIS_CONFIG = 'C:/path/to/nbis_windows.runtime.json'
& ai/platform/windows/setup_windows.ps1
python ai/scripts/check_platform_runtime.py --require-all
```
어댑터는 PE/x86-64 형식과 해시를 확인합니다. 도구 체인의 objdump -p로 의존성을 확인하고 필요한 MinGW 실행 DLL을 준비하세요. 빌드 성공만으로 실행 환경 검증이 완료되는 것은 아닙니다.

2026-10-12 네이티브 빌드는 private/nbis_build_win_20261012_03에 PE x86-64 브리지와 실행 환경 JSON을 생성했습니다. 브리지 SHA-256은 `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`입니다. 검증 프로세스 PATH에 C:/msys64/mingw64/bin을 지정한 상태에서 실제 RAW/MATCH 동작 검사와 설치·사전 요구사항 검사가 통과했습니다. Linux 대체 경로는 사용하지 않았습니다. MinGW DLL은 빌드 폴더에 포함하지 않았으며, 이 도구 체인 PATH 없이 수행하는 독립 설치는 시험하지 않았습니다.

## 5. 공개 검증용 자료 확인
공개 a011p_03.wsq, 참조 a011p_03.xyt 및 동일한 공식 빌드의 dwsq.exe를 준비합니다. 검증용 자료 파일은 포함하지 않습니다.

```powershell
python ai/platform/windows/validate_windows_runtime.py `
  --config $env:BLURFING_NBIS_CONFIG `
  --wsq 'C:/path/to/a011p_03.wsq' `
  --decoder 'C:/path/to/dwsq.exe' `
  --reference-xyt 'C:/path/to/a011p_03.xyt'
```
기대 결과는 336x512, 깊이 8비트, RAW 172032바이트, RAW 실행 결과 특징점 87행, 참조 XYT 바이트 일치, 동일 지문 매칭 결과 499 87 87입니다. 검증 도구는 임시 사본을 디코딩하고 종료 코드·표준 출력·표준 오류 및 입력·실행 파일 해시 보존 여부를 기록합니다. WINDOWS_BRIDGE_FIXTURE_VALIDATED는 브리지 검증용 자료 확인만 의미하며 전체 파이프라인이나 Windows 동등성을 의미하지 않습니다.

최종 검증 도구 감사 기록은 status=complete, WINDOWS_BRIDGE_FIXTURE_VALIDATED=true, raw_features=87, self_match="499 87 87", retry_count=0입니다. 브리지 SHA-256 `06e60cf815a7a99b38a63752487e0ee59f4016d49312dadb90f71b3d90fd7a26`을 기준으로 검증용 자료 SHA-256, 336x512·8비트 디코딩, RAW 172032바이트 및 참조 XYT 바이트 일치가 모두 통과했습니다. WINDOWS_NBIS_FIXTURE_VALIDATED=true는 앞서 기록한 검증용 자료 누락 결과를 대체합니다. 감사 기록은 windows_full_equivalence_verified=false를 유지하며, 이 결과는 Windows/Linux 전체 변환·평가 파이프라인을 검증하지 않습니다.

## 6. 변환

```powershell
python ai/scripts/transform_automatic_fingerprint_poc_v4_boundaryblend_02.py --input 'C:/path/to/input.jpg'
```
사용 동의를 받은 비공개 자료를 사용하고 공개 저장소에 추가하지 마세요. 결과는 새 시스템 임시 폴더에 저장합니다.

## 7. NBIS 평가
scripts/nbis_matcher.py의 run_nbis_job(images, pairs, run_name=...)을 기존 너비 정규화 원본 및 반환 RGB 영상과 함께 사용합니다. 매칭 쌍은 원본 자기 자신과 원본→변환본입니다. LINUX_SETUP.md의 API 계약을 따르고 새로운 잘라내기 기준이나 임계값을 만들지 마세요. insufficient_features 상태는 보호 성공과 별도로 처리합니다.

## 8. SourceAFIS 평가 및 전체 파이프라인 동등성
동일한 매칭 쌍으로 scripts/sourceafis_matcher.py의 run_matcher_job을 사용합니다. 매칭 엔진마다 점수 척도가 다르므로 원시 점수는 별도로 기록합니다. 실행 환경 검증은 네이티브 NBIS 빌드, 공식 브리지 검증용 자료 확인 및 실제 SourceAFIS 실행을 포함합니다. Windows/Linux 전체 파이프라인 동등성은 별도로 변환·평가 입력과 비교 기준의 일치, 실제 렌더링 변환의 마스크 밖 픽셀 보존, 개발용 관심 영역 결과 재현 및 남은 실패·시간 초과 상황을 확인해야 합니다. 해당 근거가 확보되기 전에는 windows_full_equivalence_verified=false를 유지합니다. 독립 최종 검증에는 새로운 사람·다른 날짜에 촬영한 개발 미사용 자료가 여전히 필요하며 FINAL_INDEPENDENT_VALIDATION_COMPLETE=false와 PROJECT_COMPLETE=false를 유지합니다.

2026-10-12 SourceAFIS 실행 검사는 합성 능선, 복제 이미지 및 잘못된 이미지를 사용했습니다. 실제 래퍼 컴파일·특징점 추출·매칭, 복제 이미지의 템플릿 캐시 재사용, 실패 상태 및 유니코드·공백 입력 경로를 확인했습니다. 개발용 관심 영역을 다시 실행한 결과나 보호 성능 검증은 아닙니다. Windows 네이티브 빌드 결과는 WINDOWS_CROSS_BUILD_SUCCESS=false를 변경하지 않습니다.

## Unified GUI and actual verification

Launch `python ai/app/windows/unified_gui.py` from the configured core environment. Configure BLURFING_COLFISPOOF_PYTHON, BLURFING_COLFISPOOF_SOURCE and BLURFING_COLFISPOOF_MODEL to Windows-local absolute paths and keep TensorFlow dependencies isolated. Runtime check is prerequisite inventory only. Run PHOTO and scanner on actual Windows, save JSON/returned images and compare with Linux before claiming equivalence. Existing frozen core and numeric settings must remain unchanged. See [FAIL_CLOSED_SYSTEM.md](FAIL_CLOSED_SYSTEM.md).

Actual single-case parity probe (reference files and input stay private):

```powershell
python ai/platform/windows/validate_unified_case.py --input /path/to/input.jpg --reference-json /path/to/linux/result.json --reference-image /path/to/linux/returned.png --output /path/to/fresh/windows-case
```

The probe verifies source identity, routed outcome/counts, region pixel-mask
signatures and returned pixels. It reports only CASE_EQUIVALENCE_PASS; one case
cannot set WINDOWS_FULL_EQUIVALENCE_VERIFIED=true. Use PHOTO success/partial/
rejected, UNKNOWN and scanner cases, including Unicode/space paths, and actual GUI
runtime operation before full equivalence claims. On Linux it reports NOT_RUN.

## 검증된 unified 실행 환경

공통 core는 `ai/requirements.txt`로 설치한 `ai/.venv`를 사용하고 모델 worker는 별도 Python 3.10 환경의 `platform/windows/requirements_colfispoof.txt`를 사용합니다. external source는 COLFISPOOF root 또는 `pre-processing`을 지정할 수 있습니다. 모델·upstream source는 수정하거나 bundle하지 않습니다. 경로를 환경변수로 설정한 뒤 `platform/windows/run_unified.ps1 -Gui`로 공통 CLI 기반 GUI를 실행합니다. [경로·의존성·검증 범위](WINDOWS_PARITY_COMPATIBILITY.md)를 확인하세요.
