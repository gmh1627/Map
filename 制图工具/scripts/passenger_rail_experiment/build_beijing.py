"""Build a Beijing hub-map experiment with a light passenger-rail background."""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree
from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPolygonF
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPolyline,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsPrintLayout,
    QgsProject,
    QgsPointXY,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


ROOT = Path(r"F:\Desktop\Blog\Map")
OUTPUT_DIR = ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
SOURCE_PROJECT = OUTPUT_DIR / "铁路枢纽局部图.qgz"
CURRENT_RAIL_GPKG = ROOT / "地图输出" / "全国专题图" / "全国足迹" / "全国足迹_数据.gpkg"
OSM_GPKG = ROOT / "制图工具" / "数据源" / "GeoPackage" / "travel_map_home2_min_gan.gpkg"
CITY_SOURCE = ROOT / "city" / "city.json"
PROVINCE_SOURCE = ROOT / "province" / "province.json"
OUTPUT_GPKG = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.gpkg"
OUTPUT_PROJECT = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.qgz"
OUTPUT_IMAGE = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.png"
SOURCE_LAYOUT = "北京及周边铁路行迹"
OUTPUT_LAYOUT = "北京及周边铁路行迹_客运铁路底图"
# Conventional corridors and connecting lines with current passenger use.
VERIFIED_PASSENGER_NAMES = {
    "京沪线",
    "京哈线",
    "京广线",
    "京九线",
    "京包线",
    "京承线",
    "京通线",
    "京原线",
    "丰沙线",
    "西长线",
    "京包客专线",
    "京哈高速线",
    "京津城际线",
    "京唐城际线",
    "京沪高铁",
    "京广高速线",
    "京雄城际线",
    "崇礼线",
    "津兴城际线",
    "怀兴城际线",
    "津蓟线",
    "怀联线",
    "延庆线",
    "康延线",
    "康延联络线",
    "北京直通线",
    "北京联络线",
    "京沪京哈联络线",
    "京沪京广联络线",
    "京沪京广下行联络线",
    "京广高速京西联络线",
    "京包客专京通联络线",
    "京包京通联络线",
    "丰双丰沙联络线",
    "沙城-沙城西线",
    "通乔线",
}
KNOWN_FREIGHT_NAMES = {
    "大秦线",
    "大秦铁路",
    "唐包线",
    "大台线",
    "西北环线",
    "良陈线",
    "虎丰线",
    "一零一线",
    "东星线",
    "塔锡线",
    "大李线",
    "房山线",
    "宣庞线",
    "沙蔚铁路",
    "沙蔚线",
    "永丰线",
    "东北环线",
    "东北环疏解线",
    "廊涿城际线",
}
EXCLUDED_SERVICES = {"siding", "spur", "yard", "crossover"}
CORRIDOR_CONNECTIONS = (
    ("崇礼线", "京包客专线"),
    ("沙城-沙城西线", "丰沙线"),
    ("延庆线", "京包线"),
    ("康延线", "京包线"),
    ("怀联线", "京承线"),
    ("通乔线", "京哈线"),
)
CORRIDOR_TERMINALS = {
    "崇礼线": (("崇礼站", (115.3110046, 41.0058806)),),
    "津蓟线": (
        ("天津北站", (117.2030494, 39.1656713)),
        ("蓟州北站", (117.3913352, 40.0253968)),
    ),
}


def parse_tags(value: object) -> dict[str, str]:
    return dict(re.findall(r'"([^"\\]+)"=>"([^"\\]*)"', str(value or "")))


def is_excluded(name: str, tags: dict[str, str]) -> bool:
    return (
        tags.get("service") in EXCLUDED_SERVICES
        or tags.get("usage") in {"industrial", "military"}
        or (
            tags.get("railway:traffic_mode") == "freight"
            and name not in VERIFIED_PASSENGER_NAMES
        )
        or name in KNOWN_FREIGHT_NAMES
        or any(key in tags for key in ("disused", "abandoned", "proposed", "construction"))
    )


