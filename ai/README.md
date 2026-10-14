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
Linux는 개발 사진의 fail-closed 처리·반환 RGB·반복 실행·scanner 회귀를 검증했습니다. Windows는 NBIS/SourceAFIS 실행 환경 검증과 제공된 10-case PHOTO/scanner exact parity 및 실제 unified GUI smoke를 완료했습니다. 검증 범위와 미검증 항목은 [검증 기록](docs/VALIDATION.md) 및 [Windows parity 기록](docs/WINDOWS_PARITY_COMPATIBILITY.md)을 따릅니다. 개발·동등성 검증을 독립 보호 성능 승인으로 간주하지 않습니다.

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

## Experimental automatic detection artifact
The new automatic boundary prototype is **not ready for unattended protection**. The 20-image baseline reproduced 17 candidates and one accepted boundary; new graph-cut masks are review-gated. [Detection contract, CLI, tests and limitations](docs/DETECTION_PIPELINE.md) and [results](results/linux_detection_validation_summary.md) distinguish the 20-image diagnostics from the successful existing-baseline artifact control.

Public-source smoke test: `python ai/scripts/test_detection_artifact.py`. Actual private-data detector/consumer and benchmark commands are in the detection guide. Windows consumers must use the identical source bytes, EXIF-transposed dimensions, decoded RGB and mask hashes. This artifact work does not change existing Windows runtime verification claims or establish Windows full equivalence.

## Linux SAM-to-pad development path

See [SAM_PAD_PIPELINE.md](docs/SAM_PAD_PIPELINE.md) for native-coordinate private-mask input, extraction, evaluation and detector-only benchmark commands. This experimental path is not approved for protection use.

## Unified photo/scanner front-end (experimental)

Use `scripts/protect_fingerprint.py --input /path/to/image --output /path/to/new-result`. Content routes to PHOTO, FINGERPRINT_IMAGE or UNKNOWN; failures return unchanged pixels. Scanner detection is development-validated on 21 fixtures with structure-guarded scanner transformation. The configured COLFISPOOF body/distal PHOTO branch now has a fail-closed quality gate and partial-success response; it remains detector/production-unapproved. MediaPipe/SAM and legacy are optional, not primary. [Architecture and setup](docs/UNIFIED_FINGERPRINT_FRONTEND.md), [measured validation](results/unified_frontend_validation.md). No general protection or final-independent-validation claim.

## Raw COLFISPOOF pretrained PHOTO evaluation

[실행 방법](docs/COLFISPOOF_RAW_EVALUATION.md)과 [GT7 결과](results/colfispoof_raw_gt7_summary.md)를 공개합니다. 공식 DeepLab fingertip class 2를 네 회전으로 추론하고 고정 2/4 consensus를 평가했습니다. 공식 contour/crop 후처리는 호출하지 않습니다. 실제 손끝 선택은 일부 개선됐지만 macro IoU 0.4973, coverage 7/10으로 자동 보호 승인 기준을 충족하지 못했습니다. PHOTO 기본 경로에 연결하지 않았으며 GT7은 개발 평가용입니다. 모델·사진·GT·overlay는 포함하지 않습니다.

[Class 1+2 finger-body distal 실험](docs/FINGER_BODY_DISTAL.md)은 class 2가 없는 초근접 입력에서도 후보를 생성합니다. GT7에서 macro IoU 0.7529, coverage 10/10을 기록했지만, 목표 IoU 0.85와 경계 정밀도를 충족하지 못해 자동 보호 frontend로 승인하지 않았습니다. Ridge 검사는 별도 진단이며 기존 renderer·scanner·legacy 경로는 유지합니다.

[PHOTO pad refinement 학습 준비](docs/PAD_REFINEMENT_TRAINING.md): 지정된 10개 annotation을 검증하고 coarse-guided crop 27개와 source 단위 5-fold 학습 코드를 준비했습니다. 학습과 최종 평가는 완료됐으나 GT7 IoU 0.4149, coverage 3/10으로 회귀하여 모델을 거절했습니다. 기본 inference에는 사용하지 않습니다.

[Refinement 최종 학습·GT7 결과](results/pad_refinement_final_summary.md): pretrained encoder 확보 후 고정 5-fold와 최종 13 epoch 학습을 완료했습니다. GT7 macro IoU 0.4149, coverage 3/10으로 coarse baseline보다 나빠져 모델을 채택하지 않았습니다. 보호 변환에는 연결하지 않았으며 GT7을 보고 설정을 바꾸거나 재학습하지 않았습니다.

## Experimental coarse PHOTO integration

The unapproved COLFISPOOF body/distal path can be exercised explicitly with
`protect_photo_coarse_experimental.py`; it does not replace the default API.
See [PHOTO_COARSE_EXPERIMENTAL.md](docs/PHOTO_COARSE_EXPERIMENTAL.md) for
source-bound private semantic caches, native-coordinate compositing, runtime
preparation and the complete 10-run benchmark. Detector and production approval
remain false; the rejected refinement model is not used.

An additional opt-in [external observed pitch v1 experiment](docs/PHOTO_EXTERNAL_PITCH_V1.md)
provides a versioned ACF/FFT evidence contract. It preserves frozen v4 and uses
an unchanged lower-level renderer; its output is not equivalent to the frozen
natural_auto_04/boundaryblend_02 baseline. Production approval remains false.

## Unified fail-closed development system

[현재 구조·quality gate·독립 평가 준비·GUI·완료 제한](docs/FAIL_CLOSED_SYSTEM.md)을 참고하세요.
`protect_image()`와 공통 CLI는 자동 routing 후 success/partial_success/rejected를 반환합니다.
독립 촬영본 검증과 실제 Windows equivalence는 미완료이며 PROJECT_COMPLETE=false입니다.

### PHOTO adapter memory safety

The unified PHOTO path now uses `photo_coarse_adapter_v2` with deterministic pre-allocation bounds. Pathological working-image requests return unchanged RGB and `adapter_memory_limit_exceeded`; no detector/pitch/feature threshold or frozen renderer formula is changed. Historical independent reports stay frozen. See [memory safety contract](docs/PHOTO_ADAPTER_MEMORY_SAFETY.md) and [post-holdout operational validation](results/post_holdout_adapter_safety_summary.md). This safety fix does not approve PHOTO detection or production protection.
