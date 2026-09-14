# Cloud setup

The published app uses Google sign-in and Supabase. Anyone with a Google account can join; each account can read and sync only its own banks. Practice without signing in remains device-only.

1. In Supabase **SQL Editor**, run all of [setup.sql](setup.sql). It is safe to rerun without clearing progress. It creates the table, row-level access policy, and version-checked write function.
2. In **Authentication → Providers → Google**, enable Google and enter the Google OAuth client ID and secret. Keep the secret in Supabase, never in the repository.
3. In the Google Cloud OAuth web client's **Authorized redirect URIs**, add `https://gqumovglktexqerwoidu.supabase.co/auth/v1/callback`.
4. In Supabase **Authentication → URL Configuration**, set **Site URL** to `https://teovisnovsky.github.io/sat/` and add that exact URL to **Redirect URLs**. For optional local PWA testing, also allow `http://127.0.0.1:8765/phone/`.
5. Enable new user signups in Supabase. In Google Cloud, use an External audience and publish the OAuth app to Production so friends are not limited to the testing user list. Google may require additional configuration shown in its console.
6. Open the published app, choose **Account → Sign in with Google**, and check that the header reaches **Synced**. On a second device, sign in to the same account and check that an answer or note from the first device appears after sync. Test a different account to confirm separate progress.

`web/cloud-config.js` contains the project URL and browser-safe publishable key. These are intentionally public. Never add a service-role key or Google client secret. Run `python build_phone.py` after changing configuration, then publish `docs/`.

## Storage and recovery

The installed app keeps a local IndexedDB copy for offline use. Sync runs after edits, when the app comes online or becomes visible, and periodically while open. The status button also retries manually. Closing the app before sync completes leaves changes on that device; open it online again to upload them.

The cloud stores separate banks per authenticated user. Writes use an expected revision; a competing write causes another pull and merge instead of overwriting unseen progress. Attempts deduplicate by ID, conflicting note revisions are retained, and difficulty/review values use timestamp ordering. Question-content conflicts stop that bank's sync and are shown in Account. Other banks can still sync. Deletions of tags do not propagate reliably through the union-based merge.

Guest banks remain separate. After signing in, **Account → Copy device-only progress** explicitly merges a guest bank into the selected account bank. The Python service's SQLite data needs a one-time **Export**, followed by **Import / merge** in the website. The Python service itself does not sync.

Keep exported backups, particularly before changing accounts or clearing browser storage. Signing out preserves local account data for later offline use after signing back into that account; it is not a device-data wipe.

## Verification

Run `npm ci --ignore-scripts` and `npm test`. Tests exercise the actual SQL in a disposable PostgreSQL runtime, account isolation in IndexedDB, concurrent merges, interrupted uploads, and note editing during sync. Real Google login and project redirect settings additionally need the signed-in browser check in step 6.
