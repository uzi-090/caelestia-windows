"""Material geometry used by Caelestia's moving artwork and visualizer.

The rounded-polygon construction is a Python adaptation of soramanew/m3shapes
(Apache-2.0), especially MaterialShapes, RoundedPolygon and Cubic, revision
32ad9ce328bb77ed349b40a3be10ee9ea610b8ab. Its star geometry matches the
Caelestia source; it is not a sinusoidal approximation of a cookie.

https://github.com/soramanew/m3shapes
Original C++ implementation: Apache License 2.0.
This adapted file is distributed under Apache License 2.0.
"""

from __future__ import annotations

import base64
from functools import lru_cache
import math

Point = tuple[float, float]
Cubic = tuple[Point, Point, Point, Point]


def _add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def _mul(a: Point, s: float) -> Point:
    return a[0] * s, a[1] * s


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _unit(a: Point) -> Point:
    length = math.hypot(*a)
    return _mul(a, 1 / length) if length else (0.0, 0.0)


def _lerp(a: Point, b: Point, t: float) -> Point:
    return _add(_mul(a, 1 - t), _mul(b, t))


def _line(a: Point, b: Point) -> Cubic:
    return a, _lerp(a, b, 1 / 3), _lerp(a, b, 2 / 3), b


def _arc(center: Point, start: Point, end: Point) -> Cubic:
    p0 = _unit(_sub(start, center))
    p1 = _unit(_sub(end, center))
    rot0 = -p0[1], p0[0]
    rot1 = -p1[1], p1[0]
    cosine = max(-1.0, min(1.0, _dot(p0, p1)))
    if cosine > 0.999:
        return _line(start, end)
    radius = math.dist(start, center)
    clockwise = _dot(rot0, _sub(end, center)) >= 0
    k = (radius * 4 / 3
         * (math.sqrt(2 * (1 - cosine)) - math.sqrt(max(0, 1 - cosine * cosine)))
         / (1 - cosine) * (1 if clockwise else -1))
    return start, _add(start, _mul(rot0, k)), _sub(end, _mul(rot1, k)), end


def _split(cubic: Cubic, t: float = 0.5) -> tuple[Cubic, Cubic]:
    a, b, c, d = cubic
    ab, bc, cd = _lerp(a, b, t), _lerp(b, c, t), _lerp(c, d, t)
    abc, bcd = _lerp(ab, bc, t), _lerp(bc, cd, t)
    mid = _lerp(abc, bcd, t)
    return (a, ab, abc, mid), (mid, bcd, cd, d)


def _point(cubic: Cubic, t: float) -> Point:
    u = 1 - t
    a, b, c, d = cubic
    return (a[0] * u ** 3 + 3 * b[0] * t * u ** 2 + 3 * c[0] * t ** 2 * u + d[0] * t ** 3,
            a[1] * u ** 3 + 3 * b[1] * t * u ** 2 + 3 * c[1] * t ** 2 * u + d[1] * t ** 3)


def _reverse(cubic: Cubic) -> Cubic:
    return cubic[3], cubic[2], cubic[1], cubic[0]


def _flanking_curve(cut: float, smoothing: float, vertex: Point, side_start: Point,
                    intersection: Point, other_intersection: Point,
                    center: Point, radius: float) -> Cubic:
    """The exact circular-to-edge smoothing construction from RoundedCorner."""
    direction = _unit(_sub(side_start, vertex))
    start = _add(vertex, _mul(direction, cut * (1 + smoothing)))
    p = _lerp(intersection, _mul(_add(intersection, other_intersection), 0.5), smoothing)
    end = _add(center, _mul(_unit(_sub(p, center)), radius))
    radial = _sub(end, center)
    tangent = -radial[1], radial[0]
    rotated_tangent = -tangent[1], tangent[0]
    denominator = _dot(direction, rotated_tangent)
    numerator = _dot(_sub(end, side_start), rotated_tangent)
    anchor_end = intersection
    if abs(denominator) >= 1e-4 and abs(denominator) >= 1e-4 * abs(numerator):
        anchor_end = _add(side_start, _mul(direction, numerator / denominator))
    anchor_start = _mul(_add(start, _mul(anchor_end, 2)), 1 / 3)
    return start, anchor_start, anchor_end, end


def _normalize(cubics: tuple[Cubic, ...] | list[Cubic]) -> tuple[Cubic, ...]:
    """m3shapes normalization uses approximate cubic control-point bounds."""
    points = [p for cubic in cubics for p in cubic]
    min_x, max_x = min(p[0] for p in points), max(p[0] for p in points)
    min_y, max_y = min(p[1] for p in points), max(p[1] for p in points)
    width, height = max_x - min_x, max_y - min_y
    side = max(width, height)
    offset = ((side - width) / 2 - min_x, (side - height) / 2 - min_y)
    return tuple(tuple(((p[0] + offset[0]) / side, (p[1] + offset[1]) / side)
                       for p in cubic) for cubic in cubics)


