"""Build the K158 Zhanjiang-Beijing West route map."""

from __future__ import annotations

import json
import sys
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


RAILWAY_ROOT = Path(r"F:\Desktop\Blog\Map")
SCRIPT_DIR = Path(__file__).resolve().parent
TIMETABLE = SCRIPT_DIR / "timetable_2026-08-23.json"
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "全国专题图" / "K158路线图"
ROUTE_GPKG = OUTPUT_DIR / "K158线路.gpkg"
OUTPUT_GPKG = OUTPUT_DIR / "K158路线图_数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "K158路线图.qgz"
OUTPUT_PNG = OUTPUT_DIR / "K158路线图.png"
PROVINCE_SOURCE = RAILWAY_ROOT / "province" / "province.json"
CITY_SOURCE = RAILWAY_ROOT / "city" / "city.json"

PAGE_SIZE = (280.0, 400.0)
MAP_FRAME = (12.0, 42.0, 256.0, 346.0)
CHINA_ALBERS_PROJ = (
    "+proj=aea +lat_1=25 +lat_2=47 +lat_0=0 +lon_0=105 "
    "+datum=WGS84 +units=m +no_defs +type=crs"
)


def text_format(
    size: float,
    family: str,
    color: str = "#202020",
    bold: bool = False,
    buffer_size: float = 0.0,
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
        buffer.setColor(QColor("#FFFFFF"))
        buffer.setSize(buffer_size)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(buffer)
    return fmt


def load_vector(
    path: Path, name: str, layer_name: str | None = None, subset: str | None = None
) -> QgsVectorLayer:
    uri = str(path)
    if layer_name:
        uri = f"{uri}|layername={layer_name}"
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid vector layer: {uri}")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Unable to set subset for {name}: {subset}")
    return layer


def save_layer(
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
        raise RuntimeError(f"Unable to save {layer_name}: {message}")
    saved = load_vector(OUTPUT_GPKG, layer_name, layer_name)
    project.addMapLayer(saved)
    return saved


def copy_source_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    layer_name: str,
    overwrite_file: bool = False,
    merge_lines: bool = False,
) -> QgsVectorLayer:
    geometry_name = QgsWkbTypes.displayString(source.wkbType())
    memory = QgsVectorLayer(
        f"{geometry_name}?crs={source.crs().authid()}", layer_name, "memory"
    )
    memory.dataProvider().addAttributes(source.fields().toList())
    memory.updateFields()
    features = []
    for source_feature in source.getFeatures():
        feature = QgsFeature(memory.fields())
        geometry = source_feature.geometry()
        if merge_lines:
            merged = geometry.mergeLines()
            if not merged.isNull() and not merged.isEmpty():
                geometry = merged
            if not QgsWkbTypes.isMultiType(geometry.wkbType()):
                geometry.convertToMultiType()
        feature.setGeometry(geometry)
        feature.setAttributes(source_feature.attributes())
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    return save_layer(project, memory, layer_name, overwrite_file)


def build_station_layers(
    project: QgsProject, payload: dict
) -> tuple[QgsVectorLayer, QgsVectorLayer, QgsVectorLayer]:
    fields = [
        QgsField("seq", QVariant.Int),
        QgsField("name", QVariant.String),
        QgsField("label", QVariant.String),
        QgsField("day", QVariant.Int),
        QgsField("arrival", QVariant.String),
        QgsField("departure", QVariant.String),
        QgsField("role", QVariant.String),
    ]
    stations = QgsVectorLayer("Point?crs=EPSG:4326", "K158经停站", "memory")
    stations.dataProvider().addAttributes(fields)
    stations.updateFields()
    intermediate_labels = QgsVectorLayer(
        "Point?crs=EPSG:4326", "经停站标签", "memory"
    )
    intermediate_labels.dataProvider().addAttributes(fields)
    intermediate_labels.updateFields()
    endpoint_labels = QgsVectorLayer("Point?crs=EPSG:4326", "起终点标签", "memory")
    endpoint_labels.dataProvider().addAttributes(fields)
    endpoint_labels.updateFields()

    coordinates = payload["station_matches"]
    station_features = []
    intermediate_features = []
    endpoint_features = []
    for stop in payload["stops"]:
        name = stop["name"]
        lon = float(coordinates[name]["lon"])
        lat = float(coordinates[name]["lat"])
        if stop["no"] == 1:
            role = "origin"
            label = "湛江"
        elif stop["no"] == len(payload["stops"]):
            role = "destination"
            label = "北京西"
        else:
            role = "stop"
            label = name
        attributes = [
            stop["no"],
            name,
            label,
            stop["day"],
            stop["arrival"] or "",
            stop["departure"] or "",
            role,
        ]

        station = QgsFeature(stations.fields())
        station.setGeometry(QgsGeometry.fromWkt(f"POINT ({lon} {lat})"))
        station.setAttributes(attributes)
        station_features.append(station)

        side = -1 if stop["no"] % 2 else 1
        label_lon = lon + side * 0.38
        label_lat = lat
        special_offsets = {
            1: (0.48, -0.12),
            2: (0.42, 0.08),
            3: (-0.44, 0.08),
            31: (-0.52, 0.05),
        }
        if stop["no"] in special_offsets:
            lon_offset, lat_offset = special_offsets[stop["no"]]
            label_lon = lon + lon_offset
            label_lat = lat + lat_offset
        label_feature = QgsFeature(
            endpoint_labels.fields() if role != "stop" else intermediate_labels.fields()
        )
        label_feature.setGeometry(
            QgsGeometry.fromWkt(f"POINT ({label_lon} {label_lat})")
        )
        label_feature.setAttributes(attributes)
        if role == "stop":
            intermediate_features.append(label_feature)
        else:
            endpoint_features.append(label_feature)

    stations.dataProvider().addFeatures(station_features)
    stations.updateExtents()
    intermediate_labels.dataProvider().addFeatures(intermediate_features)
    intermediate_labels.updateExtents()
    endpoint_labels.dataProvider().addFeatures(endpoint_features)
    endpoint_labels.updateExtents()
    saved_stations = save_layer(project, stations, "K158经停站")
    saved_intermediate = save_layer(project, intermediate_labels, "经停站标签")
    saved_endpoints = save_layer(project, endpoint_labels, "起终点标签")
    return saved_stations, saved_intermediate, saved_endpoints


