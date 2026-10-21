# 2026-10-21 Play 배포 후보 검증

이 문서는 1.0.2(3)의 최초 빌드 검증 기록이다. 아래 미게시 상태를 확인한 뒤 같은 날 13:31(한국 시간)
실제 내부 테스트에 출시했고, 등록 계정의 Play 설치 버튼을 확인했다.
현재 후속 후보는 [자동 손끝 탐지 1.0.3(4)](AUTOMATIC_FINGERTIPS_20261021.md)이다.

## 결과

후보는 `com.blurfing.app`, `1.0.2` / 코드 `3`, 최소 API 26 / 대상 API 36이다.
이전 내부 테스트에서 수락된 AAB의 업로드 인증서와 기존 PC의 개인키 인증서를 대조한 뒤
같은 키로 서명했다. 개인키와 DPAPI 암호 파일은 저장소 밖에 보관했다.
최종 파일의 소스 커밋, SHA256 및 서명 대조 결과는 로컬 배포 폴더의 검증 JSON에 기록한다.

**Play에 업로드하거나 정식 출시한 상태는 아니다.** 콘솔을 읽어 확인한 현재 상태는 앱 초안이며,
프로덕션 신청은 비활성이다. 비공개 테스트 참여자는 0명이고 앱 설정도 미완료이다.
적용되는 개인 계정 요건은 12명 이상이 14일 연속 참여하는 비공개 테스트 후 프로덕션 액세스 신청이다.
내부 테스트 기록으로 이 기간을 대체하지 않았다. 사용자 동의 없이 다른 트랙에 배포하지 않았다.

## 변경

- compileSdk/targetSdk 36, AGP 8.10.1, Gradle 8.11.1과 공식 배포 ZIP 체크섬.
- 이전 배포에서 사용한 BlurFing 런처 아이콘과 생성 도구 복원.
- 기존 업로드 키를 재사용하고 인증서 및 AAB 서명을 검사하는 Windows 빌드 도구.
- release에서도 HTTP 예외 없이 네트워크 통합 검사를 실행하도록 테스트 전용 HTTPS 인증서 사용.
  이 인증서는 테스트 클라이언트에만 신뢰시키며 앱의 TLS 정책은 바꾸지 않았다.
- 최신 main의 HTTPS/V2 준비 확인 변경을 포함한다. 이 변경은 팀원의 기존 커밋이다.

## 실행한 검사

JDK 21, Android SDK 36에서 최종 서명 빌드 도구를 실행했다.
`testDebugUnitTest testReleaseUnitTest lintRelease bundleRelease assembleDebug assembleDebugAndroidTest`
전체 실행은 3분 35초에 성공했다.

| 검사 | 실제 결과 |
|---|---|
| debug 단위 검사 | 223개 중 222개 통과, 개인 입력이 필요한 선택 검사 1개 건너뜀, 실패/오류 0 |
| release 단위 검사 | 223개 중 222개 통과, 같은 선택 검사 1개 건너뜀, 실패/오류 0 |
| release lint | 오류 0, 경고 37, 힌트 2 |
| 업로드 인증서 | 이전 수락 AAB, 기존 키, 새 서명 AAB가 일치 |
| AAB 서명 | 서명 엔트리 존재, `jarsigner -verify` 종료 0 / `jar verified.` |
| 에뮬레이터 UI 검사 | 7개 모음의 19개 통과, 약 40초 |

에뮬레이터는 `BlurFing_Test`, Android 17 프리뷰 API 37이다.
API 36 대상으로 빌드한 debug 앱에서 자동 진입·완료·종료·사진 교체·뒤로가기·설정·저장 흐름을 확인했다.
Mock 및 합성 응답을 사용한 검사이며 학교 서버의 실제 AI나 실물 휴대폰 검증을 뜻하지 않는다.
아이콘을 복원하기 전의 동일 동작 코드로 실행한 UI 검사다.

첫 전체 서명 검사에서는 기존 뒤로가기 검사
`backDuringProcessingRequestsConfirmationAndCanContinueToComparison`의 5초 상태 대기에 시간 초과 1건이 있었다.
검사 코드·대기 시간·단언을 바꾸지 않고 해당 검사를 재실행해 통과했고,
에뮬레이터 종료 후 worker 2개로 다시 실행한 debug/release 전체 검사도 통과했다.
시간 초과의 원인을 앱 결함으로 확정하거나 수정 완료로 주장하지 않는다.

lint의 남은 경고는 아이콘 형상·중복·단색 아이콘, 의존성 갱신 안내 및 기존 Compose/리소스 권고 등이다.
자체 서명 업로드 인증서의 신뢰 체인과 타임스탬프 등에 관한 jarsigner 경고도 남는다.
이 도구의 종료 0은 Play 심사 승인이나 게시 완료를 뜻하지 않는다.

## 남은 실제 검증

- 학교 HTTPS 서버 준비 완료 후 실제 사진의 V23 처리·비교·저장·재읽기.
- 실제 휴대폰에서 설치, 공유, 연속 실행 시간 측정.
- 계정 소유자가 앱 설정과 실제 데이터 취급에 맞는 스토어/개인정보 내용을 완료.
- 비공개 테스트 요건 충족 후 프로덕션 액세스 및 심사 신청.

release에서는 localhost HTTP를 허용하지 않는다. 학교 서버를 SSH/USB로 연결하는 기존 시연은
별도 debug APK를 사용한다. 서버 내부 `fast_v32` 설정을 Android API 엔진 이름으로 바꾸지 않는다.

공식 근거: [앱 서명](https://support.google.com/googleplay/android-developer/answer/9842756?hl=ko),
[대상 API](https://support.google.com/googleplay/android-developer/answer/11926878?hl=ko),
[개인 계정 테스트](https://support.google.com/googleplay/android-developer/answer/14151465?hl=ko).
