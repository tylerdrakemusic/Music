"""Local single-channel audio capture for the Windows guitar trainer."""
from __future__ import annotations

import math
import sys
from threading import Lock
from typing import Any, Callable

FOCUSRITE_INPUT_DEVICE = "Focusrite USB ASIO"


class GuitarInputMonitor:
    """Capture channel 1 from the fixed Focusrite input and expose its level."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._lifecycle_lock = Lock()
        self._stream: Any | None = None
        self._state: dict[str, object] = {
            "active": False,
            "level": 0,
            "signal_present": False,
            "clipping": False,
            "error": None,
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
                    active=True,
                    level=0,
                    signal_present=False,
                    clipping=False,
                    error=None,
                )

            stream = None
            try:
                stream = _open_focusrite_input_stream(self._audio_callback)
                stream.start()
            except Exception as exc:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
                with self._lock:
                    self._state.update(active=False, error=str(exc))
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
                self._state.update(
                    active=False,
                    level=0,
                    signal_present=False,
                    clipping=False,
                )

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
        del frame_count, time_info, status
        try:
            samples = [float(frame[0]) for frame in input_data]
        except (IndexError, TypeError, ValueError):
            return
        if not samples:
            return

        rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
        peak = max(abs(sample) for sample in samples)
        level = min(100, round(rms * 100))
        with self._lock:
            if self._state["active"]:
                self._state.update(
                    level=level,
                    signal_present=rms >= 0.01,
                    clipping=peak >= 0.98,
                )


def _open_focusrite_input_stream(callback: Callable[..., None]) -> Any:
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("Audio capture is unavailable: sounddevice is not installed") from exc

    return sd.InputStream(
        device=FOCUSRITE_INPUT_DEVICE,
        channels=1,
        samplerate=44100,
        dtype="float32",
        callback=callback,
    )