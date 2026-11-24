#!/usr/bin/env python3
"""Deploy, verify, and remove this Pi lab without using a global Docker daemon."""

import argparse
import datetime as dt
import hashlib
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / ".tools"
RUNTIME = ROOT / ".runtime"
EVIDENCE = ROOT / "docs" / "evidence"
STATE = RUNTIME / "state.json"
SOCKET = "/run/codyssey-b3-1/docker.sock"
ENGINE = "codyssey-b3-1-engine"
TUNNEL = "codyssey-b3-1-tunnel"
NETWORK = "codyssey-b3-1-net"
CONTAINER = "codyssey-b3-1-web"
IMAGE = "codyssey-b3-1:1.0"
SUBNET = "10.31.0.0/24"
CONTAINER_IP = "10.31.0.10"
PORT = 18081
LABEL = "codyssey.lab=b3-1"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def save(**values):
    current = state()
    current.update(values)
    RUNTIME.mkdir(parents=True, exist_ok=True)
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    temp.replace(STATE)
    return current


def run(args, *, check=True, evidence=None, timeout=120, input=None):
    args = [str(x) for x in args]
    result = subprocess.run(args, text=True, capture_output=True, input=input, timeout=timeout)
    if evidence:
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / evidence).write_text(
            f"Time: {now()}\n$ {shlex.join(args)}\nExit: {result.returncode}\n"
            + result.stdout + result.stderr)
    if check and result.returncode:
        raise RuntimeError(f"{shlex.join(args)}\n{result.stdout[-2000:]}{result.stderr[-4000:]}")
    return result


def docker(*args, **kwargs):
    return run(["sudo", "-n", "env", "DOCKER_BUILDKIT=0", TOOLS / "docker" / "docker",
                "--host", "unix://" + SOCKET, *args], **kwargs)


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "codyssey-b3-1-lab"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def bootstrap():
    TOOLS.mkdir(parents=True, exist_ok=True)
    versions = {}
    binary = TOOLS / "docker" / "dockerd"
    if not binary.exists():
        index_url = "https://download.docker.com/linux/static/stable/aarch64/"
        index = download(index_url).decode()
        choices = re.findall(r'docker-(\d+\.\d+\.\d+)\.tgz', index)
        version = max(set(choices), key=lambda x: tuple(map(int, x.split("."))))
        url = index_url + "docker-" + version + ".tgz"
        print("Downloading official Docker", version, flush=True)
        data = download(url)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for member in archive.getmembers():
                target = (TOOLS / member.name).resolve()
                if not target.is_relative_to(TOOLS.resolve()) or not member.isfile():
                    if member.isdir():
                        continue
                    raise RuntimeError("Unexpected Docker archive entry")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                target.chmod(0o755)
        versions["docker"] = {"version": version, "url": url, "sha256": hashlib.sha256(data).hexdigest()}
    cloudflared = TOOLS / "cloudflared"
    if not cloudflared.exists():
        release = json.loads(download("https://api.github.com/repos/cloudflare/cloudflared/releases/latest"))
        asset = next(x for x in release["assets"] if x["name"] == "cloudflared-linux-arm64")
        print("Downloading official cloudflared", release["tag_name"], flush=True)
        data = download(asset["browser_download_url"])
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if asset.get("digest") and asset["digest"] != digest:
            raise RuntimeError("cloudflared checksum mismatch")
        cloudflared.write_bytes(data)
        cloudflared.chmod(0o755)
        versions["cloudflared"] = {"version": release["tag_name"], "url": asset["browser_download_url"], "sha256": digest[7:]}
    version_path = ROOT / "docs" / "tool-versions.json"
    old = json.loads(version_path.read_text()) if version_path.exists() else {}
    old.update(versions)
    version_path.parent.mkdir(parents=True, exist_ok=True)
    version_path.write_text(json.dumps(old, indent=2) + "\n")


def active(unit, user=False):
    args = ["systemctl"] + (["--user"] if user else [])
    return run([*args, "is-active", unit], check=False).stdout.strip() == "active"