def rail_class(name: str, tags: dict[str, str]) -> str:
    if tags.get("highspeed") == "yes" or any(
        token in name for token in ("高速", "高铁", "客专", "城际")
    ):
        return "highspeed"
    return "conventional"


def source_features(
    source: QgsVectorLayer, extraction_extent: QgsRectangle
) -> list[tuple[QgsFeature, str, dict[str, str]]]:
    request = QgsFeatureRequest().setFilterRect(extraction_extent).setFilterExpression(
        '"railway" = \'rail\''
    )
    result = []
    for feature in source.getFeatures(request):
        name = str(feature["name"] or "")
        tags = parse_tags(feature["other_tags"])
        if not is_excluded(name, tags):
            result.append((feature, name, tags))
    return result


def feature_points(feature: QgsFeature) -> list[QgsPointXY]:
    geometry = feature.geometry()
    if geometry.isMultipart():
        parts = [part for part in geometry.asMultiPolyline() if len(part) >= 2]
        return list(max(parts, key=len)) if parts else []
    return list(geometry.asPolyline())


def node_key(point: QgsPointXY) -> tuple[float, float]:
    return (round(point.x(), 6), round(point.y(), 6))


def edge_length(first: tuple[float, float], second: tuple[float, float]) -> float:
    latitude = (first[1] + second[1]) / 2.0
    x_scale = max(0.1, np.cos(np.radians(latitude)))
    return float(np.hypot((first[0] - second[0]) * x_scale, first[1] - second[1]))


