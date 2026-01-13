# 上海市路网 Web 应用

该项目将前后端分离：后端使用 FastAPI 负责路网建模与路径计算，前端使用 React + Leaflet 负责地图渲染与交互。

## 后端（FastAPI）

### 启动方式

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

默认监听 `http://localhost:8000`。

### 主要功能

- 启动时加载 `data/shanghai_roads.geojson`，构建路网图结构（节点、边、距离与时间权重）。
- 根据传入的起点、终点坐标，计算距离最短与时间最短路径。

### 路网建立的思路与流程

后端在启动时读取 GeoJSON 道路数据，将其转为可用于最短路径计算的图结构，核心步骤如下：

1. **节点抽取**：遍历每条 `LineString` 的坐标序列，将每个坐标点视为图中的一个节点。  
2. **边构建**：对同一条 `LineString` 中相邻的坐标点建立有向或双向边。  
3. **距离权重**：使用 Haversine 公式计算两点之间的球面距离（米）。  
4. **时间权重**：根据道路 `maxspeed` 或 `fclass` 的默认速度，计算通行时间（秒）。  
5. **索引加速**：构建网格索引（grid），用于快速查找与点击点最近的路网节点。  

该图结构在内存中维护，后续 `/route` 请求仅需进行最短路径搜索即可，不需要反复解析 GeoJSON。

### 主要接口

- `GET /health`：健康检查，返回节点数量。
- `GET /roads`：返回路网 GeoJSON 数据。
- `POST /route`：计算距离/时间最短路径。

请求示例：
```json
{
  "start": { "lat": 31.2304, "lng": 121.4737 },
  "end": { "lat": 31.215, "lng": 121.45 }
}
```

返回示例：
```json
{
  "distance": {
    "cost": 1234.56,
    "path": [[31.2304, 121.4737], [31.229, 121.47]]
  },
  "time": {
    "cost": 321.0,
    "path": [[31.2304, 121.4737], [31.231, 121.471]]
  }
}
```

## 前端（React + Leaflet）

### 启动方式

```bash
cd frontend
npm install
npm run dev
```

默认监听 `http://localhost:5173`。  
后端地址可通过环境变量 `VITE_API_BASE` 指定（默认 `http://localhost:8000`）。

### 主要实现方式

- 使用 React 组件管理 UI 状态（起点、终点、路径结果）。
- 使用 Leaflet 渲染底图与路网（后端 `/roads` 接口）。
- 点击地图依次选择起点与终点，向后端 `/route` 发送请求。
- 将返回的两条路径绘制为不同颜色的折线，并在侧边栏展示距离/时间结果。

### 主要功能

- 路网可视化。
- 地图点击选点。
- 距离最短路径与时间最短路径计算与展示。
