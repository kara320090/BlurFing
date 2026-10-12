# Frozen pipeline

1. Private 입력 이미지를 읽고 EXIF 방향을 적용합니다.
2. 자동 fingertip/ROI 및 관측 pitch를 처리합니다.
3. natural_auto_04 renderer로 독립 synthetic field의 appearance를 생성합니다.
4. boundaryblend_02 compositor로 원본 base와 경계 detail을 합성합니다.
5. 구조 검사와 실패 계약을 거쳐 returned RGB를 결정합니다.
6. NBIS에서 원본 self 및 원본→반환본을 평가합니다.
7. 같은 pair를 SourceAFIS에서 별도로 평가합니다.
8. ROI metadata, score, status, hash 및 audit/result를 기록합니다.

Private 원본 입력 → EXIF 방향 적용 및 RGB 읽기 → 자동 손끝 후보와 원본 관측 pitch → 독립 synthetic ridge field → natural_auto_04 appearance profile → boundaryblend_02 compositor → 기존 구조 검사 → returned RGB → matcher별 결과 기록.

원본 skeleton/minutiae를 합성 field에 복사하지 않습니다. boundaryblend_02는 원본 base를 유지하고 signed-distance transition, crease buffer와 residual texture를 사용합니다. renderer 및 구조 검사 수치 파라미터는 동결했습니다.

SourceAFIS 구조 검사 기준은 양쪽 특징점 >=10, 같은 좌표·종류 Dice <=0.9, 특징점 변화 >=2, skeleton XOR/union >=0.05입니다. 실패한 영역은 원본을 반환하며 마스크 밖 픽셀을 보존합니다. 이 기준은 보호 효과 판정 기준이 아닙니다.

NBIS는 raw8/500 DPI → MINDTCT V2 → lfs2nist_format으로 전체 특징점을 추출합니다. MATCH 단계에서만 bz_prune(max150), min_computable_minutiae=10, BOZORTH3를 적용합니다. RAW 단계에는 150 제한이 없습니다. retry 없이 오류와 insufficient_features를 구분합니다.

SourceAFIS는 Java 11 target bridge와 Linux os.pathsep classpath를 사용합니다. 두 matcher 점수는 다른 척도로 별도 기록합니다. 실제 반환 RGB의 기존 width-normalized ROI 규칙을 사용하며 새 crop 기준이나 threshold를 만들지 않습니다.

공개 사본은 사용하지 않는 historical helper entry points를 제외하고 필요한 함수와 직접·전이 custom dependencies를 포함합니다. 경로와 Linux wiring만 공개 layout으로 옮겼습니다. 개인정보 manifest, 원본 영상, runtime binary는 공개하지 않습니다.

공통 nbis_matcher/sourceafis_matcher facade가 runtime OS를 선택합니다. Windows는 같은 공통 알고리즘을 사용하며 출력 경로만 system temp로 이동합니다.
