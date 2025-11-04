# AStock 网页版 Watchlist 前端改造计划

## 1. 目标
- 利用后端已提供的 `/watchlists`、`/watchlists/{name}/symbols`、`/symbols/search`、`/quotes` API，重构前端 Watchlist 页面。
- 支持列表管理、股票搜索与添加、删除、行情刷新、排序、统计栏，以及基础快捷键。
- 为后续的信息列/趋势列刷新、动态列表等功能预留 Hook 和 UI 位置。

## 2. 页面结构规划
1. **布局**：沿用现有布局（侧边菜单 + Header + 内容区域）。
2. **顶部工具栏**：
   - 列表下拉选择器（支持系统/自建列表区分）。
   - 新建列表按钮（弹窗输入名称、描述）。
   - 删除列表按钮（仅对自建列表启用）。
   - 添加股票按钮/搜索框，实时自动补全；回车或点击加入当前列表。
   - 刷新按钮、信息列刷新、趋势列刷新（先保留按钮占位/禁用状态）。
   - K 线按钮（保留现有逻辑）。
   - 缓存管理按钮占位。
3. **表格区域**：
   - 使用 Ant Design Table/ProTable。
   - 列：code、name、industry、last_price、change_percent、message、signal_level 等（后续逐步补齐其他列）。
   - 支持排序（优先做代码/名称/涨跌幅）。
   - 行操作：多选、删除、双击/回车打开 K 线。
   - 行样式：根据信号等级染色。
4. **统计栏**：显示当前列表总数、上涨/下跌数量、均价等（先实现基本计数）。
5. **状态提示**：顶部/通知区域显示刷新状态、任务进度、错误信息。

## 3. 状态管理与数据流
- 使用 React Query 处理 API 请求与缓存。
- 使用 Zustand（或 Redux Toolkit）存储当前列表名、列表集合、选择状态、表格设置。
- 快捷键 Hook 扩展：
  - `⌘R` 刷新行情
  - `⌘I` / `⌘T` 保留占位（禁用期间提示“功能建设中”）
  - `⌘K` 打开 K 线
  - `⌘C` 复制选中代码

## 4. 分阶段实施步骤
### Phase A：基础接入
1. API Hook
   - `useWatchlists()`：获取 `/watchlists`。
   - `useWatchlistSymbols(name)`：获取列表明细。
   - `useCreateWatchlist()`, `useDeleteWatchlist()`，`useAddSymbol()`, `useRemoveSymbol()`：Mutation hook。
   - `useSearchSymbols(query)`：搜索自动补全。
2. Zustand Store
   - `currentList`、`setCurrentList`
   - `modalState`（新建列表、添加股票）
3. UI 改造
   - 列表下拉、按钮事件连接 API。
   - 表格数据绑定 React Query 返回；提供 loading/empty/error 状态。
   - 删除选中操作（调用批量删除或循环删除）。
4. 行情刷新
   - `刷新` 按钮触发 `refetch`。
   - 后端返回行情空时显示占位。
   - 错误提示通过 Antd `message.error`。
5. 统计栏
   - 计算表格数据（涨跌幅 > 0 则计入上涨等）。

### Phase B：增强功能
1. 信息列/趋势列按钮：
   - 按钮点击触发后端刷新接口（待实现），当前可弹出提示“后台开发中”。
2. 系统列表支持：
   - 切换系统列表时，禁用添加/删除操作；显示“自动刷新”提示。
3. 缓存管理
   - 弹窗展示 `/cache` 状态，然后手动清空。
4. 快捷键与 K 线
   - 完善热键 Hook，接管事件（阻止表格默认行为）。
   - K 线按钮/快捷键调用已有页面逻辑。
5. 状态同步
   - WebSocket 推送时（未来接入）更新行情；当前保持轮询。

## 5. 技术注意事项
- **错误处理**：后端返回的 error code 映射为用户友好提示。
- **分页/虚拟列表**：暂不实现，如数据过多再评估虚拟滚动。
- **国际化**：沿用现有 `locales` 方案，在前端保留中文文案或预留 `i18n`。
- **无网环境**：保持当前回退行为（默认示例数据、接口失败提示）。

## 6. 文档与测试
- 更新 README / PLAN / MILESTONE，记录前端 Watchlist 改造进展。
- 编写组件测试（React Testing Library）验证核心交互（可后续补充）。
- 手工验证流程：
  1. 新建列表 -> 添加股票 -> 刷新 -> 删除。
  2. 搜索不存在股票 -> 提示。
  3. 切换系统列表 -> 禁用添加。

---

> 如需调整顺序或功能范围，可直接编辑此文档。
