"""Build a Beijing hub-map experiment with a light passenger-rail background."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPolygonF
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPolyline,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsPrintLayout,
    QgsProject,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
)


ROOT = Path(r"F:\Desktop\Railway")
OUTPUT_DIR = ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
SOURCE_PROJECT = OUTPUT_DIR / "铁路枢纽局部图.qgz"
OSM_GPKG = ROOT / "制图工具" / "数据源" / "GeoPackage" / "travel_map_home2_min_gan.gpkg"
OUTPUT_GPKG = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.gpkg"
OUTPUT_PROJECT = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.qgz"
OUTPUT_IMAGE = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.png"
SOURCE_LAYOUT = "北京及周边铁路行迹"
OUTPUT_LAYOUT = "北京及周边铁路行迹_客运铁路底图"
EXTENT = QgsRectangle(115.20, 39.28, 117.75, 41.22)

# Conventional corridors and connecting lines with current passenger use.
VERIFIED_PASSENGER_NAMES = {
    "京沪线",
    "京哈线",
    "京广线",
    "京九线",
    "京包线",
    "京承线",
    "京通线",
    "京原线",
    "丰沙线",
    "西长线",
    "京包客专线",
    "京哈高速线",
    "京津城际线",
    "京唐城际线",
    "京沪高铁",
    "京广高速线",
    "京雄城际线",
    "崇礼线",
    "津兴城际线",
    "怀兴城际线",
    "津蓟线",
    "怀联线",
    "延庆线",
    "康延线",
    "康延联络线",
    "北京直通线",
    "北京联络线",
    "京沪京哈联络线",
    "京沪京广联络线",
    "京沪京广下行联络线",
    "京广高速京西联络线",
    "京包客专京通联络线",
    "京包京通联络线",
    "丰双丰沙联络线",
}
KNOWN_FREIGHT_NAMES = {
    "大秦线",
    "大秦铁路",
    "唐包线",
    "大台线",
    "西北环线",
    "良陈线",
    "虎丰线",
    "一零一线",
    "东星线",
    "塔锡线",
    "大李线",
    "房山线",
    "宣庞线",
    "沙蔚铁路",
    "沙蔚线",
    "永丰线",
    "东北环线",
    "东北环疏解线",
    "廊涿城际线",
}
EXCLUDED_SERVICES = {"siding", "spur", "yard", "crossover"}


def parse_tags(value: object) -> dict[str, str]:
    return dict(re.findall(r'"([^"\\]+)"=>"([^"\\]*)"', str(value or "")))


def is_excluded(name: str, tags: dict[str, str]) -> bool:
    return (
        tags.get("service") in EXCLUDED_SERVICES
        or tags.get("usage") in {"industrial", "military"}
        or tags.get("railway:traffic_mode") == "freight"
        or name in KNOWN_FREIGHT_NAMES
        or any(key in tags for key in ("disused", "abandoned", "proposed", "construction"))
    )


def explicit_passenger(tags: dict[str, str]) -> bool:
    if tags.get("railway:traffic_mode") == "passenger":
        return True
    try:
        return int(tags.get("passenger_lines", "0")) > 0
    except ValueError:
        return False


def rail_class(name: str, tags: dict[str, str]) -> str:
    if tags.get("highspeed") == "yes" or any(
        token in name for token in ("高速", "高铁", "客专", "城际")
    ):
        return "highspeed"
    return "conventional"


def is_unnamed_or_structure(name: str) -> bool:
    return not name or name.endswith(("桥", "大桥", "隧道"))


def source_features(source: QgsVectorLayer) -> list[tuple[QgsFeature, str, dict[str, str]]]:
    request = QgsFeatureRequest().setFilterRect(EXTENT).setFilterExpression('"railway" = \'rail\'')
    result = []
    for feature in source.getFeatures(request):
        name = str(feature["name"] or "")
        tags = parse_tags(feature["other_tags"])
        if not is_excluded(name, tags):
            result.append((feature, name, tags))
    return result


def build_passenger_layer(project: QgsProject) -> QgsVectorLayer:
    source = QgsVectorLayer(
        f"{OSM_GPKG}|layername=china_railwayosm__lines", "OSM铁路源数据", "ogr"
    )
    if not source.isValid():
        raise RuntimeError(f"无法打开铁路源数据：{OSM_GPKG}")
    candidates = source_features(source)
    accepted_refs = {
        tags["ref"]
        for _, name, tags in candidates
        if tags.get("ref")
        and (
            name in VERIFIED_PASSENGER_NAMES
            or (is_unnamed_or_structure(name) and explicit_passenger(tags))
        )
    }

    memory = QgsVectorLayer("LineString?crs=EPSG:4326", "其他客运铁路", "memory")
    memory.dataProvider().addAttributes(
        [
            QgsField("name", QVariant.String),
            QgsField("ref", QVariant.String),
            QgsField("rail_class", QVariant.String),
            QgsField("basis", QVariant.String),
        ]
    )
    memory.updateFields()
    output = []
    for source_feature, name, tags in candidates:
        named = name in VERIFIED_PASSENGER_NAMES
        tagged = is_unnamed_or_structure(name) and explicit_passenger(tags)
        linked = bool(
            is_unnamed_or_structure(name)
            and tags.get("ref")
            and tags["ref"] in accepted_refs
        )
        if not (named or tagged or linked):
            continue
        feature = QgsFeature(memory.fields())
        feature.setGeometry(source_feature.geometry())
        feature.setAttributes(
            [
                name,
                tags.get("ref", ""),
                rail_class(name, tags),
                "verified_name" if named else "osm_passenger" if tagged else "shared_ref",
            ]
        )
        output.append(feature)
    memory.dataProvider().addFeatures(output)
    memory.updateExtents()

    OUTPUT_GPKG.unlink(missing_ok=True)
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "其他客运铁路"
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"无法写出客运铁路图层：{message}")
    layer = QgsVectorLayer(f"{OUTPUT_GPKG}|layername=其他客运铁路", "其他客运铁路", "ogr")
    if not layer.isValid():
        raise RuntimeError("写出的客运铁路图层无效")
    project.addMapLayer(layer)
    return layer


def background_symbol(color: str = "#BEC8C4", width: float = 0.30) -> QgsLineSymbol:
    symbol = QgsLineSymbol()
    line = QgsSimpleLineSymbolLayer(QColor(color), width)
    line.setWidthUnit(Qgis.RenderUnit.Millimeters)
    line.setPenJoinStyle(Qt.RoundJoin)
    line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, line)
    return symbol


def style_passenger_layer(layer: QgsVectorLayer) -> None:
    conventional = background_symbol("#C3CBC8", 0.28)
    highspeed = background_symbol("#B5C8C8", 0.32)
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "rail_class",
            [
                QgsRendererCategory("conventional", conventional, "其他普速客运铁路"),
                QgsRendererCategory("highspeed", highspeed, "其他高速客运铁路"),
            ],
        )
    )


def text_format(size: float, color: str) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont("思源黑体 CN")
    font.setPointSizeF(size)
    font.setWeight(QFont.Medium)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    return fmt


def add_background_legend(layout: QgsPrintLayout) -> None:
    line = QgsLayoutItemPolyline(
        QPolygonF([QPointF(103.0, 233.2), QPointF(117.0, 233.2)]), layout
    )
    line.setSymbol(background_symbol())
    layout.addLayoutItem(line)
    label = QgsLayoutItemLabel(layout)
    label.setText("其他客运铁路")
    label.setTextFormat(text_format(8.0, "#68736F"))
    label.setHAlign(Qt.AlignLeft)
    label.setVAlign(Qt.AlignVCenter)
    label.attemptMove(QgsLayoutPoint(118.0, 229.2, QgsUnitTypes.LayoutMillimeters))
    label.attemptResize(QgsLayoutSize(42.0, 8.0, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(label)


def main() -> int:
    for required in (SOURCE_PROJECT, OSM_GPKG):
        if not required.exists():
            raise FileNotFoundError(required)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(SOURCE_PROJECT)):
            raise RuntimeError(f"无法打开源工程：{SOURCE_PROJECT}")
        layouts = {layout.name(): layout for layout in project.layoutManager().printLayouts()}
        layout = layouts.get(SOURCE_LAYOUT)
        if layout is None:
            raise RuntimeError(f"源工程缺少布局：{SOURCE_LAYOUT}")
        for name, other in layouts.items():
            if name != SOURCE_LAYOUT:
                project.layoutManager().removeLayout(other)
        layout.setName(OUTPUT_LAYOUT)
        map_items = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
        if len(map_items) != 1:
            raise RuntimeError(f"北京布局地图框数量异常：{len(map_items)}")
        map_item = map_items[0]

        passenger = build_passenger_layer(project)
        style_passenger_layer(passenger)
        map_layers = map_item.layers()
        route_index = next(
            (index for index, layer in enumerate(map_layers) if layer.name() == "铁路行程轨迹"),
            None,
        )
        if route_index is None:
            raise RuntimeError("北京布局缺少铁路行程轨迹图层")
        map_layers.insert(route_index + 1, passenger)
        map_item.setLayers(map_layers)
        map_item.setKeepLayerSet(True)
        add_background_legend(layout)

        used_ids = {layer.id() for layer in map_layers}
        for layer_id in list(project.mapLayers()):
            if layer_id not in used_ids:
                project.removeMapLayer(layer_id)
        project.setTitle("北京及周边铁路行迹：客运铁路底图试验")
        project.setPresetHomePath(str(OUTPUT_DIR))
        project.setFilePathStorage(Qgis.FilePathType.Relative)
        OUTPUT_PROJECT.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_PROJECT)):
            raise RuntimeError(f"无法写出工程：{OUTPUT_PROJECT}")

        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 300
        OUTPUT_IMAGE.unlink(missing_ok=True)
        result = QgsLayoutExporter(layout).exportToImage(str(OUTPUT_IMAGE), settings)
        if result != QgsLayoutExporter.Success:
            raise RuntimeError(f"无法导出图片：{result}")
        image = QImage(str(OUTPUT_IMAGE))
        counts = {"conventional": 0, "highspeed": 0}
        basis = {"verified_name": 0, "osm_passenger": 0, "shared_ref": 0}
        for feature in passenger.getFeatures():
            counts[str(feature["rail_class"])] += 1
            basis[str(feature["basis"])] += 1
        print(
            {
                "features": passenger.featureCount(),
                "classes": counts,
                "basis": basis,
                "image": [image.width(), image.height(), OUTPUT_IMAGE.stat().st_size],
                "project": str(OUTPUT_PROJECT),
            }
        )
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
