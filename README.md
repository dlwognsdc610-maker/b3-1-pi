# B3-1 — Pi에서 웹 서비스 배포하기

실습·증빙 수집·리소스 정리 완료.

AWS 대신 개인 Raspberry Pi 5, Docker, Cloudflare Quick Tunnel을 사용했다. 원문의 EC2·VPC·IAM을 생성한 구성과는 다르며, 대응 관계와 차이는 [구현 범위](docs/platform-mapping.md)에 기록했다.

## 외부 접속 검증

- 선택한 방식: **B — 외부 HTTPS `GET /health` 호출**.
- 접속 정보: `https://bin-consequently-novelty-weapon.trycloudflare.com/health`
- 실제 검증 시각(UTC): `2026-11-24T10:33:31+00:00`
- 화면 캡처 시각(UTC): `2026-11-24T11:06:59+00:00`
- 정상 응답: **HTTP 200**, 본문 **`OK`**.
- 브라우저 페이지: `https://bin-consequently-novelty-weapon.trycloudflare.com/`
- 원본 응답: [외부 health](docs/evidence/external-health.txt), [웹 페이지](docs/evidence/external-page.txt).
- Pi 밖의 별도 컴퓨터에서 확인한 응답: [독립 외부 검증](docs/evidence/external-independent.txt).
- 공개 페이지 캡처: [외부 접속 화면](docs/evidence/external-access.png).
- 상태 확인 캡처: [health 화면](docs/evidence/external-health.png).
- `docker ps`와 외부 HTTP 응답의 실제 명령 출력 캡처: [실행 결과 화면](docs/evidence/runtime-evidence.png).

증빙을 남긴 뒤 임시 터널과 서버를 정리했다. 위 URL은 실습 당시 접속 주소이며 현재 서비스 중인 주소가 아니다.

## 제출 파일

| 결과물 | 파일 |
|---|---|
| 아키텍처 다이어그램 1장 | [docs/architecture.pdf](docs/architecture.pdf) |
| 외부 접속 증빙 | 이 README의 URL·검증 방식과 [캡처](docs/evidence/runtime-evidence.png) |
| 트러블슈팅 보고서 | [docs/troubleshooting.md](docs/troubleshooting.md) |
| 정리 체크리스트·근거 | [docs/cleanup-checklist.md](docs/cleanup-checklist.md), [cleanup.json](docs/evidence/cleanup.json) |

## 구성과 접근 제어

- 서버: Raspberry Pi 5, Debian 13, ARM64.
- 네트워크: 전용 Docker bridge `codyssey-b3-1-net`, `10.31.0.0/24`, gateway `10.31.0.1`.
- 웹 서버: 컨테이너 `10.31.0.10:8080`, 호스트 `127.0.0.1:18081`에만 바인딩.
- 외부 요청: Internet → Cloudflare HTTPS 443 → 암호화된 Tunnel → Pi의 loopback → Nginx.
- 아웃바운드: 컨테이너 기본 경로 → bridge gateway → Pi NAT → LAN 라우터 → 인터넷. `curl https://example.com` 성공 기록을 남겼다.
- SSH: 키로 Pi에 접속했다. 과제용 nftables table은 지정한 관리 장비 IP·LAN과 Tailscale 사설 IPv6만 허용한다. 공개 터널은 SSH를 전달하지 않는다.
- 최소권한: Nginx는 UID/GID `101:101`, 읽기 전용 root filesystem, `/tmp`만 tmpfs, capability 전체 제거, `no-new-privileges`로 실행한다.
- 자원 상한: 메모리 64MiB, CPU 0.5개, PID 64개, 로그 파일 2MiB×2개.
- Docker API는 과제 전용 Unix socket에만 연결한다. 일반 사용자에게 Docker 그룹 권한을 추가하지 않았다.

## Docker 실행과 HTTPS

이미지는 `codyssey-b3-1:1.0`이고 `nginx:stable-alpine`을 바탕으로 빌드했다. [Dockerfile](Dockerfile), [Nginx 설정](nginx.conf), [다운로드한 도구 버전](docs/tool-versions.json)을 포함했다.

실행 방법은 `lab.py up`이며, 내부적으로 전용 엔진에 `docker build`와 `docker run`을 호출한다. 포트 매핑은 **`127.0.0.1:18081 → 8080/tcp`**이다. 컨테이너 내부 `curl http://localhost:8080/health`, Pi 내부 `curl http://127.0.0.1:18081/health`, 외부 HTTPS 호출을 모두 검증했다. 실제 설정과 실행 상태는 [컨테이너 조회](docs/evidence/container-inspect.json.txt), [docker ps](docs/evidence/docker-ps.txt)에 있다.

HTTPS는 무료 임시 서브도메인과 Cloudflare 관리 인증서를 사용한다. Pi에 Let's Encrypt 인증서를 설치한 구성은 아니다.

## 다시 실행하기

Pi에 SSH로 접속한 일반 사용자 세션에서 실행한다. 관리 작업에는 기존 사용자의 sudo 권한이 필요하다.

```bash
cd /home/ljh/self-os/Codyssey/b3-1-pi
python3 lab.py up
python3 lab.py verify
python3 lab.py troubleshoot
python3 capture.py
python3 lab.py cleanup
python3 report.py
```

`up`은 공식 Docker 정적 배포본과 공식 cloudflared ARM64 파일을 `.tools/`에 받아 사용한다. 기존 OS 패키지 상태 때문에 전역 Docker 패키지 설치 대신 과제 전용 엔진을 사용했다. 이미지 빌드에만 호스트 네트워크를 사용하고, 웹 서비스 실행에는 전용 bridge를 사용한다.

화면 캡처에는 Chromium headless shell을 사용한다. Debian의 `chromium-headless-shell`과 `chromium-common` 패키지를 `.tools/`에 내려받아 추출하고, 시스템에 설치하지 않는다. 임시 브라우저 프로필은 메모리에 만들고 캡처 뒤 제거한다. 실행 결과 화면은 원본 명령 출력을 HTML 문서로 표시한 뒤 캡처한 것으로, 실제 터미널 창의 스크린샷과 구분한다.

`cleanup`은 이 과제의 label을 확인한 뒤 컨테이너·네트워크를 삭제하고, 전용 엔진·터널을 중지하며, 과제용 방화벽 table과 IP forwarding 변경을 되돌린다. 과제 전용 Docker data root도 삭제한다. 소스, 증빙, 다운로드한 도구 파일은 재현을 위해 보관한다.

## 설명할 수 있어야 할 내용

1. Subnet은 주소 범위이고, route는 목적지에 따라 다음 gateway를 고른다. 기본 경로가 있어도 아웃바운드 방화벽·NAT가 맞아야 통신한다.
2. 네트워크 접근 제어는 패킷의 출발지·포트를 판단한다. IAM은 클라우드 API 호출 권한을 판단한다. 컨테이너의 UID 제한은 프로세스 권한 제한이다.
3. 웹 서버가 실행 중이어도 listening port, 포트 매핑, 터널의 origin 주소가 다르면 외부 접속이 실패한다.
4. 로그와 상태를 비교해 원인을 좁히고, 조치 뒤 같은 요청으로 복구를 확인한다.
5. AWS에서는 EC2 실행시간, EBS, 공인 IPv4, NAT Gateway 같은 항목이 비용 요인이 된다. 이번 실습은 유료 클라우드 리소스를 생성하지 않았다.

참고: [Docker bridge](https://docs.docker.com/engine/network/drivers/bridge/), [Docker 정적 파일](https://docs.docker.com/engine/install/binaries/), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
