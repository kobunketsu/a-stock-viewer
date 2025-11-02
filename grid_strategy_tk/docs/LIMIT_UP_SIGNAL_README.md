# 连板涨停买入信号实现说明

## 功能概述

实现了连板涨停买入信号功能，当股票上一个交易日涨停且本交易日9:25分时的开盘价>=上一个交易日日内1分钟布林线最高点时，发出连板涨停类型的买入信号。

## 实现特性

### 1. 涨停检测
- 检查上一个交易日是否涨停（涨跌幅 >= 9.5%）
- 支持股票、ETF等不同证券类型
- 使用akshare获取历史日线数据

### 2. 布林带最高点计算
- 获取上一个交易日的1分钟分时数据
- 计算20周期布林带上轨
- 找到布林带上轨的最高点作为参考价格

### 3. 信号触发条件
- 时间窗口：9:25-9:31（每分钟检查一次）
- 价格条件：当前开盘价 >= 上一个交易日布林带最高点
- 连续发出：在时间窗口内每分钟都会发出信号

### 4. 信号显示
- 信号格式：`{涨跌幅}%连板`（如：`9.8%连板`）
- 显示样式：红色实线
- 标签位置：信号价格下方

## 代码结构

### 核心类：LimitUpConsecutiveBuySignal

位置：`grid_strategy_tk/src/intraday_signals.py`

主要方法：
- `_check_previous_day_limit_up()`: 检查上一个交易日是否涨停
- `_calculate_prev_day_bollinger_high()`: 计算上一个交易日布林带最高点
- `check_condition()`: 检查信号触发条件
- `create_signal_data()`: 创建信号数据

### 集成点

1. **分时窗口集成**：在`IntradayWindow._setup_default_signals()`中添加连板信号
2. **信号检测**：在`_detect_signals_with_bollinger()`中传递必要数据
3. **信号绘制**：在`_plot_buy_signals()`中处理连板信号的显示样式

## 使用方法

### 自动启用
连板信号已集成到默认信号系统中，分时窗口启动时会自动启用。

### 手动添加
```python
from src.intraday_signals import LimitUpConsecutiveBuySignal

# 创建连板信号实例
limit_up_signal = LimitUpConsecutiveBuySignal()

# 添加到信号管理器
signal_manager.add_buy_signal(limit_up_signal)
```

### 信号管理
```python
# 列出所有信号
intraday_window.list_signals()

# 移除连板信号
intraday_window.remove_buy_signal("连板涨停买入")

# 清空所有信号
intraday_window.clear_all_signals()
```

## 技术细节

### 数据获取
- 使用akshare获取历史日线和分时数据
- 支持股票、ETF、指数等不同证券类型
- 自动处理交易日历，跳过周末

### 布林带计算
- 使用20周期移动平均线作为中轨
- 2倍标准差作为上下轨
- 1分钟数据重采样为5分钟计算，再插值回1分钟

### 缓存机制
- 缓存上一个交易日的涨停状态
- 缓存布林带最高点计算结果
- 避免重复计算，提高性能

### 错误处理
- 网络请求失败时的降级处理
- 数据格式异常的容错机制
- 详细的调试日志输出

## 测试

运行测试脚本：
```bash
cd grid_strategy_tk
python test_limit_up_signal.py
```

## 注意事项

1. **数据依赖**：需要akshare模块获取历史数据
2. **网络连接**：需要稳定的网络连接获取数据
3. **时间窗口**：信号只在9:25-9:31期间触发
4. **涨停阈值**：默认使用9.5%作为涨停判断标准

## 扩展性

### 自定义涨停阈值
```python
# 修改涨停判断阈值（在_check_previous_day_limit_up方法中）
is_limit_up = pct_change >= 9.5  # 可修改为其他值
```

### 自定义时间窗口
```python
# 修改信号触发时间窗口（在check_condition方法中）
if not ('09:25' <= time_str <= '09:31'):  # 可修改时间范围
    return False
```

### 自定义布林带参数
```python
# 修改布林带计算参数（在_calculate_prev_day_bollinger_high方法中）
window = 20  # 可修改周期
upper_band = ma20 + 2 * std  # 可修改标准差倍数
```
