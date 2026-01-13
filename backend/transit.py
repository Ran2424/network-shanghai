# transit.py
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class EdgeStep:
    from_id: int
    to_id: int
    mode: str
    time_s: float
    line_name: Optional[str]


@dataclass
class RouteResult:
    cost: float
    path: List[int]
    edges: List[EdgeStep]
    v_start: int
    v_end: int


@dataclass
class StopNode:
    stop_id: int
    name: str
    lat: float
    lng: float


class TransitGraph:
    """
    Frequency-based public transit graph:
      - Nodes: stops (from stop shp)
      - Edges: consecutive stops along (BusName, Dir_Name) ordered by sequence
      - Access/Egress: walk from origin/destination to nearby stops
      - Transfers: walk between stops within radius (+ transfer penalty)
    """

    def __init__(
        self,
        walk_speed_kmh: float = 4.8,
        max_access_m: float = 1200.0,
        max_transfer_m: float = 800.0,
        transfer_penalty_s: float = 240.0,
        bus_speed_kmh: float = 18.0,
        subway_speed_kmh: float = 35.0,
        bus_wait_s: float = 300.0,     # expected wait time (frequency-based)
        subway_wait_s: float = 120.0,
        grid_cell_deg: float = 0.002,
        subway_transfer_wait_s: float = 90.0,
        bus_transfer_wait_s: float = 240.0,
        intermodal_penalty_s: float = 180.0,
    ) -> None:
        self.walk_speed_kmh = walk_speed_kmh
        self.max_access_m = max_access_m
        self.max_transfer_m = max_transfer_m
        self.transfer_penalty_s = transfer_penalty_s
        self.bus_speed_kmh = bus_speed_kmh
        self.subway_speed_kmh = subway_speed_kmh
        self.bus_wait_s = bus_wait_s
        self.subway_wait_s = subway_wait_s

        self.subway_transfer_wait_s = subway_transfer_wait_s     # 地铁换线期望等车
        self.bus_transfer_wait_s = bus_transfer_wait_s       # 公交换线期望等车
        self.intermodal_penalty_s = intermodal_penalty_s       # 公交<->地铁 额外惩罚


        self.nodes: List[StopNode] = []
        self.adj: List[List[Tuple[int, float, str, Optional[str]]]] = []  # (to_id, time_s, mode, line_name)

        # spatial index (grid in lat/lng degrees) for nearest/within queries
        self.grid_cell_deg = grid_cell_deg
        self.grid: Dict[str, List[int]] = {}

        # optional: for debugging / explaining
        self.stop_meta: List[Dict[str, str]] = []  # per node, store bus/dir etc if you want
        self.edge_paths: Dict[Tuple[int, int, str], List[List[float]]] = {}
        self.edge_distances: Dict[Tuple[int, int, str], float] = {}

    # --------------------------
    # Loading from shapefiles
    # --------------------------
    def build_from_shp(self, stop_shp: Path, line_shp: Optional[Path] = None) -> None:
        """
        stop_shp schema (as you showed):
          Station, BusName, Dir_Name, sequence, Lng, Lat, geometry(Point)
        """
        try:
            import geopandas as gpd
        except ImportError as exc:
            raise ImportError("geopandas is required to load transit shapefiles") from exc

        gdf = gpd.read_file(stop_shp)

        required = {"Station", "BusName", "Dir_Name", "sequence", "Lng", "Lat"}
        missing = required - set(gdf.columns)
        if missing:
            raise ValueError(f"Stop shp missing columns: {sorted(missing)}")

        # normalize & sort
        gdf = gdf.copy()
        gdf["sequence"] = gdf["sequence"].astype(int)

        # reset graph
        self.nodes.clear()
        self.adj.clear()
        self.grid.clear()
        self.stop_meta.clear()
        self.edge_paths.clear()
        self.edge_distances.clear()

        line_geoms: Dict[Tuple[str, str, str, str], Tuple[List[List[float]], float]] = {}
        if line_shp and line_shp.exists():
            line_geoms = self._load_line_geometries(line_shp)

        # Step 1: create stop nodes.
        # Important: same Station name can appear multiple times (different line/dir).
        # Here we treat each (BusName, Dir_Name, sequence) record as a distinct stop-node
        # to preserve ordered service patterns. Transfers are handled via proximity.
        stop_id = 0
        for _, row in gdf.iterrows():
            lat = float(row["Lat"])
            lng = float(row["Lng"])
            name = str(row["Station"])
            self.nodes.append(StopNode(stop_id=stop_id, name=name, lat=lat, lng=lng))
            self.adj.append([])
            self.stop_meta.append(
                {
                    "Station": str(row["Station"]),
                    "BusName": str(row["BusName"]),
                    "Dir_Name": str(row["Dir_Name"]),
                    "sequence": str(int(row["sequence"])),
                }
            )
            self._grid_add(stop_id, lat, lng)
            stop_id += 1

        # Step 2: add ride edges (consecutive stops per route-direction).
        # We re-use the same gdf ordering but need mapping from row index -> stop_id
        # because we created nodes in iteration order. easiest: keep row position.
        # Build per (BusName, Dir_Name) list of indices sorted by sequence.
        # Note: this assumes gdf iteration order == node id order (true above).
        gdf["_node_id"] = list(range(len(gdf)))

        grouped = gdf.sort_values(["BusName", "Dir_Name", "sequence"]).groupby(["BusName", "Dir_Name"])
        for (bus_name, dir_name), sub in grouped:
            ids = sub["_node_id"].tolist()
            if len(ids) < 2:
                continue
            mode = self._infer_mode(str(bus_name))
            speed_kmh = self.subway_speed_kmh if mode == "subway" else self.bus_speed_kmh
            wait_s = self.subway_wait_s if mode == "subway" else self.bus_wait_s

            for i in range(len(ids) - 1):
                a = ids[i]
                b = ids[i + 1]
                ta = self.nodes[a]
                tb = self.nodes[b]
                stop_a = str(sub.iloc[i]["Station"])
                stop_b = str(sub.iloc[i + 1]["Station"])
                line_key = self._line_key(str(bus_name), str(dir_name), stop_a, stop_b)
                line_info = line_geoms.get(line_key)
                if line_info:
                    geom_coords, line_len = line_info
                    d = float(line_len)
                    edge_key = (a, b, str(bus_name))
                    self.edge_paths[edge_key] = geom_coords
                    self.edge_distances[edge_key] = d
                else:
                    d = haversine_meters(ta.lat, ta.lng, tb.lat, tb.lng)
                ride_s = d / (speed_kmh * 1000 / 3600)

                # Ride edge: a -> b
                self.adj[a].append((b, ride_s, mode, str(bus_name)))

            # OPTIONAL: encode "boarding wait" once per route by adding wait_s on first edge of the route.
            # This is a simplification: in frequency-based routing, the wait is paid when you board a route.
            # To model this properly you'd need state (current route) or expand nodes; here we approximate:
            # pay wait on the first hop after any transfer/access by adding it to transfer/access edges instead.
            # So: we do NOT add wait here.

        # Step 3: add transfer edges by proximity (walk + penalty)
        self._add_transfer_edges()

    # --------------------------
    # Routing API
    # --------------------------
    def route_time(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> Optional[RouteResult]:
        """
        Returns a path over:
          [virtual_start] -> stop(s) -> ... -> stop(s) -> [virtual_end]
        For simplicity, we implement Dijkstra with ephemeral virtual nodes.
        """
        import heapq

        if not self.nodes:
            return None

        # Build access stops (origin -> stops)
        access = self._nearby_stops(start_lat, start_lng, self.max_access_m)
        egress = self._nearby_stops(end_lat, end_lng, self.max_access_m)

        if not access or not egress:
            return None

        # Dijkstra over N + 2 virtual nodes
        V_START = len(self.nodes)
        V_END = len(self.nodes) + 1
        n = len(self.nodes) + 2

        dist = [float("inf")] * n
        prev = [-1] * n
        prev_mode = [""] * n
        prev_time = [0.0] * n
        prev_line: List[Optional[str]] = [None] * n
        dist[V_START] = 0.0

        heap: List[Tuple[float, int]] = [(0.0, V_START)]

        def neighbors(u: int) -> List[Tuple[int, float, str, Optional[str]]]:
            # virtual start: connect to access stops with walk + expected wait (first boarding)
            if u == V_START:
                out = []
                for sid, walk_s in access:
                    # expected wait depends on the route you will board, but we don’t know yet.
                    # pragmatic: use a blended wait; you can refine later by stop_meta BusName.
                    out.append((sid, walk_s + self._expected_wait_for_stop(sid), "walk", None))
                return out

            # virtual end: none
            if u == V_END:
                return []

            # normal stop: ride edges + transfer edges + egress-to-end (walk)
            out = list(self.adj[u])

            # egress edges: stop -> end
            for sid, walk_s in egress:
                if sid == u:
                    out.append((V_END, walk_s, "walk", None))
            return out

        while heap:
            cost, u = heapq.heappop(heap)
            if cost != dist[u]:
                continue
            if u == V_END:
                break

            for v, w, mode, line_name in neighbors(u):
                nc = cost + w
                if nc < dist[v]:
                    dist[v] = nc
                    prev[v] = u
                    prev_mode[v] = mode
                    prev_time[v] = w
                    prev_line[v] = line_name
                    heapq.heappush(heap, (nc, v))

        if not math.isfinite(dist[V_END]):
            return None

        # reconstruct
        path: List[int] = []
        cur = V_END
        while cur != -1:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        edges: List[EdgeStep] = []
        for node_id in path[1:]:
            from_id = prev[node_id]
            edges.append(
                EdgeStep(
                    from_id=from_id,
                    to_id=node_id,
                    mode=prev_mode[node_id],
                    time_s=prev_time[node_id],
                    line_name=prev_line[node_id],
                )
            )
        return RouteResult(cost=dist[V_END], path=path, edges=edges, v_start=V_START, v_end=V_END)

    def path_coords_from_result(
        self,
        result: RouteResult,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[List[float]]:
        """
        Convert a RouteResult to [lat,lng] list including detailed line geometry.
        """
        coords: List[List[float]] = [[start[0], start[1]]]
        for edge in result.edges:
            edge_coords = self._edge_path_coords(edge, start, end)
            if not edge_coords:
                continue
            if coords[-1] == edge_coords[0]:
                coords.extend(edge_coords[1:])
            else:
                coords.extend(edge_coords)
        if coords[-1] != [end[0], end[1]]:
            coords.append([end[0], end[1]])
        return coords

    def segments_from_result(
        self,
        result: RouteResult,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[Dict[str, object]]:
        segments: List[Dict[str, object]] = []

        def node_coord(node_id: int) -> Tuple[float, float]:
            if node_id == result.v_start:
                return start
            if node_id == result.v_end:
                return end
            node = self.nodes[node_id]
            return (node.lat, node.lng)

        for edge in result.edges:
            from_coord = node_coord(edge.from_id)
            to_coord = node_coord(edge.to_id)
            edge_coords = self._edge_path_coords(edge, start, end)
            distance_m = self._edge_distance(edge, edge_coords)
            from_station = self.nodes[edge.from_id].name if 0 <= edge.from_id < len(self.nodes) else None
            to_station = self.nodes[edge.to_id].name if 0 <= edge.to_id < len(self.nodes) else None
            if (
                not segments
                or segments[-1]["type"] != edge.mode
                or segments[-1].get("line_name") != edge.line_name
            ):
                segments.append(
                    {
                        "type": edge.mode,
                        "distance_m": distance_m,
                        "time_s": edge.time_s,
                        "line_name": edge.line_name,
                        "from_station": from_station,
                        "to_station": to_station,
                        "path": edge_coords,
                    }
                )
            else:
                segments[-1]["distance_m"] += distance_m
                segments[-1]["time_s"] += edge.time_s
                if edge_coords:
                    if segments[-1]["path"] and segments[-1]["path"][-1] == edge_coords[0]:
                        segments[-1]["path"].extend(edge_coords[1:])
                    else:
                        segments[-1]["path"].extend(edge_coords)
                segments[-1]["to_station"] = to_station
        return segments

    def transfer_points_from_result(self, result: RouteResult) -> List[Dict[str, object]]:
        transfers: List[Dict[str, object]] = []
        last_service_mode: Optional[str] = None
        last_service_line: Optional[str] = None

        for edge in result.edges:
            if edge.mode not in {"bus", "subway"}:
                continue

            if last_service_mode is not None:
                if (edge.mode, edge.line_name) != (last_service_mode, last_service_line):
                    node_id = edge.from_id
                    if 0 <= node_id < len(self.nodes):
                        node = self.nodes[node_id]
                        transfers.append(
                            {
                                "station": node.name,
                                "lat": node.lat,
                                "lng": node.lng,
                                "from_mode": last_service_mode,
                                "to_mode": edge.mode,
                                "from_line": last_service_line,
                                "to_line": edge.line_name,
                            }
                        )

            last_service_mode = edge.mode
            last_service_line = edge.line_name

        return transfers

    def stop_path_from_result(self, result: RouteResult) -> List[str]:
        stops: List[str] = []
        for node_id in result.path:
            if 0 <= node_id < len(self.nodes):
                name = self.nodes[node_id].name
                if not stops or stops[-1] != name:
                    stops.append(name)
        return stops

    # --------------------------
    # Internal helpers
    # --------------------------
    def _infer_mode(self, bus_name: str) -> str:
        # tune this to your naming conventions
        if "地铁" in bus_name or "轨道" in bus_name:
            return "subway"
        return "bus"

    def _expected_wait_for_stop(self, stop_id: int) -> float:
        meta = self.stop_meta[stop_id]
        mode = self._infer_mode(meta.get("BusName", ""))
        return self.subway_wait_s if mode == "subway" else self.bus_wait_s

    def _stop_mode(self, stop_id: int) -> str:
        meta = self.stop_meta[stop_id]
        return self._infer_mode(meta.get("BusName", ""))

    def _grid_key(self, lat: float, lng: float) -> str:
        x = math.floor(lng / self.grid_cell_deg)
        y = math.floor(lat / self.grid_cell_deg)
        return f"{x}|{y}"

    def _grid_add(self, node_id: int, lat: float, lng: float) -> None:
        self.grid.setdefault(self._grid_key(lat, lng), []).append(node_id)

    def _nearby_stops(self, lat: float, lng: float, radius_m: float) -> List[Tuple[int, float]]:
        """
        return list of (stop_id, walk_time_s) within radius_m
        """
        # convert meters to approximate degrees search radius (rough)
        # 1 deg lat ~ 111km
        deg = max(0.0005, radius_m / 111_000.0)
        base_x = math.floor(lng / self.grid_cell_deg)
        base_y = math.floor(lat / self.grid_cell_deg)
        r = int(math.ceil(deg / self.grid_cell_deg)) + 1

        candidates: List[int] = []
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                key = f"{base_x + dx}|{base_y + dy}"
                candidates.extend(self.grid.get(key, []))

        res: List[Tuple[int, float]] = []
        walk_mps = self.walk_speed_kmh * 1000 / 3600
        for sid in set(candidates):
            s = self.nodes[sid]
            d = haversine_meters(lat, lng, s.lat, s.lng)
            if d <= radius_m:
                res.append((sid, d / walk_mps))
        res.sort(key=lambda x: x[1])
        return res[:20]  # cap to keep routing fast

    def _edge_path_coords(
        self,
        edge: EdgeStep,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> List[List[float]]:
        def node_coord(node_id: int) -> Tuple[float, float]:
            if node_id == -1:
                return start
            if node_id == len(self.nodes):
                return start
            if node_id == len(self.nodes) + 1:
                return end
            node = self.nodes[node_id]
            return (node.lat, node.lng)

        from_coord = node_coord(edge.from_id)
        to_coord = node_coord(edge.to_id)

        if edge.mode in {"bus", "subway"} and edge.line_name:
            key = (edge.from_id, edge.to_id, edge.line_name)
            raw = self.edge_paths.get(key)
            if raw:
                return self._normalize_path(raw, from_coord, to_coord)

        return [[from_coord[0], from_coord[1]], [to_coord[0], to_coord[1]]]

    def _edge_distance(self, edge: EdgeStep, coords: List[List[float]]) -> float:
        if edge.mode in {"bus", "subway"} and edge.line_name:
            key = (edge.from_id, edge.to_id, edge.line_name)
            dist = self.edge_distances.get(key)
            if dist is not None:
                return dist
        if len(coords) < 2:
            return 0.0
        total = 0.0
        for i in range(len(coords) - 1):
            total += haversine_meters(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        return total

    def _line_key(self, bus_name: str, dir_name: str, s_station: str, e_station: str) -> Tuple[str, str, str, str]:
        return (
            self._normalize_name(bus_name),
            self._normalize_name(dir_name),
            self._normalize_name(s_station),
            self._normalize_name(e_station),
        )

    def _normalize_name(self, value: str) -> str:
        return str(value).strip()

    def _load_line_geometries(
        self,
        line_shp: Path,
    ) -> Dict[Tuple[str, str, str, str], Tuple[List[List[float]], float]]:
        try:
            import geopandas as gpd
        except ImportError as exc:
            raise ImportError("geopandas is required to load transit shapefiles") from exc

        gdf = gpd.read_file(line_shp)
        required = {"BusName", "Dir_Name", "S_Station", "E_Station", "length"}
        missing = required - set(gdf.columns)
        if missing:
            raise ValueError(f"Line shp missing columns: {sorted(missing)}")

        geoms: Dict[Tuple[str, str, str, str], Tuple[List[List[float]], float]] = {}
        for _, row in gdf.iterrows():
            bus_name = str(row["BusName"])
            dir_name = str(row["Dir_Name"])
            s_station = str(row["S_Station"])
            e_station = str(row["E_Station"])
            key = self._line_key(bus_name, dir_name, s_station, e_station)

            geom = row.get("geometry")
            if geom is None:
                continue
            coords = self._geometry_to_coords(geom)
            if len(coords) < 2:
                continue

            length_val = row.get("length")
            length_m = 0.0
            try:
                length_m = float(length_val)
            except (TypeError, ValueError):
                length_m = 0.0
            if length_m <= 0:
                length_m = self._coords_length(coords)

            existing = geoms.get(key)
            if not existing or length_m > existing[1]:
                geoms[key] = (coords, length_m)

        return geoms

    def _geometry_to_coords(self, geom) -> List[List[float]]:
        if geom is None:
            return []
        if geom.geom_type == "LineString":
            return [[float(y), float(x)] for x, y in geom.coords]
        if geom.geom_type == "MultiLineString":
            coords: List[List[float]] = []
            for part in geom.geoms:
                part_coords = [[float(y), float(x)] for x, y in part.coords]
                if not coords:
                    coords.extend(part_coords)
                else:
                    if coords[-1] == part_coords[0]:
                        coords.extend(part_coords[1:])
                    else:
                        coords.extend(part_coords)
            return coords
        return []

    def _coords_length(self, coords: List[List[float]]) -> float:
        total = 0.0
        for i in range(len(coords) - 1):
            total += haversine_meters(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        return total

    def _normalize_path(
        self,
        coords: List[List[float]],
        from_coord: Tuple[float, float],
        to_coord: Tuple[float, float],
    ) -> List[List[float]]:
        if not coords:
            return [[from_coord[0], from_coord[1]], [to_coord[0], to_coord[1]]]
        start_dist = haversine_meters(coords[0][0], coords[0][1], from_coord[0], from_coord[1])
        end_dist = haversine_meters(coords[-1][0], coords[-1][1], from_coord[0], from_coord[1])
        path = coords if start_dist <= end_dist else list(reversed(coords))
        if haversine_meters(path[0][0], path[0][1], from_coord[0], from_coord[1]) > 30:
            path = [[from_coord[0], from_coord[1]]] + path
        if haversine_meters(path[-1][0], path[-1][1], to_coord[0], to_coord[1]) > 30:
            path = path + [[to_coord[0], to_coord[1]]]
        return path

    def _add_transfer_edges(self) -> None:
        """
        Add stop->stop transfer edges by proximity:
          time = walk_time + transfer_penalty
        """
        walk_mps = self.walk_speed_kmh * 1000 / 3600
        for i, si in enumerate(self.nodes):
            nearby = self._nearby_stops(si.lat, si.lng, self.max_transfer_m)
            for j, walk_s in nearby:
                if j == i:
                    continue
                mode_i = self._stop_mode(i)
                mode_j = self._stop_mode(j)
                if mode_i == "subway" and mode_j == "subway":
                    penalty = self.subway_transfer_wait_s
                elif mode_i == "bus" and mode_j == "bus":
                    penalty = self.bus_transfer_wait_s
                else:
                    penalty = self.intermodal_penalty_s
                # add transfer edge (both directions will be created when iterating j as well)
                self.adj[i].append((j, walk_s + penalty, "walk", None))


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    to_rad = math.radians
    d_lat = to_rad(lat2 - lat1)
    d_lng = to_rad(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(to_rad(lat1))
        * math.cos(to_rad(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c
