"""
BPM detection script for Copper Creek setlist songs.
Uses librosa beat tracking on G:\Muzic audio files.
Run with: C:\G\python.exe f:\❤Music\catalog\setlists\detect_bpm.py
"""
import os
import json
import re
import librosa
import numpy as np

MUZIC_DIR = r"G:\Muzic"

# Setlist with search keywords -> song identity
SETLIST = [
    {"id": 1, "set": 1, "order": 1,  "title": "Long Train Runnin",            "artist": "The Doobie Brothers",            "key": "Gm",  "search": "Long Train"},
    {"id": 2, "set": 1, "order": 2,  "title": "Too Much Time on My Hands",    "artist": "Styx",                           "key": "A",   "search": "Too Much Time"},
    {"id": 3, "set": 1, "order": 3,  "title": "I'm Alright",                  "artist": "Kenny Loggins",                  "key": "D",   "search": "Im Alright"},
    {"id": 4, "set": 1, "order": 4,  "title": "Me and Bobby McGee",           "artist": "Janis Joplin",                   "key": "G",   "search": "Bobby McGee"},
    {"id": 5, "set": 1, "order": 5,  "title": "Rhiannon",                     "artist": "Fleetwood Mac",                  "key": "Am",  "search": "Rhiannon"},
    {"id": 6, "set": 1, "order": 6,  "title": "Gold on the Ceiling",          "artist": "The Black Keys",                 "key": "G",   "search": "Gold on the Ceiling"},
    {"id": 7, "set": 1, "order": 7,  "title": "Call Me",                      "artist": "Blondie",                        "key": "B",   "search": "Call Me - Blondie"},
    {"id": 8, "set": 1, "order": 8,  "title": "Shaded Jade",                  "artist": "Tamala Cameron & Gene Ngo",      "key": "Bm",  "search": "Shaded Jade"},
    {"id": 9, "set": 1, "order": 9,  "title": "Reelin' in the Years",         "artist": "Steely Dan",                     "key": "A",   "search": "Reelin"},
    {"id": 10,"set": 1, "order": 10, "title": "I Will Survive",               "artist": "Gloria Gaynor",                  "key": "Am",  "search": "I Will Survive"},
    {"id": 11,"set": 1, "order": 11, "title": "Love Sneakin' Up on You",      "artist": "Bonnie Raitt",                   "key": "D",   "search": "Love Sneak"},
    {"id": 12,"set": 1, "order": 12, "title": "These Boots Are Made for Walkin'", "artist": "Nancy Sinatra",              "key": "E",   "search": "Boots"},
    {"id": 13,"set": 1, "order": 13, "title": "I Can't Go for That",          "artist": "Hall & Oates",                   "key": "F",   "search": "Can't Go"},
    {"id": 14,"set": 2, "order": 1,  "title": "25 or 6 to 4",                 "artist": "Chicago",                        "key": "A",   "search": "25 or 6"},
    {"id": 15,"set": 2, "order": 2,  "title": "What You Need",                "artist": "INXS",                           "key": "F#",  "search": "What You Need"},
    {"id": 16,"set": 2, "order": 3,  "title": "Do It Again",                  "artist": "Steely Dan",                     "key": "Gm",  "search": "Do It Again"},
    {"id": 17,"set": 2, "order": 4,  "title": "Baker Street",                 "artist": "Gerry Rafferty",                 "key": "D",   "search": "Baker Street"},
    {"id": 18,"set": 2, "order": 5,  "title": "Celebrate",                    "artist": "Kool & the Gang",                "key": "Ab",  "search": "Celebration"},
    {"id": 19,"set": 2, "order": 6,  "title": "Disco Inferno",                "artist": "Tina Turner",                    "key": "Ab",  "search": "Disco Inferno"},
    {"id": 20,"set": 2, "order": 7,  "title": "Black Magic Woman",            "artist": "Santana",                        "key": "Dm",  "search": "Black Magic Woman"},
    {"id": 21,"set": 2, "order": 8,  "title": "The Logical Song",             "artist": "Supertramp",                     "key": "C",   "search": "Logical Song"},
    {"id": 22,"set": 2, "order": 9,  "title": "Jacky",                        "artist": "Jim Mann",                       "key": "Gm",  "search": "Jacky"},
    {"id": 23,"set": 2, "order": 10, "title": "Carnival",                     "artist": "Natalie Merchant",               "key": "F#m", "search": "Carnival - Natalie"},
    {"id": 24,"set": 2, "order": 11, "title": "I Feel the Earth Move",        "artist": "Carole King",                    "key": "Cm",  "search": "Earth Move"},
    {"id": 25,"set": 2, "order": 12, "title": "Heart of Rock & Roll",         "artist": "Huey Lewis and the News",        "key": "C",   "search": "Heart of Rock"},
    {"id": 26,"set": 2, "order": 13, "title": "Heavy Chevy",                  "artist": "Alabama Shakes",                 "key": "C",   "search": "Heavy Chevy"},
    {"id": 27,"set": 3, "order": 1,  "title": "Pick Up the Pieces",           "artist": "Average White Band",             "key": "Fm",  "search": "Pick Up the Pieces"},
    {"id": 28,"set": 3, "order": 2,  "title": "Play That Funky Music",        "artist": "Wild Cherry",                    "key": "Em",  "search": "Funky Music"},
    {"id": 29,"set": 3, "order": 3,  "title": "On the Dark Side",             "artist": "John Cafferty",                  "key": "E",   "search": "Dark Side"},
    {"id": 30,"set": 3, "order": 4,  "title": "What I Like About You",        "artist": "The Romantics",                  "key": "E",   "search": "What I Like About"},
    {"id": 31,"set": 3, "order": 5,  "title": "Smooth Operator",              "artist": "Sade",                           "key": "Dm",  "search": "Smooth Operator"},
    {"id": 32,"set": 3, "order": 6,  "title": "Smooth",                       "artist": "Santana feat. Rob Thomas",       "key": "Am",  "search": "Smooth - Santana"},
    {"id": 33,"set": 3, "order": 7,  "title": "What I Do",                    "artist": "Tyler James Drake",              "key": "Bm",  "search": "What I Do"},
    {"id": 34,"set": 3, "order": 8,  "title": "Stop Draggin' My Heart Around","artist": "Stevie Nicks",                   "key": "Em",  "search": "Stop Draggin"},
    {"id": 35,"set": 3, "order": 9,  "title": "The Letter",                   "artist": "Joe Cocker",                     "key": "Bbm", "search": "The Letter"},
    {"id": 36,"set": 3, "order": 10, "title": "Blue on Black",                "artist": "Kenny Wayne Shepherd",           "key": "C",   "search": "Blue on Black"},
    {"id": 37,"set": 3, "order": 11, "title": "Evil Ways",                    "artist": "Santana",                        "key": "Gm",  "search": "Evil Ways"},
    {"id": 38,"set": 3, "order": 12, "title": "Peg",                          "artist": "Steely Dan",                     "key": "G",   "search": "Peg - Steely"},
    {"id": 39,"set": 3, "order": 13, "title": "Roll with the Changes",        "artist": "REO Speedwagon",                 "key": "C",   "search": "Roll With"},
]

