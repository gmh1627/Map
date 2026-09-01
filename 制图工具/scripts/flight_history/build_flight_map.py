"""Build a dark, Umetrip-inspired flight history map from the travel log."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont
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
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
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
)


RAILWAY_ROOT = Path(r"F:\Desktop\Railway")
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "全国专题图" / "航线图"
OUTPUT_GPKG = OUTPUT_DIR / "航线数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "航线图.qgz"
OUTPUT_PNG = OUTPUT_DIR / "航线图.png"
PROVINCE_SOURCE = RAILWAY_ROOT / "province" / "province.json"

PAGE_SIZE = (430.0, 330.0)
MAP_FRAME = (12.0, 40.0, 406.0, 248.0)
INSET_FRAME = (350.0, 208.0, 68.0, 80.0)
CHINA_EXTENT = QgsRectangle(73.0, 17.4, 135.5, 54.6)
SOUTH_CHINA_SEA_EXTENT = QgsRectangle(105.0, 2.5, 124.0, 24.0)
CHINA_ALBERS_PROJ = (
    "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 "
    "+datum=WGS84 +units=m +no_defs +type=crs"
)
ARROW_ENDPOINT_OFFSET = 0.14
ARROW_TANGENT_WINDOW = 0.025


# Coordinates are from the OurAirports airport dataset, checked 2026-07-30.
AIRPORTS = {
    "PEK": ("北京首都", 116.596702, 40.077349),
    "NNG": ("南宁吴圩", 108.181922, 22.598071),
    "ZHA": ("湛江吴川", 110.590278, 21.481667),
    "HFE": ("合肥新桥", 116.976900, 31.987790),
    "XIY": ("西安咸阳", 108.762385, 34.442207),
    "SWA": ("揭阳潮汕", 116.503300, 23.552000),
    "CAN": ("广州白云", 113.299004, 23.392401),
    "SZX": ("深圳宝安", 113.803262, 22.639474),
    "KOW": ("赣州黄金", 114.778889, 25.853333),
    "PKX": ("北京大兴", 116.413967, 39.501289),
    "JGN": ("嘉峪关酒泉", 98.339344, 39.859052),
    "DNH": ("敦煌莫高", 94.812827, 40.161953),
    "LHW": ("兰州中川", 103.620003, 36.515202),
}


FLIGHTS = (
    ("2016.1", "PEK", "NNG", "CA1335", 2250, None),
    ("2022.8", "ZHA", "HFE", "9C6308", 1594, None),
    ("2022.12", "HFE", "ZHA", "MU6409", 1594, None),
    ("2023.2", "ZHA", "HFE", "9C6308", 1594, None),
    ("2024.7", "HFE", "XIY", "MU2385", 960, None),
    ("2024.7", "XIY", "HFE", "MU5570", 960, None),
    ("2024.8", "ZHA", "SWA", "MU9070", 750, None),
    ("2024.8", "SWA", "HFE", "MU9062", 1020, None),
    ("2025.1", "HFE", "CAN", "MU5287", 1105, None),
    ("2025.2", "SZX", "HFE", "CZ5367", 1191, None),
    ("2025.9", "ZHA", "HFE", "MU9092", 1594, "KOW"),
    ("2026.4", "PKX", "JGN", "MF8211", 2074, None),
    ("2026.4", "JGN", "PKX", "MF8212", 2074, None),
    ("2026.6", "DNH", "LHW", "MU2234", 1048, None),
    ("2026.6", "LHW", "HFE", "MU9977", 1473, None),
    # 中国国航，空客321-252(NX)。
    ("2026.8", "PEK", "HFE", "CA1845", 959, None),
)


def text_format(size: float, color: str, family: str, buffer: float = 0.0, bold: bool = False) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont(family)
    font.setPointSizeF(size)
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer:
        settings = QgsTextBufferSettings()
        settings.setEnabled(True)
        settings.setColor(QColor("#06131B"))
        settings.setSize(buffer)
        settings.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(settings)
    return fmt


def projected_extent(project: QgsProject, extent: QgsRectangle) -> QgsRectangle:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"), project.crs(), project.transformContext()
    )
    return transform.transformBoundingBox(extent)


def add_label(
    layout: QgsPrintLayout,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    size: float,
    color: str,
    family: str,
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignLeft,
) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(text_format(size, color, family, bold=bold))
    item.setHAlign(align)
    item.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    return item


def write_layer(layer: QgsVectorLayer, name: str, first: bool = False) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile if first
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), QgsProject.instance().transformContext(), options
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to write {name}: {result}")
    saved = QgsVectorLayer(f"{OUTPUT_GPKG}|layername={name}", layer.name(), "ogr")
    if not saved.isValid():
        raise RuntimeError(f"Unable to reload {name}")
    QgsProject.instance().addMapLayer(saved)
    return saved


def quadratic_curve(
    start: tuple[float, float],
    end: tuple[float, float],
    bend: float,
    samples: int = 56,
) -> list[QgsPointXY]:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    distance = max(math.hypot(dx, dy), 0.001)
    normal_x, normal_y = -dy / distance, dx / distance
    offset = min(8.8, max(0.95, distance * bend))
    cx = (x1 + x2) / 2 + normal_x * offset
    cy = (y1 + y2) / 2 + normal_y * offset
    points = []
    for index in range(samples + 1):
        t = index / samples
        omt = 1 - t
        points.append(
            QgsPointXY(
                omt * omt * x1 + 2 * omt * t * cx + t * t * x2,
                omt * omt * y1 + 2 * omt * t * cy + t * t * y2,
            )
        )
    return points


def quadratic_curve_through(
    start: tuple[float, float],
    via: tuple[float, float],
    end: tuple[float, float],
    samples: int = 56,
) -> list[QgsPointXY]:
    """Return one smooth quadratic arc which passes exactly through ``via``."""
    first_distance = math.hypot(via[0] - start[0], via[1] - start[1])
    second_distance = math.hypot(end[0] - via[0], end[1] - via[1])
    t_via = first_distance / max(first_distance + second_distance, 0.001)
    t_via = min(0.78, max(0.22, t_via))
    one_minus_t = 1.0 - t_via
    denominator = 2.0 * one_minus_t * t_via
    control_x = (
        via[0] - one_minus_t * one_minus_t * start[0] - t_via * t_via * end[0]
    ) / denominator
    control_y = (
        via[1] - one_minus_t * one_minus_t * start[1] - t_via * t_via * end[1]
    ) / denominator
    points = []
    parameters = sorted({index / samples for index in range(samples + 1)} | {t_via})
    for t in parameters:
        omt = 1.0 - t
        points.append(
            QgsPointXY(
                omt * omt * start[0] + 2.0 * omt * t * control_x + t * t * end[0],
                omt * omt * start[1] + 2.0 * omt * t * control_y + t * t * end[1],
            )
        )
    return points


def build_flight_layers(project: QgsProject) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    routes = QgsVectorLayer("LineString?crs=EPSG:4326", "飞行航线", "memory")
    routes.dataProvider().addAttributes(
        [
            QgsField("seq", QVariant.Int), QgsField("date", QVariant.String),
            QgsField("origin", QVariant.String), QgsField("destination", QVariant.String),
            QgsField("flight", QVariant.String), QgsField("distance_km", QVariant.Int),
            QgsField("via", QVariant.String),
        ]
    )
    routes.updateFields()
    arrows = QgsVectorLayer("Point?crs=EPSG:4326", "航向箭头", "memory")
    arrows.dataProvider().addAttributes([QgsField("seq", QVariant.Int), QgsField("angle", QVariant.Double)])
    arrows.updateFields()

    directed_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    route_features = []
    arrow_features = []
    for seq, (date, origin, destination, flight, distance_km, via) in enumerate(FLIGHTS, 1):
        # The normal vector reverses with flight direction. Keeping bend positive
        # therefore puts return flights on the opposite side of the direct chord,
        # while repeated flights in one direction fan out cleanly.
        directed_key = (origin, destination)
        occurrence = directed_counts[directed_key]
        directed_counts[directed_key] += 1
        bend = 0.320 + occurrence * 0.065
        start = AIRPORTS[origin][1:]
        end = AIRPORTS[destination][1:]
        if via:
            midpoint = AIRPORTS[via][1:]
            points = quadratic_curve_through(start, midpoint, end)
        else:
            points = quadratic_curve(start, end, bend)
        geometry = QgsGeometry.fromPolylineXY(points)
        feature = QgsFeature(routes.fields())
        feature.setGeometry(geometry)
        feature.setAttributes([seq, date, origin, destination, flight, distance_km, via or ""])
        route_features.append(feature)

        arrow_distance = max(0.0, geometry.length() - ARROW_ENDPOINT_OFFSET)
        arrow_point = geometry.interpolate(arrow_distance)
        before = geometry.interpolate(max(0.0, arrow_distance - ARROW_TANGENT_WINDOW)).asPoint()
        after = geometry.interpolate(min(geometry.length(), arrow_distance + ARROW_TANGENT_WINDOW)).asPoint()
        angle = math.degrees(math.atan2(after.x() - before.x(), after.y() - before.y())) % 360
        arrow = QgsFeature(arrows.fields())
        arrow.setGeometry(arrow_point)
        arrow.setAttributes([seq, angle])
        arrow_features.append(arrow)
    routes.dataProvider().addFeatures(route_features)
    arrows.dataProvider().addFeatures(arrow_features)
    routes.updateExtents()
    arrows.updateExtents()

    airport_counts = Counter(code for flight in FLIGHTS for code in (flight[1], flight[2]))
    airport_counts["KOW"] += 1
    airports = QgsVectorLayer("Point?crs=EPSG:4326", "机场节点", "memory")
    airports.dataProvider().addAttributes(
        [QgsField("code", QVariant.String), QgsField("name", QVariant.String), QgsField("trips", QVariant.Int), QgsField("role", QVariant.String)]
    )
    airports.updateFields()
    airport_features = []
    for code, (name, lon, lat) in AIRPORTS.items():
        feature = QgsFeature(airports.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        role = "hub" if airport_counts[code] >= 3 else "airport"
        feature.setAttributes([code, name, airport_counts[code], role])
        airport_features.append(feature)
    airports.dataProvider().addFeatures(airport_features)
    airports.updateExtents()

    return (
        write_layer(routes, "flight_routes", first=True),
        write_layer(arrows, "flight_arrows"),
        write_layer(airports, "airports"),
    )


def style_routes(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol()
    glow = QgsSimpleLineSymbolLayer(QColor(73, 174, 198, 66), 1.05)
    core = QgsSimpleLineSymbolLayer(QColor(173, 224, 235, 172), 0.34)
    for line in (glow, core):
        line.setWidthUnit(Qgis.RenderUnit.Millimeters)
        line.setPenCapStyle(Qt.RoundCap)
        line.setPenJoinStyle(Qt.RoundJoin)
    symbol.changeSymbolLayer(0, glow)
    symbol.appendSymbolLayer(core)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_arrows(layer: QgsVectorLayer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "triangle", "color": "#B9E5EE", "outline_color": "#6CB8C9",
            "outline_width": "0.12", "outline_width_unit": "MM", "size": "1.35", "size_unit": "MM",
        }
    )
    symbol.setOpacity(1.0)
    symbol.symbolLayer(0).setDataDefinedProperty(QgsSymbolLayer.PropertyAngle, QgsProperty.fromField("angle"))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_airports(layer: QgsVectorLayer) -> None:
    def marker(size: float, fill: str, outline: str) -> QgsMarkerSymbol:
        return QgsMarkerSymbol.createSimple(
            {
                "name": "circle", "color": fill, "outline_color": outline,
                "outline_width": "0.34", "outline_width_unit": "MM",
                "size": str(size), "size_unit": "MM",
            }
        )

    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "role",
            [
                QgsRendererCategory("airport", marker(1.45, "#DDF7FB", "#61B7CA"), "机场"),
                QgsRendererCategory("hub", marker(2.05, "#F2FEFF", "#70D0E2"), "主要机场"),
            ],
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 9
    settings.dist = 0.72
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(text_format(5.4, "#87C3D2", "思源黑体 CN", 0.38))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_provinces(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {"color": "#0A2A3A", "outline_color": "#194B60", "outline_width": "0.18", "outline_width_unit": "MM"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = (
        "regexp_replace(\"name\", '(壮族自治区|回族自治区|维吾尔自治区|特别行政区|自治区|省|市)$', '')"
    )
    settings.isExpression = True
    settings.placement = QgsPalLayerSettings.Horizontal
    settings.priority = 2
    settings.setFormat(text_format(5.0, "#245A70", "思源黑体 CN"))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def add_scale(layout: QgsPrintLayout, map_item: QgsLayoutItemMap) -> None:
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitsPerSegment(500)
    scale.setUnitLabel("km")
    scale.setTextFormat(text_format(9.0, "#FFFFFF", "思源黑体 CN", bold=True))
    scale.setLineColor(QColor("#FFFFFF"))
    scale.setLineWidth(0.22)
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(15, 297, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(90, 10, QgsUnitTypes.LayoutMillimeters))


def build_layout(project: QgsProject, main_layers: list, inset_layers: list) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("飞行航迹")
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(*PAGE_SIZE, QgsUnitTypes.LayoutMillimeters))
    page.setBackgroundColor(QColor("#06131B"))
    page.setPageStyleSymbol(
        QgsFillSymbol.createSimple({"color": "#06131B", "outline_style": "no"})
    )
    project.layoutManager().addLayout(layout)

    add_label(layout, "飞行航迹", 12, 3, 190, 16, 27, "#F2FAFC", "华文新魏")
    add_label(
        layout,
        "16 次飞行｜累计 22,240 km｜抵达 12 座城市、13 座机场（含经停）",
        13,
        20,
        390,
        13,
        13.0,
        "#FFFFFF",
        "华文楷体",
    )

    main = QgsLayoutItemMap(layout)
    main.setId("主图")
    main.setBackgroundColor(QColor("#071923"))
    main.setFrameEnabled(True)
    main.setFrameStrokeColor(QColor("#527A89"))
    main.setFrameStrokeWidth(QgsLayoutMeasurement(0.22, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(main)
    main.attemptMove(QgsLayoutPoint(MAP_FRAME[0], MAP_FRAME[1], QgsUnitTypes.LayoutMillimeters))
    main.attemptResize(QgsLayoutSize(MAP_FRAME[2], MAP_FRAME[3], QgsUnitTypes.LayoutMillimeters))
    main.zoomToExtent(projected_extent(project, CHINA_EXTENT))
    main.setLayers(main_layers)
    main.setKeepLayerSet(True)
    add_scale(layout, main)

    inset = QgsLayoutItemMap(layout)
    inset.setId("南海诸岛插图")
    inset.setBackgroundColor(QColor("#071923"))
    inset.setFrameEnabled(True)
    inset.setFrameStrokeColor(QColor("#416879"))
    inset.setFrameStrokeWidth(QgsLayoutMeasurement(0.18, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(inset)
    inset.attemptMove(QgsLayoutPoint(INSET_FRAME[0], INSET_FRAME[1], QgsUnitTypes.LayoutMillimeters))
    inset.attemptResize(QgsLayoutSize(INSET_FRAME[2], INSET_FRAME[3], QgsUnitTypes.LayoutMillimeters))
    inset.zoomToExtent(projected_extent(project, SOUTH_CHINA_SEA_EXTENT))
    inset.setLayers(inset_layers)
    inset.setKeepLayerSet(True)
    add_label(layout, "南海诸岛", 376, 277, 38, 7, 5.2, "#4F8194", "思源黑体 CN", align=Qt.AlignRight)

    add_label(layout, "数据截至 2026.08", 343, 297, 75, 9, 12.0, "#FFFFFF", "思源黑体 CN", bold=True)
    return layout


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)
    for source in (PROVINCE_SOURCE,):
        if not source.exists():
            raise FileNotFoundError(source)
    if sum(flight[4] for flight in FLIGHTS) != 22240:
        raise RuntimeError("Flight mileage total no longer matches the article")

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        crs = QgsCoordinateReferenceSystem()
        if not crs.createFromProj(CHINA_ALBERS_PROJ):
            raise RuntimeError("Unable to create China Albers CRS")
        project.setCrs(crs)

        provinces = QgsVectorLayer(str(PROVINCE_SOURCE), "省级行政区", "ogr")
        if not provinces.isValid():
            raise RuntimeError("Invalid province layer")
        project.addMapLayer(provinces)
        style_provinces(provinces)

        routes, arrows, airports = build_flight_layers(project)
        style_routes(routes)
        style_arrows(arrows)
        style_airports(airports)
        project.layerTreeRoot().findLayer(arrows.id()).setItemVisibilityChecked(True)
        main_layers = [airports, arrows, routes, provinces]
        layout = build_layout(project, main_layers, [provinces])

        project.setTitle("飞行航迹")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(projected_extent(project, CHINA_EXTENT), project.crs())
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)
        if hasattr(project, "setFilePathStorage"):
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        OUTPUT_QGZ.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_QGZ)):
            raise RuntimeError(f"Unable to save {OUTPUT_QGZ}")

        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 320
        OUTPUT_PNG.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Image export failed: {result}")

        report = {
            "image": str(OUTPUT_PNG), "project": str(OUTPUT_QGZ), "data": str(OUTPUT_GPKG),
            "flight_count": len(FLIGHTS), "distance_km": sum(flight[4] for flight in FLIGHTS),
            "airport_count": len(AIRPORTS), "via_airport": "KOW",
        }
        (OUTPUT_DIR / "构建报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
