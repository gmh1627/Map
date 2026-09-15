"""Build a complete Gansu itinerary map with editable place cards."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutItemShape,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsReferencedRectangle,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)


RAILWAY_ROOT = Path(r"F:\Desktop\Blog\Map")
COMMON_DIR = RAILWAY_ROOT / "制图工具" / "scripts" / "regional_overviews"
sys.path.insert(0, str(COMMON_DIR))
import build_overviews as ov  # noqa: E402
import card_layout  # noqa: E402


OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "区域线路图" / "甘肃行旅"
OUTPUT_GPKG = OUTPUT_DIR / "甘肃行旅_数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "甘肃行旅.qgz"
OUTPUT_PNG = OUTPUT_DIR / "甘肃行旅.png"
GANSU_CITIES = RAILWAY_ROOT / "city" / "gansu_counties.geojson"
GANSU_COUNTIES = RAILWAY_ROOT / "city" / "gansu_focus_counties.geojson"
PROVINCES = RAILWAY_ROOT / "province" / "province.json"

PAGE = (500.0, 350.0)
MAP_FRAME = (5.0, 5.0, 490.0, 340.0)
GANSU_EXTENT = (91.9, 32.45, 109.1, 42.95)
MAX_IMAGE_BYTES = 3_000_000

VISITED_CITIES = (
    "天水市",
    "定西市",
    "兰州市",
    "临夏回族自治州",
    "武威市",
    "张掖市",
    "酒泉市",
    "嘉峪关市",
)
FOCUS_COUNTIES = (
    "甘谷县",
    "武山县",
    "陇西县",
    "永靖县",
    "肃南裕固族自治县",
    "玉门市",
    "瓜州县",
    "敦煌市",
)

DISPLAY_NAMES = {
    "临夏回族自治州": "临夏",
    "甘南藏族自治州": "甘南",
    "肃南裕固族自治县": "肃南县",
    "玉门市": "玉门市",
    "敦煌市": "敦煌市",
}

# Each entry is (date, place names). Each place name renders on its own line.
ITINERARY = {
    "天水": (
        ("5.31", ("麦积山石窟", "伏羲庙（天水市博物馆）")),
        (
            "6.1",
            (
                "天水古城",
                "飞将巷",
                "李家院（未入）",
                "古城墙遗址",
                "玉泉观",
                "后街清真寺",
                "胡氏古民居（未入）",
                "纪信祠",
                "李广墓",
                "南郭寺",
            ),
        ),
    ),
    "甘谷县": (("6.1", ("大像山石窟", "姜维墓")),),
    "武山县": (("6.2", ("水帘洞石窟（拉梢寺）",)),),
    "定西": (("6.3", ("定西市博物馆",)),),
    "陇西县": (("6.2", ("威远楼",)),),
    "兰州": (),
    "永靖县": (),
    "武威": (),
    "张掖": (),
    "肃南县": (),
    "酒泉": (),
    "玉门市": (("6.11", ("老君庙老一井",)),),
    "瓜州县": (),
    "敦煌市": (),
    "嘉峪关": (),
}

CARD_PLACEMENT = {
    "敦煌市": ("upper_right", 12.0, -8.0),
    "瓜州县": ("upper_right", 13.0, -12.0),
    "玉门市": ("upper_right", 4.0, -7.0),
    "酒泉": ("above", 8.0, -8.0),
    "嘉峪关": ("below", -8.0, 9.0),
    "张掖": ("upper_right", 10.0, -9.0),
    "肃南县": ("below", -10.0, 8.0),
    "武威": ("upper_right", 10.0, -9.0),
    "兰州": ("upper_right", 12.0, -10.0),
    "永靖县": ("lower_left", -10.0, 9.0),
    "定西": ("upper_right", 10.0, -8.0),
    "陇西县": ("left", -18.0, -8.0),
    "武山县": ("lower_left", -12.0, 14.0),
    "甘谷县": ("below", 8.0, 10.0),
    "天水": ("right", 14.0, -24.0),
}

CARD_ANCHORS = {
    "敦煌市": (94.66, 40.14),
    "瓜州县": (95.78, 40.52),
    "玉门市": (97.05, 40.29),
    "酒泉": (98.49, 39.73),
    "嘉峪关": (98.29, 39.77),
    "张掖": (100.45, 38.93),
    "肃南县": (99.62, 38.84),
    "武威": (102.64, 37.93),
    "兰州": (103.82, 36.06),
    "永靖县": (103.32, 35.96),
    "定西": (104.62, 35.58),
    "陇西县": (104.63, 35.00),
    "武山县": (104.89, 34.72),
    "甘谷县": (105.34, 34.74),
    "天水": (105.72, 34.58),
}

CONTEXT_LABELS = {
    "新疆": (92.65, 42.35),
    "青海": (97.10, 35.20),
    "四川": (103.15, 32.82),
    "陕西": (108.35, 34.20),
    "宁夏": (106.15, 37.35),
    "内蒙古": (107.20, 41.25),
    "哈密": (93.55, 42.55),
    "西宁": (101.78, 36.62),
    "银川": (106.23, 38.49),
    "中卫": (105.19, 37.51),
    "固原": (106.24, 36.02),
    "宝鸡": (107.24, 34.36),
    "汉中": (107.03, 33.07),
    "西安": (108.94, 34.34),
}


def sql_strings(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def short_name(name: str) -> str:
    if name in DISPLAY_NAMES:
        return DISPLAY_NAMES[name]
    return name.removesuffix("市")


def style_polygon(
    layer: QgsVectorLayer,
    fill: str,
    outline: str,
    width: float,
    outline_style: str = "solid",
) -> None:
    if outline_style == "sparse_dash":
        symbol = QgsFillSymbol.createSimple(
            {
                "color": fill,
                "outline_style": "no",
            }
        )
        border = QgsSimpleLineSymbolLayer.create(
            {
                "line_color": outline,
                "line_width": str(width),
                "line_width_unit": "MM",
            }
        )
        border.setUseCustomDashPattern(True)
        border.setCustomDashVector([1.5, 2.2])
        border.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
        border.setTweakDashPatternOnCorners(False)
        symbol.appendSymbolLayer(border)
        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        return
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill,
            "outline_color": outline,
            "outline_width": str(width),
            "outline_width_unit": "MM",
            "outline_style": outline_style,
        }
    )
    if width <= 0:
        symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def label_point(geometry: QgsGeometry) -> QgsGeometry:
    point, _ = geometry.poleOfInaccessibility(0.01)
    if point.isEmpty():
        point = geometry.pointOnSurface()
    if point.isEmpty():
        point = geometry.centroid()
    return point


def build_label_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    layer_name: str,
    output_name: str,
    first: bool,
) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for item in source.getFeatures():
        feature = QgsFeature(memory.fields())
        source_name = str(item["name"])
        feature.setAttributes([short_name(source_name)])
        geometry = label_point(item.geometry())
        if layer_name == "城市名称" and source_name == "庆阳市":
            point = geometry.asPoint()
            geometry = QgsGeometry.fromPointXY(QgsPointXY(point.x() + 0.60, point.y()))
        feature.setGeometry(geometry)
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    project.addMapLayer(memory)
    saved = ov.write_layer(memory, OUTPUT_GPKG, output_name, first=first)
    project.removeMapLayer(memory.id())
    return saved


def build_named_points(
    project: QgsProject,
    values: dict[str, tuple[float, float]],
    layer_name: str,
    output_name: str,
) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", layer_name, "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for name, (lon, lat) in values.items():
        feature = QgsFeature(memory.fields())
        feature.setAttributes([name])
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    project.addMapLayer(memory)
    saved = ov.write_layer(memory, OUTPUT_GPKG, output_name)
    project.removeMapLayer(memory.id())
    return saved


def style_labels(layer: QgsVectorLayer, size: float, color: str, bold: bool) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {"name": "circle", "size": "0", "outline_style": "no"}
            )
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.displayAll = True
    settings.priority = 10
    text = QgsTextFormat()
    font = QFont("思源黑体 CN")
    font.setBold(bold)
    text.setFont(font)
    text.setSize(size)
    text.setColor(QColor(color))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor(255, 255, 255, 235))
    text.setBuffer(buffer)
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def map_anchor_position(
    project: QgsProject,
    map_item: QgsLayoutItemMap,
    coordinates: tuple[float, float],
) -> QPointF:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    point = transform.transform(QgsPointXY(*coordinates))
    extent = map_item.extent()
    x = MAP_FRAME[0] + (point.x() - extent.xMinimum()) / extent.width() * MAP_FRAME[2]
    y = MAP_FRAME[1] + (extent.yMaximum() - point.y()) / extent.height() * MAP_FRAME[3]
    return QPointF(x, y)


def add_legend_item(
    layout: QgsPrintLayout,
    x: float,
    y: float,
    fill: str,
    outline: str,
    label: str,
    outline_style: str = "solid",
) -> None:
    shape = QgsLayoutItemShape(layout)
    shape.setShapeType(QgsLayoutItemShape.Rectangle)
    if outline_style == "sparse_dash":
        symbol = QgsFillSymbol.createSimple(
            {
                "color": fill,
                "outline_style": "no",
            }
        )
        border = QgsSimpleLineSymbolLayer.create(
            {
                "line_color": outline,
                "line_width": "0.18",
                "line_width_unit": "MM",
            }
        )
        border.setUseCustomDashPattern(True)
        border.setCustomDashVector([1.5, 2.2])
        border.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
        symbol.appendSymbolLayer(border)
    else:
        symbol = QgsFillSymbol.createSimple(
            {
                "color": fill,
                "outline_color": outline,
                "outline_width": "0.25",
                "outline_width_unit": "MM",
                "outline_style": outline_style,
            }
        )
    shape.setSymbol(symbol)
    layout.addLayoutItem(shape)
    shape.attemptMove(QgsLayoutPoint(x, y + 1.0, QgsUnitTypes.LayoutMillimeters))
    shape.attemptResize(QgsLayoutSize(7.0, 4.5, QgsUnitTypes.LayoutMillimeters))
    ov.add_label(layout, label, x + 9.5, y, 37.0, 7.0, 8.0, "思源黑体 CN", "#48555C", bold=True)


def build_layout(project: QgsProject, layers: list[QgsVectorLayer]) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("甘肃行旅")
    layout.pageCollection().page(0).setPageSize(
        QgsLayoutSize(*PAGE, QgsUnitTypes.LayoutMillimeters)
    )
    project.layoutManager().addLayout(layout)

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("甘肃全省图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#69777C"))
    map_item.setFrameStrokeWidth(
        QgsLayoutMeasurement(0.24, QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(map_item)
    map_item.attemptMove(
        QgsLayoutPoint(MAP_FRAME[0], MAP_FRAME[1], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.attemptResize(
        QgsLayoutSize(MAP_FRAME[2], MAP_FRAME[3], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.zoomToExtent(ov.projected_extent(project, GANSU_EXTENT))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)

    for name, placement in CARD_PLACEMENT.items():
        card_layout.add_itinerary_card(
            layout,
            name,
            ITINERARY[name],
            placement,
            map_anchor_position(project, map_item, CARD_ANCHORS[name]),
            MAP_FRAME,
        )
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

        context_cities = ov.add_layer(project, ov.CITY_SOURCE, "周边城市边界")
        style_polygon(context_cities, "0,0,0,0", "255,255,255,0", 0.0)

        cities = ov.add_layer(project, GANSU_CITIES, "甘肃地级行政区")
        style_polygon(cities, "#F3F6F4", "255,255,255,0", 0.0)
        visited = ov.add_layer(
            project,
            GANSU_CITIES,
            "到访城市",
            subset=f'"name" IN ({sql_strings(VISITED_CITIES)})',
        )
        style_polygon(visited, "#D7E8E1", "255,255,255,0", 0.0)
        counties = ov.add_layer(
            project,
            GANSU_COUNTIES,
            "重点县市",
            subset=f'"name" IN ({sql_strings(FOCUS_COUNTIES)})',
        )
        style_polygon(
            counties,
            "112,163,144,155",
            "#2F6257",
            0.18,
            outline_style="sparse_dash",
        )

        city_labels = build_label_layer(
            project, cities, "城市名称", "city_labels", first=True
        )
        style_labels(city_labels, 9.5, "#33413F", bold=True)
        county_labels = build_label_layer(
            project, counties, "重点县市名称", "county_labels", first=False
        )
        style_labels(county_labels, 8.2, "#315B52", bold=True)
        context_labels = build_named_points(
            project, CONTEXT_LABELS, "周边地名", "context_labels"
        )
        style_labels(context_labels, 6.8, "#98A29F", bold=False)
        context_provinces = ov.build_province_boundaries_from_cities(
            context_cities,
            OUTPUT_GPKG,
            GANSU_EXTENT,
            layer_name="context_province_boundaries",
            display_name="周边省界",
            exclude_province_codes={620000},
            line_color="#A9B1B2",
            line_width=0.32,
        )
        province = ov.build_province_boundaries_from_cities(
            cities,
            OUTPUT_GPKG,
            GANSU_EXTENT,
            layer_name="gansu_province_boundary",
            display_name="甘肃省界",
            include_province_codes={620000},
            line_color="#A9B1B2",
            line_width=0.32,
        )
        context_internal = ov.build_internal_admin_boundaries(
            project,
            context_cities,
            OUTPUT_GPKG,
            GANSU_EXTENT,
            layer_name="context_internal_boundaries",
            display_name="周边地级行政区内部边界",
        )
        gansu_internal = ov.build_internal_admin_boundaries(
            project,
            cities,
            OUTPUT_GPKG,
            GANSU_EXTENT,
            layer_name="gansu_internal_boundaries",
            display_name="甘肃地级行政区内部边界",
        )
        layers = [
            county_labels,
            city_labels,
            context_labels,
            counties,
            gansu_internal,
            visited,
            cities,
            province,
            context_internal,
            context_cities,
            context_provinces,
        ]
        layout = build_layout(project, layers)
        project.setTitle("甘肃行旅")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(
            ov.projected_extent(project, GANSU_EXTENT), project.crs()
        )
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
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Image export failed: {result}")
        image_bytes = OUTPUT_PNG.stat().st_size
        if image_bytes > MAX_IMAGE_BYTES:
            raise RuntimeError(
                f"Image exceeds 3 MB limit: {image_bytes:,} bytes"
            )

        report = {
            "image": str(OUTPUT_PNG),
            "project": str(OUTPUT_QGZ),
            "cities": cities.featureCount(),
            "visited_cities": visited.featureCount(),
            "focus_counties": counties.featureCount(),
            "cards": len(ITINERARY),
            "filled_cards": sum(bool(lines) for lines in ITINERARY.values()),
            "image_bytes": image_bytes,
        }
        (OUTPUT_DIR / "构建报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    raise SystemExit(main())
