# Lyrics Integration with Setlist Optimizer

**Status:** Planned — soak time  
**Requested:** 2026-04-17  
**Owner:** ❤music-production  
**Tyler's desire:** "We should have the lyrics handy" during setlist optimization / performance context

---

## Motivation

The current `setlist_optimizer.py` treats songs as purely numeric objects
(`energy`, `tempo_bpm`, `key`, `crowd_response`). It has no awareness of lyrical
content. Tyler wants lyrics surfaced alongside the optimized setlist so he can:

- Review verse/chorus flow between consecutive songs
- Spot thematic continuity or contrast opportunities across the set
- Have lyric cue cards ready for performance prep without a separate lookup step
- Eventually feed lyrical themes into the transition scoring model (Phase 3)

---

## Current State

```
tracks (id, title, key_signature, tempo_bpm, ...)
  └─ lyrics (track_id, version_label, content, file_path)
  └─ recordings (track_id, file_path, version_label, ...)

setlist_optimizer.py:
  Song(name, energy, tempo_bpm, key, crowd_response)  ← no lyrics field
  optimize_setlist() → list[Song]                     ← no lyric payload
```

The `lyrics` table already exists and has `content` (inline text) and
`file_path` (external file reference). The Bloom album lyrics files are
cataloged in `catalog_index` but not yet imported into `lyrics.content`.

---

## Implementation Plan

### Phase A — Data: Import Lyrics into DB (prerequisite)

**Task:** `tools/import_lyrics.py`

1. Query `catalog_index` for all rows with `category='lyrics'` or for
   files matching lyric extensions (`.txt`, `.docx`) in Bloom album folders
2. For each file, resolve which track it belongs to (match by folder name
   e.g. `Abbey's Song/Lyrics.txt` → track `Abbey's Song`)
3. Read file content (strip formatting for `.docx` using `python-docx`)
4. `INSERT OR IGNORE INTO lyrics (track_id, version_label, content, file_path)`
5. Prefer files named `Lyrics.txt` or `<track>.txt` over `V1.txt`, `Bridge.txt`
   (those are song section fragments — store separately as `version_label='section_v1'` etc.)

Known lyric files in `catalog_index` (from Bloom):
- `Abbey's Song/Lyrics.txt` → version_label=`'main'`
- `Abbey's Song/V1.txt`, `V2.txt`, `V3.txt`, `Bridge.txt`, `Chorus.txt` → section fragments
- `Bitten/Bitten Lyrics.txt`, `Bitten/Bitten.docx`
- `Fly Away/Fly Away Lyrics.txt`, `Fly Away.docx`, `Fly Away_Tyler James Drake_LyricsOnly.docx`
- `IsItReal/IsItReal.txt`
- `Lighthouse/Lighthouse_Tyler James Drake_Key_Em_Lyrics_Only.docx`
- `Same Thing/lyrics.txt`, `Same.rtf`, `Same.docx`, `Same.txt`
- `You Already Know/You Already Know - Rough 1-19-2026_...docx`

---

### Phase B — Model: Extend Song dataclass

```python
@dataclass
class Song:
    name: str
    energy: float
    tempo_bpm: int
    key: int
    crowd_response: float
    # NEW
    lyrics_snippet: str = ""    # first ~200 chars of main lyrics for display
    lyric_themes: list[str] = field(default_factory=list)  # extracted tags (optional, Phase C)
```

`lyrics_snippet` is display-only — it does NOT feed into the QAOA cost function
in Phase B. It rides along as metadata on the returned `Song` objects.

---

### Phase C — DB Loader: Populate Song from DB with lyrics

Extend `load_songs_from_db()` (or the equivalent loader function) with a
LEFT JOIN on `lyrics`:

```python
SELECT
    t.id,
    t.title,
    t.key_signature,
    t.tempo_bpm,
    l.content   AS lyrics_content,
    l.file_path AS lyrics_file
FROM tracks t
LEFT JOIN lyrics l ON l.track_id = t.id AND l.version_label = 'main'
WHERE t.album_id = ?
```

If `l.content` is NULL, fall back to reading from `l.file_path` (lazy load).
Truncate to first 200 chars for `lyrics_snippet`.

---

### Phase D — Output: Surface lyrics in results

