# 增强的前高前低检测算法

## 问题背景

原有的前高前低检测算法存在以下问题：

1. **依赖完整Peak形成**：使用`scipy.signal.find_peaks`需要完整的峰值形态才能识别
2. **参数过于严格**：`distance=5`要求峰值间隔5个交易日，`prominence`要求足够的突出度
3. **无法检测当日数据**：只处理历史日线数据，无法检测当日分时数据中的前高前低
4. **当日数据未完全形成时无法检测**：当股价在当日形成临时高点/低点但还未形成完整peak时，算法无法识别

## 解决方案

### 1. 多层次检测机制

实现了三种检测策略：

- **日线数据检测**：优化原有算法，降低检测阈值
- **分时数据检测**：专门针对当日分时数据的峰值检测
- **实时突破检测**：检测当前价格是否突破历史高低点

### 2. 增强的峰值检测算法

#### 核心特性

```python
class EnhancedPeakDetector:
    """增强的峰值检测器
    
    支持多种数据类型的峰值检测：
    1. 日线数据：完整的历史peak检测
    2. 分时数据：当日部分数据的peak检测  
    3. 实时数据：当前价格的突破检测
    """
```

#### 检测参数优化

| 数据类型 | distance | prominence_factor | min_prominence |
|---------|----------|------------------|----------------|
| 日线数据 | 5个交易日 | 0.1 | 价格标准差的5% |
| 分时数据 | 10个数据点 | 0.05 | 价格标准差的2% |
| 实时数据 | N/A | N/A | N/A |

### 3. 分时数据检测能力

#### 关键改进

1. **降低检测阈值**：分时数据使用更短的间隔和更低的突出度要求
2. **支持部分数据**：即使当日数据未完全形成，也能检测到临时高点/低点
3. **实时更新**：随着分时数据的更新，能够动态识别新的前高前低

#### 检测逻辑

```python
def _detect_intraday_peaks(self, data: pd.DataFrame, current_price: Optional[float]) -> Dict[str, Any]:
    """检测分时数据的峰值（当日部分数据）"""
    # 分时数据使用更短的检测窗口和更低的阈值
    high_peaks = self._find_peaks_optimized(
        high_prices,
        prominence_factor=0.05,  # 降低突出度要求
        distance=10,  # 10个数据点间隔（约10分钟）
        min_prominence=high_prices.std() * 0.02  # 进一步降低最小突出度
    )
```

### 4. 集成到现有系统

#### 分时窗口集成

在`intraday_window.py`中集成了增强检测，但**只使用前一个交易日的日级前高前低数据**：

```python
# 分时窗口只使用前一个交易日的日级前高前低数据
# 不检测当日分时数据中的临时高点/低点
print(f"[DEBUG] 分时窗口 - 只使用前一个交易日的日级前高前低数据")

# 计算前高双价格（历史数据）
dual_prices = get_previous_high_dual_prices(
    symbol=symbol,
    current_date=self.trade_date_str,
    months_back=12,
    security_type=security_type
)
```

**重要说明**：分时窗口不检测当日分时数据中的临时高点/低点，只显示基于历史日线数据计算的前高前低。

#### 历史数据检测优化

在`trading_utils.py`中优化了原有算法：

```python
# 优先使用增强检测算法
if use_enhanced_detection:
    try:
        result = get_enhanced_high_low(df, "daily", current_price)
        if "error" not in result and result.get("latest_high"):
            return float(latest_high['price'])
    except Exception as e:
        # 回退到原有算法
```

## 测试结果

### 测试场景

1. **日线数据测试**：366天模拟数据，成功检测到1个高点，2个低点
2. **分时数据测试**：240分钟模拟数据，成功检测到7个高点，18个低点
3. **实时突破测试**：成功检测到新高突破（3.04%）和新低突破（5.03%）

### 关键优势

1. **当日数据检测**：能够在当日分时数据中检测到前高前低
2. **部分数据支持**：即使数据未完全形成，也能识别临时高点/低点
3. **动态更新**：随着实时数据的更新，能够动态调整前高前低
4. **向后兼容**：保持与原有系统的兼容性，增强检测失败时自动回退

## 使用方法

### 基本使用

```python
from enhanced_peak_detection import detect_enhanced_peaks, get_enhanced_high_low

# 检测日线数据峰值
result = detect_enhanced_peaks(daily_data, "daily", current_price)

# 检测分时数据峰值
result = detect_enhanced_peaks(intraday_data, "intraday", current_price)

# 检测实时突破
result = detect_enhanced_peaks(historical_data, "realtime", current_price)

# 获取最近高低点
result = get_enhanced_high_low(data, "daily", current_price)
```

### 在分时窗口中使用

分时窗口会自动使用增强检测算法：

1. 首先尝试检测当日分时数据的前高前低
2. 如果检测成功，使用分时数据结果
3. 如果检测失败，回退到历史数据检测

## 配置参数

### 可调整参数

```python
# 日线数据检测参数
DAILY_DISTANCE = 5  # 峰值间隔（交易日）
DAILY_PROMINENCE_FACTOR = 0.1  # 突出度因子
DAILY_MIN_PROMINENCE = 0.05  # 最小突出度（价格标准差的百分比）

# 分时数据检测参数  
INTRADAY_DISTANCE = 10  # 峰值间隔（数据点）
INTRADAY_PROMINENCE_FACTOR = 0.05  # 突出度因子
INTRADAY_MIN_PROMINENCE = 0.02  # 最小突出度（价格标准差的百分比）
```

## 注意事项

1. **数据质量**：确保输入数据的质量，避免异常值影响检测结果
2. **参数调优**：根据具体股票特性调整检测参数
3. **性能考虑**：分时数据检测频率较高，注意性能影响
4. **错误处理**：增强检测失败时会自动回退到原有算法

## 未来改进

1. **机器学习优化**：使用ML算法优化峰值检测参数
2. **多时间框架**：支持多时间框架的峰值检测
3. **实时预警**：基于检测结果提供实时预警功能
4. **可视化增强**：在图表中更直观地显示检测结果
