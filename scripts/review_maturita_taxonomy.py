"""Create a read-only inventory of one Slovak and Math maturita form per year.

This is an analysis helper, not the production importer.  It deliberately picks
one test code/form.  For 2008, where the archive has distinct A/B levels rather
than shuffled codes, level A is used for the taxonomy review.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sources" / "maturita" / "manifest.json"
OUTPUT = ROOT / "tmp" / "maturita-review" / "questions.json"


def clean(value: str) -> str:
    value = value.replace("\x07", " ").replace("\u00ad", "")
    return " ".join(value.split())


def chosen_tests() -> list[dict[str, object]]:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidates = [row for row in data["files"] if row["kind"] in {"test", "test_with_key"}]
    selected: list[dict[str, object]] = []
    for year in sorted({int(row["year"]) for row in candidates}):
        for subject in ("slovak", "math"):
            rows = [row for row in candidates if int(row["year"]) == year and row["subject"] == subject]
            if year == 2008:
                marker = "sj_a_uroven" if subject == "slovak" else "ma_a"
                rows = [row for row in rows if marker in str(row["local_path"]).casefold()]
            if len(rows) != 1:
                raise RuntimeError(f"Expected one {subject} test for {year}, got {len(rows)}")
            selected.append(rows[0])
    return selected


def page_blocks(page: fitz.Page) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    for raw in page.get_text("dict")["blocks"]:
        if "lines" not in raw:
            continue
        text = clean("\n".join("".join(span["text"] for span in line["spans"]) for line in raw["lines"]))
        if text:
            blocks.append({"text": text, "bbox": raw["bbox"]})
    return blocks


def extract_questions(path: Path, subject: str, year: int) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    maximum = 64 if subject == "slovak" else 30
    doc = fitz.open(path)
    questions: dict[int, dict[str, object]] = {}
    stimuli: dict[int, dict[str, object]] = {}
    current: dict[str, object] | None = None

    for page_index, page in enumerate(doc):
        blocks = page_blocks(page)
        for index, block in enumerate(blocks):
            text = str(block["text"])
            x0, y0, _, y1 = block["bbox"]
            if subject == "slovak":
                stimulus_match = re.match(r"^Ukážka\s+(\d+)\b", text, re.IGNORECASE)
                if stimulus_match:
                    number = int(stimulus_match.group(1))
                    title = ""
                    for following in blocks[index + 1 : index + 4]:
                        candidate = str(following["text"])
                        if not candidate.lower().startswith("ukážka") and not re.match(r"^\d{1,2}\s+\S", candidate):
                            title = candidate
                            break
                    stimuli.setdefault(number, {"number": number, "page": page_index + 1, "title": title})

            match = re.match(r"^0?(\d{1,2})\s+(.+)$", text)
            is_start = False
            number = 0
            if match and x0 < 92 and 45 < y0 < 780 and y1 < 790:
                number = int(match.group(1))
                is_start = 1 <= number <= maximum and len(match.group(2)) > 4
            if is_start:
                current = {
                    "year": year,
                    "subject": subject,
                    "number": number,
                    "page": page_index + 1,
                    "text": clean(match.group(2)),
                }
                if subject == "slovak":
                    current["stimulus"] = (number - 1) // 8 + 1
                    current["answer_type"] = "single_choice" if (number - 1) % 8 < 5 else "short_text"
                else:
                    current["answer_type"] = "numeric" if number <= 20 else "single_choice"
                questions[number] = current
            elif current is not None and current["page"] == page_index + 1:
                # Choices and wrapped prompt lines are valuable classification context.
                if y0 < 780 and not text.startswith(("MATURITA ", "© ", "Školský rok", "Test pokračuje")):
                    current["text"] = clean(str(current["text"]) + " " + text)

    missing = sorted(set(range(1, maximum + 1)) - set(questions))
    if missing:
        raise RuntimeError(f"{path}: failed to extract questions {missing}")
    return [questions[i] for i in range(1, maximum + 1)], [stimuli[i] for i in sorted(stimuli) if 1 <= i <= 8]


def main() -> None:
    all_questions: list[dict[str, object]] = []
    all_stimuli: list[dict[str, object]] = []
    extraction_errors: list[dict[str, object]] = []
    for row in chosen_tests():
        path = ROOT / str(row["local_path"])
        try:
            questions, stimuli = extract_questions(path, str(row["subject"]), int(row["year"]))
        except RuntimeError as error:
            extraction_errors.append({"year": row["year"], "subject": row["subject"], "source": path.relative_to(ROOT).as_posix(), "error": str(error)})
            print("RENDER REVIEW NEEDED", row["year"], row["subject"], error)
            continue
        for question in questions:
            question["source"] = path.relative_to(ROOT).as_posix()
        for stimulus in stimuli:
            stimulus.update({"year": int(row["year"]), "subject": row["subject"], "source": path.relative_to(ROOT).as_posix()})
        all_questions.extend(questions)
        all_stimuli.extend(stimuli)
        print(row["year"], row["subject"], len(questions), len(stimuli), path.name)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"questions": all_questions, "stimuli": all_stimuli, "extraction_errors": extraction_errors}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("questions", len(all_questions), Counter(q["subject"] for q in all_questions))
    print("stimuli", len(all_stimuli))


if __name__ == "__main__":
    main()
