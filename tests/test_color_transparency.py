import subprocess
import sys
from pathlib import Path

from PIL import Image
import pytest

from tools import color_transparency


CLI_PATH = Path(__file__).resolve().parents[1] / "tools" / "color_transparency.py"


def _run_cli(input_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH), str(input_path), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )


def _write_edge_and_diagonal_fixture(path: Path) -> None:
    image = Image.new("RGB", (5, 5), (0, 0, 0))
    for position in ((0, 2), (1, 2), (2, 2), (3, 3)):
        image.putpixel(position, (255, 255, 255))
    image.save(path)


def _write_feather_fixture(path: Path, mode: str = "RGB") -> None:
    image = Image.new(mode, (5, 1), (0, 0, 0, 255) if mode == "RGBA" else (0, 0, 0))
    image.putpixel((0, 0), (255, 255, 255, 128) if mode == "RGBA" else (255, 255, 255))
    image.save(path)


def test_ciede2000_matches_published_reference_pairs() -> None:
    distance = getattr(color_transparency, "delta_e_ciede2000", None)
    assert callable(distance), "the CIEDE2000 helper is missing"

    reference_pairs = [
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
        ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
        ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0),
    ]
    for first, second, expected in reference_pairs:
        assert distance(first, second) == pytest.approx(expected, abs=0.0001)


def test_default_selection_keeps_enclosed_and_diagonal_only_pixels(tmp_path: Path) -> None:
    source_path = tmp_path / "components.png"
    _write_edge_and_diagonal_fixture(source_path)

    result = _run_cli(
        source_path,
        "--color",
        "#ffffff",
        "--tolerance",
        "0",
        "--smooth-radius",
        "0",
    )

    assert result.returncode == 0, result.stderr
    with Image.open(tmp_path / "components_transparent.png") as output:
        assert output.getpixel((0, 2)) == (255, 255, 255, 0)
        assert output.getpixel((1, 2)) == (255, 255, 255, 0)
        assert output.getpixel((2, 2)) == (255, 255, 255, 0)
        assert output.getpixel((3, 3)) == (255, 255, 255, 255)


