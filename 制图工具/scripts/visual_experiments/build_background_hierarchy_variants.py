"""Build a third prototype with real physical context and explicit label tiers."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsProject,
    QgsRasterLayer,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)


MAP_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_ROOT = MAP_ROOT / "地图输出" / "视觉优化试验" / "第三版_底图分级"
DATA_ROOT = EXPERIMENT_ROOT / "底图数据"
RASTER_PATH = MAP_ROOT / "制图工具" / "数据源" / "NaturalEarth" / "GRAY_LR_SR" / "GRAY_LR_SR.tif"
RIVER_PATH = DATA_ROOT / "ne_10m_rivers_lake_centerlines" / "ne_10m_rivers_lake_centerlines.shp"
LAKE_PATH = DATA_ROOT / "ne_10m_lakes" / "ne_10m_lakes.shp"
NATIONAL_SOURCE = (
    MAP_ROOT / "地图输出" / "视觉优化试验" / "第二版_路线主角" / "全国" / "全国足迹.qgz"
)
REGIONAL_SOURCES = (
    ("东北漫游", "东北漫游"),
    ("小城小记3", "小城小记3"),
)


def label_format(size: float, color: str, bold: bool = False, buffer_size: float = 0.35):
    fmt = QgsTextFormat()
    font = QFont("华文楷体")
    font.setBold(bold)
    font.setPointSizeF(size)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(buffer_size)
    buffer.setColor(QColor("#FFFDF7"))
    fmt.setBuffer(buffer)
    return fmt


def set_label_style(layer, size: float, color: str, bold: bool = False, expression: str | None = None):
    if layer.labeling() is None:
        return
    settings = layer.labeling().settings()
    settings.setFormat(label_format(size, color, bold))
    if expression is not None:
        settings.fieldName = expression
        settings.isExpression = True
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def make_background_layers(project):
    layers = []
    raster = QgsRasterLayer(str(RASTER_PATH), "低对比度地形", "gdal")
    if raster.isValid():
        raster.setOpacity(0.10)
        project.addMapLayer(raster)
        layers.append(raster)

    lakes = QgsVectorLayer(str(LAKE_PATH), "主要湖泊", "ogr")
    if lakes.isValid():
        lakes.setSubsetString("scalerank <= 4")
        lake_symbol = QgsFillSymbol.createSimple(
            {
                "color": "#A8D6E2",
                "outline_color": "#7FAFBA",
                "outline_width": "0.12",
                "outline_width_unit": "MM",
            }
        )
        lake_symbol.setOpacity(0.42)
        lakes.setRenderer(
            QgsSingleSymbolRenderer(lake_symbol)
        )
        project.addMapLayer(lakes)
        layers.append(lakes)

    rivers = QgsVectorLayer(str(RIVER_PATH), "主要河流", "ogr")
    if rivers.isValid():
        rivers.setSubsetString("scalerank <= 4")
        symbol = QgsLineSymbol()
        line = QgsSimpleLineSymbolLayer(QColor("#5DABB9"), 0.24)
        line.setWidthUnit(Qgis.RenderUnit.Millimeters)
        line.setPenCapStyle(Qt.RoundCap)
        symbol.changeSymbolLayer(0, line)
        rivers.setRenderer(QgsSingleSymbolRenderer(symbol))
        project.addMapLayer(rivers)
        layers.append(rivers)
    return layers


def insert_backgrounds(map_item, background_layers):
    layers = list(map_item.layers())
    if not background_layers:
        return
    polygon_index = next(
        (
            index
            for index, layer in enumerate(layers)
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ),
        len(layers),
    )
    layers[polygon_index:polygon_index] = background_layers
    map_item.setLayers(layers)


def style_tiers(project):
    for layer in project.mapLayers().values():
        name = layer.name()
        if name == "重点城市标注":
            set_label_style(layer, 9.4, "#153F54", True, '"display"')
        elif name == "去过的城市标注":
            set_label_style(layer, 6.8, "#486E77", False, '"display"')
        elif name == "记录车站":
            set_label_style(layer, 6.8, "#28383A", False, 'CASE WHEN "trips" >= 2 THEN "name" END')
        elif name == "城市名称":
            set_label_style(layer, 12.1, "#1E3031", True)
        elif name == "省级行政区名称":
            set_label_style(layer, 12.8, "#3B5D5B", True)
        elif name == "县区名称":
            set_label_style(layer, 7.4, "#6C5635")
        elif name == "移动后的车站名":
            set_label_style(layer, 7.9, "#28383A")
        elif name == "行程顺序":
            set_label_style(layer, 6.7, "#FFFDF7", True, 'lpad(to_string("seq"), 2, \'0\')')


def export_project(source: Path, output_dir: Path, name: str, national: bool = False):
    project = QgsProject.instance()
    project.clear()
    if not project.read(str(source)):
        raise RuntimeError(f"Cannot read project: {source}")
    backgrounds = make_background_layers(project)
    style_tiers(project)
    for layout in project.layoutManager().printLayouts():
        for item in layout.items():
            if item.__class__.__name__ == "QgsLayoutItemMap":
                insert_backgrounds(item, backgrounds)
        output = output_dir / ("铁路路线.png" if layout.name() == "铁路路线" else "去过的省市.png" if national else f"{name}_底图分级.png")
        output_dir.mkdir(parents=True, exist_ok=True)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 320
        result = QgsLayoutExporter(layout).exportToImage(str(output), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"Export failed for {name}/{layout.name()}: {result}")
    project.setPresetHomePath(str(output_dir))
    project.write(str(output_dir / ("全国足迹_底图分级.qgz" if national else f"{name}_底图分级.qgz")))


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    try:
        export_project(NATIONAL_SOURCE, EXPERIMENT_ROOT / "全国", "全国", national=True)
        for folder, name in REGIONAL_SOURCES:
            source = EXPERIMENT_ROOT.parent / "第二版_路线主角" / folder / f"{name}_强调版.qgz"
            export_project(source, EXPERIMENT_ROOT / folder, name)
        return 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