def style_provinces(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#F4F6F6",
            "outline_color": "#A9B1B2",
            "outline_width": "0.16",
            "outline_width_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_city_highlight(layer: QgsVectorLayer, fill: str, outline: str) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": fill,
            "outline_color": outline,
            "outline_width": "0.32",
            "outline_width_unit": "MM",
        }
    )
    symbol.setOpacity(0.58)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_route(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol()
    symbol.deleteSymbolLayer(0)
    casing = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "#283237",
            "line_width": "1.12",
            "line_width_unit": "MM",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )
    planned = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "#FFFDF7",
            "line_width": "0.44",
            "line_width_unit": "MM",
            "line_style": "solid",
            "capstyle": "round",
            "joinstyle": "round",
        }
    )
    symbol.appendSymbolLayer(casing)
    symbol.appendSymbolLayer(planned)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_stations(layer: QgsVectorLayer) -> None:
    categories = []
    styles = {
        "stop": ("#B45765", 2.05),
        "origin": ("#C74F5E", 3.35),
        "destination": ("#2E7D83", 3.35),
    }
    labels = {"stop": "经停站", "origin": "起点", "destination": "终点"}
    for value, (color, size) in styles.items():
        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": color,
                "size": str(size),
                "size_unit": "MM",
                "outline_color": "#FFFFFF",
                "outline_width": "0.42",
                "outline_width_unit": "MM",
            }
        )
        categories.append(QgsRendererCategory(value, symbol, labels[value]))
    layer.setRenderer(QgsCategorizedSymbolRenderer("role", categories))


