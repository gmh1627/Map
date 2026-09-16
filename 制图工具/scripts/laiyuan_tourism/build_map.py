"""Build an editable Laiyuan County tourism infographic with QGIS.

The composition follows the supplied portrait reference: a black issue strip,
large overlaid title, highlighted county silhouette, sparse geographic context,
and compact attraction callouts connected to their mapped locations.
"""

from __future__ import annotations

import json
import gzip
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
    QgsLayoutItemPicture,
    QgsLayoutItemPolyline,
    QgsLayoutItemShape,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerSymbol,
    QgsCategorizedSymbolRenderer,
    QgsRendererCategory,
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
REFERENCE_IMAGE = SCRIPT_DIR / "assets" / "涞源县旅游图_参考.png"
OSM_NETWORK = SCRIPT_DIR / "assets" / "laiyuan_osm_network.json.gz"

ADMIN_SOURCES = (
    RAILWAY_ROOT / "city" / "baoding.geojson",
    RAILWAY_ROOT / "city" / "zhangjiakou.geojson",
    RAILWAY_ROOT / "city" / "datong.geojson",
)

PAGE = (112.395, 150.707)
MAP_FRAME = (0.635, 0.635, 111.125, 149.437)
MAP_EXTENT = (114.263, 38.99, 115.137, 39.92)
REFERENCE_PIXELS = (531.0, 712.0)
PX_X = PAGE[0] / REFERENCE_PIXELS[0]
PX_Y = PAGE[1] / REFERENCE_PIXELS[1]
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
    anchor_x: float
    anchor_y: float
    card_x: float
    card_y: float
    card_w: float
    side: str
    theme: str = "simple"


# Geographic coordinates remain editable in the GeoPackage. Pixel anchors and
# card coordinates trace the supplied 531 x 712 reference composition.
POIS = (
    PoiSpec("马蹄梁", 114.430, 39.635, "", "", "", 245, 251, 130, 207, 58, "left"),
    PoiSpec("空中草原", 114.355, 39.585, "", "￥65/人 · ￥200/车", "", 181, 239, 59, 233, 111, "left", "price"),
    PoiSpec("黄花梁", 114.495, 39.570, "徒步", "免费", "小尾寒羊、徒步、高山草甸、大片羊群", 247, 267, 77, 259, 137, "left", "dark"),
    PoiSpec("横岭子", 115.045, 39.650, "", "", "", 440, 239, 454, 229, 48, "right"),
    PoiSpec("乌龙沟长城", 115.015, 39.545, "长城", "免费", "保存较为完整，适合徒步", 410, 347, 418, 305, 112, "right", "wall"),
    PoiSpec("寨子沟明长城遗址", 114.955, 39.500, "长城", "免费", "明代长城遗存及敌台", 389, 377, 416, 343, 115, "right", "wall"),
    PoiSpec("浮图峪长城", 114.940, 39.455, "长城", "免费", "全长约 4.5 公里，可登高远望", 367, 384, 415, 375, 116, "right", "wall"),
    PoiSpec("白求恩战地手术室旧址", 114.836, 39.365, "", "", "", 411, 416, 442, 406, 89, "right"),
    PoiSpec("泰山宫", 114.674, 39.344, "唐代石狮", "免费", "保存文物石刻，近县城一并游览", 249, 411, 112, 367, 139, "left", "dark"),
    PoiSpec("阁院寺", 114.686, 39.366, "辽代", "免费", "中国八大辽构之一，皇家寺院", 249, 422, 126, 392, 125, "left", "dark"),
    PoiSpec("兴文塔", 114.703, 39.355, "", "免费", "", 250, 432, 128, 418, 123, "left", "dark"),
    PoiSpec("涞源博物馆", 114.710, 39.350, "辽代", "免费", "", 249, 444, 128, 440, 123, "left", "dark"),
    PoiSpec("七山滑雪度假区", 114.400, 39.355, "", "", "", 249, 455, 20, 448, 96, "left"),
    PoiSpec("仙人峪", 114.505, 39.245, "", "￥35", "三十多公里的峡谷景观，石灰岩地貌", 156, 500, 20, 477, 101, "left", "price"),
    PoiSpec("龙门飞狐", 114.440, 39.300, "", "免费", "深峡谷、山野景观，可徒步", 154, 545, 20, 515, 93, "left"),
    PoiSpec("七亩地万花谷", 114.420, 39.265, "长城", "免费", "", 162, 553, 20, 547, 105, "left", "wall"),
    PoiSpec("十瀑峡", 114.625, 39.255, "", "", "高山峡谷瀑布景观", 229, 533, 169, 528, 55, "left"),
    PoiSpec("七彩生态植物园", 114.780, 39.350, "", "", "", 267, 455, 370, 449, 110, "right"),
    PoiSpec("白石口长城", 114.825, 39.315, "长城", "免费", "", 268, 483, 371, 477, 92, "right", "wall"),
    PoiSpec("巨石阵", 114.810, 39.285, "徒步", "免费", "导航到感恩石，徒步1小时", 269, 508, 379, 501, 82, "right", "dark"),
    PoiSpec("涞源抗战纪念馆", 114.825, 39.270, "", "", "", 269, 522, 379, 524, 89, "right"),
    PoiSpec("涞源县生态文明纪念区", 114.940, 39.170, "", "", "", 368, 551, 441, 557, 88, "right"),
    PoiSpec("天桥瀑布群", 114.785, 39.115, "", "", "", 302, 554, 304, 546, 83, "right"),
    PoiSpec("鹤望长廊", 114.735, 39.090, "", "", "白石山主要景点，沿悬崖栈道游览", 254, 552, 300, 577, 78, "right"),
    PoiSpec("白石山", 114.700, 39.218, "景区", "￥135", "世界地质公园；东门索道上山，游览约 5—6 小时", 273, 608, 303, 610, 205, "right", "major"),
    PoiSpec("白银坨", 114.870, 39.075, "", "", "", 369, 650, 305, 644, 61, "left"),
    PoiSpec("古北岳", 114.610, 39.090, "", "", "", 203, 658, 305, 677, 57, "right"),
)


