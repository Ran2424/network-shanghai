from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

ROADS_PATH = BASE_DIR / "data" / "shanghai_roads.geojson"
PT_STOPS_SHP = BASE_DIR / "data" / "上海市公交_点.shp"
PT_LINES_SHP = BASE_DIR / "data" / "上海市公交线路.shp"
