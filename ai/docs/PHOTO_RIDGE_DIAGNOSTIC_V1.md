# 후보별 원본·다중 해상도 능선 진단

`photo_candidate_ridge_diagnostic_v1.py`는 보호 범위와 pitch 실패를 조사하는 읽기 전용 도구다. 기존 pad를 늘리거나 renderer에 관측값을 연결하지 않는다.

```powershell
& $env:BLURFING_CORE_PYTHON ai/scripts/photo_candidate_ridge_diagnostic_v1.py `
  --input 'C:\private\photo.jpg' --output 'C:\private\new-diagnostic' `
  --photo-semantics 'C:\private\source-bound-semantics'
```

- body/후보 ID/원본 encoded 좌표를 보존하고 body bbox에서512/1024/2048/원본 해상도를 관측한다. 동일 raster는 한 번만 계산하며 upscale을 하지 않는다.
- 기존 ridge window 조건과 기존 ACF/FFT observer를 사용한다. window support의 pad 안/밖 면적은 GT 지문 면적이나 보호율이 아니다. ACF/FFT는 같은 profile을 사용하므로 독립 생체 증거가 아니다.
- 반올림된 실제 x/y resize 비율과 bbox 원점으로 patch 좌표·수직 방향 pitch를 원본 단위로 기록한다. working normal의 원본 period는 `pitch / norm(A.T @ normal)`이다. 명목 scale에만 의존하지 않는다.
- decode/resize 전에 기존 자원 한도를 검사한다. pitch 미관측에 기본값을 만들지 않는다. RGB/L·EXIF1~8·새 출력 폴더를 요구하며 원본/마스크를 보존한다.
- 결과는 `diagnostic.private.json`과 bbox 내부의 native window-support 마스크다. 전체 사진의 보호 마스크가 아니다. `renderer_binding_allowed=false`, `protection_applied=false`를 유지한다.
- `--annotation-folder`에 사람이 만든 `source.json`/`ground_truth_mask.png`를 주면 **관측을 마친 뒤** source/hash/EXIF/shape/binary/human 계약을 검증하고 기존 pad의 GT metrics만 계산한다. GT는 후보·crop·해상도·pitch 선택에 들어가지 않는다. 모델 segmentation을 인간 GT로 표시한 자료는 거절한다.
- 실제 training10개/새 independent 자료 구분과 provider의 data split을 유지해야 한다. 소비한 GT7/holdout 결과에 맞춰 기준을 수정하지 않는다.

2026-10-14 최초 검증: 새 합성 회귀11개 포함 core241 run=**238 PASS/optional Torch3 SKIP**, GUI9 PASS, Python130 syntax PASS. 실제 소비된 개발 입력6개에서 이전512/1024/2048 ridge 관측은 exact였다. 기본10-case의 상태/영역/RGB도 exact였다. 이 단계는 cache와 기존 observer를 사용했다.

이후 인간 정답·원본 training10쌍을 연결하고 fresh COLFISPOOF 추론과 고정 해상도 진단을 완료했다. 평균 coarse IoU **0.3511**, precision **0.3845**, recall **0.8151**이었다. GT 픽셀의 평균 **5.40%**는 body 밖, 추가 **13.09%**는 body 안에서 distal 선택에 의해 누락됐다. 다중 손가락 자세에서 proximal 피부·손 전체가 pad에 들어가는 사례를 비공개 overlay로 확인했다. 512/1024/2048/원본 해상도의 기존 external ACF/FFT 진단은 모두 거절됐다. 이는 frozen renderer의 pitch 결과나 보호율이 아니며, training 자료이므로 독립 성능 검증으로 해석하지 않는다. [익명 집계](../results/photo_training_GT10_diagnostic_status.json)를 참고한다.

이 검사에서 재현된 1픽셀 watershed 후보의 정의되지 않은 공분산 계산을 사전 거절로 수정했다. 기존 `skeleton_endpoints_unobserved` 사유를 유지하며 경고를 오류로 처리해도 정상 거절한다. 수정 후 core243 run=**240 PASS/optional Torch3 SKIP**, GUI9 PASS, Python130 syntax PASS. training10장의 mask·후보 판단과 기존 기본10-case의 상태·영역·RGB가 exact였고 보존 대상 파일553개의 해시를 보존했다. 이 수정은 정확도 개선이나 기본 pipeline 승인이 아니다. threshold·frozen renderer는 변경하지 않았다.

대표 개발 입력에서는1024에서 pitch가 관측되지만512에서는 patch 부족,2048/원본에서는 cue 불일치로 거절됐다. patch 수 증가만으로 품질을 승인할 수 없다. 실제 보호 범위 확장·feature gate 변경·기본 적용은 수행하지 않았다.
