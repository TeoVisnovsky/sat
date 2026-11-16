import json
import re
import sqlite3
import unittest
from pathlib import Path

import transfer
from scripts.import_maturita import accepted_answers, parse_answers
from scripts.review_maturita_taxonomy import chosen_tests


ROOT = Path(__file__).resolve().parent


class MaturitaBankTests(unittest.TestCase):
    def open(self, name):
        db = sqlite3.connect(ROOT / name)
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return db

    def test_slovak_bank_structure_and_keys(self):
        db = self.open("maturita-slovak-clean.db")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 1088)
        self.assertEqual(dict(db.execute("SELECT answer_type,COUNT(*) FROM questions GROUP BY answer_type")), {"choice": 680, "text": 408})
        self.assertEqual(db.execute("SELECT COUNT(*) FROM stimuli").fetchone()[0], 136)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM domains").fetchone()[0], 3)
        self.assertLessEqual(db.execute("SELECT COUNT(DISTINCT name) FROM skills").fetchone()[0], 4)
        self.assertEqual([r[0] for r in db.execute("SELECT year FROM exams ORDER BY year")], [2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2022,2023,2024,2025,2026])
        self.assertEqual(db.execute("SELECT correct_answer FROM questions WHERE id='sjl-2008-01'").fetchone()[0], "B")
        self.assertEqual(db.execute("SELECT correct_answer FROM questions WHERE id='sjl-2009-08'").fetchone()[0].casefold(), "belie sa")
        annulled = db.execute("SELECT correct_answer,accepted_answers FROM questions WHERE id='sjl-2017-49'").fetchone()
        self.assertEqual(json.loads(annulled["accepted_answers"]), list("ABCD"))
        self.assertTrue(transfer.answer_correct(dict(annulled, answer_type="choice"), "D"))

    def test_every_slovak_answer_matches_fresh_official_key_parse(self):
        db = self.open("maturita-slovak-clean.db")
        for test in (row for row in chosen_tests() if row["subject"] == "slovak"):
            answers, _ = parse_answers(test)
            year = int(test["year"])
            for number, raw in answers.items():
                row = db.execute(
                    "SELECT answer_type,correct_answer,accepted_answers FROM questions WHERE id=?",
                    (f"sjl-{year}-{number:02}",),
                ).fetchone()
                expected = accepted_answers(raw, row["answer_type"])
                if row["answer_type"] == "choice" and raw.strip() == "*":
                    expected = list("ABCD")
                self.assertEqual(json.loads(row["accepted_answers"]), expected, f"{year} question {number}")

    def test_slovak_choices_are_transcribed_when_pdf_text_is_available(self):
        db = self.open("maturita-slovak-clean.db")
        transcribed = db.execute("SELECT COUNT(DISTINCT question_id) FROM choices WHERE content_html NOT LIKE 'Možnosť %'").fetchone()[0]
        self.assertGreaterEqual(transcribed, 590)
        row = db.execute("SELECT prompt_html FROM questions WHERE id='sjl-2009-01'").fetchone()[0]
        self.assertIn("<p>", row)
        self.assertIn("source-preview", row)

    def test_math_bank_structure_and_five_choices(self):
        db = self.open("maturita-math-clean.db")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM questions").fetchone()[0], 510)
        self.assertEqual(dict(db.execute("SELECT answer_type,COUNT(*) FROM questions GROUP BY answer_type")), {"choice": 170, "numeric": 340})
        self.assertEqual(db.execute("SELECT COUNT(*) FROM choices").fetchone()[0], 850)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM domains").fetchone()[0], 4)
        self.assertLessEqual(db.execute("SELECT COUNT(DISTINCT name) FROM skills").fetchone()[0], 4)
        self.assertFalse(db.execute("SELECT 1 FROM questions WHERE answer_type='choice' AND correct_answer NOT IN ('A','B','C','D','E') LIMIT 1").fetchone())
        answer = db.execute("SELECT accepted_answers FROM questions WHERE id='mat-2026-01'").fetchone()[0]
        self.assertIn("0.35", json.loads(answer))

    def test_all_rendered_assets_exist(self):
        for name in ("maturita-slovak-clean.db", "maturita-math-clean.db"):
            db = self.open(name)
            for row in db.execute("SELECT passage_html,prompt_html FROM questions"):
                for value in row:
                    for source in re.findall(r'src="\.\/([^"]+)"', value):
                        self.assertTrue((ROOT / source).is_file(), source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
