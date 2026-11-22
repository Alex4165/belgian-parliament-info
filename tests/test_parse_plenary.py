"""Regression tests for the plenary parser, on a synthetic report that mimics the Word export.

Run: python -m unittest discover tests
"""
import tempfile
import unittest
from pathlib import Path

from pipeline.parse_plenary import parse

REPORT = """<html><body>
<p class=MsoNormal>Plenumvergadering</p><p class=MsoNormal>Donderdag 19-11-2026 Avond</p>
<p class=MsoNormal>Voorlopig Verslag</p>
<p class=som2>01 Wetsontwerp in de inhoudstafel (1721/1-6)</p>
<p class=Titre1NL>Wetsontwerpen</p><p class=Titre1FR>Projets de loi</p>
<p class=Titre2NL><span>01</span> Wetsontwerp over iets (1721/1-6)</p>
<p class=Titre2NL>- Wetsontwerp over iets anders (1847/1-5)</p>
<p class=Titre2FR><span>01</span> Projet de loi sur quelque chose (1721/1-6)</p>
<p class=Titre3NL>Algemene bespreking</p><p class=Titre3FR>Discussion générale</p>
<p class=NormalNL>De algemene bespreking is geopend.</p>
<p class=NormalFR>La discussion générale est ouverte.</p>
<p class=NormalNL><span class=oraspr>01.01</span><span class=oraspr> Jan Peeters </span>(N-VA): Eerste alinea.</p>
<p class=NormalNL>Tweede alinea van Peeters.</p>
<p class=NormalNL>Voorzitter: Florence Reuter, ondervoorzitster.</p>
<p class=NormalNL>Derde alinea van Peeters, na de wissel van voorzitter.</p>
<p class=NormalFR><span class=oraspr>01.01</span><span class=oraspr> Jan Peeters </span>(N-VA): Premier alinéa.</p>
<p class=NormalFR><span class=oraspr>01.102</span><span class=oraspr> Marie Dupont </span>(PS): Tussenkomst nummer 102.</p>
<p class=NormalNL><span class=oraspr>01.103</span><span class=oraspr> Anneleen Van Bossuyt</span>, ministre: Antwoord.</p>
<p class=NormalNL>De algemene bespreking is gesloten.</p>
<p class=Titre1NL>Naamstemmingen</p><p class=Titre1FR>Votes nominatifs</p>
<p class=Titre2NL><span>02</span> Geheel van het wetsontwerp over iets (1721/6)</p>
<p class=Titre2FR><span>02</span> Ensemble du projet de loi (1721/6)</p>
<p class=NormalNL>Uitslag van de stemming / Résultat du vote.</p>
<table><tr><td><p>(Stemming/vote 1)</p></td></tr>
<tr><td><p>Ja</p></td><td><p>2</p></td><td><p>Oui</p></td></tr>
<tr><td><p>Nee</p></td><td><p>1</p></td><td><p>Non</p></td></tr>
<tr><td><p>Onthoudingen</p></td><td><p>0</p></td><td><p>Abstentions</p></td></tr>
<tr><td><p>Totaal</p></td><td><p>3</p></td><td><p>Total</p></td></tr></table>
<p class=NormalNL>Bijgevolg neemt de Kamer het wetsontwerp aan.</p>
<p class=NormalFR>En conséquence, la Chambre adopte le projet de loi.</p>
<p class=MsoNormal>Naamstemming - Vote nominatif: 1</p>
<table><tr><td><p>Ja</p></td><td><p>2</p></td><td><p>Oui</p></td></tr></table>
<p class=MsoNormal>Peeters Jan, Samyn Ellen</p>
<table><tr><td><p>Nee</p></td><td><p>1</p></td><td><p>Non</p></td></tr></table>
<p class=MsoNormal>Dupont Marie</p>
<table><tr><td><p>Onthoudingen</p></td><td><p>0</p></td><td><p>Abstentions</p></td></tr></table>
</body></html>"""


class ParsePlenaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = Path(tempfile.mkdtemp()) / "56"
        tmp.mkdir()
        path = tmp / "ip151x.html"
        path.write_bytes(REPORT.encode("cp1252"))
        cls.doc = parse(path)
        cls.items = cls.doc["items"]
        cls.speeches = [e for e in cls.items[0]["events"] if e["type"] == "speech"]

    def test_source(self):
        s = self.doc["source"]
        self.assertEqual((s["session"], s["date"], s["part"], s["provisional"]), (151, "2026-11-19", "evening", True))

    def test_items_and_joint_documents(self):
        self.assertEqual([i["number"] for i in self.items], ["01", "02"])
        self.assertEqual(self.items[0]["docs"], ["1721", "1847"])
        self.assertEqual(self.items[0]["subtitles"]["nl"], ["Wetsontwerp over iets anders (1847/1-5)"])
        self.assertTrue(self.items[0]["title"]["fr"].startswith("Projet de loi"))

    def test_speech_continues_across_chair_change(self):
        first = self.speeches[0]
        self.assertEqual((first["name"], first["party"]), ("Jan Peeters", "N-VA"))
        self.assertEqual(len(first["paragraphs"]), 3)

    def test_translated_copy_is_attached_not_duplicated(self):
        ids = [s["id"] for s in self.speeches]
        self.assertEqual(ids.count("01.01"), 1)
        self.assertEqual(self.speeches[0]["translation"]["paragraphs"], ["Premier alinéa."])

    def test_three_digit_speech_numbers_and_government(self):
        by_id = {s["id"]: s for s in self.speeches}
        self.assertEqual(by_id["01.102"]["party"], "PS")
        self.assertEqual(by_id["01.103"]["role"], "government")

    def test_vote_and_named_vote(self):
        vote = next(e for e in self.items[1]["events"] if e["type"] == "vote")
        self.assertEqual((vote["yes"], vote["no"], vote["abstain"], vote["total"]), (2, 1, 0, 3))
        self.assertTrue(vote["result"]["nl"].startswith("Bijgevolg neemt de Kamer"))
        self.assertEqual(self.doc["named_votes"]["1"]["yes"], ["Peeters Jan", "Samyn Ellen"])
        self.assertEqual(self.doc["named_votes"]["1"]["no"], ["Dupont Marie"])


if __name__ == "__main__":
    unittest.main()
