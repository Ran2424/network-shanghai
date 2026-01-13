from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from graph import RoadGraph, load_geojson


ROADS_PATH = Path(__file__).parent / "data" / "shanghai_roads.geojson"
SUBWAY_PATH = Path(__file__).parent / "data" / "shanghai_subway.geojson"
SUBWAY_SPEED_KMH = 60.0

app = FastAPI(title="Shanghai Road Network API")

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


graph = RoadGraph()
network_geojson: Optional[dict] = None


class Point(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    start: Point
    end: Point


class RoutePath(BaseModel):
    distance_m: float
    time_s: float
    path: List[List[float]]


class RouteResponse(BaseModel):
    distance: Optional[RoutePath]
    time: Optional[RoutePath]


@app.on_event("startup")
def load_graph() -> None:
    global network_geojson
    roads = load_geojson(ROADS_PATH)
    graph.build_from_geojson(roads)

    features = list(roads.get("features", []))
    if SUBWAY_PATH.exists():
        subway = load_geojson(SUBWAY_PATH)
        graph.add_from_geojson(subway, speed_override=SUBWAY_SPEED_KMH, oneway_override=False)
        features.extend(subway.get("features", []))
    network_geojson = {"type": "FeatureCollection", "features": features}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "nodes": len(graph.nodes)}


@app.get("/roads")
def roads() -> JSONResponse:
    if not network_geojson:
        raise HTTPException(status_code=404, detail="GeoJSON not found")
    return JSONResponse(network_geojson)


@app.post("/route", response_model=RouteResponse)
def route(payload: RouteRequest) -> RouteResponse:
    if not graph.nodes:
        raise HTTPException(status_code=503, detail="Graph not loaded")
    start_id = graph.nearest_node(payload.start.lat, payload.start.lng)
    end_id = graph.nearest_node(payload.end.lat, payload.end.lng)
    if start_id is None or end_id is None:
        raise HTTPException(status_code=404, detail="No nearby node found")

    distance_result = graph.shortest_path(start_id, end_id, 1)
    time_result = graph.shortest_path(start_id, end_id, 2)

    def pack(result):
        if result is None:
            return None
        distance_m, time_s = graph.path_metrics(result.path)
        return RoutePath(
            distance_m=distance_m,
            time_s=time_s,
            path=[[graph.nodes[i][0], graph.nodes[i][1]] for i in result.path],
        )

    return RouteResponse(distance=pack(distance_result), time=pack(time_result))
