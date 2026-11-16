# SAT and Maturita Trainer

A minimal practice app with four separate banks: **753 SAT Reading & Writing**, **536 SAT Math**, **1,088 Slovak Maturita language and literature**, and **510 Slovak Maturita mathematics** questions. It includes official answers, source-faithful diagrams and passages, filters, notes, personal difficulty, progress, offline use, and private Google-account sync.

## Start on PC or phone

Open **[the trainer](https://teovisnovsky.github.io/sat/)** and choose **Account → Sign in with Google** on each device. Switch among the four banks from the compact header switcher. Each bank keeps its own questions, attempts, notes, ratings, tags and progress. Use the same Google account for your own devices. Answers, notes, difficulty ratings and question banks save locally first and sync when the app is open and connected. The header shows **Synced**, **Changes waiting**, or an offline/retry status; click it to retry and open **Account** for details.

On PC, bookmark the site, use the browser's install option, or double-click **Start SAT Web.url** from the download. You no longer need to keep a local server running. The original Python service remains available below as a separate offline option.

**Moving existing progress:** in the old PC service, click **Export**. Sign in on the website, then use **Databases → Import / merge → Merge into this database**. For progress already saved in the website without an account, sign in and use **Account → Copy device-only progress**. Guest history is never silently assigned to another person's account.

Sync does not need both devices online at once. Open the first device online until it says **Synced**, then open the second device online. Offline edits upload next time that device connects with the app open. Keep occasional Export backups. The merge rules below also apply to cloud sync.

## Install for offline practice

1. Open **[SAT English](https://teovisnovsky.github.io/sat/)** on your phone while connected to the internet.
2. **iPhone:** use Safari → Share → **Add to Home Screen**. **Android:** use Chrome → menu → **Install app / Add to Home screen**. There is also an install/help button inside **Databases**.
3. Open the app from its home-screen icon while still connected. In **Databases**, wait for **Ready offline · saved on this device**.
4. You can now turn on airplane mode, close and reopen the app, and practice. Your PC can be switched off.

The phone downloads all four banks, including the optimized Maturita source crops needed for formulas, diagrams, tables, poetry and underlined text. It saves your banks, attempts, notes, tags and ratings on the phone. When signed in, your study data also syncs to your private account in Supabase. Without sign-in it stays on that device. There is no running Python service on the phone.

Use the same installed app each time. A different browser, website address or home-screen installation can have separate storage. Keep **Export** backups in Files/Downloads: clearing browser data, removing the app, or the phone reclaiming storage can remove local data. Opening **Install / offline help** requests persistent storage where supported, but exports remain the reliable backup.

## Optional manual transfer between devices

1. On the device you studied on, choose the database and click **Export**.
2. Move the downloaded `sat-YYYY-MM-DD.satbank.json` file to the other device using a cable, AirDrop, Quick Share, or your usual file-transfer method. On a phone, save it to Files/Downloads first if necessary.
3. On the other device, select the destination database, open **Databases → Import / merge**, and choose that file.
4. Choose **Merge into this database** to combine them, or **Add as separate database** to keep an independent copy.
5. To bring both devices up to date, export the merged bank and merge it back into the first device.

Neither device needs to run at the same time. Import/export and practice work offline; whether transferring the file needs a network depends on your chosen method.

Merge behavior:

- Questions are matched by stable question ID; missing questions are added.
- Every attempt has its own ID. Reimporting a file does not duplicate attempts or increase completion.
- The latest difficulty rating and review setting win. Keep device clocks correct; an ID breaks exact timestamp ties consistently.
- Notes keep revision history. If you edited the same note independently, both versions appear in the notes editor, separated by **Other device’s note**. Edit and save the combined note to resolve it; importing an old copy later will not undo that resolution. Notes still stay hidden until Check or Show notes.
- Personal tags are combined. A tag removed on one device can return if an older transfer still contains it.
- If the same question ID has different wording, choices, metadata or answer content, the **whole merge is rejected without changing the bank**. Add it separately to compare the versions.

Use **Merge** for your own devices. Use **Add as separate database** when you want a separate practice history, such as a friend's bank. Transfers include notes and their previous revisions as well as all attempts.

## Optional local Python service

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

- Filter SAT questions by category, skill, official difficulty, progress, personal difficulty, or tag. Search by question ID or passage text. Estimated official difficulty is deliberately absent from both Maturita banks.
- Maturita banks add year, answer-format and passage-use filters. Slovak also has eight section filters, one for each official block of eight questions. Slovak questions remain grouped by passage and official order by default, but category filters may select only matching questions; you can also practise only passage-free questions or shuffle every match.
- **Timers → Start a full test** selects one official year in its original order. Maturita SJL uses 100 minutes for 64 questions; Maturita Math uses 150 minutes for 30 questions. During a full test, answers are only marked as answered/not answered and no grading is revealed. **Submit test** saves and grades the answers together, then opens review mode with the correct answers.
- Multiple-choice questions: select A, B, C, or D. You can change your selection freely; the A-D keys also work.
- Maturita Math choice questions use A–E. Slovak short answers are checked against accepted forms from the official rubric; if a spelling-tolerant official answer is rejected too strictly, use **My answer should count as correct**.
- Math student-produced responses: type a number, decimal, or fraction and press Enter or **Check**. Equivalent forms are accepted, so `18/11`, `36/22` and `1.636` all count for the same answer. Only digits, a sign, one decimal point, or one fraction bar are accepted.
- Optionally tick **I am unsure / guessing**, then click **Check**. Only Check records an attempt and reveals the answer.
- The header stopwatch times each question. The bar fills toward your pace target and the figure beside it counts down to that target, then turns red and counts up once you pass it. Press the stopwatch to pause it if you have to step away; it also pauses by itself when you switch tabs, and a reload keeps it running. While it is paused, press the figure beside the time to start the question again from 0:00. Each answer saves its own time, so a second attempt at the same question is timed separately.
- **Timers** sets the pace target to any number of minutes for any number of questions; that one figure drives both the bar and the countdown. It starts at a full section for the open bank — English 64 min for 54 questions (1:11 each), Math 70 min for 44 questions (1:35 each). The set timer runs across questions, counting up or counting down against the target for an exam-style run, and reports elapsed time, questions answered and average pace.
- Rate **How did this feel?** as Easy, Medium, or Hard. **My difficulty** filters use your latest rating, independently of the official difficulty.
- Notes stay hidden when you open a question. Check an answer to reveal them, or choose **Show notes without answering** to review without recording an attempt. Notes autosave; **Save now** saves immediately.
- Enter personal tags separated by commas, then click **Save tags**.
- Wrong and guessed answers enter review. A confident correct retry removes a question from review; you can also mark questions manually.
- **Progress** shows unique questions completed, first-attempt accuracy, and your average time per question overall and per skill. Retrying never inflates completion or erases earlier attempts.

Maturita feedback shows only the broad category, skill and (for Slovak) section. Detailed source labels, estimated difficulty and method-like tags are omitted so they cannot hint at a solution or clutter review.

The web app saves on each device and syncs to the signed-in account. Each friend has independent progress. The optional Python service saves only to its local SQLite database; it does not participate in cloud sync.

## Databases and starting fresh

Open the **Databases** menu in the header to switch among the four built-in banks, **Export this database**, or **Import / merge** another one.

- `sat-clean.db`, `sat-math-clean.db`, `maturita-slovak-clean.db`, and `maturita-math-clean.db`: clean templates with no attempts, notes, review flags, personal tags, or personal difficulty ratings.
- `sat.db`, `sat-math.db`, `maturita-slovak.db`, and `maturita-math.db`: working banks created automatically on first launch.
- `databases/`: your imported working banks.

To start a separate fresh run on PC, import `sat-clean.db` and choose **Add as separate database**. For either device, the download also contains `docs/seed.json` and `docs/math-seed.json`, clean portable banks with the same 753 English and 536 Math questions. Import either file as a separate database. Your existing history stays in its original bank; the template stays clean.

Both versions accept **SAT transfer files** (`.satbank.json` / `.json`) up to 50 MB. The PC also accepts compatible **SAT Trainer SQLite files** (`.db`, `.sqlite`, `.sqlite3`), including older backups, with either add or merge. To move an old `.db` onto your phone, first import it on the PC and use **Export**. Arbitrary SQLite files and PDFs cannot be uploaded through this control. Optional original PDF image previews remain available in the original PC bank; portable banks include text and inline charts.

## Back up, restore, and update

Click **Export** to download a portable backup of the selected bank. On PC, **Databases → SQLite backup (PC)** also downloads the complete SQLite database. Import either backup on PC, or a portable backup on the phone. Use **Add as separate database** to restore a separate copy or **Merge** to combine it with current progress.

Before installing an update, back up your data. Download the new version to a separate folder, stop the old server, start the new version, and import your backup. Do not replace your working database with the clean template.

On the phone, opening the app while connected checks for app updates. If one is ready, **Databases → Update app** reloads the new version after saving pending notes. Your IndexedDB banks are preserved. New releases do not automatically replace your question bank; use import/merge to add new questions.

If using Git, working databases, imported banks, logs, and temporary files are ignored, keeping your personal study data out of commits.

## Troubleshooting

- **Python not found:** install Python, reopen the terminal, and try `py --version` (Windows) or `python3 --version` (macOS/Linux).
- **Browser cannot connect:** start the app first, then open http://127.0.0.1:8765. Running from a terminal shows errors; the Windows launcher also writes `server-error.log`.
- **Port already in use:** the trainer may already be running. Open its existing URL, or use `python server.py --port 8767 --open` (substitute `py` or `python3` as appropriate).
- **After restarting your computer:** run the launcher or terminal command again. Saved progress remains.
- **Old version still appears:** stop the old server before starting your updated folder. If you used the hidden Windows launcher and cannot identify the process, restarting your computer stops it.
- **Import rejected:** use an app transfer/backup. Phones require the portable JSON format; convert old `.db` files using Export on PC. A content-conflict message means you should add the file separately to inspect it.
- **Phone will not open offline:** open the installed app while connected and wait for Ready offline inside Databases. Installing from a `file://` URL or an ordinary HTTP address on your PC's Wi-Fi network does not provide the HTTPS setup required on phones.
- **Cannot find phone export:** check the browser's Downloads and the Files app. Keep the `.json` extension, then select the file through Import / merge.

## Question data

### English

The English bank has 753 unique Reading & Writing questions across four domains and ten skills. PDF exports omitted the instruction lines; these were recovered from College Board's API by matching all four choices (including punctuation), checking the passage and correct answer, and retaining both export IDs and official references. All 753 matched with no unresolved conflicts.

Questions, prompts, choices, explanations, and inline charts are in the database. Original PDF passage previews are in `assets/`. No personal study history is distributed.

### Math

The Math bank has 536 questions from `sat-math-answers-emh-part-*.pdf` across four domains and nineteen skills: Algebra (168), Advanced Math (132), Problem-Solving and Data Analysis (87), and Geometry and Trigonometry (149). 383 are multiple choice and 153 are student-produced responses whose accepted numeric forms are stored alongside the question.

Formulas are stored as MathML and graphs as inline SVG, so both scale with the page and stay searchable and readable offline — no images are needed. Tables keep their real table markup. `<mfenced>` was removed from browsers' MathML, so the importer rewrites it to `<mrow><mo>(</mo>…<mo>)</mo></mrow>`; without that, brackets silently disappear from over half the bank.

Question content belongs to College Board. This is an unofficial practice tool, not affiliated with or endorsed by College Board.

### Slovak Maturita

One canonical test form is included for each available year from 2008 through 2026: 2008–2019 and 2022–2026. The written/external exams are absent for 2020 and 2021. For the exceptional 2008 A/B papers, level A is used. Parallel shuffled test codes are not duplicated.

The SJL bank contains 17 tests, 1,088 questions and 136 shared passage sections: 680 A–D questions and 408 short answers. Its visible Slovak taxonomy uses three broad categories — **Porozumenie a interpretácia textu**, **Jazyk**, and **Literatúra** — and four shared skill groups. Each test is additionally filterable as eight official sections of eight questions.

The Maturita Math bank contains 17 tests and 510 questions: 340 numeric responses and 170 A–E questions. It uses four broad categories and four general skill groups; method-level tags that could reveal a solution are not shown before submission.

Source PDFs stay under `sources/maturita/` and are ignored by Git. `scripts/download_maturita_archive.py` recreates the local archive, and `scripts/import_maturita.py` reproducibly rebuilds the two clean banks and optimized WebP source crops. Before publicly redistributing the derived banks, confirm that the archive publisher's consent and reuse terms cover that distribution.

## Development

Python 3.10+ standard library, SQLite, and plain HTML/CSS/JavaScript. The web app uses IndexedDB, a service worker, and a locally bundled Supabase JavaScript SDK. See [Supabase setup](supabase/README.md) for Google login, redirect URLs, access rules and verification. `schema.sql` documents the PC database; [TRANSFER_FORMAT.md](TRANSFER_FORMAT.md) documents the portable format and future sync boundary.

```sh
python server.py --open
python test_service.py
python test_transfer.py
npm ci --ignore-scripts
npm test
python build_phone.py
```

Tests use disposable copies and leave your study history untouched. Node 22+ is needed for development tests and refreshing the vendored SDK (`npm run vendor`), not to use the app. The SDK is included in the repository so Python alone can rebuild the website.

`build_phone.py` generates `docs/` from `web/` and the four clean banks only, and refuses to build if any template contains personal progress. It also copies and precaches the Maturita WebP source crops. Commit the generated files after changing the shared UI. GitHub Pages serves **main → /docs**. You can also serve that directory from another HTTPS static host. Preview it locally at `http://127.0.0.1:8765/phone/`; this preview has separate browser storage from the PC database and the public phone URL.

### Optional PDF rebuild

Rebuilding needs PyMuPDF and your answer PDFs in the project folder, named `sat-rw-answers-*.pdf` for English and `sat-math-answers-*.pdf` for Math:

```sh
python -m pip install -r requirements.txt
python import_pdfs.py
python recover_prompts.py
python import_math.py
python scripts/download_maturita_archive.py
python scripts/import_maturita.py
```

Run both steps. Recovery needs internet unless official responses are cached in `source-cache/`. Source PDFs and that cache are not required for practice and are not distributed in this repository. Reimporting preserves attempts, notes, tags, and ratings. Import reports contain the validation results.

The Python service binds only to `127.0.0.1`. The website syncs each device independently through Supabase using stable record IDs, note revision ancestry and version-checked writes. Keep the Supabase SQL and authentication configuration in place when hosting your own copy.