# Gather all audio files from G:\Muzic (top level only - no subfolders for originals)
audio_exts = {".mp3", ".wav", ".m4a", ".flac"}
muzic_files = []
for f in os.listdir(MUZIC_DIR):
    ext = os.path.splitext(f)[1].lower()
    if ext in audio_exts:
        muzic_files.append(f)

print(f"Found {len(muzic_files)} audio files in G:\\Muzic")

def find_match(search_term: str, files: list) -> str | None:
    """Find best matching audio file (prefer original, not transposed)."""
    term_lower = search_term.lower()
    candidates = [f for f in files if term_lower in f.lower()]
    if not candidates:
        return None
    # Prefer files without step-shift markers (no "+N" or "-N steps")
    originals = [f for f in candidates if not re.search(r'[+-]\d+ step', f, re.I)]
    return originals[0] if originals else candidates[0]

def detect_bpm(filepath: str) -> int | None:
    try:
        y, sr = librosa.load(filepath, sr=None, mono=True, duration=90)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(round(float(np.atleast_1d(tempo)[0])))
        return bpm
    except Exception as e:
        print(f"  ERROR on {os.path.basename(filepath)}: {e}")
        return None

results = []
for song in SETLIST:
    match = find_match(song["search"], muzic_files)
    bpm = None
    source_file = None
    if match:
        full_path = os.path.join(MUZIC_DIR, match)
        print(f"  [{song['id']:2d}] {song['title'][:35]:35s} -> {match[:50]}")
        bpm = detect_bpm(full_path)
        source_file = match
        print(f"       BPM: {bpm}")
    else:
        print(f"  [{song['id']:2d}] {song['title'][:35]:35s} -> NO MATCH")

    results.append({**song, "bpm": bpm, "bpm_source_file": source_file})

# Write output JSON
out_path = os.path.join(os.path.dirname(__file__), "setlist_with_bpm.json")
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(results, fh, indent=2, ensure_ascii=False)

print(f"\nDone. Results written to {out_path}")
detected = sum(1 for r in results if r["bpm"] is not None)
print(f"BPM detected: {detected}/{len(results)}")