def build_corridor_paths(
    candidates: list[tuple[QgsFeature, str, dict[str, str]]]
) -> list[tuple[str, str, str, QgsGeometry]]:
    graph = nx.Graph()
    seed_nodes: dict[str, set[tuple[float, float]]] = defaultdict(set)
    refs: dict[str, Counter[str]] = defaultdict(Counter)
    classes: dict[str, str] = {}

    for feature, name, tags in candidates:
        points = feature_points(feature)
        if len(points) < 2:
            continue
        keys = [node_key(point) for point in points]
        if name in VERIFIED_PASSENGER_NAMES:
            seed_nodes[name].update(keys)
            if tags.get("ref"):
                refs[name][tags["ref"]] += 1
            if rail_class(name, tags) == "highspeed":
                classes[name] = "highspeed"
            else:
                classes.setdefault(name, "conventional")
        for start, end in zip(keys, keys[1:]):
            if start == end:
                continue
            length = edge_length(start, end)
            current = graph.get_edge_data(start, end)
            new_rank = 0 if name in VERIFIED_PASSENGER_NAMES else 1 if not name else 2
            current_rank = current.get("rank", 99) if current else 99
            if current is None or new_rank < current_rank:
                graph.add_edge(
                    start,
                    end,
                    length=max(length, 1e-9),
                    name=name,
                    rank=new_rank,
                    connector=False,
                )

    # OSM often maps parallel tracks and station throats as separate ways whose
    # endpoints miss by a few metres. High-cost local connectors keep corridor
    # paths continuous without making those artificial links visually dominant.
    nodes = list(graph.nodes)
    coordinates = np.asarray(nodes, dtype=float)
    if len(nodes) > 1:
        tree = cKDTree(coordinates)
        distances, neighbors = tree.query(
            coordinates, k=4, distance_upper_bound=0.00025, workers=-1
        )
        for start_index, (row_distances, row_neighbors) in enumerate(
            zip(distances, neighbors)
        ):
            for distance, end_index in zip(row_distances[1:], row_neighbors[1:]):
                end_index = int(end_index)
                if end_index >= len(nodes) or not np.isfinite(distance):
                    continue
                start = nodes[start_index]
                end = nodes[end_index]
                if start_index >= end_index or graph.has_edge(start, end):
                    continue
                graph.add_edge(
                    start,
                    end,
                    length=max(edge_length(start, end), 1e-9),
                    name="",
                    rank=3,
                    connector=True,
                )

    component_by_node: dict[tuple[float, float], int] = {}
    for index, component in enumerate(nx.connected_components(graph)):
        for node in component:
            component_by_node[node] = index

    corridor_paths: dict[str, list[tuple[float, float]]] = {}
    for name in sorted(seed_nodes):
        grouped: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for node in seed_nodes[name]:
            if node in component_by_node:
                grouped[component_by_node[node]].append(node)
        if not grouped:
            continue
        seeds = max(grouped.values(), key=len)
        center = np.mean(np.asarray(seeds), axis=0)
        first = max(seeds, key=lambda node: float(np.sum((np.asarray(node) - center) ** 2)))
        second = max(
            seeds,
            key=lambda node: (node[0] - first[0]) ** 2 + (node[1] - first[1]) ** 2,
        )

        def weight(_start, _end, data):
            edge_name = str(data.get("name", ""))
            if edge_name == name:
                factor = 0.04
            elif data.get("connector"):
                factor = 25.0
            elif not edge_name:
                factor = 1.0
            elif edge_name in VERIFIED_PASSENGER_NAMES:
                factor = 3.0
            else:
                factor = 12.0
            return float(data["length"]) * factor

        path = nx.shortest_path(graph, first, second, weight=weight)
        corridor_paths[name] = path

    def connection_weight_for(names: set[str]):
        def weight(_start, _end, data):
            edge_name = str(data.get("name", ""))
            if edge_name in names:
                factor = 0.04
            elif data.get("connector"):
                factor = 25.0
            elif not edge_name:
                factor = 1.0
            elif edge_name in VERIFIED_PASSENGER_NAMES:
                factor = 3.0
            else:
                factor = 12.0
            return float(data["length"]) * factor

        return weight

    if len(nodes) < 2:
        raise RuntimeError("Rail network has too few nodes")
    node_tree = cKDTree(np.asarray(nodes, dtype=float))
    for source_name, terminals in CORRIDOR_TERMINALS.items():
        source_path = corridor_paths.get(source_name)
        if not source_path:
            raise RuntimeError(f"Missing corridor for terminal: {source_name}")
        for _, terminal_coordinate in terminals:
            _, target_index = node_tree.query(np.asarray(terminal_coordinate), k=1)
            target = nodes[int(target_index)]
            endpoint_index = min(
                (0, -1),
                key=lambda index: edge_length(source_path[index], terminal_coordinate),
            )
            endpoint = source_path[endpoint_index]
            connection = nx.shortest_path(
                graph,
                endpoint,
                target,
                weight=connection_weight_for({source_name}),
            )
            if endpoint_index == 0:
                source_path = list(reversed(connection))[:-1] + source_path
            else:
                source_path = source_path + connection[1:]
        corridor_paths[source_name] = source_path

    for source_name, target_name in CORRIDOR_CONNECTIONS:
        source_path = corridor_paths.get(source_name)
        target_path = corridor_paths.get(target_name)
        if not source_path or not target_path:
            raise RuntimeError(
                f"Missing corridor for connection: {source_name} -> {target_name}"
            )
        pairs = []
        for endpoint_index in (0, -1):
            endpoint = source_path[endpoint_index]
            target = min(
                target_path,
                key=lambda node: edge_length(endpoint, node),
            )
            pairs.append((edge_length(endpoint, target), endpoint_index, endpoint, target))
        _, endpoint_index, endpoint, target = min(pairs, key=lambda item: item[0])

        connection = nx.shortest_path(
            graph,
            endpoint,
            target,
            weight=connection_weight_for({source_name, target_name}),
        )
        if endpoint_index == 0:
            corridor_paths[source_name] = list(reversed(connection))[:-1] + source_path
        else:
            corridor_paths[source_name] = source_path + connection[1:]

    output = []
    for name, path in sorted(corridor_paths.items()):
        geometry = QgsGeometry.fromPolylineXY([QgsPointXY(*node) for node in path])
        reference = refs[name].most_common(1)[0][0] if refs[name] else ""
        output.append((name, reference, classes.get(name, "conventional"), geometry))
    return output