def _transformed(cubics: tuple[Cubic, ...], angle: float = 0,
                 y_scale: float = 1) -> tuple[Cubic, ...]:
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    def transform(p):
        x, y = p[0] - 0.5, (p[1] - 0.5) * y_scale
        return x * cosine - y * sine, x * sine + y * cosine
    return _normalize(tuple(tuple(transform(p) for p in cubic) for cubic in cubics))


def _rounded_polygon(vertices: list[Point], radii: list[float],
                     smoothings: list[float] | None = None) -> tuple[Cubic, ...]:
    """m3shapes RoundedPolygon including constrained circular corner smoothing."""
    count = len(vertices)
    smoothings = smoothings or [0.0] * count
    corners = []
    for i, vertex in enumerate(vertices):
        before, after = vertices[(i - 1) % count], vertices[(i + 1) % count]
        d1, d2 = _unit(_sub(before, vertex)), _unit(_sub(after, vertex))
        cosine = max(-1.0, min(1.0, _dot(d1, d2)))
        sine = math.sqrt(max(0.0, 1 - cosine * cosine))
        expected = radii[i] * (cosine + 1) / sine if sine > 0.001 else 0
        corners.append((vertex, d1, d2, expected))
    ratios = []
    for i in range(count):
        expected_round = corners[i][3] + corners[(i + 1) % count][3]
        expected_full = (corners[i][3] * (1 + smoothings[i])
                         + corners[(i + 1) % count][3] * (1 + smoothings[(i + 1) % count]))
        length = math.dist(vertices[i], vertices[(i + 1) % count])
        if expected_round > length:
            ratios.append((length / expected_round, 0.0))
        elif expected_full > length:
            ratios.append((1.0, (length - expected_round) / (expected_full - expected_round)))
        else:
            ratios.append((1.0, 1.0))
    rounded_corners = []
    for i, (vertex, d1, d2, expected) in enumerate(corners):
        smoothing = smoothings[i]
        full_expected = expected * (1 + smoothing)
        allowed = [expected * ratios[index][0] + (full_expected - expected) * ratios[index][1]
                   for index in ((i - 1) % count, i)]
        cut = min(min(allowed), expected)
        if expected < 1e-4 or cut < 1e-4 or radii[i] < 1e-4:
            rounded_corners.append([_line(vertex, vertex)])
            continue
        radius = radii[i] * cut / expected
        center = _add(vertex, _mul(_unit(_add(d1, d2)), math.hypot(radius, cut)))
        start, end = _add(vertex, _mul(d1, cut)), _add(vertex, _mul(d2, cut))
        def actual_smoothing(allowed_cut):
            if allowed_cut > full_expected:
                return smoothing
            if allowed_cut > expected:
                return smoothing * (allowed_cut - expected) / (full_expected - expected)
            return 0.0
        flank0 = _flanking_curve(cut, actual_smoothing(allowed[0]), vertex,
                                  vertices[(i - 1) % count], start, end, center, radius)
        flank2 = _reverse(_flanking_curve(cut, actual_smoothing(allowed[1]), vertex,
                                          vertices[(i + 1) % count], end, start, center, radius))
        rounded_corners.append([flank0, _arc(center, flank0[3], flank2[0]), flank2])
    # m3shapes starts at the midpoint of the first rounded corner.
    # Retain its split before computing its approximate control-point bounds.
    prefix = []
    if len(rounded_corners[0]) == 3:
        first, second = _split(rounded_corners[0][1])
        prefix = [rounded_corners[0][0], first]
        sequence = [second, rounded_corners[0][2]]
    else:
        sequence = list(rounded_corners[0])
    for i in range(count):
        sequence.append(_line(rounded_corners[i][-1][3], rounded_corners[(i + 1) % count][0][0]))
        if i + 1 < count:
            sequence.extend(rounded_corners[i + 1])
    sequence.extend(prefix)
    cubics = []
    for cubic in sequence:
        # Upstream skips degenerate flanks/edges and snaps their final anchor.
        if abs(cubic[0][0] - cubic[3][0]) >= 1e-4 or abs(cubic[0][1] - cubic[3][1]) >= 1e-4:
            cubics.append(cubic)
        elif cubics:
            cubics[-1] = (*cubics[-1][:3], cubic[3])
    cubics[-1] = (*cubics[-1][:3], cubics[0][0])
    return _normalize(cubics)


