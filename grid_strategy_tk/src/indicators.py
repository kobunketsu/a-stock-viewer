"""技术指标计算工具"""

from typing import Optional

import numpy as np
import pandas as pd


def calculate_rsi(df: pd.DataFrame, period: int = 14, price_col: str = "close") -> pd.Series:
    """计算RSI指标
    
    :param df: 包含价格数据的DataFrame
    :param period: RSI计算周期，默认14
    :param price_col: 价格列名，默认"close"
    :return: RSI值序列
    """
    try:
        if df.empty or len(df) < period + 1:
            return pd.Series(index=df.index, data=np.nan)
        
        # 计算价格变化
        price_changes = df[price_col].diff()
        
        # 计算上涨和下跌
        gains = price_changes.where(price_changes > 0, 0)
        losses = -price_changes.where(price_changes < 0, 0)
        
        # 使用指数移动平均（EMA）计算平均上涨和下跌
        alpha = 1.0 / period
        avg_gains = gains.ewm(alpha=alpha, adjust=False).mean()
        avg_losses = losses.ewm(alpha=alpha, adjust=False).mean()
        
        # 计算相对强弱
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        # 处理无效值
        rsi = rsi.replace([np.inf, -np.inf], np.nan).fillna(50)
        
        # 将RSI值限制在0-100范围内
        rsi = rsi.clip(0, 100)
        
        return rsi
        
    except Exception as e:
        print(f"计算RSI指标时发生错误: {str(e)}")
        return pd.Series(index=df.index, data=np.nan)


def calculate_multiple_rsi(df: pd.DataFrame, periods: list = [6, 12, 24], price_col: str = "close") -> pd.DataFrame:
    """计算多个周期的RSI指标
    
    :param df: 包含价格数据的DataFrame
    :param periods: RSI计算周期列表
    :param price_col: 价格列名，默认"close"
    :return: 包含多个RSI列的DataFrame
    """
    result_df = df.copy()
    
    for period in periods:
        rsi_series = calculate_rsi(df, period, price_col)
        result_df[f'RSI{period}'] = rsi_series
    
    return result_df


def calculate_intraday_rsi(df: pd.DataFrame, period: int = 6, price_col: str = "close", 
                          session_start_time: str = "09:30", previous_close: Optional[float] = None) -> pd.Series:
    """计算分时RSI指标，支持开盘阶段即时滚动输出
    
    使用Wilder平滑法计算RSI，确保与主流股票软件的计算结果一致。
    支持使用历史数据初始化第一根K线的RSI值。
    
    :param df: 包含价格数据的DataFrame，索引为DatetimeIndex
    :param period: RSI计算周期，默认6
    :param price_col: 价格列名，默认"close"
    :param session_start_time: 交易时段开始时间，默认"09:30"
    :param previous_close: 前一交易日收盘价，用于计算第一根K线的价格变化
    :return: RSI值序列
    """
    try:
        if df.empty or len(df) < 1:
            return pd.Series(index=df.index, data=np.nan)
        
        # 计算价格变化
        if previous_close is not None:
            # 使用前一交易日收盘价计算第一根K线的价格变化
            price_changes = df[price_col].diff()
            price_changes.iloc[0] = df[price_col].iloc[0] - previous_close
        else:
            price_changes = df[price_col].diff()
        
        # 计算上涨和下跌
        gains = price_changes.where(price_changes > 0, 0)
        losses = -price_changes.where(price_changes < 0, 0)
        
        # 使用Wilder平滑法计算平均上涨和下跌
        avg_gains = _wilder_smooth(gains.values, period)
        avg_losses = _wilder_smooth(losses.values, period)
        
        # 计算RSI
        rsi_values = []
        for i in range(len(avg_gains)):
            if avg_losses[i] == 0:
                rsi = 100.0
            else:
                rs = avg_gains[i] / avg_losses[i]
                rsi = 100 - (100 / (1 + rs))
            rsi_values.append(rsi)
        
        # 创建结果Series
        result = pd.Series(rsi_values, index=df.index)
        
        # 处理无效值
        result = result.replace([np.inf, -np.inf], np.nan).fillna(50)
        
        # 将RSI值限制在0-100范围内
        result = result.clip(0, 100)
        
        return result
        
    except Exception as e:
        print(f"计算分时RSI指标时发生错误: {str(e)}")
        return pd.Series(index=df.index, data=np.nan)


