import pandas as pd
from datetime import datetime
import akshare as ak

# 批次天数映射
BATCH_TO_DAYS_MAP = {
    1: 60,    # 买入次数最少，需要最长周期
    2: 30,    # 买入次数较少，需要较长周期
    3: 20,    # 买入次数中等，需要中等周期
    4: 10,    # 买入次数较多，需要较短周期
    5: 5      # 买入次数最多，需要最短周期
}

def build_segments(start_date: datetime, end_date: datetime, min_buy_times: int):
    """
    构建时间段
    @param start_date: 开始日期
    @param end_date: 结束日期
    @param min_buy_times: 最小买入次数（对应批次大小）
    @return: 时间段列表，每个元素为(开始日期, 结束日期)的元组
    """
    # 规范化min_buy_times
    if min_buy_times not in BATCH_TO_DAYS_MAP:
        min_buy_times = min(max(min_buy_times, 1), 5)
    
    segment_days = BATCH_TO_DAYS_MAP[min_buy_times]
    
    # 如果开始日期晚于结束日期，直接返回单个时间段
    if start_date > end_date:
        return [(start_date, end_date)]
    
    # 如果是同一天，直接返回单个时间段
    if start_date == end_date:
        return [(start_date, end_date)]
    
    # 获取交易日历
    try:
        df_calendar = ak.tool_trade_date_hist_sina()
        if df_calendar.empty:
            return [(start_date, end_date)]
            
        df_calendar['trade_date'] = pd.to_datetime(df_calendar['trade_date'])
        mask = (df_calendar['trade_date'] >= pd.to_datetime(start_date)) & \
               (df_calendar['trade_date'] <= pd.to_datetime(end_date))
        trading_days = pd.DatetimeIndex(df_calendar.loc[mask].sort_values('trade_date')['trade_date'].values)
        
        if len(trading_days) == 0:
            return [(start_date, end_date)]
            
    except Exception as e:
        print(f"获取交易日历失败: {e}")
        trading_days = pd.date_range(start=start_date, end=end_date, freq='B')
    
    # 构建时间段
    segments = []
    total_days = len(trading_days)
    start_idx = 0
    
    while start_idx < total_days:
        end_idx = min(start_idx + segment_days, total_days)
        seg_start = trading_days[start_idx]
        seg_end = trading_days[end_idx - 1]
        segments.append((seg_start, seg_end))
        start_idx = end_idx
    
    return segments

def get_segment_days(min_buy_times: int) -> int:
    """
    获取对应的天数
    @param min_buy_times: 最小买入次数（对应批次大小）
    @return: 对应的天数
    """
    if min_buy_times not in BATCH_TO_DAYS_MAP:
        min_buy_times = min(max(min_buy_times, 1), 5)
    return BATCH_TO_DAYS_MAP[min_buy_times] 