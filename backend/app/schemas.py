from typing import List, Optional

from pydantic import BaseModel


class Point(BaseModel):
    lat: float
    lng: float


class RouteRequest(BaseModel):
    start: Point
    end: Point


class Segment(BaseModel):
    type: str
    distance_m: float
    time_s: float
    path: List[List[float]]
    line_name: Optional[str] = None
    from_station: Optional[str] = None
    to_station: Optional[str] = None


class TransferPoint(BaseModel):
    station: str
    lat: float
    lng: float
    from_mode: Optional[str] = None
    to_mode: Optional[str] = None
    from_line: Optional[str] = None
    to_line: Optional[str] = None


class RoutePath(BaseModel):
    distance_m: float
    time_s: float
    path: List[List[float]]
    geo_path: List[List[float]]
    segments: List[Segment]
    transfers: List[TransferPoint]
    stop_path: Optional[List[str]] = None


class RouteResponse(BaseModel):
    mode: str
    route: Optional[RoutePath]
