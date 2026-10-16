# 둥근 손끝 보호 변환의 거절 원인과 보완 결과

2026-10-16. 이전 실제 변환 재검증의 근접 사진, 전체 손 사진, 세 손가락 사진을 대상으로 거절 경로를 추적했다. 기존 개발 자료의 재실행이며 새 독립 성능 평가가 아니다. 무늬 변환 알고리즘의 일반 적용률을 개선했다고 주장하지 않는다.

## 원인

전체 손 사진의 4개 손끝은 로컬 간격 측정에서 실패했다. 같은 측정 수치 기준을 유지한 채 내부 scanner ROI를 제외하고 실제 permission 전체를 측정하는 대조 실험에서도 통과하지 못했다. 같은 창을 원본에서 한 번만 보간하는 대조 실험도 24/24/24/22개 창 중 통과 창이 없었다. 해당 영상에서는 단순 ROI 축소나 두 번의 resize만이 원인이라고 볼 근거가 없다. 방향 검사에서 탈락하거나, 방향 검사를 통과한 profile의 대비가 부족하거나, 허용 대역 안에 일관된 주기가 없었다. 방향/지지 조건을 통과한 profile의 대비 중앙값은 손끝별 약 0.48–0.96으로 기존 최소 2보다 작았다. 이 값은 전역 이미지 대비나 생체 인식 가능성의 판정이 아니다. 대조 실험은 진단 전용으로 실행했고 production observer를 교체하지 않았다.

전체 손의 엄지는 간격을 측정하고 실제 변환 후보도 만들었지만, 최종 검사에 포함되는 SourceAFIS 특징점이 원본 62개에서 반환 후보 8개로 줄었다. 세 손가락 사진의 두 주요 영역도 34→2, 15→0개였다. 기존 `assess_structure()`는 **변환 전후 모두 10개 이상**의 특징, 위치/유형 변화, skeleton 변화를 요구한다. 따라서 지문 특징이 줄어든 변환도 `insufficient_features`로 거절된다. 이는 실행 자체의 실패와 다르다. 원래 지문 같은 구조를 유지하는 기능 검사와 지문 노출을 제거하는 목적은 동일한 수용 기준이 아니다. 특징 미추출을 보호 성공으로 바꾸거나 기존 수치 기준을 낮추지는 않았다.

세 손가락 사진의 나머지 주요 영역은 허용 범위 안의 특징이 원본/반환 후보 모두 0개였다. 실제 검사 프레임에서는 특징이 범위 밖에서만 추출됐다. 이 결과는 원본에 지문이 없다는 뜻이 아니다. 추가로 5,301화소와 81화소의 떨어진 조각에서 로컬 간격 관측이 실패했고, 42개 미배정 조각(총 3,085화소)은 손가락 owner를 확정하지 못했다. 47개 연결 영역을 손가락 47개로 해석하지 않는다.

크기/회전/축/owner 연결은 기존 native 파이프라인과 저장 결과에서 확인했다. 이번 범위에서 거절을 없앨 명확한 좌표 구현 오류는 확인되지 않았다. `insufficient_features` 하나로 서로 다른 원인을 뭉뚱그리는 보고 문제는 세분화해 해결했다. 새로운 원본 품질, 자연스러운 renderer 출력의 특징 보존, 검출 경계 정확도는 별도 과제로 남는다.

## 구현

`photo_rejection_resolution_v1.py`는 실제 gate 결과에 근거해 원본 특징 부족, 반환 후보 특징 부족, 간격 미관측, owner 미확정 등을 구분한다. gate 수치와 판정은 변경하지 않는다.

기존 `protect_photo_rounded_native_v1.py`가 처리한 뒤 `protected.png`와 `returned.png`는 그대로 보존한다. 별도 **`covered.png`**는 이미 승인된 native 변환을 유지하고, 거절된 permission 화소를 불투명 검정 RGB로 채운다. permission 밖 RGB는 원본과 같다. `fallback_mask.png`, `rejection_diagnostics.private.json`, `resolution.html`에서 가림 영역과 이유를 확인한다. `detect_only`는 이 보완본을 만들지 않는다.

이는 명시적인 별도 가림 결과이며, 거절된 무늬 변환을 성공으로 집계하지 않는다. 원래 report의 status, 변환 수, 거절 수, 반환 RGB hash가 유지된다. 원본/마스크/region hash, 적용 범위와 실제 native 구조 검사 결과를 확인하며, runtime/contract 오류나 알 수 없는 실패를 보완 가림으로 숨기지 않는다. 검출 누락과 경계 오차가 있을 수 있으므로 사진 전체 보호를 보증하지 않는다. 근거 없는 pitch 생성이나 seed/renderer 결과 선택 재시도를 추가하지 않았다.

로컬 `outputs/BlurFing-Rounded-Protect.cmd`에서 기존처럼 사진을 선택하면 `protection/covered.png`와 비교 페이지 경로도 출력한다. 기존 Android/서버 기본 엔진, scanner, frozen 수학, threshold, 모델 가중치는 변경하지 않았다.

## 실제 검증

