"""Validate the Beijing passenger-rail background experiment."""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.PyQt.QtGui import QColor, QImage
from qgis.core import (
    QgsApplication,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsLayoutItemMap,
    QgsPointXY,
    QgsProject,
)


ROOT = Path(r"F:\Desktop\Railway")
OUTPUT_DIR = ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
PROJECT_PATH = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.qgz"
IMAGE_PATH = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.png"
ORIGINAL_PROJECT = OUTPUT_DIR / "铁路枢纽局部图.qgz"
ORIGINAL_IMAGE = OUTPUT_DIR / "北京及周边铁路行迹.png"
CORRIDOR_TERMINALS = {
    "崇礼线": (("崇礼站", (115.3110046, 41.0058806)),),
    "津蓟线": (
        ("天津北站", (117.2030494, 39.1656713)),
        ("蓟州北站", (117.3913352, 40.0253968)),
    ),
}
CORRIDOR_CONNECTIONS = (
    ("崇礼线", "京包客专线"),
    ("沙城-沙城西线", "丰沙线"),
    ("延庆线", "京包线"),
    ("康延线", "京包线"),
    ("怀联线", "京承线"),
    ("通乔线", "京哈线"),
)


def nonwhite_ratio(image: QImage) -> float:
    sample = image.scaled(300, 240)
    nonwhite = 0
    total = sample.width() * sample.height()
    for y in range(sample.height()):
        for x in range(sample.width()):
            color = QColor(sample.pixel(x, y))
            if min(color.red(), color.green(), color.blue()) < 245:
                nonwhite += 1
    return nonwhite / total


