# AI

주담당: 유재윤

## 담당 범위

BlurFing의 지문 변환 알고리즘 및 성능 검증 파트를 담당합니다.

현재 동결된 기준 파이프라인은 다음과 같습니다.

- Renderer: natural_auto_04
- Compositor: boundaryblend_02
- Matching evaluation:
  - NBIS 5.0.0
  - SourceAFIS

## 현재 상태

- 기술 파이프라인 구현 완료
- Linux NBIS runtime 및 matcher 검증 완료
- SourceAFIS matcher 검증 완료
- NBIS 공식 소스 기반 clean rebuild 재현 완료
- 개발용 ROI 평가 완료
- 최종 독립 촬영본 검증은 추후 진행 예정

현재 상태:

TECHNICAL_PIPELINE_COMPLETE=true
FINAL_INDEPENDENT_VALIDATION_COMPLETE=false

## 데이터

실제 지문·손 사진 및 생체정보 데이터는 공개 저장소에 포함하지 않습니다.

사용자는 별도의 입력 이미지를 준비해야 합니다.

## 제한사항

현재 개발 데이터에서는 변환 후 NBIS 및 SourceAFIS matching score 감소가
관찰되었으나, 일반적인 지문 보호 효과가 입증된 것은 아닙니다.

또한 일부 결과에는 synthetic ridge의 규칙성과 texture seam이 남아 있습니다.
최종 독립 검증은 새 사람/다른 날짜의 촬영본으로 진행할 예정입니다.
