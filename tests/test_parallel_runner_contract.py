from pathlib import Path
import configparser
import importlib.util
import json
import shlex


def load_runner():
    runner_path = Path(__file__).parents[1] / "tools" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("run_tests", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_parallel_runner_contract_is_declared():
    policy = Path(__file__).parents[1] / "tools" / "parallel_test_policy.json"
    runner = Path(__file__).parents[1] / "tools" / "run_tests.py"

    assert policy.is_file()
    assert runner.is_file()


def test_build_command_composes_policy_exclusions_with_repository_marker_defaults():
    root = Path(__file__).parents[1]
    command = load_runner().build_command(parallel=True, junitxml=None)
    parallel_command = load_runner().build_command(parallel=True, junitxml=None)

    marker_option = command.index("-m", command.index("-m") + 1)
    marker_expression = command[marker_option + 1]
    policy = json.loads((root / "tools" / "parallel_test_policy.json").read_text(encoding="utf-8"))
    config = configparser.ConfigParser(interpolation=None)
    config.read(root / "pytest.ini", encoding="utf-8")
    addopts = shlex.split(config.get("pytest", "addopts", fallback=""))
    configured = addopts[addopts.index("-m") + 1] if "-m" in addopts else None

    assert all(f"not {marker}" in marker_expression for marker in policy["excluded_markers"])
    assert configured is None or configured in marker_expression
    parallel_marker_option = parallel_command.index("-m", parallel_command.index("-m") + 1)
    parallel_expression = parallel_command[parallel_marker_option + 1]
    assert parallel_expression == marker_expression
    assert "--ignore" not in parallel_command


def test_main_propagates_worker_failure(monkeypatch):
    runner = load_runner()
    completed = type("Completed", (), {"returncode": 17})()
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: completed)
    monkeypatch.setattr(runner.sys, "argv", ["run_tests.py", "--parallel"])

    assert runner.main() == 17


def test_main_runs_serial_lane_after_parallel_failure(monkeypatch):
    runner = load_runner()
    calls = []
    responses = iter([type("Completed", (), {"returncode": 1})(), type("Completed", (), {"returncode": 0})()])
    monkeypatch.setattr(runner.subprocess, "run", lambda command, **kwargs: calls.append(command) or next(responses))
    monkeypatch.setattr(runner.sys, "argv", ["run_tests.py", "--parallel-junitxml", "tmp/p.xml", "--serial-junitxml", "tmp/s.xml"])

    assert runner.main() == 1
    assert len(calls) == 2
    assert "-n" in calls[0]
    assert "-n" not in calls[1]


def test_main_uses_serial_rollback_when_parallel_ci_is_disabled(monkeypatch):
    runner = load_runner()
    calls = []
    completed = type("Completed", (), {"returncode": 0})()
    monkeypatch.setattr(
        runner,
        "_policy",
        lambda repo_root: {
            "parallel_ci": False,
            "excluded_markers": ["playwright", "ci_unavailable", "serial_only"],
            "serial_test_paths": ["tests/test_guitar_trainer_exercise_audio.py"],
        },
    )
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or completed,
    )
    monkeypatch.setattr(
        runner.sys,
        "argv",
        [
            "run_tests.py",
            "--parallel-junitxml",
            "tmp/p.xml",
            "--serial-junitxml",
            "tmp/s.xml",
        ],
    )

    assert runner.main() == 0
    assert len(calls) == 1
    assert "-n" not in calls[0]
    assert calls[0][-1].endswith("s.xml")


def test_main_preserves_legacy_junitxml_as_single_serial_run(monkeypatch):
    runner = load_runner()
    calls = []
    completed = type("Completed", (), {"returncode": 0})()
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or completed,
    )
    monkeypatch.setattr(
        runner.sys,
        "argv",
        ["run_tests.py", "--junitxml", "tmp/legacy.xml"],
    )

    assert runner.main() == 0
    assert len(calls) == 1
    assert "-n" not in calls[0]
    assert calls[0][-1].endswith("legacy.xml")


def test_main_rejects_explicit_parallel_request_when_disabled(monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "_parallel_ci_enabled", lambda repo_root: False)
    monkeypatch.setattr(runner.sys, "argv", ["run_tests.py", "--parallel"])

    try:
        runner.main()
    except SystemExit as error:
        assert error.code == 2
    else:
        raise AssertionError("disabled parallel request was accepted")


def test_build_commands_keep_risky_tests_in_serial_lane_and_bound_parallel_workers():
    runner = load_runner()

    parallel_command = runner.build_command(parallel=True, junitxml=Path("tmp/parallel.xml"))
    serial_command = runner.build_command(parallel=False, junitxml=Path("tmp/serial.xml"))

    assert "-n" in parallel_command
    assert parallel_command[parallel_command.index("-n") + 1] == "2"
    parallel_marker_option = parallel_command.index("-m", parallel_command.index("-m") + 1)
    serial_marker_option = serial_command.index("-m", serial_command.index("-m") + 1)
    parallel_expression = parallel_command[parallel_marker_option + 1]
    serial_expression = serial_command[serial_marker_option + 1]
    assert "not playwright" in parallel_expression
    assert "not ci_unavailable" in parallel_expression
    assert "not serial_only" in parallel_expression
    assert "playwright" in serial_expression
    assert "ci_unavailable" in serial_expression
    assert "serial_only" in serial_expression
    assert parallel_command[-1].endswith("parallel.xml")
    assert serial_command[-1].endswith("serial.xml")


def test_build_commands_explicitly_load_required_plugins_when_autoload_is_disabled():
    runner = load_runner()

    parallel_command = runner.build_command(parallel=True, junitxml=None)
    serial_command = runner.build_command(parallel=False, junitxml=None)

    assert parallel_command[parallel_command.index("-p") + 1] == "pytest_mock"
    assert "xdist.plugin" in parallel_command
    assert serial_command[serial_command.index("-p") + 1] == "pytest_mock"


def test_runner_environment_disables_ambient_plugin_configuration(monkeypatch):
    runner = load_runner()
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "0")
    monkeypatch.setenv("PYTEST_PLUGINS", "unrelated.plugin")

    environment = runner._runner_environment()

    assert environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert "PYTEST_PLUGINS" not in environment