CONTEXT_LABELS = {
    "蔚县": (114.49, 39.72),
    "灵丘": (114.18, 39.40),
    "涞水": (115.14, 39.69),
    "易县": (115.12, 39.25),
    "唐县": (114.66, 38.99),
}


ROADS = (
    ("北部山路", "县道", ((114.705, 39.78), (114.720, 39.69), (114.690, 39.62), (114.700, 39.54), (114.675, 39.45), (114.690, 39.37))),
    ("西北山路", "县道", ((114.480, 39.69), (114.475, 39.60), (114.500, 39.52), (114.535, 39.46), (114.600, 39.40), (114.690, 39.37))),
    ("东北山路", "县道", ((114.955, 39.75), (114.940, 39.66), (114.925, 39.59), (114.900, 39.50), (114.840, 39.42), (114.690, 39.37))),
    ("东部山路", "县道", ((115.090, 39.55), (115.005, 39.49), (114.950, 39.43), (114.875, 39.39), (114.790, 39.36), (114.690, 39.37))),
    ("西部山路", "县道", ((114.300, 39.43), (114.390, 39.42), (114.470, 39.40), (114.560, 39.38), (114.690, 39.37))),
    ("西南峡谷路", "县道", ((114.345, 39.23), (114.420, 39.28), (114.480, 39.31), (114.535, 39.33), (114.610, 39.35), (114.690, 39.37))),
    ("南部山路", "县道", ((114.585, 39.03), (114.600, 39.13), (114.625, 39.22), (114.650, 39.29), (114.690, 39.37))),
    ("东南景区路", "县道", ((114.970, 39.09), (114.900, 39.14), (114.835, 39.20), (114.780, 39.27), (114.735, 39.33), (114.690, 39.37))),
    ("荣乌高速", "高速", ((114.25, 39.41), (114.38, 39.40), (114.50, 39.39), (114.60, 39.38), (114.69, 39.37), (114.80, 39.37), (114.94, 39.39), (115.14, 39.43))),
    ("涞涞高速", "高速", ((114.67, 39.38), (114.73, 39.33), (114.78, 39.28), (114.84, 39.22), (114.92, 39.16), (115.05, 39.10))),
    ("G207", "国道", ((114.64, 39.76), (114.64, 39.66), (114.66, 39.56), (114.67, 39.46), (114.69, 39.37), (114.68, 39.27), (114.66, 39.15), (114.64, 39.02))),
)


