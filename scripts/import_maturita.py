"""Build the two Slovak Maturita banks from the locally downloaded archive.

The importer deliberately uses one canonical form per subject/year and level A
for 2008.  Each prompt and passage is rendered from its source PDF so formulas,
figures, underlining, poetry and tables remain faithful to the official paper.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import fitz
import pdfplumber
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.review_maturita_taxonomy import chosen_tests  # noqa: E402

ASSET_ROOT = ROOT / "assets" / "maturita"
SCHEMA = ROOT / "schema.sql"
SOURCE_URL = "https://zmaturuj.zones.sk/maturitne-testy/"
YEARS_WITHOUT_TESTS = {2020, 2021}
SHORT_SJL = {n for n in range(1, 65) if (n - 1) % 8 >= 5}
CHOICE_SJL = set(range(1, 65)) - SHORT_SJL


def clean_text(value: str) -> str:
    return " ".join(value.replace("\xad", "").replace("\x07", " ").split())


def printed_number(value: str) -> int | None:
    compact = "".join(ch for ch in value if ch.isdigit())
    residue = "".join(ch for ch in value if not ch.isdigit())
    return int(compact) if compact and len(compact) <= 2 and not residue.strip() else None


def page_words(page: fitz.Page) -> list[tuple]:
    return sorted(page.get_text("words"), key=lambda w: (round(w[1], 1), w[0]))


def line_groups(page: fitz.Page) -> list[list[tuple]]:
    groups: list[list[tuple]] = []
    for word in page_words(page):
        for group in reversed(groups[-3:]):
            if abs(group[0][1] - word[1]) < 5.5:
                group.append(word)
                break
        else:
            groups.append([word])
    for group in groups:
        group.sort(key=lambda w: w[0])
    return groups


def question_positions(doc: fitz.Document, count: int) -> dict[int, tuple[int, float, float]]:
    candidates: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for page_no, page in enumerate(doc):
        if page_no == 0:
            continue
        for group in line_groups(page):
            first = next((w for w in group if w[0] < 125 and printed_number(w[4].strip().rstrip(".")) is not None), None)
            if first is None:
                continue
            number = printed_number(first[4].strip().rstrip("."))
            if not 1 <= number <= count:
                continue
            # Older layouts put the number in a separate text block above the stem.
            # Left-margin placement excludes printed page numbers and diagram labels.
            if first[0] > 100 or not 45 < first[1] < page.rect.height - 45:
                continue
            candidates[number].append((page_no, max(38.0, first[1] - 5), first[0]))
    result = {}
    for number in range(1, count + 1):
        rows = candidates.get(number, [])
        if not rows:
            raise ValueError(f"question {number} not located")
        # The real occurrence is the earliest one in the test; repeated diagram labels
        # and answer-key rows, where present, occur later.
        result[number] = min(rows, key=lambda row: (row[0], row[1]))
    return result


def crop_for_question(doc: fitz.Document, positions: dict[int, tuple[int, float, float]], number: int) -> fitz.Rect:
    page_no, top, _ = positions[number]
    page = doc[page_no]
    bottoms = [y for n, (p, y, _) in positions.items() if p == page_no and y > top + 3]
    bottom = min(bottoms) - 2 if bottoms else page.rect.height - 42
    return fitz.Rect(28, top, page.rect.width - 25, max(top + 35, bottom))


def stimulus_positions(doc: fitz.Document, qpos: dict[int, tuple[int, float, float]]) -> dict[int, tuple[int, float, float]]:
    found: dict[int, tuple[int, float, float]] = {}
    for page_no, page in enumerate(doc):
        words = page_words(page)
        for index, word in enumerate(words[:-1]):
            if clean_text(word[4]).casefold().startswith("ukážka"):
                nearby = words[index + 1 : index + 5]
                number_word = next((w for w in nearby if abs(w[1] - word[1]) < 4 and re.fullmatch(r"[1-8]", w[4])), None)
                if number_word:
                    found[int(number_word[4])] = (page_no, max(35.0, word[1] - 5), word[0])
    for section in range(1, 9):
        if section in found:
            continue
        first = (section - 1) * 8 + 1
        page_no, qtop, _ = qpos[first]
        found[section] = (page_no, 45.0, 25.0)
    return found


def render_crop(doc: fitz.Document, page_no: int, clip: fitz.Rect, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Taxonomy/database rebuilds should not recompress thousands of unchanged
    # source crops. Delete assets/maturita first when the PDF archive changes.
    if target.is_file() and target.stat().st_size:
        return
    pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), clip=clip, alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    image.save(target, "WEBP", quality=82, method=6)


def image_html(path: Path, alt: str, kind: str) -> str:
    relative = path.relative_to(ROOT).as_posix()
    return f'<img class="source-crop {kind}" src="./{html.escape(relative)}" alt="{html.escape(alt[:1500])}" loading="lazy">'


def key_path(test_row: dict) -> Path:
    year, subject = int(test_row["year"]), str(test_row["subject"])
    if test_row["kind"] == "test_with_key":
        return ROOT / str(test_row["local_path"])
    manifest = json.loads((ROOT / "sources/maturita/manifest.json").read_text(encoding="utf-8"))
    row = next(r for r in manifest["files"] if int(r["year"]) == year and r["subject"] == subject and r["kind"] == "answer_key")
    return ROOT / row["local_path"]


MATH_2008 = {
    1:"0,7",2:"21",3:"75",4:"78125",5:"52",6:"5,5",7:"4",8:"19,47",9:"-11",10:"420",
    11:"1,2",12:"0,5",13:"2",14:"5",15:"-128",16:"43",17:"-10",18:"60",19:"120",20:"3,96",
    21:"B",22:"D",23:"E",24:"A",25:"E",26:"B",27:"B",28:"E",29:"D",30:"C",
}


def first_column_rows(page: fitz.Page, wanted: set[int]) -> dict[int, str]:
    result: dict[int, str] = {}
    # Single-form keys have a wide answer column (including rubric notes such
    # as an accepted alternative); parallel-form keys put another answer at
    # the right, so the first column must end sooner.
    groups = line_groups(page)
    first_row = next((g for g in groups if any(w[4].strip() in {"1", "01"} for w in g)), [])
    table_top = first_row[0][1] if first_row else 0
    row_values = [w for w in first_row if w[4].strip() not in {"1", "01"}]
    parallel = len(row_values) >= 2 and row_values[1][0] - row_values[0][2] > 50
    test_headers = re.findall(r"\btest\s+\d", page.get_text(), flags=re.I)
    threshold = page.rect.width * (0.58 if parallel or len(test_headers) > 1 else 0.80)
    for group in groups:
        if group[0][1] < table_top - 1:
            continue
        for index, word in enumerate(group):
            token = word[4].strip()
            if not re.fullmatch(r"0?\d{1,2}", token) or int(token) not in wanted or word[0] > page.rect.width * .42:
                continue
            parts = [w[4] for w in group[index + 1 :] if word[2] + 8 < w[0] < threshold]
            if parts:
                # Some key PDFs repeat task numbers in explanatory notes below the
                # table.  The actual answer row appears first, so never let a later
                # note overwrite it.
                result.setdefault(int(token), clean_text(" ".join(parts)).replace("–", "-"))
            break
    return result


def table_number(value: object) -> int | None:
    match = re.fullmatch(r"0?(\d{1,2})", clean_text(str(value or "")))
    return int(match.group(1)) if match else None


def slovak_table_key(path: Path, combined_2008: bool = False) -> tuple[dict[int, str], dict[int, str]]:
    """Read the canonical SJL key from actual table cells, never page coordinates.

    Answer-key PDFs often contain two shuffled forms side by side or one after
    another.  The first table is the canonical form selected by this importer.
    Continuation tables have no header and are collected until all 24 open
    answers are present.  The 2008 level-A paper embeds its key at the end.
    """
    answers: dict[int, str] = {}
    notes: dict[int, str] = {}
    started_short = False
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                rows = [row for row in table if row]
                numeric = [(table_number(row[0]), row) for row in rows]
                numeric = [(number, row) for number, row in numeric if number is not None]
                numbers = {number for number, _ in numeric}
                if not numbers:
                    continue

                # The canonical multiple-choice table is the first complete
                # 40-row table.  Parallel-form answers live in later columns.
                if len(numbers & CHOICE_SJL) >= 35 and not (answers.keys() & CHOICE_SJL):
                    for number, row in numeric:
                        if number not in CHOICE_SJL or len(row) < 2:
                            continue
                        value = clean_text(str(row[1] or "")).replace("–", "-")
                        if value:
                            answers[number] = value
                    continue

                short_numbers = numbers & SHORT_SJL
                if not short_numbers:
                    continue
                if not started_short:
                    # A canonical open-answer section always starts with the
                    # first open task (6). For the combined 2008 paper this
                    # also deliberately chooses level A before level B.
                    if 6 not in short_numbers:
                        continue
                    started_short = True
                elif 6 in short_numbers and (answers.keys() & SHORT_SJL):
                    # Beginning of the second shuffled test form / level B.
                    break

                for number, row in numeric:
                    if number not in SHORT_SJL or len(row) < 2 or number in answers:
                        continue
                    value = clean_text(str(row[1] or "")).replace("–", "-")
                    if not value:
                        continue
                    answers[number] = value
                    extra = [clean_text(str(cell or "")) for cell in row[2:] if clean_text(str(cell or ""))]
                    if extra:
                        notes[number] = " ".join(extra)
                if len(answers.keys() & SHORT_SJL) == len(SHORT_SJL):
                    break
            if len(answers) == 64:
                break
    return answers, notes


def parse_answers(test_row: dict) -> tuple[dict[int, str], dict[int, str]]:
    year, subject = int(test_row["year"]), str(test_row["subject"])
    if year == 2008 and subject == "math":
        return dict(MATH_2008), {}
    path = key_path(test_row)
    if subject == "slovak":
        answers, notes = slovak_table_key(path, test_row["kind"] == "test_with_key")
        missing = sorted(set(range(1, 65)) - set(answers))
        if missing:
            raise ValueError(f"{year} {subject}: missing table-key answers {missing}")
        return answers, notes
    doc = fitz.open(path)
    wanted = set(range(1, 31)) if subject == "math" else CHOICE_SJL
    answers: dict[int, str] = {}
    pages = list(doc)[-3:-1] if test_row["kind"] == "test_with_key" else list(doc)
    for page in pages:
        for number, value in first_column_rows(page, wanted).items():
            answers.setdefault(number, value)
    notes: dict[int, str] = {}
    expected = 30 if subject == "math" else 64
    missing = sorted(set(range(1, expected + 1)) - set(answers))
    if missing:
        raise ValueError(f"{year} {subject}: missing key answers {missing}")
    return answers, notes


def accepted_answers(raw: str, answer_type: str) -> list[str]:
    value = clean_text(raw).replace("–", "-")
    if answer_type == "numeric":
        # Keys use “alebo”, parenthetical “uznáva sa aj …”, and in 2025 a
        # spaced slash plus an asterisk to mark two accepted results. A compact
        # slash remains a mathematical fraction.
        value = re.sub(r"\b(?:uznáva sa aj|uznať aj)\b", "|", value, flags=re.I)
        value = re.sub(r"\s+/\s+", "|", value).replace("*", "")
        value = value.replace("(", " ").replace(")", " ")
        parts = re.split(r"\||\s+(?:alebo|a)\s+", value, flags=re.I)
        result = []
        for part in parts:
            candidate = part.strip(" .,;").replace(" ", "").replace(",", ".")
            if re.fullmatch(r"[+\-]?(?:\d+(?:\.\d*)?|\.\d+|\d+/[+\-]?\d+)", candidate):
                result.append(candidate)
        return list(dict.fromkeys(result or [value.replace(" ", "").replace(",", ".")]))
    parts = re.split(r"\s*/\s*|\s+alebo\s+", value, flags=re.I)
    result = []
    for part in parts:
        part = re.sub(r"\([^)]*\)", "", part).strip(" .,;")
        if part and len(part) < 160:
            result.append(part)
            # Official SJL keys commonly put inflectional alternatives in a
            # single comma-separated cell. Keep the full phrase and accept
            # each explicitly listed variant as well.
            result.extend(piece.strip(" .;") for piece in part.split(",") if piece.strip(" .;"))
    return list(dict.fromkeys(result or [value]))


def strip_print_artifacts(text: str) -> str:
    text = re.sub(r"^©\s*[^0-9]{0,40}\s+\d{4}\s+\d+\s+", "", text, flags=re.I)
    text = re.sub(r"^\d{1,2}\s+[A-Za-zÁ-ž]+\s+\d{4}\s+\d+\s+\d+\s+", "", text)
    return clean_text(text)


def transcribed_prompt(extracted: str, target: Path, number: int, answer_type: str) -> tuple[str, dict[str, str]]:
    """Prefer accessible text, retaining the original crop as a disclosure."""
    source = strip_print_artifacts(extracted)
    # A few official PDFs encode option letters as Cyrillic lookalikes or a
    # lowercase glyph even though the visible paper says A-D.
    source = re.sub(
        r"\(([АВСДавсдa-d])\)",
        lambda match: "(" + {"А": "A", "В": "B", "С": "C", "Д": "D"}.get(
            match.group(1).upper(), match.group(1).upper()
        ) + ")",
        source,
    )
    crop = image_html(target, f"Úloha {number}: {source}", "question-crop")
    # The 2011 PDF has a broken character map, and one 2018 crop begins inside
    # the preceding passage. Never expose corrupt or clearly overlong text;
    # keep the faithful source image as the explicit fallback.
    if any(ord(char) < 32 and char not in "\t\r\n" for char in source) or (answer_type == "choice" and len(source) > 1800):
        return crop, {}
    choices: dict[str, str] = {}
    stem = source
    if answer_type == "choice":
        markers = list(re.finditer(r"\(([A-D])\)\s*", source))
        if [match.group(1) for match in markers[:4]] == list("ABCD"):
            stem = source[:markers[0].start()].strip()
            for index, match in enumerate(markers[:4]):
                end = markers[index + 1].start() if index < 3 else len(source)
                choices[match.group(1)] = source[match.end():end].strip()
    fallback = f'<details class="source-preview"><summary>Zobraziť originál z PDF</summary>{crop}</details>'
    if not stem:
        return crop, choices
    prompt = f"<p>{html.escape(stem)}</p>{fallback}"
    return prompt, choices


def slovak_classify(text: str, number: int) -> tuple[str, str, str, str, bool, str]:
    t = text.casefold()
    literature = {
        "Literárny druh a žáner": ["literár", "žáner", "román", "dráma", "tragédi", "epik", "lyrik"],
        "Kompozícia a rozprávač": ["rozprávač", "kompoz", "dej", "postav", "konflikt"],
        "Obrazné pomenovania a verš": ["metaf", "metonym", "personifik", "epitet", "rým", "verš", "strofe", "umelecký prostriedok"],
        "Literárne obdobia, autori a diela": ["autor", "dielo", "obdob", "romantiz", "realiz", "modern"],
    }
    language = {
        "Zvuková rovina jazyka": ["hlásk", "slabik", "výslov", "spodob"],
        "Pravopis a interpunkcia": ["pravopis", "interpunk", "čiark", "napísan"],
        "Lexikológia a význam slov": ["lexik", "synonym", "antonym", "homonym", "význam slova", "frazeolog"],
        "Tvorenie slov": ["slovotvor", "odvoden", "zložené slovo"],
        "Morfológia": ["slovný druh", "pád", "skloň", "časov", "gramatick", "zámeno", "číslov", "príslov", "prídavné meno"],
        "Syntax": ["vetn", "súvet", "prísud", "podmet", "predmet", "prívlast", "sklad", "veta obsahuje"],
        "Štylistika a komunikácia": ["jazykový štýl", "slohov", "komunika", "funkčný", "publicist", "informačný"],
        "Dejiny a spisovná podoba jazyka": ["kodifik", "spisovn", "bernol", "štúr", "dejiny jazyka"],
    }
    for sub, words in literature.items():
        if any(w in t for w in words):
            domain = "Literatúra"; break
    else:
        sub = ""
        for sub_name, words in language.items():
            if any(w in t for w in words):
                domain, sub = "Jazyk", sub_name; break
        else:
            domain = "Porozumenie a interpretácia textu"
            sub = "Práca s informáciami a významom textu"
    direct = any(w in t for w in ("podľa ukážky", "z ukážky", "v ukážke", "z textu", "v texte", "odsek", "podčiark"))
    inference = any(w in t for w in ("vyplýva", "dôvod", "zámer", "prečo", "možno usúdiť", "naznačuje"))
    transform = any(w in t for w in ("napíšte", "utvorte", "doplňte", "zmeňte", "vypíšte"))
    if transform: skill = "Aplikácia a tvorba odpovede"
    elif inference or any(w in t for w in ("interpret", "funkciu", "význam", "porovn", "spoločné", "rozdiel")): skill = "Interpretácia a odvodenie"
    elif direct: skill = "Vyhľadanie a určenie"
    else: skill = "Vedomosti a súvislosti"
    if direct and domain != "Porozumenie a interpretácia textu": source = "Text a vedomosti"
    elif direct or domain == "Porozumenie a interpretácia textu": source = "Z textu"
    else: source = "Naučené vedomosti"
    requires = source != "Naučené vedomosti"
    difficulty = "introductory" if skill in {"Vyhľadanie a určenie", "Vedomosti a súvislosti"} else "challenging" if skill == "Interpretácia a odvodenie" else "standard"
    return domain, sub, skill, source, requires, difficulty


def math_classify(text: str) -> tuple[str, str, str, str]:
    t = text.casefold()
    categories = [
        ("Údaje, pravdepodobnosť a kombinatorika", "Pravdepodobnosť a práca s údajmi", ["pravdepodob", "štatist", "priemer", "modus", "medián", "diagram", "počet možnost"]),
        ("Geometria", "Priestorová geometria", ["kock", "kváder", "ihlan", "hranol", "valec", "kužeľ", "guľa", "teles", "objem", "priestor"]),
        ("Geometria", "Rovinná a analytická geometria", ["trojuhol", "štvorec", "obdĺž", "kruž", "uhol", "priamk", "vektor", "súradnic", "mnohouhol", "obvod", "obsah"]),
        ("Funkcie a postupnosti", "Funkcie, grafy a postupnosti", ["funkci", "graf", "postupnos", "logarit", "exponenci", "sin", "cos", "tang", "inverzn"]),
    ]
    domain, sub = "Čísla a algebra", "Čísla, algebra, rovnice a logika"
    for candidate, child, words in categories:
        if any(w in t for w in words): domain, sub = candidate, child; break
    if domain == "Geometria": skill = "Geometrické uvažovanie"
    elif domain == "Údaje, pravdepodobnosť a kombinatorika" or any(w in t for w in ("obchod", "cena", "zľav", "rýchlos", "vzdial", "úrok", "výroba", "nádrž", "tabuľ", "diagram")): skill = "Práca s údajmi a modelovanie"
    elif domain == "Funkcie a postupnosti" or any(w in t for w in ("výrok", "platí", "dokáž", "tvrden", "rovnic", "nerovnic", "parameter")): skill = "Vzťahy a logické uvažovanie"
    else: skill = "Výpočty a úpravy"
    difficulty = "challenging" if len(text) > 650 else "introductory" if len(text) < 180 else "standard"
    return domain, sub, skill, difficulty


def stimulus_type(title: str) -> str:
    t = title.casefold()
    if any(w in t for w in ("báseň", "haiku", "marína", "verš")): return "poézia"
    if any(w in t for w in ("dráma", "hamlet", "antigona", "čajka", "grobiani")): return "dráma"
    if "rozhovor" in t: return "rozhovor"
    return "literárny alebo vecný text"


def legacy_2011_slovak_positions(doc: fitz.Document) -> dict[int, tuple[int, float, float]]:
    """The 2011 paper has a broken character map; preserve each source page intact."""
    result = {}
    for section in range(8):
        first_page = 1 + section * 2
        second_page = first_page + 1
        for offset in range(8):
            number = section * 8 + offset + 1
            result[number] = (first_page if offset < 2 else second_page, 45.0, 25.0)
    return result


def build_bank(subject: str, rows: list[dict]) -> tuple[Path, dict]:
    db_path = ROOT / ("maturita-slovak-clean.db" if subject == "slovak" else "maturita-math-clean.db")
    working = db_path.with_suffix(".tmp.db")
    working.unlink(missing_ok=True)
    db = sqlite3.connect(working)
    db.executescript(SCHEMA.read_text(encoding="utf-8"))
    report = {"subject": subject, "years": [], "questions": 0, "stimuli": 0, "category_counts": defaultdict(int), "skill_counts": defaultdict(int)}
    domain_ids: dict[str, int] = {}
    skill_ids: dict[tuple[str, str], int] = {}

    def skill_id(domain: str, skill: str) -> int:
        if domain not in domain_ids:
            domain_ids[domain] = db.execute("INSERT INTO domains(name) VALUES (?)", (domain,)).lastrowid
        key = (domain, skill)
        if key not in skill_ids:
            skill_ids[key] = db.execute("INSERT INTO skills(domain_id,name) VALUES (?,?)", (domain_ids[domain], skill)).lastrowid
        return skill_ids[key]

    for row in rows:
        year = int(row["year"]); source = ROOT / row["local_path"]; key = key_path(row)
        doc = fitz.open(source); count = 64 if subject == "slovak" else 30
        qpos = legacy_2011_slovak_positions(doc) if subject == "slovak" and year == 2011 else question_positions(doc, count)
        spos = stimulus_positions(doc, qpos) if subject == "slovak" else {}
        answers, notes = parse_answers(row)
        exam_id = f"maturita-{subject}-{year}-a"; duration = 100 if subject == "slovak" else 150
        front = clean_text(doc[0].get_text("text")); code_match = re.search(r"(?:Kód testu\s*)?(\d{2}\s*\d{4})", front, re.I)
        code = clean_text(code_match.group(1)) if code_match else str(year)
        db.execute("INSERT INTO exams VALUES (?,?,?,?,?,?,?)", (exam_id, subject, year, code, "A" if year == 2008 else "canonical", duration, SOURCE_URL))
        stimulus_html: dict[int, str] = {}
        if subject == "slovak":
            for section in range(1, 9):
                page_no, top, _ = spos[section]; first = (section - 1) * 8 + 1; qpage, qtop, _ = qpos[first]
                bottom = qtop - 3 if qpage == page_no else doc[page_no].rect.height - 42
                clip = fitz.Rect(28, top, doc[page_no].rect.width - 25, max(top + 80, bottom))
                target = ASSET_ROOT / "slovak" / str(year) / f"passage-{section}.webp"
                render_crop(doc, page_no, clip, target)
                text = clean_text(doc[page_no].get_text("text", clip=clip))
                title_match = re.search(r"Ukážka\s+\d+\s+(.{0,180})", text, re.I)
                title = clean_text(title_match.group(1)) if title_match else f"Ukážka {section}"
                stim_id = f"sjl-{year}-s{section}"
                stimulus_html[section] = image_html(target, f"Ukážka {section}: {text}", "stimulus-crop")
                db.execute("INSERT INTO stimuli VALUES (?,?,?,?,?,?,?,?)", (stim_id, exam_id, section, title, stimulus_html[section], stimulus_type(title), page_no + 1, page_no + 1))
                report["stimuli"] += 1
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        source_id = db.execute("INSERT INTO sources(filename,file_sha256) VALUES (?,?)", (source.name, source_sha)).lastrowid
        for number in range(1, count + 1):
            page_no, _, _ = qpos[number]; clip = crop_for_question(doc, qpos, number)
            target = ASSET_ROOT / subject / str(year) / f"q-{number:02}.webp"
            render_crop(doc, page_no, clip, target)
            extracted = clean_text(doc[page_no].get_text("text", clip=clip))
            extracted = re.sub(r"^0?%d\s*" % number, "", extracted).strip()
            if subject == "slovak":
                domain, sub, skill, source_kind, requires, difficulty = slovak_classify(extracted, number)
                section = (number - 1) // 8 + 1; stim_id = f"sjl-{year}-s{section}"
                answer_type = "choice" if number in CHOICE_SJL else "text"
                passage = stimulus_html[section]
            else:
                domain, sub, skill, difficulty = math_classify(extracted)
                source_kind, requires, stim_id, passage = "Naučené vedomosti", False, None, ""
                answer_type = "numeric" if number <= 20 else "choice"
            accepted = accepted_answers(answers[number], answer_type)
            correct = answers[number].strip() if answer_type == "choice" else accepted[0]
            if answer_type == "choice" and correct == "*":
                accepted = list("ABCD" if subject == "slovak" else "ABCDE")
                correct = "A"
                notes[number] = (notes.get(number, "") + " Anulovaná úloha: započítava sa každá odpoveď.").strip()
            qid = ("sjl" if subject == "slovak" else "mat") + f"-{year}-{number:02}"
            prompt, visible_choices = transcribed_prompt(extracted, target, number, answer_type)
            explanation = f"<p>Oficiálna odpoveď: <strong>{html.escape(answers[number])}</strong></p>"
            if notes.get(number): explanation += f"<p>{html.escape(notes[number])}</p>"
            db.execute("""INSERT INTO questions(id,skill_id,difficulty,passage_html,prompt_html,answer_type,correct_answer,accepted_answers,explanation_html,exam_id,ordinal,stimulus_id,subcategory,knowledge_source,requires_stimulus,answer_notes)
                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (qid, skill_id(domain, skill), difficulty, passage, prompt, answer_type, correct, json.dumps(accepted, ensure_ascii=False), explanation, exam_id, number, stim_id, sub, source_kind, int(requires), notes.get(number, "")))
            if answer_type == "choice":
                letters = "ABCD" if subject == "slovak" else "ABCDE"
                for letter in letters:
                    db.execute("INSERT INTO choices VALUES (?,?,?)", (qid, letter, visible_choices.get(letter, f"Možnosť {letter}")))
            db.execute("INSERT INTO question_sources VALUES (?,?,?,?)", (qid, source_id, page_no + 1, page_no + 1))
            report["questions"] += 1; report["category_counts"][domain] += 1; report["skill_counts"][skill] += 1
        report["years"].append(year)
        print(subject, year, count, "questions", flush=True)
    db.execute("INSERT INTO transfer_meta VALUES (?,?)", ("bank_id", f"maturita-{subject}-canonical-v1"))
    db.commit()
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
        raise RuntimeError("database validation failed")
    db.close(); working.replace(db_path)
    report["category_counts"] = dict(report["category_counts"]); report["skill_counts"] = dict(report["skill_counts"])
    return db_path, report


def main() -> None:
    selected = chosen_tests()
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)
    reports = []
    subjects = tuple(sys.argv[1:]) or ("slovak", "math")
    if any(subject not in {"slovak", "math"} for subject in subjects):
        raise SystemExit("usage: import_maturita.py [slovak] [math]")
    for subject in subjects:
        path, report = build_bank(subject, [r for r in selected if r["subject"] == subject])
        reports.append(report); print("built", path.name, path.stat().st_size)
    report_path = ROOT / "maturita-import-report.json"
    if report_path.exists() and len(subjects) < 2:
        old = json.loads(report_path.read_text(encoding="utf-8"))
        reports = [r for r in old if r.get("subject") not in subjects] + reports
        reports.sort(key=lambda r: (r.get("subject") != "slovak", r.get("subject", "")))
    report_path.write_text(json.dumps(reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
