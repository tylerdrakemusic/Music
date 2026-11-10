"""Executable acceptance coverage for Windows guitar input monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import runpy
import sys
import time
from types import SimpleNamespace
from typing import Any, Callable

from flask import Flask
import pytest
from pytest_bdd import given, scenario, then, when

from training import guitar_input_monitor as capture
from training.guitar_input_monitor import GuitarInputMonitor
from training import musician_training_ui as ui


@dataclass
class _MonitoringContext:
    client: object
    monitor: GuitarInputMonitor
    stream_handles: dict[str, object]
    response: object | None = None
    pitch_observations: list[tuple[str, int, float, dict[str, Any]]] = field(default_factory=list)


class _CaptureStream:
    def __init__(self, callback: Callable[..., None]) -> None:
        self._callback = callback
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.feed(0.37)

    def feed(self, value: float) -> None:
        self._callback([[value] for _ in range(100)], 100, None, None)

    def feed_samples(self, samples: list[float]) -> None:
        self._callback([[sample] for sample in samples], len(samples), None, None)

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def _new_monitoring_context(
    monkeypatch: pytest.MonkeyPatch,
) -> _MonitoringContext:
    created: dict[str, object] = {}
    open_count = 0

    def open_stream(**options: Any) -> _CaptureStream:
        nonlocal open_count
        open_count += 1
        stream = _CaptureStream(options["callback"])
        created.update(stream=stream, options=options, open_count=open_count)
        return stream

    monkeypatch.setattr(capture, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=open_stream),
    )
    monkeypatch.setattr(ui, "_list_sessions", lambda: [])
    monkeypatch.setattr(ui, "_load_log", lambda: [])
    monkeypatch.setattr(
        ui,
        "get_practice_stats",
        lambda: {"streak_days": 0, "week_minutes": 0, "last_practiced": None},
    )
    monitor = GuitarInputMonitor()
    monkeypatch.setattr(ui, "guitar_input_monitor", monitor, raising=False)
    ui.app.config["TESTING"] = True
    return _MonitoringContext(
        client=ui.app.test_client(),
        monitor=monitor,
        stream_handles=created,
    )


def test_mock_windows_capture_does_not_change_interpreter_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    _new_monitoring_context(monkeypatch)

    assert sys.platform == "linux"


@pytest.mark.parametrize(
    ("route", "headers"),
    [
        ("/api/guitar-input/start", {"Origin": "https://attacker.example"}),
        ("/api/guitar-input/stop", {"Origin": "https://attacker.example"}),
        (
            "/api/guitar-input/start",
            {"Origin": "http://localhost.evil", "Referer": "http://localhost/"},
        ),
        (
            "/api/guitar-input/stop",
            {"Origin": "http://localhost:5056", "Referer": "http://localhost/"},
        ),
        (
            "/api/guitar-input/stop",
            {"Origin": "null", "Referer": "http://localhost/"},
        ),
        ("/api/guitar-input/start", {"Origin": "http://localhost?"}),
        ("/api/guitar-input/stop", {"Origin": "http://localhost#"}),
        ("/api/guitar-input/start", {"Origin": "http://localhost."}),
        ("/api/guitar-input/stop", {"Origin": " http://localhost"}),
        ("/api/guitar-input/stop", {}),
    ],
)
def test_capture_control_rejects_foreign_origin_before_device_access(
    monkeypatch: pytest.MonkeyPatch,
    route: str,
    headers: dict[str, str],
) -> None:
    context = _new_monitoring_context(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(context.monitor, "start", lambda: calls.append("start"))
    monkeypatch.setattr(context.monitor, "stop", lambda: calls.append("stop"))

    response = context.client.post(
        route,
        headers=headers,
    )

    assert response.status_code == 403
    assert calls == []


def test_capture_control_uses_same_origin_referer_when_origin_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _new_monitoring_context(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(
        context.monitor,
        "stop",
        lambda: calls.append("stop") or context.monitor.snapshot(),
    )

    response = context.client.post(
        "/api/guitar-input/stop",
        headers={"Referer": "http://localhost/trainer"},
    )

    assert response.status_code == 200
    assert calls == ["stop"]


def test_capture_control_rejects_untrusted_host_even_when_origin_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _new_monitoring_context(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(context.monitor, "start", lambda: calls.append("start"))

    response = context.client.post(
        "/api/guitar-input/start",
        base_url="http://attacker.example",
        headers={"Origin": "http://attacker.example"},
    )

    assert response.status_code == 403
    assert calls == []


def test_capture_control_allows_same_origin_configured_network_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_hosts = set(ui.app.config["CAPTURE_CONTROL_ALLOWED_HOSTS"])
    allowed_hosts.add("192.0.2.44")
    monkeypatch.setitem(
        ui.app.config,
        "CAPTURE_CONTROL_ALLOWED_HOSTS",
        frozenset(allowed_hosts),
    )
    context = _new_monitoring_context(monkeypatch)

    response = context.client.post(
        "/api/guitar-input/start",
        base_url="http://192.0.2.44:5055",
        headers={"Origin": "http://192.0.2.44:5055"},
    )

    assert response.status_code == 200
    assert response.get_json()["active"] is True


@scenario(
    "windows_guitar_input_monitoring.feature",
    "Start monitoring the Scarlett input",
)
def test_start_monitoring_reports_live_input() -> None:
    pass


@given(
    "the Trainer is running on Windows, the Scarlett is available, and guitar signal reaches channel 1",
    target_fixture="monitoring_context",
)
def trainer_with_available_scarlett(
    monkeypatch: pytest.MonkeyPatch,
) -> _MonitoringContext:
    return _new_monitoring_context(monkeypatch)


@when("the user starts monitoring")
def start_monitoring(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.response = monitoring_context.client.post(
        "/api/guitar-input/start",
        headers={"Origin": "http://localhost"},
    )


@then("the level meter responds to the input and the UI reports signal present")
def assert_live_input_is_reported(monitoring_context: _MonitoringContext) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 200
    payload = monitoring_context.response.get_json()
    assert payload["active"] is True
    assert payload["level"] > 0
    assert payload["signal_present"] is True
    assert monitoring_context.stream_handles["options"]["device"] == "Focusrite USB ASIO"
    assert monitoring_context.stream_handles["options"]["channels"] == 1


@scenario(
    "windows_guitar_input_monitoring.feature",
    "Report no signal below the threshold",
)
def test_monitoring_reports_no_signal_below_threshold() -> None:
    pass


@given("monitoring is active", target_fixture="monitoring_context")
def active_monitoring(monkeypatch: pytest.MonkeyPatch) -> _MonitoringContext:
    context = _new_monitoring_context(monkeypatch)
    context.response = context.client.post(
        "/api/guitar-input/start",
        headers={"Origin": "http://localhost"},
    )
    assert context.response.status_code == 200
    return context


@when("the input falls below the signal-present threshold")
def input_falls_below_signal_threshold(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.stream_handles["stream"].feed(0.0)
    monitoring_context.response = monitoring_context.client.get(
        "/api/guitar-input/status"
    )


@then("the UI reports no signal.")
def assert_no_signal_is_reported(monitoring_context: _MonitoringContext) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 200
    payload = monitoring_context.response.get_json()
    assert payload["active"] is True
    assert payload["signal_present"] is False


@scenario(
    "windows_guitar_input_monitoring.feature",
    "Warn when the input clips",
)
def test_monitoring_warns_when_input_clips() -> None:
    pass


@when("the input reaches the clipping threshold")
def input_reaches_clipping_threshold(
    monitoring_context: _MonitoringContext,
) -> None:
    monitoring_context.stream_handles["stream"].feed(1.0)
    monitoring_context.response = monitoring_context.client.get(
        "/api/guitar-input/status"
    )


@then("the UI displays a clipping/overload warning.")
def assert_clipping_warning_is_reported(
    monitoring_context: _MonitoringContext,
) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 200
    payload = monitoring_context.response.get_json()
    assert payload["active"] is True
    assert payload["clipping"] is True


@scenario(
    "windows_guitar_input_monitoring.feature",
    "Report an unavailable Scarlett input",
)
def test_unavailable_input_is_reported_without_active_monitoring() -> None:
    pass


@given(
    "the Scarlett or its input is unavailable",
    target_fixture="monitoring_context",
)
def unavailable_scarlett_input(
    monkeypatch: pytest.MonkeyPatch,
) -> _MonitoringContext:
    context = _new_monitoring_context(monkeypatch)

    def unavailable_input(**options: Any) -> None:
        raise OSError("Focusrite USB ASIO input is unavailable")

    monkeypatch.setitem(
        sys.modules,
        "sounddevice",
        SimpleNamespace(InputStream=unavailable_input),
    )
    return context


@then(
    "the UI reports the capture error and does not indicate that monitoring is active."
)
def assert_unavailable_capture_is_reported(
    monitoring_context: _MonitoringContext,
) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 503
    payload = monitoring_context.response.get_json()
    assert payload["active"] is False
    assert "Focusrite USB ASIO input is unavailable" in payload["error"]
    page = monitoring_context.client.get("/").get_data(as_text=True)
    assert 'id="guitar-input-monitor"' in page
    assert 'id="guitar-input-status"' in page


@scenario(
    "windows_guitar_input_monitoring.feature",
    "Stop capture and release the device",
)
def test_stop_capture_releases_device_and_stops_meter_updates() -> None:
    pass


@when("the user stops monitoring or the Trainer shuts down")
def stop_monitoring(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.response = monitoring_context.client.post(
        "/api/guitar-input/stop",
        headers={"Origin": "http://localhost"},
    )


@then("capture stops, the device is released, and meter updates cease.")
def assert_capture_stops_and_releases_device(
    monitoring_context: _MonitoringContext,
) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 200
    payload = monitoring_context.response.get_json()
    assert payload["active"] is False
    assert payload["level"] == 0
    assert monitoring_context.stream_handles["stream"].stopped is True
    assert monitoring_context.stream_handles["stream"].closed is True

    monitoring_context.stream_handles["stream"].feed(1.0)
    stopped_state = monitoring_context.client.get(
        "/api/guitar-input/status"
    ).get_json()
    assert stopped_state["level"] == 0
    assert stopped_state["signal_present"] is False
    assert stopped_state["clipping"] is False
    assert stopped_state["pitch"] is None
    assert stopped_state["level"] == 0


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Tune clean notes across the guitar range",
)
def test_tuner_identifies_clean_notes_across_guitar_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@given(
    "the Windows Focusrite channel 1 monitor is active",
    target_fixture="monitoring_context",
)
def active_windows_guitar_input(
    monkeypatch: pytest.MonkeyPatch,
) -> _MonitoringContext:
    context = _new_monitoring_context(monkeypatch)
    context.response = context.client.post(
        "/api/guitar-input/start",
        headers={"Origin": "http://localhost"},
    )
    assert context.response.status_code == 200
    return context


def _wait_for_tuner_pitch(
    context: _MonitoringContext,
    note: str,
    octave: int,
) -> tuple[dict[str, Any], float]:
    started_at = time.monotonic()
    deadline = started_at + 0.5
    payload: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        response = context.client.get("/api/guitar-input/status")
        payload = response.get_json()
        if "pitch" not in payload:
            break
        pitch = payload["pitch"]
        if pitch is not None and pitch["note"] == note and pitch["octave"] == octave:
            break
        time.sleep(0.005)
    return payload, time.monotonic() - started_at


def _wait_for_no_tuner_pitch(
    context: _MonitoringContext,
) -> tuple[dict[str, Any], float]:
    started_at = time.monotonic()
    deadline = started_at + 0.5
    payload: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        response = context.client.get("/api/guitar-input/status")
        payload = response.get_json()
        if "pitch" not in payload or payload["pitch"] is None:
            break
        time.sleep(0.005)
    return payload, time.monotonic() - started_at


def _clean_note_samples(frequency: float) -> list[float]:
    sample_rate = 44100
    frame_count = 16384
    return [
        0.25 * math.sin(2 * math.pi * frequency * index / sample_rate)
        for index in range(frame_count)
    ]


@when("sustained clean E2, A4, and E6 notes reach the input")
def clean_notes_reach_the_guitar_input(
    monitoring_context: _MonitoringContext,
) -> None:
    stream = monitoring_context.stream_handles["stream"]
    for note, octave, frequency in (
        ("E", 2, 82.4069),
        ("A", 4, 440.0),
        ("E", 6, 1318.5102),
    ):
        stream.feed_samples(_clean_note_samples(frequency))
        payload, elapsed = _wait_for_tuner_pitch(
            monitoring_context,
            note,
            octave,
        )
        monitoring_context.pitch_observations.append((note, octave, elapsed, payload))
        if "pitch" not in payload:
            break


@then("each note settles within 500 milliseconds and three cents")
def assert_clean_notes_are_tuned(
    monitoring_context: _MonitoringContext,
) -> None:
    observations = monitoring_context.pitch_observations
    assert len(observations) == 3, "status response does not yet expose tuner pitch"
    for note, octave, elapsed, payload in observations:
        pitch = payload["pitch"]
        assert elapsed <= 0.5
        assert pitch["note"] == note
        assert pitch["octave"] == octave
        assert abs(pitch["cents"]) <= 3
        assert pitch["frequency_hz"] > 0
        assert pitch["feedback"] == "in_tune"


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Include both five-cent boundaries in tune",
)
def test_tuner_includes_both_five_cent_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@when("A4 is five cents flat and then five cents sharp")
def feed_five_cent_boundaries(monitoring_context: _MonitoringContext) -> None:
    stream = monitoring_context.stream_handles["stream"]
    for cents in (-5, 5):
        stream.feed(0.0)
        frequency = 440.0 * 2 ** (cents / 1200)
        stream.feed_samples(_clean_note_samples(frequency))
        payload, elapsed = _wait_for_tuner_pitch(monitoring_context, "A", 4)
        monitoring_context.pitch_observations.append(("A", 4, elapsed, payload))
        if "pitch" not in payload:
            break


@then("both boundary readings report in tune")
def assert_five_cent_boundaries_are_in_tune(
    monitoring_context: _MonitoringContext,
) -> None:
    observations = monitoring_context.pitch_observations
    assert len(observations) == 2, "status response does not yet expose tuner pitch"
    for expected_cents, (_, octave, elapsed, payload) in zip((-5, 5), observations):
        assert "pitch" in payload
        pitch = payload["pitch"]
        assert octave == 4
        assert elapsed <= 0.5
        assert pitch["cents"] == expected_cents
        assert pitch["feedback"] == "in_tune"


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Tune a representative processed guitar tone",
)
def test_tuner_handles_representative_processed_tone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


def _processed_e2_samples() -> list[float]:
    sample_rate = 44100
    frame_count = 16384
    dry = [
        0.16
        * (
            0.18 * math.sin(2 * math.pi * 82.4069 * index / sample_rate)
            + math.sin(2 * math.pi * 2 * 82.4069 * index / sample_rate)
            + 0.38 * math.sin(2 * math.pi * 3 * 82.4069 * index / sample_rate)
            + 0.14 * math.sin(2 * math.pi * 4 * 82.4069 * index / sample_rate)
        )
        for index in range(frame_count)
    ]
    clipped = [math.tanh(sample * 3.0) for sample in dry]
    delay = round(sample_rate * 0.012)
    return [
        sample + (0.12 * clipped[index - delay] if index >= delay else 0.0)
        for index, sample in enumerate(clipped)
    ]


@when("a harmonic-rich overdrive tone with light echo reaches the input")
def processed_tone_reaches_input(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.stream_handles["stream"].feed_samples(_processed_e2_samples())
    monitoring_context.response, elapsed = _wait_for_tuner_pitch(
        monitoring_context,
        "E",
        2,
    )
    monitoring_context.pitch_observations.append(("E", 2, elapsed, monitoring_context.response))


@then("E2 settles within 500 milliseconds and five cents")
def assert_processed_tone_is_tuned(
    monitoring_context: _MonitoringContext,
) -> None:
    note, octave, elapsed, payload = monitoring_context.pitch_observations[-1]
    assert "pitch" in payload, "status response does not yet expose tuner pitch"
    pitch = payload["pitch"]
    assert elapsed <= 0.5
    assert (pitch["note"], pitch["octave"]) == (note, octave)
    assert abs(pitch["cents"]) <= 5


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Reject overlapping notes and resume automatically",
)
def test_tuner_rejects_overlapping_notes_and_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@when("a valid E2 is replaced by simultaneous E2 and A2, then returns to E2")
def overlapping_notes_replace_and_resume(
    monitoring_context: _MonitoringContext,
) -> None:
    stream = monitoring_context.stream_handles["stream"]
    stream.feed_samples(_clean_note_samples(82.4069))
    tuned, _ = _wait_for_tuner_pitch(monitoring_context, "E", 2)
    monitoring_context.pitch_observations.append(("E", 2, 0.0, tuned))

    sample_rate = 44100
    overlap = [
        0.2
        * (
            math.sin(2 * math.pi * 82.4069 * index / sample_rate)
            + math.sin(2 * math.pi * 110.0 * index / sample_rate)
        )
        for index in range(16384)
    ]
    stream.feed_samples(overlap)
    cleared, elapsed = _wait_for_no_tuner_pitch(monitoring_context)
    monitoring_context.pitch_observations.append(("", 0, elapsed, cleared))

    stream.feed_samples(_clean_note_samples(82.4069))
    resumed, elapsed = _wait_for_tuner_pitch(monitoring_context, "E", 2)
    monitoring_context.pitch_observations.append(("E", 2, elapsed, resumed))


@then("overlap clears pitch and tuning resumes within 500 milliseconds")
def assert_overlap_is_rejected_and_tuning_resumes(
    monitoring_context: _MonitoringContext,
) -> None:
    initial, cleared, resumed = monitoring_context.pitch_observations
    assert "pitch" in initial[3] and initial[3]["pitch"] is not None
    assert "pitch" in cleared[3], "status response does not yet expose tuner pitch"
    assert cleared[3]["pitch"] is None
    assert cleared[2] <= 0.5
    assert resumed[3]["pitch"] is not None
    assert (resumed[3]["pitch"]["note"], resumed[3]["pitch"]["octave"]) == (
        "E",
        2,
    )
    assert resumed[2] <= 0.5


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Clear pitch for clipping, silence, and lost callbacks",
)
def test_tuner_clears_unreliable_and_lost_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@when("a valid E2 is clipped, falls silent, then callbacks stop")
def clipping_silence_and_lost_callbacks(
    monitoring_context: _MonitoringContext,
) -> None:
    stream = monitoring_context.stream_handles["stream"]
    stream.feed_samples(_clean_note_samples(82.4069))
    tuned, _ = _wait_for_tuner_pitch(monitoring_context, "E", 2)
    monitoring_context.pitch_observations.append(("E", 2, 0.0, tuned))

    clipped_samples = [math.sin(2 * math.pi * 82.4069 * index / 44100) for index in range(16384)]
    stream.feed_samples(clipped_samples)
    clipped, elapsed = _wait_for_no_tuner_pitch(monitoring_context)
    monitoring_context.pitch_observations.append(("", 0, elapsed, clipped))

    stream.feed_samples(_clean_note_samples(82.4069))
    _wait_for_tuner_pitch(monitoring_context, "E", 2)
    stream.feed_samples([0.0] * 16384)
    silent, elapsed = _wait_for_no_tuner_pitch(monitoring_context)
    monitoring_context.pitch_observations.append(("", 0, elapsed, silent))

    stream.feed_samples(_clean_note_samples(82.4069))
    _wait_for_tuner_pitch(monitoring_context, "E", 2)
    lost, elapsed = _wait_for_no_tuner_pitch(monitoring_context)
    monitoring_context.pitch_observations.append(("", 0, elapsed, lost))


@then("unreliable pitch clears within 500 milliseconds and the monitor stays active")
def assert_unreliable_pitch_is_cleared(
    monitoring_context: _MonitoringContext,
) -> None:
    initial, clipped, silent, lost = monitoring_context.pitch_observations
    assert "pitch" in initial[3] and initial[3]["pitch"] is not None
    for _, _, elapsed, payload in (clipped, silent, lost):
        assert "pitch" in payload, "status response does not yet expose tuner pitch"
        assert payload["pitch"] is None
        assert elapsed <= 0.5
        assert payload["active"] is True
    assert clipped[3]["clipping"] is True
    assert silent[3]["signal_present"] is False


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Render the tuner in the existing monitor location",
)
def test_tuner_renders_in_place_with_responsive_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@when("the Trainer page is opened")
def open_trainer_page(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.response = monitoring_context.client.get("/")


@then("the compact tuner is accessible in place with responsive layout rules")
def assert_compact_tuner_markup(monitoring_context: _MonitoringContext) -> None:
    assert monitoring_context.response.status_code == 200
    page = monitoring_context.response.get_data(as_text=True)
    for element_id in (
        "guitar-tuner",
        "guitar-tuner-note",
        "guitar-tuner-frequency",
        "guitar-tuner-cents",
        "guitar-tuner-meter",
        "guitar-tuner-feedback",
        "guitar-input-start",
        "guitar-input-stop",
        "guitar-input-level",
        "guitar-input-signal",
        "guitar-input-warning",
    ):
        assert f'id="{element_id}"' in page
    assert monitoring_context.client.get("/tuner").status_code == 404
    assert "Flat" in page and "In tune" in page and "Sharp" in page
    assert "@media(max-width:600px)" in page
    assert "overflow-wrap:anywhere" in page


@scenario(
    "live_chromatic_guitar_tuner.feature",
    "Stop and restart without duplicating capture",
)
def test_repeated_start_and_stop_preserve_capture_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pass


@when("a tuned capture is started again and then stopped")
def restart_and_stop_capture(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.stream_handles["stream"].feed_samples(_clean_note_samples(82.4069))
    _wait_for_tuner_pitch(monitoring_context, "E", 2)
    monitoring_context.client.post(
        "/api/guitar-input/start",
        headers={"Origin": "http://localhost"},
    )
    monitoring_context.response = monitoring_context.client.post(
        "/api/guitar-input/stop",
        headers={"Origin": "http://localhost"},
    )


@then("pitch clears and the single capture stream is released")
def assert_stop_clears_pitch_and_releases_stream(
    monitoring_context: _MonitoringContext,
) -> None:
    payload = monitoring_context.response.get_json()
    assert monitoring_context.stream_handles["open_count"] == 1
    assert payload["active"] is False
    assert "pitch" in payload, "status response does not yet expose tuner pitch"
    assert payload["pitch"] is None
    assert monitoring_context.stream_handles["stream"].stopped is True
    assert monitoring_context.stream_handles["stream"].closed is True


def test_trainer_entrypoint_starts_flask_without_request_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ASIO worked directly (RMS 0.0277, level 5) and with threaded=False,
    but Flask's threaded server exited with 0xC0000005 after /start. Keep the
    local entrypoint single-threaded; audio is never recorded by this test.
    """
    server_options: list[dict[str, object]] = []

    def capture_run(_app: Flask, **options: object) -> None:
        server_options.append(options)

    monkeypatch.setattr(Flask, "run", capture_run)
    monkeypatch.setattr(sys, "argv", [ui.__file__, "--port", "5055"])
    monkeypatch.setattr(ui.Path, "mkdir", lambda *_args, **_kwargs: None)

    runpy.run_path(ui.__file__, run_name="__main__")

    assert server_options == [
        {"host": "127.0.0.1", "port": 5055, "debug": False, "threaded": False}
    ]
