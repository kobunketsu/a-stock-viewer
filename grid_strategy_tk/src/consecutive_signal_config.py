"""
连续信号配置模块
统一管理连涨和连跌信号的相关参数
"""

# 连涨信号配置
CONSECUTIVE_SURGE_CONFIG = {
    'consecutive_count': 5,  # 连续阳线数量
    'signal_name_prefix': '连涨',  # 信号名称前缀
    'display_text': '↗',  # 显示文本（斜向上箭头）
    'line_style': '-',  # 线条样式（实线）
    'line_color': 'red',  # 线条颜色（红色）
    'label_color': 'red',  # 标签颜色（红色）
    'line_width': 2,  # 线条宽度（加粗）
    'font_size': 16,  # 字体大小（大号）
    'label_offset_ratio': 0.1,  # 标签偏移比例（向下偏移10%数据范围）
    'font_weight': 'bold',  # 字体粗细（加粗）
    'bbox_style': None,  # 背景框样式（无背景框）
    # KDJ D值条件配置
    'kdj_d_min_value': 35,  # KDJ D值最小阈值（连涨信号需要D值>此值）
    'trend_lookback_minutes': 9,  # 趋势回看分钟数（9分钟前数据对比）
}

# 连跌信号配置
CONSECUTIVE_PLUNGE_CONFIG = {
    'consecutive_count': 5,  # 连续阴线数量
    'signal_name_prefix': '连跌',  # 信号名称前缀
    'display_text': '↘',  # 显示文本（斜向下箭头）
    'line_style': '-',  # 线条样式（实线）
    'line_color': 'green',  # 线条颜色（绿色）
    'label_color': 'green',  # 标签颜色（绿色）
    'line_width': 2,  # 线条宽度（加粗）
    'font_size': 16,  # 字体大小（大号）
    'label_offset_ratio': 0.1,  # 标签偏移比例（向下偏移10%数据范围）
    'font_weight': 'bold',  # 字体粗细（加粗）
    'bbox_style': None,  # 背景框样式（无背景框）
    # KDJ D值条件配置
    'kdj_d_max_value': 65,  # KDJ D值最大阈值（连跌信号需要D值<此值）
    'trend_lookback_minutes': 9,  # 趋势回看分钟数（9分钟前数据对比）
}

def get_surge_config():
    """获取连涨信号配置"""
    return CONSECUTIVE_SURGE_CONFIG.copy()

def get_plunge_config():
    """获取连跌信号配置"""
    return CONSECUTIVE_PLUNGE_CONFIG.copy()

def update_surge_config(**kwargs):
    """更新连涨信号配置"""
    global CONSECUTIVE_SURGE_CONFIG
    CONSECUTIVE_SURGE_CONFIG.update(kwargs)

def update_plunge_config(**kwargs):
    """更新连跌信号配置"""
    global CONSECUTIVE_PLUNGE_CONFIG
    CONSECUTIVE_PLUNGE_CONFIG.update(kwargs)
