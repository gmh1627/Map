"""Build a redesigned, editable QGIS map for the Shanxi-Shaanxi trip."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPolyline,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsProperty,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


RAILWAY_ROOT = Path(r"F:\Desktop\Blog\Map")
DATA_ROOT = RAILWAY_ROOT / "制图工具" / "数据源"
DEFAULT_OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "区域线路图" / "山陕漫游"
OUTPUT_DIR = DEFAULT_OUTPUT_DIR
OUTPUT_GPKG = OUTPUT_DIR / "山陕漫游_数据.gpkg"
OUTPUT_PROJECT = OUTPUT_DIR / "山陕漫游.qgz"
OUTPUT_IMAGE = OUTPUT_DIR / "山陕漫游.png"

PROVINCES = RAILWAY_ROOT / "province" / "province.json"
CITY_SOURCE = RAILWAY_ROOT / "city" / "city.json"
BEIJING = RAILWAY_ROOT / "city" / "beijing_contour.json"
HEBEI = RAILWAY_ROOT / "province" / "hebei.geojson"
SHANXI = RAILWAY_ROOT / "province" / "shanxi.geojson"
SHAANXI = RAILWAY_ROOT / "province" / "shaanxi.geojson"
LVLIANG = RAILWAY_ROOT / "city" / "lvliang.geojson"
XINZHOU = RAILWAY_ROOT / "city" / "xinzhou.json"
YULIN = RAILWAY_ROOT / "city" / "yulin.json"
ROUTE_SOURCES_GPKG = DATA_ROOT / "GeoPackage" / "route_sources.gpkg"

PAGE_SIZE = (300.0, 210.0)
MAP_FRAME = (12.0, 40.0, 276.0, 147.0)
MAP_EXTENT = QgsRectangle(106.95, 36.45, 117.56, 41.12)

VISITED_SHANXI = {"太原市", "吕梁市", "忻州市", "大同市"}
VISITED_SHAANXI = {"榆林市"}
STATION_NAMES = [
    "北京丰台",
    "太原",
    "蔡家崖",
    "岢岚",
    "宁武",
    "大同",
    "大同南",
    "北京北",
    "府谷",
    "神木",
]
STATION_COORDS = {
    "北京丰台": (116.2953417, 39.8499954),
    "北京北": (116.3467143, 39.9430709),
    "大同": (113.2963381, 40.1190975),
    "大同南": (113.3581164, 40.0435567),
    "太原": (112.5818317, 37.8600375),
    "宁武": (112.3128010, 39.0055710),
    "岢岚": (111.5749274, 38.7179000),
    "府谷": (111.0395720, 39.0508442),
    "神木": (110.4490968, 38.9367271),
    "蔡家崖": (111.0154640, 38.4932982),
}
ROUTE_METADATA_BY_SOURCE_FID = {
    0: ("conventional", "K8204", "神木-府谷"),
    1: ("conventional", "K609", "北京丰台-太原"),
    2: ("conventional", "K609", "北京丰台-太原"),
    3: ("conventional", "K609", "北京丰台-太原"),
    4: ("conventional", "K609", "北京丰台-太原"),
    5: ("conventional", "4621", "太原-蔡家崖"),
    6: ("conventional", "K8204", "神木-府谷"),
    7: ("conventional", "8834/8824", "岢岚-宁武-大同"),
    8: ("conventional", "8824", "宁武-大同"),
    9: ("conventional", "8824", "宁武-大同"),
    10: ("highspeed", "G2514", "大同南-北京北"),
    11: ("highspeed", "G2514", "大同南-北京北"),
}

ROAD_SPECS = [
    {
        "name": "蔡家崖至保德",
        # Draw only the transfer's middle section, so the symbol communicates
        # direction without pretending to be a surveyed road alignment.
        "points": [(111.035, 38.650), (111.075, 38.755), (111.070, 38.875)],
        "directions": "forward",
    },
    {
        "name": "保德至岢岚",
        "points": [(111.155, 38.960), (111.280, 38.920), (111.405, 38.835)],
        "directions": "forward",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def rgba(value: str, alpha: int) -> str:
    color = QColor(value)
    color.setAlpha(alpha)
    return color.name(QColor.HexArgb)


def text_format(
    size: float,
    color: str,
    family: str,
    buffer_size: float = 0.0,
    bold: bool = False,
) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont(family)
    font.setPointSizeF(size)
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer_size:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setColor(QColor("#FFFDFC"))
        buffer.setSize(buffer_size)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(buffer)
    return fmt


def load_vector(
    project: QgsProject,
    path: Path,
    name: str,
    layer_name: str | None = None,
    subset: str | None = None,
) -> QgsVectorLayer:
    uri = str(path)
    if layer_name:
        uri = f"{uri}|layername={layer_name}"
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid vector layer: {uri}")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Unable to set subset for {name}: {subset}")
    project.addMapLayer(layer)
    return layer


def save_memory_layer(
    project: QgsProject, layer: QgsVectorLayer, layer_name: str, overwrite: bool = False
) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    if overwrite:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    else:
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {layer_name}: {result}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={layer_name}", layer_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Invalid saved layer: {layer_name}")
    project.addMapLayer(saved)
    return saved


def filter_inner_mongolia_prefectures(source: QgsVectorLayer) -> QgsVectorLayer:
    memory = QgsVectorLayer(
        f"MultiPolygon?crs={source.crs().authid()}", "内蒙古地级市", "memory"
    )
    memory.dataProvider().addAttributes(list(source.fields()))
    memory.updateFields()
    features = []
    for item in source.getFeatures():
        try:
            adcode = int(item["adcode"])
        except (TypeError, ValueError):
            continue
        if not 150000 <= adcode < 160000 or str(item["level"]) != "city":
            continue
        feature = QgsFeature(memory.fields())
        feature.setAttributes(item.attributes())
        feature.setGeometry(item.geometry())
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    if not features:
        raise RuntimeError("No Inner Mongolia prefectures found")
    return memory


def add_labels(
    layer: QgsVectorLayer,
    expression: str,
    size: float,
    color: str,
    family: str,
    placement: int,
    priority: int,
    distance: float = 0.0,
    display_all: bool = False,
    fit_in_polygon: bool = False,
) -> None:
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = expression
    settings.isExpression = True
    settings.placement = placement
    settings.priority = priority
    settings.dist = distance
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = display_all
    settings.obstacle = False
    settings.fitInPolygonOnly = fit_in_polygon
    if hasattr(settings, "allowDegradedPlacement"):
        settings.allowDegradedPlacement = not fit_in_polygon
    settings.setFormat(text_format(size, color, family, 0.42))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def fill_symbol(
    fill: str, outline: str, width: float, alpha: int = 255
) -> QgsFillSymbol:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": rgba(fill, alpha),
            "outline_color": outline,
            "outline_width": str(width),
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    if width <= 0:
        symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    return symbol


def style_prefectures(
    layer: QgsVectorLayer,
    visited: set[str],
    base_fill: str = "#EEF3F6",
    base_alpha: int = 160,
) -> None:
    field_index = layer.fields().indexFromName("name")
    categories = []
    for name in sorted(str(value) for value in layer.uniqueValues(field_index)):
        is_visited = name in visited
        symbol = fill_symbol(
            "#D7E8E1" if is_visited else base_fill,
            "255,255,255,0",
            0.0,
            220 if is_visited else base_alpha,
        )
        categories.append(QgsRendererCategory(name, symbol, name))
    layer.setRenderer(QgsCategorizedSymbolRenderer("name", categories))
    if visited:
        values = ", ".join(f"'{name}'" for name in sorted(visited))
        expression = (
            f'CASE WHEN "name" IN ({values}) '
            "THEN regexp_replace(\"name\", '市$', '') END"
        )
        add_labels(
            layer,
            expression,
            9.2,
            "#243F51",
            "华文新魏",
            QgsPalLayerSettings.Horizontal,
            7,
        )


def style_beijing(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(fill_symbol("#DDB8AE", "255,255,255,0", 0.0, 188))
    )
    add_labels(
        layer,
        "'北京'",
        10.0,
        "#533C37",
        "华文新魏",
        QgsPalLayerSettings.Horizontal,
        8,
        display_all=True,
    )


def style_tianjin(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(fill_symbol("#EEF3F6", "255,255,255,0", 0.0, 36))
    )
    add_labels(
        layer,
        "'天津'",
        7.2,
        "#8A9390",
        "华文新魏",
        QgsPalLayerSettings.Horizontal,
        5,
        display_all=True,
    )


def style_focus_counties(layer: QgsVectorLayer, move_kelan: bool = False) -> None:
    symbol = fill_symbol("#70A390", "#2F6257", 0.0, 155)
    symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    outline = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "#2F6257",
            "line_width": "0.18",
            "line_width_unit": "MM",
        }
    )
    outline.setUseCustomDashPattern(True)
    outline.setCustomDashVector([1.5, 2.2])
    outline.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
    outline.setTweakDashPatternOnCorners(False)
    symbol.appendSymbolLayer(outline)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    add_labels(
        layer,
        'CASE WHEN "name" <> \'岢岚县\' THEN "name" END' if move_kelan else '"name"',
        8.1,
        "#315B52",
        "华文楷体",
        QgsPalLayerSettings.Horizontal,
        9,
        display_all=True,
    )


def style_province_outline(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {
                    "line_color": "#9AA8B0",
                    "line_width": "0.32",
                    "line_width_unit": "MM",
                    "joinstyle": "round",
                    "capstyle": "round",
                }
            )
        )
    )


def build_province_outline_from_prefectures(
    project: QgsProject, sources: tuple[QgsVectorLayer, ...]
) -> QgsVectorLayer:
    memory = QgsVectorLayer("MultiLineString?crs=EPSG:4326", "省界", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for source in sources:
        geometries = [
            feature.geometry()
            for feature in source.getFeatures()
            if not feature.geometry().isNull() and not feature.geometry().isEmpty()
        ]
        if not geometries:
            continue
        dissolved = QgsGeometry.unaryUnion(geometries)
        if dissolved.isNull() or dissolved.isEmpty():
            continue
        polygons = dissolved.asMultiPolygon() if dissolved.isMultipart() else [dissolved.asPolygon()]
        rings = [ring for polygon in polygons for ring in polygon if ring]
        if not rings:
            continue
        feature = QgsFeature(memory.fields())
        feature.setAttributes([source.name()])
        feature.setGeometry(QgsGeometry.fromMultiPolylineXY(rings))
        features.append(feature)
    if not features:
        raise RuntimeError("No province outlines could be derived from prefectures")
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    saved = save_memory_layer(project, memory, "省界")
    style_province_outline(saved)
    return saved


def build_internal_boundaries(
    project: QgsProject,
    source: QgsVectorLayer,
    layer_name: str,
) -> QgsVectorLayer:
    features = list(source.getFeatures())
    shared_lines = []
    for index, first in enumerate(features):
        first_boundary = first.geometry().convertToType(
            QgsWkbTypes.LineGeometry, True
        )
        for second in features[index + 1 :]:
            if not first.geometry().boundingBox().intersects(
                second.geometry().boundingBox()
            ):
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
                shared_lines.append(shared)
    if not shared_lines:
        raise RuntimeError(f"No shared boundaries found for {layer_name}")
    memory = QgsVectorLayer(
        f"MultiLineString?crs={source.crs().authid()}", layer_name, "memory"
    )
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    feature = QgsFeature(memory.fields())
    geometry = QgsGeometry.unaryUnion(shared_lines)
    geometry.convertToMultiType()
    feature.setGeometry(geometry)
    feature.setAttribute("name", layer_name)
    memory.dataProvider().addFeature(feature)
    saved = save_memory_layer(project, memory, layer_name)
    saved.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {
                    "line_color": "#9AA8B0",
                    "line_width": "0.16",
                    "line_width_unit": "MM",
                    "joinstyle": "round",
                    "capstyle": "round",
                }
            )
        )
    )
    return saved


def build_unvisited_prefecture_labels(
    project: QgsProject,
    sources: tuple[QgsVectorLayer, ...],
    excluded_names: set[str],
) -> QgsVectorLayer:
    label_extent = QgsRectangle(MAP_EXTENT)
    label_extent.grow(max(label_extent.width(), label_extent.height()) * 0.25)
    extent_geometry = QgsGeometry.fromRect(label_extent)
    memory = QgsVectorLayer(
        "MultiPolygon?crs=EPSG:4326", "未到达城市名称", "memory"
    )
    memory.dataProvider().addAttributes(
        [QgsField("name", QVariant.String), QgsField("display", QVariant.String)]
    )
    memory.updateFields()
    features = []
    seen = set()
    for source in sources:
        for item in source.getFeatures():
            name = str(item["name"])
            if name in excluded_names or name in seen:
                continue
            geometry = item.geometry()
            if geometry.isNull() or not geometry.boundingBox().intersects(label_extent):
                continue
            clipped = geometry.intersection(extent_geometry)
            if clipped.isNull() or clipped.isEmpty():
                continue
            clipped.convertToMultiType()
            display = name
            for suffix in ("自治州", "地区", "市", "盟"):
                if display.endswith(suffix):
                    display = display.removesuffix(suffix)
                    break
            feature = QgsFeature(memory.fields())
            feature.setAttributes([name, display])
            feature.setGeometry(clipped)
            features.append(feature)
            seen.add(name)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    saved = save_memory_layer(project, memory, "未到达城市名称")
    label_area_symbol = fill_symbol("#FFFFFF", "#FFFFFF", 0.0, 0)
    label_area_symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    saved.setRenderer(QgsSingleSymbolRenderer(label_area_symbol))
    add_labels(
        saved,
        '"display"',
        7.2,
        "#8A9390",
        "华文新魏",
        Qgis.LabelPlacement.Horizontal,
        2,
        display_all=False,
        fit_in_polygon=True,
    )
    return saved


def style_rail_network(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsLineSymbol.createSimple(
                {
                    "color": rgba("#8D999D", 105),
                    "width": "0.14",
                    "width_unit": "MM",
                    "capstyle": "round",
                    "joinstyle": "round",
                }
            )
        )
    )


def trip_route_symbol(highspeed: bool = False) -> QgsLineSymbol:
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
    outer.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def build_trip_route_layer(project: QgsProject, source: QgsVectorLayer) -> QgsVectorLayer:
    memory = QgsVectorLayer("MultiLineString?crs=EPSG:4326", "实际铁路行程", "memory")
    memory.dataProvider().addAttributes(
        [
            QgsField("source_id", QVariant.Int),
            QgsField("service", QVariant.String),
            QgsField("train", QVariant.String),
            QgsField("segment", QVariant.String),
        ]
    )
    memory.updateFields()
    features = []
    seen_ids = set()
    for source_feature in source.getFeatures():
        source_id = int(source_feature["source_fid"])
        if source_id not in ROUTE_METADATA_BY_SOURCE_FID:
            raise RuntimeError(f"Unclassified Shanxi-Shaanxi route feature: {source_id}")
        service, train, segment = ROUTE_METADATA_BY_SOURCE_FID[source_id]
        feature = QgsFeature(memory.fields())
        geometry = source_feature.geometry()
        if not geometry.isMultipart():
            geometry.convertToMultiType()
        feature.setGeometry(geometry)
        feature.setAttributes([source_id, service, train, segment])
        features.append(feature)
        seen_ids.add(source_id)
    missing_ids = set(ROUTE_METADATA_BY_SOURCE_FID) - seen_ids
    if missing_ids:
        raise RuntimeError(f"Missing Shanxi-Shaanxi route features: {sorted(missing_ids)}")
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    layer = save_memory_layer(project, memory, "实际铁路行程")
    project.removeMapLayer(source.id())
    return layer


def style_trip_routes(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "service",
            [
                QgsRendererCategory("highspeed", trip_route_symbol(True), "高铁"),
                QgsRendererCategory("conventional", trip_route_symbol(False), "普铁"),
            ],
        )
    )


def build_road_layers(project: QgsProject) -> tuple[QgsVectorLayer, QgsVectorLayer]:
    road_memory = QgsVectorLayer("LineString?crs=EPSG:4326", "公路行程", "memory")
    road_provider = road_memory.dataProvider()
    road_provider.addAttributes(
        [QgsField("name", QVariant.String), QgsField("directions", QVariant.String)]
    )
    road_memory.updateFields()

    arrow_memory = QgsVectorLayer("Point?crs=EPSG:4326", "公路方向", "memory")
    arrow_provider = arrow_memory.dataProvider()
    arrow_provider.addAttributes(
        [QgsField("name", QVariant.String), QgsField("angle", QVariant.Double)]
    )
    arrow_memory.updateFields()

    road_features = []
    arrow_features = []
    for spec in ROAD_SPECS:
        points = spec["points"]
        start, control, end = points
        curve_points = []
        for index in range(25):
            t = index / 24
            omt = 1 - t
            curve_points.append(
                QgsPointXY(
                    omt * omt * start[0] + 2 * omt * t * control[0] + t * t * end[0],
                    omt * omt * start[1] + 2 * omt * t * control[1] + t * t * end[1],
                )
            )
        geometry = QgsGeometry.fromPolylineXY(curve_points)
        road = QgsFeature(road_memory.fields())
        road.setGeometry(geometry)
        road.setAttributes([spec["name"], spec["directions"]])
        road_features.append(road)

        dx = points[-1][0] - points[-2][0]
        dy = points[-1][1] - points[-2][1]
        forward_angle = math.degrees(math.atan2(dx, dy)) % 360
        placements = [(1.0, forward_angle)]
        if spec["directions"] == "both":
            placements = [(0.30, forward_angle), (0.70, (forward_angle + 180) % 360)]
        for fraction, angle in placements:
            point_geometry = geometry.interpolate(geometry.length() * fraction)
            arrow = QgsFeature(arrow_memory.fields())
            arrow.setGeometry(point_geometry)
            arrow.setAttributes([spec["name"], angle])
            arrow_features.append(arrow)

    road_provider.addFeatures(road_features)
    arrow_provider.addFeatures(arrow_features)
    road_memory.updateExtents()
    arrow_memory.updateExtents()
    roads = save_memory_layer(project, road_memory, "公路行程", overwrite=True)
    arrows = save_memory_layer(project, arrow_memory, "公路方向")
    return roads, arrows


def style_roads(roads: QgsVectorLayer, arrows: QgsVectorLayer) -> None:
    road_symbol = QgsLineSymbol()
    outer = QgsSimpleLineSymbolLayer(QColor("#FFFDF8"), 1.28)
    inner = QgsSimpleLineSymbolLayer(QColor("#C56F4A"), 0.72)
    for line in (outer, inner):
        line.setWidthUnit(Qgis.RenderUnit.Millimeters)
        line.setPenCapStyle(Qt.RoundCap)
        line.setPenJoinStyle(Qt.RoundJoin)
    road_symbol.changeSymbolLayer(0, outer)
    road_symbol.appendSymbolLayer(inner)

    arrow_symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "triangle",
            "color": "#C56F4A",
            "outline_color": "#C56F4A",
            "outline_width": "0.10",
            "outline_width_unit": "MM",
            "size": "3.5",
            "size_unit": "MM",
        }
    )
    arrow_symbol.setAngle(180)
    marker_line = QgsMarkerLineSymbolLayer(True)
    marker_line.setSubSymbol(arrow_symbol)
    marker_line.setPlacements(Qgis.MarkerLinePlacement.LastVertex)
    marker_line.setRotateMarker(True)
    road_symbol.appendSymbolLayer(marker_line)
    roads.setRenderer(QgsSingleSymbolRenderer(road_symbol))

    # Keep the auxiliary endpoint features editable for validation, but do not
    # render a second arrow symbol on top of the marker-line arrowhead.
    hidden_arrow = QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"})
    arrows.setRenderer(QgsSingleSymbolRenderer(hidden_arrow))


def style_stations(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "#B95D6D",
                    "outline_color": "#FFFDF8",
                    "outline_width": "0.40",
                    "outline_width_unit": "MM",
                    "size": "1.8",
                    "size_unit": "MM",
                }
            )
        )
    )
    add_labels(
        layer,
        'CASE WHEN "name" <> \'大同南\' THEN "name" || \'站\' END',
        6.8,
        "#1D2528",
        "宋体",
        QgsPalLayerSettings.OrderedPositionsAroundPoint,
        10,
        distance=0.8,
        display_all=True,
    )


def build_station_layer(project: QgsProject) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "行程车站", "memory")
    provider = memory.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for name in STATION_NAMES:
        lon, lat = STATION_COORDS[name]
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttributes([name])
        features.append(feature)
    provider.addFeatures(features)
    memory.updateExtents()
    return save_memory_layer(project, memory, "行程车站")


def build_kelan_label(project: QgsProject) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "岢岚县手工标注", "memory")
    provider = memory.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    feature = QgsFeature(memory.fields())
    feature.setGeometry(QgsGeometry.fromWkt("POINT (111.43 38.70)"))
    feature.setAttributes(["岢岚县"])
    provider.addFeature(feature)
    memory.updateExtents()
    layer = save_memory_layer(project, memory, "岢岚县手工标注")
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle", "size": "0", "outline_style": "no",
                }
            )
        )
    )
    add_labels(
        layer,
        '"name"',
        8.1,
        "#5A4B27",
        "华文楷体",
        Qgis.LabelPlacement.OverPoint,
        10,
        distance=0,
        display_all=True,
    )
    return layer


def build_datong_south_label(project: QgsProject) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "大同南站手工标注", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    lon, lat = STATION_COORDS["大同南"]
    feature = QgsFeature(memory.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat - 0.070)))
    feature.setAttributes(["大同南站"])
    memory.dataProvider().addFeature(feature)
    memory.updateExtents()
    layer = save_memory_layer(project, memory, "大同南站手工标注")
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple({"name": "circle", "size": "0", "outline_style": "no"})
        )
    )
    add_labels(
        layer,
        '"name"',
        6.8,
        "#1D2528",
        "宋体",
        Qgis.LabelPlacement.OverPoint,
        10,
        display_all=True,
    )
    return layer


def add_layout_label(
    layout: QgsPrintLayout,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    family: str,
    color: str = "#111111",
    bold: bool = False,
) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(text_format(size, color, family, 0, bold))
    item.setHAlign(Qt.AlignLeft)
    item.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    return item


def projected_extent(project: QgsProject) -> QgsRectangle:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    return transform.transformBoundingBox(MAP_EXTENT)


def add_scale_bar(layout: QgsPrintLayout, map_item: QgsLayoutItemMap) -> None:
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitsPerSegment(100)
    scale.setUnitLabel("km")
    scale.setHeight(1.1)
    scale.setLabelBarSpace(0.55)
    scale.setBoxContentSpace(0.55)
    scale.setTextFormat(text_format(8.0, "#48555C", "思源黑体 CN", bold=True))
    scale.setLineColor(QColor("#56636A"))
    scale.setLineWidth(0.24)
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(15, 194, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(86, 10, QgsUnitTypes.LayoutMillimeters))


def add_route_legend(layout: QgsPrintLayout) -> None:
    highspeed = QgsLayoutItemPolyline(QPolygonF([QPointF(0, 0), QPointF(22, 0)]), layout)
    highspeed.setSymbol(trip_route_symbol(True))
    layout.addLayoutItem(highspeed)
    highspeed.attemptMove(QgsLayoutPoint(125, 199, QgsUnitTypes.LayoutMillimeters))
    add_layout_label(layout, "高铁", 151, 195, 42, 8, 10.0, "思源黑体 CN", "#48555C", bold=True)

    conventional = QgsLayoutItemPolyline(QPolygonF([QPointF(0, 0), QPointF(22, 0)]), layout)
    conventional.setSymbol(trip_route_symbol(False))
    layout.addLayoutItem(conventional)
    conventional.attemptMove(QgsLayoutPoint(205, 199, QgsUnitTypes.LayoutMillimeters))
    add_layout_label(layout, "普铁", 231, 195, 35, 8, 10.0, "思源黑体 CN", "#48555C", bold=True)


def build_layout(project: QgsProject, layers: list) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("山陕漫游")
    layout.pageCollection().page(0).setPageSize(
        QgsLayoutSize(*PAGE_SIZE, QgsUnitTypes.LayoutMillimeters)
    )
    project.layoutManager().addLayout(layout)

    add_layout_label(layout, "山陕漫游", 12, 2, 160, 15, 27, "华文新魏")
    add_layout_label(
        layout,
        "太原 · 吕梁兴县蔡家崖乡 · 忻州保德县、岢岚县 · 榆林府谷县、神木市 · 大同",
        13,
        17,
        280,
        11,
        13.0,
        "华文楷体",
    )
    add_layout_label(layout, "2026.05.14—05.17", 13, 28, 100, 10, 13.0, "华文楷体")

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#6D7A81"))
    map_item.setFrameStrokeWidth(
        QgsLayoutMeasurement(0.22, QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(map_item)
    map_item.attemptMove(
        QgsLayoutPoint(MAP_FRAME[0], MAP_FRAME[1], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.attemptResize(
        QgsLayoutSize(MAP_FRAME[2], MAP_FRAME[3], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.zoomToExtent(projected_extent(project))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)

    add_scale_bar(layout, map_item)
    add_route_legend(layout)
    return layout


def main() -> int:
    global OUTPUT_DIR, OUTPUT_GPKG, OUTPUT_PROJECT, OUTPUT_IMAGE
    args = parse_args()
    OUTPUT_DIR = args.output_dir.resolve()
    OUTPUT_GPKG = OUTPUT_DIR / "山陕漫游_数据.gpkg"
    OUTPUT_PROJECT = OUTPUT_DIR / "山陕漫游.qgz"
    OUTPUT_IMAGE = OUTPUT_DIR / "山陕漫游.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

        beijing = load_vector(project, BEIJING, "北京")
        tianjin = load_vector(
            project, PROVINCES, "天津", subset='"name" = \'天津市\''
        )
        hebei = load_vector(project, HEBEI, "河北地级市")
        shanxi = load_vector(project, SHANXI, "山西地级市")
        shaanxi = load_vector(project, SHAANXI, "陕西地级市")
        national_cities = load_vector(project, CITY_SOURCE, "全国地级行政区源数据")
        inner_mongolia_memory = filter_inner_mongolia_prefectures(national_cities)
        lvliang = load_vector(
            project, LVLIANG, "兴县", subset='"name" = \'兴县\''
        )
        xinzhou = load_vector(
            project,
            XINZHOU,
            "保德与岢岚",
            subset='"name" IN (\'保德县\', \'岢岚县\')',
        )
        yulin = load_vector(
            project,
            YULIN,
            "府谷与神木",
            subset='"name" IN (\'府谷县\', \'神木市\')',
        )
        trip_route_source = load_vector(
            project, ROUTE_SOURCES_GPKG, "铁路行程源数据", "trip_route_ss"
        )
        roads, arrows = build_road_layers(project)
        inner_mongolia = save_memory_layer(
            project, inner_mongolia_memory, "内蒙古地级市"
        )
        province_outline = build_province_outline_from_prefectures(
            project, (beijing, tianjin, hebei, shanxi, shaanxi, inner_mongolia)
        )
        project.removeMapLayer(national_cities.id())
        trip_route = build_trip_route_layer(project, trip_route_source)
        stations = build_station_layer(project)
        kelan_label = build_kelan_label(project)
        datong_south_label = build_datong_south_label(project)

        style_beijing(beijing)
        style_tianjin(tianjin)
        style_prefectures(hebei, set(), "#FFFFFF", 24)
        style_prefectures(shanxi, VISITED_SHANXI)
        style_prefectures(shaanxi, VISITED_SHAANXI)
        style_prefectures(inner_mongolia, set(), "#FFFFFF", 24)
        hebei_internal = build_internal_boundaries(project, hebei, "河北地市内部边界")
        shanxi_internal = build_internal_boundaries(project, shanxi, "山西地市内部边界")
        shaanxi_internal = build_internal_boundaries(project, shaanxi, "陕西地市内部边界")
        inner_mongolia_internal = build_internal_boundaries(
            project, inner_mongolia, "内蒙古地市内部边界"
        )
        unvisited_city_labels = build_unvisited_prefecture_labels(
            project,
            (hebei, shanxi, shaanxi, inner_mongolia),
            VISITED_SHANXI | VISITED_SHAANXI,
        )
        style_focus_counties(lvliang)
        style_focus_counties(xinzhou, move_kelan=True)
        style_focus_counties(yulin)
        style_trip_routes(trip_route)
        style_roads(roads, arrows)
        project.layerTreeRoot().findLayer(roads.id()).setItemVisibilityChecked(False)
        project.layerTreeRoot().findLayer(arrows.id()).setItemVisibilityChecked(False)
        style_stations(stations)

        layers = [
            datong_south_label,
            stations,
            kelan_label,
            unvisited_city_labels,
            trip_route,
            province_outline,
            hebei_internal,
            shanxi_internal,
            shaanxi_internal,
            inner_mongolia_internal,
            lvliang,
            xinzhou,
            yulin,
            beijing,
            tianjin,
            hebei,
            shanxi,
            shaanxi,
            inner_mongolia,
        ]

        layout = build_layout(project, layers)
        project.setTitle("山陕漫游")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(projected_extent(project), project.crs())
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)
        if hasattr(project, "setFilePathStorage"):
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        if not project.write(str(OUTPUT_PROJECT)):
            raise RuntimeError(f"Unable to save project: {OUTPUT_PROJECT}")

        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 210
        OUTPUT_IMAGE.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_IMAGE), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Export failed: {result}")
        print(OUTPUT_IMAGE)
        print(OUTPUT_PROJECT)
        print(OUTPUT_GPKG)
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
