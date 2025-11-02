"""分时信号系统 - 定义分时图的买入和卖出信号"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def is_limit_up_down(code: str, current_price: float, prev_close: float) -> tuple[bool, bool]:
    """
    检测股票是否涨停或跌停
    
    :param code: 股票代码
    :param current_price: 当前价格
    :param prev_close: 前一交易日收盘价
    :return: (是否涨停, 是否跌停)
    """
    if prev_close <= 0:
        return False, False
    
    # 计算涨跌幅
    change_pct = (current_price - prev_close) / prev_close * 100
    
    # 判断股票类型并设置阈值
    if code.startswith('ST') or code.startswith('*ST'):
        # ST股票：4.85%
        limit_threshold = 4.9
    elif code.startswith('3'):
        # 创业板：19.85%
        limit_threshold = 19.9
    else:
        # 普通股票：9.85%
        limit_threshold = 9.9
    
    # 判断是否涨停或跌停（考虑浮点数精度问题）
    is_limit_up = change_pct >= (limit_threshold - 0.05)  # 允许0.01%的误差
    is_limit_down = change_pct <= (-limit_threshold + 0.05)  # 允许0.01%的误差
    
    return is_limit_up, is_limit_down


class IntradaySignalBase(ABC):
    """分时信号基类"""
    
    # 布林带安全线比例常量
    BOLLINGER_SAFETY_LINE_RATIO = 0.1  # 布林带安全线比例，默认10%
    
    def __init__(self, name: str, delay_minutes: float = 2):
        """
        :param name: 分时信号名称
        :param delay_minutes: 延迟确认时间（分钟）
        """
        self.name = name
        self.delay_minutes = delay_minutes
    
    @abstractmethod
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查分时信号条件
        
        :param data: 包含所有必要数据的字典
        :param index: 当前数据点索引
        :return: True表示满足分时信号条件
        """
        pass
    
    @abstractmethod
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证分时信号有效性（延迟检查）
        
        :param data: 包含所有必要数据的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        pass
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时信号
        
        :param data: 包含所有必要数据的字典
        :param index: 当前数据点索引
        :return: True表示是假分时信号
        """
        return False
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建分时信号数据
        
        :param data: 包含所有必要数据的字典
        :param index: 分时信号产生的索引
        :return: 分时信号数据字典
        """
        # 检查是否为假分时信号
        is_fake = self.check_fake_signal(data, index)
        
        return {
            'index': index,
            'timestamp': index,
            'signal_type': self.name,
            'price': data.get('close_prices', pd.Series()).iloc[index] if 'close_prices' in data else 0.0,
            'is_fake': is_fake,  # 添加假分时信号标记
            'wait_validate': True  # 新增：标记为待确认状态
        }
    
    def _get_time_str(self, data: Dict[str, Any], index: int) -> str:
        """获取指定索引对应的时间字符串
        
        :param data: 包含所有必要数据的字典
        :param index: 数据点索引
        :return: 时间字符串，格式为 HH:MM:SS
        """
        try:
            close_prices = data.get('close_prices')
            if close_prices is not None and hasattr(close_prices, 'index') and index < len(close_prices.index):
                timestamp = close_prices.index[index]
                if hasattr(timestamp, 'strftime'):
                    return timestamp.strftime('%H:%M:%S')
        except Exception:
            pass
        return f"索引{index}"


