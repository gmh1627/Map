"""Validate that generated QGIS projects open at a useful default extent."""

from __future__ import annotations

import json
from pathlib import Path

from qgis.core import QgsApplication, QgsProject


ROOT = Path(r"F:\Desktop\Blog\Map")
OUTPUT = ROOT / "地图输出"
PROJECTS = [
    OUTPUT / "全国专题图" / "全国足迹" / "全国足迹.qgz",
    OUTPUT / "全国专题图" / "航线图" / "航线图.qgz",
    OUTPUT / "全国专题图" / "上大学前去过的城市" / "上大学前去过的城市.qgz",
    OUTPUT / "全国专题图" / "K158路线图" / "K158路线图.qgz",
    OUTPUT / "全国专题图" / "铁路枢纽局部图" / "北京及周边铁路行迹_客运铁路底图.qgz",
    OUTPUT / "区域线路图" / "山陕漫游" / "山陕漫游.qgz",
    OUTPUT / "区域线路图" / "走河西" / "走河西.qgz",
    OUTPUT / "区域线路图" / "甘肃行旅" / "甘肃行旅.qgz",
]
HIDDEN_DIRECTION_LAYERS = {"航向箭头", "公路方向", "公路行程"}
VISIBLE_DIRECTION_LAYERS = {"航线图.qgz": {"航向箭头"}}


def main() -> int:
    regional_report = OUTPUT / "区域线路图" / "构建报告.json"
    if regional_report.exists():
        PROJECTS.extend(Path(record["project"]) for record in json.loads(regional_report.read_text(encoding="utf-8")))
    errors: list[str] = []
    records = []
    app = QgsApplication([], False)
    app.initQgis()
    try:
        project = QgsProject.instance()
        for path in PROJECTS:
            project.clear()
            item_errors = []
            if not path.exists() or not project.read(str(path)):
                item_errors.append("工程不存在或无法读取")
                records.append({"project": str(path), "errors": item_errors})
                errors.extend(f"{path.name}: {value}" for value in item_errors)
                continue
            invalid = [layer.name() for layer in project.mapLayers().values() if not layer.isValid()]
            if invalid:
                item_errors.append("无效图层：" + "、".join(invalid))
            shapefile_layers = sorted(
                layer.name()
                for layer in project.mapLayers().values()
                if layer.source().split("|", 1)[0].lower().endswith(".shp")
            )
            if shapefile_layers:
                item_errors.append("仍引用 Shapefile：" + "、".join(shapefile_layers))
            if "区域线路图" in path.parts:
                forbidden = sorted(
                    {"背景铁路", "背景铁路复线", "OSM 淡色底图", "OpenStreetMap"}
                    & {layer.name() for layer in project.mapLayers().values()}
                )
                if forbidden:
                    item_errors.append("区域图仍含禁用底图或未去过的铁路：" + "、".join(forbidden))
            extent = project.viewSettings().defaultViewExtent()
            rectangle = extent
            if rectangle.isNull() or rectangle.isEmpty() or rectangle.width() <= 0 or rectangle.height() <= 0:
                item_errors.append("未保存有效的默认主画布范围")
            required_visible = VISIBLE_DIRECTION_LAYERS.get(path.name, set())
            visible_directions = []
            found_required = set()
            for layer in project.mapLayers().values():
                if layer.name() in HIDDEN_DIRECTION_LAYERS:
                    node = project.layerTreeRoot().findLayer(layer.id())
                    is_visible = bool(node and node.itemVisibilityChecked())
                    if layer.name() in required_visible:
                        found_required.add(layer.name())
                        if not is_visible:
                            item_errors.append("要求显示的方向图层不可见：" + layer.name())
                    elif is_visible:
                        visible_directions.append(layer.name())
            missing_required = required_visible - found_required
            if missing_required:
                item_errors.append("缺少要求显示的方向图层：" + "、".join(sorted(missing_required)))
            if visible_directions:
                item_errors.append("方向图层仍可见：" + "、".join(visible_directions))
            if not project.layoutManager().printLayouts():
                item_errors.append("没有打印布局")
            records.append({
                "project": str(path),
                "layer_count": len(project.mapLayers()),
                "default_extent": [rectangle.xMinimum(), rectangle.yMinimum(), rectangle.xMaximum(), rectangle.yMaximum()],
                "errors": item_errors,
            })
            errors.extend(f"{path.name}: {value}" for value in item_errors)
        report = {"projects": records, "errors": errors}
        (OUTPUT / "工程可打开性校验.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    raise SystemExit(main())
