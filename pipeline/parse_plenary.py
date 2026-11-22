"""Parse a plenary verbatim report (CRIV, HTML export from Word) into structured JSON.

Usage: python -m pipeline.parse_plenary data/raw/56/ip151x.html [...]
Writes data/plenary/<leg>/ipNNN.json.

Output shape (see README): session metadata, agenda items with an ordered list of
events (speeches, procedural lines, vote results), and the named-vote annex.
"""
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "plenary"
SOURCE_URL = "https://www.dekamer.be/doc/PCRI/html/{leg}/ip{num:03d}x.html"

PARTIES = {
    "N-VA", "VB", "MR", "PS", "PVDA-PTB", "Les Engagés", "Vooruit", "cd&v",
    "Ecolo-Groen", "Anders.", "DéFI", "INDEP-ONAFH",
}
SESSION_PARTS = {"Ochtend": "morning", "Namiddag": "afternoon", "Middag": "afternoon", "Avond": "evening"}

# "01.01  Charlotte Verkeyn (N-VA): text" / "02.03  Frank Vandenbroucke, ministre: text"
SPEECH_RE = re.compile(r"^(?P<id>\d{2}\.\d{2})\s+(?P<who>[^:]{2,120}?)\s*:\s*(?P<text>.*)$", re.S)
DOC_RE = re.compile(r"\((\d{2,4})/[\d\-, /]+\)")
VOTE_NO_RE = re.compile(r"\(Stemming/vote (\d+)\)")
NAMED_VOTE_RE = re.compile(r"Naamstemming - Vote nominatif:\s*(\d+)")
CHAIR_CHANGE_RE = re.compile(r"^(Voorzitter|Présidente?|Président)\s*:")
PROCEDURE_RE = re.compile(
    r"^(Voorzitter|Présidente?|Président)\s*:"
    r"|^(De|Le|La) (voorzitter|président|présidente)\s*:"
    r"|^De (algemene )?bespreking\b|^La discussion\b"
    r"|^(De|Het) (artikelen|artikel|amendementen|geheel)\b|^(Les|L'|Le|La) (articles|article|amendements|ensemble)\b"
    r"|^De rapporteurs?\b|^(Les|Le|La) rapporteu"
    r"|^Vraagt (nog )?iemand\b|^Quelqu'un demande"
    r"|^(Begin|Einde|Uitslag) van de stemming|^Heeft iedereen gestemd"
    r"|^(Voorstel|Proposition) (ingediend|déposée)"
    r"|^(Wetsontwerp|Projet de loi) (ingediend|déposé)"
    r"|^Ingediende (amendementen|moties)|^(Amendements|Motions) déposé"
    r"|^De ingediende|^Les amendements|^Wij vatten|^Nous passons|^Nous abordons"
)
DATE_RE = re.compile(r"\b(\d{2})-(\d{2})-(\d{4})\b")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def para_lang(cls: str) -> str | None:
    if cls.endswith("NL"):
        return "nl"
    if cls.endswith("FR"):
        return "fr"
    return None


def parse_speaker(who: str) -> dict:
    who = clean(who)
    m = re.match(r"^(.*?)\s*\(([^)]+)\)$", who)
    if m and m.group(2) in PARTIES:
        return {"name": m.group(1), "party": m.group(2), "role": None}
    if who.lower().startswith("de voorzitter") or who.lower().startswith("la présidente") or who.lower().startswith("le président"):
        return {"name": None, "party": None, "role": "chair"}
    m = re.match(r"^(Minister|Eerste minister|Vice-eersteminister|Staatssecretaris)\s+(.*)$", who)
    if m:
        return {"name": m.group(2), "party": None, "role": "government"}
    m = re.match(r"^(.*?)\s*,\s*(.+)$", who)
    if m:
        return {"name": m.group(1), "party": None, "role": "government", "title": m.group(2)}
    return {"name": who, "party": None, "role": None}


def walk(soup):
    """Yield (cls, text, in_table) for every <p> in document order."""
    for p in soup.find_all("p"):
        text = clean(p.get_text(" "))
        if not text:
            continue
        cls = (p.get("class") or [""])[0]
        yield cls, text, p.find_parent("table") is not None, p


