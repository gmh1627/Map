"""Build editable QGIS layouts for the travel history article."""

from __future__ import annotations

import argparse
import json
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
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPolyline,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPrintLayout,
    QgsProject,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


SCRIPT_DIR = Path(__file__).resolve().parent
PARSED = SCRIPT_DIR / "parsed_source.json"
MATCH_REPORT = SCRIPT_DIR / "source_match_report.json"
PROVINCE_JSON = Path(r"F:\Desktop\Railway\province\province.json")
CITY_JSON = Path(r"F:\Desktop\Railway\city\city.json")
DEFAULT_ROUTE_GPKG = Path(r"F:\Desktop\Railway\地图输出\全国专题图\全国足迹\铁路轨迹.gpkg")
ROUTE_GPKG = DEFAULT_ROUTE_GPKG
ROUTE_SOURCES_GPKG = Path(
    r"F:\Desktop\Railway\制图工具\数据源\GeoPackage\route_sources.gpkg"
)
DEFAULT_OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\全国专题图\全国足迹")
OUTPUT_DIR = DEFAULT_OUTPUT_DIR
OUTPUT_GPKG = OUTPUT_DIR / "全国足迹_数据.gpkg"
OUTPUT_PROJECT = OUTPUT_DIR / "全国足迹.qgz"
VISIT_IMAGE = OUTPUT_DIR / "去过的省市.png"
RAIL_IMAGE = OUTPUT_DIR / "铁路路线.png"

PAGE_SIZE = (430.0, 330.0)
MAP_FRAME = (12.0, 40.0, 406.0, 248.0)
INSET_FRAME = (350.0, 208.0, 68.0, 80.0)
CHINA_EXTENT = QgsRectangle(73.0, 17.4, 135.5, 54.6)
SOUTH_CHINA_SEA_EXTENT = QgsRectangle(105.0, 2.5, 124.0, 24.0)
CHINA_ALBERS_PROJ = (
    "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 "
    "+datum=WGS84 +units=m +no_defs +type=crs"
)
REQUIRED_CITY_LABELS = {"漯河", "合肥", "芜湖", "广州", "茂名", "江门", "东莞"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--route-gpkg", type=Path, default=DEFAULT_ROUTE_GPKG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def projected_extent(project: QgsProject, extent: QgsRectangle) -> QgsRectangle:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    return transform.transformBoundingBox(extent)


def rgba(hex_color: str, alpha: int) -> str:
    color = QColor(hex_color)
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
        buffer.setColor(QColor(252, 251, 247, 230))
        buffer.setSize(buffer_size)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(buffer)
    return fmt


def save_memory_layer(
    project: QgsProject,
    layer: QgsVectorLayer,
    layer_name: str,
    overwrite_file: bool = False,
) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if overwrite_file
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to write {layer_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={layer_name}", layer_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen {layer_name}")
    project.addMapLayer(saved)
    return saved


def copy_source_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    layer_name: str,
    predicate=None,
    extra_fields: list[QgsField] | None = None,
    extra_values=None,
    overwrite_file: bool = False,
) -> QgsVectorLayer:
    geometry_name = QgsWkbTypes.displayString(source.wkbType())
    memory = QgsVectorLayer(
        f"{geometry_name}?crs={source.crs().authid()}", layer_name, "memory"
    )
    provider = memory.dataProvider()
    provider.addAttributes(source.fields().toList() + (extra_fields or []))
    memory.updateFields()
    output = []
    for feature in source.getFeatures():
        if predicate and not predicate(feature):
            continue
        copied = QgsFeature(memory.fields())
        copied.setGeometry(feature.geometry())
        values = list(feature.attributes())
        if extra_values:
            values.extend(extra_values(feature))
        copied.setAttributes(values)
        output.append(copied)
    provider.addFeatures(output)
    memory.updateExtents()
    return save_memory_layer(project, memory, layer_name, overwrite_file)


