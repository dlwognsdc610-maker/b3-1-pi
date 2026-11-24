# Pi 대체 구성과 원문 요구사항의 대응

AWS 대신 다른 서비스를 사용할 수 있다는 안내와 Pi로 진행하라는 요청에 따라, 개인 장비에 서비스를 배포했다. AWS 리소스와 IAM을 만들었다는 의미로 사용하지 않는다. 다른 클라우드 허용 안내만으로 개인 장비까지 평가 대상인지 확정할 수는 없으므로, 이 문서에 실제 구현 범위와 차이를 남긴다.

| 원문 요소 | 이번 구현 | 확인 자료 |
|---|---|---|
| VPC와 Public Subnet | 전용 Docker bridge, `10.31.0.0/24` | `evidence/network-inspect.json.txt` |
| Route Table | 컨테이너 기본 경로 `0.0.0.0/0 → 10.31.0.1` | `evidence/container-routes.txt` |
| Internet Gateway | 아웃바운드는 Pi의 NAT와 LAN 라우터, 인바운드는 Cloudflare Tunnel | 다이어그램, 외부·아웃바운드 호출 기록 |
| EC2 | Raspberry Pi 5 물리 서버와 Nginx 컨테이너 1대 | SSH 접속 기록, `docker ps` |
| Security Group | 과제 전용 nftables table, loopback 포트 바인딩, 직접 컨테이너 접근 차단 | `evidence/firewall.txt`, `listening-ports.txt` |
| SSH 소스 제한 | Tailscale 관리 장비의 IPv4 `/32`, 지정된 LAN 대역, Tailscale 인터페이스의 사설 IPv6 대역 | `evidence/firewall.txt` |
| IAM 최소권한 | 서버 프로세스를 `101:101`로 실행하고 capability 전체 제거, 쓰기 가능한 경로를 `/tmp`로 제한 | `evidence/container-inspect.json.txt`, `container-check.txt` |
| HTTP 80 공개 | 공개 HTTPS 443 → Pi의 loopback `18081` → 컨테이너 `8080` | 외부 `/health` 200 응답 |
| 서울 리전 | 개인 물리 장비이므로 AWS 리전은 해당 없음 | SSH 호스트·아키텍처 기록 |
| EBS 8~10GiB | Pi의 기존 저장장치에 과제 전용 Docker data root 사용 | 정리 보고서 |
| 리소스 종료·삭제 | 컨테이너·네트워크 삭제, 전용 엔진·터널 종료, 방화벽·커널 설정 복원 | `evidence/cleanup.json` |

컨테이너 프로세스의 권한 제한은 클라우드 IAM 정책과 서로 다른 기능이다. 설치와 엔진 관리는 기존 관리자의 SSH·sudo 권한으로 수행한다. 클라우드 IAM 사용자 생성·정책 부여 실습과 동일하다고 주장하지 않는다.

Docker bridge는 컨테이너 사이의 네트워크 분리를 제공한다. EC2/VPC 같은 관리형 클라우드 제어면을 제공하지는 않는다. Public IP 직접 접속 대신 공개 HTTPS 호스트명으로 검증한다.

공개 HTTPS는 Cloudflare edge에서 종료된다. 커넥터와 edge는 암호화된 터널로 연결되고, Pi의 `127.0.0.1:18081`에서 컨테이너까지는 로컬 HTTP를 사용한다. Let's Encrypt를 Pi에 설치한 구성은 아니다.

참고: [Docker bridge](https://docs.docker.com/engine/network/drivers/bridge/), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
