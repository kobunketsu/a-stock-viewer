from enum import Enum
from typing import Dict, Optional, Tuple

import matplotlib

matplotlib.use('Agg')  # 设置后端为Agg，防止生成额外窗口

import akshare as ak
import pandas as pd
from trading_utils import get_symbol_info


class SignalLevel(Enum):
    """信号等级枚举类"""
    BUY = "买入"
    BULLISH = "看涨"
    SELL = "卖出"
    BEARISH = "看跌"
    NEUTRAL = "中性"


class StockType(Enum):
    """股票类型枚举类"""
    GROWTH_BOARD = "创业板"  # 创业板
    ST = "ST股"            # ST股票
    NORMAL = "普通股"      # 普通股票
    
    @property
    def limit_threshold(self) -> float:
        """获取涨停阈值"""
        thresholds = {
            StockType.GROWTH_BOARD: 19.0,  # 创业板涨停阈值
            StockType.ST: 4.5,             # ST股涨停阈值
            StockType.NORMAL: 9.5          # 普通股涨停阈值
        }
        return thresholds[self]
    
    @classmethod
    def get_type(cls, code: str, name: str) -> 'StockType':
        """
        根据股票代码和名称判断股票类型
        :param code: 股票代码
        :param name: 股票名称
        :return: 股票类型
        """
        if code.startswith('300'):
            return cls.GROWTH_BOARD
        elif 'ST' in name and not code.startswith('300'):
            return cls.ST
        return cls.NORMAL


class SignalMark(Enum):
    """信号标记枚举类"""
    RED_DOT = "ro"      # 红色圆点
    MAGENTA_DOT = "mo"  # 品红色圆点
    GREEN_DOT = "go"    # 绿色圆点
    YELLOW_DOT = "yo"   # 黄色圆点
    BLUE_DOT = "bo"     # 蓝色圆点
    ORANGE_DOT = "o"    # 橙色圆点 (使用特殊标识，颜色在绘制时指定)
    NONE = ""           # 无标记
    
    @property
    def priority(self) -> int:
        """获取标记的优先级，数字越大优先级越高"""
        priorities = {
            'ro': 100,  # 红色点最高优先级
            'go': 90,   # 绿色点次高优先级
            'mo': 80,   # 品红点
            'yo': 70,   # 黄色点
            'bo': 60,   # 蓝色点
            '': 0       # 无标记最低优先级
        }
        return priorities.get(self.value, 0)
    
    def __gt__(self, other):
        """重载大于运算符，用于比较优先级"""
        if not isinstance(other, SignalMark):
            return NotImplemented
        return self.priority > other.priority
        
    def __lt__(self, other):
        """重载小于运算符，用于比较优先级"""
        if not isinstance(other, SignalMark):
            return NotImplemented
        return self.priority < other.priority


class Signal:
    """信号类，用于统一Condition返回类型"""
    
    def __init__(
        self, 
        id: str = 'default',
        triggered: bool = False, 
        level: SignalLevel = SignalLevel.NEUTRAL,
        mark: SignalMark = SignalMark.NONE,
        description: str = "",
        score: float = 0.0,
        change: float = 0.0
    ):
        """
        初始化信号对象
        
        Args:
            triggered: 是否触发信号
            level: 信号等级(买入，看涨，卖出，看跌)
            mark: 标记样式
            description: 描述信息
            score: 信号强度分数(0-1)
            change: 涨跌幅(正值前加+)
        """
        self.id = id
        self.triggered = triggered
        self.level = level
        self.mark = mark
        self.description = description
        self.score = score
        self.change = f"+{change}" if change >= 10.0 else f"+ {change}"
    def __bool__(self) -> bool:
        """使Signal对象可以直接用于布尔判断"""
        return self.triggered
    
    def to_tuple(self) -> tuple[bool, str, str]:
        """转换为旧格式的元组，用于兼容现有代码"""
        return (self.triggered, self.description, self.mark.value)
    
    @classmethod
    def from_tuple(cls, data: tuple[bool, str, str]) -> 'Signal':
        """从旧格式元组创建Signal对象"""
        triggered, description, mark_str = data
        
        # 根据mark_str确定SignalMark
        mark = SignalMark.NONE
        for m in SignalMark:
            if m.value == mark_str:
                mark = m
                break
        
        # 根据描述和标记推断信号等级
        level = SignalLevel.NEUTRAL
        if triggered:
            if "拉升" in description or "建仓" in description:
                level = SignalLevel.BUY if "ro" in mark_str else SignalLevel.BULLISH
            elif "出货" in description or "派发" in description or "割肉" in description:
                level = SignalLevel.SELL if "go" in mark_str else SignalLevel.BEARISH
        
        return cls('default', triggered, level, mark, description)


