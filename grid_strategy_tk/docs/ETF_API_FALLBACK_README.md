# ETF数据获取多API备用机制

## 概述

为了解决`fund_etf_spot_em`接口经常出现连接问题导致无法获取到数据的问题，我们实现了一个多API备用机制，支持东财、同花顺、新浪三个数据源，自动切换备用API。

## 功能特性

### 1. 多API备用机制
- **东财API** (`fund_etf_spot_em`) - 主要数据源
- **同花顺API** (`fund_etf_spot_ths`) - 第一备用
- **新浪API** (`fund_etf_category_sina`) - 第二备用

### 2. 自动故障转移
- 当主API失败时，自动尝试备用API
- 按优先级顺序：东财 → 同花顺 → 新浪
- 只要有一个API成功，就返回数据

### 3. 数据标准化
- 不同API返回的数据格式不同
- 自动标准化列名以匹配东财格式
- 确保接口一致性

### 4. 缓存机制
- 5分钟数据缓存，减少API调用
- 支持缓存开关控制
- 提高响应速度

### 5. 性能监控
- 记录各API的成功率和响应时间
- 错误日志记录和分析
- 健康状态监控

## 文件结构

```
src/
├── etf_data_fetcher.py              # 主要数据获取器
├── etf_data_fetcher_standalone.py   # 独立版本（不依赖akshare）
├── etf_api_monitor.py               # API监控和日志
└── akshare_wrapper.py               # 更新的包装器

test_etf_standalone.py               # 独立测试脚本
test_etf_api_fallback.py             # 完整测试脚本
```

## 使用方法

### 基本使用

```python
from src.etf_data_fetcher import get_etf_spot_data, get_etf_by_code

# 获取所有ETF数据
df = get_etf_spot_data(use_cache=True)

# 获取特定ETF数据
etf_data = get_etf_by_code('159919', use_cache=True)
```

### 在现有代码中集成

原有的代码：
```python
import akshare as ak
df = ak.fund_etf_spot_em()
```

更新后的代码：
```python
from src.etf_data_fetcher import get_etf_spot_data
df = get_etf_spot_data(use_cache=True)
```

### 监控API状态

```python
from src.etf_api_monitor import print_etf_api_status, get_etf_api_status

# 打印状态报告
print_etf_api_status()

# 获取状态数据
status = get_etf_api_status()
```

## API接口说明

### 东财API (`fund_etf_spot_em`)
- **目标地址**: https://quote.eastmoney.com/center/gridlist.html#fund_etf
- **描述**: 东方财富-ETF 实时行情
- **特点**: 数据最全面，包含37个字段
- **问题**: 经常出现连接超时

### 同花顺API (`fund_etf_spot_ths`)
- **目标地址**: https://fund.10jqka.com.cn/datacenter/jz/kfs/etf/
- **描述**: 同花顺理财-基金数据-每日净值-ETF-实时行情
- **特点**: 需要指定日期参数
- **问题**: 可能有API限制

### 新浪API (`fund_etf_category_sina`)
- **目标地址**: http://vip.stock.finance.sina.com.cn/fund_center/index.html#jjhqetf
- **描述**: 新浪财经-基金列表及行情数据
- **特点**: 稳定性较好
- **问题**: 数据字段较少

## 数据字段映射

### 标准字段（东财格式）
- `代码` - ETF代码
- `名称` - ETF名称
- `最新价` - 当前价格
- `昨收` - 昨日收盘价
- `涨跌额` - 涨跌金额
- `涨跌幅` - 涨跌百分比

### 同花顺字段映射
```python
{
    '基金代码': '代码',
    '基金名称': '名称',
    '当前-单位净值': '最新价',
    '前一日-单位净值': '昨收',
    '增长值': '涨跌额',
    '增长率': '涨跌幅'
}
```

### 新浪字段映射
```python
{
    '代码': '代码',
    '名称': '名称',
    '最新价': '最新价',
    '昨收': '昨收',
    '涨跌额': '涨跌额',
    '涨跌幅': '涨跌幅'
}
```

## 性能监控

### 统计信息
- 总请求数
- 成功率
- 平均响应时间
- 各API健康状态

### 错误日志
- 错误时间戳
- API名称
- 错误信息
- 响应时间

### 健康状态
- 系统整体健康状态
- 连续失败次数
- 最后成功请求时间

## 测试

### 运行独立测试
```bash
python test_etf_standalone.py
```

### 运行完整测试
```bash
python test_etf_api_fallback.py
```

## 配置选项

### 缓存设置
```python
# 缓存超时时间（秒）
cache_timeout = 300  # 5分钟

# 是否使用缓存
use_cache = True
```

### API成功率设置
```python
# 各API模拟成功率（仅用于测试）
eastmoney_success_rate = 0.7  # 70%
ths_success_rate = 0.6        # 60%
sina_success_rate = 0.9       # 90%
```

## 错误处理

### 常见错误类型
1. **连接超时** - `Connection timeout`
2. **API限制** - `API rate limit exceeded`
3. **服务器错误** - `Server internal error`
4. **数据格式错误** - `Data format error`

### 错误恢复策略
1. 自动重试下一个API
2. 记录错误日志
3. 更新统计信息
4. 返回空DataFrame（如果所有API都失败）

## 最佳实践

### 1. 使用缓存
```python
# 推荐：使用缓存减少API调用
df = get_etf_spot_data(use_cache=True)
```

### 2. 错误处理
```python
try:
    df = get_etf_spot_data()
    if df.empty:
        print("未获取到数据")
    else:
        print(f"获取到 {len(df)} 条数据")
except Exception as e:
    print(f"获取数据失败: {e}")
```

### 3. 监控API状态
```python
# 定期检查API状态
from src.etf_api_monitor import print_etf_api_status
print_etf_api_status()
```

## 更新日志

### v1.0.0 (2025-09-18)
- 实现多API备用机制
- 支持东财、同花顺、新浪三个数据源
- 添加数据标准化功能
- 实现缓存机制
- 添加性能监控和错误日志
- 更新现有代码集成新机制

## 注意事项

1. **依赖问题**: 如果akshare库有依赖问题，可以使用独立版本
2. **网络环境**: 不同网络环境下各API的可用性可能不同
3. **数据一致性**: 不同API的数据可能有细微差异
4. **缓存更新**: 缓存数据可能不是最新的，需要定期刷新

## 故障排除

### 问题1: 所有API都失败
**解决方案**: 检查网络连接，稍后重试

### 问题2: 数据格式不一致
**解决方案**: 检查数据标准化函数，更新字段映射

### 问题3: 缓存数据过期
**解决方案**: 清除缓存或设置更短的超时时间

### 问题4: 性能问题
**解决方案**: 启用缓存，减少API调用频率
