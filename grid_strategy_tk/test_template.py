#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
akshare测试代码标准模板
此文件作为测试代码的标准模板，确保所有测试都遵循相同的格式和错误处理规范
"""

# 标准测试模板 - 必须使用
python -c "
import sys
# 强制设置Python包路径 - 确保使用正确的Python 3.9环境
sys.path.insert(0, '/opt/homebrew/lib/python3.9/site-packages')

# 验证Python版本和路径 - 必须包含
print(f'Python版本: {sys.version}')
print(f'Python路径: {sys.executable}')
print(f'包搜索路径: {sys.path[:3]}')

import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta

# 测试代码内容
print('测试开始...')
try:
    # 具体测试逻辑
    pass
except Exception as e:
    print(f'错误: {e}')
    import traceback
    traceback.print_exc()
"

# 示例：测试股票数据获取
def example_stock_data_test():
    """示例：测试股票数据获取"""
    python -c "
import sys
sys.path.insert(0, '/opt/homebrew/lib/python3.9/site-packages')

import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta

print('测试开始...')
try:
    # 获取股票实时行情
    stock_data = ak.stock_zh_a_spot_em()
    print(f'股票数据获取成功，共{len(stock_data)}条记录')
    print(f'前5条数据:')
    print(stock_data.head())
except Exception as e:
    print(f'错误: {e}')
    import traceback
    traceback.print_exc()
"

# 示例：测试技术指标计算
def example_technical_indicators_test():
    """示例：测试技术指标计算"""
    python -c "
import sys
sys.path.insert(0, '/opt/homebrew/lib/python3.9/site-packages')

import pandas as pd
import numpy as np
import akshare as ak
from datetime import datetime, timedelta

print('测试开始...')
try:
    # 获取股票历史数据
    data = ak.stock_zh_a_hist(symbol='000001', period='daily', start_date='20240101', end_date='20241231')
    print(f'获取到{len(data)}条历史数据')
    
    # 计算简单移动平均
    data['MA5'] = data['收盘'].rolling(window=5).mean()
    data['MA20'] = data['收盘'].rolling(window=20).mean()
    
    print('技术指标计算成功')
    print(data[['日期', '收盘', 'MA5', 'MA20']].tail())
except Exception as e:
    print(f'错误: {e}')
    import traceback
    traceback.print_exc()
"

# 强制规则检查清单
"""
AI助手必须检查以下项目：
- [ ] 是否使用了python -c命令？
- [ ] 是否包含了sys.path.insert路径设置？
- [ ] 是否验证了Python版本和路径？
- [ ] 是否打印了环境信息（版本、路径、包搜索路径）？
- [ ] 是否导入了pandas, numpy, akshare, datetime？
- [ ] 是否包含了try-except错误处理？
- [ ] 是否包含了traceback输出？
- [ ] 是否包含了print调试信息？
"""
