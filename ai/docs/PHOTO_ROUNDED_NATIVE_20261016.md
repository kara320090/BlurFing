# 둥근 손끝 마스크의 실제 지문 보호 변환

2026-10-16. [둥근 손끝 후처리](PHOTO_ROUNDED_PAD_20261016.md)로 만든 마스크를 기존 `natural_auto_04` / `boundaryblend_02` renderer와 V12 실제 반환 RGB 검사에 연결하는 별도 실험 경로다. 검은 가림 미리보기와 실제 지문 보호 변환의 결과를 구분한다.

후속 [거절 원인 진단과 보완 결과](PHOTO_ROUNDED_REJECTION_RESOLUTION_20261016.md): 실제 native 결과는 유지하고, 미적용 후보를 검게 가린 별도 `covered.png` 및 원인별 설명을 추가했다. 아래 수치는 무늬 변환 연결 당시 기록이며, 별도 가림을 무늬 변환 성공에 합산하지 않는다.

## 연결 계약

`protect_photo_rounded_native_v1.py`가 원본부터 검출/후처리를 실행하고 `detection_preview`에 미리보기를 저장한다. 실제 변환은 원본 RGB와 후처리 마스크에서 다시 시작해 `protection/returned.png`, `protection/protected.png`에 저장한다. 검게 가린 이미지를 renderer 입력이나 성공 결과로 사용하지 않는다.

기존 V12 평가 함수를 후처리 마스크에 직접 호출하면 손가락 owner와 축을 이전 coarse estimator에서 다시 계산한다. 둥근 검출이 pose 또는 native owner 복원을 사용한 경우 이 owner가 달라져 일부 화소가 `learned_body_owner_unavailable`로 거절될 수 있다. `photo_rounded_native_pipeline_v1.py`는 검출 단계의 owner/축을 변환에도 전달한다. 원본/semantic/worker/마스크/후처리 기록을 hash 및 기하 재계산으로 결합하고, 서로 다른 출처의 마스크나 다른 버전의 후처리 기록은 거절한다.

각 owner 안에서도 떨어진 마스크 조각은 따로 처리해 지문 간격이나 특징을 다른 조각에서 빌려오지 않는다. 겹친 owner·미배정 화소·후처리 기하 미해결 영역은 명시적으로 거절한다. 모든 허용 마스크 화소는 적용 또는 거절 기록에 포함된다. 연결 영역 수를 실제 손가락 수나 보호 성공률로 해석하지 않는다.

검증 중 prepared dataset의 tile 검사가 별도 호출 시 개발 replay 범위 밖에서 실행되는 연결 오류를 발견해 수정했다. 원본과 canonical PNG의 정확한 identity에 한해 명시적 replay 범위를 preflight부터 최종 검사까지 유지한다. strict consumed 입력 차단은 그대로이며, 호출 종료 후 기존 차단 함수가 복원되는 것을 테스트했다. Windows 실행기의 SHA256 계산은 해당 PowerShell에서 사용할 수 없었던 `Get-FileHash` 대신 기존 실행기와 같은 .NET 구현으로 처리했다.

기존 pitch observer, feature/structure 검사값과 renderer 수학을 변경하지 않는다. 실제 native 반환 RGB가 V12 구조 검사를 통과한 연결 영역만 최종 이미지에 적용한다. 거절된 영역, 적용 마스크 밖 RGB, 원본 파일과 EXIF/ICC를 보존한다. 무변경 결과를 성공으로 집계하지 않는다. 구조 변화나 SourceAFIS 특징 추출 결과 자체는 지문 privacy/security 검증이 아니다.

## 로컬 실행

`outputs/BlurFing-Rounded-Protect.cmd`에서 사진을 선택한다. 결과는 `outputs/rounded-protection-tests/<실행 ID>/protection/protected.png`에 저장된다. `comparison.png`는 원본, 둥근 허용 영역, 실제 변경 화소, 실제 반환 RGB를 표시한다. 거절 마스크와 실제 적용 허용 마스크도 별도로 저장한다.

기존 `BlurFing-Rounded-Pad-Test.cmd`는 검출 영역을 확인하는 검정 가림 실험이다. 실제 변환 실행기는 `BlurFing-Rounded-Protect.cmd`다. 기본적으로 기존 개발 사진의 명시적 재실행을 허용하며 독립 평가로 집계하지 않는다. `-StrictEvaluation`을 지정하면 consumed 입력 차단을 적용한다. 스캐너 경로나 Android/서버 기본 엔진으로 자동 연결하지 않는다.

## 실제 실행 및 판정

근접 촬영 사진을 새 `.cmd` 실행기로 COLFISPOOF → V6 → 둥근 후처리 → 기존 renderer → 실제 반환 RGB 검사까지 실행했다. 허용 연결 영역 1개가 실제 검사에 통과했고 native RGB 3,733,836화소가 변했다. 최종 PNG에서 변환된 지문 무늬를 시각적으로 확인했다. 이는 사진 한 장의 기능 실행 확인이며 일반 지문 보호 성능 승인이 아니다.

전체 손 사진은 둥근 후보 5개를 renderer에 전달했지만 최종 변환은 0개였다. 4개는 `component_local_pitch_unobserved`, 엄지는 `insufficient_features`로 거절됐다. 이전 coarse owner를 그대로 사용한 비교에서는 1개 연결 영역이 변환됐지만, 검출 단계와 다른 owner/축 및 많은 미배정 화소를 사용했다. 단순 통과 수를 높이기 위해 이 잘못 연결된 문맥을 다시 선택하지 않았다.

세 손가락 사진 역시 변환 0개였다. 실제 보호 후보는 47개 연결 조각으로 나뉘며, 그중 손가락 owner에 연결된 5개 조각은 pitch 미관측 2개·특징 부족 3개였다. 나머지 작은 조각 42개는 owner를 확정하지 못해 거절했다. 손가락 47개라는 뜻이 아니다. 752,584 허용 화소를 모두 거절 마스크에 기록했고 실제 반환은 원본과 동일했다.

둥근 검출이 된다는 것과 실제 보호 변환의 품질 조건을 충족한다는 것은 별개다. 현재 범용 PHOTO 적용률의 한계가 남아 있다. 숫자 기준을 낮추거나 거절된 원본을 보호 성공으로 표시하지 않는다. 새 사진 그룹의 GT 검증, 생체 매칭 저항성 검증, Linux/Android 실제 실행은 이번 작업에 포함하지 않았다.

관련 단위/회귀 검사 57개가 통과했다. owner/축 전달, 조각별 evidence 분리, 미배정/겹침 거절, 실제 적용 영역 밖 RGB 차단, mask hash, strict/replay 범위, PNG의 실제 변환 RGB/EXIF 보존과 기존 V12 native 검사 계약을 확인했다.

세 사진 모두 저장된 `returned.png`와 `protected.png`의 RGB, 실제 변경 마스크, 적용/거절 마스크의 완전 분할, 각 region의 hash와 실제 반환 구조 검사 PASS 여부를 독립적으로 다시 검사했다. 원본 및 적용 영역 밖/거절 영역 RGB, EXIF/ICC를 보존했다. 비공개 자료 138개와 기존 frozen renderer/구조 검사 소스 4개도 이전 hash와 일치했다. 비교 페이지는 `outputs/rounded-native-verified-20261016/comparison.html`이다. 최초 실패한 시도는 비공개 진단에 보존하고 검증된 결과와 구분했다.
