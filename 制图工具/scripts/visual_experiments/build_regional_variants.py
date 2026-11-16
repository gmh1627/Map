"""Export regional visual hierarchy prototypes from existing QGIS projects."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsLineSymbol,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsLayoutExporter,
    QgsMarkerSymbol,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsRendererCategory,
    QgsSingleSymbolRenderer,
    QgsSimpleLineSymbolLayer,
    QgsVectorLayerSimpleLabeling,
)


MAP_ROOT = Path(__file__).resolve().parents[3]
REGIONAL_ROOT = MAP_ROOT / "地图输出" / "区域线路图"
OUTPUT_ROOT = MAP_ROOT / "地图输出" / "视觉优化试验" / "第二版_路线主角"
SOURCES = (
    ("东北漫游", "东北漫游"),
    ("小城小记3", "小城小记3"),
)


def symbols_from_renderer(renderer):
    symbols = []
    try:
        symbol = renderer.symbol()
        if symbol is not None:
            symbols.append(symbol)
    except Exception:
        pass
    try:
        symbols.extend(category.symbol() for category in renderer.categories())
    except Exception:
        pass
    return [symbol for symbol in symbols if symbol is not None]


def route_symbol(highspeed: bool):
    symbol = QgsLineSymbol()
    if highspeed:
        outer = QgsSimpleLineSymbolLayer(QColor("#FFFDF7"), 3.30)
        inner = QgsSimpleLineSymbolLayer(QColor("#167F86"), 1.78)
    else:
        outer = QgsSimpleLineSymbolLayer(QColor("#182629"), 2.80)
        inner = QgsSimpleLineSymbolLayer(QColor("#FFFDF7"), 1.04)
    for line in (outer, inner):
        line.setWidthUnit(Qgis.RenderUnit.Millimeters)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def style_routes(layer) -> None:
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "service",
            [
                QgsRendererCategory("highspeed", route_symbol(True), "高铁/动车"),
                QgsRendererCategory("conventional", route_symbol(False), "普铁"),
            ],
        )
    )
    layer.triggerRepaint()


def style_boundary(layer, color: str, width: float) -> None:
    symbol = QgsLineSymbol()
    line = QgsSimpleLineSymbolLayer(QColor(color), width)
    line.setWidthUnit(Qgis.RenderUnit.Millimeters)
    symbol.changeSymbolLayer(0, line)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def enlarge_labels(layer, factor: float, minimum: float | None = None) -> None:
    if layer.labeling() is None:
        return
    try:
        settings = layer.labeling().settings()
        fmt = settings.format()
        size = float(fmt.size()) * factor
        if minimum is not None:
            size = max(size, minimum)
        fmt.setSize(size)
        settings.setFormat(fmt)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)
    except Exception:
        return


def enlarge_station_marker(layer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#FFFDF7",
            "outline_color": "#30383A",
            "outline_width": "0.42",
            "outline_width_unit": "MM",
            "size": "2.45",
            "size_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.triggerRepaint()


def add_sequence_layer(project, stations_layer):
    """Add visible sequence badges at the actual visited station points."""
    route_layer = next(
        (layer for layer in project.mapLayers().values() if layer.name() == "实际铁路行程"),
        None,
    )
    if route_layer is None:
        return None

    ordered_names = []
    for feature in sorted(route_layer.getFeatures(), key=lambda item: int(item["seq"])):
        for name in (str(feature["origin"]), str(feature["destination"])):
            if name not in ordered_names:
                ordered_names.append(name)

    def normalize(value):
        return str(value).replace("站", "").replace("南", "南")

    coordinates = {}
    for feature in stations_layer.getFeatures():
        name = str(feature["name"])
        coordinates.setdefault(normalize(name), feature.geometry().asPoint())

    sequence = QgsVectorLayer(
        f"Point?crs={stations_layer.crs().authid()}", "行程顺序", "memory"
    )
    provider = sequence.dataProvider()
    provider.addAttributes(
        [
            QgsField("seq", QVariant.Int),
            QgsField("display", QVariant.String),
            QgsField("role", QVariant.String),
        ]
    )
    sequence.updateFields()
    features = []
    for index, name in enumerate(ordered_names, start=1):
        point = coordinates.get(normalize(name))
        if point is None:
            continue
        feature = QgsFeature(sequence.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(point)))
        feature.setAttributes(
            [
                index,
                name,
                "endpoint" if index in {1, len(ordered_names)} else "waypoint",
            ]
        )
        features.append(feature)
    provider.addFeatures(features)
    sequence.updateExtents()

    endpoint = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#D85D6D",
            "outline_color": "#FFFDF7",
            "outline_width": "0.65",
            "outline_width_unit": "MM",
            "size": "4.8",
            "size_unit": "MM",
        }
    )
    waypoint = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#167F86",
            "outline_color": "#FFFDF7",
            "outline_width": "0.52",
            "outline_width_unit": "MM",
            "size": "3.2",
            "size_unit": "MM",
        }
    )
    sequence.setRenderer(
        QgsCategorizedSymbolRenderer(
            "role",
            [
                QgsRendererCategory("endpoint", endpoint, "起点/终点"),
                QgsRendererCategory("waypoint", waypoint, "行程节点"),
            ],
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "lpad(to_string(\"seq\"), 2, '0')"
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 20
    settings.displayAll = True
    settings.obstacle = False
    fmt = QgsTextFormat()
    font = QFont("Arial")
    font.setBold(True)
    font.setPointSizeF(6.7)
    fmt.setFont(font)
    fmt.setSize(6.7)
    fmt.setColor(QColor("#FFFDF7"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.10)
    buffer.setColor(QColor("#FFFDF7"))
    fmt.setBuffer(buffer)
    settings.setFormat(fmt)
    sequence.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    sequence.setLabelsEnabled(True)
    project.addMapLayer(sequence)
    return sequence


def export_variant(source: Path, output_dir: Path, name: str) -> Path:
    print(f"READ {source}", flush=True)
    project = QgsProject.instance()
    project.clear()
    if not project.read(str(source)):
        raise RuntimeError(f"Cannot read project: {source}")
    print(f"LOADED {name}", flush=True)

    stations_layer = next(
        (layer for layer in project.mapLayers().values() if layer.name() == "行程车站"),
        None,
    )
    for layer in list(project.mapLayers().values()):
        layer_name = layer.name()
        print(f"STYLE {layer_name}", flush=True)
        if layer_name == "实际铁路行程":
            style_routes(layer)
        elif layer_name == "行程车站":
            enlarge_station_marker(layer)
            enlarge_labels(layer, 1.10, 8.6)
        elif layer_name == "移动后的车站名":
            enlarge_labels(layer, 1.08, 7.7)
        elif layer_name == "城市名称":
            enlarge_labels(layer, 1.08, 11.3)
        elif layer_name == "省级行政区名称":
            enlarge_labels(layer, 1.04)
        elif layer_name == "高亮城市边界":
            style_boundary(layer, "#5E7974", 0.27)
        elif layer_name in {"省级行政区边界", "地级行政区内部边界"}:
            style_boundary(layer, "#A4AEAD", 0.16)

    sequence_layer = add_sequence_layer(project, stations_layer) if stations_layer else None
    if sequence_layer is not None:
        root = project.layerTreeRoot()
        root.findLayer(sequence_layer.id()).setItemVisibilityChecked(True)

    layouts = project.layoutManager().printLayouts()
    if not layouts:
        raise RuntimeError(f"No print layout in project: {source}")
    layout = layouts[0]
    # The existing project keeps the route layer above administrative fills.
    # Put the sequence badges above every other map layer as well.
    if sequence_layer is not None:
        map_items = [item for item in layout.items() if item.__class__.__name__ == "QgsLayoutItemMap"]
        for item in map_items:
            layers = list(item.layers())
            if sequence_layer not in layers:
                layers.insert(0, sequence_layer)
                item.setLayers(layers)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{name}_强调版.png"
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 320
    result = QgsLayoutExporter(layout).exportToImage(str(output), settings)
    print(f"EXPORTED {name} result={result}", flush=True)
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Export failed for {name}: {result}")

    # Keep an editable copy beside the PNG.  Its source layers remain the
    # original, verified project data; the official project is never changed.
    project.setPresetHomePath(str(output_dir))
    project.write(str(output_dir / f"{name}_强调版.qgz"))
    return output


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    try:
        for folder, name in SOURCES:
            source = REGIONAL_ROOT / folder / f"{name}.qgz"
            output = export_variant(source, OUTPUT_ROOT / folder, name)
            print(output, flush=True)
        return 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
