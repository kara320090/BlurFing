# Android 로컬 사전 작업 10개

2026-10-03에 구현한 로컬 작업이다. 커밋·푸시는 수행하지 않았다. 실제 이미지 대신 합성 사진으로 검증한다. SDK·센서와 AI 보호 효과는 이 작업의 검증 대상에 포함되지 않는다.

| 번호 | 작업 | 결과 및 상세 문서 |
|---|---|---|
| 01 | JDK 21 빌드 환경 | [경로 검증 및 환경 복원 스크립트](android-next-01-build.md) |
| 02 | 수동 손끝 영역 입력 | [임의 자동 후보 제거 및 빈 상태 안내](android-next-02-manual-regions.md) |
| 03 | 영역 편집 이력 | [실행 취소·다시 실행·전체 지우기](android-next-03-edit-history.md) |
| 04 | 선택 영역 크기 조절 | [모서리 드래그 및 너비·높이 슬라이더](android-next-04-resize.md) |
| 05 | 백엔드 준비 상태 확인 | [사진 전송 없는 GET /ready](android-next-05-readiness.md) |
| 06 | 서버 오류 안내 | [HTTP별 안내 및 제한된 오류 코드 해석](android-next-06-errors.md) |
| 07 | 출력 형식 선택 | [PNG·JPEG 및 JPEG 품질 설정](android-next-07-export-format.md) |
| 08 | 처리 사본 공유 | [전용 FileProvider와 읽기 권한](android-next-08-share.md) |
| 09 | 앱 측정 시간 | [변환·요청·디코딩의 실제 경과 시간](android-next-09-timing.md) |
| 10 | 진단 기록 내보내기 | [사진·주소·식별자·평가 점수를 제외한 JSON](android-next-10-diagnostics.md) |

기본 브랜치는 main이며, 팀원의 data 파일 4개의 기존 변경을 보존한다. 번호별 패치는 저장소 바깥의 `../android-next-batches/`에 보관한다. 같은 파일을 순차 수정하는 작업이므로 이후 번호별 반영은 01부터 순서대로 진행한다. 개발한 시점과 이후 커밋·공개 시점은 구분한다.

검증 결과: 단위 테스트 127개, Android API 37 에뮬레이터 시험 8개, Debug·시험 APK 빌드 통과. 합성 사진으로 앱 UI·저장·공유용 파일 접근·진단 파일 저장을 확인했다. 서버 상태·오류 계약은 MockWebServer로 검증했다. 외부 앱 공유 및 시스템 파일 선택 창의 수동 조작, 실제 백엔드·SDK·센서·AI 보호 성능 시험은 이번 완료 항목에 포함하지 않는다.

## 2026-10-14 10번 공개 검증

기능 구현과 검증을 두 커밋으로 반영했다. 현재 main 기준 Android 단위 테스트 131개(실패·오류·건너뜀 0), Debug 및 instrumentation APK 빌드가 통과했다. Android 테스트 에뮬레이터에서 ExpandedWorkflowDeviceTest 3개를 실행하여 영역 편집 이력·JPEG 저장·좁은 공유 파일 접근 범위·합성 진단 JSON 저장을 확인했다. 기존 2026-10-03 검증 수치는 당시 로컬 사전 작업의 결과이며, 이번 실행에서는 서버 연결 시험과 시스템 파일 선택 창의 수동 조작, 실제 SDK·센서·AI 보호 성능을 검증하지 않았다.

에뮬레이터 첫 instrumentation 실행은 시험 시작 단계에서 프로세스가 종료됐다. 앱 코드 변경 없이 실행 로그를 수집하며 재실행한 결과 3개가 모두 통과했다. 최초 종료 원인은 확정하지 않았다.
