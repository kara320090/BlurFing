# 2026-10-20 이봉헌 — Android 구현 마무리

## 작업 범위

사용자가 센서 프로그램의 GitHub 반영은 이미 끝냈다고 확인했으므로 해당 커밋을 반복하지 않고 Android를 진행했다. 기존 `data/`의 미커밋 파일 5개는 보존한다. 학교 Ubuntu 실제 연결은 사용자가 다음 날로 지정한 범위를 유지한다.

V2 전용 SharedPreferences, 사진 없는 준비 상태 조회, 지원 엔진 확인, 로컬 HTTP 오류 안내를 연결했다. 기존 카메라 URI·권한 전달·대기 복원과 임시 파일 정리를 재사용했다. 전체 사진함 읽기 권한 선언은 제거하고 사진 선택기/카메라 결과에 부여된 URI 권한을 사용한다.

원본 좌표에서 같은 영역을 선택하는 1–4배 비교를 추가했다. RGB PNG 행을 스트리밍해 최대 1024픽셀 표시 영역만 보관하며 원본·반환 PNG와 마스크는 바꾸지 않는다. 검증한 처리 PNG만 byte-identical 사본으로 공유하고 읽기 권한만 전달한다. 공유창을 연 것을 저장 완료로 표시하지 않는다.

SavedStateHandle에는 UUID·해시·시각·저장 요청 ID만 남기고 private cache에 원본·응답의 immutable snapshot을 쓴다. 복원 시 기존 전체 계약 검증기를 다시 사용한다. Android가 화면 정지 때 이미 저장한 이전 Bundle도 유효한 사본을 참조하도록 한 작업 안의 이전 snapshot을 유지하며 명시적인 폐기·24시간 만료로 정리한다. 취소된 IO가 dispatcher에서 돌아오는 시점에도 준비된 공유 파일·미부착 snapshot을 정리한다. 중단된 업로드·저장·공유를 자동 재실행하지 않는다.

기존 V1 Gaussian/Mock·사진 편집·PNG/JPEG 저장·평가 메타데이터는 다른 경로로 유지했다. 새 코드는 점수·성공률을 생성하지 않는다. [구현·인수 범위](../android-completion-20261020.md)를 따른다.

## 검증 방법

JDK 21.0.12.1+1, Gradle 8.9, Android compile/target 35, min 26을 사용한다. Windows Robolectric 단위 검사와 `BlurFing_Test` 에뮬레이터의 계측 검사에 공개 합성 자료만 사용한다.

```powershell
.\gradlew.bat :app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug :app:assembleRelease --no-daemon --max-workers=2
```

새 단위 검사는 실제 loopback GET·상태별 오류·계약/엔진 목록·응답 크기·취소, 설정 유지, 미지원 엔진 업로드 차단, 늦은 준비 응답, snapshot 만료·경로 제한·재검증·이전 OS Bundle, 촬영 사본 수명, 정확한 공유 PNG와 권한, 취소 handoff 정리, 원본 좌표의 확대 픽셀을 대상으로 한다.

`ExperimentalCompletionDeviceTest`는 실제 V2 Activity에서 합성 URI 입력 → 실제 TCP 준비 조회 → 제어된 HTTP 결과의 픽셀/마스크 검증 → 비교 → Activity 재생성 → 공유 확인 취소를 검사한다. 사진 선택창·카메라 앱 자체나 실제 AI 추론을 실행한 것으로 보고하지 않는다.

## 최종 실행 결과

| 항목 | 결과 |
|---|---|
| 전체 Android 단위 검사 | 209개 중 **208개 통과·1개 선택 검사 건너뜀**, 실패·오류 0 |
| 새 단위 검사 | 준비 상태 5개 + 마무리 상태·파일·복원 17개 = **22개 통과** |
| 에뮬레이터 회귀 | V1·V2 화면/저장/공유/종료/교체 및 새 V2 HTTP·재생성 **21개 통과** |
| V2 카메라 전달 URI | 실제 앱 FileProvider의 합성 JPEG, EXIF 90도 정규화 후 6×8 입력, 앱 소유 임시 출력 정리 **1개 통과** |
| 고유 에뮬레이터 검사 합계 | **22개 통과**. 실제 외부 카메라 앱을 촬영한 검사는 아니다. |
| debug·계측 APK | 빌드·에뮬레이터 설치 성공 |
| release | 서명 없는 release 빌드 성공, Play 업로드 없음 |
| lintDebug | **오류 0**, 경고 12·정보 2 |
| 자료 보존 | 기존 data 파일 5개 SHA256 일치, 제품 APK에 테스트 PNG assets 미포함 |

최종 전체 Gradle 실행은 `BUILD SUCCESSFUL`이며 단위 XML 집계와 두 기기 로그의 `OK (21 tests)`·`OK (1 test)`로 확인했다. 추가 카메라 검사는 계측 APK만 다시 빌드해 해당 메서드 1개를 실행했다. 앱 코드·debug APK는 전체 회귀를 통과한 것과 같다. 로그는 작업 폴더 바깥 `work/android-completion-final-build.log`, `work/android-completion-device-final.log`, `work/android-completion-camera-build.log`, `work/android-completion-camera-device.log`에 보관한다.

개발용 설치 APK는 바탕화면 `BlurFing_Android_20261020/BlurFing-Android-20261020-debug.apk`에 복사했다. SHA256은 `31299C6143085AE339A01C342A58BFE1A8063A8AA44330C93E93E480F0F6858B`이며 빌드 출력과 복사본이 일치한다. 사용 안내와 검사 요약 JSON을 함께 제공한다.

## 실행하지 않은 범위

- 학교 Ubuntu 설치·외부 HTTPS 연결과 실제 모델 성공 처리는 다음 날 확인한다.
- 실물 휴대폰의 카메라/외부 사진 제공자/문서 저장 제공자/공유 수신 앱 전체 흐름과 저메모리 호환성은 확인하지 않았다.
- 실제 센서·독립 자료를 이용한 AI 보호 성능을 이번 합성 검사에서 측정하지 않았다.
- `assembleRelease`는 배포 서명이 없는 빌드 확인이며 Play 업로드·심사를 진행한 것으로 표시하지 않는다. 사용자에게 전달할 설치본은 debug APK다.
