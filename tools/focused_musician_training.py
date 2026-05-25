import argparse
import pygame
from pydub import AudioSegment
import os
import json
import sys
import tempfile
from datetime import datetime
import numpy as np
import librosa
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# DB path / key (mirrors utils/init_db.py — direct sqlite3 since this script
# runs as a subprocess outside the Flask context)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _PROJECT_ROOT / "src" / "data" / "heartmusic.db"

# Module-level exercise id set by main() once we know which _run_<id>.json
# we are executing.  None = migrated / manual session (exercise_id IS NULL).
_exercise_id: int | None = None

def change_speed(sound, speed=1.0):
    """Change playback speed of the audio segment without affecting pitch."""
    # Get raw audio data as numpy array
    samples = np.array(sound.get_array_of_samples()).astype(np.float32)
    
    # Normalize to -1.0 to 1.0 range
    max_val = 2 ** (sound.sample_width * 8 - 1)
    samples = samples / max_val
    
    # For stereo, reshape and process each channel separately
    if sound.channels == 2:
        samples = samples.reshape((-1, 2)).T
        stretched_channels = []
        for channel in samples:
            stretched = librosa.effects.time_stretch(channel, rate=speed)
            stretched_channels.append(stretched)
        stretched = np.vstack(stretched_channels).T.flatten()
    else:
        stretched = librosa.effects.time_stretch(samples, rate=speed)
    
    # Convert back to original sample format
    stretched = (stretched * max_val).astype(np.int16)
    
    # Create new AudioSegment with stretched audio
    return sound._spawn(stretched.tobytes())

def parse_timecode(time_str):
    """Convert a timecode in the format MM:SS to seconds."""
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        elif len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        else:
            raise ValueError
    except ValueError:
        print(f"Invalid time format: '{time_str}'. Expected MM:SS or HH:MM:SS.")
        sys.exit(1)

def log_practice_session(log_path, song_path, segment):
    """Log the practice session to guitar_training_log in heartmusic.db."""
    seg_start = str(segment.get("start", ""))
    seg_end = str(segment.get("end", ""))
    repetition = int(segment.get("repetition", 1))
    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db_key = os.environ.get("HEARTMUSIC_DB_KEY", "")
    if not db_key:
        print("WARNING: HEARTMUSIC_DB_KEY not set — practice session not logged.")
        return

    try:
        import sqlcipher3  # noqa: PLC0415
        conn = sqlcipher3.connect(str(_DB_PATH))
        # hex-encoded key (matches init_db._try_open_with_key logic)
        key_hex = db_key.encode().hex()
        conn.execute(f"PRAGMA key=\"x'{key_hex}'\"")  # nosec B608
        conn.execute("PRAGMA cipher_page_size=4096")
        conn.execute("PRAGMA kdf_iter=256000")
        conn.execute("PRAGMA cipher_hmac_algorithm=HMAC_SHA512")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO guitar_training_log "
            "(exercise_id, song_path, seg_start, seg_end, repetition, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_exercise_id, song_path, seg_start, seg_end, repetition, logged_at),
        )
        conn.commit()
        conn.close()
        print(f"Logged practice session to heartmusic.db (exercise_id={_exercise_id}).")
    except Exception as exc:
        print(f"Failed to write practice log to DB: {exc}")

