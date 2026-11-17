# Study bank transfer v2

The UTF-8 JSON envelope retains `format: "sat-bank"` for backward compatibility, uses `version: 2`, and has a `bank` object (`id`, `name`) plus the arrays below. Exports are complete snapshots, not deltas. Version 1 imports remain supported and receive empty exam metadata and test history.

| Array | Record fields |
| --- | --- |
| `exams` | `id`, `subject`, `year`, `canonical_code`, `level`, `duration_minutes`, `source_url` |
| `stimuli` | shared passage `id`, `exam_id`, `ordinal`, `title`, `content_html`, `stimulus_type`, source pages |
| `questions` | original fields plus `answer_type` (`choice`, `numeric`, `text`), `accepted_answers`, `exam_id`, `year`, `ordinal`, `stimulus_id`, `subcategory`, `knowledge_source`, `requires_stimulus`, `answer_notes`; choices may be A-D or A-E |
| `attempts` | globally unique `id`, `question_id`, `selected_answer`, `is_correct` (0/1), `guessed` (0/1), `elapsed_ms` (integer milliseconds or `null`), `answered_at` |
| `notes` | globally unique `id`, `question_id`, `content`, `updated_at`, `parents` (superseded note revision IDs) |
| `ratings` | `id`, `question_id`, `rating` (easy/medium/hard), `updated_at` |
| `reviews` | `id`, `question_id`, `needs_review` (0/1), `updated_at` |
| `tags` | `question_id`, `name` |
| `test_sessions` | globally unique `id`, year/timing metadata, total/answered/score, and the submitted answer/result records |

New event IDs are UUIDs. Timestamps are UTC ISO 8601 with millisecond precision. Question IDs are stable within a bank; adding a separate bank creates a new bank ID but retains its question/history IDs so copies can subsequently be merged.

Python stores the original relational tables plus `attempt_ids`, `note_versions`, `state_versions`, and `transfer_meta`. Older banks are upgraded without deleting any questions or progress. Legacy attempts get deterministic IDs based on the original row, including its local ID and timestamp, so identical old backups can be deduplicated. Legacy records independently reconstructed with changed IDs/timestamps cannot be reliably recognized as identical. New UUID records do not have that ambiguity.

Phone storage is IndexedDB `sat-offline-v1`, object store `banks`. Each bank snapshot is saved in one transaction, including all state produced by Check and atomic full-test submission. Read/write transactions serialize edits from multiple tabs. The service worker caches the application shell immediately, loads each clean bank on first use, and downloads source-faithful Maturita crops when the user requests that bank's offline pack. It never caches personal progress.

## Merge contract

Question fields are compared exactly; sources are combined. Any differing existing question or same-ID immutable history record aborts the entire import. The incoming file can instead be added independently. The merge never silently chooses an answer key.

Attempts, full-test sessions and note revisions are unioned by ID. A conflicting same-ID full-test session rejects the merge. Note parents must exist in the same question's revision graph, which must be acyclic. Current notes are the graph leaves; equal leaf text is displayed once. Concurrent different leaves are displayed together, retaining every revision. Saving that combined editor creates a revision whose parents are all current leaves, resolving them. Reimporting ancestors cannot resurrect resolved text.

Ratings and review state use maximum `(updated_at, id)` per question. Attempt ordering is chronological with a stable ID tie-breaker; first-attempt accuracy refers to the earliest known attempt, including older history imported later. Tags use case-insensitive union; tag deletions have no tombstones in v1.

`elapsed_ms` is how long the question was open, excluding time paused or spent in another tab. It is additive metadata rather than history: a file written before timing existed simply omits it, validation normalises that to `null`, and merging fills a `null` from the other side instead of reporting a conflict. It never takes part in identity comparison.

Merge does not remove questions or attempts. There is no automatic relationship between two independently added banks; the user chooses the destination. Device clocks must be reasonably correct for timestamps to reflect edit order.

## Online sync

The UI calls a storage adapter (`api` / `SATOffline.request`). File import/export and the authenticated Supabase backend use the same versioned snapshots and merge contract. Each device can push/pull at different times; neither needs to connect to the other.

Supabase row-level security keeps each account's banks private. Differing question versions are rejected atomically. Tag-deletion tombstones and fine-grained deltas remain future work. Breaking changes require another version and migration. Cross-runtime tests compare the Python and JavaScript merge results.

Only clean seeds are suitable for publishing. Raw SQLite backups additionally retain PC-specific provenance. Portable question HTML references the published optimized Maturita crops; original PDFs remain local and excluded from Git.