def _wilder_smooth(data: np.ndarray, period: int) -> np.ndarray:
    """Wilder平滑法计算平均上涨和下跌
    
    :param data: 价格变化数据
    :param period: 平滑周期
    :return: 平滑后的数据
    """
    result = np.zeros_like(data)
    
    if len(data) == 0:
        return result
    
    # 初始化第一个值
    result[0] = data[0]
    
    for i in range(1, len(data)):
        if i < period:
            # 在周期内，使用简单平均
            result[i] = np.mean(data[:i+1])
        else:
            # 超过周期后，使用Wilder平滑法
            result[i] = (result[i-1] * (period - 1) + data[i]) / period
    
    return result


def calculate_intraday_kdj(df: pd.DataFrame, n: int = 55, m1: int = 21, m2: int = 5, 
                          high_col: str = "high", low_col: str = "low", close_col: str = "close",
                          previous_close: Optional[float] = None) -> pd.DataFrame:
    """计算分时KDJ指标，支持开盘阶段即时滚动输出
    
    使用指数移动平均法计算KDJ，确保与主流股票软件的计算结果一致。
    支持使用历史数据初始化第一根K线的KDJ值。
    
    参数说明：
    - 默认参数(55,21,5)针对日内高低点捕捉优化，配合RSI(6,12,24)使用
    - n=55: 约1小时数据周期，能更好地识别日内主要趋势和转折点
    - m1=21: K值平滑，减少噪音干扰，提高信号确定性
    - m2=5: D值平滑，保持一定敏感性，及时捕捉转折点
    
    日内高低点捕捉使用建议：
    - RSI6 + KDJ-K: 配合确认超卖反弹点（日内最低点）
    - RSI12 + KDJ-D: 配合确认超买回调点（日内最高点）
    - RSI24 + KDJ-J: 配合确认趋势转折点
    
    高低点信号组合：
    - 日内最低点: RSI6<30 + KDJ-K<20 + KDJ-D<20
    - 日内最高点: RSI6>70 + KDJ-K>80 + KDJ-D>80
    
    :param df: 包含价格数据的DataFrame，索引为DatetimeIndex
    :param n: KDJ计算周期，默认55（日内高低点捕捉优化）
    :param m1: K值平滑参数，默认21（日内高低点捕捉优化）
    :param m2: D值平滑参数，默认5（日内高低点捕捉优化）
    :param high_col: 最高价列名，默认"high"
    :param low_col: 最低价列名，默认"low"
    :param close_col: 收盘价列名，默认"close"
    :param previous_close: 前一交易日收盘价，用于计算第一根K线的价格变化
    :return: 包含K、D、J值的DataFrame
    """
    try:
        if df.empty or len(df) < 1:
            return pd.DataFrame(index=df.index, columns=['K', 'D', 'J'])
        
        # 计算N日内的最高价和最低价
        low_n = df[low_col].rolling(window=n, min_periods=1).min()
        high_n = df[high_col].rolling(window=n, min_periods=1).max()
        
        # 计算RSV
        rsv = (df[close_col] - low_n) / (high_n - low_n) * 100
        
        # 处理无效值
        rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(50)
        
        # 计算K、D、J值，使用指数移动平均
        k_values = rsv.ewm(alpha=1/m1, adjust=False).mean()
        d_values = k_values.ewm(alpha=1/m2, adjust=False).mean()
        j_values = 3 * k_values - 2 * d_values
        
        # 处理无效值
        k_values = k_values.replace([np.inf, -np.inf], np.nan).fillna(50)
        d_values = d_values.replace([np.inf, -np.inf], np.nan).fillna(50)
        j_values = j_values.replace([np.inf, -np.inf], np.nan).fillna(50)
        
        # 将KDJ值限制在0-100范围内
        k_values = k_values.clip(0, 100)
        d_values = d_values.clip(0, 100)
        j_values = j_values.clip(0, 100)
        
        # 创建结果DataFrame
        result = pd.DataFrame({
            'K': k_values,
            'D': d_values,
            'J': j_values
        }, index=df.index)
        
        return result
        
    except Exception as e:
        print(f"计算分时KDJ指标时发生错误: {str(e)}")
        return pd.DataFrame(index=df.index, columns=['K', 'D', 'J'])
