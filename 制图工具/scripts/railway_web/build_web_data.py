"""Export compact GeoJSON layers for the interactive railway map."""

from __future__ import annotations

import json
import re
from pathlib import Path

from qgis.core import QgsApplication, QgsFeature, QgsGeometry, QgsVectorLayer, QgsWkbTypes


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
WEB = ROOT / "web"
DATA = WEB / "data"
SOURCE = ROOT / "制图工具" / "数据源" / "GeoPackage" / "travel_map_home2_min_gan.gpkg"
NATIONAL = ROOT / "地图输出" / "全国专题图" / "全国足迹" / "全国足迹_数据.gpkg"
ROUTES = ROOT / "地图输出" / "全国专题图" / "全国足迹" / "铁路轨迹.gpkg"
ROUTE_TIMES = DATA / "route_times.json"


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def geometry_json(geometry: QgsGeometry) -> dict:
    return json.loads(geometry.asJson(6))


def export_layer(path: Path, layer_name: str, output: Path, properties: list[str] | None = None, simplify: float = 0.0) -> int:
    layer = QgsVectorLayer(f"{path.as_posix()}|layername={layer_name}", layer_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid layer: {path} / {layer_name}")
    fields = properties or [field.name() for field in layer.fields()]
    result = []
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            continue
        if simplify:
            geometry = geometry.simplify(simplify)
        props = {name: feature[name] for name in fields if name in layer.fields().names()}
        result.append({"type": "Feature", "properties": props, "geometry": geometry_json(geometry)})
    output.write_text(json.dumps(feature_collection(result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(result)


def speed_class(tags: str) -> tuple[str, int | None]:
    values = []
    for key in ("design_speed", "designed_speed", "maxspeed"):
        match = re.search(rf'"{key}"=>"([0-9]+)', tags or "")
        if match:
            values.append(int(match.group(1)))
    speed = max(values) if values else None
    if speed is None:
        return "unknown", None
    if speed >= 300:
        return "300+", speed
    if speed >= 250:
        return "250-299", speed
    if speed >= 200:
        return "200-249", speed
    if speed >= 160:
        return "160-199", speed
    if speed >= 120:
        return "120-159", speed
    return "0-119", speed


def export_rail_network(output: Path) -> int:
    layer = QgsVectorLayer(f"{SOURCE.as_posix()}|layername=china_railwayosm__lines", "railway", "ogr")
    if not layer.isValid():
        raise RuntimeError("Invalid railway source layer")
    grouped: dict[str, list[QgsGeometry]] = {}
    speed_values: dict[str, list[int]] = {}
    count = 0
    for feature in layer.getFeatures():
        if str(feature["railway"] or "") not in {"rail", "light_rail", "subway"}:
            continue
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            continue
        klass, speed = speed_class(str(feature["other_tags"] or ""))
        grouped.setdefault(klass, []).append(geometry.simplify(0.0025))
        if speed is not None:
            speed_values.setdefault(klass, []).append(speed)
        count += 1
    features = []
    for klass in sorted(grouped):
        # A small number of MultiLineString features is much faster to draw
        # than hundreds of thousands of individual OSM segments.
        merged = QgsGeometry.collectGeometry(grouped[klass])
        values = speed_values.get(klass, [])
        features.append({
            "type": "Feature",
            "properties": {"speed_class": klass, "min_speed": min(values) if values else None, "max_speed": max(values) if values else None, "segments": len(grouped[klass])},
            "geometry": geometry_json(merged),
        })
    output.write_text(json.dumps(feature_collection(features), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return count


def export_station_layer(output: Path) -> int:
    station_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=记录车站", "stations", "ogr")
    route_layer = QgsVectorLayer(f"{ROUTES.as_posix()}|layername=rail_routes", "routes", "ogr")
    service_by_station: dict[str, set[str]] = {}
    for feature in route_layer.getFeatures():
        service = str(feature["service"] or "")
        for field in ("origin", "destination"):
            name = str(feature[field] or "")
            service_by_station.setdefault(name, set()).add(service)
    features = []
    for feature in station_layer.getFeatures():
        name = str(feature["name"] or "")
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            continue
        features.append({
            "type": "Feature",
            "properties": {"name": name, "trips": feature["trips"], "services": ",".join(sorted(service_by_station.get(name, set())))},
            "geometry": geometry_json(geometry),
        })
    output.write_text(json.dumps(feature_collection(features), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(features)


def export_network_stations(output: Path) -> int:
    layer = QgsVectorLayer(f"{SOURCE.as_posix()}|layername=china_railwayosm__points", "network stations", "ogr")
    if not layer.isValid():
        raise RuntimeError("Invalid railway station source layer")
    result = []
    seen = set()
    for feature in layer.getFeatures():
        name = str(feature["name"] or "")
        tags = str(feature["other_tags"] or "")
        if not name or name in seen or '"railway"=>"station"' not in tags or '"train"=>"yes"' not in tags:
            continue
        geometry = feature.geometry()
        if geometry.isNull() or geometry.isEmpty():
            continue
        seen.add(name)
        result.append({"type": "Feature", "properties": {"name": name}, "geometry": geometry_json(geometry)})
    output.write_text(json.dumps(feature_collection(result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(result)


def province_code(feature: QgsFeature) -> int | None:
    level = str(feature["level"] or "")
    parent = feature["parent"] if "parent" in feature.fields().names() else None
    parent_code = parent.get("adcode") if isinstance(parent, dict) else None
    if level == "district" and parent_code in {110000, 120000, 310000, 500000}:
        return int(parent_code)
    if level != "city":
        return None
    routes = feature["acroutes"] if "acroutes" in feature.fields().names() else None
    value = routes[1] if isinstance(routes, list) and len(routes) > 1 else parent_code
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(feature["adcode"]) // 10000 * 10000
        except (TypeError, ValueError):
            return None


def polygon_boundary(geometry: QgsGeometry) -> QgsGeometry:
    polygons = geometry.asMultiPolygon() if geometry.isMultipart() else [geometry.asPolygon()]
    rings = [ring for polygon in polygons for ring in polygon if ring]
    result = QgsGeometry.fromMultiPolylineXY(rings)
    result.convertToMultiType()
    return result


def export_unified_admin_boundaries() -> tuple[int, int]:
    """Match the proven regional-map boundary construction method."""
    cities = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=全国地级行政区", "cities", "ogr")
    provinces = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=全国省级行政区", "provinces", "ogr")
    if not cities.isValid() or not provinces.isValid():
        raise RuntimeError("Invalid nationwide administrative layers")
    province_lines = [polygon_boundary(feature.geometry()) for feature in provinces.getFeatures()]
    province_geometry = QgsGeometry.unaryUnion(province_lines)
    segment_records = {}
    for feature in cities.getFeatures():
        code = province_code(feature)
        if code is None:
            continue
        polygons = feature.geometry().asMultiPolygon() if feature.geometry().isMultipart() else [feature.geometry().asPolygon()]
        for polygon in polygons:
            for ring in polygon:
                for start, end in zip(ring, ring[1:]):
                    first = (round(start.x(), 6), round(start.y(), 6))
                    second = (round(end.x(), 6), round(end.y(), 6))
                    key = tuple(sorted((first, second)))
                    record = segment_records.setdefault(
                        key, {"points": (start, end), "owners": set(), "codes": set()}
                    )
                    record["owners"].add(feature.id())
                    record["codes"].add(code)
    internal_segments = [
        list(record["points"])
        for record in segment_records.values()
        if len(record["owners"]) >= 2 and len(record["codes"]) == 1
    ]
    city_geometry = QgsGeometry.fromMultiPolylineXY(internal_segments).mergeLines()
    city_parts = city_geometry.asMultiPolyline() if city_geometry.isMultipart() else [city_geometry.asPolyline()]
    connected_parts = []
    for part in city_parts:
        if not part:
            continue
        adjusted = list(part)
        for index in (0, -1):
            endpoint = QgsGeometry.fromPointXY(adjusted[index])
            distance = province_geometry.distance(endpoint)
            if 1e-9 < distance < 0.03:
                adjusted[index] = province_geometry.nearestPoint(endpoint).asPoint()
        connected_parts.append(adjusted)
    connected_city_geometry = QgsGeometry.fromMultiPolylineXY(connected_parts)

    (DATA / "province_boundaries.geojson").write_text(
        json.dumps(feature_collection([{"type": "Feature", "properties": {}, "geometry": geometry_json(province_geometry)}]), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (DATA / "city_boundaries.geojson").write_text(
        json.dumps(feature_collection([{"type": "Feature", "properties": {}, "geometry": geometry_json(connected_city_geometry)}]), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return len(province_lines), len(internal_segments)


def export_routes(output: Path) -> int:
    route_layer = QgsVectorLayer(f"{ROUTES.as_posix()}|layername=rail_routes", "routes", "ogr")
    station_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=记录车站", "stations", "ogr")
    city_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=去过的城市", "visited cities", "ogr")
    station_points = {str(feature["name"]): feature.geometry().asPoint() for feature in station_layer.getFeatures()}
    city_features = list(city_layer.getFeatures())
    def city_for_station(name: str) -> str:
        point = station_points.get(name)
        if point is None:
            return ""
        point_geometry = QgsGeometry.fromPointXY(point)
        for feature in city_features:
            if feature.geometry().contains(point_geometry):
                return str(feature["display"])
        return ""
    route_times = json.loads(ROUTE_TIMES.read_text(encoding="utf-8-sig")) if ROUTE_TIMES.exists() else {}
    result = []
    for feature in route_layer.getFeatures():
        # Keep control-station vertices visible in the interactive map while
        # removing only the tiny OSM digitising noise.
        geometry = feature.geometry().simplify(0.0001)
        origin = str(feature["origin"] or "")
        destination = str(feature["destination"] or "")
        extra = route_times.get(str(feature["seq"]), {})
        result.append({"type": "Feature", "properties": {"seq": feature["seq"], "date": extra.get("date", feature["date"]), "origin": origin, "destination": destination, "origin_city": city_for_station(origin), "destination_city": city_for_station(destination), "train": feature["train"], "service": feature["service"], "table_km": feature["table_km"], "time": extra.get("time", ""), "note": extra.get("note", "")}, "geometry": geometry_json(geometry)})
    output.write_text(json.dumps(feature_collection(result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(result)


def export_rail_cities(output: Path, all_visited_path: Path) -> int:
    city_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=去过的城市", "visited cities", "ogr")
    station_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=记录车站", "stations", "ogr")
    route_layer = QgsVectorLayer(f"{ROUTES.as_posix()}|layername=rail_routes", "routes", "ogr")
    endpoint_names = set()
    for feature in route_layer.getFeatures():
        endpoint_names.update(str(feature[field] or "") for field in ("origin", "destination"))
    points = {str(feature["name"]): feature.geometry().asPoint() for feature in station_layer.getFeatures() if str(feature["name"] or "") in endpoint_names}
    city_features = list(city_layer.getFeatures())
    selected = []
    for feature in city_features:
        geometry = feature.geometry()
        if any(geometry.contains(QgsGeometry.fromPointXY(point)) for point in points.values()):
            selected.append(feature)
    result = [{"type": "Feature", "properties": {"display": feature["display"], "province": feature["province"], "rail_arrival": True}, "geometry": geometry_json(feature.geometry())} for feature in selected]
    output.write_text(json.dumps(feature_collection(result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    selected_names = {str(feature["display"]) for feature in selected}
    all_data = json.loads(all_visited_path.read_text(encoding="utf-8"))
    other = [feature for feature in all_data["features"] if str(feature.get("properties", {}).get("display", "")) not in selected_names]
    (DATA / "other_visited_cities.geojson").write_text(json.dumps(feature_collection(other), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    labels_layer = QgsVectorLayer(f"{NATIONAL.as_posix()}|layername=去过的城市标注", "visited city labels", "ogr")
    labels = [feature for feature in labels_layer.getFeatures() if str(feature["display"]) in selected_names]
    label_result = [{"type": "Feature", "properties": {"display": feature["display"], "province": feature["province"]}, "geometry": geometry_json(feature.geometry())} for feature in labels]
    (DATA / "rail_city_labels.geojson").write_text(json.dumps(feature_collection(label_result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    other_label_result = [{"type": "Feature", "properties": {"display": feature["display"], "province": feature["province"]}, "geometry": geometry_json(feature.geometry())} for feature in labels if str(feature["display"]) not in selected_names]
    (DATA / "other_city_labels.geojson").write_text(json.dumps(feature_collection(other_label_result), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(result)


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        rail_segments = export_rail_network(DATA / "railway_network.geojson")
        province_boundary_count, city_boundary_count = export_unified_admin_boundaries()
        export_layer(NATIONAL, "全国省级行政区", DATA / "provinces.geojson", ["name"], 0.01)
        export_layer(NATIONAL, "全国地级行政区", DATA / "cities.geojson", ["name"], 0.008)
        export_layer(NATIONAL, "去过的城市", DATA / "visited_cities.geojson", ["display", "province"], 0.008)
        export_layer(NATIONAL, "去过的城市标注", DATA / "visited_city_labels.geojson", ["display", "province"], 0.0)
        route_count = export_routes(DATA / "visited_routes.geojson")
        station_count = export_station_layer(DATA / "visited_stations.geojson")
        network_station_count = export_network_stations(DATA / "network_stations.geojson")
        rail_city_count = export_rail_cities(DATA / "rail_visited_cities.geojson", DATA / "visited_cities.geojson")
        metadata = {"rail_segments": rail_segments, "route_count": route_count, "station_count": station_count, "network_station_count": network_station_count, "rail_city_count": rail_city_count, "province_boundaries": province_boundary_count, "city_boundaries": city_boundary_count, "source": str(SOURCE), "simplify_degrees": 0.0025}
        (DATA / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metadata, ensure_ascii=False))
        return 0
    finally:
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
