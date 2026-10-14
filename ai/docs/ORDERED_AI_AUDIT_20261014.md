# 순서별 AI 후속 감사 완료

후속 후보 ID/full-body 보존은 [PHOTO_CANDIDATE_CONTEXT_V1.md](PHOTO_CANDIDATE_CONTEXT_V1.md)의 opt-in v3로 구현·검증했다. 아래 수치와 당시 다음 과제는 역사적 기록이며 현재 남은 과제는 새 문서를 따른다.

후속 body-mask-associated width 개발은 [PHOTO_BODY_WIDTH_V1.md](PHOTO_BODY_WIDTH_V1.md)를 따른다. opt-in v2와 계약 회귀·실제 개발 진단을 완료했으며 아래 audit 시점의 다음 후보가 구현됐다. 현재 다음 개발 대상은 union 전에 estimator candidate ID와 full body 범위를 보존하는 연결이다. 이 문서의 수치는 기존 audit 실행 기록으로 보존한다.

2026-10-14에 scale/component → 보호 범위 → feature gate → pitch 순서로 현재 기본 PHOTO 경로와 별도 region adapter를 점검했다. 확정한 구현 오류를 수정하고 각 단계의 계약을 회귀·실제 개발 사례로 확인한 뒤 다음 단계로 진행했다. 이 완료는 지정한 호출 경로의 코드 감사와 재현 범위이며 모든 알고리즘의 수학적 정확성·독립 보호 성능 승인을 뜻하지 않는다.

## 1. Scale/component

**HIGH — 기본 경로의 통계적 결합은 남아 있다.** `photo_coarse_adapter_v2.adapt()`는 모든 coarse connected component의 최대 내부 직경 중앙값으로 공통 scale을 정한다. 고정 200px 직경의 큰 pad에 1px 조각을 추가한 합성 입력에서 조각 0/1/2개일 때 scale은 2 / 약3.96 / 200이었다. 2개 이상에서는 기존 사전 자원 검사가 큰 resize를 거절한다. 자원 검사가 실행을 안전하게 거절하는 것과 scale 추정의 타당성은 다르다.

별도 `photo_region_scale_plan_v1`과 `photo_region_pipeline_v1`은 같은 큰 pad의 scale=2를 유지하고 조각별 자원 계획을 독립 계산한다. estimator parent가 정확히 하나일 때 축을 연결하며 body ID와 watershed 후보 ID를 혼동하지 않는다. 합성 noise 불변성, 모호한 parent 거절, EXIF/실제 resize 비율 변환, native 합성 및 binding 복구를 검증했다.

실험에서는 실제 a/development의 RGB 폭 관측이 유효 단면4/필요5로 거절되고 b도 특징점 검사에 미달한다. a와 development는 같은 decoded RGB라 고유 영상2개다. 이 경로는 기본 API/GUI에 채택하지 않았다. **다음 개발 후보는 검증한 finger-body mask와 RGB 폭 evidence의 association**이며 별도 개발 자료·배경·회전·잘림 조건에서 비교할 필요가 있다. 임의 area threshold와 consumed holdout tuning은 하지 않았다.

## 2. 보호 범위

**MEDIUM — 마지막 완전한 widening window 누락을 수정했다.** `component_pad()`의 반복 범위를 `range(N-K+1)`로 고쳐 마지막 시작 `N-K`를 포함한다. 기존 코드에서는 마지막 K개에서만 폭 증가 조건을 만족하면 해당 구간을 검사하지 않았다.

합성 body120x160의 마지막6행만 넓어지는 입력에서 extent가119→114.5로 줄었다. 시작 행114는 유지되고 그 뒤5행은 pad에서 제외된다. 정확히6행/7행의 widening, 미완성5행의 거절, native body 밖 픽셀0, class2 tip 보존, `estimate()` 연결, inverse quarter-turn 동일 mask를 검증했다. 기존 1.35/1.45, working512, class/voting/width 조건은 바꾸지 않았다.

기본10-case와 실제 renderer/SourceAFIS의 a/b 재실행은 이전 mask·상태·반환 RGB와 일치했다. 따라서 이 bug가 a의 보호 범위 부족이나 b의 거절 원인이었다는 증거는 없다. 이전 EXIF 좌우 반전값0 생략 수정도 유지한다.

**EXPECTED_LIMITATION — 후보 mask와 visible ridge coverage는 다르다.** 현재 detector는 geometry와 semantic tip을 사용하며 visible ridge 전체의 GT 경계를 검출한다고 주장하지 않는다. a의 mask가 finger-body 면적의53.21%였다는 값은 지문 보호율이 아니다. `boundaryblend_02`도 transition에서 원본 detail을 의도적으로 유지한다. 현재 성공 상태는 탐지한 후보의 처리 상태이므로 전체 지문 보호를 뜻하지 않는다.

후속 coverage 개선은 별도 development annotation과 원본/최종 RGB 평가가 필요하다. a에 맞춰 extent나 blend 수학을 조정하지 않았다.

## 3. Feature gate

**현재 유효 입력 계약에서 산술/연결 오류는 재현되지 않았다.** 기준은 양쪽≥10 특징점, 같은 좌표·종류의 1:1 Dice≤0.9, 추가+제거≥2, skeleton XOR/union≥0.05다. 이는 functional prototype gate이며 재식별 matcher 점수 또는 privacy 판정이 아니다.

