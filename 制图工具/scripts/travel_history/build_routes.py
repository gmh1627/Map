"""Route railway records over the local nationwide OSM rail topology.

The graph keeps the physical OSM geometry.  Each edge has two costs so that
high-speed services prefer dedicated passenger lines while conventional
services prefer conventional main lines.  Short connector use remains
possible for both classes.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PARSED = SCRIPT_DIR / "parsed_source.json"
MATCH_REPORT = SCRIPT_DIR / "source_match_report.json"
RAIL_GPKG = Path(
    r"F:\Desktop\Railway\制图工具\数据源\GeoPackage\travel_map_home2_min_gan.gpkg"
)
DEFAULT_OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\全国专题图\全国足迹")
OUTPUT_DIR = DEFAULT_OUTPUT_DIR
OUTPUT_GPKG = OUTPUT_DIR / "铁路轨迹.gpkg"
ROUTE_REPORT = OUTPUT_DIR / "线路构建报告.json"

CRS = QgsCoordinateReferenceSystem("EPSG:4326")
ROUND_DIGITS = 5
NETWORK_MARGIN_DEGREES = 2.0
CONNECTOR_RADIUS_DEGREES = 0.0008
CONNECTOR_NEIGHBORS = 8
CONNECTOR_COST_MULTIPLIER = 8.0
TRACK_CLASS_MISMATCH_MULTIPLIER = 1.7
HIGH_SPEED_KEYWORDS = ("高速", "高铁", "客专", "城际")

# Control stations are used only where a train's actual itinerary differs from
# the weighted shortest route.  Coordinates come from the local OSM station
# layer in travel_map_home2_min_gan.gpkg.
WAYPOINT_COORDS = {
    "庐江西": (117.2124520, 31.2698065),
    "舒城东": (117.0420420, 31.4869977),
    "桐城南": (116.9593385, 30.8752543),
    "铜陵北": (118.0160809, 31.0157065),
    "无为": (117.9639065, 31.3063668),
    "常平": (114.0003801, 22.9871798),
    "樟木头": (114.0626375, 22.9043667),
    "平湖": (114.1195271, 22.6948818),
    "惠州北": (114.3752592, 23.1828713),
    "龙川西": (115.1752934, 24.0804300),
    "博罗": (114.2035591, 23.1436482),
    "罗浮山": (114.0648348, 23.1973150),
    "增城": (113.7944172, 23.2071153),
    "博罗北": (114.5572092, 23.4803874),
    "河源东": (114.7327598, 23.6861322),
    "和平北": (114.9549294, 24.4754863),
    "定南南": (115.0254012, 24.7459848),
    "龙南东": (114.8636481, 24.9079901),
    "广州新塘": (113.6005178, 23.1367538),
    "白沟": (116.0866639, 39.0859629),
    "霸州西": (116.3441688, 39.0923650),
    "固安": (116.3175800, 39.4239600),
    "张家口": (114.8766144, 40.7495180),
    "沙城": (115.5105176, 40.3960155),
    "衡水": (115.6850570, 37.7434930),
    "辛集": (115.2091446, 37.9041796),
    "商丘": (115.6518561, 34.4460585),
    "开封": (114.3490527, 34.7720005),
    "郑州": (113.6536663, 34.7475076),
    "兰考南": (114.8183029, 34.7720247),
    "亳州南": (115.7930907, 33.7962410),
    "句容西": (118.9747075, 31.8347241),
    "溧阳": (119.4976825, 31.3879622),
    "长兴": (119.9706148, 31.0440015),
    "湖州东": (120.1747945, 30.8193093),
    "苏州南": (120.7949403, 31.0655557),
    "江门": (113.0653353, 22.4910006),
    "涿州东": (116.0473897, 39.4586404),
    "保定东": (115.5957278, 38.8634576),
    "保定": (115.4731670, 38.8627726),
    "石家庄": (114.4781291, 38.0095033),
    "邯郸东": (114.5531572, 36.6198074),
    "邯郸": (114.4696555, 36.6012666),
    "武昌": (114.3124643, 30.5307930),
    "岳阳": (113.1140722, 29.3793016),
    "长沙南": (113.0598811, 28.1500782),
    "长沙": (113.0088425, 28.1971531),
    "衡阳东": (112.7044896, 26.8996964),
    "衡阳": (112.6260051, 26.8934986),
    "郴州": (113.0281509, 25.8113224),
    "广州北": (113.1984329, 23.3794468),
    "佛山": (113.0983795, 23.0499845),
    "茂名南": (110.9787499, 21.6019892),
}
ROUTE_WAYPOINTS = {
    8: ["江门"],
    9: ["江门"],
    10: ["江门"],
    11: ["江门"],
    13: ["江门"],
    18: ["江门"],
    19: ["江门"],
    33: ["江门"],
    34: ["商丘", "开封"],
    38: ["兰考南", "亳州南"],
    39: ["无为", "铜陵"],
    42: ["舒城东", "庐江西", "桐城南"],
    44: ["铜陵北", "无为"],
    45: ["江门"],
    47: ["常平", "樟木头", "平湖"],
    51: ["南京南", "句容西", "溧阳", "长兴", "湖州东", "苏州南"],
    65: [
        "龙南东",
        "龙川西",
        "河源东",
        "惠州北",
        "广州新塘",
    ],
    66: ["江门"],
    81: ["衡水", "阜阳", "六安"],
    82: ["六安", "阜阳", "衡水"],
    88: ["白沟", "霸州西", "固安"],
    91: ["衡水", "阜阳", "六安"],
    92: ["商丘", "开封", "郑州"],
    99: ["桂林北"],
    108: ["辛集"],
    113: ["张家口"],
    114: ["衡水", "阜阳", "六安"],
    128: ["六安", "阜阳", "衡水"],
    129: ["沙城"],
    131: ["涿州东", "石家庄", "郑州东", "广州北"],
    132: ["佛山", "茂名南"],
}

# Extra points used only to keep a route on the intended physical railway.
# They do not appear as principal itinerary controls in the route report.
ROUTE_SHAPING_WAYPOINTS = {
    65: [
        "龙南东",
        "龙川西",
        "河源东",
        "惠州北",
        "博罗",
        "罗浮山",
        "增城",
        "广州新塘",
    ],
    131: [
        "涿州东",
        "保定东",
        "石家庄",
        "邯郸东",
        "郑州东",
        "武汉",
        "岳阳东",
        "长沙南",
        "衡阳东",
        "郴州西",
        "韶关",
        "广州北",
    ],
}

# Whole-route network overrides are reserved for services whose physical route
# differs from their statistical class. Mixed routes should use shaping points
# so each section follows its actual railway.
PREFERRED_NETWORK_OVERRIDES: dict[str, str] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--input-json", type=Path, default=PARSED)
    parser.add_argument("--matches-json", type=Path, default=MATCH_REPORT)
    parser.add_argument("--output-gpkg", type=Path)
    parser.add_argument("--report-json", type=Path)
    return parser.parse_args()


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(value)))


def geometry_length_km(points: list[QgsPointXY]) -> float:
    return sum(
        haversine_km((a.x(), a.y()), (b.x(), b.y()))
        for a, b in zip(points, points[1:])
    )


def is_highspeed(name: str, tags: str) -> bool:
    if '"highspeed"=>"no"' in tags:
        return False
    return '"highspeed"=>"yes"' in tags or any(word in name for word in HIGH_SPEED_KEYWORDS)


def service_penalty(tags: str) -> float:
    match = re.search(r'"service"=>"([^"]+)"', tags)
    if not match:
        return 1.0
    return {
        "crossover": 2.0,
        "spur": 2.5,
        "siding": 5.0,
        "yard": 7.0,
    }.get(match.group(1), 3.0)


def feature_polylines(geometry: QgsGeometry) -> list[list[QgsPointXY]]:
    if geometry.isMultipart():
        return [list(line) for line in geometry.asMultiPolyline() if len(line) >= 2]
    line = list(geometry.asPolyline())
    return [line] if len(line) >= 2 else []


def project_onto_polyline(
    points: list[QgsPointXY], target: tuple[float, float]
) -> tuple[float, float, tuple[float, float]]:
    """Return squared degree distance, along-line km, and projected coordinate."""
    tx, ty = target
    best_distance = math.inf
    best_along = 0.0
    best_coordinate = (points[0].x(), points[0].y())
    cumulative_km = 0.0
    for start, end in zip(points, points[1:]):
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        denominator = dx * dx + dy * dy
        fraction = 0.0 if denominator == 0 else max(
            0.0,
            min(1.0, ((tx - start.x()) * dx + (ty - start.y()) * dy) / denominator),
        )
        px = start.x() + fraction * dx
        py = start.y() + fraction * dy
        squared_distance = (tx - px) ** 2 + (ty - py) ** 2
        segment_km = haversine_km((start.x(), start.y()), (end.x(), end.y()))
        if squared_distance < best_distance:
            best_distance = squared_distance
            best_along = cumulative_km + fraction * segment_km
            best_coordinate = (px, py)
        cumulative_km += segment_km
    return best_distance, best_along, best_coordinate


def polyline_substring(
    points: list[QgsPointXY], start_km: float, end_km: float
) -> list[tuple[float, float]]:
    """Extract an exact vertex-preserving substring between two distances."""
    if end_km < start_km:
        start_km, end_km = end_km, start_km
    result: list[tuple[float, float]] = []
    cumulative_km = 0.0
    for start, end in zip(points, points[1:]):
        segment_km = haversine_km((start.x(), start.y()), (end.x(), end.y()))
        segment_start = cumulative_km
        segment_end = cumulative_km + segment_km
        cumulative_km = segment_end
        if segment_km <= 0 or segment_end < start_km or segment_start > end_km:
            continue
        local_start = max(start_km, segment_start)
        local_end = min(end_km, segment_end)
        first_fraction = (local_start - segment_start) / segment_km
        last_fraction = (local_end - segment_start) / segment_km
        first = (
            start.x() + first_fraction * (end.x() - start.x()),
            start.y() + first_fraction * (end.y() - start.y()),
        )
        last = (
            start.x() + last_fraction * (end.x() - start.x()),
            start.y() + last_fraction * (end.y() - start.y()),
        )
        if not result or result[-1] != first:
            result.append(first)
        if result[-1] != last:
            result.append(last)
    return result


def write_routes(features: list[QgsFeature], output_path: Path) -> None:
    layer = QgsVectorLayer("MultiLineString?crs=EPSG:4326", "rail_routes", "memory")
    provider = layer.dataProvider()
    provider.addAttributes(
        [
            QgsField("seq", QVariant.Int),
            QgsField("date", QVariant.String),
            QgsField("origin", QVariant.String),
            QgsField("destination", QVariant.String),
            QgsField("train", QVariant.String),
            QgsField("service", QVariant.String),
            QgsField("table_km", QVariant.Int),
            QgsField("route_km", QVariant.Double),
            QgsField("ratio", QVariant.Double),
            QgsField("edge_count", QVariant.Int),
            QgsField("status", QVariant.String),
        ]
    )
    layer.updateFields()
    provider.addFeatures(features)
    layer.updateExtents()

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "rail_routes"
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if not output_path.exists()
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(output_path), QgsProject.instance().transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to write rail_routes: {message}")


def main() -> int:
    global OUTPUT_DIR, OUTPUT_GPKG, ROUTE_REPORT
    args = parse_args()
    OUTPUT_DIR = args.output_dir.resolve()
    OUTPUT_GPKG = (
        args.output_gpkg.resolve()
        if args.output_gpkg
        else OUTPUT_DIR / "铁路轨迹.gpkg"
    )
    ROUTE_REPORT = (
        args.report_json.resolve()
        if args.report_json
        else OUTPUT_DIR / "线路构建报告.json"
    )
    started = time.monotonic()
    payload = json.loads(args.input_json.resolve().read_text(encoding="utf-8"))
    matches = json.loads(args.matches_json.resolve().read_text(encoding="utf-8"))
    station_matches = matches["station_matches"]
    station_coords = {
        name: (float(value["lon"]), float(value["lat"]))
        for name, value in station_matches.items()
    }
    station_coords.update(WAYPOINT_COORDS)
    min_lon = min(value[0] for value in station_coords.values()) - NETWORK_MARGIN_DEGREES
    min_lat = min(value[1] for value in station_coords.values()) - NETWORK_MARGIN_DEGREES
    max_lon = max(value[0] for value in station_coords.values()) + NETWORK_MARGIN_DEGREES
    max_lat = max(value[1] for value in station_coords.values()) + NETWORK_MARGIN_DEGREES

    app = QgsApplication([], False)
    app.initQgis()
    try:
        rail = QgsVectorLayer(
            f"{RAIL_GPKG.as_posix()}|layername=china_railwayosm__lines",
            "rail_network",
            "ogr",
        )
        if not rail.isValid():
            raise RuntimeError(f"Invalid rail network: {rail.source()}")

        graph = nx.Graph()
        coordinate_to_node: dict[tuple[float, float], int] = {}
        node_coordinates: list[tuple[float, float]] = []
        edge_details: dict[tuple[int, int, str], dict] = {}

        def node_id(point: QgsPointXY) -> int:
            key = (round(point.x(), ROUND_DIGITS), round(point.y(), ROUND_DIGITS))
            existing = coordinate_to_node.get(key)
            if existing is not None:
                return existing
            value = len(node_coordinates)
            coordinate_to_node[key] = value
            node_coordinates.append(key)
            return value

        request = QgsFeatureRequest().setFilterRect(
            QgsRectangle(min_lon, min_lat, max_lon, max_lat)
        )
        feature_count = 0
        for feature in rail.getFeatures(request):
            name = str(feature["name"] or "")
            tags = str(feature["other_tags"] or "")
            highspeed = is_highspeed(name, tags)
            penalty = service_penalty(tags)
            for part_index, points in enumerate(feature_polylines(feature.geometry())):
                start = node_id(points[0])
                end = node_id(points[-1])
                if start == end:
                    continue
                length = geometry_length_km(points)
                if length <= 0:
                    continue
                highspeed_cost = length * penalty * (
                    1.0 if highspeed else TRACK_CLASS_MISMATCH_MULTIPLIER
                )
                conventional_cost = length * penalty * (
                    TRACK_CLASS_MISMATCH_MULTIPLIER if highspeed else 1.0
                )
                if graph.has_edge(start, end):
                    data = graph[start][end]
                    if highspeed_cost < data["highspeed_cost"]:
                        data["highspeed_cost"] = highspeed_cost
                        edge_details[(min(start, end), max(start, end), "highspeed")] = {
                            "fid": feature.id(),
                            "part": part_index,
                            "length_km": length,
                            "track_class": "highspeed" if highspeed else "conventional",
                        }
                    if conventional_cost < data["conventional_cost"]:
                        data["conventional_cost"] = conventional_cost
                        edge_details[(min(start, end), max(start, end), "conventional")] = {
                            "fid": feature.id(),
                            "part": part_index,
                            "length_km": length,
                            "track_class": "highspeed" if highspeed else "conventional",
                        }
                else:
                    graph.add_edge(
                        start,
                        end,
                        highspeed_cost=highspeed_cost,
                        conventional_cost=conventional_cost,
                    )
                    detail = {
                        "fid": feature.id(),
                        "part": part_index,
                        "length_km": length,
                        "track_class": "highspeed" if highspeed else "conventional",
                    }
                    edge_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                    edge_details[(min(start, end), max(start, end), "conventional")] = detail.copy()
                feature_count += 1

        # Locate each recorded station on the nearest physical track, then add
        # exact partial-track edges from that projected point to the way ends.
        # This avoids snapping a station to a way endpoint many kilometres away.
        station_nodes: dict[str, int] = {}
        station_snap_km: dict[str, float] = {}
        placement_groups: dict[tuple[int, int], dict] = {}
        for station_name, station_coordinate in station_coords.items():
            best = None
            for search_radius in (0.02, 0.06, 0.15):
                station_request = QgsFeatureRequest().setFilterRect(
                    QgsRectangle(
                        station_coordinate[0] - search_radius,
                        station_coordinate[1] - search_radius,
                        station_coordinate[0] + search_radius,
                        station_coordinate[1] + search_radius,
                    )
                )
                for feature in rail.getFeatures(station_request):
                    name = str(feature["name"] or "")
                    tags = str(feature["other_tags"] or "")
                    penalty = service_penalty(tags)
                    highspeed = is_highspeed(name, tags)
                    for part_index, points in enumerate(
                        feature_polylines(feature.geometry())
                    ):
                        squared_distance, along_km, projected = project_onto_polyline(
                            points, station_coordinate
                        )
                        # A platform-adjacent siding is acceptable, but prefer a
                        # main track when distances are nearly identical.
                        rank = squared_distance * (1.0 + 0.08 * (penalty - 1.0))
                        if best is None or rank < best["rank"]:
                            best = {
                                "rank": rank,
                                "squared_distance": squared_distance,
                                "fid": feature.id(),
                                "part": part_index,
                                "points": points,
                                "along_km": along_km,
                                "projected": projected,
                                "penalty": penalty,
                                "highspeed": highspeed,
                            }
                if best is not None:
                    break
            if best is None:
                continue
            projected_node = node_id(QgsPointXY(*best["projected"]))
            station_nodes[station_name] = projected_node
            station_snap_km[station_name] = haversine_km(
                station_coordinate, best["projected"]
            )
            group_key = (best["fid"], best["part"])
            group = placement_groups.setdefault(
                group_key,
                {
                    "points": best["points"],
                    "penalty": best["penalty"],
                    "highspeed": best["highspeed"],
                    "placements": [],
                },
            )
            group["placements"].append(
                {
                    "station": station_name,
                    "node": projected_node,
                    "along_km": best["along_km"],
                }
            )

        for group in placement_groups.values():
            points = group["points"]
            total_km = geometry_length_km(points)
            locations = [
                {"node": node_id(points[0]), "along_km": 0.0},
                *sorted(group["placements"], key=lambda item: item["along_km"]),
                {"node": node_id(points[-1]), "along_km": total_km},
            ]
            for left, right in zip(locations, locations[1:]):
                start = int(left["node"])
                end = int(right["node"])
                length = float(right["along_km"] - left["along_km"])
                if start == end or length <= 0:
                    continue
                coordinates = polyline_substring(
                    points, float(left["along_km"]), float(right["along_km"])
                )
                if len(coordinates) < 2:
                    continue
                highspeed_cost = length * group["penalty"] * (
                    1.0 if group["highspeed"] else TRACK_CLASS_MISMATCH_MULTIPLIER
                )
                conventional_cost = length * group["penalty"] * (
                    TRACK_CLASS_MISMATCH_MULTIPLIER if group["highspeed"] else 1.0
                )
                graph.add_edge(
                    start,
                    end,
                    highspeed_cost=highspeed_cost,
                    conventional_cost=conventional_cost,
                )
                detail = {
                    "fid": None,
                    "part": None,
                    "length_km": length,
                    "track_class": (
                        "highspeed" if group["highspeed"] else "conventional"
                    ),
                    "coordinates": coordinates,
                }
                edge_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                edge_details[(min(start, end), max(start, end), "conventional")] = detail.copy()

        # OSM railway ways frequently end on opposite sides of a station throat,
        # or parallel tracks are mapped as separate ways without a shared end
        # vertex.  Join nearby endpoints even when their wider components are
        # already connected elsewhere: skipping those local links can force a
        # short trip to circle through another province.  The connector receives
        # a high cost and route rendering otherwise keeps original OSM geometry.
        node_array = np.arange(len(node_coordinates), dtype=np.int64)
        node_coords_array = np.asarray(node_coordinates)
        tree = cKDTree(node_coords_array)
        distances, neighbors = tree.query(
            node_coords_array,
            k=CONNECTOR_NEIGHBORS,
            distance_upper_bound=CONNECTOR_RADIUS_DEGREES,
            workers=-1,
        )
        connector_count = 0
        for start in range(len(node_coordinates)):
            for distance_degrees, end in zip(distances[start, 1:], neighbors[start, 1:]):
                end = int(end)
                if end >= len(node_coordinates) or not math.isfinite(float(distance_degrees)):
                    continue
                if start >= end or graph.has_edge(start, end):
                    continue
                length = haversine_km(node_coordinates[start], node_coordinates[end])
                if length <= 0:
                    continue
                cost = length * CONNECTOR_COST_MULTIPLIER
                graph.add_edge(
                    start,
                    end,
                    highspeed_cost=cost,
                    conventional_cost=cost,
                )
                detail = {
                    "fid": None,
                    "part": None,
                    "length_km": length,
                    "track_class": "connector",
                    "coordinates": [node_coordinates[start], node_coordinates[end]],
                }
                edge_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                edge_details[(min(start, end), max(start, end), "conventional")] = detail.copy()
                connector_count += 1

        component_node_lists = list(nx.connected_components(graph))
        largest_component_index = max(
            range(len(component_node_lists)), key=lambda index: len(component_node_lists[index])
        )
        component_nodes = component_node_lists[largest_component_index]
        component_by_node = np.full(len(node_coordinates), -1, dtype=np.int32)
        for component_index, nodes in enumerate(component_node_lists):
            component_by_node[np.fromiter(nodes, dtype=np.int64)] = component_index
        station_tree = cKDTree(node_coords_array)
        for name, coordinate in station_coords.items():
            if name in station_nodes:
                continue
            _, position = station_tree.query(np.asarray(coordinate), k=1)
            node = int(node_array[int(position)])
            station_nodes[name] = node
            station_snap_km[name] = haversine_km(coordinate, node_coordinates[node])

        # A station point can be mapped on a platform/service stub that remains
        # separate from the nationwide component.  Attach only components that
        # contain one of our recorded stations, using their closest pair of rail
        # endpoints.  This is far more conservative than globally increasing the
        # topology tolerance.
        main_nodes_array = np.fromiter(component_nodes, dtype=np.int64)
        main_tree = cKDTree(node_coords_array[main_nodes_array])
        station_component_connectors = 0
        station_component_indexes = {
            int(component_by_node[node]) for node in station_nodes.values()
        }
        for component_index in sorted(station_component_indexes):
            if component_index == largest_component_index:
                continue
            local_nodes = np.fromiter(
                component_node_lists[component_index], dtype=np.int64
            )
            local_distances, main_positions = main_tree.query(
                node_coords_array[local_nodes], k=1, workers=-1
            )
            local_position = int(np.argmin(local_distances))
            start = int(local_nodes[local_position])
            end = int(main_nodes_array[int(main_positions[local_position])])
            length = haversine_km(node_coordinates[start], node_coordinates[end])
            cost = length * CONNECTOR_COST_MULTIPLIER
            graph.add_edge(
                start,
                end,
                highspeed_cost=cost,
                conventional_cost=cost,
            )
            detail = {
                "fid": None,
                "part": None,
                "length_km": length,
                "track_class": "connector",
                "coordinates": [node_coordinates[start], node_coordinates[end]],
            }
            edge_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
            edge_details[(min(start, end), max(start, end), "conventional")] = detail.copy()
            connector_count += 1
            station_component_connectors += 1

        feature_cache = {}

        def feature_geometry(detail: dict) -> QgsGeometry:
            fid = detail["fid"]
            part_index = detail["part"]
            if fid is None:
                return QgsGeometry.fromPolylineXY(
                    [QgsPointXY(*coordinate) for coordinate in detail["coordinates"]]
                )
            if fid not in feature_cache:
                feature = next(rail.getFeatures(QgsFeatureRequest(fid)))
                feature_cache[fid] = feature.geometry()
            geometry = feature_cache[fid]
            parts = feature_polylines(geometry)
            return QgsGeometry.fromPolylineXY(parts[part_index])

        route_features = []
        route_report = []
        path_cache = {}
        dense_path_cache = {}

        def dense_section_details(
            start_name: str, end_name: str, preferred: str
        ) -> list[dict]:
            cache_key = (start_name, end_name, preferred)
            reverse_key = (end_name, start_name, preferred)
            if cache_key in dense_path_cache:
                return dense_path_cache[cache_key]
            if reverse_key in dense_path_cache:
                return list(reversed(dense_path_cache[reverse_key]))

            start_coordinate = station_coords[start_name]
            end_coordinate = station_coords[end_name]
            span = max(
                abs(start_coordinate[0] - end_coordinate[0]),
                abs(start_coordinate[1] - end_coordinate[1]),
            )
            margin = max(0.10, min(0.45, span * 0.14))
            request = QgsFeatureRequest().setFilterRect(
                QgsRectangle(
                    min(start_coordinate[0], end_coordinate[0]) - margin,
                    min(start_coordinate[1], end_coordinate[1]) - margin,
                    max(start_coordinate[0], end_coordinate[0]) + margin,
                    max(start_coordinate[1], end_coordinate[1]) + margin,
                )
            )
            local_graph = nx.Graph()
            local_coordinates: list[tuple[float, float]] = []
            local_coordinate_to_node: dict[tuple[float, float], int] = {}
            local_details: dict[tuple[int, int, str], dict] = {}

            def local_node(point: QgsPointXY) -> int:
                key = (round(point.x(), 6), round(point.y(), 6))
                if key in local_coordinate_to_node:
                    return local_coordinate_to_node[key]
                node = len(local_coordinates)
                local_coordinate_to_node[key] = node
                local_coordinates.append(key)
                return node

            for feature in rail.getFeatures(request):
                name = str(feature["name"] or "")
                tags = str(feature["other_tags"] or "")
                highspeed = is_highspeed(name, tags)
                penalty = service_penalty(tags)
                for points in feature_polylines(feature.geometry()):
                    for first, second in zip(points, points[1:]):
                        start = local_node(first)
                        end = local_node(second)
                        if start == end:
                            continue
                        length = haversine_km(
                            local_coordinates[start], local_coordinates[end]
                        )
                        if length <= 0:
                            continue
                        highspeed_cost = length * penalty * (
                            1.0 if highspeed else TRACK_CLASS_MISMATCH_MULTIPLIER
                        )
                        conventional_cost = length * penalty * (
                            TRACK_CLASS_MISMATCH_MULTIPLIER if highspeed else 1.0
                        )
                        detail = {
                            "fid": None,
                            "part": None,
                            "length_km": length,
                            "track_class": "highspeed" if highspeed else "conventional",
                            "coordinates": [
                                local_coordinates[start],
                                local_coordinates[end],
                            ],
                        }
                        if not local_graph.has_edge(start, end):
                            local_graph.add_edge(
                                start,
                                end,
                                highspeed_cost=highspeed_cost,
                                conventional_cost=conventional_cost,
                            )
                            local_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                            local_details[(min(start, end), max(start, end), "conventional")] = detail.copy()
                        else:
                            edge = local_graph[start][end]
                            if highspeed_cost < edge["highspeed_cost"]:
                                edge["highspeed_cost"] = highspeed_cost
                                local_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                            if conventional_cost < edge["conventional_cost"]:
                                edge["conventional_cost"] = conventional_cost
                                local_details[(min(start, end), max(start, end), "conventional")] = detail.copy()

            coordinates_array = np.asarray(local_coordinates)
            local_tree = cKDTree(coordinates_array)
            _, start_position = local_tree.query(np.asarray(start_coordinate), k=1)
            _, end_position = local_tree.query(np.asarray(end_coordinate), k=1)
            route_start = int(start_position)
            route_end = int(end_position)
            path = None
            for connector_radius in (0.00015, 0.0004, 0.0010, 0.0030):
                distances, neighbors = local_tree.query(
                    coordinates_array,
                    k=6,
                    distance_upper_bound=connector_radius,
                    workers=-1,
                )
                for start in range(len(local_coordinates)):
                    for distance_degrees, end in zip(
                        distances[start, 1:], neighbors[start, 1:]
                    ):
                        end = int(end)
                        if (
                            end >= len(local_coordinates)
                            or not math.isfinite(float(distance_degrees))
                            or start >= end
                            or local_graph.has_edge(start, end)
                        ):
                            continue
                        length = haversine_km(
                            local_coordinates[start], local_coordinates[end]
                        )
                        cost = length * CONNECTOR_COST_MULTIPLIER
                        local_graph.add_edge(
                            start,
                            end,
                            highspeed_cost=cost,
                            conventional_cost=cost,
                        )
                        detail = {
                            "fid": None,
                            "part": None,
                            "length_km": length,
                            "track_class": "connector",
                            "coordinates": [
                                local_coordinates[start],
                                local_coordinates[end],
                            ],
                        }
                        local_details[(min(start, end), max(start, end), "highspeed")] = detail.copy()
                        local_details[(min(start, end), max(start, end), "conventional")] = detail.copy()
                try:
                    path = nx.shortest_path(
                        local_graph,
                        route_start,
                        route_end,
                        weight=f"{preferred}_cost",
                    )
                    break
                except nx.NetworkXNoPath:
                    continue
            if path is None:
                global_path = corridor_path(
                    station_nodes[start_name], station_nodes[end_name], preferred
                )
                details = [
                    edge_details[(min(start, end), max(start, end), preferred)]
                    for start, end in zip(global_path, global_path[1:])
                ]
                dense_path_cache[cache_key] = details
                return details
            details = [
                local_details[(min(start, end), max(start, end), preferred)]
                for start, end in zip(path, path[1:])
            ]
            dense_path_cache[cache_key] = details
            return details

        def corridor_path(start_node: int, end_node: int, preferred: str) -> list[int]:
            start_coordinate = node_coordinates[start_node]
            end_coordinate = node_coordinates[end_node]
            span = max(
                abs(start_coordinate[0] - end_coordinate[0]),
                abs(start_coordinate[1] - end_coordinate[1]),
            )
            base_margin = max(0.12, min(0.65, span * 0.18))
            for factor in (1.0, 2.0, 4.0):
                margin = base_margin * factor
                min_x = min(start_coordinate[0], end_coordinate[0]) - margin
                max_x = max(start_coordinate[0], end_coordinate[0]) + margin
                min_y = min(start_coordinate[1], end_coordinate[1]) - margin
                max_y = max(start_coordinate[1], end_coordinate[1]) + margin
                view = nx.subgraph_view(
                    graph,
                    filter_node=lambda node, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y: (
                        min_x <= node_coordinates[node][0] <= max_x
                        and min_y <= node_coordinates[node][1] <= max_y
                    ),
                )
                try:
                    return nx.shortest_path(
                        view,
                        start_node,
                        end_node,
                        weight=f"{preferred}_cost",
                    )
                except nx.NetworkXNoPath:
                    continue
            return nx.shortest_path(
                graph,
                start_node,
                end_node,
                weight=f"{preferred}_cost",
            )

        for record in payload["rail_records"]:
            service_class = record["service_class"]
            if service_class not in {"highspeed", "conventional"}:
                raise RuntimeError(
                    f"Unsupported service class for route {record['seq']}: "
                    f"{service_class}"
                )
            preferred_network = PREFERRED_NETWORK_OVERRIDES.get(
                record["train"], service_class
            )
            reported_waypoints = record.get(
                "control_points", ROUTE_WAYPOINTS.get(record["seq"], [])
            )
            shaping_waypoints = record.get(
                "shaping_points", reported_waypoints
            )
            reported_control_names = [
                record["origin"],
                *reported_waypoints,
                record["destination"],
            ]
            control_names = [
                record["origin"],
                *record.get(
                    "shaping_points",
                    ROUTE_SHAPING_WAYPOINTS.get(record["seq"], shaping_waypoints),
                ),
                record["destination"],
            ]
            details = []
            if reported_waypoints:
                for control_start, control_end in zip(control_names, control_names[1:]):
                    details.extend(
                        dense_section_details(
                            control_start, control_end, preferred_network
                        )
                    )
            else:
                path = []
                for control_start, control_end in zip(control_names, control_names[1:]):
                    start_node = station_nodes[control_start]
                    end_node = station_nodes[control_end]
                    cache_key = (start_node, end_node, preferred_network)
                    reverse_key = (end_node, start_node, preferred_network)
                    if cache_key in path_cache:
                        section = path_cache[cache_key]
                    elif reverse_key in path_cache:
                        section = list(reversed(path_cache[reverse_key]))
                    else:
                        section = nx.shortest_path(
                            graph,
                            start_node,
                            end_node,
                            weight=f"{preferred_network}_cost",
                        )
                        path_cache[cache_key] = section
                    path.extend(section if not path else section[1:])
                details = [
                    edge_details[
                        (min(start, end), max(start, end), preferred_network)
                    ]
                    for start, end in zip(path, path[1:])
                ]

            geometries = [feature_geometry(detail) for detail in details]
            route_km = sum(detail["length_km"] for detail in details)
            ratio = route_km / record["distance_km"] if record["distance_km"] else None
            status = (
                "unchecked"
                if ratio is None
                else "ok" if 0.72 <= ratio <= 1.18 else "review"
            )
            track_counts = Counter(detail["track_class"] for detail in details)
            collected = QgsGeometry.collectGeometry(geometries)
            output = QgsFeature()
            output.setGeometry(collected)
            output.setAttributes(
                [
                    record["seq"],
                    record["date"],
                    record["origin"],
                    record["destination"],
                    record["train"],
                    service_class,
                    record["distance_km"],
                    round(route_km, 1),
                    round(ratio, 3) if ratio is not None else None,
                    len(details),
                    status,
                ]
            )
            route_features.append(output)
            route_report.append(
                {
                    **record,
                    "preferred_network": preferred_network,
                    "control_points": reported_control_names[1:-1],
                    "route_km": round(route_km, 1),
                    "ratio": round(ratio, 3) if ratio is not None else None,
                    "edge_count": len(details),
                    "track_counts": dict(track_counts),
                    "status": status,
                    "origin_snap_km": round(station_snap_km[record["origin"]], 3),
                    "destination_snap_km": round(
                        station_snap_km[record["destination"]], 3
                    ),
                }
            )

        OUTPUT_GPKG.parent.mkdir(parents=True, exist_ok=True)
        ROUTE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        write_routes(route_features, OUTPUT_GPKG)
        report = {
            "network_extent": [min_lon, min_lat, max_lon, max_lat],
            "network_features": feature_count,
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": graph.number_of_edges(),
            "topology_connectors": connector_count,
            "station_component_connectors": station_component_connectors,
            "largest_component_nodes": len(component_nodes),
            "max_station_snap_km": round(max(station_snap_km.values()), 3),
            "review_count": sum(item["status"] == "review" for item in route_report),
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "routes": route_report,
        }
        ROUTE_REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({key: value for key, value in report.items() if key != "routes"}, ensure_ascii=False))
        print(OUTPUT_GPKG)
        print(ROUTE_REPORT)
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