class MA25CrossMA50BuySignal(IntradaySignalBase):
    """MA25上穿MA50分时买入信号（基础均线仅用于图表显示参考）"""
    
    def __init__(self, delay_minutes: int = 10, fake_rsi_threshold: float = 80):
        """
        :param delay_minutes: 延迟确认时间（分钟）
        :param fake_rsi_threshold: 假分时买入信号的RSI阈值，默认80
        """
        super().__init__("MA25上穿MA50分时买入", delay_minutes)
        self.fake_rsi_threshold = fake_rsi_threshold
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查短期均线是否上穿中期均线
        
        :param data: 包含ma_short_values, ma_mid_values, ma_base_values的字典
        :param index: 当前数据点索引
        :return: True表示满足上穿条件
        """
        if index < 1:
            return False
        
        ma_short_values = data.get('ma_short_values')
        ma_mid_values = data.get('ma_mid_values')
        
        if ma_short_values is None or ma_mid_values is None:
            print(f"[DEBUG] check_condition: 缺少MA数据")
            return False
        
        if index >= len(ma_short_values) or index >= len(ma_mid_values):
            print(f"[DEBUG] check_condition: 索引超出范围，index={index}, ma_short_len={len(ma_short_values)}, ma_mid_len={len(ma_mid_values)}")
            return False
        
        prev_ma_short = ma_short_values.iloc[index-1]
        curr_ma_short = ma_short_values.iloc[index]
        prev_ma_mid = ma_mid_values.iloc[index-1]
        curr_ma_mid = ma_mid_values.iloc[index]
        
        # 检查数据有效性
        if pd.isna(prev_ma_short) or pd.isna(curr_ma_short) or pd.isna(prev_ma_mid) or pd.isna(curr_ma_mid):
            print(f"[DEBUG] check_condition: 索引{index}存在NaN值")
            return False
        
        # 短期均线从下往上穿过中期均线：前一个时刻短期MA < 中期MA，当前时刻短期MA > 中期MA
        if prev_ma_short < prev_ma_mid and curr_ma_short > curr_ma_mid:
            print(f"[DEBUG] check_condition: 索引{index}满足上穿条件: MA短{prev_ma_short:.4f}<MA中{prev_ma_mid:.4f} -> MA短{curr_ma_short:.4f}>MA中{curr_ma_mid:.4f}")
            return True
        
        # 处理边界情况：短期均线从等于中期均线变为大于中期均线
        if prev_ma_short <= prev_ma_mid and curr_ma_short > curr_ma_mid:
            print(f"[DEBUG] check_condition: 索引{index}满足边界上穿条件: MA短{prev_ma_short:.4f}<=MA中{prev_ma_mid:.4f} -> MA短{curr_ma_short:.4f}>MA中{curr_ma_mid:.4f}")
            return True
        
        return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时买入信号（1分钟RSI6 >= 80）
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示是假分时买入信号
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty or index >= len(rsi_df):
            return False
        
        # 获取1分钟级别的RSI6
        rsi_1min = rsi_df.iloc[index].get('RSI6_1min')
        
        # 检查RSI值是否有效且超过假信号阈值
        if rsi_1min is not None and not pd.isna(rsi_1min):
            return rsi_1min >= self.fake_rsi_threshold
        
        return False
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证短期均线是否仍然保持在中期均线之上
        
        :param data: 包含ma_short_values, ma_mid_values的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        ma_short_values = data.get('ma_short_values')
        ma_mid_values = data.get('ma_mid_values')
        
        if ma_short_values is None or ma_mid_values is None:
            print(f"[DEBUG] 验证信号失败：缺少MA数据")
            return False
        
        # 如果延迟时间为0，直接返回True（立即确认）
        if self.delay_minutes == 0:
            print(f"[DEBUG] 延迟时间为0，立即确认信号有效")
            return True
        
        print(f"[DEBUG] 开始验证信号，延迟时间: {self.delay_minutes}分钟")
        
        # 检查延迟时间内短期均线是否仍然保持在中期均线之上
        # 将延迟时间（分钟）转换为数据点数量，向上取整
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(ma_short_values))):
            if check_i < len(ma_short_values) and check_i < len(ma_mid_values):
                check_ma_short = ma_short_values.iloc[check_i]
                check_ma_mid = ma_mid_values.iloc[check_i]
                
                # 如果短期均线下穿回中期均线，则分时信号无效
                if pd.isna(check_ma_short) or pd.isna(check_ma_mid) or check_ma_short <= check_ma_mid:
                    # 获取时间字符串用于调试
                    check_time_str = self._get_time_str(data, check_i)
                    signal_time_str = self._get_time_str(data, signal_index)
                    print(f"[DEBUG] 短期均线下穿回中期均线，分时买入信号无效: 信号时间={signal_time_str}, 下穿时间={check_time_str}, MA短={check_ma_short:.4f}, MA中={check_ma_mid:.4f}")
                    return False
                else:
                    print(f"[DEBUG] 索引{check_i}验证通过: MA短={check_ma_short:.4f} > MA中={check_ma_mid:.4f}")
        
        print(f"[DEBUG] 信号验证完成，所有检查点都通过")
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建MA分时买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        ma_short_values = data.get('ma_short_values')
        ma_mid_values = data.get('ma_mid_values')
        ma_base_values = data.get('ma_base_values')
        close_prices = data.get('close_prices')
        
        if ma_short_values is not None and ma_mid_values is not None and ma_base_values is not None and close_prices is not None:
            current_price = close_prices.iloc[index]
            ma_short_price = ma_short_values.iloc[index]
            ma_mid_price = ma_mid_values.iloc[index]
            ma_base_price = ma_base_values.iloc[index]
            
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            # 获取RSI值用于假信号判断
            rsi_1min = 0
            rsi_df = data.get('rsi_df')
            if rsi_df is not None and index < len(rsi_df):
                rsi_1min = rsi_df.iloc[index].get('RSI6_1min', 0)
            
            base_signal.update({
                'price': current_price,
                'ma_short_price': ma_short_price,
                'ma_mid_price': ma_mid_price,
                'ma_base_price': ma_base_price,
                'net_gain': net_gain,
                'rsi_1min': rsi_1min,  # 添加RSI值用于调试
                'fake_reason': 'RSI6_1min >= 80' if base_signal['is_fake'] else None  # 添加假信号原因
            })
        
        return base_signal


class RSISellSignal(IntradaySignalBase):
    """RSI分时卖出信号"""
    
    def __init__(self, rsi_5min_threshold: float = 75, rsi_sum_threshold: float = 155, 
                 delay_minutes: float = 0.5):
        """
        :param rsi_5min_threshold: 5分钟RSI阈值，默认75
        :param rsi_sum_threshold: 5分钟RSI6 + 1分钟RSI6的总和阈值，默认155
        :param delay_minutes: 延迟确认时间（分钟），默认0.5分钟（30秒）
        """
        super().__init__(f"RSI分时卖出({rsi_5min_threshold}/{rsi_sum_threshold})", delay_minutes)
        self.rsi_5min_threshold = rsi_5min_threshold
        self.rsi_sum_threshold = rsi_sum_threshold
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI是否满足分时卖出条件
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示满足RSI分时卖出条件
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        if index >= len(rsi_df):
            return False
        
        # 获取1分钟级别的RSI6 和 5分钟级别的RSI6
        rsi_1min = rsi_df.iloc[index].get('RSI6_1min')
        rsi_5min = rsi_df.iloc[index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if rsi_1min is None or rsi_5min is None or pd.isna(rsi_1min) or pd.isna(rsi_5min):
            return False
        
        # 检查是否满足分时卖出条件：5分钟RSI6 >= threshold(75) 且 5分钟RSI6+1分钟RSI6 >= threshold(默认155) 且 1分钟RSI6 >= 5分钟RSI6
        return (rsi_5min >= self.rsi_5min_threshold and 
                (rsi_5min + rsi_1min) >= self.rsi_sum_threshold and 
                rsi_1min - rsi_5min >= -5)
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时卖出信号（基于布林带安全线条件）
        
        :param data: 包含rsi_df, close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :return: True表示是假分时卖出信号
        """
        # 检查布林带安全线条件：如果价格高于布林带上轨内安全线，则认为是假信号
        return self._check_bollinger_safety_line_fake_signal(data, index, signal_type='sell')
    
    def _check_rsi_diff_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI差值条件是否为假信号
        
        :param data: 包含close_prices, rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示是假信号
        """
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is None or rsi_df is None or rsi_df.empty:
            return False
        
        # 检查3分钟内的数据点数量（假设1分钟1个数据点）
        lookback_minutes = 3
        start_index = max(0, index - lookback_minutes)
        
        if start_index >= index:
            return False
        
        # 在3分钟内查找最高点
        price_slice = close_prices.iloc[start_index:index+1]
        if price_slice.empty:
            return False
        
        # 找到最高点的索引（相对于切片）
        max_price_idx = price_slice.idxmax()
        # 转换为全局索引
        peak_index = max_price_idx if isinstance(max_price_idx, int) else price_slice.index.get_loc(max_price_idx) + start_index
        
        # 确保峰值索引在有效范围内
        if peak_index >= len(rsi_df) or peak_index < 0:
            return False
        
        # 获取峰值点的RSI值
        peak_rsi_1min = rsi_df.iloc[peak_index].get('RSI6_1min')
        peak_rsi_5min = rsi_df.iloc[peak_index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if pd.isna(peak_rsi_1min) or pd.isna(peak_rsi_5min):
            return False
        
        # 计算RSI差值
        rsi_diff = abs(peak_rsi_1min - peak_rsi_5min)
        
        # 如果差值超过15，标记为假信号
        return rsi_diff > 15
    
    def _get_rsi_diff_fake_reason(self, data: Dict[str, Any], index: int) -> str:
        """获取RSI差值假信号的原因描述
        
        :param data: 包含close_prices, rsi_df的字典
        :param index: 当前数据点索引
        :return: 假信号原因描述
        """
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is None or rsi_df is None or rsi_df.empty:
            return "RSI差值检查失败"
        
        # 检查3分钟内的数据点数量
        lookback_minutes = 3
        start_index = max(0, index - lookback_minutes)
        
        if start_index >= index:
            return "RSI差值检查失败"
        
        # 在3分钟内查找最高点
        price_slice = close_prices.iloc[start_index:index+1]
        if price_slice.empty:
            return "RSI差值检查失败"
        
        # 找到最高点的索引
        max_price_idx = price_slice.idxmax()
        peak_index = max_price_idx if isinstance(max_price_idx, int) else price_slice.index.get_loc(max_price_idx) + start_index
        
        # 确保峰值索引在有效范围内
        if peak_index >= len(rsi_df) or peak_index < 0:
            return "RSI差值检查失败"
        
        # 获取峰值点的RSI值
        peak_rsi_1min = rsi_df.iloc[peak_index].get('RSI6_1min')
        peak_rsi_5min = rsi_df.iloc[peak_index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if pd.isna(peak_rsi_1min) or pd.isna(peak_rsi_5min):
            return "RSI差值检查失败"
        
        # 计算RSI差值
        rsi_diff = peak_rsi_1min - peak_rsi_5min
        
        return f"3分钟内高点RSI差值{rsi_diff:.1f} > 15"
    
    def _check_bollinger_safety_line_fake_signal(self, data: Dict[str, Any], index: int, signal_type: str) -> bool:
        """检查布林带安全线条件是否为假信号
        
        :param data: 包含close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :param signal_type: 信号类型 'buy' 或 'sell'
        :return: True表示是假信号
        """
        close_prices = data.get('close_prices')
        bollinger_upper = data.get('bollinger_upper')
        bollinger_middle = data.get('bollinger_middle')
        bollinger_lower = data.get('bollinger_lower')
        
        if (close_prices is None or bollinger_upper is None or 
            bollinger_middle is None or bollinger_lower is None):
            return False
        
        if index >= len(close_prices) or index >= len(bollinger_upper):
            return False
        
        current_price = close_prices.iloc[index]
        upper_band = bollinger_upper.iloc[index]
        middle_band = bollinger_middle.iloc[index]
        lower_band = bollinger_lower.iloc[index]
        
        # 检查布林带数据是否有效
        if (pd.isna(upper_band) or pd.isna(middle_band) or pd.isna(lower_band) or
            pd.isna(current_price)):
            print(f"[DEBUG] 布林带数据包含NaN值，跳过安全线检查")
            return False
        
        if signal_type == 'buy':
            # 买入信号：计算下轨安全线（中轨到下轨价格差的10%）
            safety_line = lower_band + (middle_band - lower_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            # 如果价格低于下轨安全线，则认为是假信号
            return current_price < safety_line
        elif signal_type == 'sell':
            # 卖出信号：计算上轨安全线（上轨到中轨价格差的10%）
            safety_line = upper_band - (upper_band - middle_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            # 如果价格高于上轨安全线，则认为是假信号
            return current_price > safety_line
        
        return False
    
    def _get_bollinger_safety_line_fake_reason(self, data: Dict[str, Any], index: int, signal_type: str) -> str:
        """获取布林带安全线假信号的原因描述
        
        :param data: 包含close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :param signal_type: 信号类型 'buy' 或 'sell'
        :return: 假信号原因描述
        """
        close_prices = data.get('close_prices')
        bollinger_upper = data.get('bollinger_upper')
        bollinger_middle = data.get('bollinger_middle')
        bollinger_lower = data.get('bollinger_lower')
        
        if (close_prices is None or bollinger_upper is None or 
            bollinger_middle is None or bollinger_lower is None):
            return "布林带安全线检查失败"
        
        if index >= len(close_prices) or index >= len(bollinger_upper):
            return "布林带安全线检查失败"
        
        current_price = close_prices.iloc[index]
        upper_band = bollinger_upper.iloc[index]
        middle_band = bollinger_middle.iloc[index]
        lower_band = bollinger_lower.iloc[index]
        
        if (pd.isna(upper_band) or pd.isna(middle_band) or pd.isna(lower_band) or
            pd.isna(current_price)):
            return "布林带安全线检查失败"
        
        if signal_type == 'buy':
            safety_line = lower_band + (middle_band - lower_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            return f"买入信号价格{current_price:.3f}低于下轨安全线{safety_line:.3f}"
        elif signal_type == 'sell':
            safety_line = upper_band - (upper_band - middle_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            return f"卖出信号价格{current_price:.3f}高于上轨安全线{safety_line:.3f}"
        
        return "布林带安全线检查失败"
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证RSI分时卖出信号有效性（延迟检查）
        
        :param data: 包含rsi_df的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 检查延迟时间内是否再次满足RSI条件（避免重复信号）
        # 将延迟时间（分钟）转换为数据点数量，向上取整
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(rsi_df))):
            if check_i < len(rsi_df):
                check_rsi_1min = rsi_df.iloc[check_i].get('RSI6_1min')
                check_rsi_5min = rsi_df.iloc[check_i].get('RSI6_5min')
                
                if (check_rsi_1min is not None and check_rsi_5min is not None and 
                    not pd.isna(check_rsi_1min) and not pd.isna(check_rsi_5min) and
                    check_rsi_5min >= self.rsi_5min_threshold and (check_rsi_5min + check_rsi_1min) >= self.rsi_sum_threshold):
                    # 获取时间字符串用于调试
                    check_time_str = self._get_time_str(data, check_i)
                    signal_time_str = self._get_time_str(data, signal_index)
                    print(f"[DEBUG] RSI重复满足卖出条件，分时卖出信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI1min={check_rsi_1min:.1f}, RSI5min={check_rsi_5min:.1f}")
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建RSI分时卖出信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is not None and rsi_df is not None and index < len(close_prices) and index < len(rsi_df):
            current_price = close_prices.iloc[index]
            rsi_1min = rsi_df.iloc[index].get('RSI6_1min', 0)
            rsi_5min = rsi_df.iloc[index].get('RSI6_5min', 0)
            
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            # 添加假信号原因
            fake_reason = None
            if base_signal['is_fake']:
                # RSI差值假信号
                fake_reason = self._get_rsi_diff_fake_reason(data, index)
            
            base_signal.update({
                'price': current_price,
                'rsi_1min': rsi_1min,
                'rsi_5min': rsi_5min,
                'net_gain': net_gain,
                'fake_reason': fake_reason  # 添加假信号原因
            })
        
        return base_signal


class SupportBreakdownSellSignal(IntradaySignalBase):
    """支撑位跌破分时卖出信号"""
    
    def __init__(self, delay_minutes: int = 1, rsi_threshold: float = 70):
        """
        :param delay_minutes: 延迟确认时间（分钟），默认2分钟
        :param rsi_threshold: RSI阈值，用于确认卖出信号，默认70
        """
        super().__init__("跌破支撑位分时卖出", delay_minutes)
        self.rsi_threshold = rsi_threshold
        # 状态管理：跟踪支撑位跌破状态
        self._breakdown_confirmed = False  # 是否已确认跌破
        self._last_breakdown_index = -1   # 上次跌破的索引
        self._reset_triggered = False     # 是否已触发重置
    
    def _get_5min_price(self, price_df: pd.DataFrame, index: int) -> Optional[float]:
        """获取5分钟价格数据
        
        :param price_df: 1分钟价格数据
        :param index: 当前1分钟数据索引
        :return: 对应的5分钟收盘价，如果无法获取则返回None
        """
        try:
            if price_df is None or price_df.empty:
                return None
            
            # 将1分钟数据重采样为5分钟K线数据
            price_5min = price_df.resample('5T', offset='1min').agg({
                'open': 'first',
                'close': 'last', 
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            if price_5min.empty:
                return None
            
            # 获取当前1分钟时间点对应的5分钟K线
            current_time = price_df.index[index]
            
            # 找到包含当前时间的5分钟K线
            # 5分钟K线的时间戳是5分钟的整数倍（如09:30, 09:35, 09:40等）
            # 当前时间应该属于某个5分钟区间
            for ts, row in price_5min.iterrows():
                # 检查当前时间是否在这个5分钟区间内
                if current_time >= ts and current_time < ts + pd.Timedelta(minutes=5):
                    return row['close']
            
            # 如果没有找到对应的5分钟K线，返回最新的5分钟收盘价
            if len(price_5min) > 0:
                return price_5min['close'].iloc[-1]
            
            return None
            
        except Exception as e:
            print(f"[ERROR] 获取5分钟价格失败: {e}")
            return None
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否跌破支撑位（基于5分钟价格）
        
        :param data: 包含close_prices, support_level, price_df的字典
        :param index: 当前数据点索引
        :return: True表示跌破支撑位
        """
        close_prices = data.get('close_prices')
        support_level = data.get('support_level')
        price_df = data.get('price_df')
        
        if close_prices is None or support_level is None or price_df is None:
            print(f"[DEBUG] 支撑位跌破信号检查失败: close_prices={close_prices is not None}, support_level={support_level}, price_df={price_df is not None}")
            return False
        
        if index >= len(close_prices):
            print(f"[DEBUG] 支撑位跌破信号检查失败: 索引{index}超出范围{len(close_prices)}")
            return False
        
        # 获取5分钟价格数据
        current_price = self._get_5min_price(price_df, index)
        if current_price is None:
            return False
        
        # 检查是否跌破支撑位（当前分时价格 < 支撑位）
        if current_price < support_level:
            # 如果已经确认跌破且未重置，则不再触发
            if self._breakdown_confirmed and not self._reset_triggered:
                print(f"[DEBUG] 支撑位跌破信号已确认，跳过重复触发: 价格{current_price:.3f} < 支撑位{support_level:.3f}")
                return False
            
            # 检查是否重新上穿支撑位（重置状态）
            if self._breakdown_confirmed and current_price >= support_level:
                self._reset_triggered = True
                self._breakdown_confirmed = False
                self._last_breakdown_index = -1
                print(f"[DEBUG] 支撑位跌破状态重置：价格{current_price:.3f}重新上穿支撑位{support_level:.3f}")
                return False
            
            # 首次跌破或重置后的跌破
            if not self._breakdown_confirmed or self._reset_triggered:
                self._breakdown_confirmed = True
                self._last_breakdown_index = index
                self._reset_triggered = False
                print(f"[DEBUG] 支撑位跌破信号触发：价格{current_price:.3f}跌破支撑位{support_level:.3f} (索引{index})")
                return True
        
        # 检查是否重新上穿支撑位（重置状态）
        elif current_price >= support_level and self._breakdown_confirmed:
            if not self._reset_triggered:
                self._reset_triggered = True
                self._breakdown_confirmed = False
                self._last_breakdown_index = -1
                print(f"[DEBUG] 支撑位跌破状态重置：价格{current_price:.3f}重新上穿支撑位{support_level:.3f}")
        
        return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时卖出信号（当日跌幅过大）
        
        :param data: 包含close_prices, prev_close的字典
        :param index: 当前数据点索引
        :return: True表示是假分时卖出信号
        """
        close_prices = data.get('close_prices')
        prev_close = data.get('prev_close')
        
        if close_prices is None or prev_close is None or prev_close <= 0 or index >= len(close_prices):
            return False
        
        current_price = close_prices.iloc[index]
        daily_change_pct = (current_price - prev_close) / prev_close * 100
        
        # 如果当日跌幅超过5%，可能是假信号
        return daily_change_pct <= -5.0
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证支撑位跌破分时卖出信号有效性（延迟检查）
        
        :param data: 包含close_prices, support_level的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        close_prices = data.get('close_prices')
        support_level = data.get('support_level')
        
        if close_prices is None or support_level is None:
            return False
        
        # 检查延迟时间内是否仍然跌破支撑位
        # 将延迟时间（分钟）转换为数据点数量，向上取整
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(close_prices))):
            if check_i < len(close_prices):
                check_price = close_prices.iloc[check_i]
                
                # 如果价格回到支撑位之上，信号无效
                if check_price >= support_level:
                    check_time_str = self._get_time_str(data, check_i)
                    signal_time_str = self._get_time_str(data, signal_index)
                    print(f"[DEBUG] 支撑位跌破信号无效：价格回到支撑位之上，信号时间={signal_time_str}, 确认时间={check_time_str}, 价格={check_price:.3f}, 支撑位={support_level:.3f}")
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建支撑位跌破分时卖出信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        support_level = data.get('support_level')
        prev_close = data.get('prev_close')
        
        if (close_prices is not None and 
            index < len(close_prices)):
            
            current_price = close_prices.iloc[index]
            
            # 计算到支撑位的距离
            distance_to_support = ((current_price - support_level) / current_price) * 100 if current_price > 0 else 0
            
            # 计算当日涨跌幅
            daily_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close and prev_close > 0 else 0
            
            # 更新信号数据
            base_signal.update({
                'price': current_price,
                'support_level': support_level,
                'distance_to_support': distance_to_support,
                'daily_change_pct': daily_change_pct,
                'net_gain': daily_change_pct,  # 添加net_gain字段，用于信号绘制
                'signal_info': f"跌破支撑位({support_level:.3f})"
            })
        
        return base_signal
    
    def reset_state(self):
        """重置支撑位跌破状态（用于日期切换或股票代码变化）"""
        self._breakdown_confirmed = False
        self._last_breakdown_index = -1
        self._reset_triggered = False
        print("[DEBUG] 支撑位跌破状态已重置")


class RSIBuySignal(IntradaySignalBase):
    """RSI分时买入信号"""
    
    def __init__(self, rsi_5min_threshold: float = 30, rsi_sum_threshold: float = 45, 
                 delay_minutes: float = 0.5):
        """
        :param rsi_5min_threshold: 5分钟RSI阈值，默认30
        :param rsi_sum_threshold: 5分钟RSI6 + 1分钟RSI6的总和阈值，默认50
        :param delay_minutes: 延迟确认时间（分钟），默认0.5分钟（30秒）
        """
        super().__init__(f"RSI分时买入({rsi_5min_threshold}/{rsi_sum_threshold})", delay_minutes)
        self.rsi_5min_threshold = rsi_5min_threshold
        self.rsi_sum_threshold = rsi_sum_threshold
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI是否满足分时买入条件
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示满足RSI分时买入条件
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        if index >= len(rsi_df):
            return False
        
        # 获取1分钟级别的RSI6 和 5分钟级别的RSI6
        rsi_1min = rsi_df.iloc[index].get('RSI6_1min')
        rsi_5min = rsi_df.iloc[index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if rsi_1min is None or rsi_5min is None or pd.isna(rsi_1min) or pd.isna(rsi_5min):
            return False
        
        # 检查是否满足分时买入条件：5分钟RSI6 < threshold(30) 且 5分钟RSI6+1分钟RSI6 < threshold(默认50) 且 1分钟RSI6 <= 5分钟RSI6
        return (rsi_5min < self.rsi_5min_threshold and 
                (rsi_5min + rsi_1min) < self.rsi_sum_threshold and 
                rsi_1min - rsi_5min <= 5)
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时买入信号（基于布林带安全线条件）
        
        :param data: 包含rsi_df, close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :return: True表示是假分时买入信号
        """
        # 检查布林带安全线条件：如果价格低于布林带下轨内安全线，则认为是假信号
        return self._check_bollinger_safety_line_fake_signal(data, index, signal_type='buy')
    
    def _check_rsi_diff_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI差值条件是否为假信号（买入信号：查找3分钟内低点）
        
        :param data: 包含close_prices, rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示是假信号
        """
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is None or rsi_df is None or rsi_df.empty:
            return False
        
        # 检查3分钟内的数据点数量（假设1分钟1个数据点）
        lookback_minutes = 3
        start_index = max(0, index - lookback_minutes)
        
        if start_index >= index:
            return False
        
        # 在3分钟内查找最低点（买入信号关注低点）
        price_slice = close_prices.iloc[start_index:index+1]
        if price_slice.empty:
            return False
        
        # 找到最低点的索引（相对于切片）
        min_price_idx = price_slice.idxmin()
        # 转换为全局索引
        low_index = min_price_idx if isinstance(min_price_idx, int) else price_slice.index.get_loc(min_price_idx) + start_index
        
        # 确保低点索引在有效范围内
        if low_index >= len(rsi_df) or low_index < 0:
            return False
        
        # 获取低点的RSI值
        low_rsi_1min = rsi_df.iloc[low_index].get('RSI6_1min')
        low_rsi_5min = rsi_df.iloc[low_index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if pd.isna(low_rsi_1min) or pd.isna(low_rsi_5min):
            return False
        
        # 计算RSI差值的绝对值
        rsi_diff = abs(low_rsi_1min - low_rsi_5min)
        
        # 如果差值超过15，标记为假信号
        return rsi_diff > 15
    
    def _get_rsi_diff_fake_reason(self, data: Dict[str, Any], index: int) -> str:
        """获取RSI差值假信号的原因描述（买入信号：查找3分钟内低点）
        
        :param data: 包含close_prices, rsi_df的字典
        :param index: 当前数据点索引
        :return: 假信号原因描述
        """
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is None or rsi_df is None or rsi_df.empty:
            return "RSI差值检查失败"
        
        # 检查3分钟内的数据点数量
        lookback_minutes = 3
        start_index = max(0, index - lookback_minutes)
        
        if start_index >= index:
            return "RSI差值检查失败"
        
        # 在3分钟内查找最低点
        price_slice = close_prices.iloc[start_index:index+1]
        if price_slice.empty:
            return "RSI差值检查失败"
        
        # 找到最低点的索引
        min_price_idx = price_slice.idxmin()
        low_index = min_price_idx if isinstance(min_price_idx, int) else price_slice.index.get_loc(min_price_idx) + start_index
        
        # 确保低点索引在有效范围内
        if low_index >= len(rsi_df) or low_index < 0:
            return "RSI差值检查失败"
        
        # 获取低点的RSI值
        low_rsi_1min = rsi_df.iloc[low_index].get('RSI6_1min')
        low_rsi_5min = rsi_df.iloc[low_index].get('RSI6_5min')
        
        # 检查RSI值是否有效
        if pd.isna(low_rsi_1min) or pd.isna(low_rsi_5min):
            return "RSI差值检查失败"
        
        # 计算RSI差值的绝对值
        rsi_diff = abs(low_rsi_1min - low_rsi_5min)
        
        return f"3分钟内低点RSI差值{rsi_diff:.1f} > 15"
    
    def _check_bollinger_safety_line_fake_signal(self, data: Dict[str, Any], index: int, signal_type: str) -> bool:
        """检查布林带安全线条件是否为假信号
        
        :param data: 包含close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :param signal_type: 信号类型 'buy' 或 'sell'
        :return: True表示是假信号
        """
        close_prices = data.get('close_prices')
        bollinger_upper = data.get('bollinger_upper')
        bollinger_middle = data.get('bollinger_middle')
        bollinger_lower = data.get('bollinger_lower')
        
        if (close_prices is None or bollinger_upper is None or 
            bollinger_middle is None or bollinger_lower is None):
            return False
        
        if index >= len(close_prices) or index >= len(bollinger_upper):
            return False
        
        current_price = close_prices.iloc[index]
        upper_band = bollinger_upper.iloc[index]
        middle_band = bollinger_middle.iloc[index]
        lower_band = bollinger_lower.iloc[index]
        
        # 检查布林带数据是否有效
        if (pd.isna(upper_band) or pd.isna(middle_band) or pd.isna(lower_band) or
            pd.isna(current_price)):
            return False
        
        if signal_type == 'buy':
            # 买入信号：计算下轨安全线（中轨到下轨价格差的10%）
            safety_line = lower_band + (middle_band - lower_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            # 如果价格低于下轨安全线，则认为是假信号
            return current_price < safety_line
        elif signal_type == 'sell':
            # 卖出信号：计算上轨安全线（上轨到中轨价格差的10%）
            safety_line = upper_band - (upper_band - middle_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            # 如果价格高于上轨安全线，则认为是假信号
            return current_price > safety_line
        
        return False
    
    def _get_bollinger_safety_line_fake_reason(self, data: Dict[str, Any], index: int, signal_type: str) -> str:
        """获取布林带安全线假信号的原因描述
        
        :param data: 包含close_prices, bollinger_upper, bollinger_middle, bollinger_lower的字典
        :param index: 当前数据点索引
        :param signal_type: 信号类型 'buy' 或 'sell'
        :return: 假信号原因描述
        """
        close_prices = data.get('close_prices')
        bollinger_upper = data.get('bollinger_upper')
        bollinger_middle = data.get('bollinger_middle')
        bollinger_lower = data.get('bollinger_lower')
        
        if (close_prices is None or bollinger_upper is None or 
            bollinger_middle is None or bollinger_lower is None):
            return "布林带安全线检查失败"
        
        if index >= len(close_prices) or index >= len(bollinger_upper):
            return "布林带安全线检查失败"
        
        current_price = close_prices.iloc[index]
        upper_band = bollinger_upper.iloc[index]
        middle_band = bollinger_middle.iloc[index]
        lower_band = bollinger_lower.iloc[index]
        
        if (pd.isna(upper_band) or pd.isna(middle_band) or pd.isna(lower_band) or
            pd.isna(current_price)):
            return "布林带安全线检查失败"
        
        if signal_type == 'buy':
            safety_line = lower_band + (middle_band - lower_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            return f"买入信号价格{current_price:.3f}低于下轨安全线{safety_line:.3f}"
        elif signal_type == 'sell':
            safety_line = upper_band - (upper_band - middle_band) * self.BOLLINGER_SAFETY_LINE_RATIO
            return f"卖出信号价格{current_price:.3f}高于上轨安全线{safety_line:.3f}"
        
        return "布林带安全线检查失败"
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证RSI分时买入信号有效性（延迟检查）
        
        :param data: 包含rsi_df的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 检查延迟时间内是否再次满足RSI条件（避免重复信号）
        # 将延迟时间（分钟）转换为数据点数量，向上取整
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(rsi_df))):
            if check_i < len(rsi_df):
                check_rsi_1min = rsi_df.iloc[check_i].get('RSI6_1min')
                check_rsi_5min = rsi_df.iloc[check_i].get('RSI6_5min')
                
                if (check_rsi_1min is not None and check_rsi_5min is not None and 
                    not pd.isna(check_rsi_1min) and not pd.isna(check_rsi_5min) and
                    check_rsi_5min < self.rsi_5min_threshold and (check_rsi_5min + check_rsi_1min) < self.rsi_sum_threshold):
                    # 获取时间字符串用于调试
                    check_time_str = self._get_time_str(data, check_i)
                    signal_time_str = self._get_time_str(data, signal_index)
                    print(f"[DEBUG] RSI重复满足买入条件，分时买入信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI1min={check_rsi_1min:.1f}, RSI5min={check_rsi_5min:.1f}")
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建RSI分时买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is not None and rsi_df is not None and index < len(close_prices) and index < len(rsi_df):
            current_price = close_prices.iloc[index]
            rsi_1min = rsi_df.iloc[index].get('RSI6_1min', 0)
            rsi_5min = rsi_df.iloc[index].get('RSI6_5min', 0)
            
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            # 添加假信号原因
            fake_reason = None
            if base_signal['is_fake']:
                # RSI差值假信号
                fake_reason = self._get_rsi_diff_fake_reason(data, index)
            
            base_signal.update({
                'price': current_price,
                'rsi_1min': rsi_1min,
                'rsi_5min': rsi_5min,
                'net_gain': net_gain,
                'fake_reason': fake_reason  # 添加假信号原因
            })
        
        return base_signal


class RSIPlungeSellSignal(IntradaySignalBase):
    """RSI急跌分时卖出信号 - 检测10分钟内RSI急跌情况
    
    判断条件：
    1. 5分钟内RSI下降>=15且当前RSI<=20
    2. 特殊情况：开始点RSI<20时，只要出现下降就触发。开始点RSI=0的极端超卖情况（上升幅度不超过5且1分钟RSI不能高于30时触发）
    """
    
    def __init__(self, normal_rsi_drop_threshold: float = 15, normal_time_window: int = 5, 
                 special_time_window: int = 10, delay_minutes: float = 0.0):
        """
        :param normal_rsi_drop_threshold: 正常情况RSI下降阈值，默认15
        :param normal_time_window: 正常情况时间窗口（分钟），默认5分钟
        :param special_time_window: 特殊情况时间窗口（分钟），默认10分钟
        :param delay_minutes: 延迟确认时间（分钟），默认0.0分钟（立即触发）
        """
        super().__init__(f"RSI急跌卖出({normal_rsi_drop_threshold}/{normal_time_window}分钟,特殊{special_time_window}分钟)", delay_minutes)
        self.normal_rsi_drop_threshold = normal_rsi_drop_threshold
        self.normal_time_window = normal_time_window
        self.special_time_window = special_time_window
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI是否满足急跌卖出条件
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示满足RSI急跌卖出条件
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 获取当前5分钟RSI值
        current_rsi_5min = rsi_df.iloc[index].get('RSI6_5min')
        if current_rsi_5min is None or pd.isna(current_rsi_5min):
            return False
        
        # 检查是否跌停，如果跌停则排除急跌信号
        close_prices = data.get('close_prices')
        prev_close = data.get('prev_close')
        code = data.get('code', '')
        
        if close_prices is not None and prev_close is not None and index < len(close_prices):
            current_price = close_prices.iloc[index]
            _, is_limit_down = is_limit_up_down(code, current_price, prev_close)
            if is_limit_down:
                return False  # 跌停时排除急跌信号
        
        # 检查特殊情况：开始点RSI<20时，只要出现下降就触发，time_window = 10分钟
        # 特殊情况包括：1) 开始点RSI<20且确实下降 2) 开始点RSI=0的极端超卖情况
        if index >= self.special_time_window:
            special_start_index = max(0, index - self.special_time_window)
            special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min')
            if special_start_rsi_5min is not None and not pd.isna(special_start_rsi_5min):
                special_rsi_drop = special_start_rsi_5min - current_rsi_5min
                
                # 条件1：开始点RSI<20且确实下降
                if special_start_rsi_5min < 20 and special_rsi_drop > 0:
                    return True
                
                # 条件2：开始点RSI=0的极端超卖情况，但需要排除上升超过5的情况
                if special_start_rsi_5min == 0:
                    # 检查是否上升超过5，如果是则不触发信号
                    if special_rsi_drop >= -5:  # 上升不超过5才触发
                        # 额外检查1分钟RSI不能高于30
                        current_rsi_1min = rsi_df.iloc[index].get('RSI6_1min')
                        if current_rsi_1min is not None and not pd.isna(current_rsi_1min):
                            if current_rsi_1min <= 30:  # 1分钟RSI不能高于30
                                return True
                        else:
                            # 如果1分钟RSI数据不可用，则不触发信号
                            return False
        
        # 检查正常情况：5分钟内RSI下降>=15且当前RSI<=20，time_window = 5分钟
        if index >= self.normal_time_window:
            normal_start_index = max(0, index - self.normal_time_window)
            normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min')
            if normal_start_rsi_5min is not None and not pd.isna(normal_start_rsi_5min):
                normal_rsi_drop = normal_start_rsi_5min - current_rsi_5min
                if normal_rsi_drop >= self.normal_rsi_drop_threshold and current_rsi_5min <= 20:
                    return True
        
        return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假RSI急跌信号
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示是假信号
        """
        # RSI急跌信号通常不需要假信号检查，因为它是基于历史数据的客观计算
        return False
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证RSI急跌卖出信号有效性（延迟检查）
        
        :param data: 包含rsi_df的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 检查延迟时间内是否再次满足RSI急跌条件（避免重复信号）
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(rsi_df))):
            if check_i < len(rsi_df):
                # 重新检查急跌条件（支持两种时间窗口）
                current_rsi_5min = rsi_df.iloc[check_i].get('RSI6_5min')
                
                if current_rsi_5min is not None and not pd.isna(current_rsi_5min):
                    # 检查特殊情况：10分钟时间窗口
                    if check_i >= self.special_time_window:
                        special_start_index = max(0, check_i - self.special_time_window)
                        special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min')
                        if special_start_rsi_5min is not None and not pd.isna(special_start_rsi_5min):
                            special_rsi_drop = special_start_rsi_5min - current_rsi_5min
                            # 条件1：开始点RSI<20且确实下降
                            # 条件2：开始点RSI=0的极端超卖情况
                            if (special_start_rsi_5min < 20 and special_rsi_drop > 0) or special_start_rsi_5min == 0:
                                check_time_str = self._get_time_str(data, check_i)
                                signal_time_str = self._get_time_str(data, signal_index)
                                condition_desc = "极端超卖" if special_start_rsi_5min == 0 else "特殊情况"
                                print(f"[DEBUG] RSI重复满足急跌条件({condition_desc})，分时卖出信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI下降={special_rsi_drop:.1f}, 当前RSI={current_rsi_5min:.1f}, 开始RSI={special_start_rsi_5min:.1f}")
                                return False
                    
                    # 检查正常情况：5分钟时间窗口
                    if check_i >= self.normal_time_window:
                        normal_start_index = max(0, check_i - self.normal_time_window)
                        normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min')
                        if normal_start_rsi_5min is not None and not pd.isna(normal_start_rsi_5min):
                            normal_rsi_drop = normal_start_rsi_5min - current_rsi_5min
                            if normal_rsi_drop >= self.normal_rsi_drop_threshold and current_rsi_5min <= 20:
                                check_time_str = self._get_time_str(data, check_i)
                                signal_time_str = self._get_time_str(data, signal_index)
                                print(f"[DEBUG] RSI重复满足急跌条件(正常情况)，分时卖出信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI下降={normal_rsi_drop:.1f}, 当前RSI={current_rsi_5min:.1f}, 开始RSI={normal_start_rsi_5min:.1f}")
                                return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建RSI急跌分时卖出信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is not None and rsi_df is not None and index < len(close_prices) and index < len(rsi_df):
            current_price = close_prices.iloc[index]
            current_rsi_5min = rsi_df.iloc[index].get('RSI6_5min', 0)
            
            # 计算RSI下降值（优先使用特殊情况，否则使用正常情况）
            rsi_drop = 0
            start_rsi_5min = 0
            
            # 检查特殊情况：10分钟时间窗口
            if index >= self.special_time_window:
                special_start_index = max(0, index - self.special_time_window)
                special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min', 0)
                special_rsi_drop = special_start_rsi_5min - current_rsi_5min
                # 条件1：开始点RSI<20且确实下降
                # 条件2：开始点RSI=0的极端超卖情况
                if (special_start_rsi_5min < 20 and special_rsi_drop > 0) or special_start_rsi_5min == 0:
                    rsi_drop = special_rsi_drop
                    start_rsi_5min = special_start_rsi_5min
            
            # 检查正常情况：5分钟时间窗口
            if rsi_drop == 0 and index >= self.normal_time_window:
                normal_start_index = max(0, index - self.normal_time_window)
                normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min', 0)
                if (normal_start_rsi_5min - current_rsi_5min) >= self.normal_rsi_drop_threshold and current_rsi_5min <= 20:
                    rsi_drop = normal_start_rsi_5min - current_rsi_5min
                    start_rsi_5min = normal_start_rsi_5min
            
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            base_signal.update({
                'price': current_price,
                'rsi_5min_current': current_rsi_5min,
                'rsi_5min_start': start_rsi_5min,
                'rsi_drop': rsi_drop,
                'net_gain': net_gain,
                'fake_reason': None  # RSI急跌信号通常不需要假信号检查
            })
        
        return base_signal


