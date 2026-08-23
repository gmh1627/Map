"""Validate generated travel-history QGIS artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from qgis.PyQt.QtGui import QImage
from qgis.core import (
    QgsApplication,
    QgsGeometry,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemScaleBar,
    QgsProject,
    QgsPointXY,
)


DEFAULT_OUTPUT_DIR = Path(r"F:\Desktop\Railway\地图输出\全国专题图\全国足迹")
PARSED_SOURCE = Path(__file__).resolve().parent / "parsed_source.json"
EXPECTED_COUNTS = {
    "全国省级行政区": 35,
    "全国地级行政区": 477,
    "去过的城市": 87,
    "去过的省级行政区": 21,
    "铁路行程轨迹": 133,
    "记录车站": 129,
    "去过的城市标注": 87,
    "重点城市标注": 7,
    "铁路图省级行政区": 35,
}
EXPECTED_RAIL_SUBTITLE = (
    "133 段乘车记录｜普铁 44 次 · 高铁/动车 89 次｜总里程 54,760 km\n"
    "其中普铁 21,740 km，高铁/动车 33,020 km｜抵达 65 个城市的 129 座车站"
)
EXPECTED_NEW_ROUTES = {
    131: ("D901", "北京西", "广州", ["涿州东", "石家庄", "郑州东", "广州北"]),
    132: ("G5689", "广州", "湛江北", ["佛山", "茂名南"]),
    133: (
        "K158",
        "湛江",
        "北京西",
        [
            "遂溪", "廉江", "陆川", "玉林", "贵港", "柳州", "桂林北",
            "全州南", "永州", "衡阳", "长沙", "武昌", "花园", "广水",
            "信阳", "驻马店", "西平", "漯河", "许昌", "郑州", "新乡",
            "鹤壁", "安阳", "邯郸", "邢台", "石家庄", "定州", "保定",
            "高碑店",
        ],
    ),
}
EXPECTED_NETWORK_OVERRIDES = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    project_path = output_dir / "全国足迹.qgz"
    report_path = output_dir / "线路构建报告.json"
    image_paths = [
        output_dir / "去过的省市.png",
        output_dir / "铁路路线.png",
    ]

    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not project.read(str(project_path)):
            raise RuntimeError(f"Unable to read {project_path}")

        errors = []
        invalid_layers = [
            layer.name() for layer in project.mapLayers().values() if not layer.isValid()
        ]
        if invalid_layers:
            errors.append(f"Invalid layers: {', '.join(invalid_layers)}")

        counts = {}
        for name, expected in EXPECTED_COUNTS.items():
            layers = project.mapLayersByName(name)
            if not layers:
                errors.append(f"Missing layer: {name}")
                continue
            counts[name] = layers[0].featureCount()
            if counts[name] != expected:
                errors.append(f"{name}: expected {expected}, got {counts[name]}")

        parsed = json.loads(PARSED_SOURCE.read_text(encoding="utf-8"))
        expected_records = {
            int(record["seq"]): record for record in parsed["rail_records"]
        }
        route_layers = project.mapLayersByName("铁路行程轨迹")
        service_summary = {}
        if route_layers:
            route_features = {
                int(feature["seq"]): feature
                for feature in route_layers[0].getFeatures()
            }
            actual_services = {
                seq: str(feature["service"])
                for seq, feature in route_features.items()
            }
            service_mismatches = [
                {
                    "seq": seq,
                    "train": record["train"],
                    "expected": record["service_class"],
                    "actual": actual_services.get(seq),
                }
                for seq, record in expected_records.items()
                if actual_services.get(seq) != record["service_class"]
            ]
            if service_mismatches:
                errors.append(
                    "Route service classes differ from parsed records: "
                    + ", ".join(
                        f"{item['seq']} {item['train']}"
                        for item in service_mismatches
                    )
                )
            counts_by_service = Counter(actual_services.values())
            km_by_service = Counter()
            for seq, service in actual_services.items():
                if seq in expected_records:
                    km_by_service[service] += int(
                        expected_records[seq]["distance_km"]
                    )
            service_summary = {
                service: {
                    "trips": counts_by_service[service],
                    "table_km": km_by_service[service],
                }
                for service in ("conventional", "highspeed")
            }
            expected_summary = {
                "conventional": {"trips": 44, "table_km": 21740},
                "highspeed": {"trips": 89, "table_km": 33020},
            }
            if service_summary != expected_summary:
                errors.append(
                    f"Unexpected railway service totals: {service_summary}"
                )
            d901 = route_features.get(131)
            if d901 is None:
                errors.append("Missing D901 geometry")
            else:
                d901_geometry = d901.geometry()
                zhengzhou_east_distance = d901_geometry.distance(
                    QgsGeometry.fromPointXY(QgsPointXY(113.7732527, 34.7601939))
                )
                zhengzhou_distance = d901_geometry.distance(
                    QgsGeometry.fromPointXY(QgsPointXY(113.6536663, 34.7475076))
                )
                guangzhou_north_distance = d901_geometry.distance(
                    QgsGeometry.fromPointXY(QgsPointXY(113.1984329, 23.3794468))
                )
                if zhengzhou_east_distance > 0.01:
                    errors.append("D901 does not pass Zhengzhou East")
                if zhengzhou_distance < 0.05:
                    errors.append("D901 incorrectly follows the conventional line at Zhengzhou")
                if guangzhou_north_distance > 0.01:
                    errors.append("D901 does not pass Guangzhou North before entering Guangzhou")
        else:
            service_mismatches = []

        layouts = project.layoutManager().printLayouts()
        layout_names = sorted(layout.name() for layout in layouts)
        if layout_names != ["去过的省市", "铁路路线"]:
            errors.append(f"Unexpected layouts: {layout_names}")

        layout_maps = {}
        layout_map_layers = {}
        layout_geometry = {}
        for layout in layouts:
            if layout.name() == "铁路路线":
                label_texts = [
                    item.text()
                    for item in layout.items()
                    if isinstance(item, QgsLayoutItemLabel)
                ]
                if EXPECTED_RAIL_SUBTITLE not in label_texts:
                    errors.append("Railway subtitle totals are out of date")
            map_items = [
                item for item in layout.items() if isinstance(item, QgsLayoutItemMap)
            ]
            layout_maps[layout.name()] = len(map_items)
            if len(map_items) != 2:
                errors.append(
                    f"{layout.name()}: expected main map and South China Sea inset, "
                    f"got {len(map_items)} map items"
                )
            for item in map_items:
                item_name = item.id() or "未命名地图"
                layer_names = [layer.name() for layer in item.layers()]
                layout_map_layers[f"{layout.name()}/{item_name}"] = layer_names
                if (
                    layout.name() == "铁路路线"
                    and item_name != "南海诸岛插图"
                    and "去过的城市" in layer_names
                ):
                    errors.append("Railway main map still contains the visited-city layer")

            map_by_id = {item.id(): item for item in map_items}
            main_map = map_by_id.get("主图")
            inset = map_by_id.get("南海诸岛插图")
            scales = [
                item for item in layout.items() if isinstance(item, QgsLayoutItemScaleBar)
            ]
            south_labels = [
                item
                for item in layout.items()
                if isinstance(item, QgsLayoutItemLabel) and item.text() == "南海诸岛"
            ]
            if main_map and inset:
                main_pos = main_map.positionWithUnits()
                main_size = main_map.sizeWithUnits()
                inset_pos = inset.positionWithUnits()
                inset_size = inset.sizeWithUnits()
                main_right = main_pos.x() + main_size.width()
                main_bottom = main_pos.y() + main_size.height()
                inset_right = inset_pos.x() + inset_size.width()
                inset_bottom = inset_pos.y() + inset_size.height()
                layout_geometry[layout.name()] = {
                    "main": [
                        main_pos.x(),
                        main_pos.y(),
                        main_size.width(),
                        main_size.height(),
                    ],
                    "inset": [
                        inset_pos.x(),
                        inset_pos.y(),
                        inset_size.width(),
                        inset_size.height(),
                    ],
                    "scale_y": [scale.positionWithUnits().y() for scale in scales],
                }
                if abs(main_size.width() - 406) > 0.1 or abs(main_size.height() - 248) > 0.1:
                    errors.append(f"{layout.name()}: unexpected main map size")
                if abs(inset_size.width() - 68) > 0.1 or abs(inset_size.height() - 80) > 0.1:
                    errors.append(f"{layout.name()}: unexpected inset size")
                if abs(main_right - inset_right) > 0.1 or abs(main_bottom - inset_bottom) > 0.1:
                    errors.append(f"{layout.name()}: inset is not attached to lower-right corner")
                if not scales or any(
                    scale.positionWithUnits().y() < main_bottom for scale in scales
                ):
                    errors.append(f"{layout.name()}: scale bar is not outside main map")
                if len(south_labels) != 1:
                    errors.append(f"{layout.name()}: expected one South China Sea label")
                else:
                    label = south_labels[0]
                    label_pos = label.positionWithUnits()
                    label_size = label.sizeWithUnits()
                    if not (
                        label_pos.x() >= inset_pos.x()
                        and label_pos.y() >= inset_pos.y()
                        and label_pos.x() + label_size.width() <= inset_right + 0.1
                        and label_pos.y() + label_size.height() <= inset_bottom + 0.1
                    ):
                        errors.append(f"{layout.name()}: South China Sea label is outside inset")
                if layout.name() == "铁路路线":
                    legend_labels = [
                        item
                        for item in layout.items()
                        if isinstance(item, QgsLayoutItemLabel)
                        and item.text() in {"高铁/动车（含城际、市郊）", "普铁"}
                    ]
                    if len(legend_labels) != 2 or any(
                        item.positionWithUnits().y() < main_bottom
                        for item in legend_labels
                    ):
                        errors.append("Railway legend is not outside main map")

        image_info = {}
        for path in image_paths:
            image = QImage(str(path))
            if image.isNull():
                errors.append(f"Unreadable image: {path.name}")
                continue
            image_info[path.name] = [image.width(), image.height(), path.stat().st_size]
            if image.width() < 4000 or image.height() < 2500:
                errors.append(f"Image resolution too low: {path.name}")

        if not report_path.exists():
            errors.append(f"Missing route report: {report_path.name}")
            route_report = {"review_count": None, "max_station_snap_km": None, "routes": []}
        else:
            route_report = json.loads(report_path.read_text(encoding="utf-8"))
            routes_by_seq = {route["seq"]: route for route in route_report["routes"]}
            network_overrides = {
                int(route["seq"]): (
                    route["service_class"],
                    route["preferred_network"],
                )
                for route in route_report["routes"]
                if route["service_class"] != route["preferred_network"]
            }
            if network_overrides != EXPECTED_NETWORK_OVERRIDES:
                errors.append(
                    f"Unexpected service/network overrides: {network_overrides}"
                )
            for seq, (train, origin, destination, controls) in EXPECTED_NEW_ROUTES.items():
                route = routes_by_seq.get(seq)
                if route is None:
                    errors.append(f"Missing route {seq}: {train}")
                    continue
                actual = (
                    route["train"],
                    route["origin"],
                    route["destination"],
                    route.get("control_points", []),
                )
                if actual != (train, origin, destination, controls):
                    errors.append(f"Route {seq} does not match its expected itinerary")
                if route["status"] != "ok":
                    errors.append(f"Route {seq} requires review")

        project_crs = project.crs().authid()
        if not project_crs or project_crs.lower() == "unknown":
            project_crs = project.crs().toProj()

        summary = {
            "project": str(project_path),
            "project_crs": project_crs,
            "layers": counts,
            "layouts": layout_names,
            "layout_map_items": layout_maps,
            "layout_map_layers": layout_map_layers,
            "layout_geometry": layout_geometry,
            "images": image_info,
            "service_summary": service_summary,
            "service_mismatches": service_mismatches,
            "network_overrides": network_overrides if report_path.exists() else {},
            "route_review_count": route_report["review_count"],
            "max_station_snap_km": route_report["max_station_snap_km"],
            "review_routes": [
                {
                    "seq": route["seq"],
                    "train": route["train"],
                    "origin": route["origin"],
                    "destination": route["destination"],
                    "table_km": route["distance_km"],
                    "osm_route_km": route["route_km"],
                    "controls": route.get("control_points", []),
                }
                for route in route_report["routes"]
                if route["status"] == "review"
            ],
            "errors": errors,
        }
        (output_dir / "校验报告.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