추가 회귀8개로 특징점0/6/9 거절, 동일 특징점 거절, count/Dice/skeleton 경계, 특징점 순서/1:1 대응, canonical6px 거리, point type, NaN skeleton fraction 거절을 확인했다. synthetic extractor가 Modified→Original 역순으로 반환해도 image key로 original13/modified6과512px 좌표가 올바르게 연결된다. 이 synthetic extractor 결과는 실제 보호 성능으로 계산하지 않는다.

실제 기본 b도 SourceAFIS13→6, canonical size241, skeleton 변화 약0.97581이었으며 최소 count에서 거절됐다. real template에서 가져온 원본/변환본 point 수와 canonical 좌표 범위를 확인했다. 새 region 실험의12→6, size246은 폭 관측이 달라진 별도 조건이다.

**EXPECTED_LIMITATION — 변환본에도 최소 특징점 수를 요구하는 목적은 재검토할 여지가 있다.** 원본 평가 가능성, candidate 생성 유효성, 구조 변화 관측, 독립 재식별 평가를 분리하는 결과 계약을 제안한다. feature0 또는 점수0을 자동 보호 성공으로 해석하거나 gate를 완화하지 않았다. gate 내부 helper의 임의 잘못된 외부 feature payload까지 완전히 검증했다는 주장은 하지 않는다.

## 4. Pitch

**검사한 계약에서 단위 swap 오류는 재현되지 않았다.** source(encoded) → EXIF upright → working seed →512 observer → caller working pitch → source pitch의 단위를 구분한다. `observed_seed_pitch()`는 관측512 pitch에 `seed_side/512`를 곱하고 adapter는 nominal working scale로 native 값을 기록한다. 새 region adapter의 축 변환은 반올림한 높이/폭의 실제 비율을 사용한다. 기본/native scalar pitch는 nominal uniform scale 기준이며 physical DPI는 알 수 없다.

추가 회귀3개에서 seed side256/512/768, caller period8/16/24가 모두 normalized period16과 caller 단위 관측으로 연결됐다. ACF period6/10/16/22의 회전을 확인했고 지원 band 밖 period30/40과 빈 support에는 기본 pitch를 생성하지 않았다. 기존 nested two-scale producer→consumer 진단 회귀도 유지됐다.

기존 private pitch 거절13개 진단을 현재 결과의 source hash·region mask hash와 대조하여 같은 입력/영역임을 확인했다. 해당 측정 자체는 과거 실행이며 새 관측으로 승격하지 않는다. 일부는 ROI/coherence/periodic patch 부족이고 native-equivalent seed가 약2.205px인 경우도 있었다. 단순히 사진 전체 품질이 나쁘거나 threshold 하나가 잘못됐다고 단정할 근거는 없다.

**EXPECTED_LIMITATION — seed 선택·해상도·유효 patch·주기 band의 결합**이 사용성 과제다. 별도 development에서 native/working 지원 해상도를 명시하고 multi-resolution evidence를 비교하는 것이 후속 후보다. default pitch 생성, silent clamp, holdout에 맞춘 band 조정은 하지 않았다. ACF와 같은 profile을 쓰는 FFT 실험을 독립 생체 증거로 해석하지 않는다.

## 최종 검증과 상태

- core195 run: **192 PASS / optional Torch3 SKIP**. GUI 회귀9 PASS, AI Python120 syntax PASS.
- 현재 기본 경로10-case(holdout8, development success, scanner reference)의 상태/영역 서명/native RGB exact, 최대 RGB 오차0. actual a/b 기본 반환도 이전 검증 GUI와 exact.
- 실제 matcher가 필요한 경로에서는 실제 renderer/SourceAFIS를 실행했다. **이번 실행은 source-bound cached semantics이며 fresh TensorFlow inference가 아니다.** raw Linux TF tensor parity나 matcher score parity를 추가 입증하지 않았다.
- 별도 region 실험3입력 경로의 반환은 여전히 원본이다. 독립 영상은2개이며 보호 성능 개선이나 기본 채택 근거가 아니다.
- 실행 완료 시 tracked source/기존 저장소/private 입력/reference/model/cache/data 작업862개 hash 보존. source 수정은 실행 전에 의도한 detector fix였다. frozen renderer·structure gate·pitch source는 이전2c34888 Git blob과 byte-identical이다.

```ini
FOUR_STAGE_FOLLOWUP_AUDIT_COMPLETE=true_SCOPED_CALL_PATHS
DISTAL_TERMINAL_WINDOW_BUG_FIXED=true
DEFAULT_SCALE_COUPLING_REMAINS=true
EXPERIMENTAL_REGION_PIPELINE_DEFAULT_ENABLED=false
FEATURE_GATE_ARITHMETIC_BUG_REPRODUCED=false_WITH_VALID_PRODUCER_INPUTS
PITCH_UNIT_ERROR_REPRODUCED=false_WITHIN_TESTED_CONTRACTS
ALGORITHM_THRESHOLDS_UNCHANGED=true
FROZEN_RENDERER_AND_GATE_UNCHANGED=true
LINUX_REFERENCE_UNCHANGED=true
PRIVATE_INPUTS_UNCHANGED=true
PHOTO_DETECTOR_APPROVED=false
PHOTO_PROTECTION_PRODUCTION_READY=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```

현재 요청한 코드 감사·구현 오류 수정·단계별 검증은 완료했다. 다음 성능 개발 과제는 body-mask-associated width evidence, visible ridge coverage, feature gate 목적/결과 계약, pitch resolution/patch evidence이며 각각 독립 개발 계획이 필요하다. 새 실제 다중 pad 처리와 별도 adapter 플랫폼 비교, RGBA contract, 최신 unified exe 및 backend/Android 실제 연결도 남아 있다.
