# AI 감사 후 구현 수정과 기하 실험

2026-10-14 코드 감사에서 재현한 GUI 상태, 의미 분할 입력 계약, 전처리 경계 입력, pitch 진단의 구현 문제를 수정했다. 기본 detector·pitch·width·feature 조건과 frozen `natural_auto_04` / `boundaryblend_02` 수학은 유지한다.

## 기본 경로의 수정

- GUI는 새 사진 선택 또는 새 처리 요청 시 이전 결과·미리보기·저장 가능 상태를 무효화한다. 완료와 오류 응답은 요청 generation에 연결하여 오래된 응답을 무시한다. 한 창의 subprocess 작업은 순차 실행해 큰 모델 추론이 겹치지 않게 한다. 파일 선택 취소는 현재 결과를 유지한다.
- `photo_coarse_adapter_v2`는 cache의 `coordinate_system=encoded_original_pixels`, `body_classes=[1,2]`, `tip_class=2`, `minimum_votes=2`를 명시 확인한다. source/mask hash·shape 검증도 유지한다. 해당 계약이 누락된 외부 cache를 암묵적으로 채택하지 않는다.
- `colfispoof_raw_semantics.prepare()`는 RGB uint8과 양의 정수 target을 확인하고, resize의 짧은 변이 0으로 반올림되는 aspect ratio를 `unsupported_preprocessing_aspect_ratio`로 거절한다. 정상 크기의 rounding·padding·upstream positional resize 의미는 바꾸지 않는다.
- quality gate는 실제 `two_scale_measurement`의 `scales[].selection.status`를 읽는다. 불안정한 관측은 `pitch_unstable`로 분류한다. 결과에 `quality_gate_version=photo_quality_gate_v2`를 추가한다. 이는 진단 수정이며 적용 조건이나 반환 pixel을 완화하지 않는다. 해당 증거가 있는 새 입력의 reason/signature는 과거와 달라질 수 있다.

변경한 producer/consumer 계약, 늦은 GUI 결과와 source 변경, 잘못된 cache, resize 이전 거절은 합성 회귀로 검증한다. 과거 Linux reference와 실패 기록은 보존한다.

## 별도 기하 관측 버전

`photo_region_scale_plan_v1.plan_region_scales(coarse_mask)`는 native boolean mask의 각 connected component에 대해 직경과 resource plan을 독립 계산한다. 작은 조각의 거절이 다른 component의 scale을 바꾸지 않는다. 모든 조각을 metadata에 유지하며 area filtering이나 mask cleanup을 하지 않는다. 기존 400px 정규화 목표와 resize resource limits를 재사용한다. 각 plan은 전체 working image에 대한 계획이고, 실제 memory peak 보장이 아니다.

`contactless_finger_width_axis_v1.estimate_finger_width_axis(rgb, square_roi, axis_yx)`는 호출자가 제공한 현재 영상 좌표의 손가락 축에 수직인 단면으로 skin interval을 관측한다. 기존 색·폭·행 수·IQR 조건을 사용한다. axis는 유한한 0이 아닌 y/x vector여야 하며, encoded/EXIF/working 좌표 변환은 호출자의 명시 계약이다.

합성 검증은 고정 큰 mask에 tiny fragments를 추가하는 불변성, 경계에 닿는 mask의 유한 직경, 90도 회전과 대각선 손가락 폭, 입력 보존과 invalid axis를 포함한다. 단독 관측 함수는 renderer·structure guard·GUI 기본 경로에 연결하지 않았다. 기본 v2의 global scale 문제와 기존 width gate의 방향 의존성은 이 별도 구현만으로 해결 완료가 되지 않는다.

두 기능의 다음 단계는 candidate association·좌표 연결·region별 실행/composite 계약을 별도 adapter로 검증하는 것이다. 합성 불변성을 고정한 뒤 독립 development 자료로 평가한다. 이미 사용한 holdout이나 a/b 사진에 맞춘 threshold 조정은 하지 않는다.

## 계속 남는 알고리즘 과제

a와 같은 visible ridge undercoverage, b와 같은 feature gate 보류, 새 사진의 pitch 관측률과 RGBA contract는 별도 과제다. `success`는 탐지한 후보의 처리 상태이며 전체 지문 보호를 뜻하지 않는다. PHOTO detector/production 승인과 최종 독립 보호 검증은 false를 유지한다.

제공된 10-case의 outcome/region/native RGB parity와 기하 실험의 합성 불변성은 다른 검증이다. raw Linux TF tensor 비교나 matcher score 동등성으로 확대 해석하지 않는다.

## 검증 결과

수정 후 core 테스트 168개를 실행해 165개가 통과하고 선택적 Torch 3개가 skip됐다. GUI 회귀 9개와 Python 116개 syntax 검사도 통과했다. 제공된 holdout 8개, development_success, scanner_reference를 새 출력에서 순차 실행해 outcome·region signature·native RGB 모두 exact PASS, 최대 오차 0을 확인했다.

실제 renderer와 SourceAFIS를 사용한 a/b의 source-bound cached-semantics 재현도 기존 GUI 반환 RGB와 일치했다. 이 a/b 재현은 새 TensorFlow 추론이 아니며, a의 보호 범위와 b의 보류 조건은 유지됐다. 408개 source/input/reference/model/원본·저장본 hash를 실행 전후 비교해 보존을 확인했다.

새 GUI의 실제 CLI를 사용한 자동 smoke에서도 PHOTO success, PHOTO rejected, scanner success의 선택·미리보기·저장을 확인했다. 각 저장본은 대응 CLI와 byte-identical이고 Linux reference와 RGB-identical이었다. dialog와 작업 scheduling을 자동화한 검사이며, 사람이 새 GUI를 수동 조작한 검증과 구분한다.
