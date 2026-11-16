"""Refresh official SJL content while preserving local study history."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "maturita-slovak-clean.db"
WORKING = ROOT / "maturita-slovak.db"


def main() -> None:
    if not WORKING.exists():
        return
    db = sqlite3.connect(WORKING)
    before = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
              for table in ("attempts", "notes", "review_state", "personal_difficulty", "question_tags")}
    db.execute("ATTACH DATABASE ? AS clean", (str(CLEAN),))
    local_ids = {row[0] for row in db.execute("SELECT id FROM questions")}
    clean_ids = {row[0] for row in db.execute("SELECT id FROM clean.questions")}
    if local_ids != clean_ids:
        raise RuntimeError("Working and clean SJL banks do not contain the same question IDs")
    columns = ("prompt_html", "passage_html", "answer_type", "correct_answer", "accepted_answers",
               "explanation_html", "answer_notes")
    assignments = ",".join(
        f"{column}=(SELECT {column} FROM clean.questions WHERE clean.questions.id=main.questions.id)"
        for column in columns
    )
    db.execute(f"UPDATE questions SET {assignments}")
    db.execute("UPDATE choices SET content_html=(SELECT content_html FROM clean.choices WHERE clean.choices.question_id=main.choices.question_id AND clean.choices.letter=main.choices.letter)")
    mismatched = db.execute(
        "SELECT COUNT(*) FROM main.questions q JOIN clean.questions c ON c.id=q.id "
        "WHERE q.prompt_html<>c.prompt_html OR q.correct_answer<>c.correct_answer OR q.accepted_answers<>c.accepted_answers"
    ).fetchone()[0]
    choice_mismatches = db.execute(
        "SELECT COUNT(*) FROM main.choices q JOIN clean.choices c ON c.question_id=q.question_id AND c.letter=q.letter "
        "WHERE q.content_html<>c.content_html"
    ).fetchone()[0]
    if mismatched or choice_mismatches:
        raise RuntimeError(f"Content refresh mismatch: questions={mismatched}, choices={choice_mismatches}")
    db.commit()
    after = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
    if before != after:
        raise RuntimeError(f"Personal history changed: {before} -> {after}")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RuntimeError("Working database integrity check failed")
    report = {"updated_questions": len(clean_ids), "preserved_personal_rows": after}
    (ROOT / "maturita-answer-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    db.close()
    print(json.dumps(report))


if __name__ == "__main__":
    main()
