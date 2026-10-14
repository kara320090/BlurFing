# PHOTO 후보 ID와 전체 body 보존 실험

`photo_region_pipeline_v3.py`는 기존 검출기가 만든 후보 ID, native pad, 전체 body context를 union 전에 보존하는 별도 실행 경로다. 기본 GUI/API와 region v1/v2는 유지한다. 후보 연결 오류를 해소했지만 보호 범위나 독립 보호 성능을 승인하지 않았다.

## 설계와 입력 계약

- `finger_body_distal_estimator.estimate(..., preserve_candidates=True)`에서 body component와 watershed part별 `body-NNNN-part-NNNN` ID를 부여한다. 이 ID는 동일 입력의 해당 실행 내 식별자이며 사진 간 해부학적 손가락 ID가 아니다.
- 각 후보의 full body는 기존 512 estimator partition을 NEAREST로 원본 encoded 좌표에 옮기고 관측한 native body와 교차한 것이다. 손가락의 실제 전체 해부학적 범위나 GT로 주장하지 않는다. 축소 과정에서 소실된 native body 픽셀을 채워 넣지 않는다.
- geometry가 거절한 후보에도 ID와 body를 남기되 pad를 만들지 않는다. geometry·class/voting·고정 파라미터는 유지한다. 기존 호출의 반환 keys/geometry와 optional context 호출의 pad union을 비교했다.
- 모든 후보 pad/body 계약과 union 동일성을 변환 전에 확인한다. 서로 접해도 분리 ID를 유지하고, 한 후보의 disconnected pieces는 같은 ID로 보존한다. largest-parent 선택이나 mask cleanup을 하지 않는다.
- pad 또는 body 소유 영역이 겹치면 관련 후보를 모두 명시 거절한다. 우선/마지막 후보에게 겹침을 배정하지 않는다. 독립 후보는 계속 실행할 수 있다.
- scale은 해당 후보의 전체 pad 안 최대 내부 직경으로 400px를 정규화한다. 다른 후보나 같은 후보의 작은 조각이 기존 최대 직경을 바꾸지 않으면 scale도 유지된다. 기존 resource gate와 scope/padding 검사를 적용하며 clamp·강제 downscale은 하지 않는다.
- 후보마다 같은 원본 RGB에서 변환한다. 이전 후보의 처리본을 다음 후보의 입력으로 사용하지 않는다. 구조 검사, renderer binding ID, shape/dtype/native exterior 계약을 확인한 뒤 해당 pad에만 합성한다. body는 해당 estimator partition을 직접 전달하므로 union 후 parent 추론이 필요 없다.
- 후보별 pad/body PNG를 직접 저장한다. union connected labels로 파일을 재구성하지 않는다. 원본 파일과 원본 RGB 배열 보존을 확인한다.

## 메모리와 기존 계약

optional body/pad retention에는 다음 후보의 native mask를 만들기 전에 2GiB 계획 한도를 검사한다. native plane과 working geometry buffer의 추정량이며 실제 전체 process RSS, decode, TensorFlow, Java 할당량 제한이 아니다. 초과 시 `candidate_context_memory_limit_exceeded`와 계획량을 기록하고 원본을 반환한다. 기본 estimator 호출에 이 추가 계획 검사를 적용하지 않았다.

RGB/L, EXIF1~8, strength0/0.5, 새 출력 폴더 계약을 유지한다. undefined EXIF는 worker 전에 정상 거절한다. RGBA 제품 정책은 미구현이다. body 폭 관측은 RGB 증거를 요구하고 실제 unpadded 영상 경계 안에서만 샘플링한다. renderer lock과 observer 복구를 재사용한다. frozen pitch·renderer·feature gate는 변경하지 않았다.

## 실행

설정된 기존 core/worker/SourceAFIS 환경에서 다음을 실행한다.

```powershell
& $env:BLURFING_CORE_PYTHON ai/scripts/photo_region_pipeline_v3.py `
  --input 'C:\private\photo.jpg' --output 'C:\private\new-candidate-result'
