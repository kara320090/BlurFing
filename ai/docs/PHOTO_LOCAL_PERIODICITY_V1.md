# 국소 융선 주기 관측과 방향 코드 감사

기존 [branch 후보](PHOTO_TERMINAL_BRANCH_EXPERIMENT.md)의 native crop55개에서 융선 관측 실패 원인을 확인하고 별도 `photo_local_periodicity_v1.py`를 평가했다. 이 도구는 주기적 영상 단서만 관측하며 지문 identity·finger segmentation·보호 mask를 확정하지 않는다. 기본 CLI/API/GUI·renderer와 연결하지 않는다.

기존128px profile·80px margin·64px stride에서는 37/55 bbox가 minimum6 patches를 만들 수 없었다. 인간 GT와 겹치는37개 후보 중24개도 해당한다. 정확한16px 합성 능선과 정상 방향 계산을 넣어도196×250 crop은 최대2patch라 거절된다. grid 자체가0인18개도 `no_periodicity`로 기록돼 있어 이를 실제 능선 부재로 해석하면 안 된다. 기존 observer의 방향·x/y 계산은 합성5방향에서 정상이다.

반면 `ridge_evidence_frontend.py`의 orientation metadata에는 명확한 논리 오류가 있었다. modulo-π 축을 일반 median으로 합치면 +89°/-89°가0°로 붕괴했다. 합성9개와90° 회전 대조로 재현해 **doubled-angle sin/cos 집계**로 수정했다. 같은32² credible-window 벡터를 pooled mean으로 합친다. orientation은 축 방향인 gradient normal, resized analysis pixel 공간의 radians다. 수치적 상쇄는 `None`, resultant는 방향 집중도이며 확률이나 새 quality gate가 아니다. finite 입력의 doubling overflow도 명시적으로 거절한다. mask·pitch·coherence/contrast/FFT 조건은 유지했다.

새 observer는64px normal profile,24px tangential averaging, stride32, 회전 footprint와 interpolation 여유를 포함한 margin36을 사용한다. 두 complete cycles가 필요하므로 이 실험의 최대 관측 주기는31.5px다. 기존 support≥.95, coherence≥.65, contrast≥2, ACF correlation≥.6/prominence≥.15, FFT energy≥.5, cue difference/IQR≤.15, minimum6 기준을 재사용했다. 관측창·주기 적용 범위는128px observer와 다르며 frozen pitch API의 대체품이 아니다. native crop에서만 측정하고 upscale·default pitch를 만들지 않는다. 단계별 통과 수와 실제 remapped profile의 mask coverage를 기록한다.

```python
from photo_local_periodicity_v1 import observe
report = observe(native_gray_uint8, native_candidate_bool_mask)
# report['support_mask']: 개별 관측 profile 범위, 보호 mask/GT 아님
```

창은 서로 겹치며 ACF/FFT도 같은 profile을 읽는다. 독립적인 생체 evidence가 아니다. 방향은 각 local patch에서 관측하며 전역 방향을 가정하지 않는다. `support_mask`는 aggregate 불안정/patch 부족에서도 개별 accepted 관측창을 기록할 수 있다. anatomy는 `unknown`, renderer/protection binding은 항상 false다.

training10장의 source/hash로 검증된 이전 COLFISPOOF cache를 재사용했다. 새 neural inference나 독립 validation은 하지 않았다. 코드·정책을 기록하고 native 관측과 반복 검증을 완료한 뒤 전체 인간 GT를 읽었다. 국소 accepted patches는 기존 native11개→새65개지만, 안정적인 candidate spacing은 각각1/55개였다. 단서가 있는7후보 중1개는 GT와 겹치지 않았다. 새 stable 후보만 남기는 counterfactual은 평균 recall0.7449→0.0544, 매칭25/38→1/38,10장 중9장 후보 소실로 이어져 **기본 적용을 거절**했다. 단순 창 축소만으로 PHOTO 실용성이 해결된 것은 아니다. GT는 pad mask이며 실제 융선/주기 정답이 아니다. [익명 집계](../results/photo_local_periodicity_status.json).

동시에 `contactless_ridge_pitch.estimate_ridge_pitch`에서 **실제 profile의 ROI coverage 검사 누락**을 isolated API로 재현했다. target 안은 uniform128, 밖만6px/8px 주기인 합성 입력에서도 기존 함수가 pitch를 반환했다. frozen 경로에서 사용하는 함수이므로 source와 수학은 보존했다. 새 observer는 동일 종류 대조를 실제 profile support 단계에서 거절했다. 이 결과는 전체 frozen pipeline에서 잘못된 보호가 적용됐다는 증명이 아니다. 95% support는 최대5% 미지원 sample을 허용하며 bilinear interpolation도 사용하므로 배경 영향을 완전히 제거했다고 주장하지 않는다.

공개 합성 재현은 다음과 같다. 개인 사진/GT·외부 model/runtime은 필요하지 않다.

```bash
python ai/scripts/probe_ridge_profile_support_v1.py
python -m unittest discover -s ai/scripts -p 'test_*.py'
```

검증: core289 run=286 PASS/optional Torch3 SKIP, 실제55 native crop의 orientation 외 기존 mask/pitch/quality fields exact, 기존 보호 matrix10건의 판정·영역 signature·RGB exact. orientation은10후보에서 수정됐다. 기존 reference 원본은 수정하지 않았으며 orientation metadata가 같다고 주장하지 않는다. 새 local 관측55개의 반복 mask/metadata와 training10장 부모 mask도 exact였다. frozen renderer·contactless 함수·detector/pitch/feature thresholds는 보존했다. 새 GUI 시연·Linux metadata/실험 parity는 미검증이다.

남은 과제는 실제 finger-body 분리의 오검출, 작은/저품질 영상의 융선 관측 부족, profile-size별 단위와 support 검증, frozen 함수의 support 계약 개선안이다. frozen 수정이나 실제 자동 보호 채택은 이번 단계에 포함하지 않는다.
