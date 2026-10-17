# 2026-10-17 Android 사진 AI 실험 종료·저장 상태

관련: BF-04·05·06·12 / [12번 수용 규칙](../android-next-12-experimental-exit.md).
담당: 이봉헌, Android·시스템 통합. 최신 팀 main `6e17794`를 기준으로 작업했다.

## 문제와 변경

기존 V2 실험 화면은 처리가 끝나면 시스템 뒤로가기와 일반 화면 복귀를 즉시 실행해 저장하지 않은 결과를 잃을 수 있었다. 또한 진행 중 종료 확인창의 설명이 작업 완료 뒤에도 이전 상태로 남을 수 있었다.

종료 판단을 한 Compose 구성으로 연결했다. 미저장 결과는 `계속 보기` 또는 `저장하지 않고 종료`를 확인하며, 입력·처리·저장·외부 저장 위치 선택 대기는 `취소 후 종료`를 확인한다. 완료 후에는 현재 결과에 맞게 안내를 갱신하고, 보존할 결과가 없거나 저장이 검증됐으면 확인창을 닫는다. 확인 대기는 저장 상태 복원 대상이며 사진·결과를 프로세스 종료 후 복원하는 기능은 추가하지 않았다.

ViewModel은 현재 요청의 저장 PNG를 다시 읽어 길이·SHA256을 검증한 뒤에만 저장 완료 ID를 기록한다. 저장창 취소·검증 실패·다른 요청의 늦은 저장 응답은 새 결과를 저장 완료로 바꾸지 않는다. 같은 결과의 사본이 이미 검증됐다면 추가 저장을 취소해도 그 사실을 유지한다. 원본 파일·기존 완성 사본과 V1·AI·백엔드 처리 계약은 유지한다.

정적 검사에서 기존 V2 업로드 함수의 `SuspiciousIndentation` 1건과 debug 통신 설정의 `includeSubdomains` 누락 3건을 확인했다. 메모리 검사 조건에 중괄호를 추가하고 이후 구문의 들여쓰기를 정리했다. debug 설정은 기존 세 호스트에 `includeSubdomains="false"`를 명시했으며 허용 호스트나 release 설정을 늘리지 않았다.

## 실행한 검증

Windows, JDK 21.0.12.1, Android SDK 35, Gradle 8.9에서 실행했다.

```powershell
# android/에서 실행
.\gradlew.bat :app:assembleDebug --no-daemon --max-workers=2
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebugAndroidTest :app:lintDebug --no-daemon --max-workers=2

adb -s emulator-5558 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5558 install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5558 shell am instrument -w -r -e class com.blurfing.app.experimental.ExperimentalExitDeviceTest,com.blurfing.app.BackNavigationDeviceTest com.blurfing.app.test/androidx.test.runner.AndroidJUnitRunner
```

- debug APK·계측 APK 빌드 완료.
- 단위 시험 177개: **176개 통과, 실패·오류 0, 건너뜀 1**. 건너뛴 항목은 비공개 전체 해상도 사진을 선택적으로 읽는 `optionalPrivateFullResolutionPillowSourceCrosscheckNoPhotoBundled`이며 이번에 해당 자료를 제공하지 않았다.
- 신규 `ExperimentalPhotoExitTest` **7개 모두 통과**: 실제 파일을 사용하는 제어된 ContentProvider에서 저장·재읽기, 해시 불일치·불완전 사본 정리, 저장창 취소, 이전 ticket, 새 실행, 추가 저장 취소, 엔진 변경을 검사했다. 공개 합성 PNG·마스크를 사용했다.
- API 37.1 테스트 에뮬레이터에서 **7개 모두 통과**. 최초 63.83초, lint 설정 수정 후 최신 APK 재검증 78.081초. 신규 종료 확인 4개는 실제 BackHandler·종료 버튼·확인창의 저장 상태 복원·작업 완료 후 안내 전환·저장 후 확인 해제를 확인했다. 기존 뒤로가기 3개는 일반 편집·처리 취소·Activity 재생성·늦은 응답 회귀를 검사했다.
- lint **오류 0·경고 12**. 기존 4개 오류를 수정한 뒤 단위 시험·debug/계측 빌드·lint를 함께 재실행해 `BUILD SUCCESSFUL`을 확인했다. 남은 경고는 target/dependency 버전·기존 Compose API 사용 등의 항목이며 이번 범위에서 버전을 바꾸지 않았다.

첫 검증에서는 화면 시험의 잘못된 `assertDoesNotExist` import로 계측 컴파일이 실패했다. import를 수정한 뒤 단위 시험에서 실패 상태가 갱신되자마자 임시 파일 정리 완료를 확인해 시점 경쟁을 발견했다. 공급자의 정리 완료 신호를 기다리도록 시험을 보완했으며 최종 전체 단위 시험과 계측 빌드는 위 결과로 완료했다. 의도적으로 손상시킨 입력의 decoder 로그는 기존 실패 입력 시험에서 발생한다.

## 범위와 인수인계

푸시 직전 팀원의 `a6d89cb`(Docker 기반 백엔드 Mock HTTPS 배포 구성)와 후속 `dde8908`(재배포 Git 추출 경로 수정)이 추가됐다. 변경은 백엔드에 한정되며 Android 파일은 바꾸지 않았다. 기존 작성자와 커밋을 보존하는 merge로 합쳤고, 두 번째 작업 커밋에 Android 검증 자료를 함께 기록한다. 병합된 Python 실행 진입점·도구 5개의 구문 검사를 통과했다.

병합 후 `backend/`의 `python -m pytest test_deployment.py test_measure_photo_ai.py -q`는 **39개 통과, 경고 1개**(기존 tar 추출 API 안내)였다. 최초 실행은 기존 검증 환경에 NumPy가 없어 V2 liveness 시험 1개가 실패했다. 공유 가상환경을 변경하는 대신 작업 전용 경로에 배포 요구 버전인 NumPy 2.3.5를 설치해 재실행했다. 이 시험은 합성·TestClient·제어된 실행 도구를 사용하며 실제 Docker 기동이나 모델 성능 측정을 수행하지 않는다.

실제 AI 모델·개인 사진·센서·외부 배포 서버를 이번 검증에서 실행하지 않았다. 화면 시험은 합성 표시 상태이며 모델·마스크 검증이나 보호 성공률의 근거로 재사용하지 않는다. 실물 휴대폰·Android 8/9의 외부 저장 공급자·대형 실제 입력은 후속 확인 대상이다. 저장 이후 사용자가 사본을 삭제·수정했는지를 감시하지 않는다.

기존 체크아웃의 미커밋 데이터 파일은 별도로 보존했고 Android 코드·공개 합성 시험·검증 문서만 커밋했다. AI 도구 사용: Codex로 Kotlin 변경·시험 작성·로컬 검증을 진행했다. 담당자의 최종 검토는 별도 진행한다.