def loop_segment(file_path, start_time, end_time, repetition, speed_factor, log_path, *, manage_pygame=True):
    """Loop a section of the audio file a specified number of times and log the session."""
    if manage_pygame:
        pygame.mixer.init()
        pygame.init()
        pygame.display.set_mode((1, 1))  # Minimal display for event handling

    # Load the audio file with pydub
    file_extension = os.path.splitext(file_path)[1].lower()

    if file_extension in ['.mp3', '.m4a']:
        try:
            audio = AudioSegment.from_file(file_path)
        except Exception as e:
            print(f"Error loading audio file: {e}")
            return
    else:
        print("Unsupported file format. Please use .mp3 or .m4a")
        return

    # Calculate start and end times in milliseconds
    start_ms = start_time * 1000
    end_ms = end_time * 1000

    if start_ms >= len(audio):
        print(f"Start time {start_time}s exceeds audio length.")
        return
    if end_ms > len(audio):
        print(f"End time {end_time}s exceeds audio length. Adjusting to audio length.")
        end_ms = len(audio)

    # Extract the section to loop
    section = audio[start_ms:end_ms]

    if speed_factor != 1.0:
            section = change_speed(section, speed=speed_factor)
            print(f"Speed adjusted to {speed_factor * 100:.1f}%")


    # Export the extracted section to a temporary wav file for playback with pygame.mixer
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        section.export(temp_file.name, format="wav")
        temp_file_path = temp_file.name

    # Load the temporary file into pygame
    try:
        pygame.mixer.music.load(temp_file_path)
    except pygame.error as e:
        print(f"Error loading temporary audio file: {e}")
        os.remove(temp_file_path)
        return

    print(f"Playing segment {start_time}s - {end_time}s, {repetition} repetitions.")

    for i in range(repetition):
        print(f"Repetition {i+1}/{repetition}")
        pygame.mixer.music.play()
        # Wait until the music finishes playing
        while pygame.mixer.music.get_busy():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.mixer.music.stop()
                    pygame.quit()
                    os.remove(temp_file_path)
                    sys.exit()
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_t:
                        print("Playback interrupted by user.")
                        pygame.mixer.music.stop()
                        pygame.quit()
                        os.remove(temp_file_path)
                        sys.exit()
    print("Segment playback completed.")

    # Log the practice session
    segment_info = {
        "start": f"{int(start_time // 60)}:{int(start_time % 60):02}",
        "end": f"{int(end_time // 60)}:{int(end_time % 60):02}",
        "repetition": repetition
    }
    log_practice_session(log_path, file_path, segment_info)

    # Clean up
    pygame.mixer.music.stop()
    pygame.mixer.music.unload()
    if manage_pygame:
        pygame.quit()
    try:
        os.remove(temp_file_path)
    except OSError:
        pass

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Play sections of a song based on JSON configuration and log the sessions.")
    parser.add_argument("json_file", help="Name of the JSON file containing song path and segments.")
    args = parser.parse_args()

    # Define the default directory
    default_directory = os.path.join("tyJson", "exercises", "musicTraining")

    # Construct the full path to the JSON file
    json_file = args.json_file
    json_path = os.path.join(default_directory, json_file)

    # Parse exercise_id from filename pattern _run_<id>.json
    global _exercise_id
    import re as _re
    _m = _re.match(r"_run_(\d+)\.json$", os.path.basename(json_file))
    _exercise_id = int(_m.group(1)) if _m else None

    # Define the path to the training log (kept for compatibility; not written to)
    log_file = "trainingLog.json"
    log_path = os.path.join(default_directory, log_file)

    # Check if JSON file exists
    if not os.path.isfile(json_path):
        print(f"JSON file '{json_path}' does not exist.")
        sys.exit(1)

    # Load JSON data
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        sys.exit(1)

    # Extract songPath, segments, and gradient
    song_path = data.get("songPath")
    segments = data.get("segments", [])
    gradient = float(data.get("gradient", 0))

    if not song_path:
        print("JSON file missing 'songPath'.")
        sys.exit(1)

    if not segments:
        print("JSON file missing 'segments' or it's empty.")
        sys.exit(1)

    # Check if songPath exists
    if not os.path.isfile(song_path):
        print(f"Audio file '{song_path}' does not exist.")
        sys.exit(1)

    # Count total plays for gradient reporting
    total_plays = sum(max(0, seg.get("repetition", 1)) for seg in segments)
    play_index = 0

    # Init pygame once for the whole session
    pygame.mixer.init()
    pygame.init()
    pygame.display.set_mode((1, 1))

    # Loop through each segment
    for idx, segment in enumerate(segments, start=1):
        start_str = segment.get("start")
        end_str = segment.get("end")
        base_speed = float(segment.get("speed", 100))
        repetition = max(0, int(segment.get("repetition", 1)))

        if not start_str or not end_str:
            print(f"Segment {idx} missing 'start' or 'end' time. Skipping.")
            continue

        # Parse timecodes
        start_time = parse_timecode(start_str)
        end_time = parse_timecode(end_str)

        if start_time >= end_time:
            print(f"Segment {idx} has start time >= end time. Skipping.")
            continue

        if repetition == 0:
            print(f"Segment {idx} has 0 reps. Skipping.")
            play_index += 1
            continue

        for rep in range(repetition):
            ramped_speed = min(200.0, base_speed + gradient * play_index)
            speed_factor = ramped_speed / 100
            print(f"[Segment {idx}] rep {rep+1}/{repetition}  speed={ramped_speed:.1f}%")
            loop_segment(song_path, start_time, end_time, 1, speed_factor, log_path, manage_pygame=False)
            play_index += 1

    pygame.quit()
    print("All segments have been played and logged.")

if __name__ == "__main__":
    main()
