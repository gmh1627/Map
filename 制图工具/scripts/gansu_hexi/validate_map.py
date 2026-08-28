"""Validate the Hexi Corridor overview map."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtGui import QImage
from qgis.core import QgsApplication, QgsProject


OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\区域线路图\走河西")
PROJECT = OUTPUT_DIR / "走河西.qgz"
IMAGE = OUTPUT_DIR / "走河西.png"


def main() -> int:
    errors: list[str] = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(PROJECT)):
            raise RuntimeError(f"工程无法打开：{PROJECT}")
        invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
        if invalid:
            errors.append("无效图层：" + "、".join(invalid))
        names = {layer.name() for layer in project.mapLayers().values()}
        forbidden = {
            "城市名称",
            "未到达城市名称",
            "地级行政区内部边界",
        } & names
        if forbidden:
            errors.append("仍含城市名称或市界：" + "、".join(sorted(forbidden)))
        province_layers = project.mapLayersByName("省级行政区边界")
        if len(province_layers) != 1:
            errors.append(f"省界图层数量异常：{len(province_layers)}")
        else:
            width = province_layers[0].renderer().symbol().symbolLayer(0).width()
            if abs(width - 0.15) > 0.01:
                errors.append(f"省界线宽 {width}，预期 0.15")
        for required in (
            "实际铁路行程",
            "行程车站",
            "返程航线",
            "重点县市",
            "高亮城市边界",
        ):
            if required not in names:
                errors.append("缺少图层：" + required)
        highlighted = project.mapLayersByName("高亮城市边界")
        if highlighted:
            width = highlighted[0].renderer().symbol().symbolLayer(0).width()
            if abs(width - 0.22) > 0.01:
                errors.append(f"高亮城市边界线宽 {width}，预期 0.22")
        station_label_layers = project.mapLayersByName("主要车站名")
        expected_label_latitudes = {
            "武威站": 37.91787,
            "兰州西站": 35.96879,
            "定西北站": 35.53481,
        }
        actual_label_latitudes = (
            {
                str(feature["name"]): feature.geometry().asPoint().y()
                for feature in station_label_layers[0].getFeatures()
            }
            if station_label_layers
            else {}
        )
        for name, expected in expected_label_latitudes.items():
            actual = actual_label_latitudes.get(name)
            if actual is None or abs(actual - expected) > 1e-5:
                errors.append(f"{name} 标签纬度异常：{actual}")
        image = QImage(str(IMAGE))
        if image.isNull() or image.width() < 2500 or image.height() < 1800:
            errors.append("PNG缺失或分辨率过低")
        result = {
            "layers": len(project.mapLayers()),
            "image": [image.width(), image.height(), IMAGE.stat().st_size],
            "errors": errors,
        }
        (OUTPUT_DIR / "校验报告.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    raise SystemExit(main())
