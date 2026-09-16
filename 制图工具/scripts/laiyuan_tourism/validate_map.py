"""Validate the generated Laiyuan tourism map artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.PyQt.QtGui import QImageReader
from qgis.core import QgsApplication, QgsGeometry, QgsProject, QgsRectangle, QgsVectorLayer


SCRIPT_DIR = Path(__file__).resolve().parent
RAILWAY_ROOT = SCRIPT_DIR.parents[2]
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "旅游专题图" / "涞源县旅游图"
GPKG = OUTPUT_DIR / "涞源县旅游图_数据.gpkg"
QGZ = OUTPUT_DIR / "涞源县旅游图.qgz"
PNG = OUTPUT_DIR / "涞源县旅游图.png"
REPORT = OUTPUT_DIR / "校验报告.json"
REFERENCE = SCRIPT_DIR / "assets" / "涞源县旅游图_参考.png"
OSM_NETWORK = SCRIPT_DIR / "assets" / "laiyuan_osm_network.json.gz"

EXPECTED_LAYERS = {
    "context_admin",
    "laiyuan_glow",
    "laiyuan_county",
    "roads",
    "rivers",
    "tourism_pois",
    "context_labels",
}


def main() -> int:
    errors: list[str] = []
    for path in (GPKG, QGZ, PNG):
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"missing or empty: {path}")

    app = QgsApplication([], False)
    app.initQgis()
    project = QgsProject.instance()
    try:
        if QGZ.exists() and not project.read(str(QGZ)):
            errors.append("QGIS project could not be opened")
        layout = project.layoutManager().layoutByName("涞源县旅游图")
        if layout is None:
            errors.append("layout '涞源县旅游图' is missing")
        if len(project.mapLayers()) < 7:
            errors.append(f"project has only {len(project.mapLayers())} layers")

        layer_counts: dict[str, int] = {}
        for layer_name in sorted(EXPECTED_LAYERS):
            layer = QgsVectorLayer(f"{GPKG}|layername={layer_name}", layer_name, "ogr")
            if not layer.isValid():
                errors.append(f"GeoPackage layer is missing: {layer_name}")
                continue
            layer_counts[layer_name] = layer.featureCount()
        if layer_counts.get("tourism_pois") != 27:
            errors.append(
                f"tourism_pois expected 27, got {layer_counts.get('tourism_pois')}"
            )
        if layer_counts.get("laiyuan_county") != 1:
            errors.append(
                f"laiyuan_county expected 1, got {layer_counts.get('laiyuan_county')}"
            )
        if layer_counts.get("laiyuan_glow") != 8:
            errors.append(
                f"laiyuan_glow expected 8 rings, got {layer_counts.get('laiyuan_glow')}"
            )
        if layer_counts.get("roads", 0) < 20:
            errors.append(f"roads layer is unexpectedly sparse: {layer_counts.get('roads')}")
        if layer_counts.get("rivers", 0) < 5:
            errors.append(f"rivers layer is unexpectedly sparse: {layer_counts.get('rivers')}")

        if not REFERENCE.exists():
            errors.append("hidden calibration reference is missing")
        if not OSM_NETWORK.exists():
            errors.append("cached OSM road/water extract is missing")

        layout_metrics = {}
        if layout is not None:
            items = layout.items()
            ids = {
                item.id()
                for item in items
                if hasattr(item, "id") and item.id()
            }
            missing_leaders = [
                name
                for name in ("马蹄梁", "横岭子", "白石山", "古北岳")
                if f"引线_{name}" not in ids or f"景点锚点_{name}" not in ids
            ]
            if missing_leaders:
                errors.append(f"representative callouts are incomplete: {missing_leaders}")
            calibration = layout.itemById("校准底图_导出时关闭")
            if calibration is None:
                errors.append("hidden calibration item is missing from the layout")
            elif calibration.isVisible():
                errors.append("calibration image must remain hidden during export")
            if calibration is not None and not calibration.isLocked():
                errors.append("calibration image must remain locked")
            layout_metrics = {
                "items": len(items),
                "leaders": sum(item_id.startswith("引线_") for item_id in ids),
                "anchors": sum(item_id.startswith("景点锚点_") for item_id in ids),
                "calibration_visible": calibration.isVisible() if calibration else None,
                "calibration_locked": calibration.isLocked() if calibration else None,
            }

        image_size = None
        if PNG.exists():
            size = QImageReader(str(PNG)).size()
            image_size = [size.width(), size.height()]
            if image_size != [531, 712]:
                errors.append(f"PNG expected 531 x 712, got {image_size}")

        boundary_metrics = {}
        map_extent = QgsGeometry.fromRect(QgsRectangle(114.263, 38.99, 115.137, 39.92))
        if map_extent is not None:
            for layer_name in ("roads", "rivers"):
                line_layer = QgsVectorLayer(f"{GPKG}|layername={layer_name}", layer_name, "ogr")
                outside_length = 0.0
                for feature in line_layer.getFeatures():
                    outside = feature.geometry().difference(map_extent)
                    if not outside.isNull():
                        outside_length += outside.length()
                boundary_metrics[f"{layer_name}_outside_map_extent_length"] = outside_length
                if outside_length > 1e-7:
                    errors.append(
                        f"{layer_name} extends outside map extent: {outside_length}"
                    )

        report = {
            "errors": errors,
            "project_layers": len(project.mapLayers()),
            "layouts": [layout.name() for layout in project.layoutManager().layouts()],
            "gpkg_layers": layer_counts,
            "image_bytes": PNG.stat().st_size if PNG.exists() else 0,
            "image_size": image_size,
            "layout": layout_metrics,
            "boundary": boundary_metrics,
        }
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        project.clear()


if __name__ == "__main__":
    raise SystemExit(main())
