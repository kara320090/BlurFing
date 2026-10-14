# 관측 경계 기반 pad 실험

`photo_observed_boundary_proposals_v1.py`는 [경계 진단](PHOTO_TERMINAL_CONTEXT_DIAGNOSTIC.md)의 fresh RGB 관측에서 별도 pad 후보를 만든다. 기본 CLI/API/GUI, frozen 보호 renderer에 연결하지 않는다. body/tip·기존 branch mask·원본 RGB를 수정하지 않는다. anatomy는 `unknown`, `approved_for_use=false`, `renderer_binding_allowed=false`다.

```python
from photo_observed_boundary_proposals_v1 import propose
result = propose(rgb, body, tip)  # 같은 encoded source의 uint8 RGB/Boolean masks
# result['mask']는 검토용이다. 보호 알고리즘으로 전달하지 않는다.
```

같은 source의 branch v2와 RGB 경계 evidence를 다시 계산하고 부모 mask의 hash를 확인한다. 경계가 미관측인 이웃을 포함한 **모든 eligible terminal context** 사이의 중복 픽셀을 먼저 unowned로 제외한다. 이어 관측된 candidate에만 native `M[1,0]*x + M[1,1]*y + M[1,2] <= selected_row`를 적용한다. M에 실제 rounded resize의 pixel-center 변환이 이미 포함되므로 `.5` 이동을 추가하거나 axial y를 round하지 않는다. 이는 선택된 constant axial-row transect이며 tilted crease의 fitted boundary가 아니다.

미관측 후보는 `mask=None`이다. 임의의 geometry fallback이나 default pitch를 만들지 않는다. class2 존재나 frame 접촉은 metadata이며 선택/해부학적 확정에 쓰지 않는다. 전체 native float 좌표 raster 대신 행 단위 임시 배열을 사용하고, 부모·후보 mask 보유량을 포함해 기존 메모리 한도를 검사한다. source/hash 보존·mask subset·배타적 ownership과 같은 계약을 검증한다.

평가는 training10장과 이전 fresh COLFISPOOF cache를 사용했다. 모델 재추론·독립 validation·GT7/소비한 holdout tuning은 수행하지 않았다. 코드·평가 규칙을 기록하고 추론/반복 검증을 완료한 뒤 source/hash로 검증된 인간 GT를 읽었다. 모든 aggregate는 **10장 전체 GT**를 유지한다. 동일한 관측 candidate-ID subset의 기존 부모 union과 새 proposal union을 비교하고, 전체55개 branch baseline도 별도로 보고한다. GT와 겹친 영역만 분모에 남겨 성능을 높이지 않는다. 빈 prediction의 precision은 `null`이며 정의된 이미지 수를 함께 표시한다.

후보별 GT component는 기존 parent의 최대 IoU로 대응시키는 evaluation-only 진단이다. 일대일 확정된 손가락 대응이 아니다. `selected_row - max(projected_GT_axial_y)`를 관측 analysis width로 나눈 값은 pad extent 일치도 proxy이며 실제 crease-line 정확도가 아니다. GT 밖의 pixels나 미관측/미대응 후보를 성능 성공으로 해석하지 않는다.

고정된 후보12개를 대상으로 다음 결과를 얻었다. 전체55개 baseline과 observed-only 실험을 대등한 통과율로 해석하지 않는다.

| 방법 | 평균 IoU(10장) | 평균 recall(10장) | precision(비어 있지 않은 사진) | GT 영역 매칭 | 비어 있는 사진 |
|---|---:|---:|---:|---:|---:|
| 전체 branch55 baseline |0.5481|0.7449|0.6687 (10장)|25/38|0|
| 같은 observed12 부모 union |0.1746|0.1798|0.6519 (7장)|9/38|3|
| observed boundary proposal union |0.1882|0.2200|0.5479 (7장)|10/38|3|

관측12개 중2개는 부모와 context 모두 GT와 겹치지 않았다. GT에 대응하는10개만의 **조건부** 후보 IoU도0.7686→0.7625로 개선되지 않았다. 이10개는 별도 진단이며 무대응2건을 주지표에서 제외하지 않았다. GT 최대 axial extent 대비 하단 절단선은 일부에서 약0.56~0.60 analysis width만큼 proximal로 과확장했다. 실제 crease 정답은 없으므로 해부학적 경계 정확도로 부르지 않는다. 관측 범위 부족과 precision 감소를 확인해 **새 variant의 기본 적용을 거절**했다. [익명 집계](../results/photo_observed_boundary_proposals_status.json).

class2 관측도 별도로 확인했다. 55개 부모 후보의 tip overlap을 GT를 읽기 전에 고정했다. tip 있음/GT 교집합 있음28, tip 없음/GT 교집합 있음9, tip 있음/GT 교집합 없음1, tip 없음/GT 교집합 없음17이었다. 교집합은 한 픽셀 이상이라는 평가 정보이며 해부학적 확정은 아니다. class2 존재만 요구하는 counterfactual은 평균 recall0.7449→0.6263, 매칭25/38→19/38, 한 사진의 후보 전체 소실로 이어졌다. 이 gate는 제품에 채택하지 않는다. model segmentation의 class1/2는 같은 모델에서 나온 정보이므로 독립적인 생체 검증으로 부르지 않는다.

새 합성 검증6개는 실제 affine·반 픽셀 중복 금지·oblique cut·support hole·미관측 이웃 ownership·fallback 금지·할당/입력 계약을 확인한다. core280 run=277 PASS/optional Torch3 SKIP, Python138 syntax PASS다. training10장 기존 branch mask, 새 proposal의 반복 mask/metadata가 exact였다. source·GT·semantic cache73파일과 기존 체크아웃 등을 합친513파일을 보존했다. 기존 tracked Python136파일이 byte-identical이므로 default/scanner/frozen/threshold의 source는 그대로다. 이 단계에서 default 실제 보호 matrix·새 GUI 시연·Linux 실험 parity는 재실행하지 않았다. 원본 사진·GT·cache·overlay·private 진단은 공개하지 않는다.

두 조건을 더 완화해 통과율을 맞추지 않는다. 다음 개발에서는 실제 손가락 단위의 분리와 융선 근거를 확보하고, 미관측과 잘못된 proximal transition을 구별해야 한다. 새 검출·범위 제안은 별도 versioned 경로와 개발 데이터 평가를 거쳐야 하며 현재 mask를 자동 보호로 승격하지 않는다.
