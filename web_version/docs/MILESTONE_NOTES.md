# 里程碑一记录

## 完成内容
### 里程碑一（后端）
- 建立独立目录结构（backend/frontend/docs）与项目 README。
- 搭建 FastAPI 基础应用，提供 `/`, `/health`, `/watchlists`, `/kline/{code}`, `/intraday/{code}` 接口。
- 编写核心服务骨架（watchlist、kline、intraday 占位）并提供模拟数据。
- 引入 `Settings` 配置类，整理 AkShare 节流/代理池等后续扩展点。
- 准备样例数据 `backend/data/watchlists.json`。
- 添加 pytest 测试覆盖 watchlist 读写、kline 与 intraday mock 逻辑。
- 梳理 AkShare 稳定性策略（PLAN.md）并纳入多 IP/代理说明。
- 新增 `MarketDataProvider` 聚合器，内置多源 fallback、限流与 TTL 缓存；Watchlist/K 线/分时服务已替换为实际聚合逻辑。
- 接入 AkShare 代码→名称映射，支持拼音/名称模糊搜索并落盘缓存；提供 `/symbols/search`、`/quotes` 等真实数据接口。

### 里程碑二（前端原型）
- 初始化 Vite + React + TypeScript 工程，配置 Ant Design、React Query、ECharts 等依赖。
- 实现 Watchlist、Daily K、Intraday 页面，联通后端 Mock API。
- 构建 API 客户端、Query Hooks、基础布局与响应式样式。
- 预留快捷键、音频、WebSocket 等后续扩展点。
- 编写前端使用说明（README 更新），并规划 lint 命令。
- 新增 WebSocket 实时分时流及前端 Hook（含轮询降级、音频/热键占位）。
- Watchlist 页面接入真实后端：列表管理（新建/删除）、股票添加/删除（自动补全代码/名称）、刷新统计、快捷键提示。

## 未完事项 / 下一步
- 构建 WebSocket `/ws/intraday/{code}` 以及轮询降级实现，并完善前端订阅与提示。
- 完善信息列/趋势列刷新接口与 UI（含后台任务、进度提示、列样式）。
- 动态列表（板块、信号、龙虎榜等）API 与前端适配，禁用新增操作、展示数据来源。
- 缓存管理与监控：暴露缓存状态、清理接口，前端提供管理弹窗；扩展健康检查指标。
- 完善前端交互：快捷键、音频提示、表格筛选、行情刷新策略；移动端适配、性能优化。
- 编写 Dockerfile/Compose、代理配置示例和 CI/CD 草案。
- 在具备网络环境下完成 `npm install / npm run dev / npm run lint` 验证，生成锁文件并补充开发文档。
