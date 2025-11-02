"""
趋势判断配置模块
统一管理各种周期的最小连阳天数要求
"""

# 各周期的最小连阳天数要求 - 独立变量控制
DAILY_MIN_CONSECUTIVE_DAYS = 4    # 日级：4个连续上涨交易日
WEEKLY_MIN_CONSECUTIVE_DAYS = 4   # 周级：4个连续上涨周
MONTHLY_MIN_CONSECUTIVE_DAYS = 3  # 月级：3个连续上涨月（从4连阳改为3连阳）

# 其他周期的配置
QUARTERLY_MIN_CONSECUTIVE_DAYS = 4  # 季级：4个连续上涨季度
YEARLY_MIN_CONSECUTIVE_DAYS = 4     # 年级：4个连续上涨年
MIN5_MIN_CONSECUTIVE_DAYS = 4       # 5分钟级：4个连续上涨5分钟K线

# 各周期的最小连阳天数要求映射
TREND_REQUIREMENTS = {
    'day': DAILY_MIN_CONSECUTIVE_DAYS,
    'week': WEEKLY_MIN_CONSECUTIVE_DAYS,
    'month': MONTHLY_MIN_CONSECUTIVE_DAYS,
    'quarter': QUARTERLY_MIN_CONSECUTIVE_DAYS,
    'year': YEARLY_MIN_CONSECUTIVE_DAYS,
    '5min': MIN5_MIN_CONSECUTIVE_DAYS
}

def get_min_consecutive_days(period: str) -> int:
    """
    获取指定周期的最小连阳天数要求
    
    Args:
        period: 周期类型 ('day', 'week', 'month', 'quarter', 'year', '5min')
        
    Returns:
        int: 最小连阳天数要求
    """
    return TREND_REQUIREMENTS.get(period, 4)

def get_daily_min_consecutive_days() -> int:
    """获取日级最小连阳天数要求"""
    return DAILY_MIN_CONSECUTIVE_DAYS

def get_weekly_min_consecutive_days() -> int:
    """获取周级最小连阳天数要求"""
    return WEEKLY_MIN_CONSECUTIVE_DAYS

def get_monthly_min_consecutive_days() -> int:
    """获取月级最小连阳天数要求"""
    return MONTHLY_MIN_CONSECUTIVE_DAYS

def is_period_monthly(period: str) -> bool:
    """
    判断是否为月级周期
    
    Args:
        period: 周期类型
        
    Returns:
        bool: 是否为月级周期
    """
    return period == 'month'

def get_period_display_name(period: str) -> str:
    """
    获取周期的显示名称
    
    Args:
        period: 周期类型
        
    Returns:
        str: 显示名称
    """
    display_names = {
        'day': '日',
        'week': '周', 
        'month': '月',
        'quarter': '季',
        'year': '年',
        '5min': '5分钟'
    }
    return display_names.get(period, '未知')

def get_period_date_format(period: str) -> str:
    """
    获取周期的日期格式
    
    Args:
        period: 周期类型
        
    Returns:
        str: 日期格式字符串
    """
    if period == 'day':
        return '%Y-%m-%d'
    elif period in ['week', 'month', 'quarter', 'year']:
        return '%Y-%m'
    else:
        return '%Y-%m-%d'

# 配置版本信息
CONFIG_VERSION = "v1.1.0"
CONFIG_DESCRIPTION = "月级趋势从4连阳改为3连阳"

def get_config_info():
    """
    获取配置信息
    
    Returns:
        dict: 配置信息字典
    """
    return {
        'version': CONFIG_VERSION,
        'description': CONFIG_DESCRIPTION,
        'requirements': TREND_REQUIREMENTS.copy()
    }
