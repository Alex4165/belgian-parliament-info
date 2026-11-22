"""Download plenary verbatim reports (CRIV) from dekamer.be into data/raw/.

Usage: python -m pipeline.fetch 151 [152 ...]   (session numbers, legislature 56)
"""
import sys
import urllib.request
from pathlib import Path

LEGISLATURE = 56
URL = "https://www.dekamer.be/doc/PCRI/html/{leg}/ip{num:03d}x.html"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def fetch(num: int, leg: int = LEGISLATURE, force: bool = False) -> Path:
    out = RAW_DIR / str(leg) / f"ip{num:03d}x.html"
    if out.exists() and not force:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = URL.format(leg=leg, num=num)
    req = urllib.request.Request(url, headers={"User-Agent": "belgian-parliament-info/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(fetch(int(a)))
