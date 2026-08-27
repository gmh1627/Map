"""Build editable, consistently styled overview maps for travel posts."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QPointF, Qt, QVariant
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF
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
    QgsLayoutItemPolyline,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsMarkerLineSymbolLayer,
    QgsMarkerSymbol,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsPrintLayout,
    QgsProject,
    QgsProperty,
    QgsReferencedRectangle,
    QgsRectangle,
    QgsRendererCategory,
    QgsSimpleLineSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsSymbolLayer,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsUnitTypes,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)

import card_layout


BLOG_ROOT = Path(r"F:\Desktop\Blog")
RAILWAY_ROOT = Path(r"F:\Desktop\Railway")
DATA_ROOT = RAILWAY_ROOT / "制图工具" / "数据源"
DEFAULT_OUTPUT_ROOT = RAILWAY_ROOT / "地图输出" / "区域线路图"
NATIONAL_OUTPUT = RAILWAY_ROOT / "地图输出" / "全国专题图" / "全国足迹"
ROUTE_GPKG = NATIONAL_OUTPUT / "铁路轨迹.gpkg"
MAP_DATA_GPKG = NATIONAL_OUTPUT / "全国足迹_数据.gpkg"
CITY_SOURCE = RAILWAY_ROOT / "city" / "city.json"
PROVINCE_SOURCE = RAILWAY_ROOT / "province" / "province.json"


CITY_POINTS = {
    "合肥市": (117.30, 31.72),
    "滁州市": (118.31, 32.30),
    "马鞍山市": (118.20, 31.68),
    "淮南市": (117.00, 32.63),
    "阜阳市": (115.64, 32.76),
    "周口市": (114.47, 33.78),
    "漯河市": (113.83, 33.69),
    "驻马店市": (113.78, 32.84),
    "信阳市": (113.82, 31.98),
    "孝感市": (113.66, 30.75),
    "杭州市": (120.15, 30.27),
    "宁波市": (121.55, 29.88),
    "南昌市": (115.89, 28.68),
    "郴州市": (113.02, 25.77),
    "韶关市": (113.60, 24.81),
    "广州市": (113.26, 23.13),
    "湛江市": (110.36, 21.27),
    "宣城市": (118.76, 30.95),
    "福州市": (119.30, 26.08),
    "龙岩市": (117.02, 25.08),
    "赣州市": (114.64, 25.77),
    "永州市": (111.61, 26.42),
    "柳州市": (109.41, 24.33),
    "来宾市": (109.23, 23.73),
    "贵港市": (109.60, 23.10),
    "玉林市": (110.16, 22.64),
    "扬州市": (119.41, 32.39),
    "镇江市": (119.43, 32.19),
    "枣庄市": (117.50, 34.70),
    "徐州市": (117.47, 34.08),
    "淮北市": (116.80, 33.95),
    "洛阳市": (112.20, 34.45),
    "郑州市": (113.55, 34.50),
}


@dataclass(frozen=True)
class ArrowSpec:
    name: str
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass(frozen=True)
class FocusSpec:
    source: Path
    names: tuple[str, ...]


@dataclass(frozen=True)
class CardSpec:
    title: str
    anchor: tuple[float, float]
    placement: tuple[str, float, float]
    entries: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class MapSpec:
    key: str
    folder: str
    filename: str
    title: str
    subtitle: str
    date: str
    extent: tuple[float, float, float, float]
    page: tuple[float, float]
    route_seqs: tuple[int, ...]
    station_names: tuple[str, ...]
    visited_cities: tuple[str, ...]
    start_city: str | None = "合肥市"
    end_city: str | None = None
    city_labels: tuple[str, ...] = field(default_factory=tuple)
    arrows: tuple[ArrowSpec, ...] = field(default_factory=tuple)
    place_labels: tuple[tuple[str, float, float], ...] = field(default_factory=tuple)
    area_labels: tuple[tuple[str, float, float], ...] = field(default_factory=tuple)
    station_labels: tuple[tuple[str, float, float], ...] = field(default_factory=tuple)
    focus_areas: tuple[FocusSpec, ...] = field(default_factory=tuple)
    cards: tuple[CardSpec, ...] = field(default_factory=tuple)
    scale_segment_km: int = 100
    strict_extent: bool = False


SPECS = (
    MapSpec(
        key="xiaocheng2",
        folder="小城小记2",
        filename="小城小记2",
        title="小城小记2",
        subtitle="滁州（含全椒县） · 马鞍山",
        date="2025.09.13—09.14",
        extent=(116.69, 30.95, 119.23, 33.22),
        page=(230, 220),
        route_seqs=(67, 68, 69),
        station_names=("合肥南", "全椒", "滁州北", "马鞍山", "合肥"),
        visited_cities=("合肥市", "滁州市", "马鞍山市"),
        city_labels=("合肥市", "滁州市", "马鞍山市"),
        station_labels=(("合肥南", 117.17, 31.80),),
        area_labels=(("全椒县", 118.052462, 32.058778),),
        focus_areas=(FocusSpec(RAILWAY_ROOT / "city" / "chuzhou.json", ("全椒县",)),),
        cards=(
            CardSpec(
                "全椒",
                (118.27, 32.09),
                ("upper_left", -8.0, -10.0),
                (("9.13", ("吴敬梓故居", "吴敬梓纪念馆")),),
            ),
            CardSpec(
                "滁州",
                (118.31, 32.30),
                ("upper_right", 9.0, -5.0),
                (("9.13", ("琅琊山（琅琊阁/琅琊寺/醉翁亭/二贤堂）", "南京太仆寺", "丰乐亭")),),
            ),
            CardSpec(
                "马鞍山",
                (118.51, 31.68),
                ("lower_right", 8.0, 8.0),
                (("9.14", ("采石矶", "林散之纪念馆（未入）", "朱然家族墓地博物馆", "马鞍山市博物馆")),),
            ),
        ),
        scale_segment_km=50,
    ),
    MapSpec(
        key="xiaocheng3",
        folder="小城小记3",
        filename="小城小记3",
        title="小城小记 3",
        subtitle="淮南寿县 · 阜阳（含颍上县） · 周口 · 漯河 · 驻马店 · 信阳 · 孝感",
        date="2025.09.29—10.02",
        extent=(113.10, 30.38, 117.97, 34.34),
        page=(250, 245),
        route_seqs=tuple(range(70, 80)),
        station_names=(
            "合肥南", "寿县", "颍上北", "颍上", "阜阳", "阜阳西", "周口东",
            "周口", "漯河", "漯河西", "驻马店西", "驻马店", "信阳", "信阳东",
            "孝感北", "孝感东", "汉口",
        ),
        visited_cities=("合肥市", "淮南市", "阜阳市", "周口市", "漯河市", "驻马店市", "信阳市", "孝感市"),
        city_labels=("合肥市", "阜阳市", "周口市", "漯河市", "驻马店市", "信阳市", "孝感市"),
        area_labels=(("寿县", 116.755638, 32.213044), ("颍上县", 116.12, 32.78)),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "datav_huainan_county.geojson", ("寿县",)),
            FocusSpec(RAILWAY_ROOT / "city" / "datav_fuyang_county.geojson", ("颍上县",)),
        ),
        scale_segment_km=100,
    ),
    MapSpec(
        key="home1",
        folder="回家路上1",
        filename="回家路上1",
        title="回家路上 1",
        subtitle="杭州 · 宁波慈溪市 · 南昌 · 郴州 · 韶关",
        date="2024.07.27—08.02",
        extent=(109.65, 20.21, 122.27, 32.54),
        page=(280, 280),
        route_seqs=tuple(range(28, 34)),
        station_names=("合肥南", "杭州东", "南昌西", "南昌", "郴州", "郴州西", "韶关", "广州南", "湛江西"),
        visited_cities=("合肥市", "杭州市", "宁波市", "南昌市", "郴州市", "韶关市", "湛江市"),
        end_city="湛江市",
        city_labels=("合肥市", "杭州市", "宁波市", "南昌市", "郴州市", "韶关市", "湛江市"),
        area_labels=(("慈溪", 121.266, 30.170),),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "ningbo.geojson", ("慈溪市",)),
        ),
        scale_segment_km=250,
    ),
    MapSpec(
        key="home2_full",
        folder="回家路上2",
        filename="回家路上2_完整路线",
        title="回家路上 2",
        subtitle="宣城泾县 · 福州 · 龙岩上杭县古田镇、长汀县 · 赣州（含瑞金市、于都县）",
        date="2025.07.31—08.05",
        extent=(108.80, 20.75, 120.20, 32.90),
        page=(260, 300),
        route_seqs=tuple(range(58, 67)),
        station_names=("合肥南", "泾县", "福州", "古田会址", "长汀南", "瑞金", "于都", "赣州", "赣州西", "广州东", "广州南", "湛江西"),
        visited_cities=("合肥市", "宣城市", "福州市", "龙岩市", "赣州市", "湛江市"),
        end_city="湛江市",
        city_labels=("合肥市", "宣城市", "福州市", "龙岩市", "赣州市", "湛江市"),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "xuancheng.geojson", ("泾县",)),
            FocusSpec(RAILWAY_ROOT / "city" / "longyan.geojson", ("上杭县", "长汀县")),
            FocusSpec(RAILWAY_ROOT / "city" / "ganzhou.geojson", ("瑞金市", "于都县")),
        ),
        station_labels=(("瑞金", 116.05, 25.77), ("赣州西", 114.69, 25.92)),
        scale_segment_km=200,
    ),
    MapSpec(
        key="home2_min_gan",
        folder="回家路上2",
        filename="回家路上2_闽赣段",
        title="回家路上 2 · 闽赣段",
        subtitle="福州 · 龙岩上杭县古田镇、长汀县 · 赣州（含瑞金市、于都县）",
        date="2025.08.01—08.05",
        extent=(114.10, 24.30, 119.80, 27.72),
        page=(300, 230),
        # Use the complete trip geometry and crop it in the layout, so the
        # incoming Fuzhou leg and the line leaving Ganzhou continue off-frame.
        route_seqs=tuple(range(58, 67)),
        station_names=("福州", "古田会址", "长汀南", "瑞金", "于都", "赣州", "赣州西"),
        visited_cities=("福州市", "龙岩市", "赣州市"),
        start_city=None,
        city_labels=("福州市", "龙岩市", "赣州市"),
        area_labels=(("上杭县", 116.524134, 25.058564),),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "longyan.geojson", ("上杭县", "长汀县")),
            FocusSpec(RAILWAY_ROOT / "city" / "ganzhou.geojson", ("瑞金市", "于都县")),
        ),
        station_labels=(("瑞金", 116.05, 25.92), ("赣州西", 114.65, 25.82)),
        cards=(
            CardSpec(
                "福州",
                (119.30, 26.08),
                ("upper_left", 20.0, -10.0),
                (
                    ("7.31", ("福建博物院",)),
                    (
                        "8.1",
                        (
                            "马尾船政景区（中国船政文化博物馆）",
                            "三坊七巷（严复书院/沈葆桢故居/林祥谦文化站/严复故居/林觉民冰心故居）",
                        ),
                    ),
                ),
            ),
            CardSpec(
                "古田镇",
                (116.83, 25.22),
                ("lower_right", 8.0, 8.0),
                (("8.2", ("古田会议会址", "古田会议纪念馆", "毛主席纪念园")),),
            ),
            CardSpec(
                "长汀",
                (116.36, 25.83),
                ("lower_left", -5.0, 8.0),
                (("8.2", ("瞿秋白烈士纪念碑", "瞿秋白纪念馆", "杨成武纪念馆", "汀州古城")),),
            ),
            CardSpec(
                "瑞金",
                (116.03, 25.89),
                ("upper_right", 5.0, -8.0),
                (("8.3", ("叶坪景区（中华苏维埃临时中央政府旧址）", "红井景区", "二苏大景区")),),
            ),
            CardSpec(
                "于都",
                (115.42, 25.95),
                ("upper_left", -5.0, -8.0),
                (("8.3", ("中央红军长征集结出发地纪念园",)),),
            ),
            CardSpec(
                "赣州",
                (114.94, 25.83),
                ("lower_left", -5.0, 10.0),
                (
                    ("8.4", ("江南宋城历史文化旅游区（郁孤台/宋代城墙/八境台）",)),
                    ("8.5", ("赣州市博物馆",)),
                ),
            ),
        ),
        scale_segment_km=100,
        strict_extent=True,
    ),
    MapSpec(
        key="home3",
        folder="回家路上3",
        filename="回家路上3",
        title="回家路上 3",
        subtitle="永州（含祁阳市） · 柳州 · 来宾 · 贵港 · 玉林 · 湛江",
        date="2026.02.08—02.12",
        extent=(108.35, 20.15, 112.53, 26.94),
        page=(220, 300),
        route_seqs=tuple(range(96, 104)),
        station_names=("祁阳", "永州", "零陵", "柳州", "来宾北", "来宾", "贵港", "玉林", "湛江"),
        visited_cities=("永州市", "柳州市", "来宾市", "贵港市", "玉林市", "湛江市"),
        start_city=None,
        end_city="湛江市",
        city_labels=("永州市", "柳州市", "来宾市", "贵港市", "玉林市", "湛江市"),
        focus_areas=(
            FocusSpec(
                RAILWAY_ROOT / "city" / "yongzhou.geojson",
                ("祁阳市", "零陵区", "冷水滩区"),
            ),
        ),
        scale_segment_km=100,
        strict_extent=True,
    ),
    MapSpec(
        key="yangzhou_zhenjiang",
        folder="江南江北送君归",
        filename="江南江北送君归",
        title="江南江北送君归",
        subtitle="扬州（含高邮市） · 镇江",
        date="2024.05.01—05.03",
        extent=(116.60, 30.85, 120.05, 33.50),
        page=(270, 285),
        route_seqs=(23, 24, 25),
        station_names=("合肥南", "高邮", "扬州东", "镇江"),
        visited_cities=("合肥市", "扬州市", "镇江市"),
        city_labels=("合肥市", "扬州市", "镇江市"),
        station_labels=(("合肥南", 117.16, 31.89),),
        area_labels=(("高邮市", 119.521044, 32.846740),),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "yangzhou.geojson", ("高邮市",)),
        ),
        cards=(
            CardSpec(
                "高邮",
                (119.45, 32.78),
                ("upper_right", 18.0, -10.0),
                (("5.1", ("汪曾祺纪念馆", "文游台", "盂城驿")),),
            ),
            CardSpec(
                "扬州",
                (119.42, 32.39),
                ("left", -25.0, -18.0),
                (
                    ("5.1", ("扬州博物馆", "皮市街", "东关街", "何园", "朱自清故居", "江同志故居（未入）")),
                    ("5.2", ("瘦西湖", "大明寺", "鉴真纪念堂", "平山堂", "扬州八怪纪念馆（金农故居）", "梅花岭史可法纪念馆", "古运河")),
                    ("5.3", ("张若虚纪念馆", "瓜洲古渡公园", "镇扬汽渡")),
                ),
            ),
            CardSpec(
                "镇江",
                (119.43, 32.20),
                ("lower_right", 9.0, 25.0),
                (("5.3", ("金山公园（芙蓉楼/金山寺）", "西津渡", "李公朴故居", "北固山（北固楼/甘露寺/多景楼）", "焦山")),),
            ),
        ),
        scale_segment_km=50,
        strict_extent=True,
    ),
    MapSpec(
        key="qingming",
        folder="清明游记",
        filename="清明游记",
        title="清明游记",
        subtitle="枣庄台儿庄区 · 徐州 · 淮北",
        date="2025.04.04—04.05",
        extent=(116.52, 30.95, 118.52, 35.32),
        page=(220, 280),
        route_seqs=(48, 49, 50),
        station_names=("合肥南", "枣庄", "徐州", "淮北"),
        visited_cities=("合肥市", "枣庄市", "徐州市", "淮北市"),
        city_labels=("合肥市", "枣庄市", "徐州市", "淮北市"),
        place_labels=(("台儿庄", 117.73, 34.56),),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "zaozhuang.geojson", ("台儿庄区",)),
        ),
        cards=(
            CardSpec(
                "台儿庄",
                (117.73, 34.56),
                ("upper_right", 8.0, -10.0),
                (("4.4", ("李宗仁史料馆（台儿庄北站故址）", "台儿庄大战无名英雄墓", "贺敬之柯岩文学馆", "台儿庄大战纪念馆", "台儿庄古城", "台儿庄烈士陵园")),),
            ),
            CardSpec(
                "徐州",
                (117.18, 34.26),
                ("left", -25.0, -13.0),
                (
                    ("4.4", ("快哉亭公园（未入）",)),
                    ("4.5", ("徐州博物馆", "淮海战役烈士纪念塔园林", "淮海战役纪念馆")),
                ),
            ),
            CardSpec(
                "淮北",
                (116.80, 33.96),
                ("lower_left", -25.0, 8.0),
                (("4.5", ("淮北市博物馆（中国隋唐大运河博物馆）",)),),
            ),
        ),
        scale_segment_km=50,
        strict_extent=True,
    ),
    MapSpec(
        key="luoyang_zhengzhou",
        folder="洛阳郑州中秋",
        filename="洛阳郑州中秋",
        title="“人生短短几个秋啊，不醉不罢休”：在洛阳、郑州的中秋",
        subtitle="洛阳 · 郑州（含巩义市）",
        date="2024.09.14—09.17",
        extent=(111.35, 31.00, 117.65, 35.10),
        page=(300, 225),
        route_seqs=(34, 35, 36, 37, 38),
        station_names=("合肥", "郑州", "洛阳", "巩义", "巩义南", "郑州东"),
        visited_cities=("合肥市", "洛阳市", "郑州市"),
        city_labels=("合肥市", "洛阳市", "郑州市"),
        station_labels=(
            ("洛阳", 112.43, 34.80),
            ("巩义", 112.98, 34.87),
            ("郑州", 113.65, 34.86),
            ("巩义南", 112.91, 34.56),
        ),
        focus_areas=(
            FocusSpec(RAILWAY_ROOT / "city" / "zhengzhou.geojson", ("巩义市",)),
        ),
        cards=(
            CardSpec(
                "洛阳",
                (112.45, 34.62),
                ("lower_left", -12.0, 10.0),
                (
                    ("9.15", ("龙门石窟", "香山寺蒋宋别墅", "白园", "白马寺", "明堂", "天堂", "应天门广场", "周王城天子驾六博物馆")),
                    ("9.16", ("丽景门", "洛邑古城", "隋唐大运河文化博物馆", "山陕会馆", "八路军驻洛办事处纪念馆")),
                ),
            ),
            CardSpec(
                "巩义",
                (113.02, 34.75),
                ("lower_right", 0.0, 16.0),
                (("9.16", ("杜甫故里文化园", "巩义石窟寺", "巩义博物馆", "宋仁宗永昭陵")),),
            ),
            CardSpec(
                "郑州",
                (113.62, 34.75),
                ("lower_right", 10.0, 8.0),
                (
                    ("9.16", ("中原福塔", "二七塔", "郑州绿地中心“大玉米”")),
                    ("9.17", ("河南博物院", "黄河文化公园")),
                ),
            ),
        ),
        scale_segment_km=100,
        strict_extent=True,
    ),
)

NO_CITY_CONTEXT_KEYS = {
    "home1",
    "home2_full",
    "home3",
    "qingming",
    "luoyang_zhengzhou",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--only", action="append", choices=[spec.key for spec in SPECS])
    return parser.parse_args()


def sql_strings(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def text_format(
    size: float,
    color: str,
    family: str,
    buffer: float = 0.0,
    bold: bool = False,
    weight: int | None = None,
) -> QgsTextFormat:
    fmt = QgsTextFormat()
    font = QFont(family)
    font.setPointSizeF(size)
    if weight is None:
        font.setBold(bold)
    else:
        font.setWeight(weight)
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor(color))
    if buffer:
        settings = QgsTextBufferSettings()
        settings.setEnabled(True)
        settings.setColor(QColor(255, 253, 248, 235))
        settings.setSize(buffer)
        settings.setSizeUnit(Qgis.RenderUnit.Millimeters)
        fmt.setBuffer(settings)
    return fmt


def add_layer(project: QgsProject, source: Path, name: str, layer_name: str | None = None, subset: str = "") -> QgsVectorLayer:
    uri = str(source)
    if layer_name:
        uri += f"|layername={layer_name}"
    layer = QgsVectorLayer(uri, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Invalid layer: {name} ({uri})")
    if subset and not layer.setSubsetString(subset):
        raise RuntimeError(f"Unable to subset {name}: {subset}")
    project.addMapLayer(layer)
    return layer


def write_layer(layer: QgsVectorLayer, gpkg: Path, layer_name: str, first: bool = False) -> QgsVectorLayer:
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    options.actionOnExistingFile = (
        QgsVectorFileWriter.CreateOrOverwriteFile if first
        else QgsVectorFileWriter.CreateOrOverwriteLayer
    )
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(gpkg), QgsProject.instance().transformContext(), options
    )
    if result[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(f"Unable to write {layer_name}: {result}")
    saved = QgsVectorLayer(f"{gpkg}|layername={layer_name}", layer.name(), "ogr")
    if not saved.isValid():
        raise RuntimeError(f"Unable to reload {layer_name}")
    QgsProject.instance().addMapLayer(saved)
    return saved


def fill_symbol(fill: str, alpha: int, outline: str, width: float) -> QgsFillSymbol:
    symbol = QgsFillSymbol.createSimple(
        {"color": fill, "outline_color": outline, "outline_width": str(width), "outline_width_unit": "MM"}
    )
    symbol_layer = symbol.symbolLayer(0)
    fill_color = QColor(fill)
    fill_color.setAlpha(alpha)
    symbol_layer.setFillColor(fill_color)
    if width <= 0:
        symbol_layer.setStrokeStyle(Qt.NoPen)
    else:
        symbol_layer.setStrokeColor(QColor(outline))
        symbol_layer.setStrokeWidth(width)
        symbol_layer.setStrokeWidthUnit(Qgis.RenderUnit.Millimeters)
    return symbol


def style_base_admin(cities: QgsVectorLayer) -> None:
    cities.setRenderer(
        QgsSingleSymbolRenderer(fill_symbol("#F4F6F6", 175, "255,255,255,0", 0.0))
    )


def build_province_boundaries_from_cities(
    cities: QgsVectorLayer,
    gpkg: Path,
    extent: tuple[float, float, float, float],
    *,
    layer_name: str = "province_boundaries",
    display_name: str = "省级行政区边界",
    include_province_codes: set[int] | None = None,
    exclude_province_codes: set[int] | None = None,
    line_color: str = "#A9B1B2",
    line_width: float = 0.15,
) -> QgsVectorLayer:
    """Build province outlines from the same city polygons used by the map."""
    rectangle = QgsRectangle(*extent)
    province_geometries: dict[str, list[QgsGeometry]] = {}
    municipalities = {110000, 120000, 310000, 500000}
    for feature in cities.getFeatures():
        level = str(feature["level"])
        parent = feature["parent"] if "parent" in feature.fields().names() else None
        parent_code = parent.get("adcode") if isinstance(parent, dict) else None
        if level == "city":
            routes = feature["acroutes"]
            province_code = routes[1] if isinstance(routes, list) and len(routes) > 1 else parent_code
        elif level == "district" and parent_code in municipalities:
            province_code = parent_code
        else:
            continue
        if province_code is None:
            try:
                province_code = int(feature["adcode"]) // 10000 * 10000
            except (TypeError, ValueError):
                continue
        province_code = int(province_code)
        if include_province_codes is not None and province_code not in include_province_codes:
            continue
        if exclude_province_codes is not None and province_code in exclude_province_codes:
            continue
        province_geometries.setdefault(str(province_code), []).append(feature.geometry())

    memory = QgsVectorLayer(
        f"MultiLineString?crs={cities.crs().authid()}", display_name, "memory"
    )
    memory.dataProvider().addAttributes([QgsField("province", QVariant.String)])
    memory.updateFields()
    features = []
    for province_code, geometries in province_geometries.items():
        dissolved = QgsGeometry.unaryUnion(geometries)
        if dissolved.isNull() or dissolved.isEmpty():
            continue
        if not dissolved.boundingBox().intersects(rectangle):
            continue
        if QgsWkbTypes.geometryType(dissolved.wkbType()) != QgsWkbTypes.PolygonGeometry:
            continue
        polygons = dissolved.asMultiPolygon() if dissolved.isMultipart() else [dissolved.asPolygon()]
        rings = [ring for polygon in polygons for ring in polygon if ring]
        boundary = QgsGeometry.fromMultiPolylineXY(rings)
        if boundary.isNull() or boundary.isEmpty():
            continue
        boundary.convertToMultiType()
        feature = QgsFeature(memory.fields())
        feature.setAttributes([province_code])
        feature.setGeometry(boundary)
        features.append(feature)
    if not features:
        raise RuntimeError("No province boundaries could be derived from city polygons")
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, layer_name)
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": line_color,
            "line_width": str(line_width),
            "line_width_unit": "MM",
            "joinstyle": "round",
            "capstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)
    return layer


def style_highlight(layer: QgsVectorLayer, role: str = "visited") -> None:
    if role == "start":
        symbol = fill_symbol("#DDB6AA", 158, "255,255,255,0", 0.0)
    elif role == "end":
        symbol = fill_symbol("#AFC9D6", 168, "255,255,255,0", 0.0)
    else:
        symbol = fill_symbol("#D7E8E1", 220, "255,255,255,0", 0.0)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def build_internal_admin_boundaries(
    project: QgsProject,
    cities: QgsVectorLayer,
    gpkg: Path,
    extent: tuple[float, float, float, float],
    layer_name: str = "internal_admin_boundaries",
    display_name: str = "地级行政区内部边界",
) -> QgsVectorLayer:
    rectangle = QgsRectangle(*extent)
    # The layout expands the requested extent to match the map-frame aspect ratio.
    # Include that visible fringe so edge cities retain complete boundaries.
    rectangle.grow(max(rectangle.width(), rectangle.height()) * 0.25)
    features = [
        feature
        for feature in cities.getFeatures()
        if feature.geometry().boundingBox().intersects(rectangle)
    ]
    shared_lines = []
    for index, first in enumerate(features):
        first_boundary = first.geometry().convertToType(
            QgsWkbTypes.LineGeometry, True
        )
        for second in features[index + 1 :]:
            if not first.geometry().boundingBox().intersects(
                second.geometry().boundingBox()
            ):
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
        raise RuntimeError("No internal administrative boundaries found")

    memory = QgsVectorLayer(
        f"MultiLineString?crs={cities.crs().authid()}",
        display_name,
        "memory",
    )
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    feature = QgsFeature(memory.fields())
    geometry = QgsGeometry.unaryUnion(shared_lines)
    geometry.convertToMultiType()
    feature.setGeometry(geometry)
    feature.setAttribute("name", "内部共享边界")
    memory.dataProvider().addFeature(feature)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, layer_name)
    symbol = QgsLineSymbol.createSimple(
        {
            "line_color": "#A9B1B2",
            "line_width": "0.15",
            "line_width_unit": "MM",
            "joinstyle": "round",
            "capstyle": "round",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setLabelsEnabled(False)
    return layer


def trip_route_symbol(highspeed: bool) -> QgsLineSymbol:
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
        if highspeed or line is outer:
            line.setPenCapStyle(Qt.RoundCap)
    symbol.changeSymbolLayer(0, outer)
    symbol.appendSymbolLayer(inner)
    return symbol


def style_trip_routes(layer: QgsVectorLayer) -> None:
    layer.setRenderer(
        QgsCategorizedSymbolRenderer(
            "service",
            [
                QgsRendererCategory("highspeed", trip_route_symbol(True), "高铁/动车（含城际、市郊）"),
                QgsRendererCategory("conventional", trip_route_symbol(False), "普铁"),
            ],
        )
    )


def style_background_rail(layer: QgsVectorLayer) -> None:
    symbol = QgsLineSymbol.createSimple(
        {"color": "#9DAAAD", "width": "0.12", "width_unit": "MM", "capstyle": "round"}
    )
    symbol.setOpacity(0.28)
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_stations(layer: QgsVectorLayer, moved_labels: tuple[str, ...] = ()) -> None:
    symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "circle", "color": "#B95D6D", "outline_color": "#FFFDF8",
            "outline_width": "0.34", "outline_width_unit": "MM", "size": "1.55", "size_unit": "MM",
        }
    )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    label_expression = "CASE WHEN right(\"name\", 1) = '站' THEN \"name\" ELSE \"name\" || '站' END"
    if moved_labels:
        label_expression = (
            f"CASE WHEN \"name\" IN ({sql_strings(moved_labels)}) THEN NULL "
            f"ELSE {label_expression} END"
        )
    settings.fieldName = label_expression
    settings.isExpression = True
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 10
    settings.dist = 0.65
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = True
    settings.obstacle = False
    if hasattr(settings, "allowDegradedPlacement"):
        settings.allowDegradedPlacement = True
    settings.setFormat(
        text_format(
            8.2,
            "#202020",
            "思源黑体 CN",
            0.28,
            weight=QFont.Medium,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def build_station_labels(project: QgsProject, spec: MapSpec, gpkg: Path) -> QgsVectorLayer | None:
    if not spec.station_labels:
        return None
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "移动后的车站名", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for name, lon, lat in spec.station_labels:
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttributes([name if name.endswith("站") else name + "站"])
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, "station_labels")
    layer.setRenderer(
        QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"}))
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 10
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(
        text_format(
            8.2,
            "#202020",
            "思源黑体 CN",
            0.28,
            weight=QFont.Medium,
        )
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return layer


def build_city_labels(project: QgsProject, spec: MapSpec, gpkg: Path, first: bool) -> QgsVectorLayer:
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "城市名称", "memory")
    provider = memory.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String), QgsField("display", QVariant.String), QgsField("role", QVariant.String)])
    memory.updateFields()
    features = []
    for name in spec.city_labels:
        if name not in CITY_POINTS:
            raise KeyError(f"Missing city label coordinate: {name}")
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*CITY_POINTS[name])))
        feature.setAttributes([name, name.removesuffix("市"), "start" if name == spec.start_city else "visited"])
        features.append(feature)
    provider.addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, "city_labels", first=first)
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "display"
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 7
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(text_format(10.8, "#263335", "华文新魏", 0.42))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    layer.setRenderer(QgsSingleSymbolRenderer(QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"})))
    return layer


def build_unvisited_city_labels(
    project: QgsProject,
    cities: QgsVectorLayer,
    gpkg: Path,
    extent: tuple[float, float, float, float],
    excluded_names: set[str],
    layer_name: str = "unvisited_city_labels",
    display_name: str = "未到达城市名称",
) -> QgsVectorLayer:
    rectangle = QgsRectangle(*extent)
    # Layout map items expand the requested extent to match the frame aspect ratio.
    # Include that extra visible fringe when collecting edge-city labels.
    rectangle.grow(max(rectangle.width(), rectangle.height()) * 0.25)
    extent_geometry = QgsGeometry.fromRect(rectangle)
    memory = QgsVectorLayer(
        f"MultiPolygon?crs={cities.crs().authid()}", display_name, "memory"
    )
    memory.dataProvider().addAttributes(
        [QgsField("name", QVariant.String), QgsField("display", QVariant.String)]
    )
    memory.updateFields()
    features = []
    for item in cities.getFeatures():
        name = str(item["name"])
        if str(item["level"]) != "city" or name in excluded_names:
            continue
        geometry = item.geometry()
        if geometry.isNull() or not geometry.boundingBox().intersects(rectangle):
            continue
        visible_geometry = geometry.intersection(extent_geometry)
        if visible_geometry.isNull() or visible_geometry.isEmpty():
            continue
        visible_geometry.convertToMultiType()
        display = name
        for suffix in ("自治州", "地区", "市", "盟"):
            if display.endswith(suffix):
                display = display.removesuffix(suffix)
                break
        feature = QgsFeature(memory.fields())
        feature.setAttributes([name, display])
        feature.setGeometry(visible_geometry)
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, layer_name)
    label_area_symbol = fill_symbol("#FFFFFF", 0, "#FFFFFF", 0.0)
    label_area_symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    layer.setRenderer(QgsSingleSymbolRenderer(label_area_symbol))
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "display"
    settings.placement = Qgis.LabelPlacement.Horizontal
    settings.fitInPolygonOnly = True
    settings.priority = 2
    settings.displayAll = False
    settings.obstacle = False
    if hasattr(settings, "allowDegradedPlacement"):
        settings.allowDegradedPlacement = False
    settings.setFormat(
        text_format(7.2, "#8A9390", "华文新魏", 0.22)
    )
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return layer


def build_arrows(project: QgsProject, spec: MapSpec, gpkg: Path) -> tuple[QgsVectorLayer | None, QgsVectorLayer | None]:
    if not spec.arrows:
        return None, None
    lines = QgsVectorLayer("LineString?crs=EPSG:4326", "公路及汽渡方向", "memory")
    points = QgsVectorLayer("Point?crs=EPSG:4326", "方向箭头", "memory")
    lines.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    points.dataProvider().addAttributes([QgsField("name", QVariant.String), QgsField("angle", QVariant.Double)])
    lines.updateFields()
    points.updateFields()
    line_features = []
    point_features = []
    for arrow in spec.arrows:
        x1, y1 = arrow.start
        x2, y2 = arrow.end
        dx, dy = x2 - x1, y2 - y1
        distance = max(math.hypot(dx, dy), 1e-9)
        normal_x, normal_y = -dy / distance, dx / distance
        curve_side = 1.0 if dx >= 0 else -1.0
        control_x = (x1 + x2) / 2 + normal_x * distance * 0.10 * curve_side
        control_y = (y1 + y2) / 2 + normal_y * distance * 0.10 * curve_side
        curve_points = []
        for index in range(17):
            t = index / 16
            omt = 1.0 - t
            curve_points.append(
                QgsPointXY(
                    omt * omt * x1 + 2.0 * omt * t * control_x + t * t * x2,
                    omt * omt * y1 + 2.0 * omt * t * control_y + t * t * y2,
                )
            )
        geom = QgsGeometry.fromPolylineXY(curve_points)
        line = QgsFeature(lines.fields())
        line.setGeometry(geom)
        line.setAttributes([arrow.name])
        line_features.append(line)
        before = curve_points[-2]
        tangent_dx = curve_points[-1].x() - before.x()
        tangent_dy = curve_points[-1].y() - before.y()
        marker = QgsFeature(points.fields())
        marker.setGeometry(QgsGeometry.fromPointXY(curve_points[-1]))
        marker.setAttributes(
            [arrow.name, math.degrees(math.atan2(tangent_dx, tangent_dy)) % 360]
        )
        point_features.append(marker)
    lines.dataProvider().addFeatures(line_features)
    points.dataProvider().addFeatures(point_features)
    lines.updateExtents()
    points.updateExtents()
    saved_lines = write_layer(lines, gpkg, "road_arrows")
    saved_points = write_layer(points, gpkg, "arrow_heads")

    line_symbol = QgsLineSymbol()
    outer = QgsSimpleLineSymbolLayer(QColor("#FFFDF8"), 1.30)
    inner = QgsSimpleLineSymbolLayer(QColor("#C56F4A"), 0.76)
    for item in (outer, inner):
        item.setWidthUnit(Qgis.RenderUnit.Millimeters)
        item.setPenCapStyle(Qt.RoundCap)
        item.setPenJoinStyle(Qt.RoundJoin)
    line_symbol.changeSymbolLayer(0, outer)
    line_symbol.appendSymbolLayer(inner)

    marker_symbol = QgsMarkerSymbol.createSimple(
        {
            "name": "triangle", "color": "#C56F4A", "outline_color": "#C56F4A",
            "outline_width": "0.10", "outline_width_unit": "MM", "size": "3.5", "size_unit": "MM",
        }
    )
    marker_symbol.setAngle(180)
    marker_line = QgsMarkerLineSymbolLayer(True)
    marker_line.setSubSymbol(marker_symbol)
    marker_line.setPlacements(Qgis.MarkerLinePlacement.LastVertex)
    marker_line.setRotateMarker(True)
    line_symbol.appendSymbolLayer(marker_line)
    saved_lines.setRenderer(QgsSingleSymbolRenderer(line_symbol))

    # Endpoint features remain in the GeoPackage for editing and validation;
    # the visible arrowhead belongs to the line symbol so it cannot drift.
    hidden_marker = QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"})
    saved_points.setRenderer(QgsSingleSymbolRenderer(hidden_marker))
    return saved_lines, saved_points


def build_area_labels(project: QgsProject, spec: MapSpec, gpkg: Path) -> QgsVectorLayer | None:
    if not spec.area_labels:
        return None
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "县区名称", "memory")
    memory.dataProvider().addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for name, lon, lat in spec.area_labels:
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttributes([name])
        features.append(feature)
    memory.dataProvider().addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, "area_labels")
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple({"name": "circle", "size": "0"})
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = Qgis.LabelPlacement.OverPoint
    settings.priority = 9
    settings.displayAll = True
    settings.obstacle = False
    settings.setFormat(text_format(8.6, "#5A4B27", "华文楷体", 0.40))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return layer


def build_place_labels(project: QgsProject, spec: MapSpec, gpkg: Path) -> QgsVectorLayer | None:
    if not spec.place_labels:
        return None
    memory = QgsVectorLayer("Point?crs=EPSG:4326", "公路及汽渡地点", "memory")
    provider = memory.dataProvider()
    provider.addAttributes([QgsField("name", QVariant.String)])
    memory.updateFields()
    features = []
    for name, lon, lat in spec.place_labels:
        feature = QgsFeature(memory.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttributes([name])
        features.append(feature)
    provider.addFeatures(features)
    memory.updateExtents()
    layer = write_layer(memory, gpkg, "road_places")
    layer.setRenderer(
        QgsSingleSymbolRenderer(
            QgsMarkerSymbol.createSimple(
                {
                    "name": "circle", "color": "#FFFDF8", "outline_color": "#C56F4A",
                    "outline_width": "0.28", "outline_width_unit": "MM", "size": "1.35", "size_unit": "MM",
                }
            )
        )
    )
    settings = QgsPalLayerSettings()
    settings.enabled = True
    settings.fieldName = "name"
    settings.placement = QgsPalLayerSettings.OrderedPositionsAroundPoint
    settings.priority = 9
    settings.dist = 0.65
    settings.distUnits = Qgis.RenderUnit.Millimeters
    settings.displayAll = True
    settings.setFormat(text_format(7.0, "#554137", "华文楷体", 0.38))
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    return layer


def style_focus_area(layer: QgsVectorLayer) -> None:
    symbol = fill_symbol("#70A390", 155, "#2F6257", 0.0)
    symbol.symbolLayer(0).setStrokeStyle(Qt.NoPen)
    outline = QgsSimpleLineSymbolLayer.create(
        {
            "line_color": "#2F6257",
            "line_width": "0.18",
            "line_width_unit": "MM",
        }
    )
    outline.setUseCustomDashPattern(True)
    outline.setCustomDashVector([1.5, 2.2])
    outline.setCustomDashPatternUnit(Qgis.RenderUnit.Millimeters)
    outline.setTweakDashPatternOnCorners(False)
    symbol.appendSymbolLayer(outline)
    layer.setRenderer(
        QgsSingleSymbolRenderer(symbol)
    )


def add_label(layout: QgsPrintLayout, text: str, x: float, y: float, w: float, h: float, size: float, family: str, color: str = "#111111", bold: bool = False) -> QgsLayoutItemLabel:
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    item.setTextFormat(text_format(size, color, family, bold=bold))
    item.setHAlign(Qt.AlignLeft)
    item.setVAlign(Qt.AlignVCenter)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    item.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    return item


def projected_extent(project: QgsProject, values: tuple[float, float, float, float]) -> QgsRectangle:
    transform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"), project.crs(), project.transformContext())
    return transform.transformBoundingBox(QgsRectangle(*values))


def add_scale(layout: QgsPrintLayout, map_item: QgsLayoutItemMap, y: float, segment: int) -> QgsLayoutItemScaleBar:
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Line Ticks Up")
    scale.setLinkedMap(map_item)
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitsPerSegment(segment)
    scale.setUnitLabel("km")
    scale.setHeight(1.05)
    scale.setLabelBarSpace(0.55)
    scale.setBoxContentSpace(0.5)
    scale.setTextFormat(text_format(8.0, "#48555C", "思源黑体 CN", bold=True))
    scale.setLineColor(QColor("#56636A"))
    scale.setLineWidth(0.24)
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(15, y, QgsUnitTypes.LayoutMillimeters))
    scale.attemptResize(QgsLayoutSize(84, 10, QgsUnitTypes.LayoutMillimeters))
    return scale


def add_route_legend_sample(
    layout: QgsPrintLayout,
    x: float,
    y: float,
    width: float,
    highspeed: bool,
) -> QgsLayoutItemPolyline:
    item = QgsLayoutItemPolyline(
        QPolygonF([QPointF(x, y), QPointF(x + width, y)]), layout
    )
    item.setSymbol(trip_route_symbol(highspeed))
    layout.addLayoutItem(item)
    return item


def layout_map_anchor(
    project: QgsProject,
    map_item: QgsLayoutItemMap,
    coordinates: tuple[float, float],
    frame: tuple[float, float, float, float],
) -> QPointF:
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        project.crs(),
        project.transformContext(),
    )
    point = transform.transform(QgsPointXY(*coordinates))
    extent = map_item.extent()
    x = frame[0] + (point.x() - extent.xMinimum()) / extent.width() * frame[2]
    y = frame[1] + (extent.yMaximum() - point.y()) / extent.height() * frame[3]
    return QPointF(x, y)


def add_itinerary_card(
    layout: QgsPrintLayout,
    project: QgsProject,
    map_item: QgsLayoutItemMap,
    frame: tuple[float, float, float, float],
    card: CardSpec,
) -> None:
    anchor = layout_map_anchor(project, map_item, card.anchor, frame)
    card_layout.add_itinerary_card(
        layout,
        card.title,
        card.entries,
        card.placement,
        anchor,
        frame,
    )


def build_layout(
    project: QgsProject,
    spec: MapSpec,
    layers: list,
    image: Path,
    extent_values: tuple[float, float, float, float],
    services: set[str],
) -> QgsPrintLayout:
    page_w, page_h = spec.page
    map_x, map_y = 12.0, 40.0
    map_w, map_h = page_w - 24.0, page_h - 63.0
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(spec.filename)
    layout.pageCollection().page(0).setPageSize(QgsLayoutSize(page_w, page_h, QgsUnitTypes.LayoutMillimeters))
    project.layoutManager().addLayout(layout)

    title_size = 24.5 if len(spec.title) <= 12 else (21.0 if len(spec.title) <= 18 else 18.5)
    add_label(layout, spec.title, 12, 2, page_w - 24, 15, title_size, "华文新魏")
    add_label(layout, spec.subtitle, 13, 17, page_w - 26, 11, 13.0, "华文楷体")
    add_label(layout, spec.date, 13, 28, 100, 10, 13.0, "华文楷体")

    map_item = QgsLayoutItemMap(layout)
    map_item.setId("主图")
    map_item.setFrameEnabled(True)
    map_item.setFrameStrokeColor(QColor("#69777C"))
    map_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.24, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(map_x, map_y, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(map_w, map_h, QgsUnitTypes.LayoutMillimeters))
    map_item.zoomToExtent(projected_extent(project, extent_values))
    map_item.setLayers(layers)
    map_item.setKeepLayerSet(True)
    map_frame = (map_x, map_y, map_w, map_h)
    for card in spec.cards:
        add_itinerary_card(layout, project, map_item, map_frame, card)
    add_scale(layout, map_item, map_y + map_h + 4, spec.scale_segment_km)

    legend_x = page_w - (124.0 if services == {"highspeed", "conventional"} else 67.0)
    legend_y = map_y + map_h + 1.0
    if "highspeed" in services:
        add_route_legend_sample(layout, legend_x + 1.0, legend_y + 3.7, 21.0, True)
        add_label(layout, "高铁/动车", legend_x + 25, legend_y, 34, 7, 10.0, "思源黑体 CN", "#48555C", bold=True)
    if "conventional" in services:
        conventional_x = legend_x + (61.0 if "highspeed" in services else 0.0)
        add_route_legend_sample(layout, conventional_x + 1.0, legend_y + 3.7, 21.0, False)
        add_label(layout, "普铁", conventional_x + 25, legend_y, 28, 7, 10.0, "思源黑体 CN", "#48555C", bold=True)

    settings = QgsLayoutExporter.ImageExportSettings()
    settings.dpi = 190 if spec.key in {"home1", "home2_full"} else 210
    image.unlink(missing_ok=True)
    result = QgsLayoutExporter(layout).exportToImage(str(image), settings)
    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"Export failed for {spec.key}: {result}")
    return layout


def build_one(project: QgsProject, spec: MapSpec, output_root: Path) -> dict:
    output_dir = output_root / spec.folder
    output_dir.mkdir(parents=True, exist_ok=True)
    gpkg = output_dir / f"{spec.filename}_数据.gpkg"
    qgz = output_dir / f"{spec.filename}.qgz"
    image = output_dir / f"{spec.filename}.png"
    gpkg.unlink(missing_ok=True)
    project.clear()
    project.setCrs(QgsCoordinateReferenceSystem("EPSG:3857"))

    cities = add_layer(project, CITY_SOURCE, "地级行政区")
    style_base_admin(cities)

    visited = add_layer(
        project, CITY_SOURCE, "去过的城市",
        subset=f'"name" IN ({sql_strings(spec.visited_cities)})',
    )
    style_highlight(visited)
    start = None
    if spec.start_city:
        start = add_layer(project, CITY_SOURCE, "起终点城市", subset=f'"name" = \'{spec.start_city}\'')
        style_highlight(start, role="start")
    end = None
    if spec.end_city:
        end = add_layer(project, CITY_SOURCE, "终点城市", subset=f'"name" = \'{spec.end_city}\'')
        style_highlight(end, role="end")

    route_source = add_layer(
        project, ROUTE_GPKG, "路线源数据", "rail_routes",
        subset=f'"seq" IN ({", ".join(str(value) for value in spec.route_seqs)})',
    )
    route = write_layer(route_source, gpkg, "trip_route", first=True)
    route.setName("实际铁路行程")
    style_trip_routes(route)
    services = {str(feature["service"]) for feature in route.getFeatures()}
    project.removeMapLayer(route_source.id())
    show_city_context = spec.key not in NO_CITY_CONTEXT_KEYS
    provinces = build_province_boundaries_from_cities(
        cities,
        gpkg,
        spec.extent,
        line_width=0.32 if show_city_context else 0.15,
    )
    internal_admin = (
        build_internal_admin_boundaries(project, cities, gpkg, spec.extent)
        if show_city_context
        else None
    )

    station_source = add_layer(
        project, MAP_DATA_GPKG, "车站源数据", "记录车站",
        subset=f'"name" IN ({sql_strings(spec.station_names)})',
    )
    stations = write_layer(station_source, gpkg, "stations")
    stations.setName("行程车站")
    moved_station_names = tuple(item[0] for item in spec.station_labels)
    style_stations(stations, moved_station_names)
    project.removeMapLayer(station_source.id())
    station_labels = build_station_labels(project, spec, gpkg)

    city_labels = (
        build_city_labels(project, spec, gpkg, first=False)
        if show_city_context
        else None
    )
    unvisited_city_labels = (
        build_unvisited_city_labels(
            project,
            cities,
            gpkg,
            spec.extent,
            set(spec.visited_cities)
            | ({spec.start_city} if spec.start_city else set())
            | ({spec.end_city} if spec.end_city else set()),
        )
        if show_city_context
        else None
    )
    roads, arrows = None, None
    places = build_place_labels(project, spec, gpkg)
    area_labels = build_area_labels(project, spec, gpkg)
    focus_layers = []
    for index, focus in enumerate(spec.focus_areas, 1):
        focus_layer = add_layer(
            project,
            focus.source,
            "重点县区：" + "、".join(focus.names),
            subset=f'"name" IN ({sql_strings(focus.names)})',
        )
        style_focus_area(focus_layer)
        focus_layers.append(focus_layer)

    map_layers = [stations]
    if station_labels:
        map_layers.insert(0, station_labels)
    if area_labels:
        map_layers.append(area_labels)
    if places:
        map_layers.append(places)
    if city_labels:
        map_layers.append(city_labels)
    if unvisited_city_labels:
        map_layers.append(unvisited_city_labels)
    if roads:
        map_layers.append(roads)
    map_layers.extend([route, *focus_layers])
    if start:
        map_layers.append(start)
    if end:
        map_layers.append(end)
    if internal_admin:
        map_layers.append(internal_admin)
    map_layers.extend([provinces, visited, cities])
    effective_extent = QgsRectangle(*spec.extent)
    if not spec.strict_extent:
        effective_extent.combineExtentWith(visited.extent())
        if start:
            effective_extent.combineExtentWith(start.extent())
        if end:
            effective_extent.combineExtentWith(end.extent())
    margin_x = effective_extent.width() * 0.018
    margin_y = effective_extent.height() * 0.018
    effective_extent.grow(max(margin_x, margin_y))
    extent_values = (
        effective_extent.xMinimum(), effective_extent.yMinimum(),
        effective_extent.xMaximum(), effective_extent.yMaximum(),
    )
    layout = build_layout(project, spec, map_layers, image, extent_values, services)
    project.setTitle(spec.title)
    project.setPresetHomePath(str(output_dir))
    default_extent = QgsReferencedRectangle(projected_extent(project, extent_values), project.crs())
    project.viewSettings().setDefaultViewExtent(default_extent)
    project.viewSettings().setPresetFullExtent(default_extent)
    if hasattr(project, "setFilePathStorage"):
        project.setFilePathStorage(Qgis.FilePathType.Relative)
    qgz.unlink(missing_ok=True)
    if not project.write(str(qgz)):
        raise RuntimeError(f"Unable to save {qgz}")

    return {
        "key": spec.key,
        "image": str(image),
        "project": str(qgz),
        "data": str(gpkg),
        "route_features": route.featureCount(),
        "station_features": stations.featureCount(),
        "arrow_features": arrows.featureCount() if arrows else 0,
        "map_frame": [12.0, 40.0, spec.page[0] - 24.0, spec.page[1] - 63.0],
        "map_extent_wgs84": list(extent_values),
        "scale_outside": True,
    }


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    selected = [spec for spec in SPECS if not args.only or spec.key in args.only]
    sources = {ROUTE_GPKG, MAP_DATA_GPKG, CITY_SOURCE, PROVINCE_SOURCE}
    sources.update(focus.source for spec in selected for focus in spec.focus_areas)
    for source in sources:
        if not source.exists():
            raise FileNotFoundError(source)

    app = QgsApplication([], False)
    app.initQgis()
    results = []
    try:
        project = QgsProject.instance()
        for spec in selected:
            print(f"Building {spec.key}...", flush=True)
            results.append(build_one(project, spec, output_root))
        report = output_root / "构建报告.json"
        report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report)
        return 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
