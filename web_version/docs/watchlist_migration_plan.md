# AStock Watchlist 网页版迁移计划

## 1. 项目目标
将 Tkinter 版自选列表功能完整移植到 AStock 网页端，实现与桌面版一致的功能体验，并接入真实行情数据。重点包括：列表管理、行情刷新、信号与趋势计算、快捷键/交互、动态列表（板块/信号/龙虎榜等）以及缓存管理。

---

## 2. 原有功能拆解

### 2.1 列表体系
- **默认列表 + 用户自建列表**：保存在 `config/watchlists.json`，`symbols` 字典维护代码归属的多个列表。
- **动态列表**：板块、买入信号、卖出信号、超跌、退市、龙虎榜等，数据动态生成并带缓存。

### 2.2 UI 交互与快捷键
- 下拉选择列表，新建/删除列表。
- 添加股票（代码/名称/拼音搜索）、放大镜按钮、回车触发。
- 删除选中、分类按钮。
- 刷新数据 `⌘R`、刷新信息列 `⌘I`、刷新趋势列 `⌘T`、打开 K 线 `⌘K`、复制 `⌘C`。
- 支持多选、回车打开 K 线窗口。

### 2.3 数据展示
- Treeview 列：`name/code/industry/price change/cost change/MA5偏离/次日板MA5偏离/日内趋势/日趋势/周趋势/月趋势/股东增幅/持股增幅/message/level`。
- 列宽、排序、标签颜色（买/卖等）。
- 统计栏显示汇总信息。

### 2.4 批量刷新逻辑
- 信息列刷新：调用 `ETFAnalysisEngine` 条件检测，更新 message/level。
- 趋势列刷新：计算日/周/月趋势，使用缓存防止重复计算。
- 进度提示、后台线程。

### 2.5 缓存与配置
- `list_cache`、`signal_cache`、`trend_cache`、`industry_cache`。
- `signal_cache.json`、`trend_cache.json` 文件持久化，带版本/超时控制。
- API 调用限制：并发数、请求间隔、批大小、重试次数等。
- 交易时间配置（9:30-15:00）控制刷新策略。

### 2.6 其他
- 网格行列设置影响 K 线窗口排列。
- 缓存管理界面。
- 分类逻辑、龙虎榜数据拉取。

---

## 3. 迁移实施计划

### Phase 0：架构准备
1. **API 设计**
   - Watchlist CRUD：`GET/POST/PUT/DELETE /watchlists`；`POST /watchlists/{name}/symbols`；`DELETE /watchlists/{name}/symbols/{code}`。
   - 动态列表：`GET /watchlists/system/{type}`（板块/信号/龙虎榜等），带缓存。
   - 搜索：`GET /symbols/search?q=` 支持代码/名称/拼音。
   - 信息列刷新：`POST /watchlists/{name}/refresh-info`（可返回任务 ID）。
   - 趋势列刷新：`POST /watchlists/{name}/refresh-trend`。
   - 行情接口：`GET /quotes` 支持批量代码。
   - 缓存管理：`GET/DELETE /cache/{type}`。
   - 监控：`GET /health/providers`。

2. **基础设施**
   - 后台任务队列或异步任务（`asyncio` + `BackgroundTasks` 或轻量队列）。
   - 统一错误处理与响应格式；日志采集。
   - 单元测试/集成测试覆盖列表 CRUD、搜索、动态列表、刷新逻辑。
   - 真实数据接入：扩展 `MarketDataProvider` 支持股票行情、板块、龙虎榜。

### Phase 1：核心功能迁移
1. **列表与搜索**
   - Backend：实现 watchlist CRUD、search、数据持久化（沿用原结构）。✅ 已完成首版（参见 `watchlist_api_spec.md` & `watchlists`/`symbols` 路由）。
   - Frontend：表格列映射、排序、统计栏；支持列表选择/新增/删除、添加股票（搜索自动补全）、删除选中；保留刷新快捷键。✅ `WatchlistPage` 已接入新 API（远程搜索支持代码/名称模糊匹配）。
   - 状态管理：React Query 管理数据请求，局部状态管理使用组件内部 `useState`（后续按需评估 Zustand）。

2. **行情刷新与实时联动**
   - Backend：实现 `/quotes` 接口，结合 WebSocket 推送或定时更新。
   - Frontend：手动刷新按钮、定时刷新；行情颜色显示。

3. **信息列刷新**
   - Backend：封装 `ETFAnalysisEngine` 条件计算服务，支持批量刷新、进度反馈。
   - Frontend：提供刷新按钮/快捷键、进度提示、结果显示与标签染色。

4. **趋势列刷新**
   - Backend：迁移趋势计算逻辑及缓存。
   - Frontend：按钮/快捷键、进度显示、数据展示。

### Phase 2：高级特性与动态列表
1. **动态列表适配**
   - 板块、买入/卖出信号、超跌、退市、龙虎榜等 API。
   - 前端自动加载、禁用添加按钮。

2. **网格布局与交互**
   - 讨论 web 端网格设置的呈现方式（如多窗口布局）。
   - 完整覆盖快捷键和回车打开 K 线等交互。

3. **缓存管理与设置**
   - Backend：缓存列表/清理接口。
   - Frontend：缓存管理弹窗、设置页（刷新间隔、交易时间等）。

4. **监控与日志**
   - API 成功率、错误日志、最后刷新时间；前端提示数据源状态。

### Phase 3：真实数据与稳定性增强
1. **真实行情接入**
   - 验证 `MarketDataProvider` 与 AkShare 多源 fallback。
   - 增加本地 CSV 缓存与预热脚本。
   - 考虑盘前/盘后刷新策略。

2. **性能与体验**
   - 批量请求合并、增量刷新。
   - 虚拟滚动、键盘导航、移动端适配。

3. **测试与文档**
   - 单元测试、集成测试、E2E。
   - 更新 README、PLAN、API 文档。

---

## 4. 近期实施顺序建议
1. 详细定义 Phase 0 API（含字段、返回结构、错误码），输出接口文档。
2. 实现 watchlist CRUD + search + quotes；更新前端自选列表基础功能。
3. 逐步迁移信息列/趋势列刷新、动态列表与缓存管理。
4. 于具备网络的环境验证前端依赖、快捷键、音频等功能。
5. 接入真实行情源并完善监控与稳健性。

---

*如需调整计划或补充新的需求，可以直接编辑此文档。*
