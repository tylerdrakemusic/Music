"""Executable acceptance coverage for Windows guitar input monitoring."""
from __future__ import annotations

from dataclasses import dataclass

from pytest_bdd import given, scenario, then, when

from training import musician_training_ui as ui


@dataclass
class _MonitoringContext:
    client: object
    response: object | None = None


class _SignalMonitor:
    def start(self) -> dict[str, object]:
        return {
            "active": True,
            "level": 37,
            "signal_present": True,
            "clipping": False,
            "error": None,
        }


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
def trainer_with_available_scarlett(monkeypatch) -> _MonitoringContext:
    monkeypatch.setattr(ui, "guitar_input_monitor", _SignalMonitor(), raising=False)
    ui.app.config["TESTING"] = True
    return _MonitoringContext(client=ui.app.test_client())


@when("the user starts monitoring")
def start_monitoring(monitoring_context: _MonitoringContext) -> None:
    monitoring_context.response = monitoring_context.client.post(
        "/api/guitar-input/start"
    )


@then("the level meter responds to the input and the UI reports signal present")
def assert_live_input_is_reported(monitoring_context: _MonitoringContext) -> None:
    assert monitoring_context.response is not None
    assert monitoring_context.response.status_code == 200
    payload = monitoring_context.response.get_json()
    assert payload["active"] is True
    assert payload["level"] > 0
    assert payload["signal_present"] is True