"""Validate the generated flight-history QGIS project and image."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.PyQt.QtGui import QImage
from qgis.core import (
    QgsApplication,
    QgsGeometry,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsPointXY,
    QgsProject,
)


OUTPUT_DIR = Path(r"F:\Desktop\Blog\Map\地图输出\全国专题图\航线图")


def main() -> int:
    qgz = OUTPUT_DIR / "航线图.qgz"
    png = OUTPUT_DIR / "航线图.png"
    errors = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(qgz)):
            raise RuntimeError(f"Unable to read {qgz}")
        invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
        if invalid:
            errors.append("Invalid layers: " + ", ".join(invalid))
        expected = {"飞行航线": 16, "航向箭头": 16, "机场节点": 13}
        counts = {}
        for name, count in expected.items():
            matches = project.mapLayersByName(name)
            if not matches:
                errors.append(f"Missing layer: {name}")
                continue
            counts[name] = matches[0].featureCount()
            if counts[name] != count:
                errors.append(f"{name}: expected {count}, got {counts[name]}")
        route_layer = project.mapLayersByName("飞行航线")[0]
        arrow_layer = project.mapLayersByName("航向箭头")[0]
        arrow_node = project.layerTreeRoot().findLayer(arrow_layer.id())
        if not arrow_node or not arrow_node.itemVisibilityChecked():
            errors.append("Arrow layer is not visible in the project")
        route_by_seq = {feature["seq"]: feature for feature in route_layer.getFeatures()}
        arrow_by_seq = {feature["seq"]: feature for feature in arrow_layer.getFeatures()}
        via_point = QgsGeometry.fromPointXY(QgsPointXY(114.778889, 25.853333))
        if route_by_seq[11].geometry().distance(via_point) > 1e-7:
            errors.append("Stopover route does not pass through KOW")
        latest = route_by_seq.get(16)
        if latest is None:
            errors.append("Missing CA1845 flight record")
        else:
            expected_latest = {
                "date": "2026.8",
                "origin": "PEK",
                "destination": "HFE",
                "flight": "CA1845",
                "distance_km": 959,
                "via": "",
            }
            for field, expected_value in expected_latest.items():
                if latest[field] != expected_value:
                    errors.append(
                        f"CA1845 {field}: expected {expected_value}, got {latest[field]}"
                    )
        for seq, route in route_by_seq.items():
            geometry = route.geometry()
            arrow_geometry = arrow_by_seq[seq].geometry()
            endpoint_gap = geometry.length() - geometry.lineLocatePoint(arrow_geometry)
            if not 0.12 <= endpoint_gap <= 0.16:
                errors.append(f"Arrow {seq} has inconsistent destination gap: {endpoint_gap:.3f}")
        layouts = project.layoutManager().printLayouts()
        maps = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemMap)] if len(layouts) == 1 else []
        if len(maps) != 2:
            errors.append(f"Expected main map and inset, got {len(maps)} map items")
        main_maps = [item for item in maps if item.id() == "主图"]
        if len(main_maps) != 1:
            errors.append(f"Expected one main map, got {len(main_maps)}")
        elif arrow_layer.id() not in {layer.id() for layer in main_maps[0].layers()}:
            errors.append("Arrow layer is missing from the main map")
        subtitle = "16 次飞行｜累计 22,240 km｜抵达 12 座城市、13 座机场（含经停）"
        labels = [
            item.text()
            for item in layouts[0].items()
            if isinstance(item, QgsLayoutItemLabel)
        ] if len(layouts) == 1 else []
        if subtitle not in labels:
            errors.append("Flight summary subtitle is outdated or missing")
        image = QImage(str(png))
        image_info = None
        if image.isNull():
            errors.append("Unreadable image")
        else:
            image_info = [image.width(), image.height(), png.stat().st_size]
            if image.width() < 5000 or image.height() < 4000:
                errors.append("Image resolution too low")
        result = {"layers": counts, "image": image_info, "errors": errors}
        (OUTPUT_DIR / "校验报告.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