def _custom_polygon(points: list[tuple[float, ...]], repetitions: int = 1,
                    mirroring: bool = False) -> tuple[Cubic, ...]:
    """Upstream MaterialShapes::doRepeat, including its mirrored seam rule."""
    definitions = [(p[0], p[1], p[2] if len(p) > 2 else 0,
                    p[3] if len(p) > 3 else 0) for p in points]
    vertices, radii, smoothings = [], [], []
    if mirroring:
        angles = [math.atan2(p[1] - 0.5, p[0] - 0.5) for p in definitions]
        distances = [math.hypot(p[0] - 0.5, p[1] - 0.5) for p in definitions]
        section = math.tau / (repetitions * 2)
        for rep in range(repetitions * 2):
            for index in range(len(points)):
                i = index if rep % 2 == 0 else len(points) - 1 - index
                if i == 0 and rep % 2:
                    continue
                angle = (section * rep + angles[i] if rep % 2 == 0 else
                         section * rep + section - angles[i] + 2 * angles[0])
                vertices.append((math.cos(angle) * distances[i] + 0.5,
                                 math.sin(angle) * distances[i] + 0.5))
                radii.append(definitions[i][2])
                smoothings.append(definitions[i][3])
    else:
        for rep in range(repetitions):
            angle = math.tau / repetitions * rep
            for x, y, radius, smoothing in definitions:
                x, y = x - 0.5, y - 0.5
                vertices.append((x * math.cos(angle) - y * math.sin(angle) + 0.5,
                                 x * math.sin(angle) + y * math.cos(angle) + 0.5))
                radii.append(radius)
                smoothings.append(smoothing)
    return _rounded_polygon(vertices, radii, smoothings)


@lru_cache(maxsize=32)
def shape_cubics(name: str = "cookie9") -> tuple[Cubic, ...]:
    """Normalized clockwise cubic path, fitting a unit square, as upstream."""
    if name == "cookie4":
        vertices, radii = [], []
        for i in range(4):
            angle = i * math.pi / 2
            for x, y, radius in ((1.237, 1.236, 0.258), (0.5, 0.918, 0.233)):
                x, y = x - 0.5, y - 0.5
                vertices.append((x * math.cos(angle) - y * math.sin(angle),
                                 x * math.sin(angle) + y * math.cos(angle)))
                radii.append(radius)
        return _rounded_polygon(vertices, radii)
    custom = {
        "cookie6": ([(0.723, 0.884, 0.394), (0.5, 1.099, 0.398)], 6, False),
        "verySunny": ([(0.5, 1.080, 0.085), (0.358, 0.843, 0.085)], 8, False),
        "softBurst": ([(0.193, 0.277, 0.053), (0.176, 0.055, 0.053)], 10, False),
        "pentagon": ([(0.5, -0.009, 0.172), (1.030, 0.365, 0.164), (0.828, 0.970, 0.169)], 1, True),
        "gem": ([(0.499, 1.023, 0.241, 0.778), (-0.005, 0.792, 0.208),
                 (0.073, 0.258, 0.228), (0.433, 0, 0.491)], 1, True),
        "arrow": ([(0.5, 0.892, 0.313), (-0.216, 1.050, 0.207),
                   (0.499, -0.160, 0.215, 1), (1.225, 1.060, 0.211)], 1, False),
        "pill": ([(0.961, 0.039, 0.426), (1.001, 0.428), (1.000, 0.609, 1)], 2, True),
        "fan": ([(1.004, 1.000, 0.148, 0.417), (0, 1, 0.151),
                 (0, -0.003, 0.148), (0.978, 0.020, 0.803)], 1, False),
    }
    if name in custom:
        return _custom_polygon(*custom[name])
    if name in ("circle", "oval"):
        sides = 10 if name == "circle" else 8
        radius = 1 / math.cos(math.pi / sides)
        vertices = [(radius * math.cos(i * math.tau / sides),
                     radius * math.sin(i * math.tau / sides)) for i in range(sides)]
        cubics = _rounded_polygon(vertices, [1] * sides)
        return cubics if name == "circle" else _transformed(cubics, -45, 0.64)
    if name in ("arch", "triangle"):
        sides = 4 if name == "arch" else 3
        vertices = [(math.cos(i * math.tau / sides), math.sin(i * math.tau / sides))
                    for i in range(sides)]
        radii = [1, 1, 0.2, 0.2] if name == "arch" else [0.2] * sides
        return _transformed(_rounded_polygon(vertices, radii), -135 if name == "arch" else -90)
    sides, inner, rounding = {
        "cookie9": (9, 0.8, 0.5),
        "cookie12": (12, 0.8, 0.5),
        "sunny": (8, 0.8, 0.15),
        "cookie7": (7, 0.75, 0.5),
    }[name]
    angle_offset = -math.pi / 2 if name != "sunny" else 0.0
    vertices = [((1.0 if i % 2 == 0 else inner) * math.cos(i * math.pi / sides + angle_offset),
                 (1.0 if i % 2 == 0 else inner) * math.sin(i * math.pi / sides + angle_offset))
                for i in range(sides * 2)]
    return _rounded_polygon(vertices, [rounding] * len(vertices))


