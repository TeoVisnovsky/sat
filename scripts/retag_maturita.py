"""Reapply the current broad Maturita taxonomy without rerendering PDF crops."""
from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path

from import_maturita import math_classify, slovak_classify


ROOT = Path(__file__).resolve().parents[1]


def prompt_text(markup: str) -> str:
    match = re.search(r'alt="([^"]*)"', markup)
    return html.unescape(match.group(1) if match else re.sub(r"<[^>]+>", " ", markup))


def retag(path: Path, subject: str) -> None:
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    domains = {name: ident for ident, name in db.execute("SELECT id,name FROM domains")}
    skills = {(domain, name): ident for ident, domain, name in db.execute("SELECT id,domain_id,name FROM skills")}

    def skill_id(domain: str, skill: str) -> int:
        if domain not in domains:
            domains[domain] = db.execute("INSERT INTO domains(name) VALUES (?)", (domain,)).lastrowid
        key = (domains[domain], skill)
        if key not in skills:
            skills[key] = db.execute("INSERT INTO skills(domain_id,name) VALUES (?,?)", key).lastrowid
        return skills[key]

    rows = db.execute("SELECT id,ordinal,prompt_html FROM questions").fetchall()
    for qid, ordinal, markup in rows:
        text = prompt_text(markup)
        if subject == "slovak":
            domain, sub, skill, source, requires, difficulty = slovak_classify(text, ordinal)
            values = (skill_id(domain, skill), sub, source, int(requires), difficulty, qid)
        else:
            domain, sub, skill, difficulty = math_classify(text)
            values = (skill_id(domain, skill), sub, "Naučené vedomosti", 0, difficulty, qid)
        db.execute("UPDATE questions SET skill_id=?,subcategory=?,knowledge_source=?,requires_stimulus=?,difficulty=? WHERE id=?", values)
    db.execute("DELETE FROM skills WHERE id NOT IN (SELECT DISTINCT skill_id FROM questions)")
    db.execute("DELETE FROM domains WHERE id NOT IN (SELECT DISTINCT domain_id FROM skills)")
    db.commit()
    db.close()
    print(path.name, "retagged", len(rows))


if __name__ == "__main__":
    for filename, subject in (("maturita-slovak-clean.db", "slovak"), ("maturita-math-clean.db", "math")):
        retag(ROOT / filename, subject)
