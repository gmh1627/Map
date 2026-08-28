"""Build the editable overview map for the Hexi Corridor trip."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemMap,
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
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)


RAILWAY_ROOT = Path(r"F:\Desktop\Railway")
COMMON_DIR = RAILWAY_ROOT / "制图工具" / "scripts" / "regional_overviews"
sys.path.insert(0, str(COMMON_DIR))
import build_overviews as ov  # noqa: E402


OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "区域线路图" / "走河西"
OUTPUT_GPKG = OUTPUT_DIR / "走河西_数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "走河西.qgz"
OUTPUT_PNG = OUTPUT_DIR / "走河西.png"
COUNTY_SOURCE = RAILWAY_ROOT / "city" / "gansu_focus_counties.geojson"
EXTENT = (93.50, 30.88, 118.05, 43.15)
PAGE = (360.0, 238.0)
MAP_FRAME = (12.0, 51.0, 336.0, 162.0)

VISITED_CITIES = (
    "天水市", "定西市", "兰州市", "临夏回族自治州", "武威市",
    "张掖市", "酒泉市", "嘉峪关市",
)
FOCUS_COUNTIES = (
    "甘谷县", "武山县", "陇西县", "永靖县", "肃南裕固族自治县",
    "玉门市", "瓜州县", "敦煌市",
)
STATIONS = (
    "合肥", "天水", "甘谷", "武山", "陇西", "定西", "定西北", "兰州西",
    "兰州", "武威", "武威南", "张掖", "张掖西", "酒泉南", "酒泉",
    "嘉峪关", "嘉峪关南", "敦煌",
)
STATION_LABELS = {
    "敦煌站": (94.55, 40.34),
    "嘉峪关南站": (97.70, 39.58),
    "嘉峪关站": (97.90, 40.00),
    "酒泉站": (98.60, 39.45),
    "酒泉南站": (99.00, 39.90),
    "张掖西站": (99.95, 38.75),
    "张掖站": (100.95, 39.12),
    "武威站": (102.10, 37.91787),
    "武威南站": (102.35, 37.70),
    "兰州西站": (103.25, 35.96879),
    "兰州站": (104.23, 36.10),
    "定西北站": (104.10, 35.53481),
    "定西站": (104.95, 35.75),
    "陇西站": (104.50, 34.84),
    "武山站": (104.86, 34.56),
    "甘谷站": (105.25, 34.94),
    "天水站": (105.98, 34.72),
    "合肥站": (117.03, 31.72),
}
CITY_LABELS = {
    "合肥": (117.30, 31.70),
    "天水": (105.78, 34.58),
    "定西": (104.59, 35.58),
    "兰州": (103.72, 36.10),
    "临夏": (103.19, 35.61),
    "武威": (102.64, 37.93),
    "张掖": (100.46, 38.95),
    "酒泉": (98.62, 39.67),
    "嘉峪关": (98.20, 39.88),
}
COUNTY_LABEL_NAMES = {
    "肃南裕固族自治县": "肃南县",
    "玉门市": "玉门市",
    "瓜州县": "瓜州县",
}
AIRPORTS = {
    "敦煌莫高": (94.8092, 40.1611),
    "兰州中川": (103.6208, 36.5152),
    "合肥新桥": (116.9769, 31.9878),
}
AIRPORT_LABELS = {
    "敦煌莫高": (94.81, 39.94),
    "兰州中川": (103.85, 36.42),
    "合肥新桥": (117.38, 32.15),
}


def sql_strings(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def curve_points(start: tuple[float, float], end: tuple[float, float], bend: float) -> list[QgsPointXY]:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    cx = mx - dy / length * bend
    cy = my + dx / length * bend
    points = []
    for index in range(97):
        t = index / 96.0
        omt = 1.0 - t
        points.append(QgsPointXY(omt * omt * x1 + 2 * omt * t * cx + t * t * x2,
                                  omt * omt * y1 + 2 * omt * t * cy + t * t * y2))
    return points


def build_points(project: QgsProject, values: dict[str, tuple[float, float]], name: str, layer_name: str) -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
    layer.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    layer.updateFields()
    features = []
    for label, (lon, lat) in values.items():
        feature = QgsFeature(layer.fields())
        feature.setAttributes([label])
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    project.addMapLayer(layer)
    saved = ov.write_layer(layer, OUTPUT_GPKG, layer_name)
    project.removeMapLayer(layer.id())
    return saved


def style_labels(
    layer: QgsVectorLayer,
    size: float,
    color: str,
    family: str = "华文新魏",
    buffer_size: float = 1.0,
) -> None:
    symbol = QgsMarkerSymbol.createSimple({"name": "circle", "size": "0", "outline_style": "no"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.displayAll = True
    settings.priority = 10
    text = QgsTextFormat()
    text.setFont(QFont(family))
    text.setSize(size)
    text.setColor(QColor(color))
    if buffer_size > 0:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(buffer_size)
        buffer.setColor(QColor(255, 255, 255, 225))
        text.setBuffer(buffer)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def build_county_labels(project: QgsProject, counties: QgsVectorLayer) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "重点县市名", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for source in counties.getFeatures():
        full_name = str(source["name"])
        display_name = COUNTY_LABEL_NAMES.get(full_name)
        if not display_name:
            continue
        point, _ = source.geometry().poleOfInaccessibility(0.01)
        if point.isEmpty():
            point = source.geometry().pointOnSurface()
        if point.isEmpty():
            point = source.geometry().centroid()
        feature = QgsFeature(memory.fields())
        feature.setAttributes([display_name])
        feature.setGeometry(point)
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    project.addMapLayer(memory)
    saved = ov.write_layer(memory, OUTPUT_GPKG, "county_labels")
    project.removeMapLayer(memory.id())
    return saved


def build_flights(project: QgsProject) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    routes = QgsVectorLayer("LineString?crs=EPSG:4326", "返程航线", "memory")
    routes.dataProvider().addAttributes([QgsField("leg", QVariant.String)])
    routes.updateFields()
    arrows = QgsVectorLayer("Point?crs=EPSG:4326", "航向箭头", "memory")
    arrows.dataProvider().addAttributes(
        [QgsField("leg", QVariant.String), QgsField("angle", QVariant.Double)]
    )
    arrows.updateFields()
    legs = (("敦煌莫高-兰州中川", "敦煌莫高", "兰州中川", 4.20),
            ("兰州中川-合肥新桥", "兰州中川", "合肥新桥", 4.35))
    features = []
    arrow_features = []
    for label, origin, destination, bend in legs:
        geometry = QgsGeometry.fromPolylineXY(
            curve_points(AIRPORTS[origin], AIRPORTS[destination], bend)
        )
        feature = QgsFeature(routes.fields())
        feature.setAttributes([label])
        feature.setGeometry(geometry)
        features.append(feature)
        arrow_distance = geometry.length() * 0.995
        arrow_point = geometry.interpolate(arrow_distance)
        before = geometry.interpolate(
            max(0, arrow_distance - geometry.length() * 0.012)
        ).asPoint()
        after = geometry.interpolate(
            min(geometry.length(), arrow_distance + geometry.length() * 0.012)
        ).asPoint()
        angle = math.degrees(
            math.atan2(after.x() - before.x(), after.y() - before.y())
        ) % 360
        arrow = QgsFeature(arrows.fields())
        arrow.setGeometry(arrow_point)
        arrow.setAttributes([label, angle])
        arrow_features.append(arrow)
    routes.dataProvider().addFeatures(features)
    arrows.dataProvider().addFeatures(arrow_features)
    routes.updateExtents()
    arrows.updateExtents()
    project.addMapLayer(routes)
    project.addMapLayer(arrows)
    memory_routes = routes
    routes = ov.write_layer(memory_routes, OUTPUT_GPKG, "flight_routes")
    project.removeMapLayer(memory_routes.id())
    memory_arrows = arrows
    arrows = ov.write_layer(memory_arrows, OUTPUT_GPKG, "flight_arrows")
    project.removeMapLayer(memory_arrows.id())
    symbol = QgsLineSymbol()
    core = QgsSimpleLineSymbolLayer(QColor("#367FA8"), 0.58)
    core.setWidthUnit(Qgis.RenderUnit.Millimeters)
    core.setPenCapStyle(Qt.RoundCap)
    core.setPenJoinStyle(Qt.RoundJoin)
    symbol.changeSymbolLayer(0, core)
    routes.setRenderer(QgsSingleSymbolRenderer(symbol))

    arrow_symbol = QgsMarkerSymbol.createSimple({
        "name": "triangle", "color": "#367FA8", "outline_color": "#245E7B",
        "outline_width": "0.14", "outline_width_unit": "MM", "size": "1.7", "size_unit": "MM",
    })
    arrow_symbol.setOpacity(1.0)
    arrow_symbol.symbolLayer(0).setDataDefinedProperty(
        QgsSymbolLayer.PropertyAngle, QgsProperty.fromField("angle")
    )
    arrows.setRenderer(QgsSingleSymbolRenderer(arrow_symbol))

    airports = build_points(project, AIRPORTS, "机场", "airports")
    airports.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({
        "name": "circle", "color": "#E9F7FB", "outline_color": "#367FA8",
        "outline_width": "0.30", "outline_width_unit": "MM", "size": "1.4", "size_unit": "MM",
    })))
    airports.setLabelsEnabled(False)
    return routes, arrows, airports


def add_flight_legend(layout: QgsPrintLayout, x: float, y: float) -> None:
    item = ov.QgsLayoutItemPolyline(QPolygonF([QPointF(0, 0), QPointF(24, 0)]), layout)
    symbol = QgsLineSymbol.createSimple({"line_color": "#367FA8", "line_width": "0.52", "line_width_unit": "MM"})
    item.setSymbol(symbol)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y + 3.7, QgsUnitTypes.LayoutMillimeters))
    ov.add_label(layout, "航线", x + 27, y, 24, 7, 10.0, "思源黑体 CN", "#48555C", bold=True)


def build_layout(project: QgsProject, layers: list[QgsVectorLayer], services: set[str]) -> QgsPrintLayout:
    page_w, page_h = PAGE
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("走河西")
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(page_w, page_h, QgsUnitTypes.LayoutMillimeters))
    project.layoutManager().addLayout(layout)
    ov.add_label(layout, "走河西", 12, 2, 180, 16, 27, "华文新魏")
    ov.add_label(layout, "天水（含甘谷县、武山县） · 定西（含陇西县） · 兰州 · 临夏永靖县 · 武威 · 张掖（含肃南县） · 酒泉（含玉门市、瓜州县、敦煌市） · 嘉峪关", 13, 18, 334, 11, 13.0, "华文楷体")
    ov.add_label(layout, "去程 11 趟列车（含动车），总里程 2631 km · 返程 2 段航程，共 2521 km", 13, 29, 334, 9, 13.0, "华文楷体")
    ov.add_label(layout, "2026.05.30—06.15", 13, 39, 110, 10, 13.0, "华文楷体")

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#69777C"))
    map_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.24, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(MAP_FRAME[0], MAP_FRAME[1], QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(MAP_FRAME[2], MAP_FRAME[3], QgsUnitTypes.LayoutMillimeters))
    map_item.zoomToExtent(ov.projected_extent(project, EXTENT))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)
    ov.add_scale(layout, map_item, MAP_FRAME[1] + MAP_FRAME[3] + 4, 500)

    x, y = 188.0, MAP_FRAME[1] + MAP_FRAME[3] + 1.0
    if "highspeed" in services:
        ov.add_route_legend_sample(layout, x, y + 3.7, 22, True)
        ov.add_label(layout, "高铁/动车", x + 25, y, 34, 7, 10.0, "思源黑体 CN", "#48555C", bold=True)
        x += 62
    if "conventional" in services:
        ov.add_route_legend_sample(layout, x, y + 3.7, 22, False)
        ov.add_label(layout, "普铁", x + 25, y, 24, 7, 10.0, "思源黑体 CN", "#48555C", bold=True)
        x += 54
    add_flight_legend(layout, x, y)
    return layout


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

        cities = ov.add_layer(project, ov.CITY_SOURCE, "地级行政区")
        ov.style_base_admin(cities)
        visited = ov.add_layer(project, ov.CITY_SOURCE, "去过的城市", subset=f'"name" IN ({sql_strings(VISITED_CITIES)})')
        ov.style_highlight(visited)
        hefei = ov.add_layer(project, ov.CITY_SOURCE, "起点城市", subset='"name" = \'合肥市\'')
        ov.style_highlight(hefei, role="start")
        counties = ov.add_layer(project, COUNTY_SOURCE, "重点县市", subset=f'"name" IN ({sql_strings(FOCUS_COUNTIES)})')
        ov.style_focus_area(counties)

        route_source = ov.add_layer(project, ov.ROUTE_GPKG, "路线源数据", "rail_routes", subset='"seq" >= 115 AND "seq" <= 125')
        routes = ov.write_layer(route_source, OUTPUT_GPKG, "trip_route", first=True)
        routes.setName("实际铁路行程")
        ov.style_trip_routes(routes)
        services = {str(feature["service"]) for feature in routes.getFeatures()}
        project.removeMapLayer(route_source.id())
        provinces = ov.build_province_boundaries_from_cities(
            cities, OUTPUT_GPKG, EXTENT
        )
        highlighted_city_boundaries = ov.build_highlighted_city_boundaries(
            cities, OUTPUT_GPKG, set(VISITED_CITIES) | {"合肥市"}
        )
        station_source = ov.add_layer(project, ov.MAP_DATA_GPKG, "车站源数据", "记录车站", subset=f'"name" IN ({sql_strings(STATIONS)})')
        stations = ov.write_layer(station_source, OUTPUT_GPKG, "stations")
        stations.setName("行程车站")
        ov.style_stations(stations)
        stations.setLabelsEnabled(False)
        project.removeMapLayer(station_source.id())

        station_labels = build_points(project, STATION_LABELS, "主要车站名", "station_labels")
        style_labels(station_labels, 6.2, "#4C4A45", "华文楷体", 0.65)

        county_labels = build_county_labels(project, counties)
        style_labels(county_labels, 6.5, "#244A67", "华文楷体", 0.34)

        flights, arrows, airports = build_flights(project)
        airport_labels = build_points(project, AIRPORT_LABELS, "机场名", "airport_labels")
        style_labels(airport_labels, 5.8, "#285E79", "华文楷体", 0)
        layers = [
            station_labels,
            county_labels,
            airport_labels,
            stations,
            airports,
            arrows,
            flights,
            routes,
            highlighted_city_boundaries,
            counties,
            hefei,
            provinces,
            visited,
            cities,
        ]
        layout = build_layout(project, layers, services)
        project.layerTreeRoot().findLayer(arrows.id()).setItemVisibilityChecked(False)
        project.setTitle("走河西")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(ov.projected_extent(project, EXTENT), project.crs())
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)
        if hasattr(project, "setFilePathStorage"):
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        OUTPUT_QGZ.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_QGZ)):
            raise RuntimeError(f"Unable to save {OUTPUT_QGZ}")
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 210
        OUTPUT_PNG.unlink(missing_ok=True)
        if QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings) != QgsLayoutExporter.Success:
            raise RuntimeError("Image export failed")
        report = {"image": str(OUTPUT_PNG), "project": str(OUTPUT_QGZ), "rail_segments": routes.featureCount(), "flight_legs": flights.featureCount()}
        (OUTPUT_DIR / "构建报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    raise SystemExit(main())