class ConditionBase:
    """条件判断基类（接口锁定）"""
    priority = 0  # 默认优先级
    description = ""  # 新增描述字段
    
    def check(self, data_sequence) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :return: Signal 返回信号对象
        """
        raise NotImplementedError("子类必须实现check方法")


class KdjCrossCondition(ConditionBase):
    """KDJ死叉条件（含N日内涨幅阈值）"""
    priority = 100
    description = "KDJ死叉\n近期大涨"
    
    def check(self, data_sequence, n_days=3) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :param n_days: 检查的交易日数量
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < n_days + 1:
            return Signal()
            
        # 检查N日内是否有任意一天涨幅超过20%
        has_big_rise = False
        for i in range(n_days):
            if i >= len(data_sequence)-1:  # 确保有前一天数据
                continue
                
            curr_day = data_sequence[i]
            prev_day = data_sequence[i+1]
            daily_change = (curr_day['收盘'] - prev_day['收盘'])/prev_day['收盘']*100
            if daily_change > 20:
                has_big_rise = True
                break
        
        if not has_big_rise:
            return Signal()
            
        # 维持原有KDJ死叉判断（仅对比前一个交易日）
        curr_data = data_sequence[0]
        prev_data = data_sequence[1]
        j_k_diff = abs(curr_data['J'] - curr_data['K'])
        
        is_triggered = (prev_data['J'] > prev_data['K'] and curr_data['J'] <= curr_data['K']) or j_k_diff < 10
        
        if not is_triggered:
            return Signal()
            
        return Signal(
            id='kdj_dead_cross_over_20_percent',
            triggered=True,
            level=SignalLevel.BEARISH,
            mark=SignalMark.GREEN_DOT,
            description="KDJ死叉\n近期大涨",
            change=curr_day['涨跌幅'],
            score=0.8,
            
        )


class CostAndConcentrationCondition(ConditionBase):
    """平均成本和筹码集中度警示条件"""
    priority = 90  # 优先级略低于KDJ死叉条件
    description = "筹码分散\n成本激增"  # 新增描述（添加换行符）
    
    def check(self, data_sequence, threshold_cost=10, threshold_concentration=0.2) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :param threshold_cost: 平均成本增幅阈值，默认10%
        :param threshold_concentration: 90集中度阈值，默认0.2
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < 2:
            return Signal()
            
        curr_data = data_sequence[0]
        prev_data = data_sequence[1]
        
        # 检查是否有必要的字段
        required_fields = ['平均成本', '90集中度']
        if not all(field in curr_data for field in required_fields):
            return Signal()
            
        # 计算平均成本日涨幅
        if prev_data['平均成本'] == 0:
            return Signal()
            
        cost_change = ((curr_data['平均成本'] - prev_data['平均成本']) 
                      / prev_data['平均成本'] * 100)
                      
        is_triggered = (cost_change > threshold_cost and 
                       curr_data['90集中度'] > threshold_concentration)
        
        if not is_triggered:
            return Signal()
            
        return Signal(
            id='cost_up_10_and_90c_over_0.2',
            triggered=True,
            level=SignalLevel.BEARISH,
            mark=SignalMark.YELLOW_DOT,
            description="筹码分散\n成本激增",
            change=curr_data['涨跌幅'],
            score=0.7,
            
        )


class CostCrossMaCondition(ConditionBase):
    """平均成本线穿过均线条件"""
    priority = 80  # 优先级低于KDJ和筹码集中度条件
    description = "成本穿均线"  # 新增描述
    
    def check(self, data_sequence, ma_periods=[5, 10, 20]) -> Signal:
        """
        检查平均成本线是否穿过均线
        四种情况:
        1. 成本线坡度大于均线坡度，成本线从上往下穿均线 - 户割肉
        2. 成本线坡度小于均线坡度，均线从下往上穿成本线 - 主力拉升
        3. 成本线坡度小于均线坡度，均线从上往下穿成本线 - 散户套牢
        4. 成本线坡度大于均线坡度，成本线从下往上穿均线 - 主力套牢
        """
        if len(data_sequence) < 2:
            return Signal()
            
        # 获取当前和前一日的数据
        curr_data = data_sequence[0]  # 最新数据
        prev_data = data_sequence[1]  # 前一日数据
        
        # 检查是否有平均成本数据
        if '平均成本' not in curr_data or pd.isna(curr_data['平均成本']):
            return Signal()
            
        # 获取当前和前一日的平均成本
        curr_cost = curr_data['平均成本']
        prev_cost = prev_data['平均成本']
        
        # 计算成本线斜率
        cost_slope = curr_cost - prev_cost
        
        # 检查是否穿过任何一条均线
        for period in ma_periods:
            ma_key = f'MA{period}'
            if ma_key not in curr_data:
                continue
                
            curr_ma = curr_data[ma_key]
            prev_ma = prev_data[ma_key]
            
            # 计算均线斜率
            ma_slope = curr_ma - prev_ma            
            # 将period格式化为两位数字
            period_str = f"{period:02d}"
            # 情况1: 成本线坡度大于均线坡度，成本线从上往下穿均线 - 户割肉
            if cost_slope > ma_slope and prev_cost > prev_ma and curr_cost <= curr_ma:
                return Signal(
                    id=f'cost_cross_down_ma{period_str}',
                    triggered=True,
                    level=SignalLevel.BUY,
                    mark=SignalMark.RED_DOT,
                    description=f"📈成本下穿{period_str}日线\n散户割肉",
                    change=curr_data['涨跌幅'],
                    score=0.7
                )
                
            # 情况2: 成本线坡度小于均线坡度，均线从下往上穿成本线 - 主力拉升
            if cost_slope < ma_slope and prev_ma < prev_cost and curr_ma >= curr_cost:
                return Signal(
                    id=f'ma{period_str}_cross_up_cost',
                    triggered=True,
                    level=SignalLevel.BUY,
                    mark=SignalMark.RED_DOT,
                    description=f"📈{period_str}日线上穿成本\n主力拉升",
                    change=curr_data['涨跌幅'],
                    score=0.8
                )
                
            # 情况3: 成本线坡度小于均线坡度，均线从上往下穿成本线 - 散户套牢
            if cost_slope < ma_slope and prev_ma > prev_cost and curr_ma <= curr_cost:
                return Signal(
                    id=f'ma{period_str}_cross_down_cost',
                    triggered=True,
                    level=SignalLevel.SELL,
                    mark=SignalMark.GREEN_DOT,
                    description=f"📉{period_str}日线下穿成本\n散户套牢",
                    change=curr_data['涨跌幅'],
                    score=0.6
                )
                
            # 情况4: 成本线坡度大于均线坡度，成本线从下往上穿均线 - 主力套牢
            if cost_slope > ma_slope and prev_cost < prev_ma and curr_cost >= curr_ma:
                return Signal(
                    id=f'cost_cross_up_ma{period_str}',
                    triggered=True,
                    level=SignalLevel.SELL,
                    mark=SignalMark.GREEN_DOT,
                    description=f"📉成本上穿{period_str}日线\n主力派发",
                    change=curr_data['涨跌幅'],
                    score=0.7
                )
                
        return Signal()


class CostPriceCompareCondition(ConditionBase):
    """平均成本价与股价变化速度比较条件"""
    priority = 85  # 优先级在成本穿均线和筹码集中度之间
    description = "成本价变化\n超过股价"
    
    def check(self, data_sequence) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < 2:
            return Signal()
            
        curr_data = data_sequence[0]  # 最新数据
        prev_data = data_sequence[1]  # 前一日数据

        # 检查必要字段
        required_fields = ['平均成本', '收盘']
        if not all(field in curr_data and field in prev_data for field in required_fields):
            return Signal()
            
        # 防止除零错误
        if prev_data['平均成本'] == 0 or prev_data['收盘'] == 0:
            return Signal()
            
        # 计算平均成本和股价的变化率
        cost_change_rate = ((curr_data['平均成本'] - prev_data['平均成本']) 
                           / prev_data['平均成本'] * 100)
        price_change_rate = ((curr_data['收盘'] - prev_data['收盘']) 
                            / prev_data['收盘'] * 100)
           
        # 成本涨幅超过20%，发出卖出信号
        if cost_change_rate > 20:
            return Signal(
                id='cost_up_20_per',
                triggered=True,
                level=SignalLevel.SELL,  # 卖出信号
                mark=SignalMark.GREEN_DOT,
                description="成本暴涨超20%\n主力大幅抛售",
                change=curr_data['涨跌幅'],
                score=0.85  # 更高的信号强度
            )
        
        # 计算成本/价格比值的变化率
        curr_cost_price_ratio = curr_data['平均成本'] / curr_data['收盘']
        prev_cost_price_ratio = prev_data['平均成本'] / prev_data['收盘']
        cost_price_ratio_change = ((curr_cost_price_ratio - prev_cost_price_ratio) 
                                  / prev_cost_price_ratio * 100)     
                
        # 成本股价比涨幅超过5%，发出卖出信号
        if curr_cost_price_ratio > 1 and cost_price_ratio_change > 5:
            return Signal(
                id='cost_price_ratio_up_5_per',
                triggered=True,
                level=SignalLevel.SELL,  # 卖出信号
                mark=SignalMark.GREEN_DOT,
                description=f"成本比现价{cost_price_ratio_change:.2f}%\n主力大幅抛售",
                change=curr_data['涨跌幅'],
                score=0.8  # 更高的信号强度
            )
        
        # 成本股价比跌幅超过5%，发出买入信号
        if curr_cost_price_ratio < 1 and cost_price_ratio_change < -5:
            return Signal(
                id='cost_price_ratio_down_5_per',
                triggered=True,
                level=SignalLevel.BUY,  # 卖出信号
                mark=SignalMark.RED_DOT,
                description=f"成本比现价{cost_price_ratio_change:.2f}%\n主力大幅买入",
                change=curr_data['涨跌幅'],
                score=0.8  # 更高的信号强度
            )        
                        
        # 成本上涨速度大于股价
        if cost_change_rate > price_change_rate and cost_change_rate > 0:
            return Signal(
                id='cost_up_speed_over_price',
                triggered=True,
                level=SignalLevel.BEARISH,
                mark=SignalMark.YELLOW_DOT,
                description="成本增速超均价\n主力派发",
                change=curr_data['涨跌幅'],
                score=0.65
            )
            
        # 成本下跌速度大于股价    
        if cost_change_rate < price_change_rate and cost_change_rate < 0:
            return Signal(
                id='cost_down_speed_over_price',
                triggered=True,
                level=SignalLevel.BEARISH,
                mark=SignalMark.ORANGE_DOT,
                description="成本降速超均价\n散户割肉",
                change=curr_data['涨跌幅'],
                score=0.6
            )
            
        return Signal()


class CostCrossPriceBodyCondition(ConditionBase):
    """成本线穿透价格实体条件"""
    priority = 82  # 优先级在均线穿透和变化速度之间
    description = "成本穿现价"  # 基础描述
    
    def check(self, data_sequence) -> Signal:
        """
        检查成本线是否穿透当日价格实体
        1. 成本线在实体下半部 -> 底部穿透
        2. 成本线在实体上半部 -> 顶部穿透
        """
        if len(data_sequence) < 2:  # 需要当日和前一日数据来计算涨幅
            return Signal()
            
        curr_data = data_sequence[0]
        prev_data = data_sequence[1]
        
        # 检查必要字段
        required_fields = ['平均成本', '开盘', '收盘']
        if not all(field in curr_data for field in required_fields):
            return Signal()
            
        curr_cost = curr_data['平均成本']
        open_price = curr_data['开盘']
        close_price = curr_data['收盘']
        
        # 计算涨幅
        if prev_data['收盘'] == 0:
            return Signal()
        price_change = (close_price - prev_data['收盘']) / prev_data['收盘']
                
        # 计算实体范围
        body_low = min(open_price, close_price)
        body_high = max(open_price, close_price)
        mid_point = (body_low + body_high) / 2
        
        # 穿透底部条件
        if body_low <= curr_cost <= mid_point:
            return Signal(
                id='cost_cross_down_price_body',
                triggered=True,
                level=SignalLevel.BULLISH,
                mark=SignalMark.ORANGE_DOT,
                description="成本穿现价底部\n黄金穿透",
                change=curr_data['涨跌幅'],
                score=0.75
            )
            
        # 穿透顶部条件
        if mid_point < curr_cost <= body_high:
            return Signal(
                id='cost_cross_up_price_body',
                triggered=True,
                level=SignalLevel.BEARISH,
                mark=SignalMark.YELLOW_DOT,
                description="成本缩量穿现价顶部\n死亡穿透",
                change=curr_data['涨跌幅'],
                score=0.7
            )
            
        return Signal()


class BBWChangeCondition(ConditionBase):
    """布林带宽度变化条件"""
    priority = 95
    description = "布林带宽变化"
    
    # 修改类变量为字典存储时间信息
    _last_signals: dict[str, dict[str, Optional[pd.Timestamp]]] = {
        'drop': {'time': None, 'peak_time': None},
        'rise': {'time': None, 'valley_time': None}
    }
    
    def check(self, data_sequence) -> Signal:
        """条件检查接口"""
        if len(data_sequence) < 2:
            return Signal()
            
        try:
            curr_data = data_sequence[0]
            
            # 检查必要字段
            required_fields = ['BBW', 'BBW_DROP', 'BBW_RISE', 'BBW_PEAK_DATE', 'BBW_VALLEY_DATE']
            if not all(field in curr_data.index for field in required_fields):
                return Signal()
            
            # 获取当前时间信息
            current_time = curr_data.name if isinstance(curr_data.name, pd.Timestamp) else pd.NaT
            bbw_peak_time = pd.to_datetime(curr_data['BBW_PEAK_DATE']) if pd.notna(curr_data['BBW_PEAK_DATE']) else pd.NaT
            bbw_valley_time = pd.to_datetime(curr_data['BBW_VALLEY_DATE']) if pd.notna(curr_data['BBW_VALLEY_DATE']) else pd.NaT

            # BBW_DROP信号检查
            if curr_data['BBW_DROP'] >= 15:
                # 检查前一个rise信号时间是否晚于当前peak时间
                last_rise_time = self._last_signals['rise']['time']
                if pd.isna(bbw_peak_time) or (pd.notna(last_rise_time) and last_rise_time > bbw_peak_time):
                    return Signal()
                
                # 更新信号记录
                # 存储为Timestamp，保持类型一致
                self._last_signals['drop'] = {
                    'time': current_time if isinstance(current_time, pd.Timestamp) else None,
                    'peak_time': bbw_peak_time if isinstance(bbw_peak_time, pd.Timestamp) else None
                }
                return Signal(
                    id='bbw_drop_over_15',
                    triggered=True,
                    level=SignalLevel.SELL,
                    mark=SignalMark.GREEN_DOT,
                    description=f"布林顶向下{curr_data['BBW_DROP']:.1f}%\n波动率收缩",
                    change=curr_data['涨跌幅'],
                    score=0.8
                )

            # BBW_RISE信号检查
            if curr_data['BBW_RISE'] >= 15 and curr_data['BBW'] < 0.2:
                # 检查前一个drop信号时间是否晚于当前valley时间
                last_drop_time = self._last_signals['drop']['time']
                if pd.isna(bbw_valley_time) or (pd.notna(last_drop_time) and last_drop_time > bbw_valley_time):
                    return Signal()
                
                # 更新信号记录
                self._last_signals['rise'] = {
                    'time': current_time if isinstance(current_time, pd.Timestamp) else None,
                    'valley_time': bbw_valley_time if isinstance(bbw_valley_time, pd.Timestamp) else None
                }
                return Signal(
                    id='bbw_rise_over_15',
                    triggered=True,
                    level=SignalLevel.BUY,
                    mark=SignalMark.RED_DOT,
                    description=f"布林底向上{curr_data['BBW_RISE']:.1f}%\n波动率扩张",
                    change=curr_data['涨跌幅'],
                    score=0.7
                )
                
            return Signal()
            
        except Exception as e:
            print(f"BBW条件检查出错: {str(e)}")
            return Signal()


class OversoldCondition(ConditionBase):
    """超跌股票判断条件"""
    priority = 95  # 设置较高优先级
    description = "超跌"

    def check(self, data_sequence) -> Signal:
        """
        检查是否为超跌股票
        @param data_sequence: 包含股票数据的序列
        @return: 信号对象
        """
        try:
            # 获取K线数据
            df = data_sequence.get('kline_data', None)
            if df is None or df.empty:
                return Signal(id='oversold', triggered=False)
                
            # 计算MA250
            df['MA250'] = df['收盘'].rolling(window=250).mean()
            current_ma250 = df['MA250'].iloc[-1]
            
            # 获取当日90%筹码集中度
            current_concentration_90 = df['90成本-高'].iloc[-1]
            
            # 判断是否超跌：当日90%筹码集中度小于当前的MA250年线价格
            is_oversold = current_concentration_90 < current_ma250
            
            if is_oversold:
                return Signal(
                    id='oversold',
                    triggered=True,
                    level=SignalLevel.BUY,  # 超跌信号作为买入信号
                    mark=SignalMark.RED_DOT,
                    description=f"超跌: 90%筹码{current_concentration_90:.2f} < MA250({current_ma250:.2f})",
                    score=0.8  # 较高的信号分数
                )
            
            return Signal(id='oversold', triggered=False)
            
        except Exception as e:
            print(f"超跌判断出错: {str(e)}")
            return Signal(id='oversold', triggered=False)


class PriceBelowMA5Condition(ConditionBase):
    """股价连续低于5日线条件"""
    priority = 88  # 设置优先级
    description = "股价低于5日线"
    
    def check(self, data_sequence) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < 5:  # 需要至少7天数据来计算MA5
            return Signal()
            
        # 获取最近三天的数据
        curr_data = data_sequence[0]    # 今天
        prev_data = data_sequence[1]    # 昨天
        prev2_data = data_sequence[2]   # 前天
        
        # 检查必要字段
        required_fields = ['收盘', '涨跌幅', '股票代码', '90成本-低']
        if not all(field in curr_data and field in prev_data and field in prev2_data for field in required_fields):
            return Signal()
            
        # 如果没有MA5，计算MA5
        if 'MA5' not in curr_data:
            # 创建一个临时的DataFrame来计算MA5
            df = pd.DataFrame([d['收盘'] for d in data_sequence], columns=['收盘'])
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
            
            # 为三天数据添加MA5
            curr_data['MA5'] = df['MA5'].iloc[0]
            prev_data['MA5'] = df['MA5'].iloc[1]
            prev2_data['MA5'] = df['MA5'].iloc[2]
        
        # 获取股票名称和类型
        name, _ = get_symbol_info(str(curr_data['股票代码']))
        if not name:
            return Signal()
            
        # 获取股票类型和涨停阈值
        stock_type = StockType.get_type(str(curr_data['股票代码']), name)
        limit_threshold = stock_type.limit_threshold
            
        # 检查是否涨停
        if curr_data['涨跌幅'] >= limit_threshold:
            return Signal()
            
        # 检查前天是否大于等于5日线，昨天和今天是否都低于5日线
        prev2_above_ma5 = prev2_data['收盘'] >= prev2_data['MA5']  # 前天大于等于5日线
        prev_below_ma5 = prev_data['收盘'] < prev_data['MA5']      # 昨天低于5日线
        curr_below_ma5 = curr_data['收盘'] < curr_data['MA5']      # 今天低于5日线
        
        # 检查当前价格是否在90成本-低下方
        price_below_cost90_low = curr_data['收盘'] < curr_data['90成本-低']
        
        if prev2_above_ma5 and prev_below_ma5 and curr_below_ma5:
            # 如果价格在90成本-低下方，不发出卖出信号
            if price_below_cost90_low:
                return Signal()
                
            # 计算当前价格与5日线的偏离度
            deviation = (curr_data['MA5'] - curr_data['收盘']) / curr_data['MA5'] * 100
            
            return Signal(
                id='price_below_ma5_2days',
                triggered=True,
                level=SignalLevel.SELL,  # 明确设置为卖出信号
                mark=SignalMark.GREEN_DOT,  # 使用绿色点标记
                description=f"站不稳5日线\n偏离{deviation:.1f}%",
                change=curr_data['涨跌幅'],
                score=0.85  # 提高信号强度，因为这是明确的卖出信号
            )
            
        return Signal()


class PriceAboveMA5Condition(ConditionBase):
    """股价连续高于5日线条件"""
    priority = 88  # 设置优先级与PriceBelowMA5Condition相同
    description = "股价高于5日线"
    
    def check(self, data_sequence) -> Signal:
        """
        //! 条件检查接口
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < 5:  # 需要至少7天数据来计算MA5
            return Signal()
            
        # 获取最近三天的数据
        curr_data = data_sequence[0]    # 今天
        prev_data = data_sequence[1]    # 昨天
        prev2_data = data_sequence[2]   # 前天
        
        # 检查必要字段
        required_fields = ['收盘', '涨跌幅', '股票代码', '90成本-高']
        if not all(field in curr_data and field in prev_data and field in prev2_data for field in required_fields):
            return Signal()
            
        # 如果没有MA5，计算MA5
        if 'MA5' not in curr_data:
            # 创建一个临时的DataFrame来计算MA5
            df = pd.DataFrame([d['收盘'] for d in data_sequence], columns=['收盘'])
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
            
            # 为三天数据添加MA5
            curr_data['MA5'] = df['MA5'].iloc[0]
            prev_data['MA5'] = df['MA5'].iloc[1]
            prev2_data['MA5'] = df['MA5'].iloc[2]
        
        # 获取股票名称和类型
        name, _ = get_symbol_info(str(curr_data['股票代码']))
        if not name:
            return Signal()
            
        # 获取股票类型和涨停阈值
        stock_type = StockType.get_type(str(curr_data['股票代码']), name)
        limit_threshold = stock_type.limit_threshold
            
        # 检查是否涨停
        if curr_data['涨跌幅'] >= limit_threshold:
            return Signal()
            
        # 检查前天是否小于等于5日线，昨天和今天是否都高于5日线
        prev2_below_ma5 = prev2_data['收盘'] <= prev2_data['MA5']  # 前天小于等于5日线
        prev_above_ma5 = prev_data['收盘'] > prev_data['MA5']      # 昨天高于5日线
        curr_above_ma5 = curr_data['收盘'] > curr_data['MA5']      # 今天高于5日线
        
        # 检查当前价格是否在90成本-高上方
        price_above_cost90_high = curr_data['收盘'] > curr_data['90成本-高']
        
        if prev2_below_ma5 and prev_above_ma5 and curr_above_ma5:
            # 如果价格在90成本-高上方，不发出买入信号
            if price_above_cost90_high:
                return Signal()
                
            # 计算当前价格与5日线的偏离度
            deviation = (curr_data['收盘'] - curr_data['MA5']) / curr_data['MA5'] * 100
            
            return Signal(
                id='price_above_ma5_2days',
                triggered=True,
                level=SignalLevel.BUY,  # 明确设置为买入信号
                mark=SignalMark.RED_DOT,  # 使用红色点标记
                description=f"站稳5日线\n偏离{deviation:.1f}%",
                change=curr_data['涨跌幅'],
                score=0.85  # 提高信号强度，因为这是明确的买入信号
            )
            
        return Signal()


