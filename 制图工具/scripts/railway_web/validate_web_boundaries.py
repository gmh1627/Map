"""Validate the explicit web-map boundary layers and polygon fill layers."""

from __future__ import annotations

import json
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


def geometry_report(collection: dict, expected_kind: str) -> dict:
    features = collection.get("features", [])
    kinds = {}
    segments = 0
    for feature in features:
        kind = feature.get("geometry", {}).get("type", "null")
        kinds[kind] = kinds.get(kind, 0) + 1
        if expected_kind == "line":
            for path in paths(feature.get("geometry", {})):
                segments += sum(1 for start, end in zip(path, path[1:]) if start != end)
    return {
        "features": len(features),
        "geometry_types": kinds,
        "segments": segments if expected_kind == "line" else None,
    }


def main() -> int:
    report = {
        "province_boundaries": geometry_report(read("province_boundaries"), "line"),
        "city_boundaries": geometry_report(read("city_boundaries"), "line"),
        "provinces": geometry_report(read("provinces"), "polygon"),
        "rail_visited_cities": geometry_report(read("rail_visited_cities"), "polygon"),
        "other_visited_cities": geometry_report(read("other_visited_cities"), "polygon"),
    }
    errors = [
        name
        for name in ("province_boundaries", "city_boundaries")
        if report[name]["features"] == 0 or report[name]["segments"] == 0
    ]
    report["errors"] = errors
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
