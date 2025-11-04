# AStock Watchlist API 设计草案

> 目标：为网页版 Watchlist 提供可扩展、可测试的统一接口，支撑列表管理、行情刷新、信号/趋势计算及动态列表等功能。

## 1. 通用约定
- **基地址**：`/api`
- **响应格式**：
  ```json
  {
    "status": "ok",
    "data": ...,
    "meta": {...},
    "error": null
  }
  ```
  - `status`: `"ok"` / `"error"`
  - `data`: 具体内容
  - `meta`: 分页、任务进度、缓存信息等
  - `error`: 出错时包含 `code`, `message`, `details`
- **错误码**：约定如 `WATCHLIST_NOT_FOUND`, `SYMBOL_ALREADY_EXISTS`, `TASK_NOT_FOUND` 等
- **鉴权**：暂不实现，后续可接入 token / session

## 2. Watchlist 列表管理
### 2.1 获取列表集合
- `GET /watchlists`
- **返回**
  ```json
  {
    "status": "ok",
    "data": [
      {
        "name": "默认",
        "type": "custom",            // custom/system
        "symbol_count": 25,
        "last_updated": "2025-02-01T10:00:00+08:00"
      }
    ]
  }
  ```

### 2.2 创建列表
- `POST /watchlists`
- **请求**
  ```json
  { "name": "科技股", "description": "", "metadata": {} }
  ```
- **返回**：新建列表信息

### 2.3 重命名 / 更新
- `PUT /watchlists/{name}`
- **请求**
  ```json
  { "name": "新名称", "description": "...", "metadata": {...} }
  ```

### 2.4 删除列表
- `DELETE /watchlists/{name}`
- 删除用户自建列表；系统列表（板块、信号等）不可删除。

## 3. 列表内股票管理
### 3.1 获取列表明细
- `GET /watchlists/{name}/symbols`
- **参数**
  - `with_quotes=true|false`（默认 true）
  - `with_signals=true|false`
  - `limit`, `offset`
- **返回**：数组，包含基础字段及可选行情信息
  ```json
  {
    "status": "ok",
    "data": [
      {
        "code": "600519",
        "name": "贵州茅台",
        "lists": ["默认"],
        "tags": [],
        "notes": "",
        "quote": {
          "last_price": 1672.3,
          "change_percent": 1.2,
          "industry": "白酒",
          "cost_change": 0.8,
          "ma5_deviation": 1.5,
          "next_day_limit_up_ma5_deviation": 3.2,
          "intraday_trend": "-",
          "day_trend": "up",
          "week_trend": "-",
          "month_trend": "-",
          "holders_change": -2.1,
          "capita_change": 1.0,
          "message": "成本突破MA5",
          "signal_level": "buy"
        },
        "last_refreshed": "2025-02-01T10:30:00+08:00"
      }
    ],
    "meta": {
      "list_type": "custom",
      "cache": {
        "interval_seconds": 300,
        "generated_at": "2025-02-01T10:30:00+08:00"
      }
    }
  }
  ```

### 3.2 添加股票
- `POST /watchlists/{name}/symbols`
- **请求**
  ```json
  { "code": "600519", "alias": "贵州茅台" }
  ```
- 服务器负责验证代码、名称映射，以及动态列表禁用添加逻辑。

### 3.3 删除股票
- `DELETE /watchlists/{name}/symbols/{code}`
- 支持批量：`POST /watchlists/{name}/symbols:batch-delete`
  ```json
  { "codes": ["600519", "000001"] }
  ```

### 3.4 批量更新
- 扩展接口：`PUT /watchlists/{name}/symbols/{code}`
  ```json
  { "tags": ["白酒"], "notes": "中长期持有" }
  ```

## 4. 搜索与模糊匹配
- `GET /symbols/search?q=maotai`
- **返回**
  ```json
  {
    "status": "ok",
    "data": [
      { "code": "600519", "name": "贵州茅台", "alias": ["maotai"], "type": "stock" },
      { "code": "000858", "name": "五粮液", "match_reason": "拼音" }
    ]
  }
  ```
- 支持代码、名称、拼音首字母；结果按匹配度排序。

## 5. 行情与刷新
### 5.1 批量行情
- `GET /quotes?codes=600519,000001`
- **返回**：合并 `MarketDataProvider` 输出。