def build_station_layer(project: QgsProject, matches: dict, records: list) -> QgsVectorLayer:
    counts = {}
    for record in records:
        counts[record["origin"]] = counts.get(record["origin"], 0) + 1
        counts[record["destination"]] = counts.get(record["destination"], 0) + 1
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "记录车站", "memory")
    provider = memory.dataProvider()
    provider.addAttributes(
        [QgsField("name", QVariant.String), QgsField("trips", QVariant.Int)]
    )
    memory.updateFields()
    features = []
    for name in counts:
        value = matches[name]
        feature = QgsFeature(memory.fields())
        feature.setGeometry(
            __import__("qgis.core", fromlist=["QgsGeometry"]).QgsGeometry.fromPointXY(
                __import__("qgis.core", fromlist=["QgsPointXY"]).QgsPointXY(
                    float(value["lon"]), float(value["lat"])
                )
            )
        )
        feature.setAttributes([name, counts.get(name, 0)])
        features.append(feature)
    provider.addFeatures(features)
    memory.updateExtents()
    return save_memory_layer(project, memory, "记录车站")


def build_visited_city_layer(
    project: QgsProject,
    city_source: QgsVectorLayer,
    province_source: QgsVectorLayer,
    matches: list[dict],
) -> QgsVectorLayer:
    memory = QgsVectorLayer("MultiPolygon?crs=EPSG:4326", "去过的城市", "memory")
    provider = memory.dataProvider()
    provider.addAttributes(
        [
            QgsField("display", QVariant.String),
            QgsField("full_name", QVariant.String),
            QgsField("province", QVariant.String),
            QgsField("source", QVariant.String),
        ]
    )
    memory.updateFields()
    output = []
    for match in matches:
        source = province_source if match["source"] == "province" else city_source
        selected = None
        for feature in source.getFeatures():
            if match.get("adcode") and str(feature["adcode"]) == match["adcode"]:
                selected = feature
                break
            if not match.get("adcode") and str(feature["name"]) == match["full_name"]:
                selected = feature
                break
        if selected is None:
            raise RuntimeError(f"Missing visited city geometry: {match['source_name']}")
        copied = QgsFeature(memory.fields())
        copied.setGeometry(selected.geometry())
        copied.setAttributes(
            [match["source_name"], match["full_name"], match["province"], match["source"]]
        )
        output.append(copied)
    provider.addFeatures(output)
    memory.updateExtents()
    return save_memory_layer(project, memory, "去过的城市")


def build_visited_city_label_layer(
    project: QgsProject, visited_cities: QgsVectorLayer
) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "去过的城市标注", "memory")
    provider = memory.dataProvider()
    provider.addAttributes(
        [
            QgsField("display", QVariant.String),
            QgsField("province", QVariant.String),
        ]
    )
    memory.updateFields()
    output = []
    for source in visited_cities.getFeatures():
        point, _ = source.geometry().poleOfInaccessibility(0.01)
        if point.isEmpty():
            point = source.geometry().pointOnSurface()
        if point.isEmpty():
            point = source.geometry().centroid()
        feature = QgsFeature(memory.fields())
        feature.setGeometry(point)
        feature.setAttributes([source["display"], source["province"]])
        output.append(feature)
    provider.addFeatures(output)
    memory.updateExtents()
    return save_memory_layer(project, memory, "去过的城市标注")


def build_required_city_label_layer(
    project: QgsProject, city_labels: QgsVectorLayer
) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "重点城市标注", "memory")
    provider = memory.dataProvider()
    provider.addAttributes(
        [
            QgsField("display", QVariant.String),
            QgsField("province", QVariant.String),
        ]
    )
    memory.updateFields()
    output = []
    for source in city_labels.getFeatures():
        if str(source["display"]) not in REQUIRED_CITY_LABELS:
            continue
        feature = QgsFeature(memory.fields())
        feature.setGeometry(source.geometry())
        feature.setAttributes([source["display"], source["province"]])
        output.append(feature)
    provider.addFeatures(output)
    memory.updateExtents()
    return save_memory_layer(project, memory, "重点城市标注")


