# 지문 가시성 검토와 품질 진단 V1

현재 손끝 마스크는 해부학적 보호 후보다. 지문선이 실제로 관찰되는지에 대한
정답과 구분한다. 이번 구현은 가시성 정답 수집 및 자동 관측 비교 도구이며,
기존 보호 알고리즘이나 V19 합성 결과의 적용 조건은 바꾸지 않는다.

## 검토 자료와 계약

- 기존 학습 개발 자료 23장과 이미 사용한 GT7 7장: 중복 없는 30장.
- 기존 마스크의 8 연결 성분은 67개다. 성분은 검토 제안이며 손가락 개수나
  독립 표본 수로 해석하지 않는다. 같은 손가락의 조각은 합쳐 검토할 수 있다.
- 원본 파일, 디코딩 RGB, EXIF 보정 RGB, 기존 마스크를 해시로 연결한다.
  JPEG/MPO의 보조 프레임이 있는 경우 기존 정답과 일치하는 기본 프레임 0만
  사용한다. 임의 프레임 선택이나 원본 변경은 하지 않는다.
- 기존 23장은 3개의 보수적 촬영 그룹에 속한다. 인물 독립성은 확인되지 않았다.
  GT7의 학습 금지·소비된 평가 자료 역할을 유지한다. 30장을 새로운 holdout으로
  재분류하지 않는다. 같은 사진의 손가락·패치를 독립 사진처럼 나누지 않는다.

검토는 원본 1:1 화면에서 `visible`(보임), `not_observed`(관찰되지 않음),
`uncertain`(불확실)을 선택한다. 흐림·반사·작은 크기로 판단하기 어려우면
불확실을 선택한다. `not_observed`는 지문이 존재하지 않는다는 뜻이 아니다.
`visible`에는 기존 마스크 안쪽의 대표 지문선 사각형, `uncertain`에는 사유가
필요하다. 경계나 손가락별 그룹이 잘못되었다면 geometry 사유로 남긴다.
전체 첫마디 마스크를 다시 그리는 작업은 필요 없다.

자동 관측값은 검토 화면에 노출하지 않는다. 미판정과 임시 저장은 정답이 아니다.
사람의 원본·그룹 검토 확인이 있어야 human_GT가 되며, 합성 테스트 자료는
이 확인을 해도 human_GT가 되지 않는다. 이전 revision은 보존하며 프로세스 간
파일 잠금과 revision 충돌 검사를 사용한다. ZIP은 라벨·원본/마스크 해시만 담는다.
개인 사진·마스크·비공개 진단·외부 모델 가중치는 공개 저장소에 넣지 않는다.

## 자동 진단

`photo_visibility_diagnostic_v1.py`는 원본 ROI에서 기존 구조·주기 관측기를
실행한다. 관측 범위는 GT로 지정한 해부학적 후보이므로 자동 검출기의
end-to-end 성능 평가가 아니다. 관측기 임계값은 변경하지 않는다.
원본 EXIF 보정 후 좌표, 잘라낸 ROI의 원점, 실제 resize 비율을 기록한다.
측정 실패를 음성 라벨이나 보호 성공으로 바꾸지 않는다.

MCLFIQ는 저자 제공 모델을 NFIQ 2.2.0의 `-m`으로 로딩한다. 모델 경로·SHA256·MD5와
실제 실행 로그의 모델 해시를 확인한다. 기본 NFIQ 모델 결과를 MCLFIQ로 표시하지
않으며, 종료 코드가 0이어도 특징 추출 오류가 있으면 score=null로 기록한다.

MCLFIQ 전처리에는 지문 주기 정규화가 필요하다. 원본 ACF/FFT 관측을 통과하고
허용된 해상도 사이에서도 합의하는 경우만 9 픽셀 주기로 정규화한다.
관측하지 못한 주기를 만들어 넣지 않는다. PCA 축 정렬, 흰 배경, 명시적인
보간, CLAHE(clipLimit=2, 8×8)를 쓰는 **별도 실험 어댑터**다. 논문의 반복적
선명화와 완전히 같은 전처리라는 주장은 하지 않는다. CLAHE는 원본 관측 이후에만
쓰며, 선명화가 지문 존재의 증거가 되지 않는다. 메모리 제한도 적용한다.

PCA만으로 손끝 방향의 부호를 확정할 수 없어 0°/180° 점수를 모두 기록하고
좋은 점수만 선택하지 않는다. PNG의 500 DPI는 도구 호환용 명목값이며 실제
촬영 DPI가 아니다. 모델 점수는 가시성 확률, 인식 보장, 개인정보 보호 증명이 아니다.

## 실제 실행 결과와 한계

30장 / 67개 후보에서 원본 ridge signal은 24개, 안정적인 주기 정규화 및
MCLFIQ 계산은 5개에서 가능했다. 이 숫자는 사람 정답과 비교한 정확도가 아니다.
나머지 62개에는 MCLFIQ 점수를 부여하지 않았다. 사람이 검토한 가시성 정답은
아직 0개이며 가시성 정확도는 null이다. **현재 어댑터의 MCLFIQ를 단독 적용
판정기로 채택할 근거가 없다.** 주기 관측 실패가 품질 점수 입력을 제한한다.

다음에는 사람 검토 결과와 기존 원본 관측값을 비교하고, 불확실·측정 불가 비율을
포함해 보고한다. 같은 사람/촬영 그룹의 누출을 막고, 가시성 양성 재현율과
음성 오적용률을 분리해야 한다. 작고 불명확한 표본에서는 패치 수로 신뢰도를
부풀리지 않는다. 일부 중복 검토로 사람 간 일치도도 확인하는 것이 필요하다.
독립 성능 주장은 별도 촬영 그룹과 고정된 평가 절차가 있어야 가능하다.

## 실행

```powershell
python ai/scripts/prepare_visibility_roster_v1.py --training-manifest <verified-training-manifest> --historical-registry <verified-GT7-registry> --output <new-private-project>
powershell -NoProfile -File ai/platform/windows/start_visibility_review.ps1 -PythonPath <python.exe> -RosterPath <roster.private.json> -StatePath <private-state>
python ai/scripts/photo_visibility_diagnostic_v1.py --roster <roster.private.json> --state <private-state> --output <new-private-diagnostic> --runtime-config <runtime.private.json>
```

Runtime JSON requires absolute executable/model/model_info paths and their SHA256
fields. Model-info Path and MD5 must refer to the supplied author model. Runtime and
weights remain private; redistribution licensing was not established in this task.

검증: 30개 테스트 통과. `python -m unittest -v test_photo_visibility_v1 test_photo_pad_annotation_v1`
(run from ai/scripts). Tests use synthetic images. Local browser smoke checks cover
selection, explicit review, persistence and label ZIP export on a synthetic fixture.
The real 30-image project remains unreviewed; no human judgments were invented.

Sources: [MCLFIQ paper](https://arxiv.org/html/2304.14123v2),
[author model](https://jannis-priesnitz.de/wp-content/uploads/2025/03/MCLFIQ_model.zip),
[NFIQ 2.2.0 release](https://github.com/usnistgov/NFIQ2/releases/tag/v2.2.0).
