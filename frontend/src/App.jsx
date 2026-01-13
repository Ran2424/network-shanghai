import { useEffect, useRef, useState } from "react";
import L from "leaflet";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const DEFAULT_STATUS = "点击地图选择起点与终点";
const TYPE_LABELS = {
  walk: "步行",
  bus: "公交",
  subway: "地铁",
  car: "开车",
};
const TYPE_COLORS = {
  walk: "#94a3b8",
  bus: "#2563eb",
  subway: "#10b981",
  car: "#ef4444",
};

function formatDistance(meters) {
  if (!Number.isFinite(meters)) return "-";
  if (meters < 1000) return `${meters.toFixed(0)} 米`;
  return `${(meters / 1000).toFixed(2)} 公里`;
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "-";
  const mins = seconds / 60;
  if (mins < 60) return `${mins.toFixed(1)} 分钟`;
  const hours = Math.floor(mins / 60);
  const remaining = mins % 60;
  return `${hours} 小时 ${remaining.toFixed(0)} 分钟`;
}

export default function App() {
  const mapRef = useRef(null);
  const mapContainerRef = useRef(null);
  const overlayRef = useRef(null);
  const carMapContainerRef = useRef(null);
  const transitMapContainerRef = useRef(null);
  const carMapRef = useRef(null);
  const transitMapRef = useRef(null);
  const carPolylineRefs = useRef([]);
  const transitPolylineRefs = useRef([]);
  const startMarkerRef = useRef(null);
  const endMarkerRef = useRef(null);
  const carLineRefs = useRef([]);
  const transitLineRefs = useRef([]);
  const startPointRef = useRef(null);
  const endPointRef = useRef(null);

  const [status, setStatus] = useState("加载路网中，请稍候…");
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [carResult, setCarResult] = useState({
    distance: "-",
    time: "-",
    segments: [],
    transfers: [],
  });
  const [transitResult, setTransitResult] = useState({
    distance: "-",
    time: "-",
    segments: [],
    transfers: [],
  });
  const [carSegments, setCarSegments] = useState([]);
  const [transitSegments, setTransitSegments] = useState([]);
  const [transitTransfers, setTransitTransfers] = useState([]);
  const [carRoutePath, setCarRoutePath] = useState([]);
  const [transitRoutePath, setTransitRoutePath] = useState([]);
  const transferMarkersRef = useRef([]);
  const [showRouteCards, setShowRouteCards] = useState(false);
  const [showCarRoute, setShowCarRoute] = useState(false);
  const [showTransitRoute, setShowTransitRoute] = useState(true);
  const [carCardPos, setCarCardPos] = useState({ x: 50, y: 24 });
  const [transitCardPos, setTransitCardPos] = useState({ x: 50, y: 280 });
  const carCardPosRef = useRef(carCardPos);
  const transitCardPosRef = useRef(transitCardPos);

  const dragStateRef = useRef({
    active: false,
    type: null,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  });

  const handleDragStart = (event, type) => {
    event.preventDefault();
    event.stopPropagation();
    if (mapRef.current) {
      mapRef.current.dragging.disable();
    }
    const point = "touches" in event ? event.touches[0] : event;
    dragStateRef.current = {
      active: true,
      type,
      startX: point.clientX,
      startY: point.clientY,
      originX:
        type === "car" ? carCardPosRef.current.x : transitCardPosRef.current.x,
      originY:
        type === "car" ? carCardPosRef.current.y : transitCardPosRef.current.y,
    };
  };

  useEffect(() => {
    carCardPosRef.current = carCardPos;
  }, [carCardPos]);

  useEffect(() => {
    transitCardPosRef.current = transitCardPos;
  }, [transitCardPos]);

  useEffect(() => {
    const handleMove = (event) => {
      if (!dragStateRef.current.active) return;
      const point = "touches" in event ? event.touches[0] : event;
      const dx = point.clientX - dragStateRef.current.startX;
      const dy = point.clientY - dragStateRef.current.startY;
      const nextX = dragStateRef.current.originX + dx;
      const nextY = dragStateRef.current.originY + dy;
      if (dragStateRef.current.type === "car") {
        setCarCardPos({ x: nextX, y: nextY });
      } else if (dragStateRef.current.type === "transit") {
        setTransitCardPos({ x: nextX, y: nextY });
      }
    };

    const handleEnd = () => {
      dragStateRef.current.active = false;
      if (mapRef.current) {
        mapRef.current.dragging.enable();
      }
    };

    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleEnd);
    window.addEventListener("touchmove", handleMove, { passive: false });
    window.addEventListener("touchend", handleEnd);

    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleEnd);
      window.removeEventListener("touchmove", handleMove);
      window.removeEventListener("touchend", handleEnd);
    };
  }, []);

  const clearSelection = () => {
    if (startMarkerRef.current) startMarkerRef.current.remove();
    if (endMarkerRef.current) endMarkerRef.current.remove();
    carLineRefs.current.forEach((line) => line.remove());
    transitLineRefs.current.forEach((line) => line.remove());
    startMarkerRef.current = null;
    endMarkerRef.current = null;
    carLineRefs.current = [];
    transitLineRefs.current = [];
    startPointRef.current = null;
    endPointRef.current = null;
    setStartPoint(null);
    setEndPoint(null);
    setCarResult({ distance: "-", time: "-", segments: [], transfers: [] });
    setTransitResult({ distance: "-", time: "-", segments: [], transfers: [] });
    setCarSegments([]);
    setTransitSegments([]);
    setTransitTransfers([]);
    setCarRoutePath([]);
    setTransitRoutePath([]);
    setShowRouteCards(false);
    setShowCarRoute(false);
    setShowTransitRoute(true);
    setStatus(DEFAULT_STATUS);
    carPolylineRefs.current.forEach((line) => line.remove());
    transitPolylineRefs.current.forEach((line) => line.remove());
    carPolylineRefs.current = [];
    transitPolylineRefs.current = [];
    transferMarkersRef.current.forEach((marker) => marker.remove());
    transferMarkersRef.current = [];
  };

  useEffect(() => {
    const map = L.map(mapContainerRef.current, { preferCanvas: true }).setView(
      [31.2304, 121.4737],
      11
    );
    mapRef.current = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);

    const loadData = async () => {
      try {
        const response = await fetch(`${API_BASE}/roads`);
        const data = await response.json();
        const roadLayer = L.geoJSON(data, {
          style: {
            color: "#64748b",
            weight: 1,
            opacity: 0.45,
          },
        }).addTo(map);
        if (roadLayer.getBounds().isValid()) {
          map.fitBounds(roadLayer.getBounds(), { padding: [24, 24] });
        }
        setStatus(DEFAULT_STATUS);
      } catch (error) {
        console.error(error);
        setStatus("路网加载失败，请检查后端服务");
      }
    };

    loadData();

    const onClick = (event) => {
      if (!startPointRef.current) {
        const { lat, lng } = event.latlng;
        const marker = L.marker([lat, lng], { title: "起点" }).addTo(map);
        marker.bindPopup("起点").openPopup();
        startMarkerRef.current = marker;
        startPointRef.current = { lat, lng };
        setStartPoint({ lat, lng });
        return;
      }

      if (!endPointRef.current) {
        const { lat, lng } = event.latlng;
        const marker = L.marker([lat, lng], { title: "终点" }).addTo(map);
        marker.bindPopup("终点").openPopup();
        endMarkerRef.current = marker;
        endPointRef.current = { lat, lng };
        setEndPoint({ lat, lng });
      }
    };

    map.on("click", onClick);

    return () => {
      map.off("click", onClick);
      map.remove();
    };
  }, []);

  useEffect(() => {
    const requestRoute = async () => {
      if (!startPoint || !endPoint) return;
      setStatus("正在计算路径…");
      setShowRouteCards(false);
      carLineRefs.current.forEach((line) => line.remove());
      transitLineRefs.current.forEach((line) => line.remove());
      carLineRefs.current = [];
      transitLineRefs.current = [];
      setCarSegments([]);
      setTransitSegments([]);
      transferMarkersRef.current.forEach((marker) => marker.remove());
      transferMarkersRef.current = [];
      try {
        const payload = JSON.stringify({ start: startPoint, end: endPoint });
        const request = (mode) =>
          fetch(`${API_BASE}/route?mode=${mode}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: payload,
          });

        const [carResponse, transitResponse] = await Promise.allSettled([
          request("car"),
          request("transit"),
        ]);

        const handleRoute = (
          mode,
          response,
          setResult,
          setSegments,
          setTransfers,
          setRoutePath
        ) => {
          if (!response || response.status !== "fulfilled") {
            setResult({ distance: "不可用", time: "不可用", segments: [], transfers: [] });
            setSegments([]);
            setTransfers([]);
            setRoutePath([]);
            return false;
          }
          if (!response.value.ok) {
            setResult({ distance: "未找到路线", time: "未找到路线", segments: [], transfers: [] });
            setSegments([]);
            setTransfers([]);
            setRoutePath([]);
            return false;
          }
          return response.value.json().then((data) => {
            if (!data.route) {
              setResult({ distance: "未找到路线", time: "未找到路线", segments: [], transfers: [] });
              setSegments([]);
              setTransfers([]);
              setRoutePath([]);
              return false;
            }
            const routePath = data.route.geo_path || data.route.path || [];
            setResult({
              distance: formatDistance(data.route.distance_m),
              time: formatTime(data.route.time_s),
              segments: data.route.segments || [],
              transfers: data.route.transfers || [],
            });
            const segments = data.route.segments || [];
            setSegments(segments);
            setTransfers(data.route.transfers || []);
            setRoutePath(routePath);
            return true;
          });
        };

        const carPromise = handleRoute(
          "car",
          carResponse,
          setCarResult,
          setCarSegments,
          () => {},
          setCarRoutePath
        );
        const transitPromise = handleRoute(
          "transit",
          transitResponse,
          setTransitResult,
          setTransitSegments,
          setTransitTransfers,
          setTransitRoutePath
        );

        const results = await Promise.all([carPromise, transitPromise]);
        const hasAny = results.some(Boolean);
        setStatus(
          hasAny ? "完成，可继续清除并重新选择" : "路径计算失败，请检查后端服务"
        );
        setShowRouteCards(true);
      } catch (error) {
        console.error(error);
        setStatus("路径计算失败，请检查后端服务");
        setShowRouteCards(true);
      }
    };

    requestRoute();
  }, [startPoint, endPoint]);

  useEffect(() => {
    carLineRefs.current.forEach((line) => line.remove());
    carLineRefs.current = [];
    if (!showRouteCards || !showCarRoute) return;
    if (!mapRef.current) return;
    if (carSegments.length === 0 && carRoutePath.length > 1) {
      const line = L.polyline(carRoutePath, {
        color: TYPE_COLORS.car,
        weight: 5,
        opacity: 0.9,
      }).addTo(mapRef.current);
      carLineRefs.current.push(line);
      return;
    }
    carSegments.forEach((segment) => {
      const color = TYPE_COLORS[segment.type] || "#64748b";
      const line = L.polyline(segment.path, {
        color,
        weight: 5,
        opacity: 0.9,
        dashArray: segment.type === "walk" ? "4 6" : null,
      }).addTo(mapRef.current);
      carLineRefs.current.push(line);
    });
  }, [showRouteCards, showCarRoute, carSegments, carRoutePath]);

  useEffect(() => {
    if (!showRouteCards || !showCarRoute) return;
    if (!carMapRef.current && carMapContainerRef.current) {
      carMapRef.current = L.map(carMapContainerRef.current, {
        zoomControl: false,
        attributionControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
        tap: false,
        touchZoom: false,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
      }).addTo(carMapRef.current);
    }

    carPolylineRefs.current.forEach((line) => line.remove());
    carPolylineRefs.current = [];
    if (carSegments.length === 0 && carRoutePath.length > 1) {
      const line = L.polyline(carRoutePath, {
        color: TYPE_COLORS.car,
        weight: 3,
        opacity: 0.9,
      }).addTo(carMapRef.current);
      carPolylineRefs.current.push(line);
    } else {
      carSegments.forEach((segment) => {
        const color = TYPE_COLORS[segment.type] || "#64748b";
        const line = L.polyline(segment.path, {
          color,
          weight: 3,
          opacity: 0.9,
          dashArray: segment.type === "walk" ? "4 6" : null,
        }).addTo(carMapRef.current);
        carPolylineRefs.current.push(line);
      });
    }
    if (carPolylineRefs.current.length > 0) {
      const group = L.featureGroup(carPolylineRefs.current);
      carMapRef.current.fitBounds(group.getBounds(), { padding: [6, 6] });
    }
    requestAnimationFrame(() => {
      carMapRef.current.invalidateSize();
    });
  }, [showRouteCards, showCarRoute, carSegments, carRoutePath]);

  useEffect(() => {
    transitLineRefs.current.forEach((line) => line.remove());
    transitLineRefs.current = [];
    if (!showRouteCards || !showTransitRoute) return;
    if (!mapRef.current) return;
    if (transitSegments.length === 0 && transitRoutePath.length > 1) {
      const line = L.polyline(transitRoutePath, {
        color: TYPE_COLORS.bus,
        weight: 5,
        opacity: 0.9,
      }).addTo(mapRef.current);
      transitLineRefs.current.push(line);
      return;
    }
    transitSegments.forEach((segment) => {
      const color = TYPE_COLORS[segment.type] || "#64748b";
      const line = L.polyline(segment.path, {
        color,
        weight: 5,
        opacity: 0.9,
        dashArray: segment.type === "walk" ? "4 6" : null,
      }).addTo(mapRef.current);
      transitLineRefs.current.push(line);
    });
  }, [showRouteCards, showTransitRoute, transitSegments, transitRoutePath]);

  useEffect(() => {
    if (!showRouteCards || !showTransitRoute) return;
    if (!transitMapRef.current && transitMapContainerRef.current) {
      transitMapRef.current = L.map(transitMapContainerRef.current, {
        zoomControl: false,
        attributionControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
        tap: false,
        touchZoom: false,
      });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18,
      }).addTo(transitMapRef.current);
    }

    transitPolylineRefs.current.forEach((line) => line.remove());
    transitPolylineRefs.current = [];
    if (transitSegments.length === 0 && transitRoutePath.length > 1) {
      const line = L.polyline(transitRoutePath, {
        color: TYPE_COLORS.bus,
        weight: 3,
        opacity: 0.9,
      }).addTo(transitMapRef.current);
      transitPolylineRefs.current.push(line);
    } else {
      transitSegments.forEach((segment) => {
        const color = TYPE_COLORS[segment.type] || "#64748b";
        const line = L.polyline(segment.path, {
          color,
          weight: 3,
          opacity: 0.9,
          dashArray: segment.type === "walk" ? "4 6" : null,
        }).addTo(transitMapRef.current);
        transitPolylineRefs.current.push(line);
      });
    }
    if (transitPolylineRefs.current.length > 0) {
      const group = L.featureGroup(transitPolylineRefs.current);
      transitMapRef.current.fitBounds(group.getBounds(), { padding: [6, 6] });
    }
    requestAnimationFrame(() => {
      transitMapRef.current.invalidateSize();
    });
  }, [showRouteCards, showTransitRoute, transitSegments, transitRoutePath]);

  useEffect(() => {
    if (showRouteCards) return;
    carPolylineRefs.current.forEach((line) => line.remove());
    transitPolylineRefs.current.forEach((line) => line.remove());
    carPolylineRefs.current = [];
    transitPolylineRefs.current = [];
    if (carMapRef.current) {
      carMapRef.current.remove();
      carMapRef.current = null;
    }
    if (transitMapRef.current) {
      transitMapRef.current.remove();
      transitMapRef.current = null;
    }
  }, [showRouteCards]);

  useEffect(() => {
    transferMarkersRef.current.forEach((marker) => marker.remove());
    transferMarkersRef.current = [];
    if (!showRouteCards || !showTransitRoute || transitTransfers.length === 0 || !mapRef.current) return;

    transitTransfers.forEach((transfer) => {
      const marker = L.circleMarker([transfer.lat, transfer.lng], {
        radius: 7,
        color: "#f59e0b",
        weight: 2,
        fillColor: "#fbbf24",
        fillOpacity: 0.9,
      }).addTo(mapRef.current);
      marker.bindTooltip(`换乘：${transfer.station}`, { direction: "top" });
      transferMarkersRef.current.push(marker);
    });
  }, [showRouteCards, transitTransfers]);

  const formatPoint = (point) => {
    if (!point) return "未选择";
    return `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`;
  };

  const summarizeSegments = (segments) => {
    if (!segments || segments.length === 0) return [];
    return segments.map((segment) => {
      const label = TYPE_LABELS[segment.type] || segment.type;
      let detail = "";
      if (segment.type === "bus" || segment.type === "subway") {
        if (segment.line_name) {
          detail = segment.line_name;
        } else if (segment.from_station && segment.to_station) {
          detail = `${segment.from_station}→${segment.to_station}`;
        }
      }
      const prefix = detail ? `${label}·${detail}` : label;
      return {
        label: prefix,
        distance: formatDistance(segment.distance_m),
        time: formatTime(segment.time_s),
      };
    });
  };

  const carSummary = summarizeSegments(carResult.segments);
  const transitSummary = summarizeSegments(transitResult.segments);

  return (
    <div className="min-h-screen grid lg:grid-cols-[minmax(280px,360px)_1fr]">
      <aside className="relative z-10 flex min-h-screen flex-col gap-5 border-b border-slate-200/70 bg-white/90 p-7 shadow-panel backdrop-blur lg:border-b-0 lg:border-r">
        <div className="space-y-2">
          <h1 className="font-serif text-2xl tracking-wide text-ink">上海市路网最短路径</h1>
          <p className="text-sm text-muted leading-relaxed">
            在地图上依次点击起点与终点，计算开车出行与公交出行的路线。
          </p>
        </div>

        <div className="rounded-xl border border-teal-100 bg-teal-50 px-4 py-3 text-sm font-semibold text-teal-700">
          {status}
        </div>

        <div className="grid gap-3">
          <div className="rounded-xl border border-slate-200/70 bg-white px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.2em] text-muted">起点</div>
            <div className="mt-2 text-sm font-semibold text-ink">
              {formatPoint(startPoint)}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200/70 bg-white px-4 py-3">
            <div className="text-[11px] uppercase tracking-[0.2em] text-muted">终点</div>
            <div className="mt-2 text-sm font-semibold text-ink">
              {formatPoint(endPoint)}
            </div>
          </div>
        </div>

        <div className="grid gap-3">
          <div className="text-xs font-semibold uppercase tracking-[0.2em] text-muted">
            路线显示
          </div>
          <div className="grid gap-2">
            <label className="flex items-center gap-3 rounded-xl border border-slate-200/70 bg-white px-4 py-3 text-sm font-semibold text-ink">
              <input
                type="checkbox"
                className="h-4 w-4 accent-teal-600"
                checked={showTransitRoute}
                onChange={(event) => setShowTransitRoute(event.target.checked)}
              />
              公交出行
            </label>
            <label className="flex items-center gap-3 rounded-xl border border-slate-200/70 bg-white px-4 py-3 text-sm font-semibold text-ink">
              <input
                type="checkbox"
                className="h-4 w-4 accent-teal-600"
                checked={showCarRoute}
                onChange={(event) => setShowCarRoute(event.target.checked)}
              />
              开车出行
            </label>
          </div>
        </div>

        <button
          onClick={clearSelection}
          disabled={!startPoint}
          className="w-full rounded-full bg-teal-700 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-teal-700/20 transition hover:-translate-y-0.5 hover:shadow-teal-700/30 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none disabled:hover:translate-y-0"
        >
          清除选择
        </button>

        <div className="mt-auto grid gap-2 text-sm text-muted">
          <div className="flex items-center gap-2">
            <span className="h-1 w-5 rounded-full bg-red-500"></span>
            <span>开车出行</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-1 w-5 rounded-full bg-blue-600"></span>
            <span>公交</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-1 w-5 rounded-full bg-emerald-500"></span>
            <span>地铁</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="h-1 w-5 rounded-full bg-slate-400"></span>
            <span>步行</span>
          </div>
        </div>
      </aside>
      <main
        id="map"
        ref={mapContainerRef}
        className="relative min-h-screen"
      >
        {showRouteCards ? (
          <div
            ref={overlayRef}
            className="pointer-events-none absolute inset-0 z-[500]"
          >
            {showCarRoute ? (
            <div
            className="pointer-events-auto absolute w-72 select-none rounded-2xl border border-red-200/70 bg-white/90 p-5 shadow-xl backdrop-blur"
              style={{
                transform: `translate(${carCardPos.x}px, ${carCardPos.y}px)`,
              }}
              onMouseDown={(event) => handleDragStart(event, "car")}
              onTouchStart={(event) => handleDragStart(event, "car")}
            >
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-red-500">
                <span>开车出行</span>
                <span className="h-1 w-6 rounded-full bg-red-500"></span>
              </div>
            <div className="mt-3 space-y-1 text-sm font-semibold text-ink">
              <div>距离 {carResult.distance}</div>
              <div>时间 {carResult.time}</div>
            </div>
            <div className="mt-2 space-y-1 text-xs text-muted">
              {carSummary.length > 0 ? (
                carSummary.map((item) => (
                  <div key={`${item.label}-${item.distance}-${item.time}`}>
                    <span className="font-semibold text-ink">{item.label}</span>{" "}
                    {item.distance} · {item.time}
                  </div>
                ))
              ) : (
                <div>未找到路线</div>
              )}
            </div>
            <div
              ref={carMapContainerRef}
              className="pointer-events-none mt-4 h-28 w-full overflow-hidden rounded-lg border border-slate-200/70"
            ></div>
            <div className="mt-2 text-xs text-muted">拖拽卡片可调整位置</div>
          </div>
            ) : null}

            {showTransitRoute ? (
            <div
            className="pointer-events-auto absolute w-72 select-none rounded-2xl border border-blue-200/70 bg-white/90 p-5 shadow-xl backdrop-blur"
              style={{
                transform: `translate(${transitCardPos.x}px, ${transitCardPos.y}px)`,
              }}
              onMouseDown={(event) => handleDragStart(event, "transit")}
              onTouchStart={(event) => handleDragStart(event, "transit")}
            >
              <div className="flex items-center justify-between text-xs uppercase tracking-[0.2em] text-blue-600">
                <span>公交出行</span>
                <span className="h-1 w-6 rounded-full bg-blue-600"></span>
              </div>
            <div className="mt-3 space-y-1 text-sm font-semibold text-ink">
              <div>距离 {transitResult.distance}</div>
              <div>时间 {transitResult.time}</div>
            </div>
            <div className="mt-2 space-y-1 text-xs text-muted">
              {transitSummary.length > 0 ? (
                transitSummary.map((item) => (
                  <div key={`${item.label}-${item.distance}-${item.time}`}>
                    <span className="font-semibold text-ink">{item.label}</span>{" "}
                    {item.distance} · {item.time}
                  </div>
                ))
              ) : (
                <div>未找到路线</div>
              )}
            </div>
            <div
              ref={transitMapContainerRef}
              className="pointer-events-none mt-4 h-28 w-full overflow-hidden rounded-lg border border-slate-200/70"
            ></div>
            <div className="mt-2 text-xs text-muted">拖拽卡片可调整位置</div>
          </div>
            ) : null}
          </div>
        ) : null}
      </main>
    </div>
  );
}
