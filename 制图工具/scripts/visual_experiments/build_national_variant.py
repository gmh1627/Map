"""Build a visual hierarchy prototype without changing the official national maps.

The source builder still owns the data preparation and layout.  This wrapper only
replaces the route, station, and visited-city emphasis before calling it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE = SCRIPT_DIR.parent / "travel_history" / "build_maps.py"
OUTPUT = SCRIPT_DIR.parents[2] / "地图输出" / "视觉优化试验" / "第二版_路线主角" / "全国"


def load_source():
    spec = importlib.util.spec_from_file_location("travel_history_builder", SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load source builder: {SOURCE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    bm = load_source()

    # Keep the established palette, but increase the route separation from the
    # administrative lines so the travel story survives a full-China view.
    def stronger_route_symbol(highspeed: bool):
        symbol = bm.QgsLineSymbol()
        if highspeed:
            outer = bm.QgsSimpleLineSymbolLayer(bm.QColor("#FFFDF7"), 3.10)
            inner = bm.QgsSimpleLineSymbolLayer(bm.QColor("#167F86"), 1.72)
        else:
            outer = bm.QgsSimpleLineSymbolLayer(bm.QColor("#182629"), 2.55)
            inner = bm.QgsSimpleLineSymbolLayer(bm.QColor("#FFFDF7"), 0.98)
        for line in (outer, inner):
            line.setWidthUnit(bm.Qgis.RenderUnit.Millimeters)
            line.setPenJoinStyle(bm.Qt.RoundJoin)
            line.setPenCapStyle(bm.Qt.RoundCap)
        symbol.changeSymbolLayer(0, outer)
        symbol.appendSymbolLayer(inner)
        return symbol

    def larger_stations(layer):
        symbol = bm.QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": "#FFFDF7",
                "outline_color": "#263335",
                "outline_width": "0.42",
                "outline_width_unit": "MM",
                "size": "2.10",
                "size_unit": "MM",
            }
        )
        layer.setRenderer(bm.QgsSingleSymbolRenderer(symbol))
        settings = bm.QgsPalLayerSettings()
        settings.enabled = True
        settings.fieldName = (
            "CASE WHEN \"name\" = '清河' THEN '' "
            "WHEN \"name\" = '北京丰台' THEN '丰台站' ELSE \"name\" END"
        )
        settings.isExpression = True
        settings.placement = bm.QgsPalLayerSettings.OrderedPositionsAroundPoint
        settings.priority = 10
        settings.dist = 0.72
        settings.distUnits = bm.Qgis.RenderUnit.Millimeters
        settings.setFormat(bm.text_format(7.8, "#172426", "华文楷体", 0.50))
        layer.setLabeling(bm.QgsVectorLayerSimpleLabeling(settings))
        layer.setLabelsEnabled(True)

    original_city_labels = bm.style_visited_city_labels
    original_all_provinces = bm.style_all_provinces

    def stronger_visited_provinces(layer, visited_names):
        original_all_provinces(layer, visited_names)
        renderer = layer.renderer()
        for category in renderer.categories():
            if str(category.value()) not in visited_names:
                continue
            symbol = category.symbol()
            symbol.setColor(bm.QColor("#B5D7E5"))
            symbol.setOpacity(0.94)
        layer.setRenderer(renderer)

    def stronger_city_labels(layer, required_only=False):
        original_city_labels(layer, required_only)
        labeling = layer.labeling()
        if labeling is None:
            return
        settings = labeling.settings()
        fmt = settings.format()
        fmt.setSize(7.5 if required_only else 6.9)
        fmt.setColor(bm.QColor("#183F5D" if required_only else "#244A67"))
        settings.setFormat(fmt)
        layer.setLabeling(bm.QgsVectorLayerSimpleLabeling(settings))
        if required_only:
            layer.setRenderer(
                bm.QgsSingleSymbolRenderer(
                    bm.QgsMarkerSymbol.createSimple(
                        {
                            "name": "circle",
                            "color": "#D85D6D",
                            "outline_color": "#FFFDF7",
                            "outline_width": "0.42",
                            "outline_width_unit": "MM",
                            "size": "2.0",
                            "size_unit": "MM",
                        }
                    )
                )
            )

    original_station_style = larger_stations

    def fewer_national_station_labels(layer):
        original_station_style(layer)
        settings = layer.labeling().settings()
        settings.fieldName = 'CASE WHEN "trips" >= 2 THEN "name" END'
        settings.isExpression = True
        settings.setFormat(bm.text_format(7.2, "#172426", "华文楷体", 0.46))
        layer.setLabeling(bm.QgsVectorLayerSimpleLabeling(settings))

    bm.route_symbol = stronger_route_symbol
    bm.style_stations = fewer_national_station_labels
    bm.style_visited_city_labels = stronger_city_labels
    bm.style_all_provinces = stronger_visited_provinces

    # The prototype is intentionally a single national frame.  Do not add a
    # local zoom box while the overall hierarchy is being evaluated.
    original_make_layout = bm.make_layout

    def single_frame_layout(
        project,
        name,
        title,
        subtitle,
        layers,
        output,
        rail_legend=False,
        inset_layers=None,
    ):
        return original_make_layout(
            project,
            name,
            title,
            subtitle,
            layers,
            output,
            rail_legend=rail_legend,
            inset_layers=None,
        )

    bm.make_layout = single_frame_layout

    OUTPUT.mkdir(parents=True, exist_ok=True)
    sys.argv = [str(SOURCE), "--output-dir", str(OUTPUT)]
    return bm.main()


if __name__ == "__main__":
    raise SystemExit(main())
