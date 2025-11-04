# 网格策略网页端迁移 —— 里程碑进展

本目录承载网页版迁移方案的新仓库骨架。当前进度覆盖后端基础（Milestone 1）与前端原型（Milestone 2），包括可运行的 FastAPI 框架、核心服务骨架、以及与 Mock 数据交互的 React 页面。

## 目标概述
- 独立项目结构（backend / frontend / docs），后续可直接初始化独立 Git 仓库。
- 搭建 FastAPI 应用，提供 `/health`、`/watchlists`、`/kline/{code}` 示例接口。
- 迁移/抽象核心计算模块的基础骨架与单元测试（暂用模拟数据，后续接入真实行情）。
- 输出本地启动与后续工作指引，为下一阶段前端页面开发与实时数据对接奠定基础。

## 目录结构
```
web_version/
├── README.md               # 里程碑说明（本文件）
├── PLAN.md                 # 完整方案与实施规划
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI 入口
│   │   └── routers/        # 路由模块
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py       # 配置与环境变量
│   │   ├── watchlist_service.py
│   │   ├── kline_service.py
│   │   └── intraday_service.py (占位)
│   ├── data/
│   │   └── watchlists.json # 样例数据
│   ├── tests/
│   │   └── test_watchlist_service.py
│   └── requirements.txt    # 后端依赖
├── frontend/
│   ├── README.md           # 前端规划与里程碑说明
│   ├── package.json        # 前端依赖与脚本
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/                # React 代码（看板、日K、分时页面）
└── docs/
    └── MILESTONE_NOTES.md  # 里程碑记录与下一步计划
```

> 目录中部分文件为占位或 Mock，实现将随着里程碑推进逐步替换为真实逻辑。

## Milestone 1（后端骨架）
1. **FastAPI 基架**：`backend/app/main.py` 创建应用实例，挂载 `/`, `/health`, `/watchlists`, `/kline/{code}`, `/intraday/{code}` 路由。
2. **核心服务骨架**：`backend/core` 下提供 watchlist、kline、intraday 服务，使用模拟数据实现业务接口，并编写 pytest 用例。
3. **数据与配置**：提供 `backend/data/watchlists.json` 样例，配置 AkShare 节流/代理等 TODO。
4. **行情聚合器（新增）**：`backend/core/data_provider.py` 集成多源 fallback、TTL 缓存、限速与离线兜底逻辑，Watchlist/K 线/分时服务已接入。
5. **文档与脚本**：`docs/MILESTONE_NOTES.md` 记录完成项；`PLAN.md` 同步总体方案；README 描述启动方式。

## 一键启动（推荐）
项目根目录提供 `start_astock.command`，双击即可同时启动后端 (`uvicorn`) 与前端 (`npm run dev`)。脚本会尝试激活 Conda 环境 `astock_tk`（若已安装 akshare 在其中），确保后端加载真实行情。终止应用时在弹出的终端窗口按 `Ctrl+C`，脚本会自动关闭两个进程。

如需手动运行，可分别执行：
```bash
# 后端
cd web_version/backend
# 如使用 Conda 环境：conda activate astock_tk
uvicorn backend.app.main:app --reload --port 8000

# 前端
cd web_version/frontend
npm install   # 首次安装依赖
npm run dev
```

## Milestone 2（前端原型）
- 初始化 Vite + React + TypeScript 工程，集成 Ant Design、React Query、Zustand、ECharts、KeyboardJS 等基础依赖。
- 实现自选列表、日 K、分时三大页面，默认对接后端聚合数据（支持多源 fallback）。
- 提供基础布局（侧边菜单 + Header），支持响应式布局与多 Tab 浏览场景的样式占位。
- API 请求通过 `/api` 前缀代理至 FastAPI（参见 `vite.config.ts`）。
- 新增分时 WebSocket 订阅 Hook，实时数据异常时自动回退到 REST 轮询；占位热键/音频 Hook 预留快捷键与提示音扩展。
- 后端现已提供 Watchlist CRUD / 搜索 / 行情 API（`/watchlists`, `/symbols/search`, `/quotes` 等），为前端迁移做准备。

### 前端本地运行
```bash
cd web_version/frontend
npm install  # 首次运行需联网安装依赖，此环境未实际执行
npm run dev  # 默认启动在 http://localhost:5173
```

### 代码质量
```bash
npm run lint
```

> 当前仍缺乏网络访问，`npm install` 尚未成功执行；命令保留以备联网后验证。

## 下一步里程碑预览
- 完成 FastAPI 实际数据接入（多源 + 缓存 + 限流）。
- 建立 WebSocket `/ws/intraday/{code}` 与轮询 fallback，前端实现订阅逻辑。
- 实现快捷键、音频提示、移动端交互细节与多标签性能优化。
- 构建代理池/节流模块，增强 AkShare 稳定性并完善监控告警。

如需独立仓库，只需在 `web_version` 内执行 `git init` 并根据 README 继续搭建。后续工作建议逐步拆解并按 PLAN.md 中的实施步骤推进。