def setup_firewall():
    current = state()
    if run(["sudo", "-n", "/usr/sbin/nft", "list", "table", "inet", "b3_1_lab"], check=False).returncode == 0:
        if not current.get("firewall_owned"):
            raise RuntimeError("Firewall table already exists and is not owned by this run")
        return
    connection = os.environ.get("SSH_CONNECTION", "").split()
    manager = connection[0] if connection else None
    if not manager:
        raise RuntimeError("Start up through SSH so the management source can be verified")
    ipaddress.ip_address(manager)
    # Keep this host's registered Tailscale peers and LAN available for management.
    permitted = {manager, "127.0.0.1"}
    peers = run(["tailscale", "status", "--json"], check=False)
    if peers.returncode == 0:
        data = json.loads(peers.stdout)
        for peer in data.get("Peer", {}).values():
            permitted.update(ip for ip in peer.get("TailscaleIPs", []) if ":" not in ip)
    ipv4 = sorted(x for x in permitted if ":" not in x)
    ipv4.append("192.168.200.0/24")
    rules = f"""table inet b3_1_lab {{
  chain input {{
    type filter hook input priority -10; policy accept;
    tcp dport 22 ip saddr {{ {', '.join(ipv4)} }} accept
    iifname "tailscale0" tcp dport 22 ip6 saddr fd7a:115c:a1e0::/48 accept
    iifname "lo" tcp dport 22 accept
    tcp dport 22 drop
  }}
  chain forward {{
    type filter hook forward priority -10; policy accept;
    iifname != "br-b3-1" ip daddr {CONTAINER_IP} tcp dport 8080 drop
  }}
}}\n"""
    (RUNTIME / "firewall.nft").write_text(rules)
    # Record ownership first so cleanup can recover an interrupted invocation.
    save(firewall_owned=True, ssh_sources=ipv4)
    run(["sudo", "-n", "/usr/sbin/nft", "-c", "-f", RUNTIME / "firewall.nft"])
    run(["sudo", "-n", "/usr/sbin/nft", "-f", RUNTIME / "firewall.nft"])


