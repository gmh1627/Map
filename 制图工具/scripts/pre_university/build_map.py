"""Build a national map of cities visited before university."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsReferencedRectangle,
    QgsSingleSymbolRenderer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)


RAILWAY_ROOT = Path(r"F:\Desktop\Blog\Map")
COMMON_DIR = RAILWAY_ROOT / "制图工具" / "scripts" / "travel_history"
sys.path.insert(0, str(COMMON_DIR))
import build_maps as bm  # noqa: E402


OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "全国专题图" / "上大学前去过的城市"
OUTPUT_GPKG = OUTPUT_DIR / "上大学前去过的城市_数据.gpkg"
OUTPUT_QGZ = OUTPUT_DIR / "上大学前去过的城市.qgz"
OUTPUT_PNG = OUTPUT_DIR / "上大学前去过的城市.png"
PAGE = (430.0, 330.0)
MAP_FRAME = (12.0, 40.0, 406.0, 248.0)
INSET_FRAME = (350.0, 208.0, 68.0, 80.0)

VISITED_PROVINCES = ("广东省", "贵州省", "北京市", "广西壮族自治区")
VISITED_CITIES = (
    "湛江市", "广州市", "茂名市", "东莞市", "河源市", "惠州市", "阳江市",
    "江门市", "佛山市", "中山市", "珠海市", "贵阳市", "黔南布依族苗族自治州",
    "黔东南苗族侗族自治州", "安顺市", "铜仁市", "北海市", "桂林市",
)
LABEL_NAMES = {
    "北京市": "北京",
    **{name: name.removesuffix("市") for name in VISITED_CITIES},
    "黔南布依族苗族自治州": "黔南",
    "黔东南苗族侗族自治州": "黔东南",
}


def sql_strings(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def fill(fill_color: str, alpha: int, outline: str, width: float) -> QgsFillSymbol:
    symbol = QgsFillSymbol.createSimple({
        "color": fill_color, "outline_color": outline,
        "outline_width": str(width), "outline_width_unit": "MM",
    })
    color = QColor(fill_color)
    color.setAlpha(alpha)
    symbol.symbolLayer(0).setFillColor(color)
    return symbol


def add_layer(project: QgsProject, source: Path, name: str, subset: str = "") -> QgsVectorLayer:
    layer = QgsVectorLayer(str(source), name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid layer: {source}")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Unable to subset {name}")
    project.addMapLayer(layer)
    return layer


def build_label_layer(
    project: QgsProject,
    cities: QgsVectorLayer,
    beijing: QgsVectorLayer,
) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "去过的城市名", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for source_layer in (cities, beijing):
        for source in source_layer.getFeatures():
            full_name = str(source["name"])
            point, _ = source.geometry().poleOfInaccessibility(0.01)
            if point.isEmpty():
                point = source.geometry().pointOnSurface()
            if point.isEmpty():
                point = source.geometry().centroid()
            feature = QgsFeature(memory.fields())
            feature.setAttributes([LABEL_NAMES[full_name]])
            feature.setGeometry(point)
            features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    project.addMapLayer(memory)
    bm.OUTPUT_GPKG = OUTPUT_GPKG
    saved = bm.save_memory_layer(project, memory, "visited_city_labels", overwrite_file=True)
    project.removeMapLayer(memory.id())
    saved.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "size": "0", "outline_style": "no"})))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.displayAll = True
    settings.priority = 10
    text = QgsTextFormat()
    text.setFont(QFont("华文楷体"))
    text.setSize(6.5)
    text.setColor(QColor("#244A67"))
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.34)
    buffer.setSizeUnit(Qgis.RenderUnit.Millimeters)
    buffer.setColor(QColor("#FFFDFC"))
    text.setBuffer(buffer)
    settings.setFormat(text)
    saved.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    saved.setLabelsEnabled(True)
    return saved


def build_layout(project: QgsProject, layers: list[QgsVectorLayer], inset_layers: list[QgsVectorLayer]) -> QgsPrintLayout:
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("上大学前去过的城市")
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(*PAGE, QgsUnitTypes.LayoutMillimeters))
    project.layoutManager().addLayout(layout)
    bm.add_label(layout, "上大学前走过的地方", 12, 3, 310, 16, 27, "#111111", "华文新魏")
    bm.add_label(layout, "19 个城市", 13, 20, 390, 13, 16.0, "#111111", "华文楷体")

    main = QgsLayoutItemMap(layout)
    main.setId("主图")
    main.setFrameEnabled(True)
    main.setFrameStrokeColor(QColor("#667F8E"))
    main.setFrameStrokeWidth(QgsLayoutMeasurement(0.24, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(main)
    main.attemptMove(QgsLayoutPoint(*MAP_FRAME[:2], QgsUnitTypes.LayoutMillimeters))
    main.attemptResize(QgsLayoutSize(*MAP_FRAME[2:], QgsUnitTypes.LayoutMillimeters))
    main.zoomToExtent(bm.projected_extent(project, bm.CHINA_EXTENT))
    main.setLayers(layers)
    main.setKeepLayerSet(True)
    bm.add_scale_bar(layout, main)

    inset = QgsLayoutItemMap(layout)
    inset.setId("南海诸岛插图")
    inset.setFrameEnabled(True)
    inset.setFrameStrokeColor(QColor("#667F8E"))
    inset.setFrameStrokeWidth(QgsLayoutMeasurement(0.18, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(inset)
    inset.attemptMove(QgsLayoutPoint(*INSET_FRAME[:2], QgsUnitTypes.LayoutMillimeters))
    inset.attemptResize(QgsLayoutSize(*INSET_FRAME[2:], QgsUnitTypes.LayoutMillimeters))
    inset.zoomToExtent(bm.projected_extent(project, bm.SOUTH_CHINA_SEA_EXTENT))
    inset.setLayers(inset_layers)
    inset.setKeepLayerSet(True)
    bm.add_label(layout, "南海诸岛", 374, 276, 40, 8, 5.5, "#244B61", "华文楷体", h_align=Qt.AlignRight, v_align=Qt.AlignBottom)
    return layout


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        project.clear()
        crs = QgsCoordinateReferenceSystem()
        if not crs.createFromProj(bm.CHINA_ALBERS_PROJ):
            raise RuntimeError("Unable to create China Albers CRS")
        project.setCrs(crs)

        all_cities = add_layer(project, bm.CITY_JSON, "地级行政区")
        all_cities.setRenderer(QgsSingleSymbolRenderer(fill("#F5F9FB", 165, "#A5B5BF", 0.12)))
        all_provinces = add_layer(project, bm.PROVINCE_JSON, "省级行政区")
        all_provinces.setRenderer(QgsSingleSymbolRenderer(fill("#FFFFFF", 0, "#526E7E", 0.42)))
        provinces = add_layer(project, bm.PROVINCE_JSON, "去过的省级行政区", subset=f'"name" IN ({sql_strings(VISITED_PROVINCES)})')
        provinces.setRenderer(QgsSingleSymbolRenderer(fill("#D7E9F2", 175, "#6E9CB4", 0.32)))
        cities = add_layer(project, bm.CITY_JSON, "去过的城市", subset=f'"name" IN ({sql_strings(VISITED_CITIES)})')
        cities.setRenderer(QgsSingleSymbolRenderer(fill("#8EBBD0", 185, "#477B95", 0.42)))
        beijing = add_layer(project, bm.PROVINCE_JSON, "北京", subset='"name" = \'北京市\'')
        beijing.setRenderer(QgsSingleSymbolRenderer(fill("#8EBBD0", 185, "#477B95", 0.42)))
        labels = build_label_layer(project, cities, beijing)

        layers = [labels, cities, beijing, provinces, all_provinces, all_cities]
        layout = build_layout(project, layers, [provinces, all_provinces, all_cities])
        project.setTitle("上大学前去过的城市")
        project.setPresetHomePath(str(OUTPUT_DIR))
        default_extent = QgsReferencedRectangle(bm.projected_extent(project, bm.CHINA_EXTENT), project.crs())
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
        if QgsLayoutExporter(layout).exportToImage(str(OUTPUT_PNG), settings) != QgsLayoutExporter.Success:
            raise RuntimeError("Image export failed")
        report = {"image": str(OUTPUT_PNG), "project": str(OUTPUT_QGZ), "city_count": 19, "province_count": 4}
        (OUTPUT_DIR / "构建报告.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
