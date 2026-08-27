"""Validate the complete Gansu itinerary map."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import QgsApplication, QgsProject


OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\区域线路图\甘肃行旅")
PROJECT = OUTPUT_DIR / "甘肃行旅.qgz"
IMAGE = OUTPUT_DIR / "甘肃行旅.png"
EXPECTED_LAYERS = {
    "甘肃地级行政区": 14,
    "到访城市": 8,
    "重点县市": 8,
    "城市名称": 14,
    "重点县市名称": 8,
}
MAX_IMAGE_BYTES = 3_000_000


def main() -> int:
    errors = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(PROJECT)):
            errors.append("工程无法打开")
        counts = {}
        for name, expected in EXPECTED_LAYERS.items():
            matches = project.mapLayersByName(name)
            if len(matches) != 1:
                errors.append(f"图层 {name} 数量异常: {len(matches)}")
                continue
            layer = matches[0]
            if not layer.isValid():
                errors.append(f"图层无效: {name}")
            counts[name] = layer.featureCount()
            if layer.featureCount() != expected:
                errors.append(
                    f"图层 {name} 要素数 {layer.featureCount()}，预期 {expected}"
                )
        layouts = project.layoutManager().printLayouts()
        if len(layouts) != 1 or layouts[0].name() != "甘肃行旅":
            errors.append("甘肃行旅布局缺失")
        for boundary_name in ("周边省界", "甘肃省界"):
            matches = project.mapLayersByName(boundary_name)
            if len(matches) != 1:
                errors.append(f"图层 {boundary_name} 数量异常: {len(matches)}")
                continue
            width = matches[0].renderer().symbol().symbolLayer(0).width()
            if abs(width - 0.32) > 0.01:
                errors.append(f"{boundary_name} 线宽 {width}，预期 0.32")
        image_bytes = IMAGE.stat().st_size if IMAGE.exists() else 0
        if image_bytes == 0:
            errors.append("PNG 缺失或为空")
        elif image_bytes > MAX_IMAGE_BYTES:
            errors.append(f"PNG 超过 3 MB: {image_bytes:,} bytes")
        report = {
            "project": str(PROJECT),
            "layers": counts,
            "image_bytes": image_bytes,
            "errors": errors,
        }
        (OUTPUT_DIR / "校验报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    raise SystemExit(main())
