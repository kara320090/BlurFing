# BlurFing Google Play 배포 준비

2026-10-21 기준 다음 후보는 `com.blurfing.app`, `versionName=1.0.2`, `versionCode=3`이다.
콘솔에서 기존에 사용한 최대 코드가 2임을 확인하고 정했다. 실제 업로드 직전에 모든 트랙의 최대 코드를 다시 확인한다.
Android 사진 AI의 HTTPS 연결 변경을 포함하며 고속 모드 선택은 서버 설정 `fast_v32`에서 수행한다.

## 빌드와 실제 배포 구분

2026년 8월 31일부터 새 모바일 앱과 업데이트의 제출 대상 API는 36 이상이다.
이 프로젝트는 compileSdk와 targetSdk를 36으로 맞추고 API 36을 지원하는 AGP 8.10.1,
Gradle 8.11.1을 사용한다. Gradle 배포 ZIP은 공식 SHA256으로 고정한다.
최소 실행 버전은 Android 8 API 26을 유지한다.

- [Google Play 대상 API 요구사항](https://support.google.com/googleplay/android-developer/answer/11926878?hl=ko)
- [AGP 8.10 호환성](https://developer.android.com/build/releases/agp-8-10-0-release-notes)
- [Android 16 대상 동작 변경](https://developer.android.com/about/versions/16/behavior-changes-16)

서버 주소는 사용자가 확인한 HTTPS 주소를 사용한다. release는 localhost HTTP를 허용하지 않는다.
SSH와 adb reverse를 이용하는 기존 USB 시연 구성은 debug 빌드용이다.
사진 V2는 `/v2/ready`를 먼저 검사하고 그 경로가 404일 때만 단독 서버의 `/ready`를 확인한다.
V1 또는 Mock 준비 응답을 실제 V23 서버로 받아들이지 않는다. `/ready` 통과 후 실제 사진 처리와 저장을 확인한다.

## 로컬 후보 생성

JDK 21과 SDK 36을 준비하고 Android 폴더에서 다음을 실행한다.
`blurfingRevision`에는 실제 소스 커밋의 7~40자리 해시를 넣는다.

```powershell
./gradlew.bat testDebugUnitTest testReleaseUnitTest assembleDebug assembleDebugAndroidTest bundleRelease lintRelease -PblurfingRevision=<commit> --max-workers=2
```

`app/build/outputs/bundle/release/app-release.aab`는 기본 구성에서 **서명 없는 후보**다.
AAB를 휴대폰에서 직접 설치하거나 Google Play에 업로드할 수 있는 완성본으로 안내하지 않는다.
로컬 debug APK도 Play 업로드 파일이나 기존 Play 앱의 동일 서명 업데이트가 아니다.

## 기존 업로드 키로 서명

Play 앱 서명은 Google이 관리하는 **앱 서명 키**와 개발자가 보관하는 **업로드 키**를 구분한다.
기존 앱의 새 AAB에는 콘솔에 등록된 업로드 키와 일치하는 개인키가 필요하다.
콘솔에서 내려받는 DER/PEM 공개 인증서는 그 개인키를 대신하지 못한다.

이전 로컬 배포에서 사용하는 Windows 자료가 있으면 다음 명령으로 같은 키를 재사용한다.
`ExpectedUploadSha256`에는 콘솔에서 확인한 업로드 키 인증서의 지문을 지정한다.
기존에 수락된 AAB의 인증서도 대조 자료로 쓸 수 있으며 앱 서명 키와 혼동하지 않는다.

```powershell
./scripts/Build-PlayBundle.ps1 -JavaHome '<JDK 21 경로>' -ExpectedUploadSha256 '<업로드 인증서 SHA256>'
```

기본 키 위치는 `%USERPROFILE%/.blurfing/signing/`이다. 기존 `blurfing-upload.jks`와
현재 Windows 사용자 계정으로 복호화 가능한 `upload-password.dpapi`를 읽는다.
키를 자동 생성하거나 교체하지 않는다. 키가 없거나 인증서가 다르면 빌드 전에 중단한다.
암호는 이번 빌드의 프로세스 환경에만 전달하고 종료 시 원래 환경을 복원한다.
debug와 release 단위 검사·lint·서명 AAB를 확인한 뒤 결과를 반환한다.
개인키와 암호는 배포 자료에 넣지 않는다.

1. 기존 배포를 만든 PC나 팀 보관소에서 `.jks` 또는 `.keystore` 파일을 확인한다.
2. 소유자가 Android Studio의 Generate Signed Bundle 또는 기존 검증된 서명 도구에서
   Android App Bundle과 기존 키를 선택한다. 비밀번호는 본인의 로컬 입력 창에서 직접 입력한다.
3. 서명된 AAB의 인증서 SHA256을 콘솔의 **업로드 키** 인증서와 비교한다.
4. 패키지, 버전 코드, API 36, release의 debuggable=false, ZIP 구조와 서명을 확인한다.
5. 키와 비밀번호, 개인 사진, 모델 파일을 Git이나 배포 ZIP에 포함하지 않는다.

기존 키가 없으면 계정 소유자가 공식 업로드 키 재설정 절차를 검토한다.
새 키를 만들기만 해서는 기존 업로드 키가 교체되지 않는다. 키 생성·교체·재설정 신청은 이 문서가 수행하지 않는다.

[Google Play 앱 서명과 업로드 키](https://support.google.com/googleplay/android-developer/answer/9842756?hl=ko)

## 프로덕션 제출 조건

적용 대상인 새 개인 개발자 계정은 최소 12명이 14일 연속 참여한 비공개 테스트를 완료하고
프로덕션 액세스를 신청해야 한다. 내부 테스트 배포가 이 요건을 대신하지 않는다.
버튼이 비활성인 상태에서 다른 트랙에 임의로 배포하거나 테스트 참여 기록을 만들어 내지 않는다.
스토어 등록정보와 앱 콘텐츠 설정, 실제 데이터 취급에 맞는 개인정보 안내도 완료해야 한다.

[개인 개발자 계정의 테스트 요구사항](https://support.google.com/googleplay/android-developer/answer/14151465?hl=ko)

빌드·단위 검사·에뮬레이터 검증과 학교 서버·실물 휴대폰 검증을 구분한다.
출시 완료는 콘솔의 실제 제출 또는 게시 상태를 확인한 뒤에만 기록한다.
