# Windows平台移植指南

## 概述

本指南说明如何将macOS版本的股票分析程序移植到Windows平台，特别是音效资源的处理。

## Windows音效资源问题

### ❌ 问题
- Windows系统**没有**与macOS相同的系统音效文件
- Windows音效文件格式和路径与macOS完全不同
- 直接使用macOS音效路径在Windows上会失败

### ✅ 解决方案
使用独立的音效资源包，包含所有必要的音效文件。

## 音效资源文件

### 📁 资源目录结构
```
grid_strategy_tk/
├── resources/
│   └── sounds/
│       ├── buy_signal.wav          # 买入信号音效
│       ├── sell_signal.wav         # 卖出信号音效
│       ├── alert.wav               # 警告音效
│       ├── bollinger_breakthrough.wav  # 布林带突破音效
│       └── bollinger_breakdown.wav     # 布林带跌破音效
```

### 🎵 音效文件说明

| 文件名 | 原始macOS音效 | 用途 | 文件大小 |
|--------|---------------|------|----------|
| buy_signal.wav | Glass.aiff | 买入信号 | 162,504 字节 |
| sell_signal.wav | Sosumi.aiff | 卖出信号 | 151,862 字节 |
| alert.wav | Ping.aiff | 一般警告 | 148,242 字节 |
| bollinger_breakthrough.wav | Funk.aiff | 布林带突破 | 211,788 字节 |
| bollinger_breakdown.wav | Bottle.aiff | 布林带跌破 | 78,326 字节 |

## 移植步骤

### 1. 准备音效资源
在macOS上运行转换脚本：
```bash
python convert_sounds_for_windows.py
```

### 2. 复制音效文件
将 `resources/sounds/` 目录及其所有内容复制到Windows版本的相同位置。

### 3. 验证文件结构
确保Windows版本包含以下文件：
```
your_windows_app/
├── resources/
│   └── sounds/
│       ├── buy_signal.wav
│       ├── sell_signal.wav
│       ├── alert.wav
│       ├── bollinger_breakthrough.wav
│       └── bollinger_breakdown.wav
└── src/
    └── audio_notifier.py
```

### 4. 测试音效功能
在Windows上运行程序，测试所有音效是否正常播放。

## 技术实现

### 平台检测
```python
import platform

if platform.system() == "Darwin":  # macOS
    # 使用系统音效
    sound_path = "/System/Library/Sounds/Glass.aiff"
elif platform.system() == "Windows":  # Windows
    # 使用资源包音效
    sound_path = os.path.join(base_path, "buy_signal.wav")
```

### 音效格式转换
- **源格式**: macOS .aiff 文件
- **目标格式**: Windows .wav 文件
- **转换工具**: `afconvert` (macOS内置)
- **参数**: 16位小端整数，单声道

## 注意事项

### ✅ 优势
- 跨平台兼容性好
- 音效质量保持一致
- 不依赖系统音效文件
- 便于程序分发

### ⚠️ 注意事项
- 需要额外存储空间（约750KB）
- 音效文件需要随程序一起分发
- 确保文件路径正确

## 故障排除

### 常见问题
1. **音效不播放**
   - 检查 `resources/sounds/` 目录是否存在
   - 验证所有.wav文件是否完整
   - 确认文件路径正确

2. **文件路径错误**
   - 使用相对路径而非绝对路径
   - 确保路径分隔符正确（Windows使用`\`）

3. **音效格式不支持**
   - 确保使用.wav格式
   - 检查音频编码格式

## 更新记录

- **2024-09-26**: 创建Windows移植指南
- **2024-09-26**: 实现音效资源转换脚本
- **2024-09-26**: 添加平台检测逻辑
