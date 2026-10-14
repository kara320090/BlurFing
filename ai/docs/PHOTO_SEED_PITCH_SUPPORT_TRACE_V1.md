# 실제 PHOTO seed pitch 지원 범위 점검

[이전 isolated 재현](PHOTO_LOCAL_PERIODICITY_V1.md)에서 발견한 profile support 검사 누락이 실제 PHOTO 실행에도 나타나는지 확인했다. `photo_seed_pitch_support_trace_v1.py`는 현재 스레드의 Python/C profile events로 frozen 함수의 실제 호출과 `cv2.remap` 지도를 기록한다. 함수·import alias·ROI·gate·반환값을 교체하지 않는다. 기존 profiler가 있으면 덮어쓰지 않으며 정상 종료와 예외 모두에서 원래 상태로 복원한다. 진단 오류는 원래 알고리즘을 중단시키지 않고 `errors`에 남긴다. 검증자는 이 목록이 비었는지 확인해야 한다.

추적 경로는 기본 `protect_image → photo_quality_gate → photo_coarse_adapter_v2 → observed_seed_pitch`, opt-in region v3의 `prepare_region`, 그리고 실제 frozen renderer의 pitch 재관측이다. Raw/Bilateral의 full/partial 선택과 TwoScaleGaussian을 구분한다. `participates_in_selected_estimation`은 최종 pitch 집계에 포함된 profile을 뜻한다. count/MAD·방향장·ROI 추정까지 포함한 모든 인과적 기여를 뜻하지 않는다.

```python
from photo_seed_pitch_support_trace_v1 import SeedPitchTrace
from protect_fingerprint import protect_image

with SeedPitchTrace() as trace:
    returned, report = protect_image(source, fresh_output, photo_semantics=validated_cache)
assert not trace.errors
private_diagnostic = trace.metadata()
```

`trace.seeds/estimates`에는 비공개 영상·ROI·지도 배열이 있다. `metadata()`도 crop hash·좌표를 포함한 비공개 진단이며 공개 Git에 넣지 않는다. 실제 source/hash로 확인한 기존 COLFISPOOF cache를 사용했다. 새 neural inference·GT를 입력으로 쓰는 검출·독립 검증은 수행하지 않았다.

측정 마스크는 `prepare_fingerprint`가 추정한 내부 ROI다. coarse 보호 pad·finger body·인간 GT와 다르다. 실제 remap 지도에 같은 bilinear interpolation과 border 규칙을 적용해 ROI 지원 가중치를 측정한다. nearest 지원율 100%도 bilinear 이웃 지원을 보장하지 않는다. caller에 유효한 `working_mask`가 있을 때만 seed 포함 여부를 판단하며, 범위 밖·빈 slice·renderer의 미확인 caller는 `None`이다. 이 포함 판정도 실제 촬영 배경 제외나 해부학적 정확도의 증명이 아니다.

대조는 세 범위로 분리했다.

1. **지도 고정:** 현재 전처리 frame·ROI·방향·지도를 유지하고 ROI 밖만 0/128/255로 채워 detrended profile 변화를 측정한다. 직접 profile 읽기의 의존성이다.
2. **ROI/frame 고정:** 전처리 frame의 ROI 안 픽셀을 유지하면서 밖만 바꾸고 원래 estimator의 방향장을 다시 계산한다. 직접 읽기와 방향장 맥락 영향을 포함한다. Gaussian 단일 frame의 선택값은 해당 scale의 credible estimate이며 최종 두 scale 평균·합의 판정이 아니다.
3. **canonical seed 재생성:** 관측된 raw512의 기존 ROI 안을 유지하고 밖만 바꾼 뒤 원래 seed 함수의 CLAHE·ROI·blur·방향장을 다시 실행한다. 새 ROI가 없으면 거절/미생성으로 기록한다. 이 대조는 선택된 seed만 대상으로 하며 원본 PHOTO 전체·renderer의 반사실 실행이 아니다.

사진 20장(사용자 2·training 10·이미 소비한 holdout 8)과 scanner 대조 1개를 기본 경로에서 실행하고, 같은 사진 3개를 opt-in v3에서도 실행했다. 사용자 사진과 byte-identical인 기존 개발 fixture는 중복 제외했다. **24회 모두 계측 전후 판정·영역·RGB와 같은 플랫폼 PNG mask hash가 exact**였다. 기존 Windows 체크포인트 13회도 같은 기준으로 확인했다. 역사 Linux 결과는 기존 operational outcome/region/mask pixel signature·decoded RGB 기준으로 비교하고 압축 바이트와 작은 pitch metadata 차이는 별도 보존했다. 새 Linux 실행/parity·GUI smoke는 수행하지 않았다.

37 seed 호출·98 estimator 호출에서 780 profile을 샘플링했다. 반복 호출을 제거하면 508 profile, 126 periodic profile, 최종 pitch 집계 포함 102 profile이다. 지원이 부족한 샘플 12개는 모두 periodic 단계에서 탈락했다. **periodic/선택 profile의 미지원 bilinear 이웃과 고정 지도 직접 변화는 모두 0**이었다. caller에서 seed 포함을 직접 확인한 호출은 30개, 나머지 7개는 앞선 포함 seed와 box·shape·RGB hash가 정확히 일치했다. 이를 anatomical GT로 해석하지 않는다.

선택된 canonical seed 4개의 대조에서 방향/전처리 재계산에 따른 pitch 변화가 있었고 최대 변화는 **0.00015414 canonical px**였다. 따라서 ROI 밖의 모든 간접 영향이 없다고 주장하지 않는다. 합성 isolated API의 누락은 여전히 존재하지만 이번 사진들의 실패 원인으로 확정하지 못했다. 전체 보호 성능이나 보편적 support 안전성을 증명하지 않는다.

검증: core **294 run = 291 PASS / optional Torch 3 SKIP**, public 계측 계약 검사 5개 PASS, 원본·참조·기존 로컬 파일 603개 보존. 기존 tracked Python·frozen renderer·detector/pitch/feature 임계값은 변경하지 않았다. 기본 PHOTO에서 실제 변환된 source는 이 혼합 진단 집합의 1/20에 그쳤으므로 실용성 문제가 해결됐다고 보고하지 않는다. [익명 집계](../results/photo_seed_pitch_support_trace_status.json).

다음 검토 대상은 검출 pad와 실제 융선 영역의 대응, 관측 가능한 영역을 quality/feature gate와 연결하는 계약이다. isolated support 누락의 개선은 별도 versioned 실험으로 제안하며, 이번 도구를 frozen 대체품이나 새 보호 gate로 채택하지 않았다.
