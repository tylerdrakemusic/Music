#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analysis and Summary of Changes
-------------------------------
The original file contained several issues that prevented correct execution and did not fully meet the specified requirements. Below is a summary of the key issues identified and the improvements made:

1) Invalid quantum_rt imports:
   - The original file attempted to import quantum_rt functions using an invalid multi-line syntax.
   - FIX: Replaced with the required exact import line:
       from quantum_rt import qRandom, qRax, qhoice, quuffle, qsample, qpermute, qRandomBool, qRandomBitstring

2) Lack of robust path resolution and incorrect directory handling:
   - The original code created directories relative to the current working directory, which is brittle.
   - FIX: Implemented a robust ROOT_DIR resolution as requested. All data directories now derive from ROOT_DIR.

3) Execution on import:
   - The original code executed directory creation at import-time.
   - FIX: All execution moved into functions that are invoked under the if __name__ == '__main__' guard.

4) Windows console and file Unicode safety:
   - The original file used plain open() and print(), which can fail on Windows consoles or when writing Unicode.
   - FIX: Added safe file reading/writing with encoding='utf-8' and errors='replace'. Implemented safe_print and stream reconfiguration.

5) Logging best practices:
   - The original code configured logging at import time and mixed print and logging.
   - FIX: Centralized logging configuration via configure_logging(). Logging is used for non-user-facing output.

6) Type hints and docstrings:
   - The original code lacked consistent type hints and detailed docstrings.
   - FIX: Added type hints and explicit docstrings for all public functions, classes, and methods.

7) JSON store robustness:
   - The original JSON handling did not guarantee initialization with defaults robustly or safe Unicode handling.
   - FIX: JSONStore now ensures that files are created with defaults and uses UTF-8 encoding with errors='replace'.

8) Object-Oriented and Design Patterns:
   - The original code was procedural around quote conversion.
   - FIX: Implemented a Strategy pattern for quote conversion and a QuoteConverter class to encapsulate behavior.

9) Concurrency and modularity:
   - The original code offered parallel conversion but lacked configurability.
   - FIX: Provided a modular parallel_conversion() function using ThreadPoolExecutor with configurable workers.

10) Repository storage rules:
    - All static lists stored in ROOT_DIR/tyJson. Exercise data in ROOT_DIR/exercises. Media directories ensured.
    - FIX: Implemented environment preparation and ensured directories exist under ROOT_DIR.

11) CLI interface:
    - The original code used sys.argv directly.
    - FIX: Implemented argparse for a clearer and more robust entry point.

12) Static list augmentation:
    - Requirement to "append creatively" to static lists.
    - FIX: Added seed_promo_quotes_from_quantum() that uses quantum_rt's qhoice and qRandomBool to optionally enrich the promo quotes list.

All TODOs were marked as DONE through the refactor. There are no endless loops, user input prompts, or sleep calls. The code is cross-platform compatible and import-safe.


Note: The quantum_rt import line is preserved exactly as mandated by the requirements. If the module is unavailable in the runtime environment, the import will fail with a clear error on startup.