def build_passenger_layer(
    project: QgsProject, extraction_extent: QgsRectangle
) -> QgsVectorLayer:
    source = QgsVectorLayer(
        f"{OSM_GPKG}|layername=china_railwayosm__lines", "OSM铁路源数据", "ogr"
    )
    if not source.isValid():
        raise RuntimeError(f"无法打开铁路源数据：{OSM_GPKG}")
    candidates = source_features(source, extraction_extent)
    corridors = build_corridor_paths(candidates)

    memory = QgsVectorLayer("LineString?crs=EPSG:4326", "其他客运铁路", "memory")
    memory.dataProvider().addAttributes(
        [
            QgsField("name", QVariant.String),
            QgsField("ref", QVariant.String),
            QgsField("rail_class", QVariant.String),
            QgsField("basis", QVariant.String),
        ]
    )
    memory.updateFields()
    output = []
    for name, reference, line_class, geometry in corridors:
        feature = QgsFeature(memory.fields())
        feature.setGeometry(geometry)
        feature.setAttributes([name, reference, line_class, "network_corridor"])
        output.append(feature)
    memory.dataProvider().addFeatures(output)
    memory.updateExtents()

    OUTPUT_GPKG.unlink(missing_ok=True)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "其他客运铁路"
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"无法写出客运铁路图层：{message}")
    layer = QgsVectorLayer(f"{OUTPUT_GPKG}|layername=其他客运铁路", "其他客运铁路", "ogr")
    if not layer.isValid():
        raise RuntimeError("写出的客运铁路图层无效")
    project.addMapLayer(layer)
    return layer


def write_output_layer(
    project: QgsProject, memory: QgsVectorLayer, layer_name: str
) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"无法写出{layer_name}：{message}")
    layer = QgsVectorLayer(f"{OUTPUT_GPKG}|layername={layer_name}", layer_name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"写出的{layer_name}无效")
    project.addMapLayer(layer)
    return layer


def province_code(feature: QgsFeature) -> int | None:
    level = str(feature["level"])
    parent = feature["parent"]
    parent_code = parent.get("adcode") if isinstance(parent, dict) else None
    if level == "district" and parent_code in {110000, 120000}:
        return int(parent_code)
    if level != "city":
        return None
    routes = feature["acroutes"]
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


def create_polygon_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    layer_name: str,
    geometry: QgsGeometry,
    fill: str,
    opacity: float,
) -> QgsVectorLayer:
    geometry.convertToMultiType()
    memory = QgsVectorLayer(
        f"MultiPolygon?crs={source.crs().authid()}", layer_name, "memory"
    )
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    feature = QgsFeature(memory.fields())
    feature.setAttribute("name", layer_name)
    feature.setGeometry(geometry)
    memory.dataProvider().addFeature(feature)
    memory.updateExtents()
    layer = write_output_layer(project, memory, layer_name)
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill,
            "outline_color": "255,255,255,0",
            "outline_width": "0",
        }
    )
    symbol.setOpacity(opacity)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)
    return layer


