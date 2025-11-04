# 浏览器版方案说明

## 整体架构
- 保留现有 Python 计算模块（如 `grid_strategy.py`, `trading_utils.py`, `stock_analysis_engine.py`），作为新版后端的核心计算逻辑。
- 在全新仓库（位于 `A Stock` 目录之外）构建 FastAPI 应用，暴露自选列表、日级 K 线、日内分时等接口，后续可直接部署到服务器，仅需调整环境变量与反向代理。
- 前端使用 React + TypeScript（Vite 脚手架）实现，面向浏览器环境，可在多个标签页同时打开不同股票的日 K 与分时页面。
- 新项目保持独立 Git 版本库；暂不封装 Python 模块为 pip 包，直接复制所需代码进入新仓库，后续再评估模块化方案。
- 原 `StockETFQuery` 子模块整体并入新仓库统一管理，消除子模块维护负担。

## 核心功能拆解
- `watchlist_window.py` 逻辑对应 REST 接口：
  - `GET /watchlists`、`POST /watchlists` 提供列表读取与维护；
  - `GET /quotes` 支持搜索、排序、信号刷新；
  - 后端初期沿用 JSON 存储，预留切换 SQLite 的空间。
- `stock_kline_window.py` 对应：
  - `GET /kline/{code}` 返回 K 线、指标、筹码、资金来源等数据；
  - `GET /signals/{code}` 返回条件命中列表；
  - 数据中包含筹码集中度 70%/90% 两条曲线（雷达图暂不实现）。
- `intraday_window.py` 对应：
  - `GET /intraday/{code}` 返回实时或轮询分时数据；
  - `WebSocket /ws/intraday/{code}` 推送秒级/分钟级数据；
  - 均线、成本涨幅，RSI、布林 压力线，支撑线，压力带 支撑带等指标在后端计算，音频提示由前端 `<audio>` 播放原有 WAV。

## 前端实现
- 框架：React + Ant Design ProTable、Antd Form/Select 替代 Tkinter 控件。
- 图表：ECharts 实现 K 线、分时折线、成交量柱状、RSI 折线 其他指标折线；筹码集中度70,90用填充带状折线，雷达图暂缓。
- 状态与数据：
  - React Query 负责数据请求与缓存；
  - Zustand 或 Redux Toolkit 管理全局状态（如当前股票、设置、快捷键映射）。
- 交互：
  - KeyboardJS/`useHotkeys` 提供桌面端快捷键（如 ⌘K、⌘R），并处理浏览器冲突；
  - 多标签页支持：各标签页独立拉取/订阅数据，必要时可引入 Shared Worker 做连接复用。
- 音频与通知：浏览器 `<audio>` 播放 WAV，Antd Notification/Modal 替代 Messagebox。
- 响应式设计：
  - 利用 Ant Design 布局、CSS Grid/Flex，自适配桌面与移动端；
  - 移动端默认折叠非核心信息，图表高度按视口调整；
  - 触控手势启用 ECharts 原生缩放与拖拽，移动端禁用冲突快捷键提示。
- 本地部署：`npm install && npm run dev`（Vite 5173 端口），通过代理转发到 FastAPI (`localhost:8000`)。

## 后端实现
- FastAPI 目录结构建议：
  ```
  backend/
    app/
      main.py
      api/
        watchlists.py
        kline.py
        intraday.py
      services/
        watchlist_service.py
        kline_service.py
        intraday_service.py
      core/
        storage.py
        throttling.py
        calculators/
  ```
- 复用的 Python 计算模块直接纳入 `backend/core`，并编写单元测试确保离线调用稳定。
- 缓存层沿用现有 JSON/本地缓存逻辑，预留 Redis 等扩展点。
- AkShare 数据访问增加节流/重试机制，可复用 ETF API Monitor 的限流策略。
- JSON 写入采用读写锁或单线程队列，避免并发造成文件损坏。
- WebSocket 通道提供实时推送；若 AkShare 或行情源频控触发则自动降级为轮询。

