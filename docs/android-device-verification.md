# Android 화면 흐름 검증

`WorkflowDeviceTest`는 합성 픽셀로 다음 경로를 Android에서 실행한다.

1. 사진 로드 → 영역 추가·삭제 → 설정 → 로컬 Mock → 원본/처리본 전환 → 실제 MediaStore 사본 저장 → 원본 파일 불변 확인.
2. 실제 Android FileProvider에 카메라 결과에 해당하는 합성 JPEG 기록 → 편집 화면 도착 → 임시 촬영 파일 정리.
3. 손상 파일 입력 → 갤러리·카메라 재시도 버튼 확인.

테스트가 만든 갤러리 항목만 종료 시 삭제한다. API 29 이상 기기에서 실행하며 실제 지문 영상은 사용하지 않는다. 사진 선택기·외부 카메라 앱의 결과는 테스트 경계에서 주입하므로 실제 촬영, 외부 앱의 URI 권한 행사, Android 8·9 시스템 권한 창 검증과 구분한다.

```powershell
cd android
$env:JAVA_HOME = 'C:\Program Files\BlueJ\jdk'
.\gradlew.bat connectedDebugAndroidTest --max-workers=4 --console=plain
```

대상 에뮬레이터만 연결하거나 `ANDROID_SERIAL`로 대상을 지정한다. `app/build/reports/androidTests/connected/debug/` 보고서에서 실제 실행 결과를 확인한다. 기기 연결이 없거나 빌드만 성공한 상태를 기기 테스트 통과로 기록하지 않는다.

별도 수동 확인: 실제 휴대폰에서 카메라 촬영·취소, 갤러리 선택·취소, 화면 회전, 작은 화면, 저장 후 갤러리 열기, Android 8·9 권한 허용·거부. 관련 테스트 결과와 남은 범위는 작업 기록에 기록한다.

Android 미리보기 시스템 이미지에서 기존 Espresso 3.6.1의 `InputManager.getInstance` 리플렉션 오류가 재현되어 테스트 의존성을 Espresso 3.7.0 / AndroidX JUnit 1.3.0으로 맞췄다. 해당 수정은 [AndroidX Test 공식 릴리스 노트](https://developer.android.com/jetpack/androidx/releases/test#espresso-3.7.0)에 기록되어 있다. 앱 배포용 의존성은 이 변경의 대상이 아니다.