def style_label_layer(layer: QgsVectorLayer, endpoint: bool = False) -> None:
    invisible = QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "0", "outline_style": "no"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(invisible))
    settings = QgsPalLayerSettings()
    settings.fieldName = "label"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.displayAll = True
    settings.priority = 10
    settings.obstacle = False
    settings.setFormat(
        text_format(
            8.8 if endpoint else 8.2,
            "思源黑体 CN Medium",
            bold=endpoint,
            buffer_size=0.34,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def fit_extent(extent: QgsRectangle, aspect: float, margin: float = 0.04) -> QgsRectangle:
    extent = QgsRectangle(extent)
    extent.grow(max(extent.width(), extent.height()) * margin)
    current = extent.width() / extent.height()
    if current < aspect:
        target_width = extent.height() * aspect
        delta = (target_width - extent.width()) / 2.0
        extent.setXMinimum(extent.xMinimum() - delta)
        extent.setXMaximum(extent.xMaximum() + delta)
    elif current > aspect:
        target_height = extent.width() / aspect
        delta = (target_height - extent.height()) / 2.0
        extent.setYMinimum(extent.yMinimum() - delta)
        extent.setYMaximum(extent.yMaximum() + delta)
    return extent


def add_label(
    layout: QgsPrintLayout,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    family: str,
    color: str = "#202020",
    bold: bool = False,
    alignment: Qt.AlignmentFlag = Qt.AlignLeft,
) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(text_format(size, family, color=color, bold=bold))
    item.setHAlign(alignment)
    item.setVAlign(Qt.AlignVCenter)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(item)
    return item


def build_layout(
    project: QgsProject,
    layers: list[QgsVectorLayer],
    map_extent: QgsRectangle,
) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("K158路线图")
    page = layout.pageCollection().page(0)
    page.setPageSize(QgsLayoutSize(*PAGE_SIZE, QgsUnitTypes.LayoutMillimeters))

    add_label(
        layout,
        "K158路线图",
        12,
        8,
        256,
        17,
        25.5,
        "华文新魏",
        bold=True,
    )
    add_label(
        layout,
        "湛江—北京西｜09:54—次日22:48｜停靠31个车站｜里程 2725 km",
        12,
        27,
        256,
        8,
        9.2,
        "华文楷体",
        color="#555555",
        bold=True,
    )

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.attemptMove(
        QgsLayoutPoint(MAP_FRAME[0], MAP_FRAME[1], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.attemptResize(
        QgsLayoutSize(MAP_FRAME[2], MAP_FRAME[3], QgsUnitTypes.LayoutMillimeters)
    )
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)
    map_item.setExtent(map_extent)
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#7D8988"))
    map_item.setFrameStrokeWidth(
        QgsLayoutMeasurement(0.22, QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(map_item)

    project.layoutManager().addLayout(layout)
    return layout


def main() -> int:
    if not ROUTE_GPKG.exists():
        raise RuntimeError(f"Run build_route.py first: {ROUTE_GPKG}")
    payload = json.loads(TIMETABLE.read_text(encoding="utf-8"))
    if len(payload["stops"]) != 31:
        raise RuntimeError("K158 timetable must contain 31 stations")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        albers = QgsCoordinateReferenceSystem()
        if not albers.createFromProj(CHINA_ALBERS_PROJ):
            raise RuntimeError("Unable to create China Albers CRS")
        project.setCrs(albers)
        project.setFilePathStorage(Qgis.FilePathType.Relative)
        project.setPresetHomePath(str(OUTPUT_DIR))

        province_source = load_vector(PROVINCE_SOURCE, "省级行政区源数据")
        route_source = load_vector(ROUTE_GPKG, "K158路线源数据", "rail_routes")
        provinces = copy_source_layer(
            project, province_source, "省级行政区", overwrite_file=True
        )
        origin_city_source = load_vector(
            CITY_SOURCE, "起点城市源数据", subset='"name" = \'湛江市\''
        )
        destination_city_source = load_vector(
            PROVINCE_SOURCE, "终点城市源数据", subset='"name" = \'北京市\''
        )
        origin_city = copy_source_layer(project, origin_city_source, "起点城市")
        destination_city = copy_source_layer(project, destination_city_source, "终点城市")
        route = copy_source_layer(
            project, route_source, "K158路线", merge_lines=True
        )
        stations, intermediate_labels, endpoint_labels = build_station_layers(
            project, payload
        )

        style_provinces(provinces)
        style_city_highlight(origin_city, "#DDB6AA", "#9A5B54")
        style_city_highlight(destination_city, "#AFC9D6", "#4B7480")
        style_route(route)
        style_stations(stations)
        style_label_layer(intermediate_labels)
        style_label_layer(endpoint_labels, endpoint=True)

        layers = [
            endpoint_labels,
            intermediate_labels,
            stations,
            route,
            destination_city,
            origin_city,
            provinces,
        ]
        project.layerTreeRoot().setHasCustomLayerOrder(True)
        project.layerTreeRoot().setCustomLayerOrder(layers)

        transform = QgsCoordinateTransform(
            route.crs(), project.crs(), project.transformContext()
        )
        route_extent = transform.transformBoundingBox(route.extent())
        label_source_extent = QgsRectangle(endpoint_labels.extent())
        label_source_extent.combineExtentWith(intermediate_labels.extent())
        labels_extent = transform.transformBoundingBox(label_source_extent)
        route_extent.combineExtentWith(labels_extent)
        route_extent.combineExtentWith(
            transform.transformBoundingBox(origin_city.extent())
        )
        route_extent.combineExtentWith(
            transform.transformBoundingBox(destination_city.extent())
        )
        map_extent = fit_extent(
            route_extent, MAP_FRAME[2] / MAP_FRAME[3], margin=0.025
        )
        default_extent = QgsReferencedRectangle(map_extent, project.crs())
        project.viewSettings().setDefaultViewExtent(default_extent)
        project.viewSettings().setPresetFullExtent(default_extent)
        layout = build_layout(project, layers, map_extent)

        if not project.write(str(OUTPUT_QGZ)):
            raise RuntimeError(f"Unable to save project: {OUTPUT_QGZ}")
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 240
        OUTPUT_PNG.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Export failed: {result}")
        print(OUTPUT_PNG)
        print(OUTPUT_QGZ)
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
