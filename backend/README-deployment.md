# BlurFing Mock 서버 배포

AI 모델이 완성되기 전에는 기존 V1 Mock으로 사진 업로드와 PNG 반환을 시험한다.
Mock은 블러·지문 탐지·보호 성능 평가를 하지 않는다. 실제 AI V2 계약은 유지하고,
모델을 설정하지 않은 `/v2/ready`와 `/v2/photo/protect`는 503을 반환한다.

## 구성과 담당 역할

```text
앱 → 임시 HTTPS → Cloudflare Quick Tunnel → Nginx
                                            ├─ Uvicorn 1 worker → FastAPI V1 Mock
                                            └─ Uvicorn 1 worker → FastAPI V2 미설정
```

| 구성 | 담당 |
|---|---|
| Docker | Python·직접 의존성·실행 코드 포장, 비root 실행, 읽기 전용 루트 |
| Docker Compose | 네트워크, 자원 한도, healthcheck, 재시작·종료 설정 |
| Nginx | 경로 전달, 본문 크기·접수 제한, timeout, 프록시 오류 JSON |
| Uvicorn | ASGI 실행. V1/V2 각각 worker 1개로 프로세스 내 ID·접수 제한 유지 |
| FastAPI | 기존 입력·결과 검사, 처리기 연결, 응답·오류 및 작업 수명 관리 |
| Cloudflare | 외부 HTTPS 연결. Tailscale+SSH는 관리자용이고 앱 사용자는 설치하지 않음 |

호스트에는 Nginx의 `127.0.0.1:8080`만 연결한다. API 포트와 Docker 소켓을 공개하지
않는다. Nginx는 전용 Docker 연결과 호스트 관리자만 origin에 접근한다는 전제로
Cloudflare의 사용자 IP 헤더를 신뢰하므로, 포트를 `0.0.0.0`으로 바꾸지 않는다.

## 현재 검증 범위

2026-10-17 사용자 실행 결과: `/home/user/BlurFing` 클론, main
`6e17794918ea66f61ca6ffa90f339318031f2e91`, Compose 5.1.4와
`sudo docker` 엔진 29.5.2 접근을 확인했다. `data/`의 기존 변경 5개는 보존한다.
같은 서버에서 Docker build·pip check·Compose 설정 검사·Nginx 설정 검사가 통과했고,
V1·V2·Nginx 컨테이너가 모두 Healthy로 시작됐다. 서버 내부 Mock HTTP 검사 8개와
Windows에서 임시 HTTPS를 경유한 검사 8개가 통과했다. 합성 PNG/JPEG의 반환 크기·
픽셀 일치와 Mock 표시를 확인한 결과이며 실제 AI·휴대폰 앱 시험은 아니다.

Windows 회귀는 288개와 하위 검사 59개가 통과했다. 구 checkout에 없는 계약 JSON
2개는 같은 main SHA의 원문을 메모리에서 읽었으며 `contracts/`는 수정하지 않았다.
읽기 전용 Nginx의 기본 임시 경로 문제를 수정하고 별도 회귀 검사 1개도 통과했다.
고정 주소, 재부팅 후 복구, GitHub 재배포·복구, 프록시 과부하·timeout·취소 주입,
실제 AI 및 앱 연동은 이 결과만으로 완료로 보지 않는다.

## 처음 실행

이 구성 파일이 서버의 `backend`에 있어야 한다. 아직 GitHub에 커밋하지 않은 변경은
별도 전달이 필요하다. 아래 명령은 **하나씩 입력하고 Enter**를 누른다.
Docker 권한이 있는 계정은 `--sudo`를 생략할 수 있다. 비밀번호는 터미널에만 입력한다.

```bash
cd /home/user/BlurFing
```

기본 `.env.example`은 Mock 모드·V1 대기 20초·접수 합계 4개다.
로컬 `main.py` 기본 30초는 바꾸지 않았다. Nginx의 V1 응답 대기는 25초다.
개별 운영 설정이 필요하면 `.env.example`을 `backend/.env`로 복사해 수정한다.
`.env`·`compose.local.yaml`·`.deploy/`는 Git 및 이미지에 넣지 않는다.

```bash
python3 -B backend/manage_deployment.py --sudo up
```

이 명령은 이미지 빌드와 Nginx 설정 검사를 먼저 수행하고 V1·V2·Nginx를 기동한다.
실행 중인 다른 Compose 프로젝트는 건드리지 않는다. 업데이트 때는 진행 중 요청이
중단될 수 있으므로 사용자가 없는 시간에 실행한다. 무중단 배포는 아니다.

```bash
python3 -B backend/manage_deployment.py --sudo verify
```

서버→Nginx→API에서 상태·Mock 표시·405/Allow·404·V2 미준비와 합성 PNG/JPEG
반환의 크기·픽셀을 검사한다. 응답 본문이나 이미지 파일을 저장하지 않는다.
짧은 시간에 반복하면 공개 접수 제한에 걸릴 수 있으므로 실패 후 30초 이상 기다린다.

## 임시 HTTPS 공개

`public`은 내부 Mock 검사를 다시 통과한 뒤 Tunnel을 시작한다.
앞의 verify 직후라면 요청 제한이 회복되도록 30초 이상 간격을 둔다.

```bash
python3 -B backend/manage_deployment.py --sudo public
```

```bash
python3 -B backend/manage_deployment.py --sudo url
```

출력된 `https://...trycloudflare.com`이 앱 담당자에게 전달할 임시 서버 주소다.
아직 URL이 없으면 아래 상태를 확인하고 잠시 후 `url`을 다시 실행한다.

```bash
python3 -B backend/manage_deployment.py --sudo status
```

