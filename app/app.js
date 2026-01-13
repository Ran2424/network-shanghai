const map = L.map("map", { preferCanvas: true }).setView([31.2304, 121.4737], 11);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const statusEl = document.getElementById("status");
const startEl = document.getElementById("startPoint");
const endEl = document.getElementById("endPoint");
const distanceEl = document.getElementById("distanceResult");
const timeEl = document.getElementById("timeResult");
const clearBtn = document.getElementById("clearBtn");

const GEOJSON_URL = "../data/shanghai_roads.geojson";

let startMarker = null;
let endMarker = null;
let distanceLine = null;
let timeLine = null;
let startNodeId = null;
let endNodeId = null;

const graph = {
  nodes: [],
  adjacency: [],
  grid: new Map(),
  cellSize: 0.002,
};

const speedByClass = {
  motorway: 80,
  trunk: 60,
  primary: 50,
  secondary: 40,
  tertiary: 30,
  residential: 25,
  service: 15,
  unclassified: 25,
  living_street: 10,
};

function setStatus(text) {
  statusEl.textContent = text;
}

function coordKey(lat, lng) {
  return `${lat.toFixed(6)},${lng.toFixed(6)}`;
}

function getNodeId(lat, lng) {
  const key = coordKey(lat, lng);
  let id = graph.nodeIndex.get(key);
  if (id === undefined) {
    id = graph.nodes.length;
    graph.nodeIndex.set(key, id);
    graph.nodes.push({ lat, lng });
    graph.adjacency[id] = [];
    addToGrid(id, lat, lng);
  }
  return id;
}

function addToGrid(id, lat, lng) {
  const x = Math.floor(lng / graph.cellSize);
  const y = Math.floor(lat / graph.cellSize);
  const key = `${x}|${y}`;
  if (!graph.grid.has(key)) {
    graph.grid.set(key, []);
  }
  graph.grid.get(key).push(id);
}

function haversineMeters(lat1, lng1, lat2, lng2) {
  const r = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLng / 2) *
      Math.sin(dLng / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return r * c;
}

function isOneWay(value) {
  if (value === null || value === undefined) return false;
  const v = String(value).toLowerCase();
  if (["b", "f", "0", "n", "no", "false"].includes(v)) return false;
  if (["t", "1", "y", "yes", "true"].includes(v)) return true;
  return false;
}

function speedForFeature(props) {
  const raw = Number(props?.maxspeed || 0);
  if (raw > 0) return raw;
  const fallback = speedByClass[props?.fclass] || 30;
  return fallback;
}

function buildGraph(featureCollection) {
  graph.nodes = [];
  graph.adjacency = [];
  graph.grid = new Map();
  graph.nodeIndex = new Map();

  const features = featureCollection.features || [];
  for (const feature of features) {
    const geometry = feature.geometry || {};
    if (geometry.type !== "LineString") continue;
    const coords = geometry.coordinates || [];
    if (coords.length < 2) continue;
    const props = feature.properties || {};
    const speed = speedForFeature(props);
    const oneway = isOneWay(props.oneway);

    for (let i = 0; i < coords.length - 1; i += 1) {
      const [lng1, lat1] = coords[i];
      const [lng2, lat2] = coords[i + 1];
      const fromId = getNodeId(lat1, lng1);
      const toId = getNodeId(lat2, lng2);
      const distance = haversineMeters(lat1, lng1, lat2, lng2);
      const time = distance / (speed * 1000 / 3600);
      graph.adjacency[fromId].push([toId, distance, time]);
      if (!oneway) {
        graph.adjacency[toId].push([fromId, distance, time]);
      }
    }
  }
}

function nearestNode(lat, lng) {
  const cellSize = graph.cellSize;
  const baseX = Math.floor(lng / cellSize);
  const baseY = Math.floor(lat / cellSize);
  let bestId = null;
  let bestDist = Infinity;
  const maxRadius = 30;

  for (let radius = 0; radius <= maxRadius; radius += 1) {
    for (let dx = -radius; dx <= radius; dx += 1) {
      for (let dy = -radius; dy <= radius; dy += 1) {
        const key = `${baseX + dx}|${baseY + dy}`;
        const candidates = graph.grid.get(key);
        if (!candidates) continue;
        for (const id of candidates) {
          const node = graph.nodes[id];
          const dLat = node.lat - lat;
          const dLng = node.lng - lng;
          const dist = dLat * dLat + dLng * dLng;
          if (dist < bestDist) {
            bestDist = dist;
            bestId = id;
          }
        }
      }
    }
    if (bestId !== null && radius > 0) {
      const maxCell = radius * cellSize;
      if (maxCell * maxCell > bestDist) break;
    }
  }
  return bestId;
}

