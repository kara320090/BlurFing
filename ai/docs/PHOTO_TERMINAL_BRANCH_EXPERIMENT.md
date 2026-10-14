# 손가락 가지 분리 실험

`photo_terminal_branch_candidates_v1.py`와 `v2.py`는 encoded 좌표의 검증된 COLFISPOOF body/tip Boolean 마스크에서 기하 후보를 만든다. 기본 CLI/API/GUI에는 연결하지 않으며 `approved_for_use=false`, `renderer_binding_allowed=false`를 유지한다. 결과는 보호 영상이나 해부학적으로 확정된 손가락이 아니다.

- 하나의 손 전체에 주축·폭을 적용하는 대신 skeleton의 자유 끝점에서 첫 분기까지 관측한다. 기존512 작업 해상도, 폭의1.35배 extent, 기존 길이/폭 조건을 재사용했다. GT/RGB를 estimator 입력으로 쓰지 않는다.
- 격자 모서리의 diagonal shortcut을 제외한다. 분기점의 추정 반경 안에 들어가는 짧은 내부 가지를 제거하며 **body/tip는 수정하지 않는다**. OpenCV `DIST_L2/mask5` 반경은 근사값이고 이 규칙은 공학적 기준이다. [skeleton 설명](https://scikit-image.org/docs/stable/auto_examples/edges/plot_skeleton.html)과 [EDT 설명](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.distance_transform_edt.html)을 참고한다.
- v1은 nearest-skeleton support의 경계가 겹치면 해당 후보 전체를 거절한다. v2는 같은 거리의 픽셀을 어느 후보에도 배정하지 않고, 각 후보의 나머지 고유 픽셀을 보존한다. 고유 support가 없는 후보는 거절한다. 임의의 첫/마지막/largest owner를 선택하지 않는다.
- 경계·폭·가지 길이는 working 단위로 표시한다. native mask는 동일 NEAREST resize로 복원한 뒤 관측 body와 교차한다. native candidate가 겹치면 거절하며 할당 전에 기존 자원 한도를 검사한다. class2를 pad에 강제 union하지 않는다.

```python
from photo_terminal_branch_candidates_v2 import estimate
# body/tip: 같은 source/hash/shape/encoded 좌표로 검증된 Boolean masks
result = estimate(body, tip)
# result['mask']와 result['regions']: review-only 후보, renderer에 연결 금지
```

2026-10-14 인간 training10장 결과는 다음과 같다. 이전 fresh COLFISPOOF cache를 source/hash 계약으로 검증해 재사용했다. 각 실험은 코드·정책을 기록한 뒤10장 모두를 평가했으며, v1 원본 코드 snapshot을 보존했다. v1의 공유 구현 분리 후 mask·후보 metadata도10장 모두 exact였다.

| 방법 | 평균 IoU | 평균 precision | 평균 recall | IoU≥0.5 연결영역 매칭 | FP 연결영역 |
|---|---:|---:|---:|---:|---:|
| 기존 coarse |0.3511|0.3845|0.8151|8/38|13|
| branch v1 |0.4820|0.6393|0.6179|24/38|26|
| branch v2 |0.5481|0.6687|0.7449|25/38|29|

연결영역 개수는 실제 손가락 개수가 아니다. precision/IoU 개선과 함께 recall 감소·추가 오검출이 발생했다. 특히 자유 끝점에는 손목·접힌 손가락·피부 돌출도 포함되고, 분기/몸통의 노이즈가 손끝 소유권에 영향을 준다. 따라서 **두 버전 모두 기본 적용은 거절**한다. training 결과는 독립 일반화 검증이 아니다. GT7/소비한 holdout 기반 tuning은 하지 않았다.

v2 후보55개의 bbox/support만 사용해 기존 ACF/FFT observer를512/1024/2048/native에서 추가 관측했다. 원본 해상도에서1개 후보의 pitch가 관측됐으나 대부분은 여전히 거절됐다. 이 작은 crop은 finger-body segmentation이 아니라 branch proposal이며, frozen renderer의 pitch·feature gate·실제 보호율을 평가한 결과가 아니다. observer threshold와 frozen 수학은 그대로다. [익명 집계](../results/photo_terminal_branch_experiment_status.json)를 참고한다.

다음 개발은 가지의 손끝/손목 구별과 실제 지문 하단 경계 근거가 필요하다. 통과율을 맞추려고 pitch·feature gate를 완화하거나 이 실험 mask를 기본 보호 범위로 승격하지 않는다.

검증: 새 합성 회귀19개를 포함한 core262 run=**259 PASS/optional Torch3 SKIP**, AI Python134 syntax PASS. 각 버전의 training10장 mask·후보 metadata와 반복 결정이 동일했고, 단위 표기 보완 뒤에도 mask·결정이 동일했다. 보존 대상513파일의 해시를 확인했다. 기존 보호 pipeline의 tracked source는 변경하지 않았다. 이 단계에서는 새 실제 보호 출력·새 GUI 시연·Linux 실험 parity를 검증하지 않았다.
