# API频率限制和错误处理机制

## 概述

为了解决API调用频次限制导致的连接错误问题，我们对 `AKShareWrapper` 类进行了增强，添加了智能的频率控制和错误处理机制。

## 主要特性

### 1. 频率限制控制
- **最小调用间隔**: 默认1秒，避免过于频繁的API调用
- **自动等待**: 在调用间隔不足时自动等待
- **可配置**: 可以通过修改 `_min_call_interval` 调整间隔

### 2. 连接错误处理
- **自动重试**: 连接失败时自动重试，最多2次
- **递增等待**: 重试间隔递增（2秒、4秒）
- **错误识别**: 智能识别连接相关错误

### 3. 冷却期机制
- **错误计数**: 连续连接错误达到3次时触发冷却期
- **冷却时间**: 默认60秒，期间所有API调用返回空数据
- **自动恢复**: 冷却期结束后自动恢复正常调用

### 4. 状态监控
- **实时状态**: 可以随时查看API调用状态
- **手动重置**: 支持手动重置API状态
- **详细日志**: 记录所有API调用和错误信息

## 使用方法

### 基本使用

```python
from akshare_wrapper import AKShareWrapper

# 创建包装器实例
wrapper = AKShareWrapper()

# 正常调用API（自动处理频率限制和错误）
stock_data = wrapper.stock_zh_a_hist(symbol="000001", period="daily")
```

### 状态监控

```python
# 检查API状态
status = wrapper.get_api_status()
print(f"是否在冷却期: {status['is_in_cooldown']}")
print(f"剩余冷却时间: {status['remaining_cooldown']:.1f}秒")
print(f"错误计数: {status['error_count']}/{status['max_consecutive_errors']}")

# 手动重置状态（如果需要）
if status['is_in_cooldown']:
    wrapper.reset_api_status()
```

### 错误处理示例

```python
import time

# 连续调用API
symbols = ['000001', '000002', '000858']
for symbol in symbols:
    print(f"获取 {symbol} 数据...")
    
    # 检查是否在冷却期
    status = wrapper.get_api_status()
    if status['is_in_cooldown']:
        print(f"API在冷却期，剩余 {status['remaining_cooldown']:.1f} 秒")
        break
    
    # 调用API
    data = wrapper.stock_zh_a_hist(symbol=symbol, period="daily")
    if data.empty:
        print(f"获取 {symbol} 失败，可能遇到连接错误")
    else:
        print(f"成功获取 {symbol} 数据，{len(data)} 条记录")
```

## 配置参数

### 可调整的参数

```python
# 在 __init__ 方法中修改这些参数
self._min_call_interval = 1.0          # 最小调用间隔（秒）
self._max_consecutive_errors = 3        # 最大连续错误次数
self._cooldown_duration = 60.0          # 冷却期持续时间（秒）
```

### 建议的配置

- **保守模式**: `_min_call_interval = 2.0`, `_max_consecutive_errors = 2`
- **平衡模式**: `_min_call_interval = 1.0`, `_max_consecutive_errors = 3` (默认)
- **激进模式**: `_min_call_interval = 0.5`, `_max_consecutive_errors = 5`

## 错误类型识别

系统会自动识别以下类型的连接错误：

- `Connection aborted`
- `Remote end closed connection`
- `Remote disconnected`
- `Connection reset`
- `Timeout`
- `Network is unreachable`
- `Name or service not known`

## 日志记录

系统会记录详细的API调用日志：

```
2025-09-23 20:50:19,378 - akshare_wrapper - INFO - 等待 2 秒后重试...
2025-09-23 20:50:21,380 - akshare_wrapper - ERROR - API调用失败 (尝试 2/3): ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2025-09-23 20:50:23,382 - akshare_wrapper - WARNING - API调用进入冷却期，持续 60.0 秒
```

## 最佳实践

### 1. 批量数据获取
```python
# 在批量获取数据时，让系统自动处理频率限制
symbols = ['000001', '000002', '000858', '002415', '300059']
for symbol in symbols:
    data = wrapper.stock_zh_a_hist(symbol=symbol, period="daily")
    if not data.empty:
        # 处理数据
        process_data(data)
```

### 2. 错误恢复
```python
# 检查API状态，必要时等待或重置
status = wrapper.get_api_status()
if status['is_in_cooldown']:
    print(f"API在冷却期，等待 {status['remaining_cooldown']:.1f} 秒...")
    time.sleep(status['remaining_cooldown'])
    # 或者手动重置
    wrapper.reset_api_status()
```

### 3. 监控和调试
```python
# 定期检查API状态
def monitor_api_status(wrapper):
    status = wrapper.get_api_status()
    if status['error_count'] > 0:
        print(f"API错误计数: {status['error_count']}")
    if status['is_in_cooldown']:
        print(f"API在冷却期，剩余 {status['remaining_cooldown']:.1f} 秒")
```

## 故障排除

### 常见问题

1. **API调用总是返回空数据**
   - 检查是否在冷却期：`wrapper.get_api_status()['is_in_cooldown']`
   - 等待冷却期结束或手动重置：`wrapper.reset_api_status()`

2. **调用频率仍然过高**
   - 增加 `_min_call_interval` 参数
   - 在代码中添加额外的等待时间

3. **连接错误频繁发生**
   - 检查网络连接
   - 增加 `_max_consecutive_errors` 参数
   - 增加 `_cooldown_duration` 参数

### 调试技巧

```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 监控API状态变化
def debug_api_calls(wrapper):
    for i in range(10):
        status_before = wrapper.get_api_status()
        data = wrapper.stock_zh_a_hist(symbol="000001", period="daily")
        status_after = wrapper.get_api_status()
        
        print(f"调用 {i+1}: 错误计数 {status_before['error_count']} -> {status_after['error_count']}")
        if status_after['is_in_cooldown']:
            print("进入冷却期！")
            break
```

## 更新日志

- **v1.0**: 初始版本，添加基本的频率限制和错误处理
- **v1.1**: 添加冷却期机制和状态监控
- **v1.2**: 优化错误识别和重试逻辑
- **v1.3**: 添加详细日志记录和调试功能