class RSISurgeBuySignal(IntradaySignalBase):
    """RSI急涨分时买入信号 - 检测5分钟内RSI急涨情况
    
    判断条件：
    1. 5分钟内RSI上升>=15且当前RSI>=80
    2. 特殊情况：开始点RSI>80时，只要出现上升就触发。开始点RSI=100的极端超买情况（下降幅度不超过5且1分钟RSI不能低于70时触发）
    """
    
    def __init__(self, normal_rsi_rise_threshold: float = 15, normal_time_window: int = 5, 
                 special_time_window: int = 10, delay_minutes: float = 0.0):
        """
        :param normal_rsi_rise_threshold: 正常情况RSI上升阈值，默认15
        :param normal_time_window: 正常情况时间窗口（分钟），默认5分钟
        :param special_time_window: 特殊情况时间窗口（分钟），默认10分钟
        :param delay_minutes: 延迟确认时间（分钟），默认0.0分钟（立即触发）
        """
        super().__init__(f"RSI急涨买入({normal_rsi_rise_threshold}/{normal_time_window}分钟,特殊{special_time_window}分钟)", delay_minutes)
        self.normal_rsi_rise_threshold = normal_rsi_rise_threshold
        self.normal_time_window = normal_time_window
        self.special_time_window = special_time_window
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查RSI是否满足急涨买入条件
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示满足RSI急涨买入条件
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 获取当前5分钟RSI值
        current_rsi_5min = rsi_df.iloc[index].get('RSI6_5min')
        if current_rsi_5min is None or pd.isna(current_rsi_5min):
            return False
        
        # 检查是否涨停，如果涨停则排除急涨信号
        close_prices = data.get('close_prices')
        prev_close = data.get('prev_close')
        code = data.get('code', '')
        
        if close_prices is not None and prev_close is not None and index < len(close_prices):
            current_price = close_prices.iloc[index]
            is_limit_up, _ = is_limit_up_down(code, current_price, prev_close)
            if is_limit_up:
                return False  # 涨停时排除急涨信号
        
        # 检查特殊情况：开始点RSI>80时，只要出现上升就触发，time_window = 10分钟
        # 特殊情况包括：1) 开始点RSI>80且确实上升 2) 开始点RSI=100的极端超买情况
        if index >= self.special_time_window:
            special_start_index = max(0, index - self.special_time_window)
            special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min')
            if special_start_rsi_5min is not None and not pd.isna(special_start_rsi_5min):
                special_rsi_rise = current_rsi_5min - special_start_rsi_5min
                
                # 条件1：开始点RSI>80且确实上升
                if special_start_rsi_5min > 80 and special_rsi_rise > 0:
                    return True
                
                # 条件2：开始点RSI=100的极端超买情况，但需要排除下降超过5的情况
                if special_start_rsi_5min == 100:
                    # 检查是否下降超过5，如果是则不触发信号
                    if special_rsi_rise >= -5:  # 下降不超过5才触发
                        # 额外检查1分钟RSI不能低于70
                        current_rsi_1min = rsi_df.iloc[index].get('RSI6_1min')
                        if current_rsi_1min is not None and not pd.isna(current_rsi_1min):
                            if current_rsi_1min >= 70:  # 1分钟RSI不能低于70
                                return True
                        else:
                            # 如果1分钟RSI数据不可用，则不触发信号
                            return False
        
        # 检查正常情况：5分钟内RSI上升>=15且当前RSI>=80，time_window = 5分钟
        if index >= self.normal_time_window:
            normal_start_index = max(0, index - self.normal_time_window)
            normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min')
            if normal_start_rsi_5min is not None and not pd.isna(normal_start_rsi_5min):
                normal_rsi_rise = current_rsi_5min - normal_start_rsi_5min
                if normal_rsi_rise >= self.normal_rsi_rise_threshold and current_rsi_5min >= 80:
                    return True
        
        return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假RSI急涨信号
        
        :param data: 包含rsi_df的字典
        :param index: 当前数据点索引
        :return: True表示是假信号
        """
        # RSI急涨信号通常不需要假信号检查，因为它是基于历史数据的客观计算
        return False
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证RSI急涨买入信号有效性（延迟检查）
        
        :param data: 包含rsi_df的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        rsi_df = data.get('rsi_df')
        if rsi_df is None or rsi_df.empty:
            return False
        
        # 检查延迟时间内是否再次满足RSI急涨条件（避免重复信号）
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(rsi_df))):
            if check_i < len(rsi_df):
                # 重新检查急涨条件（支持两种时间窗口）
                current_rsi_5min = rsi_df.iloc[check_i].get('RSI6_5min')
                
                if current_rsi_5min is not None and not pd.isna(current_rsi_5min):
                    # 检查特殊情况：10分钟时间窗口
                    if check_i >= self.special_time_window:
                        special_start_index = max(0, check_i - self.special_time_window)
                        special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min')
                        if special_start_rsi_5min is not None and not pd.isna(special_start_rsi_5min):
                            special_rsi_rise = current_rsi_5min - special_start_rsi_5min
                            # 条件1：开始点RSI>80且确实上升
                            # 条件2：开始点RSI=100的极端超买情况
                            if (special_start_rsi_5min > 80 and special_rsi_rise > 0) or special_start_rsi_5min == 100:
                                check_time_str = self._get_time_str(data, check_i)
                                signal_time_str = self._get_time_str(data, signal_index)
                                condition_desc = "极端超买" if special_start_rsi_5min == 100 else "特殊情况"
                                print(f"[DEBUG] RSI重复满足急涨条件({condition_desc})，分时买入信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI上升={special_rsi_rise:.1f}, 当前RSI={current_rsi_5min:.1f}, 开始RSI={special_start_rsi_5min:.1f}")
                                return False
                    
                    # 检查正常情况：5分钟时间窗口
                    if check_i >= self.normal_time_window:
                        normal_start_index = max(0, check_i - self.normal_time_window)
                        normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min')
                        if normal_start_rsi_5min is not None and not pd.isna(normal_start_rsi_5min):
                            normal_rsi_rise = current_rsi_5min - normal_start_rsi_5min
                            if normal_rsi_rise >= self.normal_rsi_rise_threshold and current_rsi_5min >= 80:
                                check_time_str = self._get_time_str(data, check_i)
                                signal_time_str = self._get_time_str(data, signal_index)
                                print(f"[DEBUG] RSI重复满足急涨条件(正常情况)，分时买入信号无效: 信号时间={signal_time_str}, 重复时间={check_time_str}, RSI上升={normal_rsi_rise:.1f}, 当前RSI={current_rsi_5min:.1f}, 开始RSI={normal_start_rsi_5min:.1f}")
                                return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建RSI急涨分时买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        rsi_df = data.get('rsi_df')
        
        if close_prices is not None and rsi_df is not None and index < len(close_prices) and index < len(rsi_df):
            current_price = close_prices.iloc[index]
            current_rsi_5min = rsi_df.iloc[index].get('RSI6_5min', 0)
            
            # 计算RSI上升值（优先使用特殊情况，否则使用正常情况）
            rsi_rise = 0
            start_rsi_5min = 0
            
            # 检查特殊情况：10分钟时间窗口
            if index >= self.special_time_window:
                special_start_index = max(0, index - self.special_time_window)
                special_start_rsi_5min = rsi_df.iloc[special_start_index].get('RSI6_5min', 0)
                special_rsi_rise = current_rsi_5min - special_start_rsi_5min
                # 条件1：开始点RSI>80且确实上升
                # 条件2：开始点RSI=100的极端超买情况
                if (special_start_rsi_5min > 80 and special_rsi_rise > 0) or special_start_rsi_5min == 100:
                    rsi_rise = special_rsi_rise
                    start_rsi_5min = special_start_rsi_5min
            
            # 检查正常情况：5分钟时间窗口
            if rsi_rise == 0 and index >= self.normal_time_window:
                normal_start_index = max(0, index - self.normal_time_window)
                normal_start_rsi_5min = rsi_df.iloc[normal_start_index].get('RSI6_5min', 0)
                if (current_rsi_5min - normal_start_rsi_5min) >= self.normal_rsi_rise_threshold and current_rsi_5min >= 80:
                    rsi_rise = current_rsi_5min - normal_start_rsi_5min
                    start_rsi_5min = normal_start_rsi_5min
            
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            base_signal.update({
                'price': current_price,
                'rsi_5min_current': current_rsi_5min,
                'rsi_5min_start': start_rsi_5min,
                'rsi_rise': rsi_rise,
                'net_gain': net_gain,
                'fake_reason': None  # RSI急涨信号通常不需要假信号检查
            })
        
        return base_signal


class ResistanceBreakthroughBuySignal(IntradaySignalBase):
    """压力位突破分时买入信号"""
    
    def __init__(self, delay_minutes: int = 2, rsi_threshold: float = 30):
        """
        :param delay_minutes: 延迟确认时间（分钟），默认2分钟
        :param rsi_threshold: RSI阈值，用于确认买入信号，默认30
        """
        super().__init__("突破压力位分时买入", delay_minutes)
        self.rsi_threshold = rsi_threshold
        # 状态管理：跟踪压力位突破状态
        self._breakthrough_confirmed = False  # 是否已确认突破
        self._last_breakthrough_index = -1   # 上次突破的索引
        self._reset_triggered = False        # 是否已触发重置
    
    def _get_5min_price(self, price_df: pd.DataFrame, index: int) -> Optional[float]:
        """获取5分钟价格数据
        
        :param price_df: 1分钟价格数据
        :param index: 当前1分钟数据索引
        :return: 对应的5分钟收盘价，如果无法获取则返回None
        """
        try:
            if price_df is None or price_df.empty:
                return None
            
            # 将1分钟数据重采样为5分钟K线数据
            price_5min = price_df.resample('5T', offset='1min').agg({
                'open': 'first',
                'close': 'last', 
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            if price_5min.empty:
                return None
            
            # 获取当前1分钟时间点对应的5分钟K线
            current_time = price_df.index[index]
            
            # 找到包含当前时间的5分钟K线
            # 5分钟K线的时间戳是5分钟的整数倍（如09:30, 09:35, 09:40等）
            # 当前时间应该属于某个5分钟区间
            for ts, row in price_5min.iterrows():
                # 检查当前时间是否在这个5分钟区间内
                if current_time >= ts and current_time < ts + pd.Timedelta(minutes=5):
                    return row['close']
            
            # 如果没有找到对应的5分钟K线，返回最新的5分钟收盘价
            if len(price_5min) > 0:
                return price_5min['close'].iloc[-1]
            
            return None
            
        except Exception as e:
            print(f"[ERROR] 获取5分钟价格失败: {e}")
            return None
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否突破压力位（基于5分钟价格）
        
        :param data: 包含close_prices, resistance_level, price_df的字典
        :param index: 当前数据点索引
        :return: True表示突破压力位
        """
        close_prices = data.get('close_prices')
        resistance_level = data.get('resistance_level')
        price_df = data.get('price_df')
        
        if close_prices is None or resistance_level is None or price_df is None:
            print(f"[DEBUG] 压力位突破信号检查失败: close_prices={close_prices is not None}, resistance_level={resistance_level}, price_df={price_df is not None}")
            return False
        
        if index >= len(close_prices):
            print(f"[DEBUG] 压力位突破信号检查失败: 索引{index}超出范围{len(close_prices)}")
            return False
        
        # 获取5分钟价格数据
        current_price = self._get_5min_price(price_df, index)
        if current_price is None:
            return False
        
        # 检查是否突破压力位（当前分时价格 > 压力位）
        if current_price > resistance_level:
            # 如果已经确认突破且未重置，则不再触发
            if self._breakthrough_confirmed and not self._reset_triggered:
                print(f"[DEBUG] 压力位突破信号已确认，跳过重复触发: 价格{current_price:.3f} > 压力位{resistance_level:.3f}")
                return False
            
            # 检查是否重新跌破压力位（重置状态）
            if self._breakthrough_confirmed and current_price <= resistance_level:
                self._reset_triggered = True
                self._breakthrough_confirmed = False
                self._last_breakthrough_index = -1
                print(f"[DEBUG] 压力位突破状态重置：价格{current_price:.3f}重新跌破压力位{resistance_level:.3f}")
                return False
            
            # 首次突破或重置后的突破
            if not self._breakthrough_confirmed or self._reset_triggered:
                self._breakthrough_confirmed = True
                self._last_breakthrough_index = index
                self._reset_triggered = False
                print(f"[DEBUG] 压力位突破信号触发：价格{current_price:.3f}突破压力位{resistance_level:.3f} (索引{index})")
                return True
        
        # 检查是否重新跌破压力位（重置状态）
        elif current_price <= resistance_level and self._breakthrough_confirmed:
            if not self._reset_triggered:
                self._reset_triggered = True
                self._breakthrough_confirmed = False
                self._last_breakthrough_index = -1
                print(f"[DEBUG] 压力位突破状态重置：价格{current_price:.3f}重新跌破压力位{resistance_level:.3f}")
        
        return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假分时买入信号（当日涨幅过大）
        
        :param data: 包含close_prices, prev_close的字典
        :param index: 当前数据点索引
        :return: True表示是假分时买入信号
        """
        close_prices = data.get('close_prices')
        prev_close = data.get('prev_close')
        
        if close_prices is None or prev_close is None or prev_close <= 0 or index >= len(close_prices):
            return False
        
        current_price = close_prices.iloc[index]
        daily_change_pct = (current_price - prev_close) / prev_close * 100
        
        # 如果当日涨幅超过5%，可能是假信号
        return daily_change_pct >= 5.0
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证压力位突破分时买入信号有效性（延迟检查）
        
        :param data: 包含close_prices, resistance_level的字典
        :param signal_index: 分时信号产生时的索引
        :param current_index: 当前索引
        :return: True表示分时信号仍然有效
        """
        close_prices = data.get('close_prices')
        resistance_level = data.get('resistance_level')
        
        if close_prices is None or resistance_level is None:
            return False
        
        # 检查延迟时间内是否仍然突破压力位
        # 将延迟时间（分钟）转换为数据点数量，向上取整
        delay_points = int(np.ceil(self.delay_minutes))
        for check_i in range(signal_index + 1, min(signal_index + delay_points + 1, len(close_prices))):
            if check_i < len(close_prices):
                check_price = close_prices.iloc[check_i]
                
                # 如果价格回到压力位之下，信号无效
                if check_price <= resistance_level:
                    check_time_str = self._get_time_str(data, check_i)
                    signal_time_str = self._get_time_str(data, signal_index)
                    print(f"[DEBUG] 压力位突破信号无效：价格回到压力位之下，信号时间={signal_time_str}, 确认时间={check_time_str}, 价格={check_price:.3f}, 压力位={resistance_level:.3f}")
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建压力位突破分时买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        resistance_level = data.get('resistance_level')
        prev_close = data.get('prev_close')
        
        if (close_prices is not None and 
            index < len(close_prices)):
            
            current_price = close_prices.iloc[index]
            
            # 计算到压力位的距离
            distance_to_resistance = ((current_price - resistance_level) / current_price) * 100 if current_price > 0 else 0
            
            # 计算当日涨跌幅
            daily_change_pct = ((current_price - prev_close) / prev_close) * 100 if prev_close and prev_close > 0 else 0
            
            # 更新信号数据
            base_signal.update({
                'price': current_price,
                'resistance_level': resistance_level,
                'distance_to_resistance': distance_to_resistance,
                'daily_change_pct': daily_change_pct,
                'net_gain': daily_change_pct,  # 添加net_gain字段，用于信号绘制
                'signal_info': f"突破压力位({resistance_level:.3f})"
            })
        
        return base_signal
    
    def reset_state(self):
        """重置压力位突破状态（用于日期切换或股票代码变化）"""
        self._breakthrough_confirmed = False
        self._last_breakthrough_index = -1
        self._reset_triggered = False
        print("[DEBUG] 压力位突破状态已重置")


