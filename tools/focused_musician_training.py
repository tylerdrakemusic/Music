import argparse
import os
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# pygame/pydub/numpy/librosa are only needed for actual audio playback (loop_segment,
# change_speed, main) — importing them lazily keeps pure helpers like
# build_playback_plan()/parse_timecode() usable (e.g. in tests) without requiring
# these heavier, audio-stack dependencies to be installed.

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from utils.init_db import get_connection  # noqa: E402

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

# Module-level exercise id set by main() once we know which _run_<id>.json
# we are executing.  None = migrated / manual session (exercise_id IS NULL).
_exercise_id: int | None = None

def change_speed(sound, speed=1.0):
    """Change playback speed of the audio segment without affecting pitch."""
    import numpy as np
    import librosa

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


def build_playback_plan(segments: list[dict], default_gradient: float = 0.0) -> list[dict]:
    """Expand rows into playback items while resetting each row's gradient ramp."""
    plan = []
    for segment_index, segment in enumerate(segments, start=1):
        start_str = segment.get("start")
        end_str = segment.get("end")
        base_speed = float(segment.get("speed", 100))
        repetition = max(0, int(segment.get("repetition", 1)))
        row_gradient = segment.get("gradient", default_gradient)
        row_gradient = default_gradient if row_gradient is None else float(row_gradient)

        if not start_str or not end_str:
            print(f"Segment {segment_index} missing 'start' or 'end' time. Skipping.")
            continue
        start_time = parse_timecode(start_str)
        end_time = parse_timecode(end_str)
        if start_time >= end_time:
            print(f"Segment {segment_index} has start time >= end time. Skipping.")
            continue
        if repetition == 0:
            print(f"Segment {segment_index} has 0 reps. Skipping.")
            continue

        for repetition_index in range(repetition):
            ramped_speed = min(200.0, base_speed + row_gradient * repetition_index)
            plan.append({
                "segment_index": segment_index,
                "start": start_time,
                "end": end_time,
                "speed": base_speed,
                "ramped_speed": ramped_speed,
                "repetition": 1,
                "repetition_index": repetition_index,
                "repetition_count": repetition,
            })
    return plan

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
        conn = get_connection()
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
    import pygame
    from pydub import AudioSegment

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
    import pygame

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

    # Init pygame once for the whole session
    pygame.mixer.init()
    pygame.init()
    pygame.display.set_mode((1, 1))

    for item in build_playback_plan(segments, default_gradient=gradient):
        speed_factor = item["ramped_speed"] / 100
        print(
            f"[Segment {item['segment_index']}] rep "
            f"{item['repetition_index'] + 1}/{item['repetition_count']}  "
            f"speed={item['ramped_speed']:.1f}%"
        )
        loop_segment(
            song_path,
            item["start"],
            item["end"],
            item["repetition"],
            speed_factor,
            log_path,
            manage_pygame=False,
        )

    pygame.quit()
    print("All segments have been played and logged.")

if __name__ == "__main__":
    main()
