# 2026-10-18 Android 사진 AI 실험 결과 교체 확인

관련: BF-04·05·06·12 / [13번 수용 규칙](../android-next-13-experimental-replacement.md).
담당: 이봉헌, Android·시스템 통합. 팀 main `8ea4974`를 기준으로 작업했다.

## 문제와 변경

V2 화면은 저장하지 않은 결과가 있어도 다른 엔진을 누르거나 사진을 바꾸거나 AI를 다시 실행하면 결과를 바로 지웠다. 특히 이미 선택된 엔진을 다시 누르는 것만으로도 결과와 저장 완료 상태가 초기화됐다.

같은 엔진 재선택은 상태를 그대로 유지한다. 다른 엔진·사진·재실행은 변경된 결과가 미저장인 경우에만 교체를 확인한다. `계속 보기`와 확인창 뒤로가기는 원본·결과·설정을 유지하며 `저장하지 않고 진행`에만 지정 작업을 한 번 실행한다. 사진 선택은 실제 URI 반환 후 확인하므로 시스템 선택창을 취소하면 새 입력을 읽지 않고 기존 결과를 유지한다. 승인 뒤 입력 읽기에 실패했을 때는 기존 결과를 복구하지 않는다는 범위를 수용 규칙에 명시했다.

대기 결정은 ViewModel에서 세대·현재 결과 객체·일회성 ticket에 연결한다. 오래된 확인·취소와 중복 확인은 다른 결정을 실행하거나 지우지 못한다. 확인 중 다른 교체·서버 수정·저장을 막으며, 외부 저장 위치 선택 대기도 활성 작업에 포함해 엔진 변경과 재실행을 차단한다. 기존 저장 ticket 만료 시험은 명시적 작업 취소 뒤 새 사진 교체를 승인하는 흐름으로 갱신했다.

같은 ViewModel을 유지한 화면 재생성에서는 대기 결정을 다시 표시한다. 새 사진 URI와 application context는 ViewModel에 일시 보관하며 사진·URI·실행할 작업을 saved-state Bundle에 추가하지 않았다. 프로세스 종료 후 원본·결과 복원 기능은 추가하지 않았다. 원본 파일과 이미 검증된 사본, 기존 V1과 AI·백엔드 계약을 유지한다.

## 실행한 검증

Windows, JDK 21.0.12.1, Android SDK 35, Gradle 8.9에서 실행했다.

```powershell
# android/에서 실행
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug --no-daemon --max-workers=2

adb -s emulator-5558 install -r app/build/outputs/apk/debug/app-debug.apk
adb -s emulator-5558 install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
adb -s emulator-5558 shell am instrument -w -r -e class com.blurfing.app.experimental.ExperimentalReplacementDeviceTest,com.blurfing.app.experimental.ExperimentalExitDeviceTest com.blurfing.app.test/androidx.test.runner.AndroidJUnitRunner
```

- 전체 Gradle 작업 `BUILD SUCCESSFUL`(5분 53초). debug APK와 계측 APK를 빌드했다.
- 단위 시험 **187개 중 186개 통과**, 실패·오류 0, 건너뜀 1. 비공개 전체 해상도 사진이 필요한 `optionalPrivateFullResolutionPillowSourceCrosscheckNoPhotoBundled`는 해당 자료를 제공하지 않아 건너뛰었다.
- 신규 `ExperimentalPhotoReplacementTest` **9개 모두 통과**: 동일 엔진 상태 보존, 엔진 교체 승인·취소, 재실행 한 번 실행, 사진 선택창 취소·새 URI 지연 읽기, 이전 결정의 늦은 승인·취소, 중복 승인, 다른 작업의 결정 덮어쓰기 차단, 저장 위치 선택 대기를 검사했다. 기존 저장·종료 시험에 저장이 검증된 결과의 동일 엔진 재선택·사진 교체 1개를 추가했고 해당 클래스는 **8개 모두 통과**했다.
- API 37 테스트 에뮬레이터에서 **8개 모두 통과**(49.956초). 신규 교체 확인 4개는 계속 보기·명시적 진행·확인창 뒤로가기·구성 복원 뒤 기존 결정 재표시를 검사했다. 기존 종료 확인 4개는 복귀 버튼·시스템 뒤로가기·종료 확인 상태 복원·작업 완료와 저장 검증 뒤 안내 갱신을 검사했다.
- lint **오류 0·경고 12·정보 2**. 경고는 기존 target/dependency 버전·Compose API 사용 등의 항목이며 버전 변경은 하지 않았다. `git diff --check`를 통과했다.

신규 구성 복원 시험은 외부에 유지된 합성 결정 메타데이터를 실제 교체 확인 구성에 다시 공급한다. 실제 Activity 회전·프로세스 종료 후 복원이나 시스템 사진 선택 공급자를 자동 실행한 시험은 아니다. 실제 사진·URI가 포함된 saved-state Bundle을 생성하지 않는다.

## 검증 범위와 인수인계

공개된 합성 RGB PNG·마스크와 제어된 파일 공급자를 사용한다. 실제 AI 모델·개인 사진·센서·외부 배포 서버는 이번 작업에서 실행하지 않는다. 합성 상태와 확인창 시험을 보호 성능·실제 사진 선택 공급자 전반·실물 휴대폰 호환성의 근거로 사용하지 않는다.

팀원의 `8ea4974`는 백엔드 Mock HTTPS 배포 검증 문서·추적 자료 변경이며 Android 코드는 바꾸지 않았다. 이를 fast-forward로 반영하고 기존 작성자와 이력을 유지했다. 외부 서버를 재배포하거나 팀원 모델을 수정하지 않았다.

기존 체크아웃의 미커밋 파일 14개가 작업 전과 같은 SHA256임을 확인해 보존했다. 공개 저장소에는 Android 코드·합성 시험·기술 문서만 반영한다. AI 도구 사용: Codex로 Kotlin 변경·회귀 시험 작성·로컬 검증을 진행했다. 담당자의 최종 검토는 별도 진행한다.
