# ETF分析工具

使用力导向图绘制所有ETF之间的全局关系图

## 功能特性

### 基础功能
- ETF基本信息查询
- 实时行情监控
- 历史数据分析
- 技术指标计算

### 数据分析
- 成交量分析
- 趋势识别
- 波动率计算
- 相关性分析

### 图表展示
- K线图展示
  - 支持日/周/月线切换
  - MA均线(5,10,20日)
  - KDJ指标
  - 成交量柱状图
  - 赚钱效应得分
  - 十字光标定位
  - 数据缩放功能
  - 数据导出功能
  - 最新交易日数据自动显示
  - 手动触发赚钱效应计算

- 雷达图分析
  - 成交量/价格相关性
  - 持仓稳定性
  - 套利影响
  - 成交量健康度
  - 动量趋势
  - 波动质量

### ETF对比分析
- 多ETF数据对比
- 差异值计算
- 涨幅对比
- 成交数据比较

### 性能优化
- 多线程数据处理
- 数据缓存机制
- 向量化计算
- 耗时统计分析

# Grid Strategy TK

网格交易策略工具

## 开发环境要求

- Python 3.9
- pip 包管理器

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行程序

```bash
python src/app.py
```

## Windows打包指南

1. 环境准备
   - 安装Python 3.9（[官方下载链接](https://www.python.org/downloads/release/python-3913/)）
   - 确保Python和pip已添加到系统环境变量

2. 安装依赖
   ```bash
   # 打开命令提示符，进入项目目录
   cd grid_strategy_tk
   
   # 安装依赖
   pip install -r requirements.txt
   ```

3. 执行打包
   ```bash
   # 执行打包命令
   python build.py
   ```

4. 打包后文件处理
   - 可执行文件位于`dist`目录下
   - 将以下文件/目录复制到可执行文件同级目录：
     * data/cache
     * data/results
     * src/assets
     * src/locales

5. 运行要求
   - Windows 10/11
   - 需要安装Visual C++ Redistributable（[下载链接](https://aka.ms/vs/17/release/vc_redist.x64.exe)）
   - 建议将程序放在英文路径下运行
   - 首次运行时可能需要允许防火墙访问

## 常见问题

1. 如果运行时提示缺少DLL文件：
   - 安装Visual C++ Redistributable
   - 确保Windows系统已更新到最新版本

2. 如果出现中文乱码：
   - 确保Windows系统的区域设置为中文
   - 检查字体文件是否完整

3. 如果程序无法启动：
   - 检查是否以管理员身份运行
   - 查看Windows事件查看器中的错误日志

## 技术支持

如有问题，请提交Issue或联系开发团队。