```

`--photo-semantics`는 source/hash/shape/class 계약을 검사하는 기존 cache 옵션이다. 생략하면 configured worker를 실행한다. 출력 schema는 `experimental-photo-candidates-v1`, quality version은 `photo_region_pipeline_v3_candidate_context_experimental`이다. `candidate_id`와 `renderer_binding_candidate_id`의 대응을 기록한다. renderer 내부의 `coarse-N`는 호환용 binding ID이며 union component ID가 아니다.

기존 `fingerprints_detected/transformed/rejected` 필드는 이 실험에서 geometry 거절까지 포함한 estimator 후보 수를 집계한다. `count_semantics`를 함께 읽어야 하며 실제 지문 개수나 보호 성공률로 해석하지 않는다. 노이즈 body 후보를 새로 보고하므로 이전 success가 partial_success로 바뀔 수 있다.

## 2026-10-14 검증

- 후보 context 회귀10개, v3 연결 회귀8개를 추가했다. touching IDs, fragmentation, overlap 모두 거절, 독립 후보 계속 처리, downsample/native subset, 거절 body 보존, 후보 메모리 사전 계획, EXIF8방향, 실제 frozen binding과 synthetic renderer 합성, feature/identity/guard/exterior 거절, observer 복구, 원본 RGB mutation 검출을 검증했다. 합성 renderer의 실행은 보호 성능 근거가 아니다.
- core230 run: **227 PASS / optional Torch3 SKIP**. GUI9 PASS, AI Python128 syntax PASS.
- 실제 개발 입력11경로에서 source-bound cache와 실제 renderer/필요한 SourceAFIS를 실행했다. 이미 소비한 PHOTO kit9경로 및 추가2경로이며 중복 영상이 있다. fresh TensorFlow 추론이나 새 independent holdout이 아니다.
- 이전 coarse union5개가 각기 두 parent를 포함하던 사례를 후보별로 연결했다. v3에서 parent ambiguity가 사라지고 pitch/feature/resource/geometry 검사 결과를 확인했다. 전 경로의 반환 RGB는 이전 v2와 exact였다. 처리 면적이나 보호 효과 증가를 주장하지 않는다.
- 대표 개발 영상의 변환 pad는 폭426/7단면/canonical238/특징점17→16을 유지했다. 추가 짧은 body 후보를 거절해 상태는 partial_success로 바뀌었다. 다른 개발 영상은 폭407/canonical250/14→7로 feature 거절을 유지했다. v2의 폭408/249/13→8과 다르며 body context의 native 경계 관측이 달라지는 별도 실험이다.
- 기본10-case의 상태/영역/native RGB exact, 최대오차0. 모든 v3 출력의 rejected pad와 union 밖 RGB를 보존했다. 최종 실행에서 source/input/reference/model/cache/기존 data896개 hash를 보존했다.
- 새 v3의 Linux 실행·플랫폼 동등성과 실제 다중 pad가 모두 변환되는 입력은 미검증이다.

## 다음 단계로 수행한 보호 범위·pitch 진단

6개 소비된 개발 입력에서 같은 기존 `ridge_evidence_frontend`를 body ROI의 max_side512/1024/2048에 적용했다. 원본과 detector mask를 수정하지 않았다. 각 해상도의 동일 body 관측 grid에서 pad 안/밖의 credible-window support를 구분했다. 이 window support는 실제 지문 ridge GT나 지문 보호율이 아니다.

개발 영상에서는 pad 밖에도 능선 후보가 관측됐고, 일부 입력은512에서 없어 보이던 관측이1024에서 나타났다. 반대로 해상도가 커질수록 관측이 줄기도 했다. 따라서 전체 사진 크기 또는 단일 관측 해상도만으로 pitch 거절과 범위 누락을 해결했다고 판단할 수 없다. 기존 fixed contrast/coherence/frequency 기준과 실제 frozen seed-pitch gate는 유지했다.

후속 설계는 다음과 같다.

1. **범위**: 별도 development annotation에 finger ID/full body/visible fingerprint pad/불확실 영역을 구분한다. 후보 ID를 유지한 상태에서 원본 해상도의 ridge evidence와 pad boundary 제안을 비교한다. 후보 mask를 임의 팽창하거나 개발 사례에 맞춰1.35/1.45를 조정하지 않는다. IoU뿐 아니라 실제 ridge 누락과 배경 침범, 반환 RGB의 잔존 detail을 검증한다.
2. **feature gate 목적**: 원본의 평가 가능성, candidate 생성/구조 변화, 재식별 측정을 분리하는 연구안을 평가한다. 원본 특징점이 충분하고 변환본이10개 미만이어도 이를 자동 성공으로 승격하지 않는다. 현재 거절 조건을 바꾸려면 제품/알고리즘 목적과 독립 평가 계약을 먼저 정해야 한다.
3. **pitch**: 동일 후보 ID와 source/working 단위로 native seed·여러 해상도·patch evidence를 기록하는 관측 실험을 설계한다. 관측이 실패하면 default pitch를 생성하지 않는다. 관측 범위 확대나 gate 완화는 별도 개발 자료에서 검증해야 한다.

현재 추가 annotation/새 독립 자료가 없으므로 범위 자동 확장이나 threshold 수정은 수행하지 않았다. 거절 결과는 현재 원본 지문을 그대로 남기므로 미보호 상태로 표시해야 한다.

```ini
CANDIDATE_ID_AND_FULL_BODY_CONTEXT_IMPLEMENTED=true_OPT_IN
CANDIDATE_CONTRACT_REVIEW_COMPLETE=true_WITHIN_TESTED_SCOPE
DEFAULT_PIPELINE_CHANGED=false
ALGORITHM_THRESHOLDS_UNCHANGED=true
FROZEN_RENDERER_AND_GATE_UNCHANGED=true
PRIVATE_INPUTS_AND_LINUX_REFERENCE_UNCHANGED=true
PHOTO_DETECTOR_APPROVED=false
PHOTO_PROTECTION_PRODUCTION_READY=false
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
PROJECT_COMPLETE=false
```
