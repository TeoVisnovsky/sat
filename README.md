# SAT English Trainer

A minimal SAT Reading & Writing practice app with **753 questions**, answers and explanations, charts, and saved progress. Use the local Python service on your PC or install the offline web app on your phone. No account, Codex installation, API key, or paid service is needed.

## Practice on your phone

1. Open **[SAT English](https://teovisnovsky.github.io/sat/)** on your phone while connected to the internet.
2. **iPhone:** use Safari → Share → **Add to Home Screen**. **Android:** use Chrome → menu → **Install app / Add to Home screen**. There is also an install/help button inside **Databases**.
3. Open the app from its home-screen icon while still connected. In **Databases**, wait for **Ready offline · saved on this device**.
4. You can now turn on airplane mode, close and reopen the app, and practice. Your PC can be switched off.

The phone downloads all question text, answers, explanations and inline charts. It saves your banks, attempts, notes, tags and ratings on the phone. The website supplies installation files and updates; your study data is never uploaded to it. There is no running Python service or account on the phone.

Use the same installed app each time. A different browser, website address or home-screen installation can have separate storage. Keep **Export** backups in Files/Downloads: clearing browser data, removing the app, or the phone reclaiming storage can remove local data. Opening **Install / offline help** requests persistent storage where supported, but exports remain the reliable backup.

## Transfer between phone and PC

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

Open the compact **Databases** menu in the header to switch banks or **Import / merge**.

- `sat-clean.db`: the included template with all 753 questions and no attempts, notes, review flags, personal tags, or difficulty ratings.
- `sat.db`: your original working bank, created automatically on first launch.
- `databases/`: your imported working banks.

To start a separate fresh run on PC, import `sat-clean.db` and choose **Add as separate database**. For either device, the download also contains `docs/seed.json`, a clean portable bank with the same 753 questions. Import that file as a separate database. Your existing history stays in its original bank; the template stays clean.

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

The included bank has 753 unique Reading & Writing questions across four domains and ten skills. PDF exports omitted the instruction lines; these were recovered from College Board's API by matching all four choices (including punctuation), checking the passage and correct answer, and retaining both export IDs and official references. All 753 matched with no unresolved conflicts.

Questions, prompts, choices, explanations, and inline charts are in the database. Original PDF passage previews are in `assets/`. No personal study history is distributed.

Question content belongs to College Board. This is an unofficial practice tool, not affiliated with or endorsed by College Board.

## Development

Python 3.10+ standard library, SQLite, and plain HTML/CSS/JavaScript. The phone uses IndexedDB and a service worker. `schema.sql` documents the PC database; [TRANSFER_FORMAT.md](TRANSFER_FORMAT.md) documents the portable format and future sync boundary.

```sh
python server.py --open
python test_service.py
python test_transfer.py
node test_bank_core.js
python build_phone.py
```

Tests use disposable copies and leave your study history untouched. Node 20+ is needed only for JavaScript and cross-runtime tests, not to use or build the app.

`build_phone.py` generates `docs/` from `web/` and **sat-clean.db only**, and refuses to build if that template contains personal progress. Commit the generated files after changing the shared UI. GitHub Pages serves **main → /docs**. You can also serve that directory from another HTTPS static host. Preview it locally at `http://127.0.0.1:8765/phone/`; this preview has separate browser storage from the PC database and the public phone URL.

### Optional PDF rebuild

Rebuilding needs PyMuPDF and your answer PDFs in the project folder, named `sat-rw-answers-*.pdf`:

```sh
python -m pip install -r requirements.txt
python import_pdfs.py
python recover_prompts.py
```

Run both steps. Recovery needs internet unless official responses are cached in `source-cache/`. Source PDFs and that cache are not required for practice and are not distributed in this repository. Reimporting preserves attempts, notes, tags, and ratings. Import reports contain the validation results.

The Python service binds only to `127.0.0.1`. Manual file transfer is implemented; online sync is deferred. Stable record IDs, UTC timestamps and note revision ancestry allow a future backend to merge snapshots while each device syncs independently.