def up():
    if os.uname().machine != "aarch64":
        raise RuntimeError("Run this deployment on the ARM64 Raspberry Pi")
    run(["sudo", "-n", "true"])
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if not state().get("started_at") or state().get("cleaned_at"):
        save(started_at=now(), cleaned_at=None, verified_at=None, trouble=None)
    bootstrap()
    if not active(ENGINE):
        for port in (PORT, PORT + 1):
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", port))
        routes = json.loads(run(["ip", "-j", "route"]).stdout)
        wanted = ipaddress.ip_network(SUBNET)
        for route in routes:
            if route.get("dst") != "default" and wanted.overlaps(ipaddress.ip_network(route["dst"], strict=False)):
                raise RuntimeError("Lab subnet overlaps an existing route")
        forwarding = run(["/usr/sbin/sysctl", "-n", "net.ipv4.ip_forward"]).stdout.strip()
        save(previous_ip_forward=forwarding)
        if forwarding != "1":
            run(["sudo", "-n", "/usr/sbin/sysctl", "-w", "net.ipv4.ip_forward=1"])
        path = str(TOOLS / "docker") + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        run(["sudo", "-n", "systemd-run", "--unit=" + ENGINE, "--collect",
             "--property=Delegate=yes", "--property=RuntimeDirectory=codyssey-b3-1",
             "--property=RuntimeMaxSec=3h", "--setenv=PATH=" + path,
             TOOLS / "docker" / "dockerd", "--host=unix://" + SOCKET,
             "--data-root=" + str(RUNTIME / "docker"), "--exec-root=/run/codyssey-b3-1/exec",
             "--pidfile=/run/codyssey-b3-1/dockerd.pid", "--bridge=none",
             "--ip-forward=false", "--ip-forward-no-drop=true", "--storage-driver=overlay2",
             "--log-opt=max-size=2m", "--log-opt=max-file=2"])
        for attempt in range(30):
            if docker("info", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Dedicated Docker engine did not start")
    data_root = docker("info", "--format={{.DockerRootDir}}").stdout.strip()
    if Path(data_root).resolve() != (RUNTIME / "docker").resolve():
        raise RuntimeError("Refusing to use a foreign Docker engine")
    setup_firewall()
    network = docker("network", "inspect", NETWORK, check=False)
    if network.returncode:
        docker("network", "create", "--driver=bridge", "--subnet=" + SUBNET,
               "--gateway=10.31.0.1", "--opt=com.docker.network.bridge.name=br-b3-1",
               "--label=" + LABEL, NETWORK)
    elif json.loads(network.stdout)[0].get("Labels", {}).get("codyssey.lab") != "b3-1":
        raise RuntimeError("Refusing to reuse a foreign network")
    existing = docker("inspect", CONTAINER, check=False)
    if existing.returncode:
        print("Building the Nginx image", flush=True)
        docker("build", "--network=host", "--label=" + LABEL, "--tag=" + IMAGE,
               ROOT, timeout=900, evidence="image-build.txt")
        docker("run", "--detach", "--name=" + CONTAINER, "--label=" + LABEL,
               "--network=" + NETWORK, "--ip=" + CONTAINER_IP,
               "--publish=127.0.0.1:" + str(PORT) + ":8080", "--user=101:101", "--read-only",
               "--tmpfs=/tmp:rw,noexec,nosuid,size=16m", "--cap-drop=ALL",
               "--security-opt=no-new-privileges", "--pids-limit=64", "--memory=64m",
               "--cpus=0.5", "--restart=unless-stopped", IMAGE)
    else:
        if json.loads(existing.stdout)[0]["Config"].get("Labels", {}).get("codyssey.lab") != "b3-1":
            raise RuntimeError("Refusing to reuse a foreign container")
        docker("start", CONTAINER)
    for _ in range(20):
        if http("http://127.0.0.1:" + str(PORT) + "/health")[0] == 200:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Nginx did not become healthy")
    if not active(TUNNEL, user=True):
        save(tunnel_started_at=now(), url=None)
        run(["systemd-run", "--user", "--unit=" + TUNNEL, "--collect", "--property=RuntimeMaxSec=3h",
             "--property=WorkingDirectory=" + str(ROOT), TOOLS / "cloudflared",
             "tunnel", "--no-autoupdate", "--protocol=http2",
             "--url=http://127.0.0.1:" + str(PORT), "--metrics=127.0.0.1:" + str(PORT + 1)])
    for _ in range(40):
        logs = tunnel_logs()
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", logs)
        if urls:
            save(url=urls[-1])
            print("PUBLIC_URL=" + urls[-1], flush=True)
            return
        time.sleep(1)
    raise RuntimeError("Tunnel URL was not issued")


def tunnel_logs():
    return run(["journalctl", "--user", "--unit=" + TUNNEL, "--no-pager", "-o", "cat",
                "--since=" + state().get("tunnel_started_at", "today")], check=False).stdout


def http(url, evidence=None):
    result = run(["curl", "--noproxy", "*", "--silent", "--show-error", "--include",
                  "--connect-timeout", "5", "--max-time", "12", "--retry", "2",
                  "--retry-all-errors", "--retry-delay", "1", "--retry-max-time", "35",
                  "--write-out", "\nLAB_STATUS=%{http_code}\n", url],
                 check=False, timeout=50, evidence=evidence)
    found = re.search(r"LAB_STATUS=(\d{3})", result.stdout)
    return int(found.group(1)) if found else 0, result


def verify():
    url = state().get("url")
    if not url:
        raise RuntimeError("No tunnel URL; run up first")
    print("Checking localhost, container, outbound network, and public HTTPS", flush=True)
    docker("exec", CONTAINER, "sh", "-ec",
           "id; nginx -t; curl -i --fail http://localhost:8080/health; "
           "curl -I --fail --max-time 15 https://example.com",
           evidence="container-check.txt")
    code, local = http("http://127.0.0.1:" + str(PORT) + "/health", "localhost-health.txt")
    if code != 200 or "\n\nOK\n" not in local.stdout:
        raise RuntimeError("Unexpected localhost response")
    for attempt in range(30):
        code, public = http(url + "/health", "external-health.txt")
        if code == 200 and "\n\nOK\n" in public.stdout:
            break
        if attempt % 5 == 0:
            print("Waiting for public tunnel routing, HTTP", code, flush=True)
        time.sleep(2)
    else:
        raise RuntimeError("Public health check did not return 200 and OK")
    code, public = http(url + "/", "external-page.txt")
    if code != 200 or "Hello Pi." not in public.stdout:
        raise RuntimeError("Public page did not render the expected response")
    checks = json.loads(docker("inspect", CONTAINER, evidence="container-inspect.json.txt").stdout)[0]
    host = checks["HostConfig"]
    if checks["Config"]["User"] != "101:101" or not host["ReadonlyRootfs"] or host["CapDrop"] != ["ALL"]:
        raise RuntimeError("Container security settings do not match the lab")
    docker("ps", "--filter=name=" + CONTAINER, evidence="docker-ps.txt")
    docker("network", "inspect", NETWORK, evidence="network-inspect.json.txt")
    docker("exec", CONTAINER, "sh", "-ec", "ip route; cat /proc/net/route", evidence="container-routes.txt")
    run(["sudo", "-n", "/usr/sbin/nft", "list", "table", "inet", "b3_1_lab"], evidence="firewall.txt")
    run(["ss", "-ltn"], evidence="listening-ports.txt")
    run(["sh", "-c", "printf 'SSH client and server: %s\\n' \"$SSH_CONNECTION\"; id; hostname; uname -m"], evidence="ssh-session.txt")
    save(verified_at=now())
    print("Verified: external HTTPS 200 /health OK", flush=True)


def troubleshoot():
    if not state().get("verified_at"):
        raise RuntimeError("Run verify before the controlled failure")
    begin = now()
    print("Reproducing a stopped web server, then restoring it", flush=True)
    try:
        docker("stop", "--time=5", CONTAINER)
        local_code, _ = http("http://127.0.0.1:" + str(PORT) + "/health", "failure-local.txt")
        code, _ = http(state()["url"] + "/health", "failure-external.txt")
        docker("ps", "--all", "--filter=name=" + CONTAINER, evidence="failure-docker-ps.txt")
        docker("logs", "--tail=30", CONTAINER, evidence="failure-nginx-log.txt")
        (EVIDENCE / "failure-tunnel-log.txt").write_text(tunnel_logs()[-14000:])
        if local_code == 200 or code == 200:
            raise RuntimeError("Stopped-server failure was not reproduced")
        save(trouble={"started_at": begin, "local_http": local_code, "external_http": code})
    finally:
        docker("start", CONTAINER)
    verify()
    info = state()["trouble"]
    info["recovered_at"] = now()
    save(trouble=info)


def cleanup_engine_rules():
    if run(["pgrep", "-x", "dockerd"], check=False).returncode == 0:
        raise RuntimeError("Another Docker daemon is active; refusing host firewall cleanup")
    allowed_filter = {
        ("-A", "FORWARD", "-j", "DOCKER-USER"),
        ("-A", "FORWARD", "-j", "DOCKER-FORWARD"),
        ("-A", "DOCKER-FORWARD", "-j", "DOCKER-CT"),
        ("-A", "DOCKER-FORWARD", "-j", "DOCKER-INTERNAL"),
        ("-A", "DOCKER-FORWARD", "-j", "DOCKER-BRIDGE"),
    }
    allowed_nat = {("-A", "PREROUTING", "-m", "addrtype", "--dst-type", "LOCAL", "-j", "DOCKER")}
    for destination in ("127.0.0.0/8", "::1/128"):
        allowed_nat.add(("-A", "OUTPUT", "!", "-d", destination, "-m", "addrtype", "--dst-type", "LOCAL", "-j", "DOCKER"))
    allowed_chains = {"DOCKER", "DOCKER-USER", "DOCKER-FORWARD", "DOCKER-CT", "DOCKER-INTERNAL", "DOCKER-BRIDGE"}
    log = []
    plans = []
    # Check all tables before deleting any rule. Foreign rules must survive untouched.
    for binary in ("/usr/sbin/iptables", "/usr/sbin/ip6tables"):
        for table, allowed in (("filter", allowed_filter), ("nat", allowed_nat)):
            rows = [shlex.split(line) for line in run(["sudo", "-n", binary, "-t", table, "-S"]).stdout.splitlines()]
            chains = [x[1] for x in rows if x[0] == "-N" and x[1].startswith("DOCKER")]
            rules = [x for x in rows if x[0] == "-A" and (x[1].startswith("DOCKER") or any(y.startswith("DOCKER") for y in x[2:]))]
            if set(chains) - allowed_chains or any(tuple(x) not in allowed for x in rules):
                raise RuntimeError("Unexpected Docker firewall rules; preserving them for review")
            plans.append((binary, table, chains, rules))
    for binary, table, chains, rules in plans:
        for rule in rules:
            run(["sudo", "-n", binary, "-t", table, "-D", *rule[1:]])
        for chain in chains:
            run(["sudo", "-n", binary, "-t", table, "-X", chain])
        log.append(f"{binary} {table}: removed {len(rules)} lab engine rules and {len(chains)} empty chains")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "docker-firewall-cleanup.txt").write_text("Time: " + now() + "\n" + "\n".join(log) + "\n")