def build_unified_admin_layers(
    project: QgsProject, extraction_extent: QgsRectangle
) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    source = QgsVectorLayer(str(CITY_SOURCE), "统一行政区源数据", "ogr")
    if not source.isValid():
        raise RuntimeError(f"无法打开行政区源数据：{CITY_SOURCE}")
    province_source = QgsVectorLayer(str(PROVINCE_SOURCE), "完整省级行政区源数据", "ogr")
    if not province_source.isValid():
        raise RuntimeError(f"无法打开省级行政区源数据：{PROVINCE_SOURCE}")
    complete_provinces = {}
    for feature in province_source.getFeatures():
        try:
            code = int(feature["adcode"])
        except (TypeError, ValueError):
            continue
        complete_provinces[code] = feature.geometry()
    if not {110000, 120000}.issubset(complete_provinces):
        raise RuntimeError("无法读取完整北京、天津轮廓")
    all_records: list[tuple[QgsFeature, int]] = []
    visible_province_codes: set[int] = set()
    for feature in source.getFeatures():
        code = province_code(feature)
        if code is None:
            continue
        if str(feature["level"]) == "district" and code not in {110000, 120000}:
            continue
        all_records.append((feature, code))
        if feature.geometry().boundingBox().intersects(extraction_extent):
            visible_province_codes.add(code)
    records = [
        (feature, code)
        for feature, code in all_records
        if code in visible_province_codes
    ]
    if not records:
        raise RuntimeError("统一行政区范围内没有要素")

    province_lines = []
    dissolved_by_code: dict[int, QgsGeometry] = {}
    missing_provinces = sorted(visible_province_codes - set(complete_provinces))
    if missing_provinces:
        raise RuntimeError(f"省级源数据缺少行政区：{missing_provinces}")
    for code in sorted(visible_province_codes):
        dissolved = QgsGeometry(complete_provinces[code])
        if dissolved.isNull() or dissolved.isEmpty():
            continue
        dissolved_by_code[code] = dissolved
        province_lines.append(polygon_boundary(dissolved))

    internal_lines = []
    for index, (first, first_code) in enumerate(records):
        first_boundary = first.geometry().convertToType(QgsWkbTypes.LineGeometry, True)
        for second, second_code in records[index + 1 :]:
            if first_code != second_code:
                continue
            if not first.geometry().boundingBox().intersects(second.geometry().boundingBox()):
                continue
            second_boundary = second.geometry().convertToType(
                QgsWkbTypes.LineGeometry, True
            )
            shared = first_boundary.intersection(second_boundary)
            if (
                not shared.isNull()
                and not shared.isEmpty()
                and QgsWkbTypes.geometryType(shared.wkbType())
                == QgsWkbTypes.LineGeometry
                and shared.length() > 1e-9
            ):
                internal_lines.append(shared)
    if not province_lines or not internal_lines:
        raise RuntimeError("无法生成统一省界或市界")

    def create_line_layer(layer_name: str, geometries: list[QgsGeometry], color: str, width: float):
        geometry = QgsGeometry.unaryUnion(geometries)
        geometry.convertToMultiType()
        memory = QgsVectorLayer(
            f"MultiLineString?crs={source.crs().authid()}", layer_name, "memory"
        )
        memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
        memory.updateFields()
        feature = QgsFeature(memory.fields())
        feature.setAttribute("name", layer_name)
        feature.setGeometry(geometry)
        memory.dataProvider().addFeature(feature)
        memory.updateExtents()
        layer = write_output_layer(project, memory, layer_name)
        layer.setRenderer(
            QgsSingleSymbolRenderer(
                QgsLineSymbol.createSimple(
                    {
                        "line_color": color,
                        "line_width": str(width),
                        "line_width_unit": "MM",
                        "joinstyle": "round",
                        "capstyle": "round",
                    }
                )
            )
        )
        layer.setLabelsEnabled(False)
        return layer

    province_geometry = QgsGeometry.unaryUnion(province_lines)
    city_geometry = QgsGeometry.unaryUnion(internal_lines)
    city_parts = (
        city_geometry.asMultiPolyline()
        if city_geometry.isMultipart()
        else [city_geometry.asPolyline()]
    )
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

    province_layer = create_line_layer(
        "统一省界", [province_geometry], "#78847F", 0.42
    )
    city_layer = create_line_layer(
        "统一市界", [connected_city_geometry], "#C1C8C6", 0.15
    )
    beijing_fill = create_polygon_layer(
        project, source, "统一北京填色", dissolved_by_code[110000], "#B7CDBD", 0.62
    )
    tianjin_fill = create_polygon_layer(
        project, source, "统一天津填色", dissolved_by_code[120000], "#F7F8F6", 1.0
    )
    style_tianjin_label(tianjin_fill)
    return province_layer, city_layer, beijing_fill, tianjin_fill


def style_fill_only(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {
                    "color": "#F7F8F6",
                    "outline_color": "255,255,255,0",
                    "outline_width": "0",
                }
            )
        )
    )