class LimitUpConsecutiveBuySignal(IntradaySignalBase):
    """连板涨停买入信号"""
    
    def __init__(self, delay_minutes: float = 0.0):
        """
        :param delay_minutes: 延迟确认时间（分钟），连板信号不需要延迟
        """
        super().__init__("连板涨停买入", delay_minutes)
        self._prev_day_limit_up = None  # 缓存上一个交易日是否涨停
        self._prev_day_bollinger_high = None  # 缓存上一个交易日布林带最高点
        self._prev_day_pct_change = None  # 缓存上一个交易日涨跌幅
    
    def _check_previous_day_limit_up(self, data: Dict[str, Any]) -> tuple[bool, float, float]:
        """检查上一个交易日是否涨停
        :param data: 包含所有必要数据的字典
        :return: (是否涨停, 涨跌幅, 布林带最高点)
        """
        try:
            # 获取当前交易日数据
            price_df = data.get('price_df')
            if price_df is None or price_df.empty:
                return False, 0.0, 0.0
            
            # 获取当前交易日日期
            current_date = price_df.index[0].date()
            
            # 计算上一个交易日
            from datetime import timedelta
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:  # 跳过周末
                prev_date -= timedelta(days=1)
            
            prev_date_str = prev_date.strftime('%Y-%m-%d')
            
            # 获取证券类型和代码
            code = data.get('code', '')
            security_type, symbol = self._get_security_type(code)
            
            # 获取上一个交易日的日线数据
            import akshare as ak
            if security_type == "STOCK":
                daily_data = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=prev_date_str.replace('-', ''),
                    end_date=prev_date_str.replace('-', ''),
                    adjust="qfq"
                )
            elif security_type == "ETF":
                daily_data = ak.fund_etf_hist_em(
                    symbol=symbol,
                    start_date=prev_date_str,
                    end_date=prev_date_str,
                    adjust="qfq"
                )
            else:
                return False, 0.0, 0.0
            
            if daily_data.empty:
                print(f"[DEBUG] 连板信号：未获取到上一个交易日 {prev_date_str} 的日线数据")
                return False, 0.0, 0.0
            
            # 计算涨跌幅（使用前一个交易日的收盘价作为基准）
            close_price = float(daily_data.iloc[-1]["收盘"])
            
            # 获取前一个交易日的收盘价
            prev_prev_date = prev_date - timedelta(days=1)
            while prev_prev_date.weekday() >= 5:  # 跳过周末
                prev_prev_date -= timedelta(days=1)
            
            prev_prev_date_str = prev_prev_date.strftime('%Y-%m-%d')
            
            # 获取前一个交易日的日线数据
            if security_type == "STOCK":
                prev_daily_data = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=prev_prev_date_str.replace('-', ''),
                    end_date=prev_prev_date_str.replace('-', ''),
                    adjust="qfq"
                )
            elif security_type == "ETF":
                prev_daily_data = ak.fund_etf_hist_em(
                    symbol=symbol,
                    start_date=prev_prev_date_str,
                    end_date=prev_prev_date_str,
                    adjust="qfq"
                )
            else:
                return False, 0.0, 0.0
            
            if prev_daily_data.empty:
                print(f"[DEBUG] 连板信号：未获取到前一个交易日 {prev_prev_date_str} 的日线数据")
                return False, 0.0, 0.0
            
            prev_close_price = float(prev_daily_data.iloc[-1]["收盘"])
            pct_change = ((close_price - prev_close_price) / prev_close_price) * 100
            
            # 使用统一的涨跌停检测函数
            is_limit_up, _ = is_limit_up_down(data.get('code', ''), close_price, prev_close_price)
            
            if not is_limit_up:
                print(f"[DEBUG] 连板信号：上一个交易日 {prev_date_str} 未涨停，涨跌幅: {pct_change:.2f}%")
                return False, pct_change, 0.0
            
            # 获取上一个交易日的分时数据计算布林带最高点
            bollinger_high = self._calculate_prev_day_bollinger_high(data, prev_date_str, security_type, symbol)
            
            print(f"[DEBUG] 连板信号：上一个交易日 {prev_date_str} 涨停，涨跌幅: {pct_change:.2f}%，布林带最高点: {bollinger_high:.3f}")
            return True, pct_change, bollinger_high
            
        except Exception as e:
            print(f"[ERROR] 连板信号：检查上一个交易日涨停失败: {str(e)}")
            return False, 0.0, 0.0
    
    def _get_security_type(self, code: str) -> tuple:
        """获取证券类型和对应的数据接口代码"""
        if code == "1A0001" or code == "000001":
            return "INDEX", "000001"
        elif len(code) == 6 and code.startswith(("5", "15")):
            return "ETF", code
        else:
            return "STOCK", code
    
    def _calculate_prev_day_bollinger_high(self, data: Dict[str, Any], prev_date_str: str, security_type: str, symbol: str) -> float:
        """计算上一个交易日日内1分钟布林带最高点
        :param data: 包含所有必要数据的字典
        :param prev_date_str: 上一个交易日日期字符串
        :param security_type: 证券类型
        :param symbol: 证券代码
        :return: 布林带最高点
        """
        try:
            import akshare as ak

            # 获取上一个交易日的分时数据
            start_dt = f"{prev_date_str} 09:30:00"
            end_dt = f"{prev_date_str} 15:00:00"
            
            if security_type == "STOCK":
                prev_intraday_df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            elif security_type == "ETF":
                prev_intraday_df = ak.fund_etf_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            else:
                return 0.0
            
            if prev_intraday_df.empty:
                print(f"[DEBUG] 连板信号：未获取到上一个交易日 {prev_date_str} 的分时数据")
                return 0.0
            
            # 统一列名
            if '时间' in prev_intraday_df.columns:
                prev_intraday_df.rename(columns={
                    "时间": "datetime", 
                    "开盘": "open", 
                    "收盘": "close", 
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume"
                }, inplace=True)
                prev_intraday_df["datetime"] = pd.to_datetime(prev_intraday_df["datetime"])
                prev_intraday_df.set_index("datetime", inplace=True)
            
            # 计算1分钟布林带
            window = 20
            ma20 = prev_intraday_df['close'].rolling(window=window, min_periods=1).mean()
            std = prev_intraday_df['close'].rolling(window=window, min_periods=1).std()
            upper_band = ma20 + 2 * std
            
            # 找到布林带上轨的最高点
            bollinger_high = upper_band.max()
            
            print(f"[DEBUG] 连板信号：上一个交易日布林带最高点计算完成: {bollinger_high:.3f}")
            return bollinger_high
            
        except Exception as e:
            print(f"[ERROR] 连板信号：计算上一个交易日布林带最高点失败: {str(e)}")
            return 0.0
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查连板涨停买入信号条件
        :param data: 包含所有必要数据的字典
        :param index: 当前数据点索引
        :return: True表示满足连板信号条件
        """
        try:
            # 检查是否在9:25-9:31时间段内
            close_prices = data.get('close_prices')
            if close_prices is None or index >= len(close_prices):
                return False
            
            current_time = close_prices.index[index]
            time_str = current_time.strftime('%H:%M')
            
            # 只在9:25-9:31时间段内检查（包含9:30开盘）
            if not ('09:25' <= time_str <= '09:31'):
                return False
            
            print(f"[DEBUG] 连板信号：检查时间 {time_str}，在9:25-9:31范围内")
            
            # 检查上一个交易日是否涨停（缓存结果避免重复计算）
            if self._prev_day_limit_up is None:
                is_limit_up, pct_change, bollinger_high = self._check_previous_day_limit_up(data)
                self._prev_day_limit_up = is_limit_up
                self._prev_day_pct_change = pct_change
                self._prev_day_bollinger_high = bollinger_high
            else:
                is_limit_up = self._prev_day_limit_up
                pct_change = self._prev_day_pct_change
                bollinger_high = self._prev_day_bollinger_high
            
            if not is_limit_up or bollinger_high <= 0:
                return False
            
            # 检查当前开盘价是否 >= 布林带最高点
            current_price = close_prices.iloc[index]
            if current_price >= bollinger_high:
                print(f"[DEBUG] 连板信号触发：时间 {time_str}，当前价格 {current_price:.3f} >= 布林带最高点 {bollinger_high:.3f}")
                return True
            
            return False
            
        except Exception as e:
            print(f"[ERROR] 连板信号：检查条件失败: {str(e)}")
            return False
    
    def check_fake_signal(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否为假连板信号
        :param data: 包含所有必要数据的字典
        :param index: 当前数据点索引
        :return: True表示是假信号
        """
        # 连板信号不进行假信号检查，因为已经通过涨停和布林带条件验证
        return False
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证连板信号有效性
        :param data: 包含所有必要数据的字典
        :param signal_index: 信号产生时的索引
        :param current_index: 当前索引
        :return: True表示信号仍然有效
        """
        # 连板信号立即生效，不需要延迟验证
        # 因为连板信号已经设置了 wait_validate=False
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建连板信号数据
        :param data: 包含所有必要数据的字典
        :param index: 信号产生的索引
        :return: 信号数据字典
        """
        try:
            # 获取涨跌幅信息
            pct_change = self._prev_day_pct_change or 0.0
            
            # 创建信号数据
            close_prices = data.get('close_prices')
            if close_prices is not None and index < len(close_prices):
                price = close_prices.iloc[index]
            else:
                price = 0.0
                
            # 计算当日涨跌幅（相对于前一交易日收盘价）
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
                
            signal_data = {
                'index': index,
                'timestamp': index,
                'signal_type': self.name,  # 使用signal.name而不是自定义格式
                'price': price,
                'net_gain': net_gain,  # 添加net_gain字段
                'is_fake': False,
                'wait_validate': False,  # 连板信号不需要延迟验证
                'color': 'red',  # 红色实线
                'line_style': '-',  # 实线
                'display_label': f"{pct_change:.1f}%连板"  # 用于显示的标签
            }
            
            print(f"[DEBUG] 连板信号创建：{signal_data['signal_type']}，显示标签: {signal_data['display_label']}，价格: {signal_data['price']:.3f}")
            return signal_data
            
        except Exception as e:
            print(f"[ERROR] 连板信号：创建信号数据失败: {str(e)}")
            return super().create_signal_data(data, index)