### 5.2 手动刷新
- `POST /watchlists/{name}/refresh`
  ```json
  { "scope": ["quotes", "info", "trend"] }
  ```
- 返回异步任务 ID。

### 5.3 任务查询
- `GET /tasks/{id}`
  ```json
  {
    "status": "ok",
    "data": {
      "id": "task_123",
      "type": "watchlist_refresh",
      "state": "running",       // queued/running/completed/failed
      "progress": 55,
      "result": {...},
      "started_at": "...",
      "finished_at": null
    }
  }
  ```
- 可扩展为 Server-Sent Events / WebSocket 推送进度。

### 5.4 WebSocket 推送
- `GET /ws/watchlists/{name}`（选项）
  - 推送行情增量、刷新完成通知等。

## 6. 动态列表
- `GET /watchlists/system/{type}`
  - `type` ∈ `board`, `buy_signals`, `sell_signals`, `oversold`, `delisted`, `longhubang`
  - 可附带 `?force_refresh=true`
- 返回结构与普通列表一致，`meta.list_type = "system"`。

## 7. 信息列与趋势列
### 7.1 刷新信息列
- `POST /watchlists/{name}/refresh-info`
  ```json
  { "codes": ["600519","000001"], "force": false }
  ```
- 返回任务 ID，任务执行完成后可通过 `/tasks/{id}` 获取结果（每个 code 对应 message/level）。

### 7.2 刷新趋势列
- `POST /watchlists/{name}/refresh-trend`
  ```json
  { "codes": ["600519"], "force": false }
  ```
- 结果包含 `day/week/month`、`ma5_deviation`、`next_day_limit_up_ma5_deviation`、`intraday_trend`、`cost_change` 等字段。

## 8. 缓存管理
- 查看缓存状态：`GET /cache`
  ```json
  {
    "status": "ok",
    "data": [
      { "type": "quotes", "entries": 12, "expires_in": 180 },
      { "type": "signal", "entries": 40, "expires_in": 600 }
    ]
  }
  ```
- 清理缓存：`DELETE /cache/{type}`
  - `type` ∈ `quotes`, `signal`, `trend`, `industry`, `all`

## 9. 监控与健康检查
- `GET /health`
  - 基础状态。
- `GET /health/providers`
  ```json
  {
    "status": "ok",
    "data": {
      "akshare": {
        "state": "degraded",
        "fail_rate": 0.12,
        "last_success": "2025-02-01T10:20:00+08:00",
        "message": "fallback to sina"
      },
      "cache": { "quotes": "warm", "signal": "cold" }
    }
  }
  ```

## 10. 数据结构草案
```ts
type WatchlistName = string;

interface WatchlistMeta {
  name: WatchlistName;
  type: "custom" | "system";
  symbol_count: number;
  description?: string;
  metadata?: Record<string, unknown>;
  last_updated?: string;
}

interface WatchlistEntry {
  code: string;
  name: string;
  lists: WatchlistName[];
  tags?: string[];
  notes?: string;
  last_refreshed?: string;
  quote?: QuoteDetail;
}

interface QuoteDetail {
  last_price: number | null;
  change_percent: number | null;
  industry?: string;
  cost_change?: number | null;
  ma5_deviation?: number | null;
  next_day_limit_up_ma5_deviation?: number | null;
  intraday_trend?: string | null;
  day_trend?: string | null;
  week_trend?: string | null;
  month_trend?: string | null;
  holders_change?: number | null;
  capita_change?: number | null;
  message?: string;
  signal_level?: string | null;
}

interface TaskStatus {
  id: string;
  type: string;
  state: "queued" | "running" | "completed" | "failed";
  progress?: number; // 0-100
  result?: unknown;
  error?: { code: string; message: string };
  started_at?: string;
  finished_at?: string;
}
```

## 11. 开发优先级建议
1. 实现 `GET/POST/DELETE /watchlists`、`GET /watchlists/{name}/symbols`、`POST/DELETE symbols`、`GET /symbols/search`、`GET /quotes`。
2. 引入任务管理（信息列 & 趋势刷新）、`/tasks/{id}`。
3. 动态列表 & 缓存管理接口。
4. WebSocket 推送与健康监控扩展。

--- 

可根据讨论结果进一步细化字段及鉴权策略，欢迎直接在文档中修改或标注。
