"""Validate regional overview QGIS projects and exported images."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qgis.PyQt.QtGui import QImage
from qgis.core import (
    QgsApplication,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsProject,
)


DEFAULT_OUTPUT_ROOT = Path(r"F:\Desktop\Railway\地图输出\区域线路图")
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
    return parser.parse_args()


def main() -> int:
    root = parse_args().output_root.resolve()
    build_report = json.loads((root / "构建报告.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    results = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        for record in build_report:
            project.clear()
            qgz = Path(record["project"])
            image_path = Path(record["image"])
            key = record["key"]
            item_errors = []
            if not project.read(str(qgz)):
                item_errors.append("project unreadable")
                continue
            invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
            if invalid:
                item_errors.append("invalid layers: " + ", ".join(invalid))
            required = {
                "实际铁路行程",
                "行程车站",
                "去过的城市",
                "省级行政区边界",
            }
            city_context = {
                "城市名称",
                "未到达城市名称",
                "地级行政区内部边界",
            }
            if key not in NO_CITY_CONTEXT_KEYS:
                required |= city_context
            names = {layer.name() for layer in project.mapLayers().values()}
            forbidden = sorted({"背景铁路", "背景铁路复线", "OSM 淡色底图"} & names)
            if forbidden:
                item_errors.append("unvisited railway layers present: " + ", ".join(forbidden))
            missing = sorted(required - names)
            if missing:
                item_errors.append("missing layers: " + ", ".join(missing))
            unexpected_context = sorted(city_context & names) if key in NO_CITY_CONTEXT_KEYS else []
            if unexpected_context:
                item_errors.append("city context should be absent: " + ", ".join(unexpected_context))
            province_layers = project.mapLayersByName("省级行政区边界")
            if province_layers:
                symbol_layer = province_layers[0].renderer().symbol().symbolLayer(0)
                expected_width = 0.15 if key in NO_CITY_CONTEXT_KEYS else 0.32
                actual_width = symbol_layer.width()
                if abs(actual_width - expected_width) > 0.01:
                    item_errors.append(
                        f"province boundary width {actual_width}, expected {expected_width}"
                    )
            context_labels = project.mapLayersByName("未到达城市名称")
            if context_labels:
                if not context_labels[0].labelsEnabled():
                    item_errors.append("unvisited city labels are disabled")
            layouts = project.layoutManager().printLayouts()
            if len(layouts) != 1:
                item_errors.append(f"expected one layout, got {len(layouts)}")
                frame = None
            else:
                maps = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemMap)]
                scales = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemScaleBar)]
                labels = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemLabel)]
                if len(maps) != 1:
                    item_errors.append(f"expected one map item, got {len(maps)}")
                    frame = None
                else:
                    map_item = maps[0]
                    pos = map_item.positionWithUnits()
                    size = map_item.sizeWithUnits()
                    bottom = pos.y() + size.height()
                    frame = [pos.x(), pos.y(), size.width(), size.height()]
                    if not map_item.frameEnabled():
                        item_errors.append("map frame disabled")
                    if len(scales) != 1 or scales[0].positionWithUnits().y() < bottom:
                        item_errors.append("scale bar is not outside the map")
                    route_layers = project.mapLayersByName("实际铁路行程")
                    services = (
                        {str(feature["service"]) for feature in route_layers[0].getFeatures()}
                        if route_layers else set()
                    )
                    expected_legends = {
                        "highspeed": "高铁/动车",
                        "conventional": "普铁",
                    }
                    for service, legend_text in expected_legends.items():
                        matches = [item for item in labels if item.text() == legend_text]
                        expected_count = 1 if service in services else 0
                        if len(matches) != expected_count:
                            item_errors.append(f"missing or duplicate legend label: {legend_text}")
                        elif matches and matches[0].positionWithUnits().y() < bottom:
                            item_errors.append(f"legend label is not outside the map: {legend_text}")
            image = QImage(str(image_path))
            if image.isNull():
                item_errors.append("image unreadable")
                image_info = None
            else:
                image_info = [image.width(), image.height(), image_path.stat().st_size]
                if image.width() < 1800 or image.height() < 1700:
                    item_errors.append("image resolution too low")
                if image_path.stat().st_size > 3_000_000:
                    item_errors.append("image exceeds 3 MB")
            if record.get("route_features", 0) < 1:
                item_errors.append("empty route")
            errors.extend(f"{key}: {error}" for error in item_errors)
            results.append({"key": key, "frame": frame, "image": image_info, "errors": item_errors})
        report = {"maps": results, "errors": errors}
        (root / "校验报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