class IntradaySignalManager:
    """分时信号管理器"""
    
    def __init__(self):
        self.buy_signals: List[IntradaySignalBase] = []
        self.sell_signals: List[IntradaySignalBase] = []
        self.buy_signal_pending: Dict[int, Dict[str, Any]] = {}
        self.sell_signal_pending: Dict[int, Dict[str, Any]] = {}
    
    def add_buy_signal(self, signal: IntradaySignalBase):
        """添加分时买入信号"""
        self.buy_signals.append(signal)
    
    def add_sell_signal(self, signal: IntradaySignalBase):
        """添加分时卖出信号"""
        self.sell_signals.append(signal)
    
    def detect_buy_signals(self, data: Dict[str, Any], close_prices: pd.Series) -> List[Dict[str, Any]]:
        """检测所有分时买入信号"""
        confirmed_signals = []
        current_index = len(close_prices) - 1
        
        print(f"[DEBUG] 开始检测买入信号，数据长度: {len(close_prices)}, 当前索引: {current_index}")
        print(f"[DEBUG] 已配置的买入信号数量: {len(self.buy_signals)}")
        
        # 获取最近一次布林带突破类型（用于假信号判断）
        latest_bollinger_type = 'none'
        try:
            from trading_utils import get_latest_bollinger_breakthrough_type
            price_df = data.get('price_df')
            bollinger_upper = data.get('bollinger_upper')
            bollinger_lower = data.get('bollinger_lower')
            
            if (price_df is not None and bollinger_upper is not None and bollinger_lower is not None):
                latest_bollinger_type = get_latest_bollinger_breakthrough_type(
                    price_data=price_df,
                    bollinger_upper=bollinger_upper,
                    bollinger_lower=bollinger_lower
                )
                print(f"[DEBUG] 最近一次布林带突破类型: {latest_bollinger_type}")
        except Exception as e:
            print(f"[WARNING] 获取最近布林带突破类型失败: {e}")
        
        # 检测所有分时买入信号
        for i in range(1, len(close_prices)):
            for signal in self.buy_signals:
                # 添加调试信息
                if i % 10 == 0:  # 每10个数据点输出一次调试信息
                    print(f"[DEBUG] 检查索引 {i}, 信号类型: {signal.name}")
                
                if signal.check_condition(data, i):
                    print(f"[DEBUG] 发现买入信号条件满足，索引: {i}")
                    # 记录待确认的分时买入信号（但不立即显示）
                    if i not in self.buy_signal_pending:
                        signal_data = signal.create_signal_data(data, i)
                        
                        # 检查布林带突破类型，判断是否为假信号
                        if latest_bollinger_type == 'breakdown':
                            # 最近一次破日内5分钟布林通道是跌波下轨类型，标记为假信号
                            signal_data['is_fake'] = True
                            signal_data['fake_reason'] = f"最近一次布林带突破为跌波下轨类型({latest_bollinger_type})"
                            print(f"[DEBUG] 买入信号标记为假信号: 最近布林带突破类型={latest_bollinger_type}")
                        
                        self.buy_signal_pending[i] = signal_data
                        
                        # 获取时间字符串用于调试
                        time_str = signal._get_time_str(data, i)
                        
                        # 根据是否为假信号输出不同的日志
                        if signal_data.get('is_fake', False):
                            print(f"记录待确认假分时买入信号: 时间={time_str}, 类型={signal.name}, 原因={signal_data.get('fake_reason', '未知')}")
                        else:
                            print(f"记录待确认分时买入信号: 时间={time_str}, 类型={signal.name}")
                    else:
                        print(f"[DEBUG] 索引 {i} 的买入信号已在待确认列表中")
        
        # 延迟检查：处理延迟时间前记录的分时信号
        signals_to_remove = []
        
        print(f"[DEBUG] 开始延迟检查，待确认信号数量: {len(self.buy_signal_pending)}")
        
        for signal_index, signal_data in self.buy_signal_pending.items():
            # 找到对应的分时信号对象
            signal_obj = None
            for signal in self.buy_signals:
                if signal.name == signal_data.get('signal_type'):
                    signal_obj = signal
                    break
            
            if signal_obj is None:
                print(f"[DEBUG] 未找到对应的信号对象: {signal_data.get('signal_type')}")
                continue
            
            # 检查是否已经过去延迟时间（包括延迟时间为0的情况）
            time_diff = current_index - signal_data['timestamp']
            # 将延迟时间（分钟）转换为数据点数量，向上取整
            delay_required_points = int(np.ceil(signal_obj.delay_minutes))
            print(f"[DEBUG] 检查待确认信号: 索引={signal_index}, 时间戳={signal_data['timestamp']}, 时间差={time_diff}, 延迟要求={signal_obj.delay_minutes}分钟({delay_required_points}个数据点)")
            
            if time_diff >= delay_required_points:
                print(f"[DEBUG] 满足延迟要求，开始验证信号有效性")
                # 验证分时信号有效性
                if signal_obj.validate_signal(data, signal_data['timestamp'], current_index):
                    # 保持信号原有的wait_validate设置，不强制覆盖
                    # 连板信号等不需要延迟验证的信号会保持wait_validate=False
                    confirmed_signals.append(signal_data)
                    
                    # 获取时间字符串用于调试
                    time_str = signal_obj._get_time_str(data, signal_data['index'])
                    
                    # 根据是否为假信号输出不同的日志
                    if signal_data.get('is_fake', False):
                        print(f"确认假分时买入信号(待确认): 时间={time_str}, 类型={signal_obj.name}, 延迟检查通过, 原因={signal_data.get('fake_reason', '未知')}")
                    else:
                        print(f"确认分时买入信号(待确认): 时间={time_str}, 类型={signal_obj.name}, 延迟检查通过")
                else:
                    # 获取时间字符串用于调试
                    time_str = signal_obj._get_time_str(data, signal_data['index'])
                    print(f"分时买入信号无效: 时间={time_str}, 类型={signal_obj.name}, 延迟检查失败")
                
                # 标记为移除
                signals_to_remove.append(signal_index)
            else:
                print(f"[DEBUG] 不满足延迟要求，继续等待")
        
        # 移除已处理的分时信号
        for signal_index in signals_to_remove:
            del self.buy_signal_pending[signal_index]
        
        print(f"[DEBUG] 买入信号检测完成，确认信号数量: {len(confirmed_signals)}")
        return confirmed_signals
    
    def detect_sell_signals(self, data: Dict[str, Any], close_prices: pd.Series) -> List[Dict[str, Any]]:
        """检测所有分时卖出信号"""
        confirmed_signals = []
        current_index = len(close_prices) - 1
        
        print(f"[DEBUG] 开始检测卖出信号，数据长度: {len(close_prices)}, 当前索引: {current_index}")
        print(f"[DEBUG] 已配置的卖出信号数量: {len(self.sell_signals)}")
        
        # 获取最近一次布林带突破类型（用于假信号判断）
        latest_bollinger_type = 'none'
        try:
            from trading_utils import get_latest_bollinger_breakthrough_type
            price_df = data.get('price_df')
            bollinger_upper = data.get('bollinger_upper')
            bollinger_lower = data.get('bollinger_lower')
            
            if (price_df is not None and bollinger_upper is not None and bollinger_lower is not None):
                latest_bollinger_type = get_latest_bollinger_breakthrough_type(
                    price_data=price_df,
                    bollinger_upper=bollinger_upper,
                    bollinger_lower=bollinger_lower
                )
                print(f"[DEBUG] 最近一次布林带突破类型: {latest_bollinger_type}")
        except Exception as e:
            print(f"[WARNING] 获取最近布林带突破类型失败: {e}")
        
        # 检测所有分时卖出信号
        for i in range(len(close_prices)):
            for signal in self.sell_signals:
                if signal.check_condition(data, i):
                    print(f"[DEBUG] 发现卖出信号条件满足，索引: {i}")
                    # 记录待确认的分时卖出信号（但不立即显示）
                    if i not in self.sell_signal_pending:
                        signal_data = signal.create_signal_data(data, i)
                        
                        # 检查布林带突破类型，判断是否为假信号
                        if latest_bollinger_type == 'breakthrough':
                            # 最近一次破日内5分钟布林通道是涨波上轨类型，标记为假信号
                            signal_data['is_fake'] = True
                            signal_data['fake_reason'] = f"最近一次布林带突破为涨波上轨类型({latest_bollinger_type})"
                            print(f"[DEBUG] 卖出信号标记为假信号: 最近布林带突破类型={latest_bollinger_type}")
                        
                        self.sell_signal_pending[i] = signal_data
                        
                        # 获取时间字符串用于调试
                        time_str = signal._get_time_str(data, i)
                        
                        # 根据是否为假信号输出不同的日志
                        if signal_data.get('is_fake', False):
                            print(f"记录待确认假分时卖出信号: 时间={time_str}, 类型={signal.name}, 原因={signal_data.get('fake_reason', '未知')}")
                        else:
                            print(f"记录待确认分时卖出信号: 时间={time_str}, 类型={signal.name}")
                    else:
                        print(f"[DEBUG] 索引 {i} 的卖出信号已在待确认列表中")
        
        # 延迟检查：处理延迟时间前记录的分时信号
        signals_to_remove = []
        
        print(f"[DEBUG] 开始延迟检查，待确认信号数量: {len(self.sell_signal_pending)}")
        
        for signal_index, signal_data in self.sell_signal_pending.items():
            # 找到对应的分时信号对象
            signal_obj = None
            for signal in self.sell_signals:
                if signal.name == signal_data.get('signal_type'):
                    signal_obj = signal
                    break
            
            if signal_obj is None:
                print(f"[DEBUG] 未找到对应的信号对象: {signal_data.get('signal_type')}")
                continue
            
            # 检查是否已经过去延迟时间
            time_diff = current_index - signal_data['timestamp']
            # 将延迟时间（分钟）转换为数据点数量，向上取整
            delay_required_points = int(np.ceil(signal_obj.delay_minutes))
            print(f"[DEBUG] 检查待确认信号: 索引={signal_index}, 时间戳={signal_data['timestamp']}, 时间差={time_diff}, 延迟要求={signal_obj.delay_minutes}分钟({delay_required_points}个数据点)")
            
            if time_diff >= delay_required_points:
                print(f"[DEBUG] 满足延迟要求，开始验证信号有效性")
                # 验证分时信号有效性
                if signal_obj.validate_signal(data, signal_data['timestamp'], current_index):
                    # 保持信号原有的wait_validate设置，不强制覆盖
                    # 连板信号等不需要延迟验证的信号会保持wait_validate=False
                    confirmed_signals.append(signal_data)
                    
                    # 获取时间字符串用于调试
                    time_str = signal_obj._get_time_str(data, signal_data['index'])
                    
                    # 根据是否为假信号输出不同的日志
                    if signal_data.get('is_fake', False):
                        print(f"确认假分时卖出信号(待确认): 时间={time_str}, 类型={signal_obj.name}, 延迟检查通过, 原因={signal_data.get('fake_reason', '未知')}")
                    else:
                        print(f"确认分时卖出信号(待确认): 时间={time_str}, 类型={signal_obj.name}, 延迟检查通过")
                else:
                    # 获取时间字符串用于调试
                    time_str = signal_obj._get_time_str(data, signal_data['index'])
                    print(f"分时卖出信号无效: 时间={time_str}, 类型={signal_obj.name}, 延迟检查失败")
                
                # 标记为移除
                signals_to_remove.append(signal_index)
            else:
                print(f"[DEBUG] 不满足延迟要求，继续等待")
        
        # 移除已处理的分时信号
        for signal_index in signals_to_remove:
            del self.sell_signal_pending[signal_index]
        
        print(f"[DEBUG] 卖出信号检测完成，确认信号数量: {len(confirmed_signals)}")
        return confirmed_signals
    
    def clear_pending_signals(self):
        """清空待确认分时信号"""
        self.buy_signal_pending.clear()
        self.sell_signal_pending.clear()
    
    def reset_all_signal_states(self):
        """重置所有信号的状态（用于日期切换或股票代码变化）"""
        for signal in self.buy_signals:
            # 使用getattr安全地获取方法，如果不存在则返回None
            reset_method = getattr(signal, 'reset_state', None)
            if reset_method is not None and callable(reset_method):
                reset_method()
        
        for signal in self.sell_signals:
            # 使用getattr安全地获取方法，如果不存在则返回None
            reset_method = getattr(signal, 'reset_state', None)
            if reset_method is not None and callable(reset_method):
                reset_method()
        
        print("[DEBUG] 所有信号状态已重置")
    
    def detect_support_breakdown_signals(self, data: Dict[str, Any], close_prices: pd.Series) -> List[Dict[str, Any]]:
        """检测支撑位跌破卖出信号"""
        confirmed_signals = []
        current_index = len(close_prices) - 1
        
        # 创建支撑位跌破卖出信号对象
        support_breakdown_signal = SupportBreakdownSellSignal()
        
        print(f"[DEBUG] 开始检测支撑位跌破卖出信号，数据长度: {len(close_prices)}, 当前索引: {current_index}")
        print(f"[DEBUG] 支撑位: {data.get('support_level')}")
        
        # 检测支撑位跌破卖出信号
        for i in range(len(close_prices)):
            if support_breakdown_signal.check_condition(data, i):
                print(f"[DEBUG] 发现支撑位跌破信号条件满足，索引: {i}")
                # 记录待确认的分时卖出信号（但不立即显示）
                if i not in self.sell_signal_pending:
                    signal_data = support_breakdown_signal.create_signal_data(data, i)
                    self.sell_signal_pending[i] = signal_data
                    
                    # 获取时间字符串用于调试
                    time_str = support_breakdown_signal._get_time_str(data, i)
                    
                    # 根据是否为假信号输出不同的日志
                    if signal_data.get('is_fake', False):
                        print(f"记录待确认假分时卖出信号: 时间={time_str}, 类型={support_breakdown_signal.name}, 原因={signal_data.get('fake_reason', '未知')}")
                    else:
                        print(f"记录待确认分时卖出信号: 时间={time_str}, 类型={support_breakdown_signal.name}")
                else:
                    print(f"[DEBUG] 索引 {i} 的支撑位跌破信号已在待确认列表中")
        
        # 延迟检查：处理延迟时间前记录的分时信号
        signals_to_remove = []
        
        print(f"[DEBUG] 开始延迟检查支撑位跌破信号，待确认信号数量: {len(self.sell_signal_pending)}")
        
        for signal_index, signal_data in self.sell_signal_pending.items():
            # 检查是否为支撑位跌破信号
            if signal_data.get('signal_type') == support_breakdown_signal.name:
                # 检查是否已经过去延迟时间
                time_diff = current_index - signal_data['timestamp']
                # 将延迟时间（分钟）转换为数据点数量，向上取整
                delay_required_points = int(np.ceil(support_breakdown_signal.delay_minutes))
                print(f"[DEBUG] 检查待确认支撑位跌破信号: 索引={signal_index}, 时间戳={signal_data['timestamp']}, 时间差={time_diff}, 延迟要求={support_breakdown_signal.delay_minutes}分钟({delay_required_points}个数据点)")
                
                if time_diff >= delay_required_points:
                    print(f"[DEBUG] 满足延迟要求，开始验证支撑位跌破信号有效性")
                    # 验证分时信号有效性
                    if support_breakdown_signal.validate_signal(data, signal_data['timestamp'], current_index):
                        # 确认分时卖出信号（延迟验证通过后才显示）
                        confirmed_signals.append(signal_data)
                        
                        # 获取时间字符串用于调试
                        time_str = support_breakdown_signal._get_time_str(data, signal_data['index'])
                        
                        # 根据是否为假信号输出不同的日志
                        if signal_data.get('is_fake', False):
                            print(f"确认假分时卖出信号: 时间={time_str}, 类型={support_breakdown_signal.name}, 延迟检查通过, 原因={signal_data.get('fake_reason', '未知')}")
                        else:
                            print(f"确认分时卖出信号: 时间={time_str}, 类型={support_breakdown_signal.name}, 延迟检查通过")
                    else:
                        # 获取时间字符串用于调试
                        time_str = support_breakdown_signal._get_time_str(data, signal_data['index'])
                        print(f"分时卖出信号无效: 时间={time_str}, 类型={support_breakdown_signal.name}, 延迟检查失败")
                    
                    # 标记为移除
                    signals_to_remove.append(signal_index)
                else:
                    print(f"[DEBUG] 不满足延迟要求，继续等待")
        
        # 移除已处理的分时信号
        for signal_index in signals_to_remove:
            del self.sell_signal_pending[signal_index]
        
        print(f"[DEBUG] 支撑位跌破卖出信号检测完成，确认信号数量: {len(confirmed_signals)}")
        return confirmed_signals
    
    def detect_resistance_breakthrough_signals(self, data: Dict[str, Any], close_prices: pd.Series) -> List[Dict[str, Any]]:
        """检测压力位突破买入信号"""
        confirmed_signals = []
        current_index = len(close_prices) - 1
        
        # 创建压力位突破买入信号对象
        resistance_breakthrough_signal = ResistanceBreakthroughBuySignal()
        
        print(f"[DEBUG] 开始检测压力位突破买入信号，数据长度: {len(close_prices)}, 当前索引: {current_index}")
        print(f"[DEBUG] 压力位: {data.get('resistance_level')}")
        
        # 检测压力位突破买入信号
        for i in range(len(close_prices)):
            if resistance_breakthrough_signal.check_condition(data, i):
                print(f"[DEBUG] 发现压力位突破信号条件满足，索引: {i}")
                # 记录待确认的分时买入信号（但不立即显示）
                if i not in self.buy_signal_pending:
                    signal_data = resistance_breakthrough_signal.create_signal_data(data, i)
                    self.buy_signal_pending[i] = signal_data
                    
                    # 获取时间字符串用于调试
                    time_str = resistance_breakthrough_signal._get_time_str(data, i)
                    
                    # 根据是否为假信号输出不同的日志
                    if signal_data.get('is_fake', False):
                        print(f"记录待确认假分时买入信号: 时间={time_str}, 类型={resistance_breakthrough_signal.name}, 原因={signal_data.get('fake_reason', '未知')}")
                    else:
                        print(f"记录待确认分时买入信号: 时间={time_str}, 类型={resistance_breakthrough_signal.name}")
                else:
                    print(f"[DEBUG] 索引 {i} 的压力位突破信号已在待确认列表中")
        
        # 延迟检查：处理延迟时间前记录的分时信号
        signals_to_remove = []
        
        print(f"[DEBUG] 开始延迟检查压力位突破信号，待确认信号数量: {len(self.buy_signal_pending)}")
        
        for signal_index, signal_data in self.buy_signal_pending.items():
            # 检查是否为压力位突破信号
            if signal_data.get('signal_type') == resistance_breakthrough_signal.name:
                # 检查是否已经过去延迟时间
                time_diff = current_index - signal_data['timestamp']
                # 将延迟时间（分钟）转换为数据点数量，向上取整
                delay_required_points = int(np.ceil(resistance_breakthrough_signal.delay_minutes))
                print(f"[DEBUG] 检查待确认压力位突破信号: 索引={signal_index}, 时间戳={signal_data['timestamp']}, 时间差={time_diff}, 延迟要求={resistance_breakthrough_signal.delay_minutes}分钟({delay_required_points}个数据点)")
                
                if time_diff >= delay_required_points:
                    print(f"[DEBUG] 满足延迟要求，开始验证压力位突破信号有效性")
                    # 验证分时信号有效性
                    if resistance_breakthrough_signal.validate_signal(data, signal_data['timestamp'], current_index):
                        # 确认分时买入信号（延迟验证通过后才显示）
                        confirmed_signals.append(signal_data)
                        
                        # 获取时间字符串用于调试
                        time_str = resistance_breakthrough_signal._get_time_str(data, signal_data['index'])
                        
                        # 根据是否为假信号输出不同的日志
                        if signal_data.get('is_fake', False):
                            print(f"确认假分时买入信号: 时间={time_str}, 类型={resistance_breakthrough_signal.name}, 延迟检查通过, 原因={signal_data.get('fake_reason', '未知')}")
                        else:
                            print(f"确认分时买入信号: 时间={time_str}, 类型={resistance_breakthrough_signal.name}, 延迟检查通过")
                    else:
                        # 获取时间字符串用于调试
                        time_str = resistance_breakthrough_signal._get_time_str(data, signal_data['index'])
                        print(f"分时买入信号无效: 时间={time_str}, 类型={resistance_breakthrough_signal.name}, 延迟检查失败")
                    
                    # 标记为移除
                    signals_to_remove.append(signal_index)
                else:
                    print(f"[DEBUG] 不满足延迟要求，继续等待")
        
        # 移除已处理的分时信号
        for signal_index in signals_to_remove:
            del self.buy_signal_pending[signal_index]
        
        print(f"[DEBUG] 压力位突破买入信号检测完成，确认信号数量: {len(confirmed_signals)}")
        return confirmed_signals
    
    def validate_wait_confirm_signals(self, data: Dict[str, Any], current_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证待确认信号的有效性（60秒重新检测时调用）
        
        :param data: 包含所有必要数据的字典
        :param current_signals: 当前信号列表
        :return: 验证后的信号列表
        """
        validated_signals = []
        
        for signal in current_signals:
            # 只处理wait_validate=True的信号
            if not signal.get('wait_validate', False):
                validated_signals.append(signal)
                continue
            
            # 找到对应的信号对象
            signal_obj = None
            signal_type = signal.get('signal_type', '')
            
            # 在买入和卖出信号中查找
            for buy_signal in self.buy_signals:
                if buy_signal.name == signal_type:
                    signal_obj = buy_signal
                    break
            
            if signal_obj is None:
                for sell_signal in self.sell_signals:
                    if sell_signal.name == signal_type:
                        signal_obj = sell_signal
                        break
            
            if signal_obj is None:
                print(f"[DEBUG] 未找到对应的信号对象: {signal_type}")
                validated_signals.append(signal)
                continue
            
            # 重新验证信号条件
            signal_index = signal['index']
            if signal_obj.check_condition(data, signal_index):
                # 信号仍然有效，标记为已确认（wait_validate=false）
                signal['wait_validate'] = False
                validated_signals.append(signal)
                
                time_str = signal_obj._get_time_str(data, signal_index)
                print(f"[DEBUG] 信号重新验证有效: 时间={time_str}, 类型={signal_type}, 已确认")
            else:
                # 信号不再有效，移除该信号
                time_str = signal_obj._get_time_str(data, signal_index)
                print(f"[DEBUG] 信号重新验证无效: 时间={time_str}, 类型={signal_type}, 已移除")
        
        return validated_signals
