"""Validate the detailed railway-history hub maps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.PyQt.QtGui import QColor, QImage
from qgis.core import (
    QgsApplication,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsProject,
)


RAILWAY_ROOT = Path(r"F:\Desktop\Railway")
OUTPUT_DIR = (
    RAILWAY_ROOT / "地图输出" / "全国专题图" / "铁路枢纽局部图"
)
PROJECT_PATH = OUTPUT_DIR / "铁路枢纽局部图.qgz"
REPORT_PATH = OUTPUT_DIR / "构建报告.json"
VALIDATION_PATH = OUTPUT_DIR / "校验报告.json"
EXPECTED = {
    "北京及周边铁路行迹": 9,
    "合肥及周边铁路行迹": 10,
    "广州及周边铁路行迹": 11,
}


def nonwhite_ratio(image: QImage) -> float:
    sample = image.scaled(300, 220)
    nonwhite = 0
    total = sample.width() * sample.height()
    for y in range(sample.height()):
        for x in range(sample.width()):
            color = QColor(sample.pixel(x, y))
            if min(color.red(), color.green(), color.blue()) < 245:
                nonwhite += 1
    return nonwhite / total


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    try:
        errors = []
        project = QgsProject.instance()
        if not project.read(str(PROJECT_PATH)):
            raise RuntimeError(f"Unable to read {PROJECT_PATH}")

        invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
        if invalid:
            errors.append(f"Invalid layers: {', '.join(invalid)}")

        route_layers = project.mapLayersByName("铁路行程轨迹")
        route_count = route_layers[0].featureCount() if route_layers else None
        if route_count != 133:
            errors.append(f"Expected 133 railway routes, got {route_count}")
        elif route_layers:
            service_counts = {"conventional": 0, "highspeed": 0}
            d901_service = None
            for feature in route_layers[0].getFeatures():
                service = str(feature["service"])
                if service in service_counts:
                    service_counts[service] += 1
                if str(feature["train"]) == "D901":
                    d901_service = service
            if service_counts != {"conventional": 44, "highspeed": 89}:
                errors.append(f"Unexpected route service counts: {service_counts}")
            if d901_service != "highspeed":
                errors.append(f"D901 should use the EMU style, got {d901_service}")

        municipality_checks = (
            ("北京", "北京及周边铁路行迹高亮城市", "北京及周边铁路行迹北京市内部区界"),
            ("天津", "北京及周边铁路行迹天津市共边轮廓", "北京及周边铁路行迹天津市内部区界"),
        )
        for label, outline_name, internal_name in municipality_checks:
            outline_layers = project.mapLayersByName(outline_name)
            internal_layers = project.mapLayersByName(internal_name)
            if not outline_layers or outline_layers[0].featureCount() != 1:
                errors.append(f"Missing single province-level {label} outline")
            if not internal_layers or internal_layers[0].featureCount() != 1:
                errors.append(f"Missing {label} internal district boundaries")
            elif next(internal_layers[0].getFeatures()).geometry().length() <= 0:
                errors.append(f"Empty {label} internal district boundaries")
        tianjin_labels = project.mapLayersByName("北京及周边铁路行迹天津市共边轮廓")
        if not tianjin_labels or not tianjin_labels[0].labelsEnabled():
            errors.append("Tianjin label is missing or disabled")

        context_layers = project.mapLayersByName("北京及周边铁路行迹周边城市")
        context_boundary_layers = project.mapLayersByName(
            "北京及周边铁路行迹周边城市内部边界"
        )
        if context_layers:
            leaked_municipalities = [
                str(feature["name"])
                for feature in context_layers[0].getFeatures()
                if "110000" in str(feature["parent"])
                or "120000" in str(feature["parent"])
            ]
            if leaked_municipalities:
                errors.append(
                    "Beijing/Tianjin districts leaked into the context boundary layer"
                )
        else:
            errors.append("Missing Beijing context city layer")
        if not context_boundary_layers:
            errors.append("Missing shared internal boundaries for context cities")
        elif next(context_boundary_layers[0].getFeatures()).geometry().length() <= 0:
            errors.append("Empty shared internal boundaries for context cities")

        guangzhou_boundaries = project.mapLayersByName(
            "广州及周边铁路行迹周边城市内部边界"
        )
        if not guangzhou_boundaries:
            errors.append("Missing shared internal boundaries for Guangzhou context cities")
        elif next(guangzhou_boundaries[0].getFeatures()).geometry().length() <= 0:
            errors.append("Empty shared internal boundaries for Guangzhou context cities")
        sar_labels = project.mapLayersByName("广州及周边铁路行迹港澳名称")
        if not sar_labels or sar_labels[0].featureCount() != 2:
            errors.append("Missing Hong Kong/Macao label features")
        elif not sar_labels[0].labelsEnabled():
            errors.append("Hong Kong/Macao labels are disabled")

        hefei_boundaries = project.mapLayersByName(
            "合肥及周边铁路行迹周边城市内部边界"
        )
        if not hefei_boundaries:
            errors.append("Missing shared internal boundaries for Hefei context cities")
        elif next(hefei_boundaries[0].getFeatures()).geometry().length() <= 0:
            errors.append("Empty shared internal boundaries for Hefei context cities")

        layouts = {layout.name(): layout for layout in project.layoutManager().printLayouts()}
        if set(layouts) != set(EXPECTED):
            errors.append(f"Unexpected layouts: {sorted(layouts)}")

        image_info = {}
        for title, station_count in EXPECTED.items():
            layers = project.mapLayersByName(f"{title}车站")
            actual_count = sum(1 for _ in layers[0].getFeatures()) if layers else None
            if actual_count != station_count:
                errors.append(f"{title}: expected {station_count} stations, got {actual_count}")
            focus_layers = project.mapLayersByName(f"{title}高亮城市")
            focus_count = (
                sum(1 for _ in focus_layers[0].getFeatures()) if focus_layers else None
            )
            if focus_count != 1:
                errors.append(f"{title}: expected one highlighted city, got {focus_count}")
            if focus_layers and focus_layers[0].labelsEnabled():
                errors.append(f"{title}: highlighted city label should be disabled")
            layout = layouts.get(title)
            if layout:
                map_items = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
                labels = [item.text() for item in layout.items() if isinstance(item, QgsLayoutItemLabel)]
                if len(map_items) != 1:
                    errors.append(f"{title}: expected one map item")
                if title not in labels:
                    errors.append(f"{title}: missing title label")
                automatic_labels = project.mapLayersByName(f"{title}自动车站标注")
                fixed_labels = project.mapLayersByName(f"{title}固定车站标注")
                if not automatic_labels or not automatic_labels[0].labelsEnabled():
                    errors.append(f"{title}: automatic station labels are not enabled")
                if not fixed_labels or not fixed_labels[0].labelsEnabled():
                    errors.append(f"{title}: fixed station labels are not enabled")

            image_path = OUTPUT_DIR / f"{title}.png"
            image = QImage(str(image_path))
            ratio = 0.0 if image.isNull() else nonwhite_ratio(image)
            image_info[image_path.name] = {
                "size": [image.width(), image.height()],
                "bytes": image_path.stat().st_size if image_path.exists() else 0,
                "nonwhite_ratio": round(ratio, 4),
            }
            if image.isNull() or image.width() < 2350 or image.height() < 2500:
                errors.append(f"{title}: image is missing or too small")
            if ratio < 0.012:
                errors.append(f"{title}: image appears blank")

        summary = {
            "project": str(PROJECT_PATH),
            "route_count": route_count,
            "layouts": sorted(layouts),
            "images": image_info,
            "errors": errors,
        }
        VALIDATION_PATH.write_text(
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
