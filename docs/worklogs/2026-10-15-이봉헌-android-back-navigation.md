# Android 11번: 시스템 뒤로가기와 처리 취소 확인

작업자: 이봉헌 / 2026-10-15

최신 main `e4a3ea1`을 기준으로 Android 앱의 화면 이동을 보완했다. 팀원들의 AI·백엔드 구현과 작성자 이력은 유지했으며, 이번 변경은 앱 탐색과 요청 취소 연결에 한정한다.

## 변경

기존 앱 화면의 뒤로가기 버튼과 달리 시스템 뒤로가기는 화면 단계와 연결되어 있지 않았다. `BackHandler`와 ViewModel의 `onBackRequested()`를 연결하여 설정·비교 화면에서는 편집으로, 편집 화면에서는 첫 화면으로 돌아가게 했다. 첫 화면에서는 운영체제 기본 동작을 유지한다.

처리 중에는 확인창을 표시한다. 계속 처리하거나 확인창을 닫으면 현재 요청을 유지하고, 취소를 선택하면 같은 사진·영역을 유지한 설정 화면에서 다시 시작할 수 있다. 취소 확인 중 처리가 완료되면 확인창을 닫는다. 확인창 대기는 Activity 재생성 때 복원한다. 기존 취소·화면 이동의 식별자 무효화 로직으로 늦은 처리·저장 결과와 오래된 저장 권한 응답을 적용하지 않는다.

## 자동 검증

- JDK 21, Gradle 8.9, compile SDK 35에서 `testDebugUnitTest assembleDebug assembleDebugAndroidTest --max-workers=4 --console=plain` 성공.
- Android 단위 테스트 **136개 통과**, 실패·오류·건너뜀 0개. 새 `BackNavigationTest` 5개가 포함된다.
- 첫 화면의 기본 동작 유지, 설정에서 편집 복귀, 사진·영역·설정 유지, 편집 복원용 임시 사본 정리, 비교에서 편집 복귀, 처리 중 확인만으로 요청을 취소하지 않음, 확인 후 취소와 늦은 응답 무시를 합성 이미지로 확인했다.
- debug APK와 계측 테스트 APK를 빌드했다. 손상된 이미지 입력 테스트의 decoder 로그와 기존 deprecated API 경고는 빌드 실패가 아니다.

Android API 37.1 에뮬레이터에서 `BackNavigationDeviceTest` **3개가 모두 통과**했다 (`OK (3 tests)`, 77.075초). 시스템 Back 입력, 계속 처리·확인창 닫기·확정 취소, Activity 재생성, 확인 중 처리 완료를 확인했다. 서버 경로는 기기 내부 loopback HTTP fixture이며 결과는 명시적으로 Mock이다. 다른 기존 기기 테스트 전체를 재실행한 결과로 집계하지 않는다.

```text
adb -s emulator-5558 shell am instrument -w -r -e class com.blurfing.app.BackNavigationDeviceTest com.blurfing.app.test/androidx.test.runner.AndroidJUnitRunner
```

## 실행 환경 문제 기록

초기 에뮬레이터에서는 APK 설치가 응답하지 않아 재시작했다. 이어 Android System UI의 응답 없음 창이 앱의 창 포커스를 가져가 Espresso Back 입력 3건이 실패했다. 해당 창을 닫아 System UI를 재시작한 뒤에는 계측 시작 전 프로세스 종료가 발생했다. 에뮬레이터 메모리·CPU 할당을 조정하고 다시 부팅한 뒤 동일 APK로 재검증하여 위 3건이 통과했다. 초기 실패 시도를 통과 건수에 포함하지 않았다.

실물 휴대폰의 뒤로가기 제스처, 배포 서버, 실제 AI 보호 효과와 센서 매칭 성능은 이번 검증 범위에 포함하지 않는다. 원본 개인 사진·지문 자료와 지출증빙은 커밋하지 않는다.
