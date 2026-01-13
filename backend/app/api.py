from typing import List, Optional, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import ROADS_PATH, PT_STOPS_SHP, PT_LINES_SHP
from ..network.geo import haversine_meters, load_geojson
from ..network.road import RoadGraph
from ..network.transit import TransitGraph
from .schemas import (
    Point,
    RoutePath,
    RouteRequest,
    RouteResponse,
    Segment,
    TransferPoint,
)

app = FastAPI(title="Shanghai Multimodal Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

road_graph = RoadGraph()
transit_graph = TransitGraph()
network_geojson: Optional[dict] = None


@app.on_event("startup")
def load_graphs() -> None:
    global network_geojson

    # Load roads
    roads = load_geojson(ROADS_PATH)
    road_graph.build_from_geojson(roads)
    features = list(roads.get("features", []))

    # Load public transit (stops shp)
    if PT_STOPS_SHP.exists():
        transit_graph.build_from_shp(
            PT_STOPS_SHP,
            PT_LINES_SHP if PT_LINES_SHP.exists() else None,
        )

    network_geojson = {"type": "FeatureCollection", "features": features}


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "road_nodes": len(road_graph.nodes),
        "transit_stops": len(transit_graph.nodes),
    }


@app.get("/roads")
def roads() -> JSONResponse:
    if not network_geojson:
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return JSONResponse(network_geojson)


@app.post("/route", response_model=RouteResponse)
def route(
    payload: RouteRequest,
    mode: Literal["car", "transit"] = Query(default="car"),
) -> RouteResponse:
    if mode == "car":
        return _route_car(payload)
    if mode == "transit":
        return _route_transit(payload)
    raise HTTPException(status_code=400, detail="Unsupported mode")


def _route_car(payload: RouteRequest) -> RouteResponse:
    if not road_graph.nodes:
        raise HTTPException(status_code=503, detail="Road graph not loaded")

    start_id = road_graph.nearest_node(payload.start.lat, payload.start.lng)
    end_id = road_graph.nearest_node(payload.end.lat, payload.end.lng)
    if start_id is None or end_id is None:
        raise HTTPException(status_code=404, detail="No nearby road node found")

    time_result = road_graph.shortest_path(start_id, end_id, 2)

    if time_result is None:
        raise HTTPException(status_code=404, detail="No car route found")

    distance_m, time_s = road_graph.path_metrics(time_result.path)
    path_coords = [[road_graph.nodes[i][0], road_graph.nodes[i][1]] for i in time_result.path]
    segments: List[Segment] = [
        {
            "type": "car",
            "distance_m": distance_m,
            "time_s": time_s,
            "path": path_coords,
        }
    ]
    packed = RoutePath(
        distance_m=distance_m,
        time_s=time_s,
        path=path_coords,
        geo_path=path_coords,
        segments=segments,
        transfers=[],
    )

    return RouteResponse(mode="car", route=packed)


def _route_transit(payload: RouteRequest) -> RouteResponse:
    if not transit_graph.nodes:
        raise HTTPException(status_code=503, detail="Transit graph not loaded (missing stops shp?)")

    # time-optimal for transit
    result = transit_graph.route_time(
        payload.start.lat, payload.start.lng, payload.end.lat, payload.end.lng
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No transit route found")

    coords = transit_graph.path_coords_from_result(
        result,
        start=(payload.start.lat, payload.start.lng),
        end=(payload.end.lat, payload.end.lng),
    )

    distance_m = 0.0
    for i in range(len(coords) - 1):
        lat1, lng1 = coords[i]
        lat2, lng2 = coords[i + 1]
        distance_m += haversine_meters(lat1, lng1, lat2, lng2)

    segments = transit_graph.segments_from_result(
        result,
        start=(payload.start.lat, payload.start.lng),
        end=(payload.end.lat, payload.end.lng),
    )
    transfers = transit_graph.transfer_points_from_result(result)
    packed = RoutePath(
        distance_m=distance_m,
        time_s=result.cost,
        path=coords,
        geo_path=coords,
        segments=segments,
        transfers=transfers,
        stop_path=transit_graph.stop_path_from_result(result),
    )
    return RouteResponse(mode="transit", route=packed)