def cleanup():
    if RUNTIME.is_symlink() or RUNTIME.resolve() != ROOT.resolve() / ".runtime":
        raise RuntimeError("Unexpected runtime path")
    if not state().get("started_at"):
        raise RuntimeError("No owned deployment state; refusing cleanup")
    print("Removing only this lab's services and resources", flush=True)
    errors = []
    if active(TUNNEL, user=True):
        run(["systemctl", "--user", "stop", TUNNEL])
    if active(ENGINE):
        entry = docker("inspect", CONTAINER, check=False)
        if entry.returncode == 0:
            if json.loads(entry.stdout)[0]["Config"].get("Labels", {}).get("codyssey.lab") != "b3-1":
                raise RuntimeError("Refusing to remove a foreign container")
            docker("rm", "--force", CONTAINER)
        net = docker("network", "inspect", NETWORK, check=False)
        if net.returncode == 0:
            if json.loads(net.stdout)[0].get("Labels", {}).get("codyssey.lab") != "b3-1":
                raise RuntimeError("Refusing to remove a foreign network")
            docker("network", "rm", NETWORK)
        docker("image", "rm", IMAGE, check=False)
        run(["sudo", "-n", "systemctl", "stop", ENGINE])
    if state().get("firewall_owned"):
        present = run(["sudo", "-n", "/usr/sbin/nft", "list", "table", "inet", "b3_1_lab"], check=False)
        if present.returncode == 0:
            run(["sudo", "-n", "/usr/sbin/nft", "delete", "table", "inet", "b3_1_lab"])
    if state().get("previous_ip_forward") == "0":
        run(["sudo", "-n", "/usr/sbin/sysctl", "-w", "net.ipv4.ip_forward=0"])
    if (RUNTIME / "docker").exists():
        run(["sudo", "-n", "rm", "-rf", "--", RUNTIME / "docker"], timeout=180)
    cleanup_engine_rules()
    probe = run(["sudo", "-n", "/usr/sbin/nft", "list", "table", "inet", "b3_1_lab"], check=False)
    if probe.returncode == 0:
        errors.append("Firewall table remains")
    routes = json.loads(run(["ip", "-j", "route"]).stdout)
    if any(x.get("dst") == SUBNET for x in routes):
        errors.append("Lab subnet route remains")
    if Path(SOCKET).exists() or active(ENGINE) or active(TUNNEL, user=True):
        errors.append("Lab engine or tunnel remains")
    if http("http://127.0.0.1:" + str(PORT) + "/health")[0] != 0:
        errors.append("Published local port remains open")
    audit = {"checked_at": now(), "errors": errors, "engine_active": active(ENGINE),
             "tunnel_active": active(TUNNEL, user=True), "socket_exists": Path(SOCKET).exists(),
             "lab_route_exists": any(x.get("dst") == SUBNET for x in routes),
             "docker_data_exists": (RUNTIME / "docker").exists(), "docker_firewall_chains_removed": True,
             "cloud_resources_created": False}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "cleanup.json").write_text(json.dumps(audit, indent=2) + "\n")
    if errors:
        raise RuntimeError("Cleanup incomplete: " + "; ".join(errors))
    save(cleaned_at=now(), firewall_owned=False)
    print("Cleanup verified: no lab engine, tunnel, subnet, or published port", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["up", "verify", "troubleshoot", "cleanup", "status"])
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(state(), ensure_ascii=False, indent=2))
    else:
        globals()[args.command]()


if __name__ == "__main__":
    main()