def main() -> int:
    errors: list[str] = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(PROJECT_PATH)):
            raise RuntimeError(f"无法打开工程：{PROJECT_PATH}")
        invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
        if invalid:
            errors.append("无效图层：" + "、".join(invalid))
        passenger_layers = project.mapLayersByName("其他客运铁路")
        feature_count = passenger_layers[0].featureCount() if passenger_layers else 0
        if feature_count != 36:
            errors.append(f"客运铁路要素数异常：{feature_count}")
        if passenger_layers:
            invalid_geometries = [
                str(feature["name"])
                for feature in passenger_layers[0].getFeatures()
                if feature.geometry().isNull()
                or feature.geometry().isEmpty()
                or feature.geometry().isMultipart()
                or feature.geometry().length() <= 0
            ]
            if invalid_geometries:
                errors.append("客运走廊不是单一连续线：" + "、".join(invalid_geometries))
            forbidden = {
                str(feature["name"])
                for feature in passenger_layers[0].getFeatures()
                if str(feature["name"])
                in {"大秦线", "唐包线", "东北环线", "东北环疏解线", "廊涿城际线"}
            }
            if forbidden:
                errors.append("混入货运或未运营线路：" + "、".join(sorted(forbidden)))
            corridors = {
                str(feature["name"]): feature.geometry()
                for feature in passenger_layers[0].getFeatures()
            }
            disconnected = [
                f"{source}->{target}"
                for source, target in CORRIDOR_CONNECTIONS
                if source not in corridors
                or target not in corridors
                or corridors[source].distance(corridors[target]) > 1e-8
            ]
            if disconnected:
                errors.append("客运走廊未接入枢纽：" + "、".join(disconnected))
            expected_styles = {
                "conventional": ("#aec2cd", 0.34),
                "highspeed": ("#9eb9c7", 0.36),
            }
            for category in passenger_layers[0].renderer().categories():
                value = str(category.value())
                if value not in expected_styles:
                    continue
                symbol_layer = category.symbol().symbolLayer(0)
                expected_color, expected_width = expected_styles[value]
                if symbol_layer.color().name().lower() != expected_color:
                    errors.append(f"{value}背景铁路颜色异常")
                if abs(symbol_layer.width() - expected_width) > 0.01:
                    errors.append(f"{value}背景铁路线宽异常")
        unified_names = {"统一省界", "统一市界", "统一北京填色", "统一天津填色"}
        missing_unified = [
            name for name in sorted(unified_names) if len(project.mapLayersByName(name)) != 1
        ]
        if missing_unified:
            errors.append("缺少统一行政区图层：" + "、".join(missing_unified))
        obsolete_tokens = {
            "高亮城市",
            "北京市内部区界",
            "天津市内部区界",
            "周边城市内部边界",
            "天津市共边轮廓",
        }
        obsolete = [
            layer.name()
            for layer in project.mapLayers().values()
            if any(token in layer.name() for token in obsolete_tokens)
        ]
        if obsolete:
            errors.append("仍含旧行政边界图层：" + "、".join(obsolete))
        province_layers = project.mapLayersByName("统一省界")
        city_layers = project.mapLayersByName("统一市界")
        if province_layers and city_layers:
            province_symbol = province_layers[0].renderer().symbol().symbolLayer(0)
            city_symbol = city_layers[0].renderer().symbol().symbolLayer(0)
            if abs(province_symbol.width() - 0.42) > 0.01:
                errors.append("统一省界线宽应为0.42 mm")
            if abs(city_symbol.width() - 0.15) > 0.01:
                errors.append("统一市界线宽应为0.15 mm")
            province_geometry = next(province_layers[0].getFeatures()).geometry()
            city_geometry = next(city_layers[0].getFeatures()).geometry()
            parts = (
                city_geometry.asMultiPolyline()
                if city_geometry.isMultipart()
                else [city_geometry.asPolyline()]
            )
            near_misses = []
            for part in parts:
                if not part:
                    continue
                for point in (part[0], part[-1]):
                    distance = province_geometry.distance(
                        QgsGeometry.fromPointXY(point)
                    )
                    if 1e-9 < distance < 0.005:
                        near_misses.append(distance)
            if near_misses:
                errors.append(
                    f"市界与省界存在{len(near_misses)}个近距离未接合端点"
                )
        route_layers = project.mapLayersByName("铁路行程轨迹")
        route_count = route_layers[0].featureCount() if route_layers else 0
        if route_count != 133:
            errors.append(f"当前行迹数量应为133，实际为：{route_count}")
        if project.mapLayersByName("其他客运铁路终点"):
            errors.append("不应显示背景客运终点图层")
        if passenger_layers:
            corridors = {
                str(feature["name"]): feature.geometry()
                for feature in passenger_layers[0].getFeatures()
            }
            detached_terminals = []
            for corridor_name, terminals in CORRIDOR_TERMINALS.items():
                geometry = corridors.get(corridor_name)
                for terminal_name, coordinate in terminals:
                    point = QgsGeometry.fromPointXY(QgsPointXY(*coordinate))
                    if geometry is None or geometry.distance(point) > 0.01:
                        detached_terminals.append(terminal_name)
            if detached_terminals:
                errors.append("客运走廊未经过真实终点：" + "、".join(detached_terminals))

        layouts = project.layoutManager().printLayouts()
        if len(layouts) != 1 or layouts[0].name() != "北京及周边铁路行迹_客运铁路底图":
            errors.append("试验布局缺失或重复")
        else:
            maps = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemMap)]
            if len(maps) != 1:
                errors.append(f"主图地图框数量异常：{len(maps)}")
            elif passenger_layers:
                names = [layer.name() for layer in maps[0].layers()]
                if (
                    "其他客运铁路" not in names
                    or "统一省界" not in names
                    or "统一市界" not in names
                    or "铁路行程轨迹" not in names
                ):
                    errors.append("主图缺少客运底图或原有行迹")
                elif names.index("铁路行程轨迹") > names.index("其他客运铁路"):
                    errors.append("原有行迹没有绘制在客运底图上方")
                to_passenger_crs = QgsCoordinateTransform(
                    project.crs(),
                    passenger_layers[0].crs(),
                    project.transformContext(),
                )
                visible_extent = to_passenger_crs.transformBoundingBox(maps[0].extent())
                through_corridors = {
                    "京九线", "京包客专线", "京包线", "京原线",
                    "京哈线", "京哈高速线", "京唐城际线", "京广线",
                    "京广高速线", "京承线", "京沪线", "京沪高铁",
                    "京津城际线", "京通线", "京雄城际线",
                }
                premature = []
                for feature in passenger_layers[0].getFeatures():
                    name = str(feature["name"])
                    if name not in through_corridors:
                        continue
                    points = feature.geometry().asPolyline()
                    if (
                        points
                        and visible_extent.contains(points[0])
                        and visible_extent.contains(points[-1])
                    ):
                        premature.append(name)
                if premature:
                    errors.append("跨区域干线在图框内提前结束：" + "、".join(premature))

        image = QImage(str(IMAGE_PATH))
        ratio = 0.0 if image.isNull() else nonwhite_ratio(image)
        if image.isNull() or image.width() < 2800 or image.height() < 2700:
            errors.append("试验图片缺失或分辨率过低")
        if ratio < 0.02:
            errors.append("试验图片疑似空白")
        if not ORIGINAL_PROJECT.exists() or not ORIGINAL_IMAGE.exists():
            errors.append("原始局部图成果缺失")
        shapefiles = [
            layer.name()
            for layer in project.mapLayers().values()
            if layer.source().split("|", 1)[0].lower().endswith(".shp")
        ]
        if shapefiles:
            errors.append("工程仍引用Shapefile：" + "、".join(shapefiles))
        print(
            {
                "passenger_features": feature_count,
                "travel_routes": route_count,
                "image": [image.width(), image.height(), IMAGE_PATH.stat().st_size],
                "nonwhite_ratio": round(ratio, 4),
                "errors": errors,
            }
        )
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
