import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .geo import haversine_meters


@dataclass
class RouteResult:
    cost: float
    path: List[int]


class RoadGraph:
    def __init__(self, cell_size: float = 0.002) -> None:
        self.nodes: List[Tuple[float, float]] = []
        self.adjacency: List[List[Tuple[int, float, float]]] = []
        self.node_index: Dict[str, int] = {}
        self.grid: Dict[str, List[int]] = {}
        self.cell_size = cell_size

    def coord_key(self, lat: float, lng: float) -> str:
        return f"{lat:.6f},{lng:.6f}"

    def add_to_grid(self, node_id: int, lat: float, lng: float) -> None:
        x = math.floor(lng / self.cell_size)
        y = math.floor(lat / self.cell_size)
        key = f"{x}|{y}"
        self.grid.setdefault(key, []).append(node_id)

    def get_node_id(self, lat: float, lng: float) -> int:
        key = self.coord_key(lat, lng)
        node_id = self.node_index.get(key)
        if node_id is None:
            node_id = len(self.nodes)
            self.node_index[key] = node_id
            self.nodes.append((lat, lng))
            self.adjacency.append([])
            self.add_to_grid(node_id, lat, lng)
        return node_id

    def nearest_node(self, lat: float, lng: float) -> Optional[int]:
        base_x = math.floor(lng / self.cell_size)
        base_y = math.floor(lat / self.cell_size)
        best_id = None
        best_dist = float("inf")
        max_radius = 30

        for radius in range(max_radius + 1):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    key = f"{base_x + dx}|{base_y + dy}"
                    candidates = self.grid.get(key)
                    if not candidates:
                        continue
                    for node_id in candidates:
                        node = self.nodes[node_id]
                        d_lat = node[0] - lat
                        d_lng = node[1] - lng
                        dist = d_lat * d_lat + d_lng * d_lng
                        if dist < best_dist:
                            best_dist = dist
                            best_id = node_id
            if best_id is not None and radius > 0:
                max_cell = radius * self.cell_size
                if max_cell * max_cell > best_dist:
                    break
        return best_id

    def build_from_geojson(self, geojson: dict) -> None:
        self.nodes.clear()
        self.adjacency.clear()
        self.node_index.clear()
        self.grid.clear()

        for feature in geojson.get("features", []):
            geometry = feature.get("geometry") or {}
            if geometry.get("type") != "LineString":
                continue
            coords = geometry.get("coordinates") or []
            if len(coords) < 2:
                continue
            props = feature.get("properties") or {}
            speed = speed_for_feature(props)
            oneway = is_oneway(props.get("oneway"))

            for idx in range(len(coords) - 1):
                lng1, lat1 = coords[idx]
                lng2, lat2 = coords[idx + 1]
                from_id = self.get_node_id(lat1, lng1)
                to_id = self.get_node_id(lat2, lng2)
                distance = haversine_meters(lat1, lng1, lat2, lng2)
                time_cost = distance / (speed * 1000 / 3600)
                self.adjacency[from_id].append((to_id, distance, time_cost))
                if not oneway:
                    self.adjacency[to_id].append((from_id, distance, time_cost))

    def shortest_path(self, start_id: int, end_id: int, weight_index: int) -> Optional[RouteResult]:
        import heapq

        n = len(self.nodes)
        dist = [float("inf")] * n
        prev = [-1] * n
        dist[start_id] = 0.0
        heap: List[Tuple[float, int]] = [(0.0, start_id)]

        while heap:
            cost, node = heapq.heappop(heap)
            if cost != dist[node]:
                continue
            if node == end_id:
                break
            for next_id, distance, time_cost in self.adjacency[node]:
                weight = distance if weight_index == 1 else time_cost
                next_cost = cost + weight
                if next_cost < dist[next_id]:
                    dist[next_id] = next_cost
                    prev[next_id] = node
                    heapq.heappush(heap, (next_cost, next_id))

        if not math.isfinite(dist[end_id]):
            return None

        path: List[int] = []
        cursor = end_id
        while cursor != -1:
            path.append(cursor)
            cursor = prev[cursor]
        path.reverse()
        return RouteResult(cost=dist[end_id], path=path)

    def path_metrics(self, path: List[int]) -> Tuple[float, float]:
        total_distance = 0.0
        total_time = 0.0
        fallback_speed = 30.0
        for idx in range(len(path) - 1):
            from_id = path[idx]
            to_id = path[idx + 1]
            edge = None
            for candidate in self.adjacency[from_id]:
                if candidate[0] == to_id:
                    edge = candidate
                    break
            if edge:
                total_distance += edge[1]
                total_time += edge[2]
            else:
                lat1, lng1 = self.nodes[from_id]
                lat2, lng2 = self.nodes[to_id]
                distance = haversine_meters(lat1, lng1, lat2, lng2)
                total_distance += distance
                total_time += distance / (fallback_speed * 1000 / 3600)
        return total_distance, total_time


SPEED_BY_CLASS = {
    # 高等级快速通行道路
    "motorway": 65,        # 城市高架 / 快速路平均
    "motorway_link": 45,

    "trunk": 55,           # 城市主干快速路
    "trunk_link": 40,

    # 主干 / 次干
    "primary": 45,
    "primary_link": 35,

    "secondary": 35,
    "secondary_link": 30,

    # 支路
    "tertiary": 28,
    "tertiary_link": 25,

    # 居住 / 内部道路
    "residential": 22,
    "unclassified": 20,
    "living_street": 12,

    # 服务 / 内部
    "service": 15,
}


def speed_for_feature(props: dict) -> float:
    return SPEED_BY_CLASS.get(props.get("fclass"), 30)


def is_oneway(value) -> bool:
    if value is None:
        return False
    v = str(value).lower()
    if v in {"b", "0", "n", "no", "false"}:
        return False
    if v in {"f", "t", "1", "y", "yes", "true"}:
        return True
    return False