def svg_path(name: str = "cookie9", size: float = 1000.0) -> str:
    """SVG path suitable for QtQuick.Shapes.PathSvg; it uses cubic curves."""
    cubics = shape_cubics(name)
    start = cubics[0][0]
    sections = [f"M {start[0] * size:.6f} {start[1] * size:.6f}"]
    for _, control0, control1, end in cubics:
        sections.append("C " + " ".join(f"{v * size:.6f}" for p in (control0, control1, end) for v in p))
    return " ".join(sections) + " Z"


def svg_data_url(name: str = "cookie9", fill: str = "white", size: int = 1000) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
           f'viewBox="0 0 {size} {size}"><path fill="{fill}" d="{svg_path(name, size)}"/></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@lru_cache(maxsize=16)
def radial_samples(name: str = "cookie9", count: int = 720) -> tuple[float, ...]:
    """Distance from item center to outer path, clockwise from +X, in unit size.

    Query a rotated cookie using angle=(screenAngle - rotation) modulo 360.
    Multiply by artwork size, then add visualizer spacing and half stroke width.
    This is the same ray/flattened-edge method as MaterialShape.distanceAtAngle.
    """
    points = [_point(cubic, i / 32) for cubic in shape_cubics(name) for i in range(32)]
    points.append(points[0])
    samples = []
    for index in range(count):
        angle = index * math.tau / count
        dx, dy = math.cos(angle), math.sin(angle)
        best = 0.0
        for a, b in zip(points, points[1:]):
            ex, ey = b[0] - a[0], b[1] - a[1]
            denominator = ex * dy - ey * dx
            if abs(denominator) < 1e-12:
                continue
            rx, ry = a[0] - 0.5, a[1] - 0.5
            distance = (ex * ry - ey * rx) / denominator
            edge_fraction = (dx * ry - dy * rx) / denominator
            if distance >= 0 and 0 <= edge_fraction <= 1:
                best = max(best, distance)
        samples.append(best)
    return tuple(samples)


def shape_payload(name: str = "cookie9", count: int = 720) -> dict:
    """Small bridge payload root can expose through a QVariantMap."""
    return {"path": svg_path(name), "mask": svg_data_url(name),
            "radii": list(radial_samples(name, count)), "pathSize": 1000,
            "sampleCount": count}


def cookie_geometry(size: float = 200, samples: int = 720, name: str = "cookie9") -> dict:
    """Root application bridge: absolute SVG coordinates, normalized radii."""
    return {"path": svg_path(name, size), "mask": svg_data_url(name, size=round(size)),
            "radii": list(radial_samples(name, samples)), "size": size,
            "sampleCount": samples}


BACKGROUND_SHAPE_NAMES = ("circle", "cookie4", "cookie6", "cookie7", "cookie9", "cookie12",
                          "sunny", "verySunny", "softBurst", "pentagon", "gem", "arch",
                          "arrow", "pill", "triangle", "fan", "oval")


def background_shapes(size: float = 200) -> list[str]:
    """Exact 17-entry BackgroundShapes.qml pool, as absolute SVG path strings."""
    return [svg_path(name, size) for name in BACKGROUND_SHAPE_NAMES]


if __name__ == "__main__":
    for shape in ("cookie9", "cookie12", "cookie4", "sunny"):
        distances = radial_samples(shape)
        assert min(distances) > 0.2
        assert max(distances) <= math.sqrt(0.5) + 1e-6
        assert math.dist(shape_cubics(shape)[0][0], shape_cubics(shape)[-1][3]) < 1e-8
        print(shape, "cubics", len(shape_cubics(shape)), "radial range", min(distances), max(distances))
    for name in BACKGROUND_SHAPE_NAMES:
        cubics = shape_cubics(name)
        assert len(cubics) >= 3, name
        assert all(math.isfinite(value) and -1e-8 <= value <= 1 + 1e-8
                   for cubic in cubics for point in cubic for value in point), name
        for first, second in zip(cubics, cubics[1:] + cubics[:1]):
            assert math.dist(first[3], second[0]) < 1e-7, (name, first[3], second[0])
        print("background", name, "closed cubics", len(cubics))
    assert len(background_shapes()) == 17
