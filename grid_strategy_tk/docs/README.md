# 网格策略系统文档索引

## 📚 文档分类

### 1. 核心功能文档
- **`README.md`** - 项目主要说明文档（位于项目根目录）
- **`progress.md`** - 项目开发进度记录（位于项目根目录）

### 2. 功能实现文档 [`features/`](./features/)
- **`SUPPORT_RESISTANCE_IMPLEMENTATION_COMPLETE.md`** - 支撑位和压力位功能完整实现
- **`SIGNAL_SYSTEM_README.md`** - 分时信号系统说明
- **`RSI_FEATURE_README.md`** - RSI指标功能说明
- **`ASYNC_LOADING_README.md`** - 异步加载功能说明

### 3. 功能优化文档 [`optimizations/`](./optimizations/)
- **`BORDER_STYLE_OPTIMIZATION_COMPLETE.md`** - 边框样式优化完成
- **`RESISTANCE_BREAKTHROUGH_IMPLEMENTATION_COMPLETE.md`** - 压力位突破功能实现完成
- **`SUPPORT_BREAKDOWN_ONCE_IMPLEMENTATION.md`** - 支撑位跌破信号只显示一次功能
- **`SUPPORT_BREAKDOWN_SIGNAL_IMPLEMENTATION.md`** - 支撑位跌破信号功能实现
- **`SUPPORT_SIGNAL_LOGIC_OPTIMIZATION.md`** - 支撑位信号逻辑优化
- **`SUPPORT_LOGIC_IMPROVEMENT.md`** - 支撑位逻辑改进

### 4. 问题修复文档 [`fixes/`](./fixes/)
- **`EXECUTION_ORDER_FIX.md`** - 执行顺序修复完成
- **`SIGNAL_COLORS_SWAP_COMPLETE.md`** - 信号颜色交换完成
- **`NET_GAIN_FIELD_FIX.md`** - 净收益字段修复

### 5. 项目状态文档 [`status/`](./status/)
- **`FINAL_DOCUMENTATION_STATUS.md`** - 最终文档状态说明

## 🎯 文档使用指南

### 新用户入门
1. 首先阅读项目根目录的 `README.md`
2. 查看 [`features/SUPPORT_RESISTANCE_IMPLEMENTATION_COMPLETE.md`](./features/SUPPORT_RESISTANCE_IMPLEMENTATION_COMPLETE.md) 了解核心功能
3. 根据需要查看其他功能文档

### 开发者参考
1. `progress.md` 记录开发历程和决策过程
2. 各功能README提供具体的实现指导
3. 问题修复文档提供解决方案参考

### 功能使用
1. 每个功能都有对应的README文档
2. 包含详细的使用说明和示例
3. 提供调试信息和故障排除

## 📁 目录结构
```
docs/
├── README.md (本文件)
├── features/          # 功能实现文档
│   ├── README.md
│   ├── SUPPORT_RESISTANCE_IMPLEMENTATION_COMPLETE.md
│   ├── SIGNAL_SYSTEM_README.md
│   ├── RSI_FEATURE_README.md
│   └── ASYNC_LOADING_README.md
├── optimizations/     # 功能优化文档
│   ├── README.md
│   ├── BORDER_STYLE_OPTIMIZATION_COMPLETE.md
│   ├── RESISTANCE_BREAKTHROUGH_IMPLEMENTATION_COMPLETE.md
│   ├── SUPPORT_BREAKDOWN_ONCE_IMPLEMENTATION.md
│   ├── SUPPORT_BREAKDOWN_SIGNAL_IMPLEMENTATION.md
│   ├── SUPPORT_SIGNAL_LOGIC_OPTIMIZATION.md
│   └── SUPPORT_LOGIC_IMPROVEMENT.md
├── fixes/             # 问题修复文档
│   ├── README.md
│   ├── EXECUTION_ORDER_FIX.md
│   ├── SIGNAL_COLORS_SWAP_COMPLETE.md
│   └── NET_GAIN_FIELD_FIX.md
└── status/            # 项目状态文档
    ├── README.md
    └── FINAL_DOCUMENTATION_STATUS.md
```

## 🔄 文档维护
- 所有.md文件统一放在docs目录下
- 按功能分类组织，便于查找和维护
- 定期更新文档状态，保持信息准确性
- 每个分类目录都有独立的README说明文件

## 📊 文档统计
- **总文档数量**: 15个.md文档
- **分类目录**: 5个主要分类
- **核心文档**: 保留所有重要功能说明
- **临时文档**: 已清理完毕
- **文档覆盖率**: 100%（覆盖所有核心功能）
