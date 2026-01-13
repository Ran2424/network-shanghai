from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------
# Data paths
# ---------------------------
ROADS_PATH = BASE_DIR / "data" / "shanghai_roads.geojson"
PT_STOPS_SHP = BASE_DIR / "data" / "上海市公交_点.shp"
PT_LINES_SHP = BASE_DIR / "data" / "上海市公交线路.shp"

# ---------------------------
# Road (car)
# ---------------------------
# Degree-based grid size used for nearest-node search.
ROAD_GRID_CELL_DEG = 0.002
# Default driving speed by road class (km/h).
ROAD_SPEED_BY_CLASS_KMH = {
    # High-grade expressways
    "motorway": 65,
    "motorway_link": 45,

    "trunk": 55,
    "trunk_link": 40,

    # Arterials
    "primary": 45,
    "primary_link": 35,

    "secondary": 35,
    "secondary_link": 30,

    # Local roads
    "tertiary": 28,
    "tertiary_link": 25,

    "residential": 22,
    "unclassified": 20,
    "living_street": 12,

    # Service/internal
    "service": 15,
}
# Fallback driving speed (km/h) when road class is missing.
ROAD_FALLBACK_SPEED_KMH = 30.0

# ---------------------------
# Transit - walk
# ---------------------------
# Walking speed used for access/egress/transfer (km/h).
TRANSIT_WALK_SPEED_KMH = 4.8
# Max walking distance from origin/destination to stops (meters).
TRANSIT_MAX_ACCESS_M = 1200.0
# Max walking distance between stops for transfer links (meters).
TRANSIT_MAX_TRANSFER_M = 800.0
# Transfer penalty added on top of walk time (seconds).
TRANSIT_TRANSFER_PENALTY_S = 240.0
# Degree-based grid size for stop lookup.
TRANSIT_GRID_CELL_DEG = 0.002

# ---------------------------
# Transit - bus
# ---------------------------
# In-vehicle bus speed (km/h).
TRANSIT_BUS_SPEED_KMH = 18.0
# Expected wait time before boarding a bus (seconds).
TRANSIT_BUS_WAIT_S = 300.0
# Expected wait time when transferring between bus lines (seconds).
TRANSIT_BUS_TRANSFER_WAIT_S = 240.0

# ---------------------------
# Transit - subway
# ---------------------------
# In-vehicle subway speed (km/h).
TRANSIT_SUBWAY_SPEED_KMH = 35.0
# Expected wait time before boarding a subway (seconds).
TRANSIT_SUBWAY_WAIT_S = 120.0
# Expected wait time when transferring between subway lines (seconds).
TRANSIT_SUBWAY_TRANSFER_WAIT_S = 90.0

# ---------------------------
# Transit - intermodal
# ---------------------------
# Extra penalty for bus <-> subway transfers (seconds).
TRANSIT_INTERMODAL_PENALTY_S = 180.0
