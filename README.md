# SAT English Trainer

A minimal, local SAT Reading & Writing practice app with **753 questions**, answers and explanations, charts, and saved progress. No account, Codex installation, API key, or paid service is needed. Practice works offline after downloading.

## Download and start

### Windows

1. Install **Python 3.10 or newer** from [python.org](https://www.python.org/downloads/). Enable **Add Python to PATH** if offered.
2. [Download the ZIP](https://github.com/TeoVisnovsky/sat/archive/refs/heads/main.zip), or click **Code > Download ZIP** on GitHub.
3. **Extract the entire ZIP** into a folder where you want to keep your study data. Do not run it inside the ZIP.
4. Double-click **Start SAT.cmd** in that folder.
5. Your browser opens **http://127.0.0.1:8765**.

On first launch, the app copies `sat-clean.db` into your personal `sat.db`. Every question starts unseen. Later launches reuse your progress. No extra Python packages are required for normal use.

If the launcher does not work, open a terminal in the extracted folder and run:

```powershell
py server.py --open
```

If your Python installation uses `python` instead of `py`, run `python server.py --open`.

### macOS or Linux

Install Python 3.10 or newer, download and extract the ZIP, open a terminal in the extracted folder, and run:

```sh
python3 server.py --open
```

Keep the terminal open while practicing. Press **Ctrl+C** to stop the server. No `pip install` is needed for normal practice on any platform.

## How to practice

- Filter by category, skill, official difficulty, progress, personal difficulty, or tag. Search by question ID or passage text.
- Select A, B, C, or D. You can change your selection freely; the A-D keys also work.
- Optionally tick **I am unsure / guessing**, then click **Check**. Only Check records an attempt and reveals the answer.
- Rate **How did this feel?** as Easy, Medium, or Hard. **My difficulty** filters use your latest rating, independently of the official difficulty.
- Notes stay hidden when you open a question. Check an answer to reveal them, or choose **Show notes without answering** to review without recording an attempt. Notes autosave; **Save now** saves immediately.
- Enter personal tags separated by commas, then click **Save tags**.
- Wrong and guessed answers enter review. A confident correct retry removes a question from review; you can also mark questions manually.
- **Progress** shows unique questions completed and first-attempt accuracy. Retrying never inflates completion or erases earlier attempts.

Everything saves to your computer. Each friend has independent progress. Local question links work on the computer running the app; they do not share your server over the internet.

## Databases and starting fresh

Open **Databases** in the header to switch banks or **Add database**.

- `sat-clean.db`: the included template with all 753 questions and no attempts, notes, review flags, personal tags, or difficulty ratings.
- `sat.db`: your original working bank, created automatically on first launch.
- `databases/`: your imported working banks.

To start a separate fresh run, choose **Add database** and select `sat-clean.db`. The app imports a copy, so the template stays clean. Your old bank and history remain available in the dropdown. Each bank keeps its own notes and progress, including when different browser tabs use different banks.

Imports accept compatible **SAT Trainer SQLite files** (`.db`, `.sqlite`, `.sqlite3`) up to 50 MB, including app backups. Arbitrary SQLite files and PDFs cannot be uploaded through this control. Imported banks contain their text and inline charts; optional original PDF image previews are available in the original bank only.

## Back up, restore, and update

Click **Back up data** to download the selected database, including its notes, ratings, tags, and history. To restore, use **Databases > Add database** and select that backup.

Before installing an update, back up your data. Download the new version to a separate folder, stop the old server, start the new version, and import your backup. Do not replace your working database with the clean template.

If using Git, working databases, imported banks, logs, and temporary files are ignored, keeping your personal study data out of commits.

## Troubleshooting

- **Python not found:** install Python, reopen the terminal, and try `py --version` (Windows) or `python3 --version` (macOS/Linux).
- **Browser cannot connect:** start the app first, then open http://127.0.0.1:8765. Running from a terminal shows errors; the Windows launcher also writes `server-error.log`.
- **Port already in use:** the trainer may already be running. Open its existing URL, or use `python server.py --port 8767 --open` (substitute `py` or `python3` as appropriate).
- **After restarting your computer:** run the launcher or terminal command again. Saved progress remains.
- **Old version still appears:** stop the old server before starting your updated folder. If you used the hidden Windows launcher and cannot identify the process, restarting your computer stops it.
- **Import rejected:** use an app backup or `sat-clean.db`; unrelated SQLite files have a different structure.

## Question data

The included bank has 753 unique Reading & Writing questions across four domains and ten skills. PDF exports omitted the instruction lines; these were recovered from College Board's API by matching all four choices (including punctuation), checking the passage and correct answer, and retaining both export IDs and official references. All 753 matched with no unresolved conflicts.

Questions, prompts, choices, explanations, and inline charts are in the database. Original PDF passage previews are in `assets/`. No personal study history is distributed.

Question content belongs to College Board. This is an unofficial practice tool, not affiliated with or endorsed by College Board.

## Development

Python 3.10+ standard library, SQLite, and plain HTML/CSS/JavaScript. `schema.sql` documents the database.

```sh
python server.py --open
python test_service.py
```

Tests use disposable copies and leave your study history untouched.

### Optional PDF rebuild

Rebuilding needs PyMuPDF and your answer PDFs in the project folder, named `sat-rw-answers-*.pdf`:

```sh
python -m pip install -r requirements.txt
python import_pdfs.py
python recover_prompts.py
```

Run both steps. Recovery needs internet unless official responses are cached in `source-cache/`. Source PDFs and that cache are not required for practice and are not distributed in this repository. Reimporting preserves attempts, notes, tags, and ratings. Import reports contain the validation results.

The server binds only to `127.0.0.1` and is intended for local use, with no public hosting or device sync.
