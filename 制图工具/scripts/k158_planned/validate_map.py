"""Validate the K158 route project and published image."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.PyQt.QtGui import QImage
from qgis.core import (
    QgsApplication,
    QgsCoordinateTransform,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsProject,
)


ROOT = Path(r"F:\Desktop\Blog\Map")
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "地图输出" / "全国专题图" / "K158路线图"
TIMETABLE = SCRIPT_DIR / "timetable_2026-08-23.json"
PROJECT = OUTPUT_DIR / "K158路线图.qgz"
IMAGE = OUTPUT_DIR / "K158路线图.png"
EXPECTED_LAYERS = {
    "省级行政区": 35,
    "起点城市": 1,
    "终点城市": 1,
    "K158路线": 1,
    "K158经停站": 31,
    "经停站标签": 29,
    "起终点标签": 2,
}


def main() -> int:
    payload = json.loads(TIMETABLE.read_text(encoding="utf-8"))
    expected_names = [stop["name"] for stop in payload["stops"]]
    errors: list[str] = []
    counts: dict[str, int] = {}
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        if not PROJECT.exists() or not project.read(str(PROJECT)):
            raise RuntimeError(f"工程无法打开：{PROJECT}")

        invalid = [
            layer.name() for layer in project.mapLayers().values() if not layer.isValid()
        ]
        if invalid:
            errors.append("无效图层：" + "、".join(invalid))
        shapefiles = [
            layer.name()
            for layer in project.mapLayers().values()
            if layer.source().split("|", 1)[0].lower().endswith(".shp")
        ]
        if shapefiles:
            errors.append("仍引用 Shapefile：" + "、".join(shapefiles))

        for name, expected in EXPECTED_LAYERS.items():
            matches = project.mapLayersByName(name)
            if len(matches) != 1:
                errors.append(f"图层 {name} 数量异常：{len(matches)}")
                continue
            count = matches[0].featureCount()
            counts[name] = count
            if count != expected:
                errors.append(f"图层 {name} 要素数 {count}，预期 {expected}")

        station_layers = project.mapLayersByName("K158经停站")
        if station_layers:
            stations = sorted(station_layers[0].getFeatures(), key=lambda item: item["seq"])
            names = [feature["name"] for feature in stations]
            if names != expected_names:
                errors.append("经停站名称或顺序与 2026-08-23 时刻表不一致")
            if [feature["label"] for feature in stations] != expected_names:
                errors.append("站名标签不应包含序号或到发时间")
            roles = [feature["role"] for feature in stations]
            if roles != ["origin"] + ["stop"] * 29 + ["destination"]:
                errors.append("起点、经停站和终点角色不正确")

        route_layers = project.mapLayersByName("K158路线")
        if route_layers:
            route = next(route_layers[0].getFeatures(), None)
            if route is None or route.geometry().isNull() or route.geometry().isEmpty():
                errors.append("计划线路几何为空")
            elif route["train"] != "K158" or route["service"] != "conventional":
                errors.append("计划线路车次或列车类型不正确")

        layouts = project.layoutManager().printLayouts()
        if len(layouts) != 1 or layouts[0].name() != "K158路线图":
            errors.append("K158路线图布局缺失或重复")
        else:
            maps = [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemMap)]
            if len(maps) != 1 or maps[0].id() != "主图":
                errors.append("主图地图框缺失或重复")
            else:
                map_extent = maps[0].extent()
                for city_name in ("起点城市", "终点城市"):
                    city_layer = project.mapLayersByName(city_name)[0]
                    transform = QgsCoordinateTransform(
                        city_layer.crs(), project.crs(), project.transformContext()
                    )
                    city_extent = transform.transformBoundingBox(city_layer.extent())
                    if not (
                        map_extent.xMinimum() <= city_extent.xMinimum()
                        and map_extent.yMinimum() <= city_extent.yMinimum()
                        and map_extent.xMaximum() >= city_extent.xMaximum()
                        and map_extent.yMaximum() >= city_extent.yMaximum()
                    ):
                        errors.append(f"{city_name}轮廓未完整进入主图")
            text = "\n".join(
                item.text()
                for item in layouts[0].items()
                if isinstance(item, QgsLayoutItemLabel)
            )
            for required in (
                "K158路线图",
                "湛江—北京西｜09:54—次日22:48｜停靠31个车站｜里程 2725 km",
            ):
                if required not in text:
                    errors.append(f"布局文字缺少：{required}")
            if len(
                [item for item in layouts[0].items() if isinstance(item, QgsLayoutItemLabel)]
            ) != 2:
                errors.append("布局应只有标题和小标题，不应有图下说明文字")

        image = QImage(str(IMAGE))
        image_info = None
        if image.isNull():
            errors.append("PNG 缺失或无法读取")
        else:
            image_info = [image.width(), image.height(), IMAGE.stat().st_size]
            if image.width() < 2500 or image.height() < 3700:
                errors.append("PNG 分辨率低于 2500 x 3700")
            if IMAGE.stat().st_size > 3_000_000:
                errors.append("PNG 超过 3 MB")

        report = {
            "source_date": payload["source"]["travel_date"],
            "expected_stations": len(expected_names),
            "layers": counts,
            "image": image_info,
            "errors": errors,
        }
        (OUTPUT_DIR / "校验报告.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
