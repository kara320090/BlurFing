# 시스템 통합 및 담당자별 연동 안내 (Integration Notes)

- 작성자: 이봉헌 (팀장, Android 앱 및 시스템 통합)
- 작성일: 2026-09-19
- 대상: 한윤섭(백엔드), 정회서(데이터/영역 추출), 유재윤(AI 알고리즘), 최승빈(센서/평가)

---

## 1. 백엔드 API 연동 (한윤섭 담당)

### 구현 상태
- `contracts/protection-api.md` 초안을 기반으로 `ApiProtectionRepository` 구현 완료.
- 엔드포인트: `POST /v1/protect` (multipart/form-data)
  - `image`: 정규화된 PNG 바이너리
  - `request_id`: UUID 문자열
  - `method`: `gaussian_blur`
  - `strength`: 0.1 ~ 1.0 부동소수점 문자열
  - `regions`: `[{"x":0.2,"y":0.1,"width":0.1,"height":0.2}]` 형태의 JSON 문자열

### 클라이언트 결정 사항 및 백엔드 검토 요청
1. **타임아웃**: 기본 30초 설정. 대용량 이미지 처리 시 적절한지 서버 처리 시간 벤치마크 후 확정 필요.
2. **최대 파일 크기**: 클라이언트에서 15MB 초과 파일은 네트워크 전송 전 차단. 서버측 `MAX_CONTENT_LENGTH`와 동기화 필요.
3. **취소(Cancellation)**: 클라이언트에서 취소 시 OkHttp `Call.cancel()`을 호출하며, 서버에서 늦게 도착한 응답은 `request_id` 비교를 통해 UI에 반영하지 않고 안전하게 폐기함.

---

## 2. 손끝 영역 추출 연동 (정회서 담당)

### 구현 상태
- `NormalizedRegion` (0..1 상대 좌표) 데이터 모델 및 화면 터치/드래그 오버레이(`FingertipOverlayCanvas`) 구현 완료.
- 지문 패드 영역 외의 손톱·손등을 사용자가 직접 배제하거나 수정할 수 있도록 영역 추가/삭제/이동 지원.

### 연동 요청
- 자동 탐지 모듈 완성 시 `ProtectionResponse.applied_regions`로 추출된 후보 목록을 반환해 주면 앱 화면에서 즉시 렌더링 가능.

---

## 3. AI 보호 알고리즘 연동 (유재윤 담당)

### 구현 상태
- 현재 앱에서는 개발/프리뷰용으로 `LocalBlurProcessor`를 탑재하여 UI 전후 비교를 시연함.
- UI 상에 "[Mock 결과] 실제 AI 모델 평가는 진행되지 않았습니다" 안내 문구를 명시하여 가짜 성능 주장을 방지함.

### 연동 요청
- 신규 알고리즘(노이즈 주입, 적대적 섭동 등) 연구 완료 시 `method` 파라미터 값 추가 합의 필요.

---

## 4. 센서 및 평가 연동 (최승빈 담당)

### 구현 상태
- `EvaluationMetrics` 모델 구성 완료. 실제 센서 측정 전까지는 `originalScore`, `protectedScore`를 모두 `null`("미측정")로 유지함.

### 연동 요청
- 실제 지문 센서 취득 및 평가 도구 실행 시 sample ID, 엔진 버전, 측정 시각과 함께 전후 점수를 전달받는 규격 확정 필요.
