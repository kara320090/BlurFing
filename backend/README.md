# BlurFing Backend

주담당: 한윤섭

## 역할

백엔드는 보호 요청을 검사하고 AI 담당자의 처리 모듈에 전달한 뒤, 결과를 확인해 앱에 반환합니다. 블러 알고리즘 자체는 AI 파트에서 구현합니다.

## 지금까지 구현한 것

- FastAPI 서버와 상태 확인용 `GET /`
- `POST /v1/protect` 요청 검증: 이미지 형식·크기, 처리 방식·강도, 영역 좌표
- AI 처리 모듈을 호출할 연결 지점과 결과 이미지 형식·해상도 검사
- 오류 응답과 영역이 없을 때의 `no_regions` 응답
- 합성 이미지 기반 백엔드 테스트 10개

## 현재 상태

AI 모듈은 아직 연결되지 않았습니다. 연결 전 보호 요청은 `503 PROCESSOR_UNAVAILABLE`을 반환하며, 실제 보호 성공으로 표시하지 않습니다. 자동 영역 추출과 실제 기기 연동도 아직 검증하지 않았습니다.

## 다음 할 일

1. AI 담당자의 보호 처리 모듈을 연결하고 결과를 검증하기
2. 요청 취소·처리 오류·용량 제한을 점검하기
3. Android 앱과 합성 이미지로 실제 통신 테스트하기

## 실행 및 테스트

`backend` 폴더에서 실행합니다.

```bash
pip install -r requirements-dev.txt
uvicorn main:app --reload
pytest -q
```

AI 모듈 연결 지점은 `app.state.protection_processor`입니다. 연결할 함수는 `(image_bytes, method, strength, regions)`를 받아 입력과 같은 크기의 완성된 PNG 바이트를 반환해야 합니다. 이미지 보호 방식과 강도 해석은 AI 담당자가 결정합니다.
