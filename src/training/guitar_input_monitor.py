"""Local single-channel audio capture for the Windows guitar trainer."""

from __future__ import annotations

import math
from collections import deque
from queue import Empty, Full, Queue
from statistics import median
import sys
from threading import Event, Lock, Thread
import time
from typing import Any, Callable

from training.pitch_detection import (
    FRAME_SIZE,
    SAMPLE_RATE,
    PitchEstimate,
    detect_pitch,
    prepare_pitch_detector,
)

FOCUSRITE_INPUT_DEVICE = "Focusrite USB ASIO"
ANALYSIS_QUEUE_SIZE = 4
MAX_CALLBACK_SAMPLES = FRAME_SIZE * 2
LOST_CALLBACK_SECONDS = 0.25


class GuitarInputMonitor:
    """Capture channel 1 from the fixed Focusrite input and expose its level."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._lifecycle_lock = Lock()
        self._stream: Any | None = None
        self._analysis_queue: Queue[tuple[int, tuple[float, ...]]] = Queue(
            maxsize=ANALYSIS_QUEUE_SIZE
        )
        self._analysis_stop = Event()
        self._analysis_thread: Thread | None = None
        self._pitch_epoch = 0
        self._pitch_history: deque[PitchEstimate] = deque(maxlen=3)
        self._last_callback_at: float | None = None
        self._state: dict[str, object] = {
            "active": False,
            "level": 0,
            "signal_present": False,
            "clipping": False,
            "error": None,
            "pitch": None,
        }

    def start(self) -> dict[str, object]:
        """Start capture from channel 1 of the fixed Focusrite input device."""
        with self._lifecycle_lock:
            if sys.platform != "win32":
                raise RuntimeError("Guitar input monitoring is supported on Windows only")
            with self._lock:
                if self._state["active"]:
                    return dict(self._state)
                self._state.update(
                    active=False,
                    level=0,
                    signal_present=False,
                    clipping=False,
                    error=None,
                    pitch=None,
                )
                self._clear_pitch_locked()

            stream = None
            worker = None
            stop_event = Event()
            analysis_queue: Queue[tuple[int, tuple[float, ...]]] = Queue(
                maxsize=ANALYSIS_QUEUE_SIZE
            )
            try:
                prepare_pitch_detector()
                worker = Thread(
                    target=self._process_audio,
                    args=(analysis_queue, stop_event),
                    name="guitar-pitch-analysis",
                    daemon=True,
                )
                self._analysis_queue = analysis_queue
                self._analysis_stop = stop_event
                self._analysis_thread = worker
                worker.start()
                stream = _open_focusrite_input_stream(self._audio_callback)
                with self._lock:
                    self._state["active"] = True
                    self._last_callback_at = time.monotonic()
                stream.start()
            except Exception as exc:
                if stream is not None:
                    try:
                        stream.stop()
                    except Exception:
                        pass
                    try:
                        stream.close()
                    except Exception:
                        pass
                stop_event.set()
                if worker is not None:
                    worker.join()
                with self._lock:
                    self._stream = None
                    self._analysis_thread = None
                    self._last_callback_at = None
                    self._state.update(
                        active=False,
                        level=0,
                        signal_present=False,
                        clipping=False,
                        error=str(exc),
                        pitch=None,
                    )
                    self._clear_pitch_locked()
                raise

            with self._lock:
                self._stream = stream
                return dict(self._state)

    def snapshot(self) -> dict[str, object]:
        """Return the current capture state."""
        with self._lock:
            return dict(self._state)

    def stop(self) -> dict[str, object]:
        """Stop capture and release its input stream."""
        with self._lifecycle_lock:
            with self._lock:
                stream = self._stream
                self._stream = None
                worker = self._analysis_thread
                self._analysis_thread = None
                stop_event = self._analysis_stop
                stop_event.set()
                self._last_callback_at = None
                self._state.update(
                    active=False,
                    level=0,
                    signal_present=False,
                    clipping=False,
                    pitch=None,
                )
                self._clear_pitch_locked()

            error = None
            if stream is not None:
                try:
                    stream.stop()
                except Exception as exc:
                    error = str(exc)
                finally:
                    try:
                        stream.close()
                    except Exception as exc:
                        error = error or str(exc)
            if worker is not None:
                worker.join()

            with self._lock:
                self._state["error"] = error
                return dict(self._state)

    def _audio_callback(
        self,
        input_data: Any,
        frame_count: int,
        time_info: Any,
        status: Any,
    ) -> None:
        del frame_count, time_info
        try:
            samples = tuple(float(frame[0]) for frame in input_data)
        except (IndexError, TypeError, ValueError):
            self._mark_input_unreliable()
            return
        if not samples:
            self._mark_input_unreliable()
            return
        if any(not math.isfinite(sample) for sample in samples):
            self._mark_input_unreliable()
            return

        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        peak = max(abs(sample) for sample in samples)
        level = min(100, round(rms * 100))
        with self._lock:
            if not self._state["active"]:
                return
            self._last_callback_at = time.monotonic()
            clipping = peak >= 0.98
            signal_present = rms >= 0.01
            self._state.update(
                level=level,
                signal_present=signal_present,
                clipping=clipping,
            )
            if not signal_present or clipping or bool(status):
                self._clear_pitch_locked()
                return
            epoch = self._pitch_epoch

        bounded_samples = samples[-MAX_CALLBACK_SAMPLES:]
        packet = (epoch, bounded_samples)
        try:
            self._analysis_queue.put_nowait(packet)
        except Full:
            try:
                self._analysis_queue.get_nowait()
            except Empty:
                pass
            with self._lock:
                if not self._state["active"]:
                    return
                self._clear_pitch_locked()
                packet = (self._pitch_epoch, bounded_samples)
            try:
                self._analysis_queue.put_nowait(packet)
            except Full:
                return

    def _mark_input_unreliable(self) -> None:
        with self._lock:
            if not self._state["active"]:
                return
            self._last_callback_at = time.monotonic()
            self._state.update(level=0, signal_present=False, clipping=False)
            self._clear_pitch_locked()

    def _clear_pitch_locked(self) -> None:
        self._pitch_epoch += 1
        self._pitch_history.clear()
        self._state["pitch"] = None

    def _process_audio(
        self,
        analysis_queue: Queue[tuple[int, tuple[float, ...]]],
        stop_event: Event,
    ) -> None:
        buffered_samples: list[float] = []
        current_epoch: int | None = None
        while not stop_event.is_set():
            try:
                epoch, samples = analysis_queue.get(timeout=0.05)
            except Empty:
                self._clear_pitch_if_callbacks_lost()
                continue

            if current_epoch != epoch:
                buffered_samples.clear()
                current_epoch = epoch
            buffered_samples.extend(samples)
            if len(buffered_samples) > MAX_CALLBACK_SAMPLES:
                buffered_samples = buffered_samples[-MAX_CALLBACK_SAMPLES:]

            while len(buffered_samples) >= FRAME_SIZE and not stop_event.is_set():
                frame = buffered_samples[:FRAME_SIZE]
                del buffered_samples[:FRAME_SIZE]
                with self._lock:
                    current = self._state["active"] and epoch == self._pitch_epoch
                if not current:
                    buffered_samples.clear()
                    break
                try:
                    estimate = detect_pitch(frame)
                except Exception as exc:
                    estimate = None
                    detection_error = str(exc)
                else:
                    detection_error = None
                self._record_pitch_estimate(epoch, estimate, detection_error)

    def _record_pitch_estimate(
        self,
        epoch: int,
        estimate: PitchEstimate | None,
        error: str | None,
    ) -> None:
        with self._lock:
            if not self._state["active"] or epoch != self._pitch_epoch:
                return
            if error is not None:
                self._state.update(pitch=None, error=f"Pitch detection failed: {error}")
                self._pitch_history.clear()
                return
            self._state["error"] = None
            if estimate is None:
                self._pitch_history.clear()
                self._state["pitch"] = None
                return
            if self._pitch_history and (
                self._pitch_history[-1]["note"],
                self._pitch_history[-1]["octave"],
            ) != (estimate["note"], estimate["octave"]):
                self._pitch_history.clear()
                self._state["pitch"] = None
            self._pitch_history.append(estimate)
            if len(self._pitch_history) < 2:
                return

            frequency = float(median(item["frequency_hz"] for item in self._pitch_history))
            cents = round(median(item["cents"] for item in self._pitch_history))
            feedback = "flat" if cents < -5 else "sharp" if cents > 5 else "in_tune"
            self._state["pitch"] = {
                "note": estimate["note"],
                "octave": estimate["octave"],
                "frequency_hz": round(frequency, 2),
                "cents": cents,
                "feedback": feedback,
            }

    def _clear_pitch_if_callbacks_lost(self) -> None:
        with self._lock:
            last_callback = self._last_callback_at
            if (
                not self._state["active"]
                or last_callback is None
                or time.monotonic() - last_callback < LOST_CALLBACK_SECONDS
            ):
                return
            self._last_callback_at = None
            self._state.update(level=0, signal_present=False, clipping=False)
            self._clear_pitch_locked()


def _open_focusrite_input_stream(callback: Callable[..., None]) -> Any:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Audio capture is unavailable: sounddevice is not installed") from exc

    return sd.InputStream(
        device=FOCUSRITE_INPUT_DEVICE,
        channels=1,
        samplerate=SAMPLE_RATE,
        dtype="float32",
        callback=callback,
    )
