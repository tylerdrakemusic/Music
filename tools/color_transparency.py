import argparse
import re
from collections import deque
from math import atan2, cos, degrees, exp, hypot, isfinite, radians, sin, sqrt
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def rgb_to_lab(color: tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = (channel / 255 for channel in color)
    red = red / 12.92 if red <= 0.04045 else ((red + 0.055) / 1.055) ** 2.4
    green = green / 12.92 if green <= 0.04045 else ((green + 0.055) / 1.055) ** 2.4
    blue = blue / 12.92 if blue <= 0.04045 else ((blue + 0.055) / 1.055) ** 2.4

    x = (red * 0.4124564 + green * 0.3575761 + blue * 0.1804375) / 0.95047
    y = red * 0.2126729 + green * 0.7151522 + blue * 0.0721749
    z = (red * 0.0193339 + green * 0.1191920 + blue * 0.9503041) / 1.08883

    threshold = (6 / 29) ** 3

    def transform(value: float) -> float:
        if value > threshold:
            return value ** (1 / 3)
        return value / (3 * (6 / 29) ** 2) + 4 / 29

    x_value, y_value, z_value = transform(x), transform(y), transform(z)
    return (
        116 * y_value - 16,
        500 * (x_value - y_value),
        200 * (y_value - z_value),
    )


def delta_e_ciede2000(
    first: tuple[float, float, float], second: tuple[float, float, float]
) -> float:
    first_l, first_a, first_b = first
    second_l, second_a, second_b = second
    first_chroma = hypot(first_a, first_b)
    second_chroma = hypot(second_a, second_b)
    mean_chroma = (first_chroma + second_chroma) / 2
    mean_chroma_seven = mean_chroma**7
    g = 0.5 * (1 - sqrt(mean_chroma_seven / (mean_chroma_seven + 25**7)))

    first_a_prime = (1 + g) * first_a
    second_a_prime = (1 + g) * second_a
    first_chroma_prime = hypot(first_a_prime, first_b)
    second_chroma_prime = hypot(second_a_prime, second_b)

    first_hue_prime = degrees(atan2(first_b, first_a_prime)) % 360
    second_hue_prime = degrees(atan2(second_b, second_a_prime)) % 360
    delta_l_prime = second_l - first_l
    delta_c_prime = second_chroma_prime - first_chroma_prime

    hue_difference = second_hue_prime - first_hue_prime
    if first_chroma_prime * second_chroma_prime == 0:
        delta_hue_prime = 0.0
    elif hue_difference > 180:
        delta_hue_prime = hue_difference - 360
    elif hue_difference < -180:
        delta_hue_prime = hue_difference + 360
    else:
        delta_hue_prime = hue_difference
    delta_h_prime = 2 * sqrt(first_chroma_prime * second_chroma_prime) * sin(
        radians(delta_hue_prime / 2)
    )

    mean_l_prime = (first_l + second_l) / 2
    mean_c_prime = (first_chroma_prime + second_chroma_prime) / 2
    if first_chroma_prime * second_chroma_prime == 0:
        mean_hue_prime = first_hue_prime + second_hue_prime
    elif abs(first_hue_prime - second_hue_prime) <= 180:
        mean_hue_prime = (first_hue_prime + second_hue_prime) / 2
    elif first_hue_prime + second_hue_prime < 360:
        mean_hue_prime = (first_hue_prime + second_hue_prime + 360) / 2
    else:
        mean_hue_prime = (first_hue_prime + second_hue_prime - 360) / 2

    t = (
        1
        - 0.17 * cos(radians(mean_hue_prime - 30))
        + 0.24 * cos(radians(2 * mean_hue_prime))
        + 0.32 * cos(radians(3 * mean_hue_prime + 6))
        - 0.20 * cos(radians(4 * mean_hue_prime - 63))
    )
    delta_theta = 30 * exp(-((mean_hue_prime - 275) / 25) ** 2)
    mean_chroma_prime_seven = mean_c_prime**7
    rotation_c = 2 * sqrt(
        mean_chroma_prime_seven / (mean_chroma_prime_seven + 25**7)
    )
    lightness_scale = 1 + 0.015 * (mean_l_prime - 50) ** 2 / sqrt(
        20 + (mean_l_prime - 50) ** 2
    )
    chroma_scale = 1 + 0.045 * mean_c_prime
    hue_scale = 1 + 0.015 * mean_c_prime * t
    rotation_t = -sin(radians(2 * delta_theta)) * rotation_c

    lightness_term = delta_l_prime / lightness_scale
    chroma_term = delta_c_prime / chroma_scale
    hue_term = delta_h_prime / hue_scale
    return sqrt(
        lightness_term**2
        + chroma_term**2
        + hue_term**2
        + rotation_t * chroma_term * hue_term
    )


def _perimeter_connected_mask(
    candidates: bytearray, width: int, height: int
) -> bytearray:
    selected = bytearray(len(candidates))
    frontier: deque[int] = deque()

    def enqueue(index: int) -> None:
        if candidates[index] and not selected[index]:
            selected[index] = 1
            frontier.append(index)

    for x in range(width):
        enqueue(x)
        enqueue((height - 1) * width + x)
    for y in range(height):
        enqueue(y * width)
        enqueue(y * width + width - 1)

    while frontier:
        index = frontier.popleft()
        x = index % width
        if x > 0:
            enqueue(index - 1)
        if x + 1 < width:
            enqueue(index + 1)
        if index >= width:
            enqueue(index - width)
        if index + width < len(candidates):
            enqueue(index + width)

    return selected


def _feather_rgba(
    source_pixels: bytes,
    candidates: bytearray,
    selected: bytearray,
    width: int,
    height: int,
    radius: int,
) -> bytes:
    output_pixels = bytearray(source_pixels)
    frontier = [index for index, value in enumerate(selected) if value]
    visited = bytearray(selected)

    for index in frontier:
        output_pixels[index * 4 + 3] = 0
    if radius == 0 or not frontier:
        return bytes(output_pixels)

    max_distance = min(radius, width + height - 2)
    for distance in range(1, max_distance + 1):
        next_frontier: list[int] = []

        def enqueue(index: int) -> None:
            if not visited[index]:
                visited[index] = 1
                next_frontier.append(index)

        for index in frontier:
            x = index % width
            if x > 0:
                enqueue(index - 1)
            if x + 1 < width:
                enqueue(index + 1)
            if index >= width:
                enqueue(index - width)
            if index + width < len(selected):
                enqueue(index + width)

        if not next_frontier:
            break
        for index in next_frontier:
            if not candidates[index]:
                alpha_index = index * 4 + 3
                output_pixels[alpha_index] = round(
                    source_pixels[alpha_index] * distance / (radius + 1)
                )
        frontier = next_frontier

    return bytes(output_pixels)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Make a selected color transparent in a PNG image."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--color", required=True)
    parser.add_argument("--tolerance", type=float, default=10)
    parser.add_argument("--global-match", action="store_true")
    parser.add_argument("--smooth-radius", type=int, default=1)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    if not re.fullmatch(r"#[0-9a-fA-F]{6}", arguments.color):
        parser.error("color must use #RRGGBB format")
    if not isfinite(arguments.tolerance) or not 0 <= arguments.tolerance <= 100:
        parser.error("tolerance must be a finite number from 0 to 100")
    if arguments.smooth_radius < 0:
        parser.error("smooth radius must be 0 or greater")
    if not arguments.input.is_file():
        parser.error(f"input file does not exist: {arguments.input}")
    if arguments.input.suffix.lower() != ".png":
        parser.error(f"input must be a PNG file: {arguments.input}")

    hex_color = arguments.color[1:]
    target_color = tuple(
        int(hex_color[index : index + 2], 16) for index in (0, 2, 4)
    )
    target_lab = rgb_to_lab(target_color)
    distance_cache: dict[tuple[int, int, int], float] = {}
    output_path = arguments.output or arguments.input.with_name(
        f"{arguments.input.stem}_transparent.png"
    )
    if arguments.input.resolve() == output_path.resolve():
        parser.error("refusing to overwrite the input file")
    if output_path.exists():
        parser.error(f"output already exists: {output_path}")

    try:
        with Image.open(arguments.input) as image:
            if image.format != "PNG":
                parser.error(f"input is not a PNG image: {arguments.input}")
            rgba = image.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        parser.error(f"cannot read input PNG {arguments.input}: {exc}")

    with rgba:
        source_pixels = rgba.tobytes()
        pixel_count = rgba.width * rgba.height
        candidate_mask = bytearray(pixel_count)
        for index in range(pixel_count):
            pixel_index = index * 4
            pixel_color = tuple(source_pixels[pixel_index : pixel_index + 3])
            if pixel_color not in distance_cache:
                distance_cache[pixel_color] = delta_e_ciede2000(
                    rgb_to_lab(pixel_color), target_lab
                )
            if distance_cache[pixel_color] <= arguments.tolerance:
                candidate_mask[index] = 1

        selected_mask = (
            candidate_mask
            if arguments.global_match
            else _perimeter_connected_mask(candidate_mask, *rgba.size)
        )
        output_pixels = _feather_rgba(
            source_pixels,
            candidate_mask,
            selected_mask,
            rgba.width,
            rgba.height,
            arguments.smooth_radius,
        )
        output = Image.frombytes("RGBA", rgba.size, output_pixels)
        output.save(output_path, format="PNG")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())