"""

# Critical quantum functions import (must match exactly as required by the prompt).
from quantum_rt import qRandom, qRax, qhoice, quuffle, qsample, qpermute, qRandomBool, qRandomBitstring

import argparse
import concurrent.futures
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence


def _resolve_root() -> Path:
    """
    Resolve the repository root directory by walking up from this file location.

    Rules:
    - If a directory named 'tyJson' or a '.git' directory is found in the path or any ancestor,
      that directory is returned.
    - Otherwise, the parent directory of this file is returned.

    Returns:
        Path: The resolved repository root directory.
    """
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "tyJson").exists() or (p / ".git").exists():
            return p
    return here.parent


# Root directory and well-known subdirectories.
ROOT_DIR: Path = _resolve_root()
TYJSON_DIR: Path = ROOT_DIR / "tyJson"
EXERCISES_DIR: Path = ROOT_DIR / "exercises"
IMAGES_DIR: Path = ROOT_DIR / "images"
ENHANCED_IMAGES_DIR: Path = ROOT_DIR / "enhanced_images"
VIDEOS_DIR: Path = ROOT_DIR / "videos"
RECORDINGS_DIR: Path = ROOT_DIR / "recordings"


# Module-level logger.
LOGGER = logging.getLogger(__name__)


def configure_logging(level: str = "INFO") -> None:
    """
    Configure the logging subsystem for the module.

    Args:
        level (str): Logging level as a string (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR').
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    # Basic configuration with a clear, concise format and timestamps.
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    LOGGER.debug("Logging configured at level: %s", level.upper())


def configure_streams() -> None:
    """
    Configure standard output and error streams for UTF-8 output where possible,
    enabling robust Windows console behavior for Unicode.

    This function safely reconfigures stdout and stderr if the platform and Python
    version support it. Otherwise, it leaves them unchanged.
    """
    # Python 3.7+ supports reconfigure; older versions do not.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                # If reconfigure fails (rare), we will fallback in safe_print.
                pass


def ensure_directory(path: Path) -> None:
    """
    Ensure that a directory exists, creating it if missing.

    Args:
        path (Path): Directory path to ensure exists.
    """
    try:
        path.mkdir(parents=True, exist_ok=True)
        LOGGER.debug("Ensured directory exists: %s", str(path))
    except Exception as exc:
        LOGGER.error("Failed to ensure directory %s: %s", str(path), exc)


def prepare_environment() -> None:
    """
    Create all required directories under the repository root using the resolved ROOT_DIR.
    Also ensures JSON directories exist.

    Directories:
        - ROOT_DIR/tyJson
        - ROOT_DIR/exercises
        - ROOT_DIR/images
        - ROOT_DIR/enhanced_images
        - ROOT_DIR/videos
        - ROOT_DIR/recordings
    """
    for d in (TYJSON_DIR, EXERCISES_DIR, IMAGES_DIR, ENHANCED_IMAGES_DIR, VIDEOS_DIR, RECORDINGS_DIR):
        ensure_directory(d)
    LOGGER.info("Environment prepared. Data directories are ensured under ROOT_DIR: %s", str(ROOT_DIR))


class JSONStore:
    """
    JSON file storage utility class for managing persistent data.

    It initializes files with default content if missing and provides methods
    to append data safely.

    All file I/O is performed using UTF-8 encoding with 'replace' error handling
    to be robust across platforms including Windows consoles and filesystems.
    """

    def __init__(self, filepath: Path, default_data: Any) -> None:
        """
        Initialize the JSONStore.

        Args:
            filepath (Path): The path to the JSON file.
            default_data (Any): Default data to initialize if the file does not exist or is invalid.
        """
        self.filepath: Path = filepath
        self.default_data: Any = default_data
        ensure_directory(self.filepath.parent)
        self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """
        Ensure the JSON file exists and is initialized with default data if missing or corrupted.
        """
        if not self.filepath.exists():
            LOGGER.info("JSON file does not exist. Initializing with defaults: %s", str(self.filepath))
            self.save_json(self.default_data)
            return

        try:
            _ = self.load_json()
        except Exception as exc:
            LOGGER.error("Failed to load JSON (%s). Reinitializing with defaults. Error: %s", str(self.filepath), exc)
            self.save_json(self.default_data)

    def load_json(self) -> Any:
        """
        Load and return the JSON content from the file.

        Returns:
            Any: Parsed JSON data.

        Raises:
            RuntimeError: If the file cannot be read or JSON is malformed and cannot be recovered.
        """
        try:
            with self.filepath.open("r", encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Malformed JSON in {self.filepath}: {exc}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to read JSON file {self.filepath}: {exc}") from exc

    def save_json(self, data: Any) -> None:
        """
        Save the provided data to the JSON file.

        Args:
            data (Any): Data to write to JSON.
        """
        try:
            with self.filepath.open("w", encoding="utf-8", errors="replace") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            LOGGER.error("Failed to write JSON file %s: %s", str(self.filepath), exc)
            raise

    def append_data(self, key: str, new_item: Any) -> bool:
        """
        Append a new item to a list stored at the specified key if not already present.

        Args:
            key (str): JSON key that should point to a list.
            new_item (Any): The item to append.

        Returns:
            bool: True if the item was appended, False otherwise.
        """
        try:
            data = self.load_json()
        except RuntimeError as exc:
            LOGGER.error("Cannot append data because loading failed: %s", exc)
            return False

        if not isinstance(data, dict) or key not in data:
            LOGGER.warning("Key '%s' not found in JSON data or data is not a dict.", key)
            return False

        target = data.get(key)
        if not isinstance(target, list):
            LOGGER.warning("Key '%s' is not a list in JSON data.", key)
            return False

        if new_item in target:
            LOGGER.info("Item already present under key '%s'. Not appending.", key)
            return False

        target.append(new_item)
        try:
            self.save_json(data)
            LOGGER.info("Appended new item to '%s' in %s", key, str(self.filepath))
            return True
        except Exception as exc:
            LOGGER.error("Failed saving JSON after append: %s", exc)
            return False


class QuoteConversionStrategy(Protocol):
    """
    Protocol for quote conversion strategies.
    Implementations should define a 'convert' method that performs the conversion.
    """

    def convert(self, text: str) -> str:
        """
        Convert quotes in the provided text according to the strategy.

        Args:
            text (str): Input text.

        Returns:
            str: Converted text.
        """
        ...


@dataclass
class SimpleReplaceStrategy:
    """
    A simple quote conversion strategy that replaces all occurrences of one quote
    character with another using str.replace.
    """
    quote_to_replace: str = '"'
    replacement_quote: str = "'"

    def convert(self, text: str) -> str:
        """
        Convert quotes by replacing occurrences of quote_to_replace with replacement_quote.

        Args:
            text (str): Input text.

        Returns:
            str: Converted text.
        """
        return text.replace(self.quote_to_replace, self.replacement_quote)


@dataclass
class QuoteConverter:
    """
    A converter that applies a given quote conversion strategy to text.
    """
    strategy: QuoteConversionStrategy = field(default_factory=SimpleReplaceStrategy)

    def convert_quotes(self, text: str) -> str:
        """
        Convert quotes in the provided text using the configured strategy.

        Args:
            text (str): Input text.

        Returns:
            str: Converted text.
        """
        return self.strategy.convert(text)


def process_conversion(input_text: str, converter: Optional[QuoteConverter] = None) -> str:
    """
    Convert quotes in a single text using the provided converter.

    Args:
        input_text (str): Text to convert.
        converter (Optional[QuoteConverter]): A QuoteConverter instance. If None, a default is used.

    Returns:
        str: Converted text.
    """
    conv = converter or QuoteConverter()
    return conv.convert_quotes(input_text)


def parallel_conversion(
    text_list: Sequence[str],
    max_workers: Optional[int] = None,
    converter: Optional[QuoteConverter] = None,
) -> List[str]:
    """
    Convert quotes in a list of texts concurrently using ThreadPoolExecutor.

    Args:
        text_list (Sequence[str]): List of texts to process.
        max_workers (Optional[int]): Maximum worker threads. If None, defaults to ThreadPoolExecutor's default.
        converter (Optional[QuoteConverter]): Optional QuoteConverter to reuse among tasks.

    Returns:
        List[str]: Converted texts in the same order.
    """
    if not text_list:
        return []

    conv = converter or QuoteConverter()
    # Using a closure to capture conv and satisfy the executor mapping.
    def _task(s: str) -> str:
        return process_conversion(s, conv)

    try:
        # Limit workers to a reasonable number to avoid resource contention on very large inputs.
        workers = min(len(text_list), os.cpu_count() or 4) if max_workers is None else max_workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(_task, text_list))
        return results
    except Exception as exc:
        LOGGER.error("Error during parallel conversion: %s", exc)
        return []


def safe_print(text: str) -> None:
    """
    Print text to stdout safely across platforms, replacing invalid characters if necessary.

    Args:
        text (str): Text to print.
    """
    try:
        # Normal case: print will use the (possibly reconfigured) stdout.
        print(text)
    except UnicodeEncodeError:
        # Fallback: write bytes with replacement.
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write((text + os.linesep).encode(encoding, errors="replace"))


def seed_promo_quotes_from_quantum(store: JSONStore, key: str = "promo_quotes") -> None:
    """
    Seed the promotional quotes JSON with an additional creative entry using quantum_rt randomness.
    Uses qhoice to pick a candidate and qRandomBool to decide whether to add it.

    Args:
        store (JSONStore): The JSON store containing promo quotes.
        key (str): The JSON key listing promotional quotes.
    """
    # Candidate phrases that might be appended.
    candidates = [
        "Unlock member-only savings today",
        "Early-bird pricing ends soon",
        "Weekend flash sale: don't miss out",
        "Upgrade and save more this season",
        "Celebrate with bonus rewards",
        "Your cart qualifies for a surprise gift",
        "Bundle and save on top-rated items",
    ]

    try:
        should_add = qRandomBool()
    except Exception:
        # If the quantum function fails, default to True once to keep behavior deterministic.
        should_add = True

    if not should_add:
        LOGGER.debug("Quantum coin flip decided not to add a new promotional quote this run.")
        return

    try:
        # Use qhoice to select a creative promotional quote.
        # If it fails, fall back to the first candidate.
        selected = qhoice(candidates)
    except Exception:
        selected = candidates[0]

    appended = store.append_data(key, selected)
    if appended:
        LOGGER.info("Seeded promo quotes with a new item via quantum selection: %s", selected)
    else:
        LOGGER.debug("No new promotional item appended (already present or list missing).")


def initialize_default_data() -> None:
    """
    Initialize or ensure default JSON data files exist:
    - promo_static_quotes.json under ROOT_DIR/tyJson
    - physical_exercises.json under ROOT_DIR/exercises
    """
    # Promo quotes JSON
    promo_json_path = TYJSON_DIR / "promo_static_quotes.json"
    default_promo_data: Dict[str, Any] = {
        "promo_quotes": [
            "Limited time offer",
            "Exclusive deal",
            "Buy one get one free",
        ]
    }
    promo_store = JSONStore(promo_json_path, default_promo_data)
    # Attempt a creative append using quantum randomness.
    seed_promo_quotes_from_quantum(promo_store, key="promo_quotes")

    # Physical exercises JSON
    exercise_json_path = EXERCISES_DIR / "physical_exercises.json"
    default_exercise_data: Dict[str, Any] = {
        "exercises": [
            {"name": "Push-ups", "type": "strength", "duration_seconds": 60},
            {"name": "Jumping Jacks", "type": "cardio", "duration_seconds": 45},
            {"name": "Plank", "type": "core", "duration_seconds": 90},
        ]
    }
    JSONStore(exercise_json_path, default_exercise_data)
    LOGGER.info("Default data initialized in tyJson and exercises directories.")


def build_arg_parser() -> argparse.ArgumentParser:
    """
    Build and return the argument parser for the CLI.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Convert all double quotes to single quotes in promotional text."
    )
    parser.add_argument(
        "--text",
        type=str,
        help="An input string to convert quotes for. If omitted, a demo runs unless --no-demo is set.",
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        help="Skip the demo parallel conversion when no --text is provided.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level. Default is INFO.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Maximum number of worker threads for parallel conversion demo.",
    )
    return parser


def run_demo(max_workers: Optional[int] = None) -> None:
    """
    Run a demo of parallel quote conversion on sample texts.

    Args:
        max_workers (Optional[int]): Maximum threads to use in the demo conversion.
    """
    sample_texts = [
        'This is a "sample" text with "multiple" quotes.',
        '"Hello", she said, "World!"',
        "No quotes here at all.",
        "Café \"Signature\" special — try it now!",
    ]
    converted = parallel_conversion(sample_texts, max_workers=max_workers)
    for original, result in zip(sample_texts, converted):
        LOGGER.info("Original: %s", original)
        LOGGER.info("Converted: %s", result)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """
    Main entry point for the script.

    Args:
        argv (Optional[Iterable[str]]): Optional iterable of arguments for testing.

    Returns:
        int: Process exit code (0 for success, non-zero for errors).
    """
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    configure_logging(args.log_level)
    configure_streams()
    try:
        prepare_environment()
        initialize_default_data()
    except Exception as exc:
        LOGGER.error("Failed to prepare environment or initialize data: %s", exc)
        return 2

    if args.text:
        try:
            converted_string = process_conversion(args.text)
            safe_print(f"Converted string: {converted_string}")
        except Exception as exc:
            LOGGER.error("Error converting input text: %s", exc)
            return 3
    else:
        if not args.no_demo:
            run_demo(max_workers=args.max_workers)
        else:
            LOGGER.info("No input text provided and demo disabled by --no-demo.")

    return 0


if __name__ == "__main__":
    # Execute only when run as a script, not on import.
    sys.exit(main())
""" 
End of file.
"""