class MinHeap {
  constructor() {
    this.items = [];
  }
  push(node, priority) {
    this.items.push({ node, priority });
    this.bubbleUp(this.items.length - 1);
  }
  bubbleUp(index) {
    while (index > 0) {
      const parent = Math.floor((index - 1) / 2);
      if (this.items[parent].priority <= this.items[index].priority) break;
      [this.items[parent], this.items[index]] = [this.items[index], this.items[parent]];
      index = parent;
    }
  }
  pop() {
    if (this.items.length === 0) return null;
    const root = this.items[0];
    const last = this.items.pop();
    if (this.items.length > 0) {
      this.items[0] = last;
      this.bubbleDown(0);
    }
    return root;
  }
  bubbleDown(index) {
    const length = this.items.length;
    while (true) {
      let smallest = index;
      const left = index * 2 + 1;
      const right = index * 2 + 2;
      if (left < length && this.items[left].priority < this.items[smallest].priority) {
        smallest = left;
      }
      if (right < length && this.items[right].priority < this.items[smallest].priority) {
        smallest = right;
      }
      if (smallest === index) break;
      [this.items[smallest], this.items[index]] = [this.items[index], this.items[smallest]];
      index = smallest;
    }
  }
  get size() {
    return this.items.length;
  }
}

function shortestPath(startId, endId, weightIndex) {
  const n = graph.nodes.length;
  const dist = new Float64Array(n);
  dist.fill(Infinity);
  const prev = new Int32Array(n);
  prev.fill(-1);
  const heap = new MinHeap();
  dist[startId] = 0;
  heap.push(startId, 0);

  while (heap.size > 0) {
    const current = heap.pop();
    if (!current) break;
    const { node, priority } = current;
    if (priority !== dist[node]) continue;
    if (node === endId) break;
    const edges = graph.adjacency[node];
    for (const edge of edges) {
      const next = edge[0];
      const weight = edge[weightIndex];
      const nextDist = priority + weight;
      if (nextDist < dist[next]) {
        dist[next] = nextDist;
        prev[next] = node;
        heap.push(next, nextDist);
      }
    }
  }

  if (!Number.isFinite(dist[endId])) return null;

  const path = [];
  let cursor = endId;
  while (cursor !== -1) {
    path.push(cursor);
    cursor = prev[cursor];
  }
  path.reverse();
  return { cost: dist[endId], path };
}

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

function resetSelection() {
  if (startMarker) startMarker.remove();
  if (endMarker) endMarker.remove();
  if (distanceLine) distanceLine.remove();
  if (timeLine) timeLine.remove();
  startMarker = null;
  endMarker = null;
  distanceLine = null;
  timeLine = null;
  startNodeId = null;
  endNodeId = null;
  startEl.textContent = "未选择";
  endEl.textContent = "未选择";
  distanceEl.textContent = "-";
  timeEl.textContent = "-";
  clearBtn.disabled = true;
}

function updatePointLabel(element, lat, lng) {
  element.textContent = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

function drawPath(path, color) {
  const points = path.map((id) => [graph.nodes[id].lat, graph.nodes[id].lng]);
  return L.polyline(points, {
    color,
    weight: 5,
    opacity: 0.9,
  }).addTo(map);
}

async function init() {
  setStatus("加载路网中，请稍候…");
  const response = await fetch(GEOJSON_URL);
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

  setStatus("构建路网图结构…");
  await new Promise((resolve) => setTimeout(resolve, 50));
  buildGraph(data);

  setStatus("点击地图选择起点与终点");
}

map.on("click", (event) => {
  if (graph.nodes.length === 0) return;
  if (!startMarker) {
    const { lat, lng } = event.latlng;
    const nearest = nearestNode(lat, lng);
    if (nearest === null) return;
    const node = graph.nodes[nearest];
    startMarker = L.marker([node.lat, node.lng], { title: "起点" }).addTo(map);
    startMarker.bindPopup("起点").openPopup();
    updatePointLabel(startEl, node.lat, node.lng);
    clearBtn.disabled = false;
    startNodeId = nearest;
    return;
  }

  if (!endMarker) {
    const { lat, lng } = event.latlng;
    const nearest = nearestNode(lat, lng);
    if (nearest === null) return;
    const node = graph.nodes[nearest];
    endMarker = L.marker([node.lat, node.lng], { title: "终点" }).addTo(map);
    endMarker.bindPopup("终点").openPopup();
    updatePointLabel(endEl, node.lat, node.lng);
    endNodeId = nearest;

    setStatus("正在计算最短路径…");
    setTimeout(() => {
      const distancePath = shortestPath(startNodeId, endNodeId, 1);
      const timePath = shortestPath(startNodeId, endNodeId, 2);

      if (distancePath) {
        distanceLine = drawPath(distancePath.path, "#ef4444");
        distanceEl.textContent = formatDistance(distancePath.cost);
      } else {
        distanceEl.textContent = "未找到路线";
      }

      if (timePath) {
        timeLine = drawPath(timePath.path, "#2563eb");
        timeEl.textContent = formatTime(timePath.cost);
      } else {
        timeEl.textContent = "未找到路线";
      }

      setStatus("完成，可继续清除并重新选择");
    }, 30);
  }
});

clearBtn.addEventListener("click", () => {
  resetSelection();
  setStatus("点击地图选择起点与终点");
});

resetSelection();
init().catch((error) => {
  console.error(error);
  setStatus("加载失败，请检查数据文件或网络环境");
});
