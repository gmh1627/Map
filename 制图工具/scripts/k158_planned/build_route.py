"""Build the K158 route on the local nationwide railway topology."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


RAILWAY_ROOT = Path(r"F:\Desktop\Blog\Map")
SCRIPT_DIR = Path(__file__).resolve().parent
COMMON_ROUTER = RAILWAY_ROOT / "制图工具" / "scripts" / "travel_history" / "build_routes.py"
TIMETABLE = SCRIPT_DIR / "timetable_2026-08-23.json"
OUTPUT_DIR = RAILWAY_ROOT / "地图输出" / "全国专题图" / "K158路线图"
OUTPUT_GPKG = OUTPUT_DIR / "K158线路.gpkg"
REPORT = OUTPUT_DIR / "线路构建报告.json"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_GPKG.unlink(missing_ok=True)
    REPORT.unlink(missing_ok=True)
    command = [
        sys.executable,
        str(COMMON_ROUTER),
        "--input-json",
        str(TIMETABLE),
        "--matches-json",
        str(TIMETABLE),
        "--output-dir",
        str(OUTPUT_DIR),
        "--output-gpkg",
        str(OUTPUT_GPKG),
        "--report-json",
        str(REPORT),
    ]
    return_code = subprocess.run(command, check=False).returncode
    if not OUTPUT_GPKG.exists() or not REPORT.exists():
        return return_code or 1
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    routes = report.get("routes", [])
    if len(routes) != 1 or routes[0].get("train") != "K158":
        return return_code or 1
    if len(routes[0].get("control_points", [])) != 29:
        return return_code or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
