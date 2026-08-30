from pathlib import Path
import importlib.util
import json
import subprocess


def load_runner():
    runner_path = Path(__file__).parents[1] / "tools" / "run_tests.py"
    spec = importlib.util.spec_from_file_location("run_tests", runner_path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def test_serial_lane_collects_every_serial_only_file_without_leaking_parallel_safe_tests(tmp_path):
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\n"
        "testpaths = tests\n"
        "markers =\n"
        "    serial_only: requires the serial lane\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "tools" / "parallel_test_policy.json"
    policy_path.parent.mkdir()
    policy_path.write_text(
        json.dumps(
            {
                "parallel_ci": True,
                "max_workers": 2,
                "excluded_markers": ["serial_only"],
                "serial_test_paths": ["tests/test_audio.py"],
            }
        ),
        encoding="utf-8",
    )
    tests_path = tmp_path / "tests"
    tests_path.mkdir()
    (tests_path / "test_audio.py").write_text(
        "import pytest\n"
        "@pytest.mark.serial_only\n"
        "def test_audio(): pass\n",
        encoding="utf-8",
    )
    (tests_path / "test_second_serial.py").write_text(
        "import pytest\n"
        "@pytest.mark.serial_only\n"
        "def test_second_serial(): pass\n",
        encoding="utf-8",
    )
    (tests_path / "test_parallel_safe.py").write_text(
        "def test_parallel_safe(): pass\n",
        encoding="utf-8",
    )

    runner = load_runner()
    serial_command = runner.build_command(parallel=False, junitxml=None, repo_root=tmp_path)
    serial_collection = subprocess.run(
        [*serial_command, "--collect-only"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=runner._runner_environment(),
    )
    parallel_command = runner.build_command(parallel=True, junitxml=None, repo_root=tmp_path)

    assert serial_collection.returncode == 0, serial_collection.stdout + serial_collection.stderr
    assert "test_audio.py::test_audio" in serial_collection.stdout
    assert "test_second_serial.py::test_second_serial" in serial_collection.stdout
    assert "test_parallel_safe.py::test_parallel_safe" not in serial_collection.stdout
    assert "-p" in parallel_command and "xdist.plugin" in parallel_command
    marker_option = parallel_command.index("-m", parallel_command.index("-m") + 1)
    parallel_expression = parallel_command[marker_option + 1]
    assert "not serial_only" in parallel_expression
    assert "--ignore" not in parallel_command