"""Validate the redesigned Shanxi-Shaanxi QGIS project and image."""

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


DEFAULT_OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\区域线路图\山陕漫游")
EXPECTED_COUNTS = {
    "实际铁路行程": 12,
    "公路行程": 2,
    "公路方向": 2,
    "行程车站": 10,
    "大同南站手工标注": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    project_path = output_dir / "山陕漫游.qgz"
    image_path = output_dir / "山陕漫游.png"
    errors = []

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(project_path)):
            raise RuntimeError(f"Unable to read {project_path}")
        invalid = [
            layer.name() for layer in project.mapLayers().values() if not layer.isValid()
        ]
        if invalid:
            errors.append(f"Invalid layers: {', '.join(invalid)}")
        names = {layer.name() for layer in project.mapLayers().values()}
        forbidden = sorted({"背景铁路", "背景铁路复线", "OSM 淡色底图"} & names)
        if forbidden:
            errors.append("Unvisited railway layers present: " + ", ".join(forbidden))

        counts = {}
        for name, expected in EXPECTED_COUNTS.items():
            layers = project.mapLayersByName(name)
            if not layers:
                errors.append(f"Missing layer: {name}")
                continue
            counts[name] = layers[0].featureCount()
            if counts[name] != expected:
                errors.append(f"{name}: expected {expected}, got {counts[name]}")

        route_layers = project.mapLayersByName("实际铁路行程")
        if route_layers:
            services = {"highspeed": 0, "conventional": 0}
            for feature in route_layers[0].getFeatures():
                service = str(feature["service"])
                if service not in services:
                    errors.append(f"Unexpected rail service: {service}")
                else:
                    services[service] += 1
            if services != {"highspeed": 2, "conventional": 10}:
                errors.append(f"Unexpected rail service counts: {services}")

        for name in ("内蒙古地级市", "内蒙古地市内部边界", "未到达城市名称"):
            layers = project.mapLayersByName(name)
            if not layers:
                errors.append(f"Missing layer: {name}")
            elif name == "未到达城市名称" and not layers[0].labelsEnabled():
                errors.append("Unvisited city labels are disabled")
        tianjin_layers = project.mapLayersByName("天津")
        if not tianjin_layers or tianjin_layers[0].featureCount() != 1:
            errors.append("Missing Tianjin polygon")
        elif not tianjin_layers[0].labelsEnabled():
            errors.append("Tianjin label is disabled")
        province_layers = project.mapLayersByName("省界")
        if province_layers:
            width = province_layers[0].renderer().symbol().symbolLayer(0).width()
            if abs(width - 0.32) > 0.01:
                errors.append(f"Province boundary width {width}, expected 0.32")
        else:
            errors.append("Missing province boundary layer")

        layouts = project.layoutManager().printLayouts()
        if len(layouts) != 1:
            errors.append(f"Expected one layout, got {len(layouts)}")
            layout_geometry = None
        else:
            layout = layouts[0]
            maps = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
            scales = [
                item for item in layout.items() if isinstance(item, QgsLayoutItemScaleBar)
            ]
            if len(maps) != 1:
                errors.append(f"Expected one map, got {len(maps)}")
                layout_geometry = None
            else:
                map_item = maps[0]
                pos = map_item.positionWithUnits()
                size = map_item.sizeWithUnits()
                bottom = pos.y() + size.height()
                layout_geometry = [pos.x(), pos.y(), size.width(), size.height()]
                if abs(size.width() - 276) > 0.1 or abs(size.height() - 147) > 0.1:
                    errors.append("Unexpected main map dimensions")
                if not scales or any(
                    scale.positionWithUnits().y() < bottom for scale in scales
                ):
                    errors.append("Scale bar is not outside main map")
                legend_labels = [
                    item
                    for item in layout.items()
                    if isinstance(item, QgsLayoutItemLabel)
                    and item.text() in {"高铁", "普铁"}
                ]
                if len(legend_labels) != 2 or any(
                    item.positionWithUnits().y() < bottom for item in legend_labels
                ):
                    errors.append("Railway legends are missing or inside the main map")

        image = QImage(str(image_path))
        image_info = None
        if image.isNull():
            errors.append(f"Unreadable image: {image_path}")
        else:
            image_info = [image.width(), image.height(), image_path.stat().st_size]
            if image.width() < 1800 or image.height() < 1700:
                errors.append("Image resolution too low")
            if image_path.stat().st_size > 3_000_000:
                errors.append("Image exceeds 3 MB")

        summary = {
            "project": str(project_path),
            "layers": counts,
            "layout_geometry": layout_geometry,
            "image": image_info,
            "errors": errors,
        }
        (output_dir / "校验报告.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