외부 Windows에서 같은 Python 의존성이 준비됐다면 다음으로 실제 HTTPS를 검사한다.
`실제주소`는 `url`의 출력으로 바꾼다. 휴대폰은 Wi-Fi를 끄고 같은 주소의 `/`,
`/ready`, `/info`를 연 다음 앱 담당자와 이미지 업로드·표시·저장을 공동 확인한다.

```text
python backend/check_deployment_http.py --base-url https://실제주소.trycloudflare.com
```

Quick Tunnel은 도메인·계정 없이 쓸 수 있지만, 주소가 바뀔 수 있고 가동 보장이 없다.
`unless-stopped`는 Docker가 실행될 때 컨테이너 재시작을 돕지만 이전 URL을 보장하지
않는다. 상시 배포는 고정 도메인과 정식 Tunnel이 필요하다. 일반 사용자에게 이메일
PIN·VPN·API 키·인증서 설치를 요구하는 설정은 추가하지 않았다.
[Cloudflare Quick Tunnel 공식 문서](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## GitHub 변경 재배포와 복구

Dockerfile·Compose·배포 진입점을 포함한 `backend` 변경이 GitHub main에 반영된
후 아래 명령을 사용한다. 이 작업 자체가 커밋이나 push를 하지는 않는다.

```bash
python3 -B backend/manage_deployment.py --sudo update
```

`git fetch` 후 해당 커밋의 `backend`만 `backend/.deploy/releases`에 풀어 빌드한다.
현재 checkout과 `data/` 등 다른 파일을 checkout/reset/stash하지 않는다.
원격 버전에 `compose.yaml`이 없으면 기존 서버를 교체하지 않고 실패한다.
성공한 기동의 경로·커밋과 이전 경로를 `.deploy/state.json`에 남긴다.
이미지 빌드 실패는 기존 서비스를 교체하지 않는다. 기동 이후 실패는 자동으로
성공 처리하지 않으며 상태·verify 결과를 확인해야 한다.

이전 배포 경로가 남아 있다면 다음으로 다시 기동할 수 있다. 최초 `local` 배포로
돌아갈 때는 현재 작업 폴더가 원본이므로, 이후 수정했다면 불변 snapshot은 아니다.
기존 이미지·release 폴더·개인 자료를 자동 삭제하지 않는다.

```bash
python3 -B backend/manage_deployment.py --sudo rollback
```

재배포 후 `verify`, `url`과 외부 HTTPS 검사를 다시 수행한다. Tunnel 프로세스 자체를
유지하더라도 주소·외부 연결이 유지되는지는 실제 결과로 확인한다.

## AI 연결 준비

V1 처리기는 기존 4개 위치 인자 계약을 따른다. `BLURFING_DEPLOY_MODE=real`과
`BLURFING_PROCESSOR=모듈:함수`를 명시한다. `mock` 상태에서 실제 처리기를 설정하거나
`real`에 MockProcessor를 등록하면 시작을 거절한다. 미등록은 503이며 자동 Mock
전환은 없다. V2는 [기존 V2 설정](README-photo-v2.md)의 명시 경로·모델·registry를 사용한다.

AI 담당자가 Python/패키지/GPU·모델 요구사항을 확정하면 AI runtime 이미지를 준비하고
필요한 코드·모델·registry만 읽기 전용으로 연결한다. 현재 API 이미지는 AI 패키지나
모델을 포함하지 않는다. Ubuntu의 임의 Python venv를 컨테이너에 복사하는 것만으로
실행 가능하다고 가정하지 않는다. 확장은 비공개 `compose.local.yaml`로 적용할 수 있고
마운트 경로는 절대 경로로 작성한다.

실제 모델을 공개하기 전 [측정 도구](README-ai-measurement.md)로 Linux 처리 시간을
확인한다. V2 600초/Nginx 630초 설정은 Cloudflare의 기본 125초 read timeout을
늘리지 못한다. 필요하면 처리 방식·공개 경로를 다시 합의하며 비동기 API로 자동 변경하지 않는다.
[Cloudflare timeout 공식 설명](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-524/)

## 개인정보와 운영 제한

- 보호 POST는 IP별 분당 6개·burst 2, 전체 분당 30개·burst 4를 기준으로 제한한다.
  동시 연결은 IP별 2개·전체 8개다. V1 초과는 503, V2 초과는 429 공통 JSON이다.
- Nginx 본문 상한 16MiB와 API 파일 상한 15MiB를 별도로 적용한다. V2는 실제 수신량
  15MiB+64KiB 검사도 유지한다. 프록시가 본문을 읽기 전에 차단하면 request_id는 빈 문자열이다.
- POST 자동 재시도·프록시 캐시·디스크 응답 버퍼를 끈다. `no-store`를 반환한다.
  Nginx 요청 로그와 Uvicorn access/일반 오류 traceback 로그는 끄며 AI child 출력은
  기존 V2처럼 외부로 전달하지 않는다. 진단은 상태·고정 오류 코드 중심으로 한다.
- 임시 쓰기는 크기를 제한한 컨테이너 tmpfs를 사용한다. tmpfs도 호스트 swap 정책의
  영향을 받을 수 있으므로 실제 개인 사진 시험 전 학교의 자료 보관 정책을 확인한다.
- 공개 주소를 아는 누구나 호출할 수 있다. 합성 시험부터 진행하고, 실제 사진은
  Cloudflare를 거친다는 점과 참여 동의·사용 범위를 확인한 후 사용한다.
- 이미지 digest는 2026-10-17 확인 값으로 고정했다. Python 직접 의존성은 고정했지만
  전이 의존성 전체 lock이나 취약점 검사가 완료됐다는 뜻은 아니다. 업데이트는 검토 후 진행한다.
