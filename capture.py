#!/usr/bin/env python3
"""Capture the public page and a view of real command output with Chromium."""

import html
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import re

import lab


def ensure_headless():
    target = lab.TOOLS / "headless"
    binary = target / "usr/lib/chromium/chromium-headless-shell"
    packages = lab.TOOLS / "headless-debs"
    packages.mkdir(parents=True, exist_ok=True)
    if not binary.is_file():
        metadata = lab.run(["apt-cache", "show", "chromium-headless-shell"]).stdout
        versions = re.findall(r"^Version: (.+)$", metadata, re.MULTILINE)
        if not versions:
            raise RuntimeError("Chromium headless package is not available in the configured APT repositories")
        version = next((x for x in versions if ":" not in x and "rpt" not in x), versions[0])
        result = subprocess.run(["apt-get", "download", "chromium-headless-shell=" + version,
                                 "chromium-common=" + version], cwd=packages,
                                text=True, capture_output=True, timeout=240)
        (lab.EVIDENCE / "headless-download.txt").write_text(result.stdout + result.stderr)
        result.check_returncode()
        for deb in sorted(packages.glob("*.deb")):
            lab.run(["dpkg-deb", "-x", deb, target])
    versions_path = lab.ROOT / "docs/tool-versions.json"
    versions = json.loads(versions_path.read_text())
    versions["chromium_headless"] = [{"package": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                    for p in sorted(packages.glob("*.deb"))]
    versions_path.write_text(json.dumps(versions, indent=2) + "\n")


def capture(url, filename, expected):
    shell = lab.TOOLS / "headless/usr/lib/chromium/chromium-headless-shell"
    chromium = str(shell) if shell.is_file() else (shutil.which("chromium") or shutil.which("chromium-browser"))
    if not chromium:
        raise RuntimeError("Chromium is required for screenshot capture")
    output = lab.EVIDENCE / filename
    with tempfile.TemporaryDirectory(prefix="b3-1-capture-", dir="/dev/shm") as profile:
        env = dict(os.environ)
        for key in ["LD_LIBRARY_PATH", "LD_PRELOAD", "VK_ICD_FILENAMES", "MESA_LOADER_DRIVER_OVERRIDE", "GALLIUM_DRIVER"]:
            env.pop(key, None)
        base = [chromium, "--headless", "--disable-gpu", "--no-first-run", "--password-store=basic",
                "--disable-background-networking", "--disable-extensions", "--disable-sync",
                "--no-default-browser-check", "--hide-scrollbars", "--window-size=1480,1200",
                "--user-data-dir=" + profile, "--timeout=20000"]
        for mode in ["--screenshot=" + str(output), "--dump-dom"]:
            process = subprocess.Popen([*base, mode, url], env=env, text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
                raise RuntimeError("Chromium capture timed out: " + stderr[-2000:])
            if process.returncode or (mode == "--dump-dom" and expected not in stdout):
                raise RuntimeError("Capture did not show the expected page: " + stderr[-2000:])
    if not output.is_file():
        raise RuntimeError("Chromium did not write the screenshot")
    if output.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("Screenshot is not a PNG")
    print("Captured", output, flush=True)


def main():
    data = lab.state()
    if not data.get("verified_at") or data.get("cleaned_at"):
        raise RuntimeError("Capture after live verification and before cleanup")
    ensure_headless()
    # Refresh the displayed data directly from the running container and public endpoint.
    lab.docker("ps", "--filter=name=" + lab.CONTAINER, evidence="docker-ps.txt")
    code, _ = lab.http(data["url"] + "/health", "external-health.txt")
    if code != 200:
        raise RuntimeError("Public health check failed immediately before capture")
    blocks = []
    for title, name in [("Docker: running container", "docker-ps.txt"),
                        ("External HTTPS: /health", "external-health.txt")]:
        value = (lab.EVIDENCE / name).read_text()
        blocks.append("<h2>" + html.escape(title) + "</h2><pre>" + html.escape(value) + "</pre>")
    document = """<!doctype html><html><meta charset="utf-8"><title>B3-1 runtime evidence</title>
<style>body{margin:36px;background:#eef3f7;color:#152f44;font:17px/1.5 system-ui,sans-serif}
h1{font-size:30px}h2{font-size:20px;margin-top:24px}pre{background:#fff;border:1px solid #bdcdd9;
border-radius:10px;padding:20px;font:15px/1.45 monospace;white-space:pre-wrap;overflow-wrap:anywhere}
p{color:#4d6576}</style><h1>B3-1 / live command evidence</h1>
<p>Screenshot of a document showing actual captured CLI output. The output below is not a simulated terminal.</p>
""" + "\n".join(blocks) + "</html>"
    page = lab.RUNTIME / "runtime-evidence.html"
    page.write_text(document)
    capture(data["url"] + "/", "external-access.png", "Hello Pi.")
    capture(page.as_uri(), "runtime-evidence.png", "HTTP/2 200")
    capture(data["url"] + "/health", "external-health.png", "OK")
    lab.save(captured_at=lab.now())


if __name__ == "__main__":
    main()
