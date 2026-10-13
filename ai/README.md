# AI

주담당: 유재윤

## 담당 범위
BlurFing 지문 변환 알고리즘 및 NBIS / SourceAFIS 기반 검증 파트.

## 고정 기준 구성
렌더러: natural_auto_04. 합성기: boundaryblend_02. 지문 매칭 엔진: NBIS 5.0.0 / SourceAFIS 3.18.1.
공통 알고리즘은 scripts/ 아래 한 벌입니다. 플랫폼별 차이는 실행 환경 경로, 프로세스, Java·네이티브 입출력 및 설치·빌드뿐입니다. 계산 파라미터와 구조 검사 기준은 유지합니다.

## 플랫폼 상태
| 구성 요소 | Linux | Windows |
|---|---|---|
| 핵심 변환 | 개발용 기준 구성 검증 완료 | 공통 구현, 실행 검증 대기 |
| natural_auto_04 | 검증 완료 | 동일한 공통 핵심 구현 사용 |
| boundaryblend_02 | 검증 완료 | 동일한 공통 핵심 구현 사용 |
| NBIS 어댑터 | 검증 완료 | 네이티브 빌드 및 공식 브리지 검증용 자료 확인 완료 |
| SourceAFIS | 검증 완료 | Windows 실제 실행 검증 완료 |
| 전체 파이프라인 | 개발용 파이프라인 검증 완료 | 실행 환경 검증 완료; Windows/Linux 전체 파이프라인 동등성 미검증 |

```text
TECHNICAL_PIPELINE_COMPLETE=true
LINUX_PIPELINE_VALIDATED=true
WINDOWS_IMPLEMENTATION_READY=true
WINDOWS_CROSS_COMPILER_AVAILABLE=false
WINDOWS_CROSS_BUILD_SUCCESS=false
WINDOWS_NBIS_NATIVE_BUILD_SUCCESS=true
WINDOWS_NBIS_FIXTURE_VALIDATED=true
WINDOWS_SOURCEAFIS_RUNTIME_VALIDATED=true
WINDOWS_RUNTIME_VALIDATED=true
windows_full_equivalence_verified=false
LINUX_REGRESSION_OK=true
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```
Linux 상태는 비공개 작업본의 기존 검증 근거에 따릅니다. LINUX_REGRESSION_OK는 구문·가져오기·설정·운영체제별 호출 분기 및 소스 보존 검사이며 Linux 네이티브 실행을 재검증한 결과가 아닙니다. Windows에서는 NBIS 네이티브 빌드, 공식 검증용 자료의 특징점 87개·참조 XYT 바이트 일치·동일 지문 매칭 결과 499 87 87, SourceAFIS 실제 실행을 확인하여 실행 환경 검증을 완료했습니다. Windows/Linux 전체 변환·평가 파이프라인 동등성은 별도 미검증이므로 windows_full_equivalence_verified=false를 유지합니다. 상세 범위는 [검증 기록](docs/VALIDATION.md)을 확인하세요.

## 저장소 구성
- scripts/: 공통 렌더러, 합성기, 관심 영역(ROI)·기하 및 이미지 보조 함수, 운영체제별 호출을 분기하는 매칭 인터페이스, 단일 Java 소스.
- platform/linux/: Linux 어댑터, 네이티브 소스, 설치 안내.
- platform/windows/: Windows 어댑터, 네이티브 소스, PowerShell 빌드·설치 스크립트, 검증용 자료 검사 도구.
- config/: 실행 환경 설정 JSON 예시. 실제 비공개 설정은 저장소 밖 또는 private/에 보관합니다.
- docs/: 설치, 파이프라인, 검증 및 제한사항.
- results/: 익명화한 Linux 개발용 검증 결과와 NBIS 새 빌드 요약.
- requirements.txt: 공통 Python 의존성 목록. NBIS/JDK/JAR은 외부 요구사항입니다.

## 설치 및 실행
[Linux 설치 안내](docs/LINUX_SETUP.md) / [Windows 설치 안내](docs/WINDOWS_SETUP.md)를 따르세요. Python >=3.10, Java/Javac >=11이 필요합니다. SourceAFIS JAR 15개는 docs/sourceafis_runtime.json의 공식 URL 및 SHA-256으로 별도 준비합니다. 실행 바이너리와 JAR은 포함하지 않습니다.

공통 호출:
```python
from nbis_matcher import run_nbis_job
from sourceafis_matcher import run_matcher_job
```
scripts를 Python 모듈 검색 경로에 두거나 문서의 명령줄 명령을 사용합니다. 공통 인터페이스는 운영체제를 자동 선택하며 지원하지 않는 운영체제에서는 오류를 냅니다. 평가 점수·임계값과 특징점 가지치기 설정은 바꾸지 않았습니다.

## 데이터 및 검증
실제 지문·손 사진, 개인 자료 목록, 체크포인트, 압축 자료, 데이터셋은 공개하지 않습니다. [검증 기록](docs/VALIDATION.md)은 기존 Linux 개발용 결과와 Windows 실행 환경 검증 범위를 구분합니다. Linux의 개발용 관심 영역 3개에서 두 매칭 엔진 모두 원본→변환본 점수가 동일 지문 매칭 점수보다 크게 낮았습니다. 이 수치를 Windows 결과로 승격하지 않습니다. 독립 검증용 보류 자료(holdout)의 결과는 없으며 B/D 자료를 독립 검증 자료로 승격하지 않습니다.

## 제한사항
일반적 보호 효과나 완전한 자연스러움을 입증하지 않습니다. 합성 지문 능선의 규칙성과 일부 질감 경계가 남고 Windows 전체 동등성도 미검증입니다. 특징점 추출 실패를 보호 성공으로 계산하지 않습니다. NBIS와 SourceAFIS의 점수 척도는 다르므로 직접 비교하지 않습니다.
