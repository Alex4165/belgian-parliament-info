"""Fetch committee reports ("VERSLAG") of a parliamentary document and extract their text per page.

Usage: python -m pipeline.committee 674 [1721 ...]  -> data/committee/56/56K0674006.json, ...

Committee reports are the Chamber's own written account of the committee discussion: per
member, with party, what they argued, plus the committee votes. Many parties argue only
there, not in plenary. The PDFs are bilingual (FR and NL columns); text is kept as is,
per page, so summaries can cite "56K0674006/p4".
"""
import html
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import pypdf

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "committee"
DOSSIER_URL = ("https://www.dekamer.be/kvvcr/showpage.cfm?section=/flwb&language=nl"
               "&cfm=/site/wwwcfm/flwb/flwbn.cfm?legislist=legisnr&dossierID={doc:04d}")
PDF_URL = "https://www.dekamer.be/FLWB/PDF/{leg}/{doc:04d}/{leg}K{doc:04d}{sub}.pdf"
UA = {"User-Agent": "belgian-parliament-info/0.1"}


def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def report_list(doc: int, leg: int = 56) -> list[dict]:
    """Subdocuments of type VERSLAG listed on the dossier page."""
    t = _get(DOSSIER_URL.format(doc=doc)).decode("latin-1")
    t = re.sub(r"(?s)<(script|style).*?</\1>", "", t)
    lines = [l.strip() for l in html.unescape(re.sub(r"<[^>]+>", "\n", t)).split("\n") if l.strip()]
    out = []
    for i, l in enumerate(lines):
        # "006", "[388 Kb]", "19/10/2026", "VERSLAG", ..., optionally "EERSTE LEZING/..."
        if re.fullmatch(r"\d{3}", l) and i + 3 < len(lines) and lines[i + 1].startswith("["):
            if lines[i + 3] == "VERSLAG":
                reading = next((x.split("/")[0].title() for x in lines[i + 4:i + 16]
                                if "LEZING" in x or "NA VERSLAG" in x), None)
                d, m, y = lines[i + 2].split("/")
                out.append({"id": f"{leg}K{doc:04d}{l}", "doc": str(doc), "sub": l,
                            "date": f"{y}-{m}-{d}", "reading": reading,
                            "url": PDF_URL.format(leg=leg, doc=doc, sub=l)})
    return out


def clean_page(t: str) -> str:
    t = re.sub(r"(\w) -\n(\w)", r"\1\2", t)           # hyphenation across lines: "pro -\nposition"
    t = re.sub(r"(\w)-\n(\w)", r"\1\2", t)
    t = t.replace("L ’", "L’").replace("D ’", "D’")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def fetch_reports(doc: int, leg: int = 56) -> list[Path]:
    paths = []
    for rep in report_list(doc, leg):
        path = OUT_DIR / str(leg) / f"{rep['id']}.json"
        if not path.exists():
            reader = pypdf.PdfReader(io.BytesIO(_get(rep["url"])))
            rep["pages"] = [clean_page(p.extract_text() or "") for p in reader.pages]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        paths.append(path)
    return paths


def load_reports(docs: list[str], leg: int = 56) -> list[dict]:
    """Cached reports for these documents (no network)."""
    out = []
    for doc in docs:
        for p in sorted((OUT_DIR / str(leg)).glob(f"{leg}K{int(doc):04d}*.json")):
            out.append(json.loads(p.read_text()))
    return out


if __name__ == "__main__":
    for a in sys.argv[1:]:
        for p in fetch_reports(int(a)):
            r = json.loads(p.read_text())
            print(f"{p.name}: {r['reading'] or ''} {r['date']}, {len(r['pages'])} pages, "
                  f"{sum(len(x) for x in r['pages'])} chars")
