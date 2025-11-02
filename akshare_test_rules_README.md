# akshare测试规则强制应用指南

## 🚨 问题描述
Cursor在写测试时经常忘记遵守akshare-dev.mdc或.cursorrules中关于Python导入的撰写规则，导致akshare模板无法识别。

**特别强调**：必须确保Python版本和路径的正确性，避免环境冲突导致的问题。

## ✅ 解决方案

### 1. 规则配置优化
经过分析，发现两个.cursorrules文件存在大量重叠内容，已进行合并优化：
- `.cursorrules` - 项目根目录全局规则（已合并所有规则）
- ~~`grid_strategy_tk/.cursorrules` - 子项目规则（已删除，避免重复）~~
- `.cursor/rules/akshare-dev.mdc` - 原始规则文件
- `.cursor/rules/akshare-test-enforcement.mdc` - 强化规则文件

### 2. 强制测试模板
所有测试代码必须使用以下模板，**特别强调Python版本和路径验证**：

```python
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
```

### 3. 强制应用条件
以下情况必须无条件使用测试模板：
- ✅ 用户要求编写测试代码
- ✅ 用户要求验证功能
- ✅ 用户要求调试代码
- ✅ 用户要求运行Python代码
- ✅ 用户要求测试akshare功能
- ✅ 用户要求测试股票分析
- ✅ 用户要求测试技术指标
- ✅ 用户要求验证数据接口
- ✅ 任何涉及pandas、numpy、akshare的场景
- ✅ 任何测试相关的请求

### 4. 规则检查清单
AI助手必须检查以下项目：
- [ ] 是否使用了python -c命令？
- [ ] 是否包含了sys.path.insert路径设置？
- [ ] 是否验证了Python版本和路径？
- [ ] 是否打印了环境信息（版本、路径、包搜索路径）？
- [ ] 是否导入了pandas, numpy, akshare, datetime？
- [ ] 是否包含了try-except错误处理？
- [ ] 是否包含了traceback输出？
- [ ] 是否包含了print调试信息？

## 🔧 使用方法

### 验证规则配置
运行验证脚本检查规则是否正确配置：
```bash
python test_rule_enforcement.py
```

### 测试模板参考
参考 `grid_strategy_tk/test_template.py` 文件中的标准模板。

### 强制提醒
如果AI助手忘记应用规则，请明确提醒：
"请使用akshare测试模板，包含sys.path.insert和完整错误处理，并验证Python版本和路径"

## 🐍 Python环境验证

### 环境要求
- **Python版本**: 3.9.x
- **包路径**: `/opt/homebrew/lib/python3.9/site-packages`
- **执行路径**: `/opt/homebrew/Caskroom/miniforge/base/bin/python`

### 验证输出示例
```
Python版本: 3.9.15 | packaged by conda-forge | (main, Nov 22 2022, 08:48:25) 
[Clang 14.0.6 ]
Python路径: /opt/homebrew/Caskroom/miniforge/base/bin/python
包搜索路径: ['/opt/homebrew/lib/python3.9/site-packages', '', '/opt/homebrew/Caskroom/miniforge/base/lib/python39.zip']
测试开始...
akshare版本: 1.17.54
pandas版本: 2.1.4
numpy版本: 1.26.2
测试成功完成
```

### 环境验证的重要性
1. **避免版本冲突**: 确保使用正确的Python 3.9环境
2. **路径正确性**: 确保包搜索路径包含akshare等依赖
3. **环境隔离**: 避免与其他Python环境冲突
4. **调试便利**: 通过版本信息快速定位问题

## ⚠️ 重要提醒
- 此规则优先级最高，覆盖所有其他规则
- 任何测试代码都必须使用此模板
- 不允许任何例外情况
- 如果忘记应用，用户有权要求重新执行

## 📁 文件结构
```
A Stock/
├── .cursorrules                           # 全局规则文件（已合并所有规则）
├── .cursor/rules/
│   ├── akshare-dev.mdc                   # 原始规则文件
│   └── akshare-test-enforcement.mdc      # 强化规则文件
├── grid_strategy_tk/
│   └── test_template.py                  # 测试模板文件
└── akshare_test_rules_README.md          # 规则说明文档
```

## 🔄 规则合并说明
- **合并原因**: 两个.cursorrules文件存在大量重叠内容，维护成本高
- **合并结果**: 只保留根目录的.cursorrules文件，包含所有规则
- **优势**: 避免重复维护，规则优先级清晰，减少冲突