### AkShare 接口稳定性策略
- **多数据源冗余**：沿用东财/同花顺/新浪三级 API 备用方案，实现 `DataProvider` 抽象按优先级切换；失败信息写入监控，便于告警。
- **自适应重试**：统一在服务层做指数回退 + 随机抖动的重试策略，限定单源最大尝试次数，超限自动切换备用源并在响应中标记降级。
- **限流与合并请求**：为高频接口增加 Token Bucket/漏桶限流，对同股票的短期请求做去重合并，减少远端压力。
- **缓存策略**：组合内存与持久化缓存（默认 5 分钟），行情失败时优先返回缓存数据，标记数据时间戳；历史指标尽量预计算。
- **健康监控**：提供 `/health/providers` 端点与指标汇总（成功率、响应耗时、连续失败次数），触发阈值时写日志或推送通知。
- **离线兜底**：连续失败时回退到最近缓存或本地 CSV（如 `data/cache`），同时向前端返回“数据可能过期”状态提示用户。
- **多 IP/代理策略**：针对频繁访问导致的临时封禁，预留可配置的代理池接口，支持轮换出口 IP（需符合目标站点服务条款）；调度策略与限流配合，避免异常流量模式。

### 已落地实现（里程碑 3 更新）
- 新增 `MarketDataProvider` 聚合器：封装多源 fallback、TTL 内存缓存、令牌桶限速，优先尝试 AkShare，失败回退到本地缓存或样例数据。
- Watchlist/K 线/分时服务接入聚合器，自动补齐涨跌幅、K 线指标、筹码集中度及分时 RSI/MA；默认缓存 5 分钟以减轻外部接口压力。
- API 与单元测试均基于新数据通路，确保离线环境仍可响应（回退到本地样例）。
- 新增 `/ws/intraday/{code}` WebSocket 通道，服务端定期推送实时/缓存数据并要求客户端 ACK；提供 5 秒节奏推送，异常时可回退 REST。
- 前端构建 WebSocket Hook（`useIntradayStream`）并与 React Query 融合，实现“实时优先 + 轮询降级”；占位热键/音频 Hook 预留后续增强。

## 实施步骤
1. 在新目录初始化 Git 仓库，编写基础 README（包含项目背景、启动方式、目录结构说明）。
2. 整理并复制现有 Python 计算模块到 `backend/core`，补充测试用例以确保兼容性。
3. 实现 FastAPI 接口：
   - `watchlists` 增删改查；
   - `kline/{code}`、`signals/{code}`、筹码集中度曲线；
   - `intraday/{code}`、`/ws/intraday/{code}`。
4. 搭建 React 前端：
   - 自选列表页（ProTable + 搜索/排序/标签色彩）；
   - 日 K 页面（K 线 + 指标 + 筹码 70/90 曲线）；
   - 分时页面（分时线 + RSI/布林/均线）。
5. 引入 React Query、状态管理、快捷键、音频提醒，完成移动端适配。
6. 实现 WebSocket 与轮询双模式，并在多标签场景下进行性能与连接数测试。
7. 编写本地启动脚本（`uvicorn backend.app.main:app --reload --port 8000`、`npm run dev`）与操作手册。
8. 准备 Dockerfile、Procfile 等部署脚手架，预留 Nginx/Traefik 反向代理配置。

## 风险与对策
- **AkShare 并发限制**：在服务层增加节流/失败重试与备用数据源，参考 ETF API Monitor 实现经验。
- **本地 JSON 读写竞态**：统一存储接口、加入文件锁或队列写入机制，必要时计划切换 SQLite。
- **计算逻辑迁移**：将 Matplotlib 前准备的数据处理抽成纯函数，确保前端图表所需数据完备。
- **多标签资源占用**：监测 WebSocket/CPU 负载，必要时统一连接或限制刷新频率。
- **移动端兼容**：针对触控/小屏测试，调整布局、字体、交互区域，确保 Chart 在手机上可用。
- **仓库维护**：StockETFQuery 文件直接合并进新仓库，统一依赖管理，避免子模块漂移。

## 后续规划
- 在功能稳定后评估是否拆分 Python 核心模块为独立包，便于多个项目复用。
- 补充 E2E 测试（Playwright/Cypress）验证桌面与移动端关键流程。
- 规划远期部署方案（Docker Compose、CI/CD）并结合登录鉴权、权限控制需求。