def parse(path: Path) -> dict:
    raw = path.read_bytes().decode("cp1252", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    m = re.search(r"ip(\d{3})", path.name)
    num = int(m.group(1)) if m else None
    leg = int(path.parent.name) if path.parent.name.isdigit() else 56

    head = clean(soup.get_text(" ")[:5000])
    dm = DATE_RE.search(head)
    date = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else None
    part = next((v for k, v in SESSION_PARTS.items() if re.search(rf"\b{k}\b", head)), None)

    doc = {
        "source": {
            "type": "plenary",
            "legislature": leg,
            "session": num,
            "url": SOURCE_URL.format(leg=leg, num=num) if num else None,
            "date": date,
            "part": part,
            "provisional": "Voorlopig Verslag" in head,
        },
        "items": [],
        "named_votes": {},
    }

    section = None          # Titre1: {"nl":..., "fr":...}
    item = None             # current agenda item
    speech = None           # current speech event
    vote = None             # current vote event (table being read)
    annex = None            # current named vote in the annex
    annex_key = None
    pending_count = None
    in_toc = True
    votes_by_number = {}

    def events():
        return item["events"] if item else None

    for cls, text, in_table, p in walk(soup):
        lang = para_lang(cls)

        if cls.startswith("Titre1"):
            in_toc = False
            speech = None
            if lang == "nl":
                section = {"nl": text, "fr": None}
            elif section and lang == "fr":
                section["fr"] = text
            continue
        if in_toc or cls.startswith("som"):
            continue

        # --- named-vote annex -------------------------------------------------
        nm = NAMED_VOTE_RE.search(text)
        if nm:
            annex = {"yes": [], "no": [], "abstain": []}
            doc["named_votes"][nm.group(1)] = annex
            annex_key = None
            item = speech = vote = None  # the annex closes the agenda
            continue
        if annex is not None:
            key = {"Ja": "yes", "Oui": "yes", "Nee": "no", "Non": "no",
                   "Onthoudingen": "abstain", "Abstentions": "abstain"}.get(text)
            if key:
                annex_key = key
                continue
            if annex_key and not text.isdigit():
                annex[annex_key] += [n.strip() for n in text.split(",") if n.strip()]
            continue

        # --- agenda items -----------------------------------------------------
        if cls.startswith("Titre2"):
            speech = None
            vote = None
            m2 = re.match(r"^(\d{2})\s+(.*)$", text)
            number, title = (m2.group(1), m2.group(2)) if m2 else (None, text)
            lang = lang or "nl"
            if number and lang == "nl" or item is None:
                item = {
                    "number": number,
                    "section": dict(section) if section else None,
                    "title": {"nl": None, "fr": None},
                    # joint items / interpellations: extra "- ..." title lines
                    "subtitles": {"nl": [], "fr": []},
                    "docs": [],
                    "events": [],
                }
                doc["items"].append(item)
            if number:
                item["title"][lang] = title
            else:
                item["subtitles"][lang].append(title.lstrip("- ").strip())
            item["docs"] = sorted(set(item["docs"]) | set(DOC_RE.findall(title)))
            continue
        if item is None:
            continue
        if cls.startswith(("Titre3", "Titre4")):
            speech = None
            level = 3 if cls.startswith("Titre3") else 4
            ev = events()
            if lang == "fr" and ev and ev[-1]["type"] == "heading" and ev[-1]["fr"] is None:
                ev[-1]["fr"] = text
            else:
                ev.append({"type": "heading", "level": level, "nl": text if lang != "fr" else None,
                           "fr": text if lang == "fr" else None})
            continue

        # --- vote result tables ------------------------------------------------
        vm = VOTE_NO_RE.search(text)
        if vm:
            speech = None
            number = int(vm.group(1))
            subject = next((e["text"] for e in reversed(events())
                            if e["type"] == "procedure" and e["lang"] == "nl"
                            and e["text"].startswith("Stemming over")), None)
            vote = {"type": "vote", "number": number, "subject": subject, "yes": None, "no": None,
                    "abstain": None, "total": None, "result": {"nl": None, "fr": None}}
            earlier = votes_by_number.get(number)
            if earlier:  # "Mag de uitslag van de vorige stemming ook gelden?" -> same result reused
                vote.update({k: earlier[k] for k in ("yes", "no", "abstain", "total")}, reused=True)
            else:
                votes_by_number[number] = vote
            events().append(vote)
            pending_count = None
            continue
        if in_table and vote is not None:
            key = {"Ja": "yes", "Nee": "no", "Onthoudingen": "abstain", "Totaal": "total"}.get(text)
            if key:
                pending_count = key
            elif pending_count and text.isdigit():
                vote[pending_count] = int(text)
                pending_count = None
            continue
        if vote is not None and not in_table and vote["result"]["nl"] is None and lang == "nl":
            vote["result"]["nl"] = text
            continue
        if vote is not None and not in_table and vote["result"]["fr"] is None and lang == "fr":
            vote["result"]["fr"] = text
            vote = None
            continue

        # --- speeches and procedure -------------------------------------------
        if p.find(class_="oraspr"):
            sm = SPEECH_RE.match(text)
            if sm:
                speech = {"type": "speech", "id": sm.group("id"), **parse_speaker(sm.group("who")),
                          "lang": lang, "paragraphs": [clean(sm.group("text"))]}
                events().append(speech)
                continue
        if cls.startswith("ital"):
            events().append({"type": "note", "lang": lang, "text": text})
            continue
        if PROCEDURE_RE.match(text):
            # chair formulas; a chair change ("Voorzitter: X") interrupts but does not end a speech
            events().append({"type": "procedure", "lang": lang, "text": text})
            if not CHAIR_CHANGE_RE.match(text):
                speech = None
            continue
        if speech is not None:
            speech["paragraphs"].append(text)
            continue
        events().append({"type": "procedure", "lang": lang, "text": text})

    return doc



def main(paths):
    for a in paths:
        path = Path(a)
        doc = parse(path)
        out = OUT_DIR / str(doc["source"]["legislature"]) / f"ip{doc['source']['session']:03d}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        speeches = sum(1 for i in doc["items"] for e in i["events"] if e["type"] == "speech")
        votes = sum(1 for i in doc["items"] for e in i["events"] if e["type"] == "vote")
        print(f"{out}: {len(doc['items'])} items, {speeches} speeches, {votes} votes, "
              f"{len(doc['named_votes'])} named votes")


if __name__ == "__main__":
    main(sys.argv[1:])
