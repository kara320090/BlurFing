# Body mask와 RGB 폭 관측 연결 실험

`contactless_finger_width_body_v1`과 `photo_region_pipeline_v2`를 opt-in 경로로 구현했다. 한 native connected body와 한 distal estimator parent를 연결하고, 손가락 축에 수직인 RGB 피부색 구간을 body mask 안으로 제한한다. 기본 GUI/API는 기존 PHOTO adapter를 유지한다. 실제 a에서 기존 region v1의 폭 관측 실패가 해소됐지만 검출 mask와 처리 면적은 그대로다.

## 버전과 설계 계약

| 경로 | 역할 | 기본 채택 |
|---|---|---|
| `protect_fingerprint.py` / `photo_coarse_adapter_v2` | 기존 unified PHOTO/scanner 실행 | 기존 경로 유지 |
| `photo_region_pipeline_v1.py` | 영역별 scale + axis RGB 폭 | opt-in |
| `photo_region_pipeline_v2.py` | 영역별 scale + axis body-associated RGB 폭 | opt-in |

새 폭 관측은 semantic mask만으로 폭을 만들어 내지 않는다. RGB saturation/R-G/value, 1x9 closing, ±90/30 단면, ±600 탐색, width160~900, 최소5개 단면, relative IQR≤0.25는 이전 실험 조건을 유지한다. body 단면 안의 center/±20 부근에 RGB evidence가 있어야 하고 그 연속 구간을 관측한다. 물리적 DPI나 실제 anatomical width는 승인하지 않는다.

native pad가 정확히 하나의 body component 안에 있고 해당 body에 하나의 valid estimator parent만 있을 때 연결한다. native body label과512 estimator body ID를 같은 ID로 가정하지 않는다. 여러 후보가 한 body에 붙으면 명시 거절한다. body/axis는 원본 encoded 좌표에서 EXIF와 실제 rounded resize 비율을 따라 working 좌표로 매핑한다. mask는 NEAREST로 옮기고 padding에는 false를 채운다.

**샘플링은 padding 이전의 실제 working 영상 크기로 제한한다.** RGB edge padding이나 semantic false padding을 실제 관측 경계로 오인하지 않는다. 단면이 실제 영상/탐색 경계에 닿으면 폭을 관측하지 않는다. 잘린 입력을 padding으로 통과시키는 조건은 없다.

shared renderer lock 안에서 관측 함수를 잠시 연결하고 예외에도 복구한다. frozen renderer·pitch·structure gate와 양쪽 최소10 특징점 기준은 유지한다. 폭 관측과 canonical size는 새 실험에서 달라질 수 있다. common API는 candidate ID/구조 검사/shape/dtype/native exterior 계약을 다시 확인한 뒤 적용 mask에만 합성한다.

## 실행

core/worker/SourceAFIS 환경은 기존 설치 안내를 따른다. 새 source를 사용한다.

```powershell
& $env:BLURFING_CORE_PYTHON ai/scripts/photo_region_pipeline_v2.py `
  --input 'C:\private\photo.jpg' --output 'C:\private\new-body-width-result'