RIVERS = (
    ("拒马河", ((114.665, 39.385), (114.705, 39.360), (114.755, 39.348), (114.815, 39.350), (114.880, 39.370), (114.950, 39.395))),
    ("唐河", ((114.590, 39.120), (114.620, 39.190), (114.625, 39.255), (114.600, 39.315), (114.550, 39.365), (114.495, 39.430))),
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
    shadow = memory_layer(
        "MultiPolygon",
        "涞源县轮廓光",
        fields + [QgsField("level", QVariant.Int)],
    )
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
                # Keep the administrative polygon as the visible outline. The
                # reference-derived polygon remains a separate calibration
                # artifact; its raster quantisation is unsuitable for a
                # smooth 531 px export.
                visible_geometry = geometry
                selected = QgsFeature(focus.fields())
                selected.setAttributes([name, adcode])
                selected.setGeometry(visible_geometry)
                focus_features.append(selected)
                previous = visible_geometry
                for suffix, distance in enumerate(
                    (0.0025, 0.0050, 0.0075, 0.0100, 0.0125, 0.0150, 0.0175, 0.0200),
                    start=1,
                ):
                    buffered = visible_geometry.buffer(distance, 32)
                    glow = QgsFeature(shadow.fields())
                    glow.setAttributes([f"{name}_{suffix}", adcode, suffix])
                    glow.setGeometry(buffered.difference(previous))
                    shadow_features.append(glow)
                    previous = buffered

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
    clip_layer: QgsVectorLayer | None = None,
) -> QgsVectorLayer:
    layer = memory_layer(
        "MultiLineString",
        name,
        [QgsField("name", QVariant.String), QgsField("class", QVariant.String)],
    )
    clip_geometry = None
    if clip_layer is not None:
        clip_geometry = QgsGeometry.unaryUnion(
            [feature.geometry() for feature in clip_layer.getFeatures()]
        )
    features = []
    for record in records:
        line_name, line_class, coordinates = record
        geometry = QgsGeometry.fromPolylineXY(
            [QgsPointXY(x, y) for x, y in coordinates]
        )
        if clip_geometry is not None:
            geometry = geometry.intersection(clip_geometry)
        if geometry.isNull() or geometry.isEmpty():
            continue
        if QgsWkbTypes.geometryType(geometry.wkbType()) != Qgis.GeometryType.Line:
            continue
        feature = QgsFeature(layer.fields())
        feature.setAttributes([line_name, line_class])
        feature.setGeometry(geometry)
        features.append(feature)
    layer.dataProvider().addFeatures(features)
    layer.updateExtents()
    return write_layer(project, layer, output_name)


def build_river_layer(
    project: QgsProject, clip_layer: QgsVectorLayer | None = None
) -> QgsVectorLayer:
    records = tuple((name, "河流", coordinates) for name, coordinates in RIVERS)
    return build_line_layer(project, "河流", "rivers", records, clip_layer)


