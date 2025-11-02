# 分时窗口前高前低检测说明

## 核心原则

**分时窗口只使用前一个交易日的日级前高前低数据，不检测当日分时数据中的临时高点/低点。**

## 实现逻辑

### 1. 数据来源

分时窗口的前高前低数据完全基于历史日线数据计算：

```python
# 分时窗口只使用前一个交易日的日级前高前低数据
# 不检测当日分时数据中的临时高点/低点
print(f"[DEBUG] 分时窗口 - 只使用前一个交易日的日级前高前低数据")

# 计算前高双价格（历史数据）
dual_prices = get_previous_high_dual_prices(
    symbol=symbol,
    current_date=self.trade_date_str,
    months_back=12,  # 回溯12个月
    security_type=security_type
)
```

### 2. 检测范围

- **前高检测**：基于过去12个月的日线数据
- **前低检测**：基于过去12个月的日线数据
- **数据验证**：前低不能高于上个交易日收盘价

### 3. 不检测的内容

分时窗口**不会**检测以下内容：
- 当日分时数据中的临时高点
- 当日分时数据中的临时低点
- 实时价格突破
- 分时级别的峰值

## 代码位置

### 主要文件

- `src/intraday_window.py` - 分时窗口主文件
- `src/trading_utils.py` - 前高前低计算函数
- `src/enhanced_peak_detection.py` - 增强检测算法（分时窗口不使用）

### 关键函数

1. **前高检测**：
   ```python
   # 在 intraday_window.py 的 _update_data() 方法中
   dual_prices = get_previous_high_dual_prices(
       symbol=symbol,
       current_date=self.trade_date_str,
       months_back=12,
       security_type=security_type
   )
   ```

2. **前低检测**：
   ```python
   # 在 intraday_window.py 的 _update_data() 方法中
   dual_prices = get_previous_low_dual_prices(
       symbol=symbol,
       current_date=self.trade_date_str,
       months_back=12,
       security_type=security_type
   )
   ```

## 数据流程

```
历史日线数据 → 峰值检测算法 → 前高前低价格 → 分时窗口显示
     ↑
   12个月回溯
```

## 验证机制

### 前低验证

```python
# 验证前低不能高于上个交易日收盘价
if prev_close is not None:
    if entity_low_price > prev_close:
        print(f"[WARNING] 前低实体最低价({entity_low_price:.3f})高于上个交易日收盘价({prev_close:.3f})，跳过前低计算")
        self.previous_low_dual_prices = None
        self.previous_low_price = None
```

### 前高验证

前高价格基于历史数据计算，无需额外验证。

## 显示效果

分时窗口会在图表上显示：
- **前高线**：基于历史日线数据计算的前高价格
- **前低线**：基于历史日线数据计算的前低价格
- **支撑带/阻力带**：双价格区间

## 注意事项

1. **数据一致性**：确保使用的前高前低数据来自同一数据源
2. **时间同步**：前高前低数据基于交易日，与分时数据时间轴对应
3. **性能考虑**：历史数据计算在窗口初始化时进行，避免重复计算
4. **错误处理**：计算失败时提供明确的错误信息

## 与增强检测算法的关系

虽然系统包含增强的峰值检测算法（`enhanced_peak_detection.py`），但分时窗口**不使用**该算法检测当日分时数据。增强算法主要用于：

1. 算法验证和测试
2. 其他模块的峰值检测需求
3. 实时突破检测（非分时窗口使用）

分时窗口严格遵循"只使用前一个交易日的日级前高前低数据"的原则。