Extend the `optimize_setlist()` return value or wrap it in a richer response:

```python
@dataclass
class SetlistResult:
    ordered_songs: list[Song]      # Song objects now carry lyrics_snippet
    cut_value: float
    raw_result: dict
    lyric_cue_cards: list[dict]    # [{position, title, snippet, file_path}]
```

The `lyric_cue_cards` list mirrors `ordered_songs` in order — Tyler gets a
ready-to-print or terminal-renderable cue card sheet for the optimized set.

CLI `--demo` flag should render:

```
  #1  Abbey's Song (E major, 124 BPM)
      ┌─ "She's the light at the end of the hall..."
  #2  Fly Away (C major, 110 BPM)
      ┌─ "I've been waiting on a broken wing..."
  ...
```

---

### Phase E (Future) — Lyric themes in transition scoring

Once lyrics are imported and tagged, add a lyric-theme compatibility
dimension to `transition_cost()`:

```python
# Theme continuity bonus: matching themes → lower cost
theme_overlap = len(set(song_a.lyric_themes) & set(song_b.lyric_themes))
theme_cost = 1.0 - min(theme_overlap / 3.0, 1.0)  # 3+ shared themes = perfect

# Add to weighted combination (replace or supplement energy_cost)
return 0.35 * key_cost + 0.25 * tempo_cost + 0.20 * energy_cost + 0.20 * theme_cost
```

Theme extraction options (in order of effort):
1. **Manual tags** — Tyler tags each song in the `lyrics` table with a `themes` column
2. **Keyword extraction** — simple word frequency on lyric content (no model needed)
3. **Embedding similarity** — sentence-transformers on lyric text (overkill for 7 songs, revisit at larger catalog)

---

## DB Schema Change Needed

```sql
-- Add themes column to lyrics table (Phase E only)
ALTER TABLE lyrics ADD COLUMN themes TEXT;  -- JSON array e.g. '["love","loss","freedom"]'
```

No schema change needed for Phase A–D.

---

## Files to Create/Modify

| File | Action | Phase |
|------|--------|-------|
| `tools/import_lyrics.py` | Create — bulk import from catalog_index | A |
| `src/integrations/setlist_optimizer.py` | Extend `Song` dataclass, loader, output | B–D |
| `tests/test_setlist_optimizer.py` | Add lyrics_snippet fixture tests | B–D |
| `src/utils/init_db.py` | ADD COLUMN lyrics.themes (migration) | E |

---

## Dependencies

- `python-docx` (for `.docx` lyric files) — `pip install python-docx`
- No new dependencies for Phase B–D
- Phase E: optionally `sentence-transformers` (deferred)

---

## Decisions (2026-04-17)

| Question | Answer |
|----------|--------|
| Lyric version to display | **Full lyrics** (complete `main` version, not just snippet) |
| Cue card output format | **HTML** — exportable file, renderable in browser for show night |
| Theme tagging | **Auto-extracted** — keyword frequency on lyric content (no manual tagging, no models) |

### HTML Cue Card Format

Output: `setlist_<date>.html` — self-contained single file, no external deps.

```html
<section class="song">
  <h2>#1 — Abbey's Song <span class="meta">E major · 124 BPM</span></h2>
  <div class="themes">themes: love · memory · family</div>
  <pre class="lyrics">She's the light at the end of the hall...\n...</pre>
  <div class="transition">▼ transition score: 0.18 (excellent)</div>
</section>
```

Styling: dark background, large readable font, printer-friendly CSS (`@media print`).

### Auto Theme Extraction

Algorithm (keyword frequency, no ML):
1. Lowercase + strip punctuation from full lyric content
2. Remove stopwords (`the`, `and`, `I`, `you`, `a`, etc.)
3. Score remaining words by TF across the track's lyrics
4. Map top words to theme buckets (e.g. `fly/free/away` → `freedom`; `love/heart/hold` → `love`)
5. Top 3 theme tags per song → stored in `lyrics.themes` JSON column

Theme bucket definitions live in `tools/import_lyrics.py` as a simple dict — Tyler can tune them.

---

*Plan locked. All decisions made. Implement starting with Phase A (`tools/import_lyrics.py`) when ready.*
