"""Sync reviewed railway records without recomputing unchanged track geometry."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import QgsApplication, QgsGeometry, QgsVectorLayer
from parse_source import read_rail_records

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "地图输出/全国专题图/全国足迹"


def update_layer(path: Path, name: str, records: dict) -> int:
    layer = QgsVectorLayer(f"{path}|layername={name}", name, "ogr")
    if not layer.isValid() or layer.featureCount() != len(records):
        raise RuntimeError(f"Unexpected railway layer: {path}/{name}")
    planned = []
    fields = layer.fields()
    for feature in layer.getFeatures():
        record = records[int(feature["seq"])]
        old_endpoints = (str(feature["origin"]), str(feature["destination"]))
        new_endpoints = (record["origin"], record["destination"])
        if old_endpoints not in (new_endpoints, tuple(reversed(new_endpoints))):
            raise RuntimeError(f"Route {record['seq']} needs new track geometry")
        attributes = {
            "date": record["date"], "origin": record["origin"],
            "destination": record["destination"], "train": record["train"],
            "table_km": record["distance_km"], "service": record["service_class"],
        }
        changes = {fields.indexOf(key): value for key, value in attributes.items() if feature[key] != value}
        geometry = None
        if old_endpoints != new_endpoints:
            original = feature.geometry()
            if original.isMultipart():
                geometry = QgsGeometry.fromMultiPolylineXY([list(reversed(part)) for part in reversed(original.asMultiPolyline())])
            else:
                geometry = QgsGeometry.fromPolylineXY(list(reversed(original.asPolyline())))
        planned.append((feature.id(), changes, geometry))
    if not layer.startEditing():
        raise RuntimeError(f"Unable to edit {path}")
    for fid, changes, geometry in planned:
        for field, value in changes.items():
            if not layer.changeAttributeValue(fid, field, value):
                layer.rollBack()
                raise RuntimeError(f"Unable to update railway attribute {fid}")
        if geometry is not None and not layer.changeGeometry(fid, geometry):
            layer.rollBack()
            raise RuntimeError(f"Unable to reverse route {fid}")
    if not layer.commitChanges():
        raise RuntimeError(str(layer.commitErrors()))
    return sum(bool(changes) or geometry is not None for _, changes, geometry in planned)


def main() -> int:
    app = QgsApplication([], False)
    app.initQgis()
    records = {record["seq"]: record for record in read_rail_records()}
    try:
        updates = {
            "rail_routes": update_layer(OUTPUT / "铁路轨迹.gpkg", "rail_routes", records),
            "铁路行程轨迹": update_layer(OUTPUT / "全国足迹_数据.gpkg", "铁路行程轨迹", records),
        }
        times = {str(seq): {field: record.get(field, "") for field in ("date", "time", "note", "origin", "destination", "train")} for seq, record in records.items()}
        (ROOT / "web/data/route_times.json").write_text(json.dumps(times, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path = OUTPUT / "线路构建报告.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            for route in report["routes"]:
                route.update(records[int(route["seq"])])
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(updates, ensure_ascii=False))
        return 0
    finally:
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