```

`--photo-semantics`로 source/hash/shape/class 계약을 검증할 기존 cache를 지정할 수 있다. 생략하면 기존 configured worker를 실행한다. PHOTO RGB/L, strength0/0.5, fresh output 계약을 유지한다. scanner는 기존 unified 경로로 처리한다. result schema는 `experimental-photo-regions-v1`, quality version은 `photo_region_pipeline_v2_body_width_experimental`이다. 출력은 native RGB, EXIF, masks와 private diagnostic JSON이다.

## 발견하고 해결한 실행/경계 문제

확장 진단 중 한 RGB 입력의 EXIF orientation이0이었다. 이전 region v1은 이를 axis validation에서 `ValueError`로 종료했다. shared 경로는 이제 worker/renderer 전에 `invalid_source_exif_orientation`으로 정상 거절한다. source 파일·encoded RGB를 보존하고 returned PNG에는 encoded 픽셀 표시용 orientation1을 기록한다. source orientation/repr와 output orientation을 각각 metadata에 남긴다. 방향을 추측하여 변환하지 않는다. 기본 unified 경로의 기존 EXIF 동작은 바꾸지 않았다.

padding 검토에서는 semantic false padding이 잘린 원본 body의 끝을 관측 경계로 오인할 가능성을 발견했다. `image_shape`로 실제 unpadded 크기를 전달하고 그 안에서만 샘플링하게 했다. 정상 padding과 실제 frame-edge clipping을 별도 회귀로 확인했다. 초기 실패/중간 실행 기록은 local work에 보존하고 최종 검증은 새 출력에서 실행했다.

## 2026-10-14 결과와 범위

- body/color 회귀11개, v2 wiring 회귀6개: 피부색 배경 제한, 회전·대각선, RGB evidence 없는 mask 거절, 실제 clipping, padding clipping, RGB/body/axis 입력 보존, invalid 계약, disjoint/ambiguous body association, EXIF8방향 native composite, custom observer 예외 복구, undefined EXIF 정상 거절을 포함한다. wiring의 synthetic renderer는 실제 보호 성능으로 계산하지 않는다.
- 전체 core212 run: **209 PASS / optional Torch3 SKIP**. GUI9 PASS, AI Python124 syntax PASS.
- 기존 unified10-case의 상태/영역 서명/native RGB exact, 최대오차0. 실제 default a/b 결과도 이전 검증 RGB와 같다. 수정된 region v1의 a/b/development 결과도 이전 v1과 같다.
- 실제 region v1/v2 CLI를 a/b/development3경로에 연결했다. a와 development는 decoded RGB가 같아 고유 영상2개다. **source-bound cache와 실제 renderer/SourceAFIS 실행이며 fresh TensorFlow inference가 아니다.**

| 실제 개발 사례 | region v1 | region v2 body width |
|---|---|---|
| a 및 같은 RGB의 development | 유효 폭 단면4개, width unavailable, rejected | 단면7개·width426 working px·canonical238·SourceAFIS17→16, success |
| b | width413·canonical246·12→6, rejected | width408·canonical249·13→8, rejected |

v2 a의 반환 RGB는 기존 default a와 exact이며 변경 pixel3,857,780이다. b는 원본 반환이 유지된다. a의 탐지 mask/보호 범위를 늘리지 않았고 b의 특징점 gate를 우회하지 않았다. 단순 특징점 수 감소나 실행 success를 privacy/security proof로 해석하지 않는다.

## 다음 단계로 수행한 확장 진단

이미 소비한 kit PHOTO9개(기존 이름 holdout001~008, development)를 **개발 진단**으로 실행했다. 새로운 independent holdout으로 승격하지 않고 결과에 맞춘 튜닝은 하지 않았다. 모든 출력에서 rejected 영역과 전체 mask 밖 RGB 보존을 확인했다.

- kit004:2개 coarse component 중1개 applied,1개 resource rejected → partial success.
- development:1개 applied → success.
- 나머지7개:rejected. kit006은 invalid EXIF, kit005는 후보 없음.
- region 거절은 parent ambiguous5개, pitch unobserved6개, resource limit12개였다. 이 component 수는 실제 지문 개수나 독립 보호 성공률이 아니다.
- a/b와 기본 회귀 실행 완료 때865개 protected source/input/reference/model/cache/data hash를 보존했다. 확장 실행에서는 새 source를 포함한155개 hash를 보존했다. 두 집합은 중복되므로 합산하지 않는다.

parent 거절을 추가 진단했다. kit001은 coarse3개/valid estimator parent4개이고 각 coarse에 두 parent가 연결됐다. kit002는 coarse4개/valid parent5개이며 두 coarse가 모호했다. 해당 parent mask 쌍의 overlap은0이었다. **union 후 connected labeling이 접하거나 조각난 parent 정보를 섞는 정보 손실**이 다음 개발 대상이다. 현재 strict rejection은 계약에 맞게 동작한다. 다음 버전은 union 전에 candidate ID와 각 후보의 full body 범위를 보존하고, overlap/fragment/adjacency와 native composite 계약을 합성 검증해야 한다. 임의 fragments 제거나 가장 큰 parent 강제 선택은 하지 않는다.

## 남은 제한과 승인 상태

현재 body는 calibrated anatomical GT가 아닌 pretrained semantic evidence다. 잘못된 segmentation, fused fingers, 소실된 parent ID, pitch 미관측, resource limits는 계속 실패 원인이 될 수 있다. 새 observer는 RGB 구간을 body 안으로 제한하는 관측 실험이지 detector 정확도 개선이나 전체 지문 보호 보장이 아니다.

지원하지 않는 EXIF와 RGBA의 제품 decode 정책, 새 실제 다중 pad/독립 자료/새 adapter Linux·Windows 비교, visible ridge coverage, feature gate 목적, pitch 해상도, 최신 unified exe와 backend/Android 실제 연결은 별도 과제다. 원본/reference/model/threshold/frozen 수학을 보존했고 기본 채택을 하지 않았다.

```ini
BODY_ASSOCIATED_WIDTH_IMPLEMENTED=true_OPT_IN
BODY_WIDTH_AND_PIPELINE_CONTRACT_TESTS_PASSED=true_WITHIN_TESTED_SCOPE
UNDEFINED_EXIF_ERROR_HANDLED=true_NORMAL_REJECTION
PADDING_NOT_USED_AS_OBSERVED_FRAME=true
DEFAULT_PIPELINE_CHANGED=false
PHOTO_DETECTOR_APPROVED=false
PHOTO_PROTECTION_PRODUCTION_READY=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```
