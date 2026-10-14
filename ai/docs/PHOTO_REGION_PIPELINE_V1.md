# PHOTO 영역별 geometry adapter 실험

`photo_region_pipeline_v1`은 영역별 scale과 손가락 축의 폭 관측을 기존 pitch 검사·frozen renderer·구조 검사·원본 좌표 합성까지 연결한 **opt-in 실험**이다. unified API/GUI의 기본 PHOTO adapter는 v2를 유지한다. 이 실험은 기존 성공 사례도 거절하므로 기본 경로로 채택하지 않는다.

## 연결 계약

1. RGB/L 입력을 encoded 원본 좌표로 읽고 EXIF 1~8을 검증한다. RGBA는 암묵적으로 변환하지 않는다.
2. 기존 COLFISPOOF worker 또는 source/mask hash·shape·class·좌표 계약을 검증한 cache를 사용한다. 모델, 네 회전, consensus, distal detector의 조건은 변경하지 않는다.
3. native coarse mask의 각 connected component를 독립 계획한다. 작은 조각도 기록하며 자원 한계로 거절한 조각은 다른 영역의 배율에 영향을 주지 않는다. crop 대체, scale clamp, mask cleanup은 없다.
4. coarse component 전체가 정확히 하나의 estimator native mask에 속할 때만 축을 연결한다. watershed 후보들은 같은 body ID를 가질 수 있으므로 estimator 목록의 고유 index를 사용한다. 겹치는 부모·연결 불능은 거절한다.
5. estimator resize의 실제 반올림한 높이·폭 비율을 역변환하고, EXIF 방향과 실제 working resize 비율을 축에 적용한다. pitch는 기존 working seed 관측을 사용하고 nominal scale로 native 단위를 기록한다. working/native/512 canonical 단위를 구분한다.
6. working raster와 square padding의 자원 계획을 검사한다. 각 영역은 순차 실행하며 같은 원본 RGB를 renderer에 전달한다. 이전 영역의 변환 결과를 다음 영역의 관측 입력으로 사용하지 않는다.
7. 기존 renderer binding의 공유 `RLock` 안에서 structure checker의 폭 관측 함수만 축 관측으로 잠시 연결한다. 예외에도 기존 binding을 복구한다. frozen 파일과 renderer·feature 판정 수학은 유지하지만 **관측 입력과 canonical size는 달라질 수 있다**.
8. structure guard가 통과하고 candidate ID/shape/dtype/exterior 계약이 맞을 때만 해당 native mask에 합성한다. 거절 영역과 전체 mask 밖의 RGB는 보존한다.

기존 adapter의 EXIF 좌우 반전 구현에는 `Image.Transpose.FLIP_LEFT_RIGHT == 0`을 False로 판정해 생략하는 구현 버그가 있었다. v1/v2의 조건을 `method is not None`으로 수정했다. 이것이 이번 기본 경로의 변경이다. round-trip만으로는 생략을 잡지 못하므로 8가지 기대 픽셀 위치를 비교하는 회귀를 추가했다. 기존 renderer 수학은 바꾸지 않았다.

## 실행

기존 설치 안내대로 core/worker/SourceAFIS 환경을 준비한 뒤 별도 CLI를 실행한다. 최신 source에서 실행하고 기존 legacy exe를 사용하지 않는다.

```powershell
& $env:BLURFING_CORE_PYTHON ai/scripts/photo_region_pipeline_v1.py `
  --input 'C:\private\photo.jpg' --output 'C:\private\new-experiment'
