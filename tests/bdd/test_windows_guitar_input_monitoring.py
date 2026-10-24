"""Executable acceptance coverage for Windows guitar input monitoring."""
from __future__ import annotations

from dataclasses import dataclass
import sys
from types import SimpleNamespace
from typing import Any, Callable

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


class _CaptureStream:
    def __init__(self, callback: Callable[..., None]) -> None:
        self._callback = callback
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.feed(0.37)

    def feed(self, value: float) -> None:
        self._callback([[value] for _ in range(100)], 100, None, None)

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def _new_monitoring_context(
    monkeypatch: pytest.MonkeyPatch,
) -> _MonitoringContext:
    created: dict[str, object] = {}

    def open_stream(**options: Any) -> _CaptureStream:
        stream = _CaptureStream(options["callback"])
        created.update(stream=stream, options=options)
        return stream

    monkeypatch.setattr(capture.sys, "platform", "win32")
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
    assert stopped_state["clipping"] is False