| 사례 | 기존 무늬 변환 | 별도 검정 가림 | 후보 내 미처리 |
|---|---:|---:|---:|
| 전체 손 | 0/5 연결 영역 | 634,279화소 | 0 |
| 세 손가락 | 0/47 연결 영역 | 752,584화소 | 0 |
| 근접 사진 | 1/1 연결 영역, 3,733,836화소 변경 | 0화소 | 0 |

전체 손은 `.cmd`에서 실제 COLFISPOOF/V6/pose/둥근 후처리부터 다시 실행했다. 나머지 두 사진은 source/model/mask/geometry를 검증한 기존 검출 자료를 사용해 native renderer와 gate를 다시 실행했다. 세 사진의 native 결과는 이전 결과와 pixel-identical이었다. 별도 가림 결과에서 거절 영역은 모두 0 RGB이고, 승인된 변환과 후보 밖 RGB는 그대로였다. 저장 PNG를 다시 읽어 RGB, 적용/거절/가림 마스크, EXIF/ICC를 확인했다. 비공개 입력 138개와 frozen 소스 4개도 이전 hash와 같았다.

관련 단위/회귀 검사 **71개 통과**. 거절 원인 분류, 원본 화소를 바꾸어도 가림 영역에 노출되지 않는 성질, 잘못된 hash/마스크/거짓 성공 차단, runtime 오류를 가림으로 숨기지 않는 조건, 원본 및 EXIF 보존, 기존 V12와 둥근 검출 경로를 포함한다. 실제 SourceAFIS 작업의 `scores 0` 출력은 점수 비교 작업을 요청하지 않았다는 진행 로그이며 매칭 점수 0이라는 뜻이 아니다.

로컬 비교: `outputs/rounded-rejection-resolution-20261016/comparison.html`. 진단은 `work/rounded-rejection-audit-20261016/`에 비공개로 보존했다. 자연스러운 무늬 변환의 적용률과 독립적인 지문 보호 성능은 아직 해결되지 않았으며 검정 가림 수로 대체해 보고하지 않는다.

## 추가 사진에서 발견한 축소 경계 조건

추가 입력의 유효한 3화소 permission 조각이 working scale 약 0.556의 nearest-neighbor 축소 후 0화소가 됐다. 관측 seed 함수가 빈 working mask를 잘못된 입력으로 처리하면서 `body_observation_mask_contract`가 발생했고, 보완본 검증에서는 이 오류가 `rejection_resolution_region_binding_mismatch`로 가려졌다. native permission 자체의 hash나 영역 분할이 틀린 사례는 아니었다.

`photo_body_observation_seed_v1.prepare_region()`은 native mask 계약을 먼저 검사하고, 유효한 native 조각이 축소 후 비었을 때 기존 `body_supported_seed_unavailable` 사유로 반환한다. component 경로에서는 `component_local_seed_unavailable`이 된다. working/native 화소 수를 기록하며, 원래 permission은 삭제·팽창하지 않는다. 간격을 만들어 넣거나 scale을 강제로 바꾸지 않는다. 잘못된 native mask는 계속 계약 오류이며, 실제 runtime 오류도 보완 가림으로 숨기지 않는다. 보완본의 오류 메시지는 region ID와 원래 오류 사유를 전달하도록 구분했다.

관련 회귀 검사 **95개 통과**. 8개 EXIF 방향에서 축소로 사라지는 합성 조각, native 입력 보존, 기존 미관측 사유 연결, 살아남은 조각의 기존 관측 경로, 잘못된 입력 및 runtime 오류 차단을 포함한다. 실제 실패 사진도 재실행해 3화소 조각이 오류 없이 거절되고 원래 좌표에서 보완 가림되는 것을 확인했다. frozen renderer, 보호 gate 수치와 모델 가중치는 변경하지 않았다.

추가 사진 6장(JPG 3장, DNG에서 만든 RGB 사본 3장)을 검출부터 처리하고, 수정 후에는 hash-bound 검출 자료를 사용해 native 경로를 6장 모두 재실행했다. **무늬 변환 적용 사진 0/6, 별도 검정 가림 보완본 6/6**이며, 연결 후보 안 미처리 화소는 0이다. 최종 PNG를 다시 읽어 원본 파일 6개, permission 밖 RGB, native 결과 및 기존 마스크, EXIF/ICC, frozen 소스 4개의 보존을 확인했다. 작은 오검출 조각과 불규칙한 경계는 남아 있으며 검출 정확도나 일반 보호 성공률로 해석하지 않는다.

DNG는 이번 비공개 실행에서 격리된 rawpy/LibRaw로 전체 해상도 sRGB PNG를 생성했다. JPEG 미리보기를 대신 사용하지 않았고, EXIF 표시 방향과 LibRaw의 자동 방향 결과를 픽셀로 대조했다. 원본 DNG는 보존했다. 이는 사진 준비 단계이며 기본 실행기의 DNG 지원을 추가한 것은 아니다. 로컬 결과와 오류 재현 자료는 `outputs/two-photo-folders-20261016/`에 보관하며, `comparison.html`은 재검증된 결과만 연결한다.