```

`--photo-semantics`로 검증할 cache directory를 지정할 수 있다. 생략하면 process-local `BLURFING_COLFISPOOF_PYTHON/SOURCE/MODEL`로 기존 worker를 실행하며 timeout 300초를 유지한다. `--detect-only`, strength 0 또는 0.5만 지원한다. fresh output에 returned PNG, native masks, result JSON을 쓴다. CLI stdout은 JSON이고 native/Java progress는 stderr로 보낸다. 이 CLI는 PHOTO 전용이며 scanner/UNKNOWN은 원본을 반환하고 명시 거절한다.

## 2026-10-14 Windows 검증

- core 181개 실행: **178 PASS / optional Torch 3 SKIP**. GUI 회귀 9 PASS, AI Python 118개 syntax PASS.
- 합성 좌표 검사는 8가지 EXIF의 실제 픽셀 위치·native 합성, 비대칭 크기/위치, resize 축 변환, watershed parent 모호성, 작은 조각의 자원 거절과 다른 영역 보존을 포함한다.
- 공유 lock에서 observer 복구·대기 중 기본 adapter와의 격리·예외 복구, 구조 검사 없는 applied flag의 거절, invalid cache/RGBA/fresh output 계약을 확인했다. 합성 compositor stub 결과는 실제 보호 성공률로 계산하지 않는다.
- 기본 경로 10개 사례(holdout 8, development success, scanner reference)를 기존 source-bound cache와 실제 renderer/해당 matcher로 재실행했다. 상태·영역 서명·native RGB 모두 exact, 최대 RGB 오차 0. **이번 재실행은 새 TensorFlow 추론이 아니다.** 이전 fresh worker matrix 결과는 기존 감사 수정 기록을 따른다.
- 실험 CLI의 실제 renderer에 a/b 및 development success를 연결했다. 입력 경로는 3개지만 a와 development success는 decoded RGB가 같으므로 **고유 영상 2개**의 개발 진단이다. 독립 validation이 아니다. 실험 반환은 모두 원본이었다.

| 사례 | 실험 결과 | 근거 |
|---|---|---|
| a / development success | `original_width_unavailable` | 7단면 중 유효 4개. 나머지 3개는 skin interval이 sampling/image 경계에 닿아 기존 조건으로 제외. 필요한 5개 미달. 구조 특징점 추출은 실행하지 않음 |
| b | `insufficient_features` | 폭 413 working px 관측. canonical size 246에서 실제 SourceAFIS 특징점 12→6, 양쪽 최소 10 조건 미달 |

기본 경로의 a/development 성공과 b 거절은 유지됐다. 실험 a의 거절을 개선으로 주장하지 않는다. b의 이전 13→6, size 241과 새 12→6, size 246은 폭 관측 변경에 따른 서로 다른 실험 조건이다. 원본·Linux reference·모델·기존 미커밋 data 작업은 보존했다.

## 다음 조사와 채택 조건

축 좌표 연결이 맞아도 RGB skin interval이 배경·경계에 연결되면 폭 관측을 잃을 수 있다. 다음 개발 후보는 **검증한 finger-body mask와 RGB 관측의 association을 이용한 폭 evidence**다. sample별 gate 완화, 배경을 임의 제거하는 우회, a에 맞춘 row/threshold 변경은 하지 않는다. 합성 배경/회전/손가락 잘림 및 별도 development 자료에서 기존 조건·mask 신뢰도·실패 조건을 비교해야 한다.

다중 실제 pad의 순차 처리, 새 adapter의 Linux/Windows parity, 성공 renderer 경로의 실제 영상 재현은 아직 확인하지 않았다. 현재 per-region 자원 계획은 전체 이미지 resize와 padding을 제한하며 전체 process RSS, 원본 decode, TensorFlow 메모리의 상한을 보장하지 않는다. lock 격리는 해당 adapter를 사용하는 호출에 적용되며 lock 없이 직접 frozen API를 동시에 호출하는 경우는 지원하지 않는다. 별도 CLI process 실행을 권장한다.

mask undercoverage, feature gate 목적, pitch 관측률, RGBA 제품 입력 계약, 새 독립 평가와 최신 unified exe/backend/Android 연동은 별도 과제다. `PHOTO_DETECTOR_APPROVED=false`, `PHOTO_PROTECTION_PRODUCTION_READY=false`, `FINAL_INDEPENDENT_VALIDATION_COMPLETE=false`, `PROJECT_COMPLETE=false`를 유지한다.