def style_tianjin_label(layer: QgsVectorLayer) -> None:
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "'天津'"
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 3
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(text_format(9.3, "#697570"))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def background_symbol(color: str = "#AEC2CD", width: float = 0.34) -> QgsLineSymbol:
    symbol = QgsLineSymbol()
    line = QgsSimpleLineSymbolLayer(QColor(color), width)
    line.setWidthUnit(Qgis.RenderUnit.Millimeters)
    line.setPenJoinStyle(Qt.RoundJoin)
    line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, line)
    return symbol


def style_passenger_layer(layer: QgsVectorLayer) -> None:
    conventional = background_symbol("#AEC2CD", 0.34)
    highspeed = background_symbol("#9EB9C7", 0.36)
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "rail_class",
            [
                QgsRendererCategory("conventional", conventional, "其他普速客运铁路"),
                QgsRendererCategory("highspeed", highspeed, "其他高速客运铁路"),
            ],
        )
    )


def text_format(size: float, color: str) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont("思源黑体 CN")
    font.setPointSizeF(size)
    font.setWeight(QFont.Medium)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    return fmt


def travel_route_symbol(highspeed: bool) -> QgsLineSymbol:
    symbol = QgsLineSymbol()
    if highspeed:
        outer = QgsSimpleLineSymbolLayer(QColor("#FFFDF7"), 1.30)
        inner = QgsSimpleLineSymbolLayer(QColor("#2E7D83"), 0.72)
    else:
        outer = QgsSimpleLineSymbolLayer(QColor("#283237"), 1.12)
        inner = QgsSimpleLineSymbolLayer(QColor("#FFFDF7"), 0.44)
    for line in (outer, inner):
        line.setWidthUnit(Qgis.RenderUnit.Millimeters)
        line.setPenJoinStyle(Qt.RoundJoin)
        line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def add_legend_entry(
    layout: QgsPrintLayout,
    x: float,
    label_text: str,
    label_width: float,
    symbol: QgsLineSymbol,
    line_width: float = 12.0,
) -> None:
    line = QgsLayoutItemPolyline(
        QPolygonF([QPointF(x, 222.5), QPointF(x + line_width, 222.5)]), layout
    )
    line.setSymbol(symbol)
    layout.addLayoutItem(line)
    label_item = QgsLayoutItemLabel(layout)
    label_item.setText(label_text)
    label_item.setTextFormat(text_format(8.0, "#68736F"))
    label_item.setHAlign(Qt.AlignLeft)
    label_item.setVAlign(Qt.AlignVCenter)
    label_item.attemptMove(
        QgsLayoutPoint(x + line_width + 1.0, 218.5, QgsUnitTypes.LayoutMillimeters)
    )
    label_item.attemptResize(
        QgsLayoutSize(label_width, 8.0, QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(label_item)


def replace_inline_legend(layout: QgsPrintLayout) -> None:
    legend_texts = {"高铁/动车（含城际、市郊）", "普铁", "其他铁路线路"}
    for item in list(layout.items()):
        if isinstance(item, QgsLayoutItemPolyline):
            layout.removeLayoutItem(item)
        elif isinstance(item, QgsLayoutItemLabel) and item.text() in legend_texts:
            layout.removeLayoutItem(item)
    add_legend_entry(
        layout,
        94.0,
        "高铁/动车（含城际、市郊）",
        52.0,
        travel_route_symbol(True),
        11.0,
    )
    add_legend_entry(
        layout, 160.0, "普铁", 17.0, travel_route_symbol(False), 11.0
    )
    add_legend_entry(
        layout, 191.0, "其他铁路线路", 36.0, background_symbol(), 11.0
    )


def main() -> int:
    for required in (SOURCE_PROJECT, CURRENT_RAIL_GPKG, OSM_GPKG):
        if not required.exists():
            raise FileNotFoundError(required)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(SOURCE_PROJECT)):
            raise RuntimeError(f"无法打开源工程：{SOURCE_PROJECT}")
        layouts = {layout.name(): layout for layout in project.layoutManager().printLayouts()}
        layout = layouts.get(SOURCE_LAYOUT)
        if layout is None:
            raise RuntimeError(f"源工程缺少布局：{SOURCE_LAYOUT}")
        for name, other in layouts.items():
            if name != SOURCE_LAYOUT:
                project.layoutManager().removeLayout(other)
        layout.setName(OUTPUT_LAYOUT)
        map_items = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
        if len(map_items) != 1:
            raise RuntimeError(f"北京布局地图框数量异常：{len(map_items)}")
        map_item = map_items[0]

        map_layers = map_item.layers()
        route_index = next(
            (index for index, layer in enumerate(map_layers) if layer.name() == "铁路行程轨迹"),
            None,
        )
        if route_index is None:
            raise RuntimeError("北京布局缺少铁路行程轨迹图层")
        previous_routes = map_layers[route_index]
        current_routes = QgsVectorLayer(
            f"{CURRENT_RAIL_GPKG}|layername=铁路行程轨迹", "铁路行程轨迹", "ogr"
        )
        if not current_routes.isValid():
            raise RuntimeError(f"无法打开当前铁路行迹：{CURRENT_RAIL_GPKG}")
        current_routes.setRenderer(previous_routes.renderer().clone())
        project.addMapLayer(current_routes)
        map_layers[route_index] = current_routes

        to_wgs84 = QgsCoordinateTransform(
            project.crs(),
            QgsCoordinateReferenceSystem("EPSG:4326"),
            project.transformContext(),
        )
        extraction_extent = to_wgs84.transformBoundingBox(map_item.extent())
        extraction_extent.grow(
            max(extraction_extent.width(), extraction_extent.height()) * 0.20
        )
        passenger = build_passenger_layer(project, extraction_extent)
        style_passenger_layer(passenger)
        province_boundaries, city_boundaries, beijing_fill, tianjin_fill = (
            build_unified_admin_layers(project, extraction_extent)
        )
        obsolete_tokens = {
            "高亮城市",
            "北京市内部区界",
            "天津市内部区界",
            "周边城市内部边界",
            "天津市共边轮廓",
        }
        filtered_layers = []
        for layer in map_layers:
            name = layer.name()
            if any(token in name for token in obsolete_tokens):
                continue
            if "周边省份" in name:
                style_fill_only(layer)
            filtered_layers.append(layer)
        map_layers = filtered_layers
        route_index = next(
            index
            for index, layer in enumerate(map_layers)
            if layer.name() == "铁路行程轨迹"
        )
        map_layers[route_index + 1 : route_index + 1] = [
            passenger,
            province_boundaries,
            city_boundaries,
            beijing_fill,
            tianjin_fill,
        ]
        map_item.setLayers(map_layers)
        map_item.setKeepLayerSet(True)
        replace_inline_legend(layout)

        used_ids = {layer.id() for layer in map_layers}
        for layer_id in list(project.mapLayers()):
            if layer_id not in used_ids:
                project.removeMapLayer(layer_id)
        project.setTitle("北京及周边铁路行迹：客运铁路底图试验")
        project.setPresetHomePath(str(OUTPUT_DIR))
        project.setFilePathStorage(Qgis.FilePathType.Relative)
        OUTPUT_PROJECT.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_PROJECT)):
            raise RuntimeError(f"无法写出工程：{OUTPUT_PROJECT}")

        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 300
        OUTPUT_IMAGE.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_IMAGE), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"无法导出图片：{result}")
        image = QImage(str(OUTPUT_IMAGE))
        counts = {"conventional": 0, "highspeed": 0}
        basis = {"network_corridor": 0}
        for feature in passenger.getFeatures():
            counts[str(feature["rail_class"])] += 1
            basis[str(feature["basis"])] += 1
        print(
            {
                "features": passenger.featureCount(),
                "classes": counts,
                "basis": basis,
                "image": [image.width(), image.height(), OUTPUT_IMAGE.stat().st_size],
                "project": str(OUTPUT_PROJECT),
            }
        )
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