class FundSourceTradingCondition(ConditionBase):
    """资金来源交易条件"""
    priority = 110  # 设置高优先级
    description = "资金来源"
    
    # 简单缓存以减少同一code/日期的重复查询
    _cache: Dict[Tuple[str, str], Signal] = {}
    _cache_limit: int = 256

    def check(self, data_sequence) -> Signal:
        """
        检查当前股票是否有机构买卖信号
        
        Args:
            data_sequence: 数据序列，期望包含日期和股票代码信息
            
        Returns:
            Signal: 机构买卖信号
        """
        try:
            from lhb_data_processor import lhb_processor
            
            if not data_sequence:
                return Signal()

            current_data = data_sequence[0]

            # 获取股票代码
            code = str(current_data.get('股票代码', '')).zfill(6)
            if not code:
                return Signal()

            # 获取日期索引
            date_index = getattr(current_data, 'name', None)
            if date_index is None:
                date_index = getattr(current_data, 'Index', None)
            if date_index is None:
                return Signal()

            date_str = date_index.strftime('%Y%m%d') if hasattr(date_index, 'strftime') else str(date_index).replace('-', '')[:8]

            # 查询缓存
            cache_key = (code, date_str)
            if cache_key in self._cache:
                return self._cache[cache_key]

            # 查询龙虎榜（加速策略：仅对最近一段时间或首次调用时查询）
            lhb_record = lhb_processor.get_institution_signal(code, date_str)
            if not lhb_record:
                # 负缓存避免重复查询
                self._cache[cache_key] = Signal()
                # 控制缓存大小
                if len(self._cache) > self._cache_limit:
                    self._cache.pop(next(iter(self._cache)))
                return self._cache[cache_key]

            # 计算三股势力的净买入占比
            institution_ratio = lhb_record.institution_net_ratio
            hot_ratio = lhb_record.hot_net_ratio
            retail_ratio = lhb_record.retail_net_ratio
            
            # 判断势力存在情况
            has_institution = abs(institution_ratio) > 0.01  # 机构势力存在
            has_retail = abs(retail_ratio) > 0.01  # 散户势力存在
            
            # 动态调整游资角色
            if has_institution and has_retail and abs(hot_ratio) <= 0.01:
                # 只有机构和散户：机构 vs 散户
                total_positive_ratio = institution_ratio
                total_negative_ratio = retail_ratio
                net_signal_ratio = total_positive_ratio - total_negative_ratio
                signal_logic = "机构vs散户"
            elif has_institution and has_retail:
                # 三股势力都存在：机构 vs 散户（游资作为中立观察）
                total_positive_ratio = institution_ratio
                total_negative_ratio = retail_ratio
                net_signal_ratio = total_positive_ratio - total_negative_ratio
                signal_logic = "三股势力"
            elif has_institution and not has_retail:
                # 只有机构和游资：游资作为机构对手盘
                total_positive_ratio = institution_ratio
                total_negative_ratio = hot_ratio
                net_signal_ratio = total_positive_ratio - total_negative_ratio
                signal_logic = "机构vs游资"
            elif not has_institution and has_retail:
                # 只有游资和散户：游资作为散户对手盘
                total_positive_ratio = hot_ratio
                total_negative_ratio = retail_ratio
                net_signal_ratio = total_positive_ratio - total_negative_ratio
                signal_logic = "游资vs散户"
            else:
                # 只有游资势力
                net_signal_ratio = hot_ratio
                signal_logic = "仅游资"
            
            score = min(1.0, abs(net_signal_ratio) / 10.0)
            
            # 选择颜色: 取绝对占比最大的势力对应颜色
            def _select_mark():
                candidates: list[tuple[str, float]] = []
                if abs(institution_ratio) > 0.01:
                    candidates.append(('机构', institution_ratio))
                if abs(hot_ratio) > 0.01:
                    candidates.append(('游资', hot_ratio))
                if abs(retail_ratio) > 0.01:
                    candidates.append(('散户', retail_ratio))
                if not candidates:
                    return SignalMark.NONE
                force, ratio = max(candidates, key=lambda x: abs(x[1]))
                if force == '机构':
                    return SignalMark.RED_DOT if ratio > 0 else SignalMark.GREEN_DOT
                if force == '游资':
                    return SignalMark.ORANGE_DOT if ratio > 0 else SignalMark.YELLOW_DOT
                # 散户
                return SignalMark.GREEN_DOT if ratio > 0 else SignalMark.RED_DOT

            selected_mark = _select_mark()
            
            # 根据综合净买入占比判断信号
            if net_signal_ratio > 0:
                # 正面信号
                signal_level = SignalLevel.BUY
                signal_mark = selected_mark
                signal_id = 'fund_source_buy'
                
                # 构建描述信息
                description_parts = []
                
                # 根据势力情况显示信息
                if has_institution and has_retail and abs(hot_ratio) <= 0.01:
                    # 机构vs散户
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                    
                    # 添加负面信息
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                        
                elif has_institution and has_retail:
                    # 三股势力都存在：机构 vs 散户（游资作为中立观察）
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    elif hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    
                    # 添加负面信息
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                        
                elif has_institution and not has_retail:
                    # 机构vs游资
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    
                    # 添加负面信息
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                        
                elif not has_institution and has_retail:
                    # 游资vs散户
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                    
                    # 添加负面信息
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                        
                else:
                    # 仅游资
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    else:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                
            else:
                # 负面信号
                signal_level = SignalLevel.SELL
                signal_mark = selected_mark
                signal_id = 'fund_source_sell'
                
                # 构建描述信息
                description_parts = []
                
                # 根据势力情况显示信息
                if has_institution and has_retail and abs(hot_ratio) <= 0.01:
                    # 机构vs散户
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                    
                    # 添加正面信息
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                        
                elif has_institution and has_retail:
                    # 三股势力都存在：机构 vs 散户（游资作为中立观察）
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    elif hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    
                    # 添加正面信息
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                        
                elif has_institution and not has_retail:
                    # 机构vs游资
                    if institution_ratio < 0:
                        description_parts.append(f"机构净卖: {abs(institution_ratio):.2f}%")
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    
                    # 添加正面信息
                    if institution_ratio > 0:
                        description_parts.append(f"机构净买: {institution_ratio:.2f}%")
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                        
                elif not has_institution and has_retail:
                    # 游资vs散户
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    if retail_ratio > 0:
                        description_parts.append(f"散户净买: {retail_ratio:.2f}%")
                    
                    # 添加正面信息
                    if hot_ratio > 0:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
                    if retail_ratio < 0:
                        description_parts.append(f"散户净卖: {abs(retail_ratio):.2f}%")
                        
                else:
                    # 仅游资
                    if hot_ratio < 0:
                        description_parts.append(f"游资净卖: {abs(hot_ratio):.2f}%")
                    else:
                        description_parts.append(f"游资净买: {hot_ratio:.2f}%")
            
            description = "\n".join(description_parts)

            signal = Signal(
                id=signal_id,
                triggered=True,
                level=signal_level,
                mark=signal_mark,
                description=description,
                score=score,
                change=lhb_record.change_pct
            )
            # 写入缓存
            self._cache[cache_key] = signal
            if len(self._cache) > self._cache_limit:
                self._cache.pop(next(iter(self._cache)))
            return signal

        except ImportError:
            # akshare不可用
            return Signal()
        except Exception as e:
            import logging
            logging.error(f"资金来源交易条件检查失败: {str(e)}")
            return Signal()

