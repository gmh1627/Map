"""Build an editable Laiyuan County tourism infographic with QGIS.

The composition follows the supplied portrait reference: a black issue strip,
large overlaid title, highlighted county silhouette, sparse geographic context,
and compact attraction callouts connected to their mapped locations.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF
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
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPolyline,
    QgsLayoutItemShape,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsReferencedRectangle,
    QgsRectangle,
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
RAILWAY_ROOT = SCRIPT_DIR.parents[2]
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "旅游专题图" / "涞源县旅游图"
OUTPUT_GPKG = OUTPUT_DIR / "涞源县旅游图_数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "涞源县旅游图.qgz"
OUTPUT_PNG = OUTPUT_DIR / "涞源县旅游图.png"

ADMIN_SOURCES = (
    RAILWAY_ROOT / "city" / "baoding.geojson",
    RAILWAY_ROOT / "city" / "zhangjiakou.geojson",
    RAILWAY_ROOT / "city" / "datong.geojson",
)

PAGE = (112.395, 150.707)
MAP_FRAME = (0.635, 0.635, 111.125, 149.437)
MAP_EXTENT = (114.24, 38.99, 115.16, 39.92)
LAYOUT_SCALE_X = PAGE[0] / 180.0
LAYOUT_SCALE_Y = PAGE[1] / 315.0
FOCUS_NAME = "涞源县"
MAX_IMAGE_BYTES = 4_000_000

FONT_SANS = "微软雅黑"
FONT_TITLE = "黑体"
FONT_SERIF = "华文楷体"


@dataclass(frozen=True)
class PoiSpec:
    name: str
    lon: float
    lat: float
    category: str
    tag: str
    note: str
    card_x: float
    card_y: float
    card_w: float
    side: str


# Coordinates are cartographic anchors. They can be refined in the generated
# GeoPackage without changing the layout design.
POIS = (
    PoiSpec("马蹄梁", 114.430, 39.635, "自然", "可打卡", "草甸与山口景观", 19, 72, 41, "left"),
    PoiSpec("空中草原", 114.355, 39.585, "自然", "推荐", "高山草甸 · 夏季避暑", 18, 83, 43, "left"),
    PoiSpec("横岭子", 115.045, 39.650, "自然", "可打卡", "北部山地村落", 143, 82, 30, "right"),
    PoiSpec("乌龙沟长城", 115.015, 39.545, "长城", "重点", "明长城敌楼较集中", 132, 104, 41, "right"),
    PoiSpec("浮图峪长城", 114.974, 39.475, "长城", "推荐", "山谷古堡与长城遗存", 129, 120, 44, "right"),
    PoiSpec("白石口长城", 114.978, 39.405, "长城", "可打卡", "白石山北侧长城节点", 132, 140, 41, "right"),
    PoiSpec("插箭岭长城", 114.884, 39.510, "长城", "可打卡", "古关隘与山脊长城", 130, 157, 43, "right"),
    PoiSpec("白石山景区", 114.700, 39.218, "景区", "必打卡", "峰林栈道 · 国家 5A 景区", 118, 218, 55, "right"),
    PoiSpec("十瀑峡", 114.625, 39.255, "自然", "推荐", "峡谷瀑布群", 77, 237, 34, "right"),
    PoiSpec("仙人峪", 114.505, 39.245, "自然", "可打卡", "峡谷溪流与山地步道", 16, 243, 43, "left"),
    PoiSpec("七山滑雪度假区", 114.400, 39.355, "滑雪", "推荐", "冬季滑雪与山地度假", 7, 171, 54, "left"),
    PoiSpec("龙门飞狐", 114.440, 39.300, "自然", "可打卡", "太行峡谷地貌", 11, 213, 39, "left"),
    PoiSpec("阁院寺", 114.686, 39.366, "古建", "重点", "辽代文殊殿", 14, 129, 37, "left"),
    PoiSpec("兴文塔", 114.703, 39.355, "古建", "可打卡", "县城古塔", 20, 143, 34, "left"),
    PoiSpec("拒马源头", 114.695, 39.373, "自然", "可打卡", "拒马河源头", 75, 103, 38, "left"),
    PoiSpec("涞源博物馆", 114.710, 39.350, "博物馆", "推荐", "了解涞源历史文化", 17, 157, 46, "left"),
    PoiSpec("涞源古城", 114.690, 39.348, "古建", "可打卡", "县城历史街区", 121, 177, 40, "right"),
    PoiSpec("泰山宫", 114.674, 39.344, "古建", "可打卡", "古建筑群", 23, 185, 33, "left"),
    PoiSpec("白求恩战地手术室旧址", 114.836, 39.365, "遗址", "推荐", "抗战历史纪念地", 112, 194, 61, "right"),
    PoiSpec("石窝遗址", 114.760, 39.435, "遗址", "可打卡", "史前文化遗址", 117, 135, 36, "right"),
    PoiSpec("涞源湖", 114.730, 39.322, "自然", "可打卡", "县城近郊水景", 120, 208, 34, "right"),
    PoiSpec("天桥山自然保护区", 114.785, 39.115, "自然", "推荐", "森林与山地生态", 106, 265, 55, "right"),
    PoiSpec("白石山温泉度假区", 114.654, 39.286, "景区", "可打卡", "温泉与度假住宿", 17, 228, 52, "left"),
    PoiSpec("古北岳", 114.610, 39.090, "古建", "可打卡", "北岳文化遗存", 86, 286, 34, "right"),
)


CONTEXT_LABELS = {
    "蔚县": (114.57, 39.77),
    "广灵": (114.22, 39.72),
    "灵丘": (114.19, 39.37),
    "易县": (115.28, 39.36),
    "涞水": (115.27, 39.63),
    "唐县": (114.96, 38.98),
    "阜平": (114.22, 38.99),
}


ROADS = (
    ("G112", "国道", ((114.30, 39.57), (114.49, 39.48), (114.69, 39.37), (114.91, 39.43), (115.15, 39.56))),
    ("G108", "国道", ((114.26, 39.32), (114.48, 39.34), (114.69, 39.37), (114.88, 39.30), (115.09, 39.21))),
    ("G207", "国道", ((114.62, 39.73), (114.66, 39.55), (114.69, 39.37), (114.66, 39.18), (114.62, 38.96))),
    ("荣乌高速", "高速", ((114.18, 39.44), (114.43, 39.40), (114.69, 39.36), (114.93, 39.36), (115.25, 39.45))),
    ("涞涞高速", "高速", ((114.69, 39.36), (114.86, 39.28), (115.03, 39.18), (115.25, 39.09))),
    ("白石山旅游路", "县道", ((114.69, 39.36), (114.66, 39.29), (114.70, 39.22), (114.78, 39.12))),
    ("乌龙沟旅游路", "县道", ((114.69, 39.37), (114.83, 39.44), (114.96, 39.54), (115.04, 39.65))),
    ("西部旅游路", "县道", ((114.69, 39.36), (114.55, 39.34), (114.43, 39.30), (114.35, 39.22))),
)


RIVERS = (
    ("拒马河", ((114.690, 39.382), (114.720, 39.355), (114.790, 39.338), (114.900, 39.345), (115.060, 39.385), (115.270, 39.430))),
    ("唐河", ((114.610, 39.150), (114.650, 39.235), (114.635, 39.310), (114.565, 39.375), (114.485, 39.450))),
)


CATEGORY_COLORS = {
    "景区": "#78CE4C",
    "自然": "#A8E96F",
    "长城": "#27B79A",
    "古建": "#F0C94C",
    "博物馆": "#5CB8D4",
    "遗址": "#EA9B57",
    "滑雪": "#80D7C6",
}


def load_vector(path: Path, name: str, subset: str | None = None) -> QgsVectorLayer:
    layer = QgsVectorLayer(str(path), name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Unable to load vector layer: {path}")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Unable to apply subset to {name}: {subset}")
    return layer


def write_layer(
    project: QgsProject,
    layer: QgsVectorLayer,
    layer_name: str,
    first: bool = False,
) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if first
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to write {layer_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={layer_name}", layer.name(), "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reload {layer_name}")
    project.addMapLayer(saved)
    return saved


def memory_layer(geometry: str, name: str, fields: list[QgsField]) -> QgsVectorLayer:
    layer = QgsVectorLayer(f"{geometry}?crs=EPSG:4326", name, "memory")
    layer.dataProvider().addAttributes(fields)
    layer.updateFields()
    return layer


def build_admin_layers(project: QgsProject) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    fields = [QgsField("name", QVariant.String), QgsField("adcode", QVariant.Int)]
    context = memory_layer("MultiPolygon", "周边县区", fields)
    focus = memory_layer("MultiPolygon", "涞源县", fields)
    shadow = memory_layer("MultiPolygon", "涞源县轮廓光", fields)
    context_features = []
    focus_features = []
    shadow_features = []
    extent = QgsRectangle(*MAP_EXTENT)

    for path in ADMIN_SOURCES:
        if not path.exists():
            continue
        source = load_vector(path, f"source_{path.stem}")
        for item in source.getFeatures():
            geometry = item.geometry()
            if geometry.isNull() or not geometry.boundingBox().intersects(extent):
                continue
            name = str(item["name"])
            adcode = int(item["adcode"])
            out = QgsFeature(context.fields())
            out.setAttributes([name, adcode])
            out.setGeometry(geometry)
            context_features.append(out)
            if name == FOCUS_NAME:
                selected = QgsFeature(focus.fields())
                selected.setAttributes([name, adcode])
                selected.setGeometry(geometry)
                focus_features.append(selected)
                for distance, suffix in ((0.030, 1), (0.018, 2), (0.009, 3)):
                    glow = QgsFeature(shadow.fields())
                    glow.setAttributes([f"{name}_{suffix}", adcode])
                    glow.setGeometry(geometry.buffer(distance, 24))
                    shadow_features.append(glow)

    if not focus_features:
        raise RuntimeError("Laiyuan County is missing from the administrative source")
    context.dataProvider().addFeatures(context_features)
    focus.dataProvider().addFeatures(focus_features)
    shadow.dataProvider().addFeatures(shadow_features)
    for layer in (context, focus, shadow):
        layer.updateExtents()

    saved_context = write_layer(project, context, "context_admin", first=True)
    saved_shadow = write_layer(project, shadow, "laiyuan_glow")
    saved_focus = write_layer(project, focus, "laiyuan_county")
    return saved_context, saved_shadow, saved_focus


def build_line_layer(
    project: QgsProject,
    name: str,
    output_name: str,
    records: tuple,
) -> QgsVectorLayer:
    layer = memory_layer(
        "LineString",
        name,
        [QgsField("name", QVariant.String), QgsField("class", QVariant.String)],
    )
    features = []
    for record in records:
        line_name, line_class, coordinates = record
        feature = QgsFeature(layer.fields())
        feature.setAttributes([line_name, line_class])
        feature.setGeometry(
            QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in coordinates])
        )
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return write_layer(project, layer, output_name)


def build_river_layer(project: QgsProject) -> QgsVectorLayer:
    records = tuple((name, "河流", coordinates) for name, coordinates in RIVERS)
    return build_line_layer(project, "河流", "rivers", records)


def build_poi_layer(project: QgsProject) -> QgsVectorLayer:
    fields = [
        QgsField("name", QVariant.String),
        QgsField("category", QVariant.String),
        QgsField("tag", QVariant.String),
        QgsField("note", QVariant.String),
        QgsField("card_x", QVariant.Double),
        QgsField("card_y", QVariant.Double),
        QgsField("card_w", QVariant.Double),
        QgsField("side", QVariant.String),
    ]
    layer = memory_layer("Point", "旅游景点", fields)
    features = []
    for poi in POIS:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(
            [poi.name, poi.category, poi.tag, poi.note, poi.card_x, poi.card_y, poi.card_w, poi.side]
        )
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(poi.lon, poi.lat)))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return write_layer(project, layer, "tourism_pois")


def build_context_label_layer(project: QgsProject) -> QgsVectorLayer:
    layer = memory_layer("Point", "周边地名", [QgsField("name", QVariant.String)])
    features = []
    for name, (lon, lat) in CONTEXT_LABELS.items():
        feature = QgsFeature(layer.fields())
        feature.setAttributes([name])
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return write_layer(project, layer, "context_labels")


def style_context(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#FCFDFB",
            "outline_color": "#D3DDD5",
            "outline_width": "0.18",
            "outline_width_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_shadow(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "110,124,109,32",
            "outline_style": "no",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_focus(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "187,228,164,220",
            "outline_color": "#687D6B",
            "outline_width": "0.48",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_roads(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol()
    symbol.deleteSymbolLayer(0)
    casing = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "255,255,255,210",
            "line_width": "0.86",
            "line_width_unit": "MM",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )
    inner = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "#9BC58A",
            "line_width": "0.25",
            "line_width_unit": "MM",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )
    symbol.appendSymbolLayer(casing)
    symbol.appendSymbolLayer(inner)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_rivers(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": "#B7D7D0",
            "line_width": "0.34",
            "line_width_unit": "MM",
            "capstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_pois(layer: QgsVectorLayer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#111711",
            "size": "1.55",
            "size_unit": "MM",
            "outline_color": "#F7FFF2",
            "outline_width": "0.34",
            "outline_width_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def text_format(
    size: float,
    family: str = FONT_SANS,
    color: str = "#151915",
    bold: bool = False,
    buffer_color: str | None = None,
    buffer_size: float = 0.0,
) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont(family)
    font.setPointSizeF(size)
    font.setBold(bold)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer_color and buffer_size:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setColor(QColor(buffer_color))
        buffer.setSize(buffer_size)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(buffer)
    return fmt


def style_context_labels(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple({"name": "circle", "size": "0", "outline_style": "no"})
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(text_format(10.0, FONT_SANS, "#D7DDD7", bold=True))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def add_shape(
    layout: QgsPrintLayout,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    outline: str = "255,255,255,0",
    outline_width: float = 0.0,
) -> QgsLayoutItemShape:
    item = QgsLayoutItemShape(layout)
    item.setShapeType(QgsLayoutItemShape.Rectangle)
    item.setSymbol(
        QgsFillSymbol.createSimple(
            {
                "color": fill,
                "outline_color": outline,
                "outline_width": str(outline_width),
                "outline_width_unit": "MM",
            }
        )
    )
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    return item


def add_ellipse(
    layout: QgsPrintLayout,
    x: float,
    y: float,
    width: float,
    height: float,
    fill: str,
    outline: str = "255,255,255,0",
    outline_width: float = 0.0,
) -> QgsLayoutItemShape:
    item = QgsLayoutItemShape(layout)
    item.setShapeType(QgsLayoutItemShape.Ellipse)
    item.setSymbol(QgsFillSymbol.createSimple({
        "color": fill,
        "outline_color": outline,
        "outline_width": str(outline_width),
        "outline_width_unit": "MM",
    }))
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    return item


def add_label(
    layout: QgsPrintLayout,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    family: str = FONT_SANS,
    color: str = "#151915",
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignLeft,
    buffer_color: str | None = None,
    buffer_size: float = 0.0,
) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(
        text_format(size, family, color, bold, buffer_color, buffer_size)
    )
    item.setHAlign(align)
    item.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    return item


def add_polyline(
    layout: QgsPrintLayout,
    points: list[QPointF],
    color: str,
    width: float,
    dashed: bool = False,
) -> QgsLayoutItemPolyline:
    item = QgsLayoutItemPolyline(QPolygonF(points), layout)
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": color,
            "line_width": str(width),
            "line_width_unit": "MM",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )
    if dashed:
        layer = symbol.symbolLayer(0)
        layer.setUseCustomDashPattern(True)
        layer.setCustomDashVector([0.8, 1.25])
        layer.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
        layer.setTweakDashPatternOnCorners(False)
    item.setSymbol(symbol)
    layout.addLayoutItem(item)
    return item


def map_anchor(project: QgsProject, map_item: QgsLayoutItemMap, lon: float, lat: float) -> QPointF:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    point = transform.transform(QgsPointXY(lon, lat))
    extent = map_item.extent()
    x = MAP_FRAME[0] + (point.x() - extent.xMinimum()) / extent.width() * MAP_FRAME[2]
    y = MAP_FRAME[1] + (extent.yMaximum() - point.y()) / extent.height() * MAP_FRAME[3]
    return QPointF(x, y)


def add_header(layout: QgsPrintLayout) -> None:
    add_shape(layout, 0.6, 1.9, 111.2, 4.0, "#050807")
    add_label(layout, "【北京周边系列】之保定 · 小城", 21.5, 1.95, 47, 3.8, 6.2, color="#FFFFFF", bold=True)
    add_label(layout, "第 2-005 期 / 100", 67.5, 1.95, 27, 3.8, 6.0, color="#F6FF61", bold=True, align=Qt.AlignCenter)
    add_ellipse(layout, 87.3, 1.95, 4.3, 3.9, "#F6F8F6", "#D9E0DB", 0.18)
    add_label(layout, "●", 88.0, 1.95, 3.0, 3.8, 6.0, color="#6C746F", align=Qt.AlignCenter)
    add_label(layout, "@冷三岁 · 制作", 92.5, 1.95, 18.5, 3.8, 5.4, color="#FFFFFF", bold=True, align=Qt.AlignRight)


def add_title(layout: QgsPrintLayout) -> None:
    add_shape(layout, 3.8, 14.0, 4.0, 8.5, "#070A08", "#070A08", 0.35)
    add_label(layout, "保\n定", 4.0, 14.2, 3.6, 8.0, 6.2, color="#FFFFFF", bold=True, align=Qt.AlignCenter)
    add_label(layout, "涞源县", 8.7, 12.5, 56.0, 18.5, 52.0, FONT_TITLE, "#050705", bold=True)
    add_label(
        layout,
        "北京周边",
        63.0,
        13.0,
        48.0,
        13.0,
        30.0,
        FONT_TITLE,
        "#FFF600",
        bold=True,
        buffer_color="#050705",
        buffer_size=0.75,
    )
    add_label(layout, "保定各区县旅游 · 第 01 / 21", 68.0, 25.5, 42.0, 5.8, 8.6, FONT_SANS, "#111511", bold=True, align=Qt.AlignCenter)
    add_label(layout, "北", 8.0, 37.2, 6.0, 4.5, 6.2, FONT_SANS, "#151A16", bold=True, align=Qt.AlignCenter)
    add_label(layout, "▲", 8.0, 40.0, 6.0, 6.0, 10.5, FONT_SANS, "#111511", bold=True, align=Qt.AlignCenter)


def add_city_badge(layout: QgsPrintLayout, project: QgsProject, map_item: QgsLayoutItemMap) -> None:
    anchor = map_anchor(project, map_item, 114.695, 39.360)
    add_shape(layout, anchor.x() - 13.5, anchor.y() - 4.0, 27.0, 8.0, "214,238,196,245", "#3F7449", 0.42)
    add_label(layout, "涞源县城区", anchor.x() - 13.0, anchor.y() - 3.7, 26.0, 7.2, 7.7, FONT_SANS, "#173D20", bold=True, align=Qt.AlignCenter)


def add_poi_callout(
    layout: QgsPrintLayout,
    project: QgsProject,
    map_item: QgsLayoutItemMap,
    poi: PoiSpec,
) -> None:
    anchor = map_anchor(project, map_item, poi.lon, poi.lat)
    card_x = poi.card_x * LAYOUT_SCALE_X
    card_y = poi.card_y * LAYOUT_SCALE_Y
    card_w = poi.card_w * LAYOUT_SCALE_X
    card_h = (11.0 if poi.note else 7.0) * LAYOUT_SCALE_Y
    card_center_y = card_y + card_h / 2.0
    if poi.side == "left":
        edge_x = card_x + card_w
        elbow_x = min(anchor.x() - 3.0, edge_x + 8.0)
    else:
        edge_x = card_x
        elbow_x = max(anchor.x() + 3.0, edge_x - 8.0)
    add_polyline(
        layout,
        [QPointF(anchor.x(), anchor.y()), QPointF(elbow_x, anchor.y()), QPointF(edge_x, card_center_y)],
        "#303B32",
        0.30,
        dashed=True,
    )

    color = CATEGORY_COLORS[poi.category]
    chip_w = max(5.3, (2.45 * len(poi.category) + 3.0) * LAYOUT_SCALE_X)
    tag_w = max(6.3, (2.35 * len(poi.tag) + 3.0) * LAYOUT_SCALE_X)
    chip_h = 5.7 * LAYOUT_SCALE_Y
    add_shape(layout, card_x, card_y, chip_w, chip_h, color, "255,255,255,0", 0.0)
    add_label(layout, poi.category, card_x + 0.35, card_y, chip_w - 0.7, chip_h, 4.6, FONT_SANS, "#FFFFFF" if poi.category in {"长城", "博物馆", "遗址"} else "#21411B", bold=True, align=Qt.AlignCenter)
    add_shape(layout, card_x + chip_w + 0.6, card_y, tag_w, chip_h, "#F1F4E7", "#A5B38D", 0.12)
    add_label(layout, poi.tag, card_x + chip_w + 0.9, card_y, tag_w - 0.6, chip_h, 4.3, FONT_SANS, "#536044", bold=True, align=Qt.AlignCenter)
    title_x = card_x + chip_w + tag_w + 1.8
    title_w = max(5.0, card_w - (title_x - card_x))
    add_label(layout, poi.name, title_x, card_y - 0.1, title_w, chip_h, 5.1, FONT_SANS, "#101510", bold=True)
    if poi.note:
        add_label(layout, poi.note, card_x, card_y + chip_h, card_w, 4.6 * LAYOUT_SCALE_Y, 3.5, FONT_SANS, "#5C665C", False)


def add_legend(layout: QgsPrintLayout) -> None:
    add_shape(layout, 5.0, 126.5, 26.0, 20.5, "250,252,247,220", "#506052", 0.22)
    add_shape(layout, 5.0, 126.5, 26.0, 0.75, "#202820", "255,255,255,0", 0.0)
    add_label(layout, "冷三岁 · 注", 10.8, 127.0, 18.0, 4.5, 5.4, FONT_SANS, "#1D271E", bold=True)
    add_shape(layout, 6.2, 127.2, 3.5, 3.5, "#F6FAF4", "#677469", 0.16)
    add_label(layout, "●", 6.5, 127.2, 2.8, 3.5, 4.8, FONT_SANS, "#657168", align=Qt.AlignCenter)
    rows = (
        ("#78CE4C", "核心景区", "优先安排"),
        ("#F0C94C", "古建遗址", "人文节点"),
        ("#27B79A", "长城节点", "适合徒步"),
    )
    for index, (color, label, note) in enumerate(rows):
        y = 132.0 + index * 4.3
        add_shape(layout, 6.2, y + 0.7, 2.8, 2.8, color, "#FFFFFF", 0.16)
        add_label(layout, label, 10.6, y, 10.5, 3.8, 4.7, FONT_SANS, "#111511", bold=True)
        add_label(layout, note, 21.0, y, 9.0, 3.8, 4.0, FONT_SANS, "#5B665C")


def build_layout(project: QgsProject, layers: list[QgsVectorLayer]) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("涞源县旅游图")
    layout.pageCollection().page(0).setPageSize(
        QgsLayoutSize(*PAGE, QgsUnitTypes.LayoutMillimeters)
    )
    project.layoutManager().addLayout(layout)

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("涞源县旅游主图")
    map_item.setBackgroundColor(QColor("#F7F7F7"))
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#242A25"))
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
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    map_item.zoomToExtent(transform.transformBoundingBox(QgsRectangle(*MAP_EXTENT)))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)

    add_header(layout)
    add_title(layout)
    add_city_badge(layout, project, map_item)
    for poi in POIS:
        add_poi_callout(layout, project, map_item, poi)
    add_legend(layout)
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
        project.setTitle("涞源县旅游图")
        project.setPresetHomePath(str(OUTPUT_DIR))
        project.setFilePathStorage(Qgis.FilePathType.Relative)

        context, shadow, focus = build_admin_layers(project)
        roads = build_line_layer(project, "道路骨架", "roads", ROADS)
        rivers = build_river_layer(project)
        pois = build_poi_layer(project)
        context_labels = build_context_label_layer(project)

        style_context(context)
        style_shadow(shadow)
        style_focus(focus)
        style_roads(roads)
        style_rivers(rivers)
        style_pois(pois)
        style_context_labels(context_labels)

        layers = [pois, context_labels, roads, rivers, focus, shadow, context]
        project.layerTreeRoot().setHasCustomLayerOrder(True)
        project.layerTreeRoot().setCustomLayerOrder(layers)
        layout = build_layout(project, layers)

        default_extent = QgsReferencedRectangle(
            QgsCoordinateTransform(
                QgsCoordinateReferenceSystem("EPSG:4326"),
                project.crs(),
                project.transformContext(),
            ).transformBoundingBox(QgsRectangle(*MAP_EXTENT)),
            project.crs(),
        )
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)

        OUTPUT_QGZ.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_QGZ)):
            raise RuntimeError(f"Unable to write project: {OUTPUT_QGZ}")

        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 120
        OUTPUT_PNG.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Image export failed: {result}")
        image_bytes = OUTPUT_PNG.stat().st_size
        if image_bytes > MAX_IMAGE_BYTES:
            raise RuntimeError(f"Image exceeds size limit: {image_bytes:,} bytes")

        report = {
            "image": str(OUTPUT_PNG),
            "project": str(OUTPUT_QGZ),
            "geopackage": str(OUTPUT_GPKG),
            "poi_count": pois.featureCount(),
            "context_admin_count": context.featureCount(),
            "image_bytes": image_bytes,
            "page_mm": PAGE,
            "extent_wgs84": MAP_EXTENT,
        }
        (OUTPUT_DIR / "构建报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
