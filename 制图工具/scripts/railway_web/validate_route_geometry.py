"""Detect visible hooks and short returns in the published route geometry."""

from __future__ import annotations

import json
import math
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
ROUTES = ROOT / "web" / "data" / "visited_routes.geojson"
INTENTIONAL_REVERSALS = {39}  # G7725 changes direction at Tongling.


def distance_km(first: list[float], second: list[float]) -> float:
    latitude = math.radians((first[1] + second[1]) / 2.0)
    return math.hypot(
        (second[0] - first[0]) * 111.32 * math.cos(latitude),
        (second[1] - first[1]) * 110.57,
    )


def route_paths(geometry: dict) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if kind == "LineString":
        return [coordinates]
    if kind == "MultiLineString":
        return coordinates
    return []


def repeated_vertices(points: list[list[float]]) -> list[dict]:
    seen: dict[tuple[float, float], int] = {}
    repeats = []
    for index, point in enumerate(points):
        key = round(point[0], 6), round(point[1], 6)
        previous = seen.get(key)
        if previous is not None and index - previous > 1:
            repeats.append({"start": previous, "end": index, "point": key})
        seen[key] = index
    return repeats


def short_returns(points: list[list[float]]) -> list[dict]:
    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + distance_km(first, second))
    results = []
    for end in range(2, len(points)):
        for start in range(end - 2, -1, -1):
            span = cumulative[end] - cumulative[start]
            if span > 1.5:
                break
            if span < 0.15:
                continue
            closure = distance_km(points[start], points[end])
            if closure <= 0.12:
                results.append(
                    {
                        "start": start,
                        "end": end,
                        "span_km": round(span, 3),
                        "closure_km": round(closure, 3),
                    }
                )
    return results


def endpoint_reversals(points: list[list[float]]) -> list[dict]:
    results = []
    candidates = list(range(1, min(16, len(points) - 1)))
    candidates += list(range(max(1, len(points) - 16), len(points) - 1))
    for index in sorted(set(candidates)):
        before, point, after = points[index - 1 : index + 2]
        latitude = math.radians((before[1] + point[1] + after[1]) / 3.0)
        incoming = (
            (point[0] - before[0]) * 111.32 * math.cos(latitude),
            (point[1] - before[1]) * 110.57,
        )
        outgoing = (
            (after[0] - point[0]) * 111.32 * math.cos(latitude),
            (after[1] - point[1]) * 110.57,
        )
        incoming_length = math.hypot(*incoming)
        outgoing_length = math.hypot(*outgoing)
        if incoming_length < 0.015 or outgoing_length < 0.015:
            continue
        cosine = (
            incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        ) / (incoming_length * outgoing_length)
        if cosine < -0.35:
            results.append(
                {
                    "index": index,
                    "turn_cosine": round(cosine, 3),
                    "incoming_km": round(incoming_length, 3),
                    "outgoing_km": round(outgoing_length, 3),
                }
            )
    return results


def main() -> int:
    collection = json.loads(ROUTES.read_text(encoding="utf-8"))
    findings = []
    for feature in collection.get("features", []):
        properties = feature.get("properties", {})
        seq = int(properties.get("seq", 0))
        paths = route_paths(feature.get("geometry", {}))
        item = {
            "seq": seq,
            "train": properties.get("train"),
            "origin": properties.get("origin"),
            "destination": properties.get("destination"),
        }
        if len(paths) != 1:
            item["parts"] = len(paths)
        if seq not in INTENTIONAL_REVERSALS:
            points = paths[0] if paths else []
            repeats = repeated_vertices(points)
            returns = short_returns(points)
            reversals = endpoint_reversals(points)
            if repeats:
                item["repeated_vertices"] = repeats
            if returns:
                item["short_returns"] = returns
            if reversals:
                item["endpoint_reversals"] = reversals
        if len(item) > 4:
            findings.append(item)

    report = {
        "route_count": len(collection.get("features", [])),
        "intentional_reversal_sequences": sorted(INTENTIONAL_REVERSALS),
        "findings": findings,
        "errors": [] if not findings else ["route geometry findings remain"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
