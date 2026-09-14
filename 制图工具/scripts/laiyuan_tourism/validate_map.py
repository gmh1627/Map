"""Validate the generated Laiyuan tourism map artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qgis.core import QgsApplication, QgsProject, QgsVectorLayer


SCRIPT_DIR = Path(__file__).resolve().parent
RAILWAY_ROOT = SCRIPT_DIR.parents[2]
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "旅游专题图" / "涞源县旅游图"
GPKG = OUTPUT_DIR / "涞源县旅游图_数据.gpkg"
QGZ = OUTPUT_DIR / "涞源县旅游图.qgz"
PNG = OUTPUT_DIR / "涞源县旅游图.png"
REPORT = OUTPUT_DIR / "校验报告.json"

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
        if project.layoutManager().layoutByName("涞源县旅游图") is None:
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
        if layer_counts.get("tourism_pois") != 24:
            errors.append(
                f"tourism_pois expected 24, got {layer_counts.get('tourism_pois')}"
            )
        if layer_counts.get("laiyuan_county") != 1:
            errors.append(
                f"laiyuan_county expected 1, got {layer_counts.get('laiyuan_county')}"
            )

        report = {
            "errors": errors,
            "project_layers": len(project.mapLayers()),
            "layouts": [layout.name() for layout in project.layoutManager().layouts()],
            "gpkg_layers": layer_counts,
            "image_bytes": PNG.stat().st_size if PNG.exists() else 0,
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
