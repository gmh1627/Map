"""Validate exact shared segments between web-map fills and admin lines."""

from __future__ import annotations

import json
import math
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
DATA = ROOT / "web" / "data"


def read(name: str) -> dict:
    return json.loads((DATA / f"{name}.geojson").read_text(encoding="utf-8"))


def paths(geometry: dict) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "LineString":
        return [coordinates]
    if kind == "MultiLineString":
        return coordinates
    if kind == "Polygon":
        return coordinates
    if kind == "MultiPolygon":
        return [ring for polygon in coordinates for ring in polygon]
    if kind == "GeometryCollection":
        return [path for part in geometry.get("geometries", []) for path in paths(part)]
    return []


def point_key(point: list[float]) -> tuple[float, float]:
    return round(point[0], 6), round(point[1], 6)


def segment_key(start: list[float], end: list[float]) -> tuple:
    return tuple(sorted((point_key(start), point_key(end))))


def segment_set(collection: dict) -> set[tuple]:
    result = set()
    for feature in collection.get("features", []):
        for path in paths(feature.get("geometry", {})):
            result.update(segment_key(start, end) for start, end in zip(path, path[1:]))
    return result


def boundary_report(collection: dict, admin_segments: set[tuple]) -> dict:
    total_segments = 0
    missing_segments = 0
    total_length = 0.0
    missing_length = 0.0
    for feature in collection.get("features", []):
        for path in paths(feature.get("geometry", {})):
            for start, end in zip(path, path[1:]):
                length = math.hypot(end[0] - start[0], end[1] - start[1])
                if length <= 1e-12:
                    continue
                total_segments += 1
                total_length += length
                if segment_key(start, end) not in admin_segments:
                    missing_segments += 1
                    missing_length += length
    return {
        "features": len(collection.get("features", [])),
        "segments": total_segments,
        "missing_segments": missing_segments,
        "missing_length_degrees": missing_length,
        "missing_length_ratio": missing_length / total_length if total_length else 0.0,
    }


def main() -> int:
    admin_segments = segment_set(read("city_boundaries"))
    admin_segments.update(segment_set(read("province_boundaries")))
    report = {
        "admin_segments": len(admin_segments),
        "provinces": boundary_report(read("provinces"), admin_segments),
        "rail_visited_cities": boundary_report(
            read("rail_visited_cities"), admin_segments
        ),
        "other_visited_cities": boundary_report(
            read("other_visited_cities"), admin_segments
        ),
    }
    errors = [
        name
        for name, result in report.items()
        if isinstance(result, dict) and result["missing_segments"]
    ]
    report["errors"] = errors
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
