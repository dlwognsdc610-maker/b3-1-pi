# 리소스 정리 체크리스트

검증 시각(UTC): `2026-11-24T11:20:59+00:00`

- [x] 공개 Tunnel 중지. 해당 URL로 Pi에 들어오는 경로 제거.
- [x] `codyssey-b3-1-web` 컨테이너 종료·삭제.
- [x] `codyssey-b3-1-net` 네트워크와 bridge·route 제거.
- [x] 과제 전용 Docker 엔진 종료·Unix socket 제거.
- [x] 전용 Docker data root 삭제. 이미지·레이어·컨테이너 writable layer·내부 볼륨 보관 없음.
- [x] 과제용 nftables table 삭제. 기존 호스트 방화벽은 유지.
- [x] 전용 엔진이 남긴 빈 Docker 방화벽 체인·참조 제거. 예상과 다른 규칙이 있으면 삭제를 중단하도록 구현.
- [x] 과제 시작 전의 IPv4 forwarding 값으로 복원.
- [x] Pi의 loopback `18081` 포트 종료 확인.

근거: [cleanup.json](evidence/cleanup.json). 소스·문서·스크린샷·다운로드한 도구 파일은 재현용 파일로 보관하며 실행 중인 서비스는 아니다.

| 원문의 AWS 정리 대상 | 이번 실습 |
|---|---|
| EC2 | 생성하지 않음. 대응하는 과제 컨테이너 삭제·엔진 종료로 정리 |
| EBS Volumes | 생성하지 않음. 과제 전용 Docker data root 삭제 |
| Elastic IP | 할당하지 않음 |
| Internet Gateway | 생성하지 않음. 공개 터널 종료 |
| VPC·Subnet·Route Table | 생성하지 않음. 전용 Docker network·bridge·route 제거 |
| NAT Gateway | 생성하지 않음. 호스트 Docker NAT 규칙은 네트워크 삭제와 함께 제거 |
| ELB/ALB | 생성하지 않음 |
| RDS | 생성하지 않음 |
| Billing Dashboard | AWS 계정·유료 리소스를 사용하지 않아 해당 없음 |

Pi의 전원, 기존 SSH, Tailscale, 기존 개발 서비스는 과제 정리 대상에 포함하지 않는다.
