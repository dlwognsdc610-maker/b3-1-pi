"""Create the one-page architecture diagram without third-party dependencies."""

from pathlib import Path


def write_architecture(path):
    ops = []

    def color(s):
        return " ".join(str(int(s[i:i + 2], 16) / 255) for i in (0, 2, 4))

    def box(x, y, w, h, fill="ffffff", stroke="a8bbc8", dashed=False):
        ops.append(f"q {color(fill)} rg {color(stroke)} RG 1.3 w "
                   f"{'[6 4] 0 d ' if dashed else ''}{x} {y} {w} {h} re B Q")

    def text(x, y, value, size=12, bold=False, shade="19364a"):
        value = value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"BT /{'B' if bold else 'F'} {size} Tf {color(shade)} rg "
                   f"1 0 0 1 {x} {y} Tm ({value}) Tj ET")

    def arrow(points, shade="26718a", dashed=False):
        path = f"{points[0][0]} {points[0][1]} m " + " ".join(f"{x} {y} l" for x, y in points[1:])
        ops.append(f"q {color(shade)} RG 2 w {'[5 4] 0 d ' if dashed else ''}{path} S Q")
        x, y = points[-1]
        px, py = points[-2]
        if x != px:
            d = -8 if x > px else 8
            tri = f"{x} {y} m {x+d} {y+4} l {x+d} {y-4} l"
        else:
            d = -8 if y > py else 8
            tri = f"{x} {y} m {x+4} {y+d} l {x-4} {y+d} l"
        ops.append(f"q {color(shade)} rg {tri} h f Q")

    box(0, 0, 1120, 760, "f4f7f9", "f4f7f9")
    text(40, 708, "HELLO PI / PUBLIC WEB SERVICE", 28, True)
    text(40, 677, "B3-1  |  Raspberry Pi 5 + Docker + Nginx + Cloudflare Quick Tunnel", 15)
    text(40, 650, "Alternative platform implementation. AWS resources are not created.", 11, shade="526f80")

    box(450, 235, 630, 390, "eaf2f7", "85a6bb")
    text(470, 599, "Raspberry Pi 5 / Debian / ARM64", 18, True)
    text(470, 575, "Dedicated Docker engine: local Unix socket; no remote API", 11)
    box(490, 473, 230, 77, "ffffff", "5c9c99")
    text(506, 523, "cloudflared", 16, True)
    text(506, 500, "Origin: 127.0.0.1:18081", 12)
    box(760, 473, 265, 77, "ffffff", "5c9c99")
    text(775, 523, "Loopback port publishing", 14, True)
    text(775, 500, "127.0.0.1:18081 -> container:8080", 11)
    arrow([(720, 511), (760, 511)])

    box(490, 275, 535, 160, "ffffff", "80a6bd", True)
    text(507, 409, "Dedicated bridge: codyssey-b3-1-net", 14, True)
    text(507, 387, "Subnet 10.31.0.0/24", 12)
    text(507, 363, "Gateway 10.31.0.1", 12)
    text(507, 339, "NAT outbound via Pi", 11)
    box(736, 298, 267, 98, "edf7ef", "77a37f")
    text(751, 369, "Nginx / Docker container", 14, True)
    text(751, 346, "10.31.0.10:8080  /health -> OK", 11)
    text(751, 323, "UID 101 / read-only / no capabilities", 10)
    arrow([(895, 473), (895, 435), (869, 435), (869, 396)])

    box(40, 470, 175, 98)
    text(58, 533, "Internet client", 15, True)
    text(58, 509, "HTTPS /health", 12)
    text(58, 487, "200 OK", 12)
    box(267, 470, 142, 98, "fff4e6", "ba995b")
    text(283, 533, "Cloudflare", 15, True)
    text(283, 509, "Public TLS edge", 11)
    text(283, 487, "*.trycloudflare.com", 10)
    arrow([(215, 519), (267, 519)])
    text(223, 538, "443", 10)
    arrow([(409, 519), (490, 519)])
    text(415, 538, "Tunnel", 10)
    text(267, 447, "Tunnel is initiated outbound from the Pi.", 11, shade="526f80")

    box(40, 287, 175, 98)
    text(58, 352, "Management", 15, True)
    text(58, 326, "SSH key + Tailscale", 11)
    text(58, 305, "Private management path", 10)
    arrow([(215, 335), (310, 335), (310, 255), (450, 255)], "647589", True)
    text(255, 344, "TCP 22 / allowed sources", 10)

    box(40, 75, 1040, 120)
    text(58, 166, "Traffic and access rules", 15, True)
    text(58, 141, "Public: HTTPS 443 through the tunnel. Nginx's published host port listens only on 127.0.0.1.", 12)
    text(58, 118, "SSH: named management peers /32 and designated LAN; other SSH sources are dropped by the lab nftables table.", 11)
    text(58, 95, "Container egress: 0.0.0.0/0 -> 10.31.0.1 -> Pi NAT -> LAN router -> Internet. No cloud IAM is used.", 11)
    text(40, 36, "Security Group concept: nftables + loopback binding. Least privilege: UID 101, no-new-privileges, and all capabilities dropped.", 11, shade="526f80")

    stream = "\n".join(ops).encode("ascii")
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1120 760] /Resources << /Font << /F 4 0 R /B 5 0 R >> >> /Contents 6 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
               b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    content = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)


if __name__ == "__main__":
    write_architecture(Path(__file__).parent / "docs" / "architecture.pdf")
