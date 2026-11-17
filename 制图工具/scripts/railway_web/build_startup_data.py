"""Pack exact web geometries into shared, delta-encoded paths and gzip them."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "web/data"
LAYERS = ("province_boundaries", "city_boundaries", "rail_city_labels", "other_city_labels", "visited_routes", "visited_stations")
PRECISION = 1_000_000


def encode(points):
    encoded = []
    previous = (0, 0)
    for point in points:
        for value, last in zip(point, previous):
            delta = value - last
            unsigned = ~(delta << 1) if delta < 0 else delta << 1
            while unsigned >= 32:
                encoded.append(chr((unsigned & 31 | 32) + 63))
                unsigned >>= 5
            encoded.append(chr(unsigned + 63))
        previous = point
    return "".join(encoded)


def build(data_dir=DATA):
    arcs = []
    arc_ids = {}

    def path(points):
        coordinates = [tuple(round(value * PRECISION) for value in point) for point in points]
        if not coordinates:
            return []
        references = []
        start = 0
        ends = [index for index in range(1, len(coordinates)) if index == len(coordinates) - 1 or (coordinates[index][0] * 73856093 ^ coordinates[index][1] * 19349663) & 31 == 0]
        if len(coordinates) == 1:
            ends = [0]
        for end in ends:
            segment = coordinates[start:end + 1]
            forward = encode(segment)
            reverse = encode(reversed(segment))
            key = min(forward, reverse)
            if key not in arc_ids:
                arc_ids[key] = len(arcs)
                arcs.append(key)
            index = arc_ids[key]
            references.append(index if key == forward else ~index)
            start = end
        return references

    def geometry(item):
        kind = item["type"]
        if kind == "GeometryCollection":
            return {**item, "geometries": [geometry(part) for part in item["geometries"]]}
        depths = {"LineString": 0, "MultiLineString": 1, "Polygon": 1, "MultiPolygon": 2}
        if kind not in depths:
            return item
        def nest(coordinates, depth):
            return path(coordinates) if depth == 0 else [nest(part, depth - 1) for part in coordinates]
        result = {key: value for key, value in item.items() if key != "coordinates"}
        result["arcs"] = nest(item["coordinates"], depths[kind])
        return result

    layers = {}
    original_bytes = 0
    for name in LAYERS:
        raw = (data_dir / f"{name}.geojson").read_bytes()
        original_bytes += len(raw)
        collection = json.loads(raw)
        layers[name] = {**collection, "features": [{**feature, "geometry": geometry(feature["geometry"])} for feature in collection["features"]]}
    packed = json.dumps({"format": "rail-map-1", "precision": PRECISION, "arcs": arcs, "layers": layers}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(packed, compresslevel=9, mtime=0)
    (data_dir / "startup.json.gz").write_bytes(compressed)
    web = data_dir.parent
    if (web / "app.js").exists():
        version = hashlib.sha256()
        for asset_path in sorted([*data_dir.glob("*.geojson"), data_dir / "startup.json.gz"]):
            version.update(asset_path.read_bytes())
        app = (web / "app.js").read_text(encoding="utf-8")
        app = re.sub(r'const DATA_VERSION = "[^"]+";', f'const DATA_VERSION = "{version.hexdigest()[:12]}";', app)
        (web / "app.js").write_text(app, encoding="utf-8")
        index = (web / "index.html").read_text(encoding="utf-8")
        index = re.sub(r'app\.js\?v=[^"\s]+', f'app.js?v={hashlib.sha256(app.encode()).hexdigest()[:12]}', index)
        codec = (web / "data-codec.js").read_bytes()
        index = re.sub(r'data-codec\.js\?v=[^"\s]+', f'data-codec.js?v={hashlib.sha256(codec).hexdigest()[:12]}', index)
        routes = layers["visited_routes"]["features"]
        services = {service: [f["properties"] for f in routes if f["properties"]["service"] == service] for service in ("conventional", "highspeed")}
        properties = [f["properties"] for f in routes]
        values = {
            "summaryTrips": len(routes),
            "summaryConventional": len(services["conventional"]),
            "summaryHighspeed": len(services["highspeed"]),
            "summaryDistance": sum(p["table_km"] for p in properties),
            "summaryConventionalKm": sum(p["table_km"] for p in services["conventional"]),
            "summaryHighspeedKm": sum(p["table_km"] for p in services["highspeed"]),
            "summaryCities": len({p[field] for p in properties for field in ("origin_city", "destination_city") if p.get(field)}),
            "summaryStations": len({p[field] for p in properties for field in ("origin", "destination")}),
        }
        for key, value in values.items():
            index = re.sub(rf'(id="{key}">)[^<]*', rf'\g<1>{value:,}', index)
        (web / "index.html").write_text(index, encoding="utf-8")
    report = {"original_bytes": original_bytes, "packed_bytes": len(packed), "download_bytes": len(compressed), "shared_paths": len(arcs)}
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    build()
