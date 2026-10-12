# Linux development-only validation

## NBIS

| Sample | Original features | Transformed features | Self | Original→Transformed |
|---|---:|---:|---:|---:|
| DEV-01 | 39 | 34 | 320 | 4 |
| DEV-02-R1 | 49 | 37 | 499 | 7 |
| DEV-02-R3 | 58 | 26 | 499 | 9 |

## SourceAFIS

| Sample | Original features | Transformed features | Self | Original→Transformed |
|---|---:|---:|---:|---:|
| DEV-01 | 31 | 20 | 373.5211 | 1.3059 |
| DEV-02-R1 | 34 | 15 | 408.4964 | 1.2415 |
| DEV-02-R3 | 33 | 13 | 396.8380 | 0 |

세 development ROI에서 두 matcher 모두 original→transformed score가 self-match보다 크게 낮았습니다.

NBIS와 SourceAFIS score scale은 다르므로 직접 비교하지 않습니다. 작은 development sample의 결과이며 일반적 보호 성능이나 식별 불가능성·보안을 보장하지 않습니다. insufficient_features/추출 실패는 보호 성공으로 집계하지 않습니다.

FINAL_INDEPENDENT_VALIDATION_COMPLETE=false