def test_global_match_also_removes_enclosed_pixels(tmp_path: Path) -> None:
    source_path = tmp_path / "components.png"
    _write_edge_and_diagonal_fixture(source_path)
    output_path = tmp_path / "global.png"

    result = _run_cli(
        source_path,
        "--color",
        "#ffffff",
        "--tolerance",
        "0",
        "--global-match",
        "--smooth-radius",
        "0",
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    with Image.open(output_path) as output:
        assert output.getpixel((3, 3)) == (255, 255, 255, 0)


def test_default_smooth_radius_feathers_one_pixel(tmp_path: Path) -> None:
    source_path = tmp_path / "feather.png"
    _write_feather_fixture(source_path)

    result = _run_cli(source_path, "--color", "#ffffff")

    assert result.returncode == 0, result.stderr
    with Image.open(tmp_path / "feather_transparent.png") as output:
        assert output.getpixel((0, 0))[3] == 0
        assert output.getpixel((1, 0))[3] == 128
        assert output.getpixel((2, 0))[3] == 255


def test_custom_smooth_radius_feathers_each_requested_pixel(tmp_path: Path) -> None:
    source_path = tmp_path / "feather.png"
    _write_feather_fixture(source_path)
    output_path = tmp_path / "wide.png"

    result = _run_cli(
        source_path,
        "--color",
        "#ffffff",
        "--smooth-radius",
        "2",
        "--output",
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    with Image.open(output_path) as output:
        assert [output.getpixel((x, 0))[3] for x in range(5)] == [0, 85, 170, 255, 255]


def test_feather_alpha_respects_partial_source_alpha(tmp_path: Path) -> None:
    source_path = tmp_path / "partial.png"
    image = Image.new("RGBA", (5, 1), (0, 0, 0, 200))
    image.putpixel((0, 0), (255, 255, 255, 128))
    image.save(source_path)

    result = _run_cli(source_path, "--color", "#ffffff")

    assert result.returncode == 0, result.stderr
    with Image.open(tmp_path / "partial_transparent.png") as output:
        assert output.getpixel((0, 0))[3] == 0
        assert output.getpixel((1, 0))[3] == 100
        assert output.getpixel((2, 0))[3] == 200


def test_tolerance_100_includes_the_delta_e00_boundary(tmp_path: Path) -> None:
    source_path = tmp_path / "black_and_white.png"
    output_path = tmp_path / "boundary.png"
    image = Image.new("RGB", (2, 1))
    image.putdata([(0, 0, 0), (255, 255, 255)])
    image.save(source_path)

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            str(source_path),
            "--color",
            "#000000",
            "--tolerance",
            "100",
            "--global-match",
            "--smooth-radius",
            "0",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    with Image.open(output_path) as output:
        assert output.getpixel((0, 0)) == (0, 0, 0, 0)
        assert output.getpixel((1, 0)) == (255, 255, 255, 0)


def test_cli_refuses_to_overwrite_source(tmp_path: Path) -> None:
    source_path = tmp_path / "artwork.png"
    image = Image.new("RGB", (1, 1), (255, 255, 255))
    image.save(source_path)
    original_bytes = source_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            str(source_path),
            "--color",
            "#ffffff",
            "--output",
            str(source_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "overwrite the input" in result.stderr.lower()
    assert source_path.read_bytes() == original_bytes


def test_cli_refuses_to_overwrite_existing_destination(tmp_path: Path) -> None:
    source_path = tmp_path / "artwork.png"
    output_path = tmp_path / "result.png"
    Image.new("RGB", (1, 1), (255, 255, 255)).save(source_path)
    output_path.write_bytes(b"keep this existing file")
    original_output = output_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            str(source_path),
            "--color",
            "#ffffff",
            "--output",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode != 0
    assert "already exists" in result.stderr.lower()
    assert output_path.read_bytes() == original_output


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("--color", "123456", "color"),
        ("--color", "#12GG00", "color"),
        ("--tolerance", "-0.1", "tolerance"),
        ("--tolerance", "100.1", "tolerance"),
        ("--tolerance", "nan", "tolerance"),
        ("--smooth-radius", "-1", "smooth radius"),
    ],
)
def test_cli_rejects_invalid_arguments(
    tmp_path: Path, option: str, value: str, message: str
) -> None:
    source_path = tmp_path / "artwork.png"
    Image.new("RGB", (1, 1), (255, 255, 255)).save(source_path)

    result = _run_cli(source_path, "--color", "#ffffff", option, value)

    assert result.returncode != 0
    assert message in result.stderr.lower()
    assert not source_path.with_name("artwork_transparent.png").exists()


def test_cli_rejects_missing_input_with_clear_error(tmp_path: Path) -> None:
    source_path = tmp_path / "missing.png"

    result = _run_cli(source_path, "--color", "#ffffff")

    assert result.returncode != 0
    assert "input" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()
    assert not tmp_path.joinpath("missing_transparent.png").exists()


def test_cli_rejects_non_png_input_with_clear_error(tmp_path: Path) -> None:
    source_path = tmp_path / "artwork.jpg"
    Image.new("RGB", (1, 1), (255, 255, 255)).save(source_path, format="JPEG")

    result = _run_cli(source_path, "--color", "#ffffff")

    assert result.returncode != 0
    assert "png" in result.stderr.lower()
    assert "traceback" not in result.stderr.lower()
    assert not tmp_path.joinpath("artwork_transparent.png").exists()


def test_cli_preserves_source_alpha_for_unselected_pixels(tmp_path: Path) -> None:
    source_path = tmp_path / "alpha.png"
    image = Image.new("RGBA", (2, 1))
    image.putdata([(255, 255, 255, 123), (12, 34, 56, 77)])
    image.save(source_path)

    result = _run_cli(
        source_path,
        "--color",
        "#ffffff",
        "--tolerance",
        "0",
        "--global-match",
        "--smooth-radius",
        "0",
    )

    assert result.returncode == 0, result.stderr
    with Image.open(tmp_path / "alpha_transparent.png") as output:
        assert output.getpixel((0, 0)) == (255, 255, 255, 0)
        assert output.getpixel((1, 0)) == (12, 34, 56, 77)


def test_cli_writes_default_rgba_sibling_without_changing_source(tmp_path: Path) -> None:
    source_path = tmp_path / "artwork.png"
    output_path = tmp_path / "artwork_transparent.png"
    original_pixels = [(255, 255, 255), (12, 34, 56)]
    source_image = Image.new("RGB", (2, 1))
    source_image.putdata(original_pixels)
    source_image.save(source_path)
    original_bytes = source_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            str(source_path),
            "--color",
            "#ffffff",
            "--tolerance",
            "0",
            "--global-match",
            "--smooth-radius",
            "0",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert source_path.read_bytes() == original_bytes
    with Image.open(output_path) as output:
        assert output.mode == "RGBA"
        assert output.size == (2, 1)
        assert output.getpixel((0, 0)) == (255, 255, 255, 0)
        assert output.getpixel((1, 0)) == (12, 34, 56, 255)