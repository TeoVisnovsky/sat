# SAT bank transfer v1

The UTF-8 JSON envelope has `format: "sat-bank"`, `version: 1`, a `bank` object (`id`, `name`), and six arrays. Exports are complete snapshots, not deltas. Unsupported versions are rejected.

| Array | Record fields |
| --- | --- |
| `questions` | `id`, `domain`, `skill`, `difficulty`, `passage_html`, `prompt_html`, `correct_answer`, `explanation_html`, `choices` (`letter`, `content_html`), `sources` (`filename`, `file_sha256`, `page_start`, `page_end`) |
| `attempts` | globally unique `id`, `question_id`, `selected_answer`, `is_correct` (0/1), `guessed` (0/1), `elapsed_ms` (integer milliseconds or `null`), `answered_at` |
| `notes` | globally unique `id`, `question_id`, `content`, `updated_at`, `parents` (superseded note revision IDs) |
| `ratings` | `id`, `question_id`, `rating` (easy/medium/hard), `updated_at` |
| `reviews` | `id`, `question_id`, `needs_review` (0/1), `updated_at` |
| `tags` | `question_id`, `name` |

New event IDs are UUIDs. Timestamps are UTC ISO 8601 with millisecond precision. Question IDs are stable within a bank; adding a separate bank creates a new bank ID but retains its question/history IDs so copies can subsequently be merged.

Python stores the original relational tables plus `attempt_ids`, `note_versions`, `state_versions`, and `transfer_meta`. Older banks are upgraded without deleting any questions or progress. Legacy attempts get deterministic IDs based on the original row, including its local ID and timestamp, so identical old backups can be deduplicated. Legacy records independently reconstructed with changed IDs/timestamps cannot be reliably recognized as identical. New UUID records do not have that ambiguity.

Phone storage is IndexedDB `sat-offline-v1`, object store `banks`. Each bank snapshot is saved in one transaction, including all state produced by Check. Read/write transactions serialize edits from multiple tabs. The service worker caches application files and the clean initial bank, never personal progress.

## Merge contract

Question fields are compared exactly; sources are combined. Any differing existing question or same-ID immutable history record aborts the entire import. The incoming file can instead be added independently. The merge never silently chooses an answer key.

Attempts and note revisions are unioned by ID. Note parents must exist in the same question's revision graph, which must be acyclic. Current notes are the graph leaves; equal leaf text is displayed once. Concurrent different leaves are displayed together, retaining every revision. Saving that combined editor creates a revision whose parents are all current leaves, resolving them. Reimporting ancestors cannot resurrect resolved text.

Ratings and review state use maximum `(updated_at, id)` per question. Attempt ordering is chronological with a stable ID tie-breaker; first-attempt accuracy refers to the earliest known attempt, including older history imported later. Tags use case-insensitive union; tag deletions have no tombstones in v1.

`elapsed_ms` is how long the question was open, excluding time paused or spent in another tab. It is additive metadata rather than history: a file written before timing existed simply omits it, validation normalises that to `null`, and merging fills a `null` from the other side instead of reporting a conflict. It never takes part in identity comparison.

Merge does not remove questions or attempts. There is no automatic relationship between two independently added banks; the user chooses the destination. Device clocks must be reasonably correct for timestamps to reflect edit order.

## Future online sync

The UI calls a storage adapter (`api` / `SATOffline.request`). File import/export is the transport today. A future authenticated backend can accept the same versioned snapshot, apply the same merge contract, and return the merged result. Each device can push/pull at different times; neither needs to connect to the other.

Accounts, server authorization, conflict review for differing question versions, delta cursors, deletion tombstones, and a Sync button are future work. Do not add cloud uploads to the service worker or alter the v1 merge semantics silently. Breaking format changes require a new version and migration. Cross-runtime tests compare the Python and JavaScript merge results.

Only the clean seed is published. Raw SQLite backups additionally retain PC-specific provenance and original PDF asset paths; portable files contain the content necessary for practice plus PDF source references, not the optional original image files or all SQLite administration fields.
