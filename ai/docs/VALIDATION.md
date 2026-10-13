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

## SAM pad development evaluation

See [SAM pad evaluation](../results/sam_pad_evaluation_summary.md): macro IoU 0.8458, coverage 7/7, approval false due to sample-specific outside-GT leakage. No downstream transform or matcher run.

### SAM foreground follow-up

Macro pad IoU 0.9051, coverage 7/7; DET-03 outside-GT ratio 14.16% versus 38.67%. Other sample masks are unchanged. The comparative metrics improve but automatic pad approval is withheld because DET-03 still lacks a verified proximal boundary. No transform/matcher run. See [follow-up evidence](../results/sam_pad_foreground_refinement_summary.md).

### Proximal evidence follow-up

IoU and coverage are unchanged (macro 0.9051, 7/7). DET-03 lacks agreeing observed crease/appearance evidence; `proximal_boundary_unobserved` blocks approval. 56 tests pass, no downstream execution. See [proximal evidence result](../results/sam_pad_proximal_summary.md).

### Crease-optional estimator GT7 rejection

Unmodified estimator, seven human nonempty positive masks: macro IoU 0.4913, coverage 7/10, false pad regions in extra samples. Approval false. No ambiguous/non-target annotation exists in this set; those branches are tested only synthetically. No downstream transform/matcher. [Detailed GT7 result](../results/distal_pad_GT7_summary.md).
