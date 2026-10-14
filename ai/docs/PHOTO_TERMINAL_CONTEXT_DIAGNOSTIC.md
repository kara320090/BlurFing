# 손가락 후보의 맥락·경계 관측 점검

`photo_terminal_context_diagnostic_v1.py`는 [branch v2](PHOTO_TERMINAL_BRANCH_EXPERIMENT.md)의 후보를 바꾸지 않고 source frame 접촉과 RGB 경계 단서를 기록한다. 기본 CLI/API/GUI나 renderer에 연결하지 않는다. 입력은 같은 encoded source 좌표의 uint8 RGB와 검증된 Boolean body/tip이며, GT·파일명·개인 자료를 추론 입력으로 쓰지 않는다.

```python
from photo_terminal_context_diagnostic_v1 import diagnose
report = diagnose(rgb, body, tip)
# review-only: report['rows']; mask 변경/보호 처리 없음
```

pad의 1.35폭 prefix만으로는 기존 observer의 1.1~2.4폭 검색 구간을 관측하기 어렵다. 그래서 전체 terminal skeleton의 nearest support를 별도로 읽는다. junction seed는 제외하고, junction 없는 하나의 path는 arc<중간점으로 양 끝의 맥락을 분리한다. 이 맥락은 동거리 픽셀을 포함할 수 있으며 renderer의 배타적 소유권이나 확정된 손가락 segmentation이 아니다.

frame flag는 실제 source mask의 네 변 접촉을 기록한다. cap ray의 frame-cut 여부와 구분한다. training 후보 중 frame 접촉 6개에는 인간 GT와 겹치는 실제 대상 후보 1개도 있었으므로, frame에 닿는다는 이유로 손목 판정·후보 삭제를 하지 않는다. 해부학적 분류는 `unknown`이다.

경계 관측은 기존 SAM RGB crease/appearance 조건을 재사용한다. bbox를 최대720px로 축소하고, 반올림된 실제 x/y resize 비율과 pixel center `(x+.5)*scale-.5`를 사용해 source↔axial affine을 기록한다. working 방향도 실제 x/y 비율로 native 단위로 변환한다. nominal scale로 좌표를 역산하지 않는다. 반환 선은 선택된 axial row의 **참조 transect**이며, tilted crease를 fitted line이나 지문 경계 곡선으로 복원한 것이 아니다. 끝점은 support 밖일 수 있다.

이번 코드 감사에서 기존 `proximal_boundary_evidence.py`의 논리 오류를 재현·수정했다. 마스크가 없는 행의 초기 신호 0과 중앙 span의 배경 픽셀 때문에 같은 RGB에서 가짜 appearance transition을 승인할 수 있었다. 이제 appearance의 before/after window와 기존 Gaussian kernel 반경 전체에 유효한 foreground 관측 행이 있어야 한다. 중앙20~80 percentile span에 마스크 hole이 있는 행도 유효 관측으로 쓰지 않는다. 결측은 `appearance_window_mask_support_unavailable`로 거절한다. 정상 관측의 수치와 기존 crease/appearance 조건은 유지했다.

입력 dtype·shape·범위·finite 조건과 할당 한도를 확인한다. NaN/inf·chroma median overflow는 명시적으로 거절한다. 유효하지만 한 axial 행뿐이거나 resize/warp에서 support가 사라진 입력은 `unobserved`로 기록한다. 이런 후보 하나가 전체 진단을 중단하지 않는다.

2026-10-15 training10장/후보55개를 source/hash 계약으로 검증된 기존 COLFISPOOF cache에서 관측했다. 새 neural inference나 독립 검증은 수행하지 않았다. 경계 단서12개 관측·43개 미관측, 불완전 appearance peak22개 거절이었다. 이는 **해부학적 경계 정확도, 보호 성공률 또는 privacy proof가 아니다**. 코드를 평가 전에 기록했고 GT는 관측 완료 뒤의 평가에만 읽었다. 후보 mask10장 모두 이전 v2와 pixel-identical이며 반복 진단도 exact였다. 기본 적용은 계속 미승인이다.

검증은 core274 run=**271 PASS/optional Torch3 SKIP**이다. 결측·중앙 hole·유효 Gaussian 범위·overflow·얇은 support·resize 소실·실제 affine 등의 합성 회귀를 포함한다. 새로운 중앙 hole 회귀는 이전 HEAD에서 실제 실패했다. 정상 경계의 기존 전체 수치도 동일했다. 기본 보호 matrix10건은 PHOTO/SCANNER 판정·영역 signature·반환RGB 모두 기존 reference와 exact였고, 원본/GT/cache/기존 체크아웃 등553파일을 보존했다. 새 Linux diagnostic parity·새 GUI 시연은 검증하지 않았다. [익명 집계](../results/photo_terminal_context_diagnostic_status.json).

다음 성능 개발은 실제 손끝/손목을 구별할 관측 근거와 경계의 해부학적 타당성 검증이 필요하다. 기존 branch의 recall 저하·오검출·pitch 미관측 문제는 해결된 것으로 보고하지 않는다. detector/pitch/feature threshold, frozen v4·natural_auto_04·boundaryblend_02 수학, Linux reference와 private 입력은 변경하지 않았다.
