# AI

주담당: 유재윤

## 담당 범위
BlurFing 지문 변환 알고리즘 및 NBIS / SourceAFIS 기반 검증 파트.

## Frozen baseline
Renderer: natural_auto_04. Compositor: boundaryblend_02. Matchers: NBIS 5.0.0 / SourceAFIS 3.18.1.
공통 알고리즘은 scripts/ 아래 한 벌입니다. 플랫폼별 차이는 runtime path, process, Java/native I/O 및 setup/build뿐입니다. 계산 파라미터와 구조 검사 기준은 유지합니다.

## 플랫폼 상태
| Component | Linux | Windows |
|---|---|---|
| Core transform | 검증된 development baseline | 공통 구현, 실행 검증 대기 |
| natural_auto_04 | Validated | Same shared core |
| boundaryblend_02 | Validated | Same shared core |
| NBIS adapter | Validated | Implemented; runtime validation pending |
| SourceAFIS | Validated | Implemented; runtime validation pending |
| Full pipeline | Validated development pipeline | Windows validation pending |

```text
TECHNICAL_PIPELINE_COMPLETE=true
LINUX_PIPELINE_VALIDATED=true
WINDOWS_IMPLEMENTATION_READY=true
WINDOWS_CROSS_COMPILER_AVAILABLE=false
WINDOWS_CROSS_BUILD_SUCCESS=false
WINDOWS_RUNTIME_VALIDATED=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```
Linux status는 private 작업본의 기존 검증 근거입니다. 새 공개 구조의 Linux 회귀 검사는 syntax/import/config/dispatch로 제한됩니다. Windows는 Python 정적 검사를 통과한 구현이며 실제 build/runtime/full pipeline 검증이 아닙니다.

## Repository layout
- scripts/: 공통 renderer, compositor, ROI/geometry 및 image helpers; OS-dispatch matcher facades; 단일 Java source.
- platform/linux/: Linux adapters, native source, setup 안내.
- platform/windows/: Windows adapters, native source, PowerShell build/setup, fixture validator.
- config/: runtime example JSON; 실제 private config는 저장소 밖 또는 private/에 보관.
- docs/: setup, pipeline, validation 및 제한사항.
- results/: 익명 Linux development 결과와 NBIS clean rebuild 요약.
- requirements.txt: 실제 공통 Python dependencies. NBIS/JDK/JAR은 외부 요구사항입니다.

## 설치 및 실행
[Linux setup](docs/LINUX_SETUP.md) / [Windows setup](docs/WINDOWS_SETUP.md)을 따르세요. Python >=3.10, Java/Javac >=11이 필요합니다. SourceAFIS JAR 15개는 docs/sourceafis_runtime.json의 공식 URL 및 SHA-256으로 별도 준비합니다. runtime binary/JAR는 포함하지 않습니다.

공통 호출:
```python
from nbis_matcher import run_nbis_job
from sourceafis_matcher import run_matcher_job
```
`scripts`를 Python import path에 두거나 문서의 CLI 명령을 사용합니다. facades는 운영체제를 자동 선택하며 unsupported OS는 오류를 냅니다. 평가 score/threshold와 prune 설정은 바꾸지 않았습니다.

## 데이터 및 검증
실제 지문/손 사진, 개인 manifest, checkpoint, archive, dataset은 공개하지 않습니다. [validation](docs/VALIDATION.md)은 Linux development-only입니다. 세 development ROI에서 두 matcher 모두 original→transformed score가 self-match보다 크게 낮았습니다. 독립 holdout 결과는 없으며 B/D 자료를 승격하지 않습니다.

## 제한사항
일반적 보호 효과나 완전한 자연스러움을 입증하지 않습니다. synthetic ridge regularity와 texture seam이 일부 남고 Windows full equivalence도 미검증입니다. 특징점 추출 실패를 보호 성공으로 계산하지 않습니다. NBIS와 SourceAFIS score scale은 다르므로 직접 비교하지 않습니다.

## Experimental automatic detection artifact
The new automatic boundary prototype is **not ready for unattended protection**. The 20-image baseline reproduced 17 candidates and one accepted boundary; new graph-cut masks are review-gated. [Detection contract, CLI, tests and limitations](docs/DETECTION_PIPELINE.md) and [results](results/linux_detection_validation_summary.md) distinguish the 20-image diagnostics from the successful existing-baseline artifact control.

Public-source smoke test: `python ai/scripts/test_detection_artifact.py`. Actual private-data detector/consumer and benchmark commands are in the detection guide. Windows consumers must use the identical source bytes, EXIF-transposed dimensions, decoded RGB and mask hashes. This artifact work does not change existing Windows runtime verification claims or establish Windows full equivalence.