def set_polygon_labels(
    layer: QgsVectorLayer,
    field: str,
    size: float,
    color: str,
    family: str,
    priority: int,
) -> None:
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = field
    settings.placement = QgsPalLayerSettings.Horizontal
    settings.priority = priority
    settings.setFormat(text_format(size, color, family, 0.34))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_all_provinces(layer: QgsVectorLayer, visited_names: set[str]) -> None:
    field_index = layer.fields().indexFromName("name")
    categories = []
    for name in sorted(str(value) for value in layer.uniqueValues(field_index)):
        visited = name in visited_names
        symbol = QgsFillSymbol.createSimple(
            {
                "color": rgba("#D8E8F3", 224) if visited else "#EEF3F6",
                "outline_color": "#587A93" if visited else "#7B8B96",
                "outline_width": "0.52" if visited else "0.38",
                "outline_width_unit": "MM",
                "joinstyle": "round",
            }
        )
        categories.append(QgsRendererCategory(name, symbol, name))
    layer.setRenderer(QgsCategorizedSymbolRenderer("name", categories))


def style_neutral_provinces(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#F3F4F2",
            "outline_color": "#727D78",
            "outline_width": "0.38",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_all_cities(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "255,255,255,0",
            "outline_color": rgba("#A8B8C4", 130),
            "outline_width": "0.085",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_visited_cities(layer: QgsVectorLayer, for_rail: bool = False) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": rgba("#B5D3E8", 42 if for_rail else 172),
            "outline_color": rgba("#47799C", 120 if for_rail else 230),
            "outline_width": "0.14" if for_rail else "0.28",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_visited_city_labels(
    layer: QgsVectorLayer, required_only: bool = False
) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle",
                    "color": "255,255,255,0",
                    "outline_color": "255,255,255,0",
                    "size": "0",
                }
            )
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    if required_only:
        settings.fieldName = "display"
    else:
        excluded = ", ".join(f"'{name}'" for name in sorted(REQUIRED_CITY_LABELS))
        settings.fieldName = (
            f'CASE WHEN "display" NOT IN ({excluded}) THEN "display" END'
        )
        settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 10
    settings.dist = 0.0
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = True
    settings.obstacle = False
    if hasattr(settings, "allowDegradedPlacement"):
        settings.allowDegradedPlacement = True
    if hasattr(QgsPalLayerSettings, "AllowOverlapAtNoCost"):
        settings.overlapHandling = QgsPalLayerSettings.AllowOverlapAtNoCost
    settings.setFormat(
        text_format(
            6.5,
            "#183F5D" if required_only else "#244A67",
            "华文楷体",
            0.38 if required_only else 0.34,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def route_symbol(highspeed: bool) -> QgsLineSymbol:
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
        if highspeed or line is outer:
            line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def style_routes(layer: QgsVectorLayer) -> None:
    categories = [
        QgsRendererCategory("highspeed", route_symbol(True), "高铁/动车（含城际、市郊）"),
        QgsRendererCategory("conventional", route_symbol(False), "普铁"),
    ]
    layer.setRenderer(QgsCategorizedSymbolRenderer("service", categories))


def style_stations(layer: QgsVectorLayer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#FFFDF7",
            "outline_color": "#30383A",
            "outline_width": "0.22",
            "outline_width_unit": "MM",
            "size": "1.20",
            "size_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = (
        "CASE WHEN \"name\" = '清河' THEN '' "
        "WHEN \"name\" = '北京丰台' THEN '丰台站' ELSE \"name\" END"
    )
    settings.isExpression = True
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 9
    settings.dist = 0.65
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.setFormat(text_format(6.3, "#1D2527", "华文楷体", 0.38))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def add_label(
    layout,
    text,
    x,
    y,
    width,
    height,
    size,
    color,
    family,
    bold=False,
    h_align=Qt.AlignLeft,
    v_align=Qt.AlignVCenter,
):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(text_format(size, color, family, 0, bold))
    item.setHAlign(h_align)
    item.setVAlign(v_align)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    return item


def add_scale_bar(layout, map_item):
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setNumberOfSegments(3)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitsPerSegment(500)
    scale.setUnitLabel("km")
    scale.setHeight(1.2)
    scale.setLabelBarSpace(0.6)
    scale.setBoxContentSpace(0.6)
    scale.setTextFormat(text_format(9.0, "#4E5954", "思源黑体 CN", bold=True))
    scale.setLineColor(QColor("#626A66"))
    scale.setLineWidth(0.24)
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(15, 298, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(96, 12, QgsUnitTypes.LayoutMillimeters))


def add_route_legend_sample(
    layout: QgsPrintLayout,
    x: float,
    y: float,
    width: float,
    highspeed: bool,
) -> QgsLayoutItemPolyline:
    item = QgsLayoutItemPolyline(
        QPolygonF([QPointF(x, y), QPointF(x + width, y)]), layout
    )
    item.setSymbol(route_symbol(highspeed))
    layout.addLayoutItem(item)
    return item


def make_layout(
    project: QgsProject,
    name: str,
    title: str,
    subtitle: str,
    layers: list,
    output: Path,
    rail_legend: bool = False,
    inset_layers: list | None = None,
) -> None:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name)
    layout.pageCollection().page(0).setPageSize(
        QgsLayoutSize(*PAGE_SIZE, QgsUnitTypes.LayoutMillimeters)
    )
    project.layoutManager().addLayout(layout)
    add_label(layout, title, 12, 3, 300, 16, 27, "#111111", "华文新魏")
    add_label(layout, subtitle, 13, 19, 402, 17, 13.0, "#111111", "华文楷体")

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#77807B"))
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
    map_item.zoomToExtent(projected_extent(project, CHINA_EXTENT))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)
    add_scale_bar(layout, map_item)

    if inset_layers:
        inset = QgsLayoutItemMap(layout)
        inset.setId("南海诸岛插图")
        inset.setFrameEnabled(True)
        inset.setFrameStrokeColor(QColor("#6F7772"))
        inset.setFrameStrokeWidth(
            QgsLayoutMeasurement(0.18, QgsUnitTypes.LayoutMillimeters)
        )
        layout.addLayoutItem(inset)
        inset.attemptMove(
            QgsLayoutPoint(INSET_FRAME[0], INSET_FRAME[1], QgsUnitTypes.LayoutMillimeters)
        )
        inset.attemptResize(
            QgsLayoutSize(INSET_FRAME[2], INSET_FRAME[3], QgsUnitTypes.LayoutMillimeters)
        )
        inset.zoomToExtent(projected_extent(project, SOUTH_CHINA_SEA_EXTENT))
        inset.setLayers(inset_layers)
        inset.setKeepLayerSet(True)
        add_label(
            layout,
            "南海诸岛",
            INSET_FRAME[0] + INSET_FRAME[2] - 42,
            INSET_FRAME[1] + INSET_FRAME[3] - 9,
            39,
            7,
            5.5,
            "#111111",
            "华文楷体",
            h_align=Qt.AlignRight,
            v_align=Qt.AlignBottom,
        )
    if rail_legend:
        add_route_legend_sample(layout, 125, 301.5, 22, True)
        add_label(layout, "高铁/动车（含城际、市郊）", 151, 297, 88, 9, 12.0, "#4E5954", "思源黑体 CN", bold=True)
        add_route_legend_sample(layout, 245, 301.5, 22, False)
        add_label(layout, "普铁", 271, 297, 30, 9, 12.0, "#4E5954", "思源黑体 CN", bold=True)
    add_label(layout, "数据截至 2026.08", 343, 297, 75, 9, 12.0, "#4E5954", "思源黑体 CN", bold=True)

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 320
    output.unlink(missing_ok=True)
    result = exporter.exportToImage(str(output), settings)
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Export failed for {name}: {result}")


