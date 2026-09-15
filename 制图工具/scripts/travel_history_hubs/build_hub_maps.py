"""Build detailed Beijing, Hefei, and Guangzhou railway-history maps."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from qgis.PyQt.QtCore import QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QImage, QPolygonF
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCategorizedSymbolRenderer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFillSymbol,
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
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
    QgsRectangle,
    QgsReferencedRectangle,
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
SOURCE_GPKG = (
    RAILWAY_ROOT
    / "地图输出"
    / "全国专题图"
    / "全国足迹"
    / "全国足迹_数据.gpkg"
)
OUTPUT_DIR = (
    RAILWAY_ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
)
OUTPUT_PROJECT = OUTPUT_DIR / "铁路枢纽局部图.qgz"
OUTPUT_GPKG = OUTPUT_DIR / "铁路枢纽局部图.gpkg"
REPORT_PATH = OUTPUT_DIR / "构建报告.json"
LEGACY_COMBINED_IMAGE = OUTPUT_DIR / "北京合肥广州_三联图.png"

PAGE_HEIGHT = 240.0
MAP_TOP = 24.0
MAP_HEIGHT = 188.0
PROJECT_CRS = QgsCoordinateReferenceSystem("EPSG:3857")
STATION_LABEL_SIZE_PT = 10.0
STATION_LABEL_EM_MM = STATION_LABEL_SIZE_PT * 25.4 / 72.0


@dataclass(frozen=True)
class HubSpec:
    key: str
    title: str
    extent: tuple[float, float, float, float]
    focus_layer: str
    focus_name: str
    stations: tuple[str, ...]
    page_width: float
    scale_segment_km: int

    @property
    def map_frame(self) -> tuple[float, float, float, float]:
        return (10.0, MAP_TOP, self.page_width - 20.0, MAP_HEIGHT)

    @property
    def output(self) -> Path:
        return OUTPUT_DIR / f"{self.title}.png"


SPECS = (
    HubSpec(
        key="beijing",
        title="北京及周边铁路行迹",
        extent=(115.20, 39.28, 117.75, 41.22),
        focus_layer="铁路图省级行政区",
        focus_name="北京市",
        stations=("北京", "北京丰台", "北京北", "北京南", "北京西", "清河", "大兴机场", "古北口"),
        page_width=250.0,
        scale_segment_km=50,
    ),
    HubSpec(
        key="hefei",
        title="合肥及周边铁路行迹",
        extent=(116.45, 30.78, 118.22, 32.70),
        focus_layer="全国地级行政区",
        focus_name="合肥市",
        stations=("合肥", "合肥南", "合肥北城", "合肥西"),
        page_width=205.0,
        scale_segment_km=20,
    ),
    HubSpec(
        key="guangzhou",
        title="广州及周边铁路行迹",
        extent=(112.70, 22.05, 114.32, 24.10),
        focus_layer="全国地级行政区",
        focus_name="广州市",
        stations=("广州", "广州东", "广州南", "广州白云", "佛山西"),
        page_width=240.0,
        scale_segment_km=20,
    ),
)


def text_format(
    size: float,
    color: str,
    family: str,
    *,
    buffer_size: float = 0.0,
    weight: int = QFont.Normal,
) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont(family)
    font.setPointSizeF(size)
    font.setWeight(weight)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer_size:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setColor(QColor(255, 255, 255, 235))
        buffer.setSize(buffer_size)
        buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(buffer)
    return fmt


def load_layer(project: QgsProject, layer_name: str, display_name: str) -> QgsVectorLayer:
    layer = QgsVectorLayer(
        f"{SOURCE_GPKG}|layername={layer_name}", display_name, "ogr"
    )
    if not layer.isValid():
        raise RuntimeError(f"Unable to open source layer: {layer_name}")
    project.addMapLayer(layer)
    return layer


def filtered_copy(
    project: QgsProject,
    source: QgsVectorLayer,
    display_name: str,
    expression: str,
) -> QgsVectorLayer:
    layer = source.materialize(QgsFeatureRequest().setFilterExpression(expression))
    layer.setName(display_name)
    if not layer.isValid():
        raise RuntimeError(f"Unable to create filtered layer: {display_name}")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = display_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if not OUTPUT_GPKG.exists()
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {display_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={display_name}", display_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen filtered layer: {display_name}")
    project.addMapLayer(saved)
    return saved


def shared_internal_boundaries(
    project: QgsProject,
    source: QgsVectorLayer,
    display_name: str,
    features: list[QgsFeature],
    expected_count: int | None = None,
) -> QgsVectorLayer:
    if expected_count is not None and len(features) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} features for {display_name}, got {len(features)}"
        )

    shared_lines = []
    for index, first in enumerate(features):
        first_boundary = first.geometry().convertToType(
            QgsWkbTypes.LineGeometry, True
        )
        for second in features[index + 1 :]:
            if not first.geometry().boundingBox().intersects(second.geometry().boundingBox()):
                continue
            second_boundary = second.geometry().convertToType(
                QgsWkbTypes.LineGeometry, True
            )
            shared = first_boundary.intersection(second_boundary)
            if (
                not shared.isNull()
                and not shared.isEmpty()
                and QgsWkbTypes.geometryType(shared.wkbType())
                == QgsWkbTypes.LineGeometry
                and shared.length() > 1e-9
            ):
                shared_lines.append(shared)
    if not shared_lines:
        raise RuntimeError(f"No shared boundaries found for {display_name}")
    geometry = QgsGeometry.unaryUnion(shared_lines)
    geometry.convertToMultiType()

    layer = QgsVectorLayer(
        f"MultiLineString?crs={source.crs().authid()}", display_name, "memory"
    )
    provider = layer.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    layer.updateFields()
    feature = QgsFeature(layer.fields())
    feature.setAttribute("name", display_name)
    feature.setGeometry(geometry)
    if not provider.addFeature(feature):
        raise RuntimeError(f"Unable to create {display_name}")

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = display_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile
        if not OUTPUT_GPKG.exists()
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {display_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={display_name}", display_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen boundary layer: {display_name}")
    project.addMapLayer(saved)
    return saved


def geometry_line_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    display_name: str,
    geometry: QgsGeometry,
) -> QgsVectorLayer:
    geometry.convertToMultiType()
    layer = QgsVectorLayer(
        f"MultiLineString?crs={source.crs().authid()}", display_name, "memory"
    )
    provider = layer.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    layer.updateFields()
    feature = QgsFeature(layer.fields())
    feature.setAttribute("name", display_name)
    feature.setGeometry(geometry)
    if not provider.addFeature(feature):
        raise RuntimeError(f"Unable to create {display_name}")

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = display_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {display_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={display_name}", display_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen line layer: {display_name}")
    project.addMapLayer(saved)
    return saved


def dissolved_polygon_layer(
    project: QgsProject,
    source: QgsVectorLayer,
    display_name: str,
    features: list[QgsFeature],
    expected_count: int,
    simplify_tolerance: float = 0.0,
    feature_name: str | None = None,
) -> QgsVectorLayer:
    if len(features) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} features for {display_name}, got {len(features)}"
        )
    geometry = QgsGeometry.unaryUnion([feature.geometry() for feature in features])
    if geometry.isNull() or geometry.isEmpty():
        raise RuntimeError(f"Unable to dissolve {display_name}")
    if simplify_tolerance:
        geometry = geometry.simplify(simplify_tolerance)
    geometry.convertToMultiType()
    layer = QgsVectorLayer(
        f"MultiPolygon?crs={source.crs().authid()}", display_name, "memory"
    )
    provider = layer.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    layer.updateFields()
    feature = QgsFeature(layer.fields())
    feature.setAttribute("name", feature_name or display_name)
    feature.setGeometry(geometry)
    if not provider.addFeature(feature):
        raise RuntimeError(f"Unable to create {display_name}")

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = display_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {display_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={display_name}", display_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen polygon layer: {display_name}")
    project.addMapLayer(saved)
    return saved


def guangdong_outline_without_sar_duplicates(
    project: QgsProject,
    provinces: QgsVectorLayer,
    display_name: str,
    hong_kong_geometry: QgsGeometry,
    macao_geometry: QgsGeometry,
) -> QgsVectorLayer:
    by_name = {
        str(feature["name"]): feature.geometry()
        for feature in provinces.getFeatures()
        if str(feature["name"])
        in {"广东省", "香港特别行政区", "澳门特别行政区"}
    }
    if set(by_name) != {"广东省", "香港特别行政区", "澳门特别行政区"}:
        raise RuntimeError("Unable to load Guangdong/Hong Kong/Macao boundaries")
    guangdong_line = by_name["广东省"].convertToType(
        QgsWkbTypes.LineGeometry, True
    )
    sar_buffer = QgsGeometry.unaryUnion(
        [hong_kong_geometry, macao_geometry]
    ).buffer(0.02, 12)
    clean_line = guangdong_line.difference(sar_buffer)
    if clean_line.isNull() or clean_line.isEmpty():
        raise RuntimeError("Unable to create the cleaned Guangdong outline")
    return geometry_line_layer(project, provinces, display_name, clean_line)


def municipality_internal_boundaries(
    project: QgsProject,
    cities: QgsVectorLayer,
    display_name: str,
    parent_adcode: str,
) -> QgsVectorLayer:
    districts = [
        feature
        for feature in cities.getFeatures()
        if str(feature["level"]) == "district"
        and parent_adcode in str(feature["parent"])
    ]
    return shared_internal_boundaries(
        project, cities, display_name, districts, expected_count=16
    )


def style_provinces(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#F7F8F6",
            "outline_color": "#78847F",
            "outline_width": "0.42",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_province_fill_only(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#F7F8F6",
            "outline_color": "255,255,255,0",
            "outline_width": "0",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


def style_province_outline(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": "#78847F",
            "line_width": "0.42",
            "line_width_unit": "MM",
            "joinstyle": "round",
            "capstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


def style_sar_outline(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#F7F8F6",
            "outline_color": "#78847F",
            "outline_width": "0.34",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


def style_sar_label(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsFillSymbol.createSimple(
                {
                    "color": "255,255,255,0",
                    "outline_color": "255,255,255,0",
                    "outline_width": "0",
                }
            )
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = 'regexp_replace("name", \'特别行政区$\', \'\')'
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 8
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(
        text_format(
            9.3,
            "#697570",
            "思源黑体 CN",
            buffer_size=0.34,
            weight=QFont.Medium,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_tianjin_label(layer: QgsVectorLayer) -> None:
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "'天津'"
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 3
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(
        text_format(
            9.3,
            "#697570",
            "思源黑体 CN",
            buffer_size=0.34,
            weight=QFont.Medium,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_internal_boundaries(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": "#BAC4C0",
            "line_width": "0.16",
            "line_width_unit": "MM",
            "joinstyle": "round",
            "capstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


def style_cities(
    layer: QgsVectorLayer,
    hidden_name: str | None = None,
    *,
    draw_boundaries: bool = True,
) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "255,255,255,0",
            "outline_color": "#BAC4C0" if draw_boundaries else "255,255,255,0",
            "outline_width": "0.16" if draw_boundaries else "0",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    hidden_clause = (
        f" OR \"name\" = '{hidden_name.replace(chr(39), chr(39) * 2)}'"
        if hidden_name
        else ""
    )
    settings.fieldName = (
        f"CASE WHEN right(\"name\", 1) IN ('区', '县'){hidden_clause} THEN NULL "
        "ELSE regexp_replace(\"name\", '市$', '') END"
    )
    settings.isExpression = True
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 2
    settings.obstacle = False
    settings.setFormat(
        text_format(
            9.3,
            "#697570",
            "思源黑体 CN",
            buffer_size=0.34,
            weight=QFont.Medium,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def style_focus_city(layer: QgsVectorLayer) -> None:
    symbol = QgsFillSymbol.createSimple(
        {
            "color": "#B7CDBD",
            "outline_color": "#587066",
            "outline_width": "0.48",
            "outline_width_unit": "MM",
            "joinstyle": "round",
        }
    )
    symbol.setOpacity(0.62)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


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
        line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def style_routes(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "service",
            [
                QgsRendererCategory("highspeed", route_symbol(True), "高铁/动车"),
                QgsRendererCategory("conventional", route_symbol(False), "普铁"),
            ],
        )
    )


STATION_LABEL_OFFSETS_MM = {
    "beijing": {
        "北京南": (4.0, -2.7),
        "北京西": (0.0, 2.0),
        "北京丰台": (-6.0, -2.9),
    },
    "hefei": {
        "合肥南": (0.0, 2.0 - 1.5 * STATION_LABEL_EM_MM),
        # Preserve the automatic label's horizontal side while applying the
        # requested vertical movement in units of one 10 pt character size.
        "六安": (5.3, 1.8 - STATION_LABEL_EM_MM),
        "全椒": (5.7, 2.2 + 0.25 * STATION_LABEL_EM_MM),
    },
    "guangzhou": {
        "佛山西": (0.0, 4.0),
        "广州": (-1.3 + STATION_LABEL_EM_MM, -5.0),
        "深圳": (-8.0, 0.0),
    },
}


def style_station_markers(layer: QgsVectorLayer) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle",
            "color": "#B95D6D",
            "outline_color": "#FFFDF8",
            "outline_width": "0.34",
            "outline_width_unit": "MM",
            "size": "1.75",
            "size_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)


def style_station_labels(layer: QgsVectorLayer, *, fixed: bool) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {"name": "circle", "size": "0", "outline_width": "0"}
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = (
        "CASE WHEN right(\"name\", 1) = '站' THEN \"name\" "
        "ELSE \"name\" || '站' END"
    )
    settings.isExpression = True
    settings.placement = (
        Qgis.LabelPlacement.OverPoint
        if fixed
        else QgsPalLayerSettings.OrderedPositionsAroundPoint
    )
    settings.priority = 10
    settings.dist = 0.60
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = True
    settings.obstacle = False
    if hasattr(settings, "allowDegradedPlacement"):
        settings.allowDegradedPlacement = True
    settings.setFormat(
        text_format(
            STATION_LABEL_SIZE_PT,
            "#202020",
            "思源黑体 CN",
            buffer_size=0.55,
            weight=QFont.DemiBold,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def shifted_station_label_copy(
    project: QgsProject,
    source: QgsVectorLayer,
    display_name: str,
    offsets_mm: dict[str, tuple[float, float]],
    map_item: QgsLayoutItemMap,
    map_width_mm: float,
    map_height_mm: float,
) -> QgsVectorLayer:
    quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in offsets_mm)
    layer = source.materialize(
        QgsFeatureRequest().setFilterExpression(f'"name" IN ({quoted})')
    )
    to_map = QgsCoordinateTransform(
        source.crs(), project.crs(), project.transformContext()
    )
    from_map = QgsCoordinateTransform(
        project.crs(), source.crs(), project.transformContext()
    )
    x_units_per_mm = map_item.extent().width() / map_width_mm
    y_units_per_mm = map_item.extent().height() / map_height_mm
    layer.startEditing()
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        geometry.transform(to_map)
        dx_mm, dy_mm = offsets_mm[str(feature["name"])]
        geometry.translate(dx_mm * x_units_per_mm, dy_mm * y_units_per_mm)
        geometry.transform(from_map)
        layer.changeGeometry(feature.id(), geometry)
    if not layer.commitChanges():
        raise RuntimeError(f"Unable to position station labels: {display_name}")
    layer.setName(display_name)

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = display_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    error, message, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(OUTPUT_GPKG), project.transformContext(), options
    )
    if error != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to save {display_name}: {message}")
    saved = QgsVectorLayer(
        f"{OUTPUT_GPKG}|layername={display_name}", display_name, "ogr"
    )
    if not saved.isValid():
        raise RuntimeError(f"Unable to reopen positioned labels: {display_name}")
    project.addMapLayer(saved)
    return saved


def add_label(
    layout: QgsPrintLayout,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    size: float,
    family: str,
    *,
    color: str = "#202020",
    weight: int = QFont.Normal,
    buffer_size: float = 0.0,
) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(
        text_format(
            size,
            color,
            family,
            buffer_size=buffer_size,
            weight=weight,
        )
    )
    item.setHAlign(Qt.AlignCenter)
    item.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(
        QgsLayoutSize(width, height, QgsUnitTypes.LayoutMillimeters)
    )
    return item


def projected_extent(
    project: QgsProject, extent: tuple[float, float, float, float]
) -> QgsRectangle:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    return transform.transformBoundingBox(QgsRectangle(*extent))


def add_scale_bar(
    layout: QgsPrintLayout,
    map_item: QgsLayoutItemMap,
    segment_km: int,
    page_width: float,
) -> None:
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitsPerSegment(segment_km)
    scale.setUnitLabel("km")
    scale.setHeight(1.0)
    scale.setLabelBarSpace(0.55)
    scale.setBoxContentSpace(0.5)
    scale.setTextFormat(
        text_format(8.2, "#485551", "思源黑体 CN", weight=QFont.Medium)
    )
    scale.setLineColor(QColor("#56635E"))
    scale.setLineWidth(0.24)
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(13, 218, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(72, 10, QgsUnitTypes.LayoutMillimeters))


def add_legend(layout: QgsPrintLayout, spec: HubSpec) -> None:
    if spec.key == "beijing":
        highspeed_label = "高铁/动车（含城际、市郊）"
        # Keep a clear horizontal break after the scale bar on the wider Beijing page.
        highspeed_x = 103.0
        highspeed_width = 68.0
        conventional_x = 202.0
    else:
        highspeed_label = "高铁/动车（含城际）"
        highspeed_x = 68.0 if spec.key == "hefei" else 72.0
        highspeed_width = 57.0
        conventional_x = 147.0 if spec.key == "hefei" else 155.0
    for x, highspeed, label, label_width in (
        (highspeed_x, True, highspeed_label, highspeed_width),
        (conventional_x, False, "普铁", 22.0),
    ):
        line = QgsLayoutItemPolyline(
            QPolygonF([QPointF(x, 222.5), QPointF(x + 14.0, 222.5)]), layout
        )
        line.setSymbol(route_symbol(highspeed))
        layout.addLayoutItem(line)
        legend_label = add_label(
            layout,
            label,
            x + 15.0,
            218.5,
            label_width,
            8.0,
            8.0,
            "思源黑体 CN",
            color="#485551",
            weight=QFont.Medium,
        )
        legend_label.setHAlign(Qt.AlignLeft)


def station_coordinates(layer: QgsVectorLayer) -> dict[str, tuple[float, float]]:
    result = {}
    for feature in layer.getFeatures():
        point = feature.geometry().asPoint()
        result[feature["name"]] = (point.x(), point.y())
    return result


def create_layout(
    project: QgsProject,
    spec: HubSpec,
    provinces: QgsVectorLayer,
    context_cities: QgsVectorLayer,
    focus_city: QgsVectorLayer,
    routes: QgsVectorLayer,
    station_source: QgsVectorLayer,
    boundary_overlays: tuple[QgsVectorLayer, ...] = (),
    base_overlays: tuple[QgsVectorLayer, ...] = (),
) -> dict:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(spec.title)
    layout.pageCollection().page(0).setPageSize(
        QgsLayoutSize(spec.page_width, PAGE_HEIGHT, QgsUnitTypes.LayoutMillimeters)
    )
    project.layoutManager().addLayout(layout)

    add_label(
        layout,
        spec.title,
        10,
        3,
        spec.page_width - 20.0,
        16,
        23.0,
        "华文新魏",
        color="#111111",
    ).setHAlign(Qt.AlignLeft)
    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#77807B"))
    map_item.setFrameStrokeWidth(
        QgsLayoutMeasurement(0.22, QgsUnitTypes.LayoutMillimeters)
    )
    layout.addLayoutItem(map_item)
    map_item.attemptMove(
        QgsLayoutPoint(
            spec.map_frame[0], spec.map_frame[1], QgsUnitTypes.LayoutMillimeters
        )
    )
    map_item.attemptResize(
        QgsLayoutSize(
            spec.map_frame[2], spec.map_frame[3], QgsUnitTypes.LayoutMillimeters
        )
    )
    map_item.zoomToExtent(projected_extent(project, spec.extent))
    to_station_crs = QgsCoordinateTransform(
        project.crs(), station_source.crs(), project.transformContext()
    )
    visible_station_extent = to_station_crs.transformBoundingBox(map_item.extent())
    stations = filtered_copy(
        project,
        station_source,
        f"{spec.title}车站",
        (
            f"x($geometry) >= {visible_station_extent.xMinimum()} "
            f"AND x($geometry) <= {visible_station_extent.xMaximum()} "
            f"AND y($geometry) >= {visible_station_extent.yMinimum()} "
            f"AND y($geometry) <= {visible_station_extent.yMaximum()}"
        ),
    )
    style_station_markers(stations)
    offsets = STATION_LABEL_OFFSETS_MM[spec.key]
    quoted = ", ".join("'" + name.replace("'", "''") + "'" for name in offsets)
    automatic_labels = filtered_copy(
        project,
        stations,
        f"{spec.title}自动车站标注",
        f'"name" NOT IN ({quoted})',
    )
    style_station_labels(automatic_labels, fixed=False)
    fixed_labels = shifted_station_label_copy(
        project,
        stations,
        f"{spec.title}固定车站标注",
        offsets,
        map_item,
        spec.map_frame[2],
        spec.map_frame[3],
    )
    style_station_labels(fixed_labels, fixed=True)
    map_item.setLayers(
        [
            fixed_labels,
            automatic_labels,
            stations,
            routes,
            *boundary_overlays,
            focus_city,
            context_cities,
            provinces,
            *base_overlays,
        ]
    )
    map_item.setKeepLayerSet(True)

    coords = station_coordinates(stations)
    missing = sorted(set(spec.stations) - set(coords))
    if missing:
        raise RuntimeError(f"{spec.title} is missing stations: {', '.join(missing)}")
    add_scale_bar(layout, map_item, spec.scale_segment_km, spec.page_width)
    add_legend(layout, spec)
    add_label(
        layout,
        "数据截至 2026.08",
        spec.page_width - 65.0,
        7.0,
        54,
        8,
        8.0,
        "思源黑体 CN",
        color="#485551",
        weight=QFont.Medium,
    )

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 300
    spec.output.unlink(missing_ok=True)
    result = exporter.exportToImage(str(spec.output), settings)
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Unable to export {spec.title}: {result}")
    image = QImage(str(spec.output))
    return {
        "key": spec.key,
        "title": spec.title,
        "image": str(spec.output),
        "image_size": [image.width(), image.height()],
        "station_count": len(coords),
        "stations": sorted(coords),
        "extent": list(spec.extent),
        "visible_station_extent": [
            visible_station_extent.xMinimum(),
            visible_station_extent.yMinimum(),
            visible_station_extent.xMaximum(),
            visible_station_extent.yMaximum(),
        ],
    }


def main() -> int:
    if not SOURCE_GPKG.exists():
        raise FileNotFoundError(SOURCE_GPKG)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_COMBINED_IMAGE.unlink(missing_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        project.setCrs(PROJECT_CRS)
        project.setTitle("北京、合肥、广州铁路局部图")
        project.setPresetHomePath(str(OUTPUT_DIR))

        provinces = load_layer(project, "铁路图省级行政区", "省级行政区")
        cities = load_layer(project, "全国地级行政区", "地级行政区")
        routes = load_layer(project, "铁路行程轨迹", "铁路行程轨迹")
        station_source = load_layer(project, "记录车站", "记录车站源数据")
        style_provinces(provinces)
        provinces.setLabelsEnabled(False)
        cities.setLabelsEnabled(False)
        style_routes(routes)

        reports = []
        for spec in SPECS:
            context_features: list[QgsFeature] | None = None
            base_overlays: tuple[QgsVectorLayer, ...] = ()
            if spec.key == "beijing":
                focus_city = filtered_copy(
                    project,
                    provinces,
                    f"{spec.title}高亮城市",
                    '"name" = \'北京市\'',
                )
                tianjin_boundary = filtered_copy(
                    project,
                    provinces,
                    f"{spec.title}天津市共边轮廓",
                    '"name" = \'天津市\'',
                )
                style_provinces(tianjin_boundary)
                style_tianjin_label(tianjin_boundary)
                beijing_district_lines = municipality_internal_boundaries(
                    project,
                    cities,
                    f"{spec.title}北京市内部区界",
                    "110000",
                )
                tianjin_district_lines = municipality_internal_boundaries(
                    project,
                    cities,
                    f"{spec.title}天津市内部区界",
                    "120000",
                )
                context_features = [
                    feature
                    for feature in cities.getFeatures()
                    if "110000" not in str(feature["parent"])
                    and "120000" not in str(feature["parent"])
                ]
                context_internal_lines = shared_internal_boundaries(
                    project,
                    cities,
                    f"{spec.title}周边城市内部边界",
                    context_features,
                )
                style_internal_boundaries(beijing_district_lines)
                style_internal_boundaries(tianjin_district_lines)
                style_internal_boundaries(context_internal_lines)
                boundary_overlays = (
                    beijing_district_lines,
                    tianjin_district_lines,
                    context_internal_lines,
                    tianjin_boundary,
                )
                context_provinces = provinces.clone()
                context_provinces.setName(f"{spec.title}周边省份")
                context_provinces.setSubsetString(
                    '"name" NOT IN (\'北京市\', \'天津市\')'
                )
                project.addMapLayer(context_provinces)
            else:
                focus_source = (
                    provinces if spec.focus_layer == "铁路图省级行政区" else cities
                )
                focus_city = filtered_copy(
                    project,
                    focus_source,
                    f"{spec.title}高亮城市",
                    f'"name" = \'{spec.focus_name.replace(chr(39), chr(39) * 2)}\'',
                )
                context_provinces = provinces
                boundary_overlays = ()
            style_focus_city(focus_city)
            if spec.key == "beijing":
                context_ids = [
                    str(feature.id()) for feature in context_features
                ]
                context_cities = filtered_copy(
                    project,
                    cities,
                    f"{spec.title}周边城市",
                    f"$id IN ({', '.join(context_ids)})",
                )
            elif spec.key == "guangzhou":
                context_features = list(cities.getFeatures())
                context_internal_lines = shared_internal_boundaries(
                    project,
                    cities,
                    f"{spec.title}周边城市内部边界",
                    context_features,
                )
                style_internal_boundaries(context_internal_lines)
                sar_labels = filtered_copy(
                    project,
                    provinces,
                    f"{spec.title}港澳名称",
                    '"name" IN (\'香港特别行政区\', \'澳门特别行政区\')',
                )
                style_sar_label(sar_labels)
                boundary_overlays = (context_internal_lines, sar_labels)
                base_overlays = ()
                context_provinces = provinces
                context_cities = cities.clone()
                context_cities.setName(f"{spec.title}周边城市")
                project.addMapLayer(context_cities)
            elif spec.key == "hefei":
                visible_city_extent = QgsRectangle(*spec.extent)
                context_features = [
                    feature
                    for feature in cities.getFeatures(
                        QgsFeatureRequest().setFilterRect(visible_city_extent)
                    )
                    if str(feature["level"]) == "city"
                ]
                context_internal_lines = shared_internal_boundaries(
                    project,
                    cities,
                    f"{spec.title}周边城市内部边界",
                    context_features,
                )
                style_internal_boundaries(context_internal_lines)
                boundary_overlays = (context_internal_lines,)
                context_cities = cities.clone()
                context_cities.setName(f"{spec.title}周边城市")
                project.addMapLayer(context_cities)
            else:
                context_cities = cities.clone()
                context_cities.setName(f"{spec.title}周边城市")
                project.addMapLayer(context_cities)
            style_cities(
                context_cities,
                spec.focus_name,
                draw_boundaries=spec.key not in {"beijing", "hefei", "guangzhou"},
            )
            reports.append(
                create_layout(
                    project,
                    spec,
                    context_provinces,
                    context_cities,
                    focus_city,
                    routes,
                    station_source,
                    boundary_overlays,
                    base_overlays,
                )
            )

        first_extent = QgsReferencedRectangle(
            projected_extent(project, SPECS[0].extent), project.crs()
        )
        project.viewSettings().setDefaultViewExtent(first_extent)
        project.viewSettings().setPresetFullExtent(first_extent)
        if hasattr(project, "setFilePathStorage"):
            project.setFilePathStorage(Qgis.FilePathType.Relative)
        OUTPUT_PROJECT.unlink(missing_ok=True)
        if not project.write(str(OUTPUT_PROJECT)):
            raise RuntimeError(f"Unable to save project: {OUTPUT_PROJECT}")

        report = {
            "source": str(SOURCE_GPKG),
            "project": str(OUTPUT_PROJECT),
            "data": str(OUTPUT_GPKG),
            "route_count": routes.featureCount(),
            "maps": reports,
        }
        REPORT_PATH.write_text(
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
