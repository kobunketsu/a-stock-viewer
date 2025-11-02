# 🚀 分时图分时信号自定义系统

## 📖 概述

分时图分时信号自定义系统是一个灵活、可扩展的分时信号检测框架，允许用户自定义买入和卖出分时信号条件，并支持延迟确认机制来过滤假分时信号。

## 🏗️ 系统架构

### 核心组件

1. **IntradaySignalBase** - 分时信号基类（抽象类）
2. **IntradaySignalManager** - 分时信号管理器
3. **IntradayWindow** - 分时窗口主类

### 内置分时信号

- **MA25CrossMA50BuySignal** - MA25上穿MA50分时买入信号
- **RSISellSignal** - RSI分时卖出信号

## 🔧 使用方法

### 1. 基本信号操作

```python
from intraday_window import IntradayWindow, SignalBase

# 创建分时窗口
intraday_window = IntradayWindow(parent, "000001", "平安银行")

# 查看当前信号配置
intraday_window.list_signals()

# 清空所有自定义信号，恢复默认配置
intraday_window.clear_all_signals()
```

### 2. 添加自定义信号

```python
# 添加自定义买入信号
intraday_window.add_buy_signal(custom_buy_signal)

# 添加自定义卖出信号
intraday_window.add_sell_signal(custom_sell_signal)
```

### 3. 移除指定信号

```python
# 移除指定名称的买入信号
intraday_window.remove_buy_signal("信号名称")

# 移除指定名称的卖出信号
intraday_window.remove_sell_signal("信号名称")
```

## 📝 创建自定义信号

### 继承SignalBase类

```python
from intraday_window import SignalBase
from typing import Dict, Any

class CustomBuySignal(SignalBase):
    def __init__(self, name: str, delay_minutes: int = 2):
        super().__init__(name, delay_minutes)
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查信号条件"""
        # 实现你的信号逻辑
        pass
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证信号有效性（延迟检查）"""
        # 实现你的验证逻辑
        pass
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建信号数据"""
        # 可以重写此方法来添加自定义字段
        return super().create_signal_data(data, index)
```

### 必须实现的方法

1. **check_condition()** - 检查是否满足信号条件
2. **validate_signal()** - 延迟验证信号有效性

### 可选重写的方法

1. **create_signal_data()** - 创建包含自定义字段的信号数据

## 📊 数据字典结构

信号检测时，系统会提供以下数据：

```python
data = {
    'ma25_values': pd.Series,      # MA25移动平均线数据
    'ma50_values': pd.Series,      # MA50移动平均线数据
    'rsi_df': pd.DataFrame,        # RSI指标数据
    'close_prices': pd.Series,     # 收盘价数据
    'volumes': pd.Series,          # 成交量数据（如果有）
    'prev_close': float            # 前一交易日收盘价
}
```

## 🎯 示例：成交量突破信号

```python
class VolumeBreakoutSignal(SignalBase):
    def __init__(self, multiplier: float = 2.0):
        super().__init__(f"成交量突破({multiplier}倍)", delay_minutes=1)
        self.multiplier = multiplier
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        volumes = data.get('volumes')
        if volumes is None or index < 5:
            return False
        
        current_volume = volumes.iloc[index]
        avg_volume = volumes.iloc[max(0, index-5):index].mean()
        
        return current_volume >= avg_volume * self.multiplier
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        # 检查延迟时间内成交量是否保持在高位
        volumes = data.get('volumes')
        if volumes is None:
            return False
        
        for check_i in range(signal_index + 1, min(signal_index + 2, len(volumes))):
            if check_i < len(volumes):
                check_volume = volumes.iloc[check_i]
                avg_volume = volumes.iloc[max(0, check_i-5):check_i].mean()
                
                if check_volume < avg_volume * self.multiplier * 0.8:
                    return False
        
        return True
```

## ⚙️ 信号参数配置

### 延迟时间设置

```python
# 设置1分钟延迟
signal = CustomSignal(delay_minutes=1)

# 设置5分钟延迟
signal = CustomSignal(delay_minutes=5)
```

### 阈值参数

```python
# 成交量倍数阈值
volume_signal = VolumeBreakoutSignal(multiplier=2.5)

# RSI阈值
rsi_signal = RSISellSignal(rsi_5min_threshold=80, rsi_1min_threshold=90)
```

## 🔍 信号验证机制

### 延迟确认

1. **记录阶段** - 检测到信号条件时，记录为待确认信号
2. **等待阶段** - 等待指定的延迟时间
3. **验证阶段** - 延迟时间后，验证信号是否仍然有效
4. **确认阶段** - 通过验证的信号被确认为有效信号

### 验证逻辑示例

```python
def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
    # 检查延迟时间内是否仍然满足条件
    for check_i in range(signal_index + 1, signal_index + self.delay_minutes + 1):
        if self.check_condition(data, check_i):
            return False  # 重复满足条件，取消信号
    
    return True  # 信号有效
```

## 🚨 注意事项

1. **数据完整性** - 确保信号检测时有足够的历史数据
2. **性能考虑** - 复杂的信号逻辑可能影响性能
3. **信号冲突** - 避免添加过多相似的信号
4. **延迟设置** - 根据市场特点调整延迟时间

## 📈 最佳实践

1. **信号设计** - 设计简单、明确的信号条件
2. **参数调优** - 通过回测优化信号参数
3. **组合使用** - 结合多个信号提高准确性
4. **定期评估** - 定期评估信号效果并调整

## 🔧 故障排除

### 常见问题

1. **信号不触发** - 检查数据是否完整，条件是否合理
2. **假信号过多** - 增加延迟时间，优化验证逻辑
3. **性能问题** - 简化信号逻辑，减少计算复杂度

### 调试技巧

```python
# 启用详细日志
print(f"信号检测: 索引{index}, 条件检查结果: {result}")

# 检查数据状态
print(f"数据长度: {len(data.get('close_prices', []))}")
print(f"当前值: {current_value}")
```

## 📚 相关文档

- [分时窗口使用指南](./README.md)
- [技术指标计算](./INDICATORS.md)
- [回测系统](./BACKTEST.md)

## 🤝 贡献指南

欢迎提交自定义信号实现！请确保：

1. 继承自`SignalBase`类
2. 实现所有必需的方法
3. 添加适当的文档和注释
4. 包含使用示例

---

**版本**: 1.0.0  
**更新日期**: 2024年12月  
**维护者**: 开发团队