def build_osm_network_layers(
    project: QgsProject, clip_layer: QgsVectorLayer
) -> tuple[QgsVectorLayer, QgsVectorLayer]:
    """Build a restrained real road/water network from the cached OSM extract."""
    if not OSM_NETWORK.exists():
        return (
            build_line_layer(project, "道路骨架", "roads", ROADS, clip_layer),
            build_river_layer(project, clip_layer),
        )

    with gzip.open(OSM_NETWORK, "rt", encoding="utf-8") as source:
        payload = json.load(source)

    road_records = []
    river_records = []
    major_classes = {"motorway", "trunk", "primary", "secondary"}
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue
        coordinates = tuple((float(point["lon"]), float(point["lat"])) for point in geometry)
        highway = tags.get("highway")
        if highway in major_classes or (highway == "tertiary" and tags.get("name")):
            road_records.append(
                (tags.get("name") or f"OSM {element.get('id')}", highway, coordinates)
            )
        waterway = tags.get("waterway")
        if waterway in {"river", "stream"}:
            river_records.append(
                (tags.get("name") or f"OSM {element.get('id')}", waterway, coordinates)
            )

    return (
        build_line_layer(project, "真实道路", "roads", tuple(road_records), clip_layer),
        build_line_layer(project, "真实河流", "rivers", tuple(river_records), clip_layer),
    )


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
        QgsField("theme", QVariant.String),
        QgsField("anchor_x", QVariant.Double),
        QgsField("anchor_y", QVariant.Double),
    ]
    layer = memory_layer("Point", "旅游景点", fields)
    features = []
    for poi in POIS:
        feature = QgsFeature(layer.fields())
        feature.setAttributes(
            [
                poi.name,
                poi.category,
                poi.tag,
                poi.note,
                poi.card_x,
                poi.card_y,
                poi.card_w,
                poi.side,
                poi.theme,
                poi.anchor_x,
                poi.anchor_y,
            ]
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
            "color": "247,247,247,255",
            "outline_color": "#DDE7DF",
            "outline_width": "0.15",
            "outline_width_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_shadow(layer: QgsVectorLayer) -> None:
    categories = []
    alphas = (58, 46, 35, 25, 17, 11, 7, 3)
    for level, alpha in enumerate(alphas, start=1):
        symbol = QgsFillSymbol.createSimple(
            {
                "color": f"76,94,73,{alpha}",
                "outline_style": "no",
            }
        )
        categories.append(QgsRendererCategory(level, symbol, f"轮廓光 {level}"))
    layer.setRenderer(QgsCategorizedSymbolRenderer("level", categories))


def style_focus(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "191,226,172,255",
            "outline_color": "#F7FFF3",
            "outline_width": "0.34",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_roads(layer: QgsVectorLayer) -> None:
    categories = []
    widths = {
        "motorway": 0.25,
        "trunk": 0.23,
        "primary": 0.21,
        "secondary": 0.17,
        "tertiary": 0.13,
        "国道": 0.21,
        "高速": 0.25,
        "县道": 0.13,
    }
    for road_class, width in widths.items():
        symbol = QgsLineSymbol.createSimple(
            {
                "line_color": "119,183,98,142",
                "line_width": str(width),
                "line_width_unit": "MM",
                "capstyle": "round",
                "joinstyle": "round",
            }
        )
        categories.append(QgsRendererCategory(road_class, symbol, road_class))
    layer.setRenderer(QgsCategorizedSymbolRenderer("class", categories))


def style_rivers(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": "129,202,193,150",
            "line_width": "0.16",
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
            "size": "0",
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
    radius: float = 0.0,
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
    if radius:
        item.setCornerRadius(
            QgsLayoutMeasurement(radius, QgsUnitTypes.LayoutMillimeters)
        )
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


def mm_x(pixels: float) -> float:
    return pixels * PX_X


def mm_y(pixels: float) -> float:
    return pixels * PX_Y


def px_point(x: float, y: float) -> QPointF:
    return QPointF(mm_x(x), mm_y(y))


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
    bar = add_shape(layout, mm_x(3), mm_y(7), mm_x(525), mm_y(22), "#020302")
    bar.setId("刊头_黑条")
    add_shape(layout, mm_x(14), mm_y(11), mm_x(17), mm_y(16), "#FFFFFF", "#B8C0BA", 0.16)
    add_label(layout, "【北京周边系列】", mm_x(39), mm_y(7), mm_x(119), mm_y(22), 6.8, color="#FFFFFF", bold=True)
    add_label(layout, "之保定 · 小城", mm_x(161), mm_y(7), mm_x(95), mm_y(22), 6.8, color="#EFFF20", bold=True)
    add_label(layout, "#第2-005期/100", mm_x(310), mm_y(7), mm_x(96), mm_y(22), 6.5, color="#FFFFFF", bold=True, align=Qt.AlignCenter)
    add_ellipse(layout, mm_x(416), mm_y(8), mm_x(21), mm_y(20), "#F7F8F7", "#657069", 0.24)
    add_ellipse(layout, mm_x(423), mm_y(11), mm_x(7), mm_y(7), "#4D5550")
    add_shape(layout, mm_x(420), mm_y(18), mm_x(13), mm_y(7), "#78837C", radius=0.8)
    add_label(layout, "@冷三岁 · 制作", mm_x(441), mm_y(7), mm_x(84), mm_y(22), 6.2, color="#FFFFFF", bold=True, align=Qt.AlignRight)


def add_title(layout: QgsPrintLayout) -> None:
    add_shape(layout, mm_x(17), mm_y(66), mm_x(20), mm_y(42), "#050705", "#050705", 0.25, radius=2.4)
    add_label(layout, "保\n定", mm_x(18), mm_y(67), mm_x(18), mm_y(40), 6.7, color="#FFFFFF", bold=True, align=Qt.AlignCenter)
    add_label(layout, "涞源县", mm_x(39), mm_y(65), mm_x(267), mm_y(90), 55.0, FONT_TITLE, "#020402", bold=True)
    add_label(
        layout,
        "北京周边",
        mm_x(309),
        mm_y(68),
        mm_x(218),
        mm_y(61),
        31.0,
        FONT_TITLE,
        "#050705",
        bold=True,
        buffer_color="#FFF500",
        buffer_size=1.25,
    )
    add_label(layout, "保定各区县旅游·第01/21", mm_x(323), mm_y(123), mm_x(194), mm_y(31), 9.2, FONT_SANS, "#111511", bold=True, align=Qt.AlignCenter)
    add_label(layout, "北", mm_x(42), mm_y(174), mm_x(20), mm_y(17), 6.4, FONT_SANS, "#151A16", bold=True, align=Qt.AlignCenter)
    add_label(layout, "▲", mm_x(42), mm_y(186), mm_x(20), mm_y(27), 13.5, FONT_SANS, "#090B09", bold=True, align=Qt.AlignCenter)


def add_city_badge(layout: QgsPrintLayout, project: QgsProject, map_item: QgsLayoutItemMap) -> None:
    add_shape(layout, mm_x(257), mm_y(318), mm_x(72), mm_y(25), "194,230,151,245", "#294D29", 0.38, radius=1.6)
    add_label(layout, "涞源县城区", mm_x(258), mm_y(319), mm_x(70), mm_y(23), 7.8, FONT_SANS, "#152B14", bold=True, align=Qt.AlignCenter)
    add_shape(layout, mm_x(257), mm_y(292), mm_x(77), mm_y(12), "248,248,244,245", "#DFE3DC", 0.12, radius=0.7)
    add_label(layout, "到北京火车3h/￥32", mm_x(260), mm_y(291), mm_x(72), mm_y(13), 4.3, FONT_SANS, "#202420", bold=True, align=Qt.AlignCenter)
    add_shape(layout, mm_x(257), mm_y(305), mm_x(77), mm_y(12), "248,248,244,245", "#DFE3DC", 0.12, radius=0.7)
    add_label(layout, "距北京210KM/3.0h", mm_x(260), mm_y(304), mm_x(72), mm_y(13), 4.2, FONT_SANS, "#202420", bold=True, align=Qt.AlignCenter)
    line = add_polyline(layout, [px_point(265, 343), px_point(265, 407)], "#1E261F", 0.33)
    line.setId("城区引线")
    add_ellipse(layout, mm_x(258), mm_y(402), mm_x(14), mm_y(14), "#111512", "#E6ECE5", 0.18)
    add_label(layout, "涞", mm_x(259), mm_y(402), mm_x(12), mm_y(12), 5.2, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
    add_label(layout, "图", mm_x(258), mm_y(414), mm_x(14), mm_y(12), 4.0, FONT_SANS, "#394039", bold=True, align=Qt.AlignCenter)


def add_poi_callout(
    layout: QgsPrintLayout,
    project: QgsProject,
    map_item: QgsLayoutItemMap,
    poi: PoiSpec,
) -> None:
    anchor = px_point(poi.anchor_x, poi.anchor_y)
    card_x = mm_x(poi.card_x)
    card_y = mm_y(poi.card_y)
    card_w = mm_x(poi.card_w)
    card_h = mm_y(24.0 if poi.note else 15.0)
    # Reference leaders terminate on the first-line name/chip row, not in the
    # smaller explanatory text below it.
    card_center_y = card_y + mm_y(7.0)
    if poi.side == "left":
        edge_x = card_x + card_w
        elbow_x = min(anchor.x() - mm_x(8), edge_x + mm_x(15))
    else:
        edge_x = card_x
        elbow_x = max(anchor.x() + mm_x(8), edge_x - mm_x(15))
    leader = add_polyline(
        layout,
        [
            QPointF(anchor.x(), anchor.y()),
            QPointF(elbow_x, anchor.y()),
            QPointF(elbow_x, card_center_y),
            QPointF(edge_x, card_center_y),
        ],
        "#3D463E",
        0.27,
        dashed=True,
    )
    leader.setId(f"引线_{poi.name}")

    dot_fill = "#E9F000" if poi.theme == "major" else "#0A0E0B"
    dot = add_ellipse(
        layout,
        anchor.x() - mm_x(3.2),
        anchor.y() - mm_y(3.2),
        mm_x(6.4),
        mm_y(6.4),
        dot_fill,
        "#E9F1E8",
        0.22,
    )
    dot.setId(f"景点锚点_{poi.name}")

    cursor = card_x
    chip_h = mm_y(14)
    if poi.theme == "major":
        add_shape(layout, card_x, card_y, card_w, mm_y(40), "255,255,255,232", "#D7DED5", 0.12, radius=0.7)
        add_shape(layout, card_x, card_y, mm_x(5), mm_y(17), "#E7EF00", "255,255,255,0", 0.0)
        add_label(layout, poi.name, card_x + mm_x(9), card_y, mm_x(52), mm_y(17), 6.4, FONT_SANS, "#111511", bold=True)
        add_shape(layout, card_x + mm_x(66), card_y + mm_y(1), mm_x(29), mm_y(14), "#242B26", "255,255,255,0", 0.0, radius=1.0)
        add_label(layout, "景区", card_x + mm_x(68), card_y + mm_y(1), mm_x(25), mm_y(14), 4.4, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
        add_shape(layout, card_x + mm_x(99), card_y + mm_y(1), mm_x(37), mm_y(14), "#22B99B", "255,255,255,0", 0.0, radius=1.0)
        add_label(layout, "推荐", card_x + mm_x(101), card_y + mm_y(1), mm_x(33), mm_y(14), 4.4, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
        add_shape(layout, card_x + mm_x(140), card_y + mm_y(1), mm_x(43), mm_y(14), "#92D94F", "255,255,255,0", 0.0, radius=1.0)
        add_label(layout, poi.tag, card_x + mm_x(142), card_y + mm_y(1), mm_x(39), mm_y(14), 4.4, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
        add_label(layout, poi.note, card_x + mm_x(8), card_y + mm_y(17), card_w - mm_x(13), mm_y(21), 3.8, FONT_SANS, "#4E5750", False)
        return
    elif poi.category:
        badge_w = mm_x(max(24, 8 + 7 * len(poi.category)))
        badge_color = "#22B99B" if poi.category in {"长城", "辽代", "唐代石狮", "徒步", "景区"} else "#7ED14D"
        add_shape(layout, cursor, card_y, badge_w, chip_h, badge_color, "#FFFFFF", 0.10, radius=1.2)
        add_label(layout, poi.category, cursor + mm_x(2), card_y, badge_w - mm_x(4), chip_h, 4.7, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
        cursor += badge_w + mm_x(1.5)

    if poi.theme == "price" and poi.name != "空中草原":
        name_w = mm_x(max(42, len(poi.name) * 12 + 8))
        add_shape(layout, cursor, card_y, name_w, chip_h, "#B6F48B", "#D6E8C7", 0.10, radius=1.4)
        add_label(layout, poi.name, cursor + mm_x(3), card_y, name_w - mm_x(6), chip_h, 5.0, FONT_SANS, "#152214", bold=True, align=Qt.AlignCenter)
        cursor += name_w + mm_x(1.5)

    if poi.tag:
        if poi.theme == "price" and poi.tag.startswith("￥"):
            tag_w = mm_x(66 if poi.name == "空中草原" else 31)
        else:
            tag_w = mm_x(max(22, 8 + 6 * len(poi.tag)))
        tag_fill = "#8FD950" if poi.tag.startswith("￥") else "#AEEA70"
        add_shape(layout, cursor, card_y, tag_w, chip_h, tag_fill, "#FFFFFF", 0.10, radius=1.2)
        add_label(layout, poi.tag, cursor + mm_x(2), card_y, tag_w - mm_x(4), chip_h, 4.5, FONT_SANS, "#FFFFFF" if poi.tag.startswith("￥") else "#304C25", bold=True, align=Qt.AlignCenter)
        cursor += tag_w + mm_x(1.5)

    remaining = max(mm_x(22), card_x + card_w - cursor)
    if poi.theme == "dark":
        name_fill, name_color = "#050706", "#FFFFFF"
    else:
        name_fill, name_color = "#B6F48B", "#152214"
    if poi.theme != "major" and not (poi.theme == "price" and poi.name != "空中草原"):
        desired = mm_x(max(31, len(poi.name) * 11 + 8))
        name_w = min(remaining, desired)
        add_shape(layout, cursor, card_y, name_w, chip_h, name_fill, "#D6E8C7", 0.10, radius=1.4)
        add_label(layout, poi.name, cursor + mm_x(2), card_y, max(mm_x(18), name_w - mm_x(4)), chip_h, 4.7, FONT_SANS, name_color, bold=True, align=Qt.AlignCenter)
    if poi.note:
        note_y = card_y + mm_y(16.0) if poi.name == "巨石阵" else card_y + chip_h
        note_height = mm_y(12.0) if poi.name != "巨石阵" else mm_y(10.0)
        note_size = 3.7 if poi.name != "巨石阵" else 4.2
        note_color = "#4E5750" if poi.name == "巨石阵" else "#59635A"
        add_label(layout, poi.note, card_x, note_y, card_w, note_height, note_size, FONT_SANS, note_color, False)


def add_legend(layout: QgsPrintLayout) -> None:
    add_shape(layout, mm_x(24), mm_y(598), mm_x(122), mm_y(101), "239,247,232,222", "255,255,255,0", 0.0)
    add_shape(layout, mm_x(24), mm_y(598), mm_x(122), mm_y(7), "#111512")
    add_ellipse(layout, mm_x(29), mm_y(607), mm_x(30), mm_y(30), "#F7F8F6", "#59625C", 0.28)
    add_ellipse(layout, mm_x(40), mm_y(611), mm_x(8), mm_y(8), "#535B56")
    add_shape(layout, mm_x(35), mm_y(620), mm_x(18), mm_y(11), "#747D77", radius=1.0)
    add_label(layout, "冷三岁·注", mm_x(61), mm_y(606), mm_x(72), mm_y(26), 7.2, FONT_SANS, "#172017", bold=True)
    rows = (
        ("#E7EF00", "白石山", "必打卡", "#F4F500"),
        ("#070A08", "悦客公园", "推荐打卡", "#FFFFFF"),
        ("#184716", "仙人峪", "可打卡", "#183516"),
    )
    for index, (dot_color, label, note, label_color) in enumerate(rows):
        y = 641 + index * 25
        add_ellipse(layout, mm_x(34), mm_y(y), mm_x(12), mm_y(12), dot_color, "#EAF0E8", 0.16)
        if index in {0, 2}:
            add_ellipse(layout, mm_x(37), mm_y(y + 3), mm_x(6), mm_y(6), "#080B08")
        fill = "#050706" if index < 2 else "#B4F48A"
        add_shape(layout, mm_x(49), mm_y(y - 1), mm_x(57), mm_y(16), fill, "255,255,255,0", 0.0, radius=1.5)
        add_label(layout, label, mm_x(51), mm_y(y - 1), mm_x(53), mm_y(16), 6.0, FONT_SANS, label_color, bold=True, align=Qt.AlignCenter)
        add_label(layout, note, mm_x(113), mm_y(y - 1), mm_x(31), mm_y(16), 5.8, FONT_SANS, "#1E261F", bold=True)


def add_reference_linework(layout: QgsPrintLayout) -> None:
    """Add the faint contextual network visible behind the infographic."""
    paths = (
        ((6, 58), (65, 48), (116, 51), (161, 38), (222, 42), (285, 30)),
        ((72, 29), (78, 85), (96, 121), (105, 178), (129, 211)),
        ((152, 30), (164, 69), (176, 105), (184, 164), (203, 207)),
        ((254, 31), (251, 91), (248, 145), (249, 206)),
        ((346, 30), (334, 75), (344, 119), (361, 160)),
        ((424, 31), (411, 79), (425, 127), (442, 170)),
        ((523, 55), (481, 78), (456, 120), (463, 168)),
        ((5, 294), (47, 308), (83, 332), (114, 369)),
        ((5, 370), (38, 356), (71, 345), (105, 345)),
        ((6, 524), (54, 532), (94, 553), (125, 583)),
        ((411, 547), (452, 523), (490, 513), (527, 518)),
        ((392, 623), (429, 608), (474, 614), (528, 640)),
        ((347, 697), (398, 669), (448, 670), (527, 691)),
        ((5, 660), (44, 644), (78, 650), (111, 681)),
    )
    for index, path in enumerate(paths):
        item = add_polyline(
            layout,
            [px_point(x, y) for x, y in path],
            "#DDEADB",
            0.22,
        )
        item.setId(f"周边浅色线网_{index + 1}")


def add_minor_annotations(layout: QgsPrintLayout) -> None:
    # The summit block and secondary place labels are deliberately quieter than
    # attraction cards, matching the hierarchy of the reference infographic.
    add_label(layout, "2159米 ▲\n东甸子梁", mm_x(366), mm_y(156), mm_x(64), mm_y(29), 5.1, FONT_SANS, "#202520", bold=True, align=Qt.AlignCenter)
    add_shape(layout, mm_x(369), mm_y(181), mm_x(25), mm_y(13), "#91D851", "#FFFFFF", 0.1, radius=1.0)
    add_label(layout, "免费", mm_x(369), mm_y(181), mm_x(25), mm_y(13), 4.3, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)
    add_shape(layout, mm_x(397), mm_y(181), mm_x(27), mm_y(13), "#23B99D", "#FFFFFF", 0.1, radius=1.0)
    add_label(layout, "徒步", mm_x(397), mm_y(181), mm_x(27), mm_y(13), 4.3, FONT_SANS, "#FFFFFF", bold=True, align=Qt.AlignCenter)

    muted = (
        ("王安镇", 242, 278, "#B97747"),
        ("杨家庄镇", 446, 277, "#B97747"),
        ("金家井乡", 289, 365, "#B97747"),
        ("银坊镇", 286, 514, "#B97747"),
        ("走马驿镇", 252, 637, "#B97747"),
        ("水堡镇", 160, 452, "#72BDB4"),
        ("南屯镇", 301, 406, "#74C7BB"),
        ("北石佛镇", 297, 421, "#74C7BB"),
        ("涞源汽车站", 293, 438, "#74C7BB"),
        ("拒马源", 335, 448, "#7DB5D7"),
        ("白石山镇", 186, 486, "#78BEB5"),
        ("白石山大街", 185, 506, "#78BEB5"),
    )
    for name, x, y, color in muted:
        add_label(layout, name, mm_x(x), mm_y(y), mm_x(max(45, len(name) * 13)), mm_y(13), 3.8, FONT_SANS, color, bold=False)

    add_polyline(layout, [px_point(260, 567), px_point(260, 611), px_point(296, 611)], "#3F4740", 0.27, dashed=True)
    add_label(layout, "▲", mm_x(251), mm_y(557), mm_x(18), mm_y(24), 11.5, FONT_SANS, "#111411", bold=True, align=Qt.AlignCenter)


def add_reference_calibration(layout: QgsPrintLayout) -> None:
    """Keep the supplied image in-project as a hidden tracing/calibration item."""
    if not REFERENCE_IMAGE.exists():
        return
    picture = QgsLayoutItemPicture(layout)
    picture.setId("校准底图_导出时关闭")
    picture.setPicturePath(str(REFERENCE_IMAGE))
    picture.setResizeMode(QgsLayoutItemPicture.Stretch)
    layout.addLayoutItem(picture)
    picture.attemptMove(QgsLayoutPoint(0, 0, QgsUnitTypes.LayoutMillimeters))
    picture.attemptResize(QgsLayoutSize(*PAGE, QgsUnitTypes.LayoutMillimeters))
    picture.setLocked(True)
    picture.setVisibility(False)


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

    add_reference_linework(layout)
    add_header(layout)
    add_title(layout)
    add_city_badge(layout, project, map_item)
    add_minor_annotations(layout)
    for poi in POIS:
        add_poi_callout(layout, project, map_item, poi)
    add_legend(layout)
    add_reference_calibration(layout)
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
        roads, rivers = build_osm_network_layers(project, focus)
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
            "road_count": roads.featureCount(),
            "river_count": rivers.featureCount(),
            "glow_ring_count": shadow.featureCount(),
            "calibration_reference": str(REFERENCE_IMAGE),
            "calibration_visible": False,
            "network_source": "OpenStreetMap cached extract",
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
