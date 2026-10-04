# 1. 재현 가능한 JDK 21 빌드

Android Studio가 제공하는 JDK 25는 현재 Gradle 8.9와 호환되지 않아 테스트 시작 전 중단된다. 기존 Gradle과 앱 대상 버전은 유지하고 JDK 21을 명시적으로 선택하는 실행 스크립트를 추가했다.

```powershell
# 저장소 루트에서 실제 JDK 21 경로를 지정한다.
.\android\tools\build_checked.ps1 -JdkHome 'C:\path\to\jdk-21'
```

스크립트는 JDK release 파일과 SDK 35 설치 여부를 먼저 검사한다. JAVA_HOME·ANDROID_HOME은 이번 실행에만 적용하고 종료 시 원래 값으로 복원한다. 사용자/시스템 환경 변수나 Android Studio 설정을 수정하지 않는다.

JDK는 [Eclipse Temurin 공식 배포](https://adoptium.net/temurin/releases/?version=21) 또는 학교에서 제공한 JDK 21을 사용한다. 이 PC에서는 공식 API의 ZIP과 SHA-256을 확인한 휴대용 JDK를 저장소 밖에 준비했다. 실행 파일과 설치 환경은 Git 패치에 포함하지 않는다.