def main() -> int:
    global ROUTE_GPKG, OUTPUT_DIR, OUTPUT_GPKG, OUTPUT_PROJECT, VISIT_IMAGE, RAIL_IMAGE
    args = parse_args()
    ROUTE_GPKG = args.route_gpkg.resolve()
    OUTPUT_DIR = args.output_dir.resolve()
    OUTPUT_GPKG = OUTPUT_DIR / "全国足迹_数据.gpkg"
    OUTPUT_PROJECT = OUTPUT_DIR / "全国足迹.qgz"
    VISIT_IMAGE = OUTPUT_DIR / "去过的省市.png"
    RAIL_IMAGE = OUTPUT_DIR / "铁路路线.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    parsed = json.loads(PARSED.read_text(encoding="utf-8"))
    matches = json.loads(MATCH_REPORT.read_text(encoding="utf-8"))
    visited_provinces = {place["province_full"] for place in parsed["places"]}
    province_display = {
        place["province_full"]: place["province"] for place in parsed["places"]
    }

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        albers = QgsCoordinateReferenceSystem()
        if not albers.createFromProj(CHINA_ALBERS_PROJ):
            raise RuntimeError("Unable to create China Albers CRS")
        project.setCrs(albers)
        all_province_source = QgsVectorLayer(str(PROVINCE_JSON), "省级行政区源", "ogr")
        all_city_source = QgsVectorLayer(str(CITY_JSON), "地级行政区源", "ogr")
        route_source = QgsVectorLayer(
            f"{ROUTE_GPKG}|layername=rail_routes", "铁路记录源", "ogr"
        )
        for layer in (all_province_source, all_city_source, route_source):
            if not layer.isValid():
                raise RuntimeError(f"Invalid source: {layer.source()}")

        OUTPUT_GPKG.unlink(missing_ok=True)
        all_provinces = copy_source_layer(
            project, all_province_source, "全国省级行政区", overwrite_file=True
        )
        all_cities = copy_source_layer(project, all_city_source, "全国地级行政区")
        rail_provinces = copy_source_layer(
            project, all_province_source, "铁路图省级行政区"
        )
        visited_city_layer = build_visited_city_layer(
            project,
            all_city_source,
            all_province_source,
            matches["city_matches"],
        )
        visited_city_labels = build_visited_city_label_layer(
            project, visited_city_layer
        )
        required_city_labels = build_required_city_label_layer(
            project, visited_city_labels
        )
        visited_province_layer = copy_source_layer(
            project,
            all_province_source,
            "去过的省级行政区",
            predicate=lambda feature: str(feature["name"]) in visited_provinces,
            extra_fields=[QgsField("display", QVariant.String)],
            extra_values=lambda feature: [province_display[str(feature["name"])]],
        )
        routes = copy_source_layer(project, route_source, "铁路行程轨迹")
        stations = build_station_layer(
            project, matches["station_matches"], parsed["rail_records"]
        )

        style_all_provinces(all_provinces, visited_provinces)
        style_neutral_provinces(rail_provinces)
        style_all_cities(all_cities)
        style_visited_cities(visited_city_layer, False)
        style_visited_city_labels(visited_city_labels)
        style_visited_city_labels(required_city_labels, required_only=True)
        visited_province_layer.setRenderer(
            QgsSingleSymbolRenderer(
                QgsFillSymbol.createSimple(
                    {
                        "color": "255,255,255,0",
                        "outline_color": "#4B6F8A",
                        "outline_width": "0.52",
                        "outline_width_unit": "MM",
                    }
                )
            )
        )
        style_routes(routes)
        style_stations(stations)

        legacy = None
        if ROUTE_SOURCES_GPKG.exists():
            legacy = QgsVectorLayer(
                f"{ROUTE_SOURCES_GPKG}|layername=railway",
                "原铁路轨迹（参考）",
                "ogr",
            )
            if legacy.isValid():
                project.addMapLayer(legacy)
                project.layerTreeRoot().findLayer(legacy.id()).setItemVisibilityChecked(False)

        # Lists are top-to-bottom in a locked layout map.
        visit_layers = [
            required_city_labels,
            visited_city_labels,
            visited_city_layer,
            visited_province_layer,
            all_cities,
            all_provinces,
        ]
        make_layout(
            project,
            "去过的省市",
            "我的行旅版图",
            "21 个省级行政区 · 87 个城市",
            visit_layers,
            VISIT_IMAGE,
            inset_layers=[all_cities, all_provinces],
        )

        rail_layers = [stations, routes, all_cities, rail_provinces]
        make_layout(
            project,
            "铁路路线",
            "坐火车走过的地方",
            "133 段乘车记录｜普铁 44 次 · 高铁/动车 89 次｜总里程 54,760 km\n其中普铁 21,740 km，高铁/动车 33,020 km｜抵达 65 个城市的 129 座车站",
            rail_layers,
            RAIL_IMAGE,
            rail_legend=True,
            inset_layers=[all_cities, rail_provinces],
        )

        project.setTitle("全国足迹与铁路路线")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(projected_extent(project, CHINA_EXTENT), project.crs())
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)
        if hasattr(project, "setFilePathStorage"):
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        if not project.write(str(OUTPUT_PROJECT)):
            raise RuntimeError(f"Unable to save project: {OUTPUT_PROJECT}")
        print(VISIT_IMAGE)
        print(RAIL_IMAGE)
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
