"""Validate the Beijing passenger-rail background experiment."""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.PyQt.QtGui import QColor, QImage
from qgis.core import QgsApplication, QgsLayoutItemMap, QgsProject


ROOT = Path(r"F:\Desktop\Railway")
OUTPUT_DIR = ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
PROJECT_PATH = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.qgz"
IMAGE_PATH = OUTPUT_DIR / "北京及周边铁路行迹_客运铁路底图.png"
ORIGINAL_PROJECT = OUTPUT_DIR / "铁路枢纽局部图.qgz"
ORIGINAL_IMAGE = OUTPUT_DIR / "北京及周边铁路行迹.png"


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
        if not 500 <= feature_count <= 8000:
            errors.append(f"客运铁路要素数异常：{feature_count}")
        if passenger_layers:
            forbidden = {
                str(feature["name"])
                for feature in passenger_layers[0].getFeatures()
                if str(feature["name"])
                in {"大秦线", "唐包线", "东北环线", "东北环疏解线", "廊涿城际线"}
            }
            if forbidden:
                errors.append("混入货运或未运营线路：" + "、".join(sorted(forbidden)))
        route_layers = project.mapLayersByName("铁路行程轨迹")
        route_count = route_layers[0].featureCount() if route_layers else 0
        if route_count != 133:
            errors.append(f"当前行迹数量应为133，实际为：{route_count}")

        layouts = project.layoutManager().printLayouts()
        if len(layouts) != 1 or layouts[0].name() != "北京及周边铁路行迹_客运铁路底图":
            errors.append("试验布局缺失或重复")
        else:
            maps = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemMap)]
            if len(maps) != 1:
                errors.append(f"主图地图框数量异常：{len(maps)}")
            elif passenger_layers:
                names = [layer.name() for layer in maps[0].layers()]
                if "其他客运铁路" not in names or "铁路行程轨迹" not in names:
                    errors.append("主图缺少客运底图或原有行迹")
                elif names.index("铁路行程轨迹") > names.index("其他客运铁路"):
                    errors.append("原有行迹没有绘制在客运底图上方")

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