# 保持向后兼容性
InstitutionTradingCondition = FundSourceTradingCondition



class PriceMA5DeviationCondition(ConditionBase):
    """计算价格相对5日线的偏离度条件"""
    priority = 75
    description = "价格偏离5日线"
    
    def check(self, data_sequence) -> Signal:
        """
        //! 条件检查接口
        计算当日最高价和最低价相对5日线的偏离度
        :param data_sequence: 数据序列（按时间倒序排列，[0]为当前数据）
        :return: Signal 返回信号对象
        """
        if len(data_sequence) < 5:  # 需要至少5天数据来计算MA5
            return Signal()
            
        curr_data = data_sequence[0]
        
        # 检查必要字段
        required_fields = ['最高', '最低', '收盘']
        if not all(field in curr_data for field in required_fields):
            return Signal()
            
        # 创建一个临时的DataFrame来计算MA5
        df = pd.DataFrame([d['收盘'] for d in data_sequence], columns=['收盘'])
        df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
        
        # 获取当日数据
        high_price = curr_data['最高']
        low_price = curr_data['最低']
        ma5 = df['MA5'].iloc[0]  # 使用计算出的MA5
        
        # 计算涨跌幅
        # 涨幅：如果最高价大于MA5，计算偏离度，否则为0
        up_deviation = ((high_price - ma5) / ma5 * 100) if high_price > ma5 else 0
        # 跌幅：如果最低价小于MA5，计算偏离度，否则为0
        down_deviation = ((low_price - ma5) / ma5 * 100) if low_price < ma5 else 0
        
        # 将计算结果添加到当日数据中
        curr_data['MA5_UP_DEV'] = up_deviation
        curr_data['MA5_DOWN_DEV'] = down_deviation
        
        return Signal()