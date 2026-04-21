"""
File: tylerJamesDrakeClick.py

# Analysis and Change Summary

## Analysis
This script provides a quantum-enhanced metronome with audio click playback. The original concept relied on an infinite loop with time.sleep, used print statements, had limited modularity, and lacked robust error handling and Unicode safety. It also did not fulfill the additional requirements to manage JSON list files in tyJson and exercises directories, ensure directory creation for media assets, and avoid failures when sound files are missing.

## Key Enhancements Implemented
- Introduced a Metronome class with clear responsibilities and robust validation.
- Replaced print statements with logging; added configurable logging levels and Unicode-safe output sanitization for Windows consoles.
- Lazy and safe handling of the simpleaudio dependency; meaningful errors if unavailable.
- Added quantum_rt random utilities to sample click sounds when a directory is provided.
- Avoided endless loops by defaulting to a finite number of beats when neither beats nor duration is provided.
- Implemented a WAV synthesizer fallback to generate click sounds if no valid sound files are found (no external dependencies like numpy).
- Added JSON list store utilities with correct initialization, list top-level structure, and backward compatibility (dict to list conversion).
- Introduced session logging to tyJson/metronome_sessions.json for each metronome run.
- Created an ExerciseRepository that initializes physical exercises data and logs an exercise activity per run in exercises/exercise_log.json.
- Ensured existence of directories: tyJson, exercises, images, enhanced_images, videos, recordings.
- Used concurrent.futures.ThreadPoolExecutor for controlled asynchronous playback.
- Comprehensive type hints, docstrings, and modular design suitable for testing.
- Comments and docstrings only; no stray non-code text.

Note: The script synthesizes click WAV files if no valid files are available, ensuring the metronome functions out-of-the-box.

"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
import struct
import sys
import time
from typing import Any, List, Optional, Tuple

# Quantum random imports (must be preserved exactly as specified)
from quantum_rt import qRandom, qRax, qhoice, quuffle, qsample, qpermute, qRandomBool, qRandomBitstring

# Lazy import placeholder for simpleaudio to avoid raising import errors on module import
try:
    import simpleaudio as _sa  # type: ignore
    sa = _sa
except Exception:
    sa = None  # Will be validated on metronome start


# ---------------------------
# Utilities and Infrastructure
# ---------------------------

def sanitize_console_output(text: str) -> str:
    """
    Sanitize string for console output on Windows by replacing non-encodable characters.

    Args:
        text: The text to sanitize.

    Returns:
        A sanitized string safe for console output.
    """
    encoding = sys.stdout.encoding or 'utf-8'
    try:
        return text.encode(encoding, errors='replace').decode(encoding)
    except Exception:
        return text.encode('ascii', errors='replace').decode('ascii')


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure logging for the application with a stream handler to stdout.

    Args:
        level: The logging level to set (e.g., logging.INFO).
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(stream=sys.stdout)],
        force=True,
    )


def ensure_directories(base: Path) -> None:
    """
    Ensure that required directories exist for JSON and media storage.

    Args:
        base: The base directory of the script.
    """
    required_dirs = [
        base / 'tyJson',
        base / 'exercises',
        base / 'images',
        base / 'enhanced_images',
        base / 'videos',
        base / 'recordings',
    ]
    for d in required_dirs:
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            logging.getLogger(__name__).error(
                sanitize_console_output(f"Failed to ensure directory '{d}': {ex}")
            )


class JsonListStore:
    """
    JSON list store utility that ensures files are initialized as lists and provides
    append and read functionality with backward compatibility for dict-based files.
    """

    def __init__(self, path: Path) -> None:
        """
        Initialize the JSON store.

        Args:
            path: Path to the JSON file.
        """
        self.path = path
        self.logger = logging.getLogger(__name__)
        self._ensure_exists()

    def _ensure_exists(self) -> None:
        """
        Ensure the JSON file exists and is initialized to an empty list if missing.
        """
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.exists():
                with self.path.open('w', encoding='utf-8') as f:
                    json.dump([], f)
        except Exception as ex:
            self.logger.error(sanitize_console_output(f"Failed to initialize JSON file '{self.path}': {ex}"))

    def read(self) -> List[Any]:
        """
        Read the JSON file and return a list.

        Returns:
            A list loaded from JSON file. If a dict is found, it's converted to a list of values.
        """
        try:
            with self.path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, list):
                    if isinstance(data, dict):
                        data = list(data.values())
                    else:
                        data = []
                return data
        except FileNotFoundError:
            # Recreate the file and return empty list
            self._ensure_exists()
            return []
        except json.JSONDecodeError:
            self.logger.warning(sanitize_console_output(f"JSON decode error for '{self.path}', re-initializing as empty list."))
            try:
                with self.path.open('w', encoding='utf-8') as f:
                    json.dump([], f)
            except Exception as ex:
                self.logger.error(sanitize_console_output(f"Failed to rewrite JSON file '{self.path}': {ex}"))
            return []
        except Exception as ex:
            self.logger.error(sanitize_console_output(f"Failed to read JSON file '{self.path}': {ex}"))
            return []

    def append(self, item: Any) -> None:
        """
        Append an item to the JSON list file.

        Args:
            item: The item to append (must be JSON serializable).
        """
        data = self.read()
        data.append(item)
        try:
            with self.path.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as ex:
            self.logger.error(sanitize_console_output(f"Failed to write to JSON file '{self.path}': {ex}"))


@dataclass
class MetronomeSession:
    """
    Dataclass describing a metronome session to be persisted to tyJson.
    """
    tempo: int
    time_signature: str
    beats_requested: Optional[int]
    duration_requested: Optional[float]
    beats_played: int
    started_at: float
    ended_at: float
    first_beat_sound: str
    click_sound: str
    bitstring: str  # an example of quantum_rt integration for session entropy


class TyJsonManager:
    """
    Manager for tyJson-related persistence, particularly metronome sessions.
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize the TyJson manager.

        Args:
            base_dir: The base directory where tyJson resides.
        """
        self.base_dir = base_dir
        self.store = JsonListStore(self.base_dir / 'tyJson' / 'metronome_sessions.json')

    def log_session(self, session: MetronomeSession) -> None:
        """
        Append a metronome session record to tyJson.

        Args:
            session: The MetronomeSession instance to persist.
        """
        self.store.append(asdict(session))


class ExerciseRepository:
    """
    Repository for storing default physical exercises and logging activity.
    """

    def __init__(self, base_dir: Path) -> None:
        """
        Initialize the repository.

        Args:
            base_dir: The base directory where exercises reside.
        """
        self.base_dir = base_dir
        self.exercises_store = JsonListStore(self.base_dir / 'exercises' / 'physical_exercises.json')
        self.log_store = JsonListStore(self.base_dir / 'exercises' / 'exercise_log.json')

    def ensure_defaults(self) -> None:
        """
        Ensure that the default physical exercises are present.
        """
        defaults = [
            {"name": "Bodyweight Squats", "reps": "3x15", "focus": "lower_body"},
            {"name": "Push-ups", "reps": "3x12", "focus": "upper_body"},
            {"name": "Plank", "reps": "3x45s", "focus": "core"},
            {"name": "Lunges", "reps": "3x10/leg", "focus": "lower_body"},
            {"name": "Glute Bridges", "reps": "3x20", "focus": "posterior_chain"},
        ]
        data = self.exercises_store.read()
        if not data:
            # Initialize with defaults
            for ex in defaults:
                self.exercises_store.append(ex)

    def log_activity(self, activity: dict) -> None:
        """
        Log an exercise-related activity.

        Args:
            activity: A dictionary describing the activity (JSON serializable).
        """
        self.log_store.append(activity)


# ---------------------------------
# Audio click sound utilities/synth
# ---------------------------------

def synthesize_click(output_path: Path, frequency: float = 1000.0, duration_sec: float = 0.03) -> Path:
    """
    Synthesize a simple sine-wave click and save as a WAV file.

    Args:
        output_path: Where to save the synthesized WAV.
        frequency: Frequency of the sine wave in Hz.
        duration_sec: Duration of the sound in seconds.

    Returns:
        Path to the synthesized WAV file.

    Raises:
        IOError: If writing the file fails.
    """
    sample_rate = 44100
    amplitude = 16000  # 16-bit audio
    n_samples = int(duration_sec * sample_rate)

    # Create directory
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import wave
        with wave.open(str(output_path), 'wb') as wf:
            wf.setnchannels(1)  # mono
            wf.setsampwidth(2)  # 2 bytes per sample
            wf.setframerate(sample_rate)
            for i in range(n_samples):
                t = i / sample_rate
                value = int(amplitude * math.sin(2 * math.pi * frequency * t))
                wf.writeframes(struct.pack('<h', value))
    except Exception as ex:
        logging.getLogger(__name__).error(
            sanitize_console_output(f"Failed to synthesize click WAV '{output_path}': {ex}")
        )
        raise
    return output_path


def ensure_default_clicks(base_dir: Path) -> Tuple[Path, Path]:
    """
    Ensure that default click sounds exist. If not, synthesize them.

    Args:
        base_dir: Base directory of the script.

    Returns:
        A tuple of (first_beat_sound_path, click_sound_path).
    """
    asmr_dir = base_dir / 'asmr'
    default_click = asmr_dir / 'Click2-Sebastian-759472264.wav'
    default_first = asmr_dir / 'Click2-Sebastian-759472264_n_steps_8.wav'

    if default_click.exists() and default_first.exists():
        return default_first, default_click

    # Synthesize if needed
    generated_dir = base_dir / 'generated_sounds'
    gen_click = generated_dir / 'click.wav'
    gen_first = generated_dir / 'first.wav'

    if not gen_click.exists():
        synthesize_click(gen_click, frequency=1200.0, duration_sec=0.03)
    if not gen_first.exists():
        synthesize_click(gen_first, frequency=800.0, duration_sec=0.06)

    return gen_first, gen_click


# ------------------
# Metronome Core OOP
# ------------------

class Metronome:
    """
    A metronome class for audio click playback at a specified tempo and time signature.
    """

    def __init__(
        self,
        tempo: int,
        time_signature: Tuple[int, int],
        first_beat_sound: Optional[Path] = None,
        click_sound: Optional[Path] = None,
        num_beats: Optional[int] = None,
        duration_sec: Optional[float] = None,
        click_sounds_dir: Optional[Path] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        """
        Initialize the Metronome with audio resources and timing parameters.

        Args:
            tempo: Beats per minute.
            time_signature: Tuple of (beats_per_measure, note_value).
            first_beat_sound: Path to first-beat sound.
            click_sound: Path to regular click sound.
            num_beats: Stop after this many beats (defaults to 120 if duration is not specified).
            duration_sec: Stop after this many seconds.
            click_sounds_dir: Directory of .wav click sounds for quantum selection.
            logger: Optional logger instance.
        """
        self.logger = logger or logging.getLogger(__name__)

        if tempo <= 0:
            raise ValueError("Tempo must be a positive integer BPM.")

        self.tempo = tempo
        self.time_signature = time_signature
        self.click_sounds_dir = click_sounds_dir

        # Avoid endless loop: if both None, default beats to 120
        self.num_beats = num_beats if (num_beats is not None or duration_sec is not None) else 120
        self.duration_sec = duration_sec

        self.first_beat_sound: Optional[Path] = first_beat_sound
        self.click_sound: Optional[Path] = click_sound

        self._interval = 60.0 / float(self.tempo)
        self._beats_per_measure = int(self.time_signature[0])
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        self._should_stop = False

        # Validate sounds or synthesize defaults
        self._validate_and_prepare_sounds()

    def _validate_and_prepare_sounds(self) -> None:
        """
        Validate and initialize click sounds. If click_sounds_dir is provided, quantum-sample
        sounds from that directory. If sounds are missing, attempt to use defaults or synthesize.
        """
        base_dir = Path(__file__).parent

        # Directory-sampled sounds if provided
        if self.click_sounds_dir and self.click_sounds_dir.is_dir():
            wav_files = list(self.click_sounds_dir.glob('*.wav'))
            if wav_files:
                # Quantum selection
                sampled_click = qhoice(wav_files)
                # Choose a different file for the first beat if possible
                if len(wav_files) > 1:
                    first_choices = [f for f in wav_files if f != sampled_click]
                    sampled_first = qhoice(first_choices)
                else:
                    sampled_first = sampled_click
                self.click_sound = self.click_sound or sampled_click
                self.first_beat_sound = self.first_beat_sound or sampled_first
                self.logger.info(
                    sanitize_console_output(
                        f"Quantum-selected sounds: click='{self.click_sound}', first='{self.first_beat_sound}'"
                    )
                )

        # If still None, attempt default files or synthesized
        if self.click_sound is None or self.first_beat_sound is None:
            default_first, default_click = ensure_default_clicks(base_dir)
            self.click_sound = self.click_sound or default_click
            self.first_beat_sound = self.first_beat_sound or default_first

        # Final existence check; if missing, synthesize as fallback
        if not self.click_sound.exists() or not self.first_beat_sound.exists():
            self.logger.warning(
                sanitize_console_output("Provided sound files not found; synthesizing defaults.")
            )
            default_first, default_click = ensure_default_clicks(base_dir)
            self.click_sound = default_click
            self.first_beat_sound = default_first

        # Type assertion
        if not isinstance(self.click_sound, Path) or not isinstance(self.first_beat_sound, Path):
            raise TypeError("Sound paths must be pathlib.Path instances.")

    def play_click(self, sound_path: Path) -> None:
        """
        Play a click sound synchronously inside a thread pool worker.

        Args:
            sound_path: Path to the .wav file to play.
        """
        if sa is None:
            # The dependency is not installed; provide actionable error
            self.logger.error(
                sanitize_console_output(
                    "Audio playback requires 'simpleaudio'. Install it with: pip install simpleaudio"
                )
            )
            return

        try:
            wave_obj = sa.WaveObject.from_wave_file(str(sound_path))
            play_obj = wave_obj.play()
            play_obj.wait_done()
        except Exception as ex:
            self.logger.error(sanitize_console_output(f"Failed to play sound '{sound_path}': {ex}"))

    def run(self) -> int:
        """
        Start the metronome. Stops after num_beats or duration_sec if specified.

        Returns:
            The total number of beats played.
        """
        if sa is None:
            raise RuntimeError("The 'simpleaudio' module is required to play audio. Install with 'pip install simpleaudio'.")

        beats_limit_text = f"{self.num_beats} beats" if self.num_beats is not None else "unlimited beats"
        dur_text = f"{self.duration_sec:.2f} seconds" if self.duration_sec is not None else "no duration limit"
        self.logger.info(
            sanitize_console_output(
                f"Starting metronome at {self.tempo} BPM, {self.time_signature[0]}/{self.time_signature[1]} "
                f"({beats_limit_text}, {dur_text})"
            )
        )

        beat_count = 0
        start_time = time.time()
        try:
            while not self._should_stop:
                beat_count += 1
                is_first = ((beat_count - 1) % self._beats_per_measure == 0)
                sound = self.first_beat_sound if is_first else self.click_sound
                assert sound is not None
                self._executor.submit(self.play_click, sound)

                # Exit conditions
                if self.num_beats is not None and beat_count >= self.num_beats:
                    self.logger.info(sanitize_console_output(f"Metronome stopped after {beat_count} beats."))
                    break
                if self.duration_sec is not None and (time.time() - start_time) >= self.duration_sec:
                    self.logger.info(
                        sanitize_console_output(f"Metronome stopped after {self.duration_sec:.2f} seconds.")
                    )
                    break

                # Interval control with monotonic time for accuracy
                next_tick = time.monotonic() + self._interval
                while True:
                    remaining = next_tick - time.monotonic()
                    if remaining <= 0:
                        break
                    # Short, bounded sleep to maintain responsiveness and avoid endless sleeps
                    time.sleep(min(0.02, remaining))
        except KeyboardInterrupt:
            self.logger.info(sanitize_console_output("Metronome interrupted by user (KeyboardInterrupt)."))
        finally:
            self._should_stop = True
            self._executor.shutdown(wait=True)
            self.logger.info(sanitize_console_output("Metronome shut down cleanly."))
        return beat_count


# -----------------
# CLI and Main Entry
# -----------------

def parse_time_signature(sig: str) -> Tuple[int, int]:
    """
    Parse a time signature string such as "4/4" or "3/8".

    Args:
        sig: The time signature string.

    Returns:
        A tuple of (beats_per_measure, note_value).

    Raises:
        ValueError: If the signature is not in the expected format 'x/y' with integers.
    """
    try:
        beats_str, note_str = sig.strip().split('/')
        beats = int(beats_str)
        note = int(note_str)
        if beats <= 0 or note <= 0:
            raise ValueError
        return (beats, note)
    except Exception:
        raise ValueError(f"Invalid time signature format: '{sig}'. Use forms like '4/4' or '3/8'.")


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the metronome.

    Returns:
        An argparse.Namespace with parsed arguments.
    """
    parser = argparse.ArgumentParser(description='Quantum-enhanced Metronome')
    parser.add_argument('tempo', type=int, help='Tempo in beats per minute (BPM)')
    parser.add_argument('--time_signature', type=str, default="4/4", help='Time signature, e.g., 4/4, 3/4')
    parser.add_argument('--first_beat_sound', type=str, help='Path to custom first beat sound file (wav)')
    parser.add_argument('--click_sound', type=str, help='Path to custom click sound file (wav)')
    parser.add_argument('--beats', type=int, help='Number of beats to play before stopping')
    parser.add_argument('--duration', type=float, help='Duration in seconds to play before stopping')
    parser.add_argument('--click_sounds_dir', type=str, help='Directory of .wav click sounds for quantum selection')
    parser.add_argument(
        '--loglevel',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the metronome CLI.
    """
    args = parse_args()
    loglevel = getattr(logging, args.loglevel.upper(), logging.INFO)
    setup_logging(level=loglevel)
    logger = logging.getLogger(__name__)

    # Prepare directories
    base_dir = Path(__file__).parent.resolve()
    ensure_directories(base_dir)

    # Initialize repositories for JSON management
    tyjson_manager = TyJsonManager(base_dir)
    exercise_repo = ExerciseRepository(base_dir)
    exercise_repo.ensure_defaults()

    # Validate and parse CLI inputs
    if args.tempo < 30 or args.tempo > 400:
        logger.error(sanitize_console_output("Tempo must be between 30 and 400 BPM for practicality."))
        sys.exit(1)

    try:
        time_sig = parse_time_signature(args.time_signature)
    except ValueError as ve:
        logger.error(sanitize_console_output(str(ve)))
        sys.exit(1)

    if args.beats is not None and args.beats < 1:
        logger.error(sanitize_console_output("Number of beats must be positive."))
        sys.exit(1)
    if args.duration is not None and args.duration <= 0:
        logger.error(sanitize_console_output("Duration must be a positive number of seconds."))
        sys.exit(1)

    # Prepare paths
    first_beat_sound: Optional[Path] = Path(args.first_beat_sound).resolve() if args.first_beat_sound else None
    click_sound: Optional[Path] = Path(args.click_sound).resolve() if args.click_sound else None
    click_sounds_dir: Optional[Path] = Path(args.click_sounds_dir).resolve() if args.click_sounds_dir else None

    # Construct and run metronome
    try:
        metronome = Metronome(
            tempo=args.tempo,
            time_signature=time_sig,
            first_beat_sound=first_beat_sound,
            click_sound=click_sound,
            num_beats=args.beats,
            duration_sec=args.duration,
            click_sounds_dir=click_sounds_dir,
            logger=logger
        )
        started_at = time.time()
        beats_played = metronome.run()
        ended_at = time.time()

        # Compose and log session record to tyJson with a quantum bitstring for entropy
        bitstring = qRandomBitstring(32)
        session = MetronomeSession(
            tempo=args.tempo,
            time_signature=args.time_signature,
            beats_requested=args.beats,
            duration_requested=args.duration,
            beats_played=beats_played,
            started_at=started_at,
            ended_at=ended_at,
            first_beat_sound=str(metronome.first_beat_sound) if metronome.first_beat_sound else "",
            click_sound=str(metronome.click_sound) if metronome.click_sound else "",
            bitstring=bitstring,
        )
        tyjson_manager.log_session(session)

        # Log an exercise-related activity entry, creatively generated with quantum_rt
        activities = [
            "Coordination drill with alternating claps",
            "Foot-tapping synchronization practice",
            "Posture and breathing alignment exercise",
            "Tempo stability focus with minimal movement",
            "Hand-percussion groove refinement",
        ]
        chosen_activity = qhoice(activities)
        exercise_activity = {
            "activity": chosen_activity,
            "duration_sec": args.duration if args.duration else max(10, int(beats_played * (60.0 / args.tempo))),
            "tempo": args.tempo,
            "time_signature": args.time_signature,
            "ts_bitstring": bitstring,
        }
        exercise_repo.log_activity(exercise_activity)

    except Exception as e:
        logger.error(sanitize_console_output(f"Failed to run metronome: {e}"))
        sys.exit(1)


if __name__ == '__main__':
    main()