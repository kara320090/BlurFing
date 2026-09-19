# BlurFing Android App

주담당: 이봉헌 (Android 앱 개발 및 시스템 통합, 팀장)

SNS 사진 속 손가락 지문 노출을 줄이는 Android 보호 앱 프로젝트입니다.
정지 사진 입력 → 손끝 영역 확인·수정 → 보호 설정 → 처리 → 전후 비교 → 보호 사본 저장의 전체 흐름을 제공합니다.

---

## 1. 아키텍처 및 모듈 구성

- **UI 프레임워크**: Jetpack Compose (Material3)
- **상태 관리**: ViewModel, StateFlow, Coroutines
- **네트워크 / 직렬화**: OkHttp3, Kotlinx Serialization
- **이미지 및 EXIF**: Coil, AndroidX ExifInterface
- **저장소 패턴**:
  - `ProtectionRepository` 인터페이스를 통해 `MockProtectionRepository`(기본값, 독립 실행 및 UI 개발용)와 `ApiProtectionRepository`(`contracts/protection-api.md` 연동용) 교체 가능

### 패키지 구조 (`android/app/src/main/java/com/blurfing/app/`)
```
├── MainActivity.kt               # 화면 전환 네비게이션 및 진입점
├── model/
│   ├── NormalizedRegion.kt       # 0..1 상대 좌표 및 경계 검증 (BF-03)
│   └── ProtectionModels.kt       # 요청/응답 DTO 및 연구용 평가 메트릭 (BF-07)
├── repository/
│   ├── ProtectionRepository.kt   # 공통 인터페이스
│   ├── MockProtectionRepository.kt # 개발용 Mock 구현체 (취소 지원, MOCK_RESULT 명시)
│   └── ApiProtectionRepository.kt  # OkHttp 기반 백엔드 연동 어댑터 (BF-07)
├── ui/
│   ├── components/
│   │   └── FingertipOverlayCanvas.kt # 손끝 지문 패드 인터랙티브 오버레이 (BF-03)
│   ├── screens/
│   │   ├── ImagePickerScreen.kt      # 사진 선택 및 오류 안내 (BF-01)
│   │   ├── RegionEditorScreen.kt     # 손끝 영역 확인/수정 (BF-03)
│   │   ├── ProcessingScreen.kt       # 강도 설정 및 처리 진행/취소 (BF-04)
│   │   └── ComparisonScreen.kt       # 전후 비교 및 사본 저장 (BF-05, BF-06)
│   └── theme/                        # Material3 테마 및 색상
├── utils/
│   ├── CoordinateTransformer.kt  # 뷰 픽셀 ↔ 정규화 좌표 양방향 변환
│   ├── ExifNormalizer.kt         # EXIF 회전각 픽셀 반영 및 정규화
│   ├── ImageSaver.kt             # MediaStore Scoped Storage 사본 저장 (BF-06)
│   └── LocalBlurProcessor.kt     # 개발 프리뷰용 로컬 블러 (AI 성능 미주장)
└── viewmodel/
    └── BlurFingViewModel.kt      # 전체 화면 상태 및 취소/재시도 제어
```

---

## 2. 개발 환경 및 요구 사항

- **JDK**: Java 21 LTS 권장 (로컬 환경: `C:\Program Files\BlueJ\jdk` 확인)
- **Android SDK**: `C:\Users\soma\AppData\Local\Android\Sdk`
  - `compileSdk`: 35 (Android 15)
  - `minSdk`: 26 (Android 8.0 Oreo)
  - `targetSdk`: 35
- **빌드 도구**: Gradle 8.9+, Android Gradle Plugin 8.7.0

---

## 3. 실행 및 빌드 방법

### Android Studio에서 실행
1. Android Studio를 실행하고 `android/` 폴더를 프로젝트로 엽니다.
2. Gradle 동기화(Sync)가 완료되면 에뮬레이터(`Medium_Phone` 등) 또는 실물 기기를 선택합니다.
3. `Run 'app'` (Shift + F10)을 실행합니다.

### 터미널에서 빌드 및 테스트
```powershell
# 디버그 APK 빌드
./gradlew assembleDebug

# 단위 테스트 실행
./gradlew testDebugUnitTest
```

---

## 4. 검증 결과 및 구분

### 실행 및 완료한 검증
- [x] **상대 좌표 변환 및 경계 검증 (`NormalizedRegionTest`)**: 0.0 ~ 1.0 범위 초과 및 `x+w > 1`, `y+h > 1`에 대한 안전한 예외 발생 및 `safeCreate` 클램핑 확인
- [x] **종횡비 보정 및 좌표계 역변환 (`CoordinateTransformerTest`)**: Letterbox / Pillarbox 여백 계산 및 화면 터치 ↔ 원본 상대 좌표 간 정밀 변환 확인
- [x] **Mock 및 통신 실패 복구 (`ProtectionRepositoryTest`)**: Mock 결과 반환, 15MB 초과 파일 사전 차단, 사전/진행 중 요청 취소(`CancellationException`) 동작 확인
- [x] **평가 점수 무결성 (`EvaluationMetricsTest`)**: 미측정 수치가 null로 유지되어 가짜 일치율(0~100%)을 생성하지 않음을 확인

### 미실행 검증 (기기 및 서버 준비 후 진행 필요)
- [ ] **실제 기기/에뮬레이터 런타임 UI 동작**: AVD 부팅 및 화면 터치 제스처 실기 검증 (에뮬레이터 오프라인 상태)
- [ ] **실제 백엔드 서버 HTTP 연동**: `POST /v1/protect` 실제 서버 배포 후 엔드투엔드 통신 검증 (백엔드 서버 미기동 상태)
