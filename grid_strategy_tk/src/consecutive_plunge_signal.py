"""
连续连跌卖出信号
"""

from typing import Any, Dict

try:
    from .consecutive_signal_config import get_plunge_config
    from .intraday_signals import IntradaySignalBase
except ImportError:
    from consecutive_signal_config import get_plunge_config
    from intraday_signals import IntradaySignalBase


class ConsecutivePlungeSellSignal(IntradaySignalBase):
    """
    连续连跌卖出信号
    
    判断条件：
    1. 连续N个1分钟K线都是阴线（收盘价 < 开盘价）
    2. 没有延迟，立即触发
    3. 每次出现连跌都会绘制信号，直到出现阳线后重新开始计算
    """
    
    def __init__(self, consecutive_count: int = None, delay_minutes: float = 0.0):
        """
        :param consecutive_count: 连续阴线数量，默认使用配置文件中的值
        :param delay_minutes: 延迟确认时间（分钟），默认0.0分钟（立即触发）
        """
        # 获取配置
        config = get_plunge_config()
        if consecutive_count is None:
            consecutive_count = config['consecutive_count']
        
        super().__init__(f"{config['signal_name_prefix']}{consecutive_count}", delay_minutes)
        self.consecutive_count = consecutive_count
        self.config = config
        self._last_signal_index = -1  # 记录上次信号的索引，避免重复触发
        self._in_consecutive_sequence = False  # 标记是否在连续序列中
        self._has_displayed_signal = False  # 标记是否已经显示过连跌信号
        self._buy_signal_appeared = False  # 标记是否已经出现买入信号
    
    def reset_state(self):
        """重置信号状态，用于重新检测"""
        self._last_signal_index = -1
        self._in_consecutive_sequence = False
        self._has_displayed_signal = False
        self._buy_signal_appeared = False
        print(f"[DEBUG] 连跌信号状态已重置")
    
    def mark_buy_signal_appeared(self):
        """标记买入信号已出现，重置连跌信号显示状态"""
        self._buy_signal_appeared = True
        self._has_displayed_signal = False
        self._in_consecutive_sequence = False  # 重置连续序列状态
        print(f"[DEBUG] 买入信号已出现，重置连跌信号显示状态")
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查是否满足连续连跌条件
        
        :param data: 包含价格数据的字典
        :param index: 当前数据索引
        :return: 是否满足连跌条件
        """
        try:
            # 获取价格数据
            close_prices = data.get('close_prices')
            open_prices = data.get('open_prices')
            kdj_d_values = data.get('kdj_d_values')  # 获取KDJ的D值数据
            
            # 添加调试信息
            if index % 50 == 0:  # 每50个数据点输出一次调试信息
                print(f"[DEBUG] 连跌信号检测: 索引={index}, close_prices={'有' if close_prices is not None else '无'}, open_prices={'有' if open_prices is not None else '无'}")
            
            if close_prices is None or open_prices is None:
                if index % 50 == 0:
                    print(f"[DEBUG] 连跌信号检测失败: 缺少价格数据")
                return False
            
            # 检查是否有足够的数据点
            if index < self.consecutive_count - 1:
                return False
            
            # 检查当前K线是否为阴线（收盘价 < 开盘价，排除平盘）
            close_price = close_prices.iloc[index] if hasattr(close_prices, 'iloc') else close_prices[index]
            open_price = open_prices.iloc[index] if hasattr(open_prices, 'iloc') else open_prices[index]
            current_is_bearish = close_price < open_price
            
            if not current_is_bearish:
                # 当前不是阴线（包括平盘），重置连续序列状态
                self._in_consecutive_sequence = False
                return False
            
            # 当前是阴线，检查连续阴线数量
            consecutive_bearish = 0
            for i in range(index, -1, -1):  # 从当前索引向前检查
                if i < 0 or i >= len(close_prices) or i >= len(open_prices):
                    break
                
                close_price = close_prices.iloc[i] if hasattr(close_prices, 'iloc') else close_prices[i]
                open_price = open_prices.iloc[i] if hasattr(open_prices, 'iloc') else open_prices[i]
                
                # 只有收盘价严格小于开盘价才算阴线（排除平盘）
                if close_price < open_price:  # 阴线：收盘价 < 开盘价
                    consecutive_bearish += 1
                else:
                    break  # 遇到非阴线（包括平盘）就停止
            
            # 如果连续阴线数量达到要求，且不在连续序列中
            if consecutive_bearish >= self.consecutive_count and not self._in_consecutive_sequence:
                # 检查KDJ的D值趋势和5分钟RSI趋势条件
                trend_lookback = self.config.get('trend_lookback_minutes', 15)
                if kdj_d_values is not None and index >= trend_lookback:  # 确保有足够的历史数据
                    # 获取当前和N分钟前的KDJ D值
                    kdj_d_value = kdj_d_values.iloc[index] if hasattr(kdj_d_values, 'iloc') else kdj_d_values[index]
                    kdj_d_value_ago = kdj_d_values.iloc[index - trend_lookback] if hasattr(kdj_d_values, 'iloc') else kdj_d_values[index - trend_lookback]
                    
                    # 检查D值趋势：N分钟前的D值 > 当前D值
                    if kdj_d_value_ago <= kdj_d_value:
                        print(f"[DEBUG] 连跌信号KDJ D值趋势不满足条件: 索引={index}, 当前D值={kdj_d_value:.2f}, {trend_lookback}分钟前D值={kdj_d_value_ago:.2f} <= 当前D值")
                        return False
                    
                    # 检查D值绝对数值：当前D值 < 配置的最大值
                    kdj_d_max = self.config.get('kdj_d_max_value', 65)
                    if kdj_d_value >= kdj_d_max:
                        print(f"[DEBUG] 连跌信号KDJ D值不满足条件: 索引={index}, 当前D值={kdj_d_value:.2f} >= {kdj_d_max}")
                        return False
                    
                    # 检查5分钟RSI趋势条件
                    rsi_df = data.get('rsi_df')
                    if rsi_df is not None and 'RSI6_5min' in rsi_df.columns and index < len(rsi_df):
                        current_rsi = rsi_df['RSI6_5min'].iloc[index] if hasattr(rsi_df['RSI6_5min'], 'iloc') else rsi_df['RSI6_5min'][index]
                        rsi_ago = rsi_df['RSI6_5min'].iloc[index - trend_lookback] if hasattr(rsi_df['RSI6_5min'], 'iloc') else rsi_df['RSI6_5min'][index - trend_lookback]
                        
                        # 检查RSI趋势：N分钟前的5分钟RSI > 当前5分钟RSI
                        if rsi_ago <= current_rsi:
                            print(f"[DEBUG] 连跌信号5分钟RSI趋势不满足条件: 索引={index}, 当前RSI={current_rsi:.2f}, {trend_lookback}分钟前RSI={rsi_ago:.2f} <= 当前RSI")
                            return False
                        
                        print(f"[DEBUG] 连跌信号KDJ D值和5分钟RSI趋势满足条件: 索引={index}, 当前D值={kdj_d_value:.2f} < {trend_lookback}分钟前D值={kdj_d_value_ago:.2f}, 当前RSI={current_rsi:.2f} < {trend_lookback}分钟前RSI={rsi_ago:.2f}")
                    else:
                        print(f"[DEBUG] 连跌信号5分钟RSI数据不足: 索引={index}, RSI数据长度={len(rsi_df) if rsi_df is not None else 0}")
                        return False
                elif kdj_d_values is not None:
                    print(f"[DEBUG] 连跌信号KDJ D值数据不足{trend_lookback}分钟: 索引={index}, KDJ数据长度={len(kdj_d_values)}")
                    return False
                
                # 检查是否已经显示过连跌信号且没有出现买入信号
                if self._has_displayed_signal and not self._buy_signal_appeared:
                    print(f"[DEBUG] 连跌信号已显示过且未出现买入信号，跳过显示: 索引={index}")
                    return False
                
                # 如果买入信号已出现，重置显示状态
                if self._buy_signal_appeared:
                    self._has_displayed_signal = False
                    print(f"[DEBUG] 买入信号已出现，重置连跌信号显示状态")
                
                self._in_consecutive_sequence = True
                self._last_signal_index = index
                self._has_displayed_signal = True
                print(f"[DEBUG] 连跌信号触发: 索引={index}, 连续阴线数={consecutive_bearish}, 已显示={self._has_displayed_signal}, 买入信号出现={self._buy_signal_appeared}")
                return True
            
            return False
            
        except Exception as e:
            print(f"[ERROR] 连续连跌信号检查失败: {e}")
            return False
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建连跌信号数据
        
        :param data: 包含价格数据的字典
        :param index: 当前数据索引
        :return: 信号数据字典
        """
        try:
            # 获取基础信号数据
            base_signal = super().create_signal_data(data, index)
            
            # 获取当前价格
            close_prices = data.get('close_prices')
            if close_prices is None:
                current_price = 0.0
            else:
                current_price = close_prices.iloc[index] if hasattr(close_prices, 'iloc') else close_prices[index]
            
            # 计算涨跌幅
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            # 添加连续连跌特有的数据
            base_signal.update({
                'consecutive_count': self.consecutive_count,
                'signal_type': f'连跌{self.consecutive_count}',
                'price': current_price,  # 确保价格字段正确
                'net_gain': net_gain,    # 添加net_gain字段，用于信号绘制
                'is_fake': False,        # 连续连跌信号不是假信号
                'wait_validate': False   # 无延迟，不需要等待验证
            })
            
            return base_signal
            
        except Exception as e:
            print(f"[ERROR] 连续连跌信号：创建信号数据失败: {str(e)}")
            return {}
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证信号有效性（连跌信号无需额外验证）
        
        :param data: 包含价格数据的字典
        :param signal_index: 信号触发时的索引
        :param current_index: 当前数据索引
        :return: 信号是否有效
        """
        # 连跌信号无需额外验证，直接返回True
        return True
