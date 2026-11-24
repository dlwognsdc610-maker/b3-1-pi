# 트러블슈팅 보고서

## 사례 1 — 웹 서버 중지로 외부 접속 실패

운영 장애를 가정해 이 과제의 웹 컨테이너만 의도적으로 중지한 통제 실험이다. 원래부터 우연히 발생했던 장애로 기록하지 않는다.

| 항목 | 관측·조치 |
|---|---|
| 재현 시각 | `2026-11-24T10:33:24+00:00` (UTC) |
| 증상 | Pi 내부 접속에는 HTTP 응답이 없었고(curl 표시 `000`), 공개 `/health`는 HTTP `502`로 실패 |
| 가설 | 네트워크나 인증서 문제와 별도로, origin 웹 서버 프로세스가 중지되어 터널이 연결할 수 없다 |
| 검증 | `docker ps -a`의 Exited 상태, Nginx 종료 로그, localhost 접속 실패, tunnel origin 오류를 비교 |
| 조치 | `docker start codyssey-b3-1-web`로 같은 컨테이너를 시작 |
| 결과 | `2026-11-24T10:33:31+00:00` (UTC), 컨테이너 내부·Pi loopback·공개 HTTPS에서 `/health`의 200 OK와 고정 본문 OK 재확인 |
| 재발 방지 | `restart=unless-stopped` 적용. 수동 중지 후에는 명시적으로 start하고, 배포 직후 localhost와 외부 health를 함께 확인 |

### 원본 증거

- [내부 접속 실패](evidence/failure-local.txt)
- [외부 접속 실패](evidence/failure-external.txt)
- [컨테이너 상태](evidence/failure-docker-ps.txt)
- [Nginx 로그](evidence/failure-nginx-log.txt)
- [Tunnel 로그](evidence/failure-tunnel-log.txt)
- [복구한 내부 응답](evidence/localhost-health.txt)
- [복구한 외부 응답](evidence/external-health.txt)

## 사례 2 — 새 임시 호스트명의 DNS 해석이 일시 실패

| 항목 | 관측·조치 |
|---|---|
| 증상 | 최초 외부 페이지 검증에서 curl exit 6, `Could not resolve host` 발생 |
| 가설 | 웹 서버 응답 이전 단계인 호스트명 해석의 일시 오류다. DNS 전파나 사용한 resolver 문제 중 어느 쪽인지는 이 기록만으로 확정하지 않는다 |
| 검증 | 컨테이너·Pi loopback은 200이며, 같은 공개 호스트의 health도 성공한 기록과 대조 |
| 조치 | curl에 횟수·전체 시간이 제한된 재시도를 추가하고, 루트 페이지와 health를 다시 요청 |
| 결과 | 공개 페이지와 health의 200 응답 확인 |
| 재발 방지 | DNS 실패와 HTTP 실패를 나누어 기록하고, 한 번의 조회 실패를 서버 중지로 판정하지 않는다 |

원본: [초기 DNS 실패](evidence/dns-initial-failure.txt), [최종 페이지 응답](evidence/external-page.txt).
