"""Download Slovak-language and Math maturita PDFs from Zmaturuj.

The PDFs remain local source material.  The generated manifest records the
original URL, archive label, hash, and basic PDF validation data so an importer
can be reproduced and audited later.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
PAGE_CACHE = ROOT / "tmp" / "maturita-pages"
OUTPUT = ROOT / "sources" / "maturita"
BASE = "https://zmaturuj.zones.sk/"


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current_href is not None:
            text = " ".join("".join(self.current_text).split())
            self.links.append((self.current_href, text))
            self.current_href = None
            self.current_text = []


def get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "SAT-study-app archive importer/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def page_links(year: int) -> list[tuple[str, str]]:
    PAGE_CACHE.mkdir(parents=True, exist_ok=True)
    cached = PAGE_CACHE / f"{year}.html"
    if cached.exists():
        html = cached.read_text(encoding="utf-8", errors="replace")
    else:
        html = get(f"{BASE}maturitne-testy/{year}/").decode("utf-8", errors="replace")
        cached.write_text(html, encoding="utf-8")
    parser = LinkParser()
    parser.feed(html)
    return parser.links


def classify(label: str) -> str | None:
    folded = label.casefold()
    if folded.startswith("slovenský jazyk a literatúra"):
        return "slovak"
    if folded.startswith("matematika") and "maďarský preklad" not in folded:
        return "math"
    return None


def safe_name(url: str) -> str:
    name = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
    return re.sub(r"[^0-9A-Za-z._() -]+", "_", name).strip(" .")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, object]] = []
    missing_years: list[int] = []
    seen: set[tuple[int, str]] = set()

    for year in range(2008, 2027):
        selected: list[tuple[str, str, str]] = []
        for href, label in page_links(year):
            subject = classify(label)
            if subject and ".pdf" in href.casefold():
                url = urllib.parse.urljoin(BASE, href)
                key = (year, url)
                if key not in seen:
                    selected.append((url, label, subject))
                    seen.add(key)

        if not selected:
            missing_years.append(year)
            continue

        year_dir = OUTPUT / str(year)
        year_dir.mkdir(exist_ok=True)
        for url, label, subject in selected:
            path = year_dir / safe_name(url)
            if not path.exists():
                path.write_bytes(get(url))
            data = path.read_bytes()
            if not data.startswith(b"%PDF"):
                raise RuntimeError(f"Not a PDF: {url}")
            with fitz.open(path) as document:
                pages = document.page_count
                text_chars = sum(len(page.get_text()) for page in document)
            # The 2008 archive explicitly bundles each test and its key in one PDF.
            kind = "test_with_key" if year == 2008 else "answer_key" if "/kluce/" in url.casefold() or "kľúč" in label.casefold() else "test"
            files.append(
                {
                    "year": year,
                    "subject": subject,
                    "kind": kind,
                    "archive_label": label,
                    "source_url": url,
                    "local_path": path.relative_to(ROOT).as_posix(),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "pages": pages,
                    "text_characters": text_chars,
                }
            )
            print(f"{year} {subject:7} {kind:13} {path.name}")

    manifest = {
        "archive_url": f"{BASE}maturitne-testy/",
        "years_requested": [2008, 2026],
        "years_without_matching_files": missing_years,
        "file_count": len(files),
        "files": files,
    }
    (OUTPUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Downloaded/verified {len(files)} PDFs; missing years: {missing_years}")


if __name__ == "__main__":
    main()
