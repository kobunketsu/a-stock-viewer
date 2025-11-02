import copy
import logging
import math
import multiprocessing
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, List, Optional, Tuple

import akshare as ak
import numpy as np
import pandas as pd
from akshare_wrapper import akshare
from conditions import (ConditionBase, CostAndConcentrationCondition,
                        CostCrossMaCondition, Signal)
from dateutil.relativedelta import relativedelta

# 添加src目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from conditions import CostAndConcentrationCondition, CostCrossMaCondition
from etf_realtime_data import ETFRealtimeData


def timing_decorator(func):
    """执行时间测量装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed = (end_time - start_time) * 1000  # 转换为毫秒
        print(f"[性能] {func.__name__} 耗时: {elapsed:.2f}ms")
        return result
    return wrapper

class ETFAnalysisEngine:
    """ETF多维度分析引擎
    
    基于多个核心指标对ETF进行综合分析，生成赚钱效应判断分数。
    """
    
    def __init__(self):
        self._history_data: Dict[str, pd.DataFrame] = {}  # 存储历史数据
        self._realtime_data = ETFRealtimeData()  # 实时数据获取器
        
        # 定义相关性矩阵
        self._correlation_matrix = {
            'volume_price_correlation': {
                'volume_price_correlation': 1.00,
                'holding_stability': -0.32,
                'arbitrage_impact': 0.18,
                'volume_health': 0.45,
                'momentum_trend': 0.67,
                'volatility_quality': -0.25
            },
            'holding_stability': {
                'volume_price_correlation': -0.32,
                'holding_stability': 1.00,
                'arbitrage_impact': 0.12,
                'volume_health': -0.28,
                'momentum_trend': -0.15,
                'volatility_quality': 0.41
            },
            'arbitrage_impact': {
                'volume_price_correlation': 0.18,
                'holding_stability': 0.12,
                'arbitrage_impact': 1.00,
                'volume_health': 0.05,
                'momentum_trend': 0.22,
                'volatility_quality': -0.33
            },
            'volume_health': {
                'volume_price_correlation': 0.45,
                'holding_stability': -0.28,
                'arbitrage_impact': 0.05,
                'volume_health': 1.00,
                'momentum_trend': 0.38,
                'volatility_quality': -0.18
            },
            'momentum_trend': {
                'volume_price_correlation': 0.67,
                'holding_stability': -0.15,
                'arbitrage_impact': 0.22,
                'volume_health': 0.38,
                'momentum_trend': 1.00,
                'volatility_quality': -0.31
            },
            'volatility_quality': {
                'volume_price_correlation': -0.25,
                'holding_stability': 0.41,
                'arbitrage_impact': -0.33,
                'volume_health': -0.18,
                'momentum_trend': -0.31,
                'volatility_quality': 1.00
            }
        }
        
        # 基础权重（可以根据需要调整）
        self._weights = {
            'volume_price_correlation': 0.20,  # 量价背离指数权重
            'holding_stability': 0.20,        # 筹码稳定度权重
            'arbitrage_impact': 0.15,        # 套利影响权重
            'volume_health': 0.15,           # 量能结构健康度权重
            'momentum_trend': 0.15,          # 动量趋势权重
            'volatility_quality': 0.15       # 波动率质量权重
        }
        
        self._score_history: Dict[str, List[float]] = {}  # 历史得分缓存
        self._data_cache = {}  # 添加数据缓存
        self._cache_timeout = 300  # 缓存超时时间(秒)
        self._last_update = {}  # 记录每个ETF的最后更新时间
        self.analysis_periods = {
            'momentum': 30,  # 动量分析周期（匹配MACD短期EMA）
            'volatility': 30,  # 波动率分析周期（匹配布林带标准周期）
            'min_data_days': 60  # 最小数据要求（覆盖最长分析周期）
        }
        self._last_market_status = 'normal'  # 默认市场状态
        self._last_market_detection = datetime.min  # 最后检测时间
        self.market_status_refresh_interval = 1800  # 30分钟刷新间隔(秒)
        self._profit_score_cache = {}  # 新增缓存字典
        self._cache_days = 65  # 缓存天数
        self._indicator_cache: Dict[tuple, pd.DataFrame | pd.Series] = {}
        
        # 设置线程池大小
        self._cpu_count = multiprocessing.cpu_count()
        self._thread_workers = max(1, self._cpu_count - 1)  # 至少保留1个线程
    
    def _fetch_history_data(self, code: str, start_date: str = None, end_date: str = None, days: int = 65) -> pd.DataFrame:
        """获取历史数据(优化版) - 根据证券类型选择合适的API"""
        try:
            # 处理日期参数
            end_date = pd.to_datetime(end_date) if end_date else datetime.now()
            
            # 当start_date未指定时，使用days参数
            if not start_date:
                start_date = end_date - timedelta(days=days*2)
            else:
                start_date = pd.to_datetime(start_date)
            
            # 根据证券类型选择合适的API
            if str(code).startswith('BK'):
                # 板块数据 - 需要先获取板块名称
                try:
                    # 获取板块名称
                    board_list = ak.stock_board_concept_name_em()
                    board_info = board_list[board_list['板块代码'] == code]
                    if not board_info.empty:
                        board_name = board_info.iloc[0]['板块名称']
                        df = ak.stock_board_concept_hist_em(
                            symbol=board_name,
                            start_date=start_date.strftime("%Y%m%d"),
                            end_date=end_date.strftime("%Y%m%d")
                        )
                    else:
                        df = pd.DataFrame()
                except Exception as e:
                    print(f"获取板块信息失败 {code}: {e}")
                    df = pd.DataFrame()
            elif str(code).startswith('5') or str(code).startswith('15'):
                # ETF基金数据
                df = ak.fund_etf_hist_em(
                    symbol=code, 
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust="qfq"
                )
            elif code == "1A0001" or code == "000001":
                # 指数数据
                df = ak.index_zh_a_hist(
                    symbol="000001",  # 上证指数代码
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                )
            else:
                # 普通股票数据
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust="qfq"
                )
            
            if not df.empty:
                # 确保日期列存在
                if '日期' not in df.columns:
                    # 保存索引作为日期列
                    df['日期'] = df.index
                
                # 转换日期格式
                df['日期'] = pd.to_datetime(df['日期'])
                
                # 设置日期索引并排序
                df = df.set_index('日期').sort_index()
                
                # 将日期列添加回DataFrame
                df['日期'] = df.index
                
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"获取历史数据失败 {code}: {e}")
            return pd.DataFrame()
    
    def _calculate_volume_price_correlation(self, data: pd.DataFrame) -> float:
        """计算量价背离指数
        
        Args:
            data: 历史数据DataFrame
            
        Returns:
            float: 相关系数，范围[0, 1]
        """
        if len(data) < 2:
            return 0.5  # 数据不足返回中性值
            
        try:
            # 计算价格变动和成交量变动
            price_changes = data['收盘'].pct_change().dropna()
            volume_changes = data['成交量'].pct_change().dropna()
            
            if len(price_changes) < 2:
                return 0.5
                
            # 计算相关系数
            corr = np.corrcoef(price_changes, volume_changes)[0, 1]
            
            # 计算价格趋势
            price_trend = np.polyfit(range(len(price_changes)), price_changes, 1)[0]
            
            # 计算成交量趋势
            volume_trend = np.polyfit(range(len(volume_changes)), volume_changes, 1)[0]
            
            # 基础分数：将相关系数映射到[0.2, 0.8]区间
            base_score = 0.2 + 0.6 * (corr + 1) / 2
            
            # 趋势加权
            if price_trend > 0:
                if volume_trend > 0:
                    # 价量齐升，提高得分
                    trend_score = min(0.2, abs(price_trend) * 100) * min(0.2, abs(volume_trend) * 100)
                    base_score = min(1.0, base_score + trend_score)
                else:
                    # 价升量缩，降低得分
                    trend_score = min(0.2, abs(price_trend) * 100) * min(0.2, abs(volume_trend) * 100)
                    base_score = max(0.0, base_score - trend_score)
            else:
                if volume_trend < 0:
                    # 价量齐跌，适度提高得分（但幅度小于价量齐升）
                    trend_score = min(0.1, abs(price_trend) * 50) * min(0.1, abs(volume_trend) * 50)
                    base_score = min(1.0, base_score + trend_score)
                else:
                    # 价跌量升，显著降低得分
                    trend_score = min(0.3, abs(price_trend) * 150) * min(0.3, abs(volume_trend) * 150)
                    base_score = max(0.0, base_score - trend_score)
            
            return base_score
            
        except Exception as e:
            print(f"计算量价相关性时出错: {e}")
            return 0.5
    
    def _calculate_holding_stability(self, code: str, data: pd.DataFrame) -> float:
        """计算筹码稳定度
        
        Args:
            code: ETF代码
            data: 历史数据DataFrame
            
        Returns:
            float: 稳定度得分，范围[0, 1]
        """
        if len(data) < 2:
            return 0.5
            
        try:
            # 计算换手率变异系数
            turnover_rates = data['换手率'].astype(float)
            turnover_cv = turnover_rates.std() / turnover_rates.mean() if turnover_rates.mean() != 0 else float('inf')
            
            # 获取大单净流入数据
            current_data = self._realtime_data.get_realtime_quotes(code)
            if current_data and '大单净流入-净占比' in current_data:
                big_order_ratio = float(current_data['大单净流入-净占比'])
                big_order_stability = 1.0 - min(1.0, abs(big_order_ratio) / 50.0)  # 将大单净流入占比映射到稳定性分数
            else:
                big_order_stability = 0.5
            
            # 综合评分
            stability_score = 0.7 * (1 / (1 + turnover_cv)) + 0.3 * big_order_stability
            return min(1.0, max(0.0, stability_score))
            
        except (ValueError, TypeError, KeyError):
            return 0.5
    
    def _calculate_arbitrage_impact(self, code: str) -> float:
        """计算套利综合影响因子
        
        Returns:
            float: 套利影响得分，范围[0, 1]
            0表示最大套利压力，1表示最大套利推动力
            
        Note:
            基金折价率为正时表示折价，负时表示溢价
        """
        # 获取实时数据
        current_data = self._realtime_data.get_realtime_quotes(code)
        if not current_data:
            return 0.5
        
        try:
            discount_rate = float(current_data.get('基金折价率', 0))  # 正数表示折价，负数表示溢价
            amplitude = float(current_data.get('振幅', 0))
            
            # 基础分数从0.5开始
            score = 0.5
            
            if discount_rate > 0:  # 折价情况，提升得分
                # 折价率影响（最多提升0.4分）
                discount_impact = min(0.4, discount_rate * 0.8)  # 折价0.5%时达到最大值0.4
                # 振幅补偿（高波动降低套利可行性）
                volatility_discount = max(0.0, (amplitude - 1.0) * 0.1)
                score += discount_impact - volatility_discount
                
            elif discount_rate < 0:  # 溢价情况，降低得分
                # 溢价率影响（最多降低0.4分）
                premium_impact = min(0.4, abs(discount_rate) * 1.2)  # 溢价0.33%时达到最大值0.4
                # 振幅放大效应（高波动加剧抛压）
                volatility_amplifier = min(0.1, amplitude * 0.05)
                score -= premium_impact + volatility_amplifier
            
            return min(1.0, max(0.0, score))
            
        except (ValueError, TypeError):
            return 0.5
    
    def _calculate_volume_health(self, code: str) -> float:
        """计算量能结构健康度
        
        Args:
            code: ETF代码
            
        Returns:
            float: 健康度得分，范围[0, 1]
        """
        try:
            volume_structure = self._realtime_data.get_volume_structure(code)
            if not volume_structure:
                return 0.5
                
            out_ratio = volume_structure.get('out_ratio', 0)
            
            # 基于外盘占比判断
            if out_ratio > 0.55:
                score = 0.8
            elif out_ratio < 0.45:
                score = 0.2
            else:
                # 中性状态
                score = 0.5
                # 外盘占比影响
                score += (out_ratio - 0.5) * 0.3
                
            return min(1.0, max(0.0, score))
            
        except (ValueError, TypeError, KeyError):
            return 0.5
    
    def _calculate_momentum_trend(self, data: pd.DataFrame) -> float:
        """计算动量趋势得分
        
        Args:
            data: 历史数据DataFrame，需要至少20天数据
            
        Returns:
            float: 动量趋势得分，范围[0, 1]
        """
        if len(data) < self.analysis_periods['min_data_days']:
            print(f"警告: 数据量不足{self.analysis_periods['min_data_days']}天...")
            return 0.5
            
        try:
            # 计算EMA斜率
            close_prices = data['收盘'].values
            ema_fast = pd.Series(close_prices).ewm(span=12).mean()  # MACD短期EMA
            ema_slow = pd.Series(close_prices).ewm(span=26).mean()  # MACD长期EMA
            
            # 计算趋势方向
            trend = 1 if ema_fast.iloc[-1] > ema_slow.iloc[-1] else -1
            
            # 计算RSI
            delta = data['收盘'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # 计算动量
            momentum = data['收盘'].pct_change(5).iloc[-1]
            
            # 综合评分
            score = 0.5  # 基础分
            
            # RSI影响
            rsi_latest = rsi.iloc[-1]
            if rsi_latest > 70:
                score += 0.2
            elif rsi_latest < 30:
                score -= 0.2
                
            # 趋势影响
            score += trend * 0.15
            
            # 动量影响
            score += np.sign(momentum) * min(abs(momentum), 0.15)
            
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            print(f"计算动量趋势时出错: {str(e)}")
            return 0.5
            
    def _calculate_volatility_quality(self, data: pd.DataFrame) -> float:
        """计算波动率质量得分
        
        Args:
            data: 历史数据DataFrame，需要至少20天数据
            
        Returns:
            float: 波动率质量得分，范围[0, 1]
        """
        if len(data) < self.analysis_periods['min_data_days']:
            print(f"警告: 数据量不足{self.analysis_periods['min_data_days']}天...")
            return 0.5
            
        try:
            # 计算波动率指标
            high_low_range = (data['最高'] - data['最低']) / data['收盘'].shift(1)
            volatility = high_low_range.rolling(window=14).std()  # 匹配ATR标准周期
            
            # 计算波动率聚集性
            vol_clustering = volatility.rolling(window=5).mean() / volatility.rolling(window=20).mean()
            
            # 计算波动率趋势
            vol_trend = volatility.rolling(window=5).mean().diff()
            
            # 获取最新值
            latest_vol = volatility.iloc[-1]
            latest_clustering = vol_clustering.iloc[-1]
            latest_trend = vol_trend.iloc[-1]
            
            # 基础分
            score = 0.5
            
            # 波动率水平影响
            vol_percentile = pd.Series(volatility).rank(pct=True).iloc[-1]
            if vol_percentile < 0.2:  # 低波动
                score += 0.2
            elif vol_percentile > 0.8:  # 高波动
                score -= 0.2
                
            # 波动率聚集性影响
            if latest_clustering < 0.8:  # 波动率分散
                score += 0.15
            elif latest_clustering > 1.2:  # 波动率聚集
                score -= 0.15
                
            # 波动率趋势影响
            if latest_trend < 0:  # 波动率下降
                score += 0.15
            elif latest_trend > 0:  # 波动率上升
                score -= 0.15
                
            return min(1.0, max(0.0, score))
            
        except Exception as e:
            print(f"计算波动率质量时出错: {str(e)}")
            return 0.5
    
    def _normalize_score(self, code: str, score: float) -> float:
        """标准化赚钱指数（优化版）
        
        使用动态分位数和自适应窗口标准化
        
        Args:
            code: ETF代码
            score: 原始得分
            
        Returns:
            float: 标准化后的得分[0,1]
        """
        if code not in self._score_history:
            self._score_history[code] = []
            
        history = self._score_history[code]
        history.append(score)
        
        # 使用较短的窗口(约1个月)捕捉市场变化
        if len(history) > 20:
            history.pop(0)
            
        if len(history) < 5:
            # 使用基于波动率的初始化
            volatility = np.std(history) if len(history) > 1 else 0.2
            normalized = np.clip((score - 0.5) * (1 + volatility) + 0.5, 0, 1)
            z_score = 0  # 初始化z_score为0,用于日志记录
        else:
            # 计算动态分位数
            sorted_scores = np.sort(history)
            q1 = np.percentile(sorted_scores, 10)  # 更敏感的分位点
            q3 = np.percentile(sorted_scores, 90)
            iqr = max(q3 - q1, 0.05)  # 防止低波动市场下区分度过低
            
            # 使用修正的Z-Score
            median = np.median(sorted_scores)
            z_score = (score - median) / iqr
            
            # 使用分段函数替代sigmoid，保持更好的区分度
            if abs(z_score) <= 1:
                normalized = 0.5 + z_score * 0.3  # 中间区域保持线性
            else:
                # 极端区域使用非线性映射
                sign = np.sign(z_score)
                normalized = 0.8 + sign * 0.2 * (1 - np.exp(-(abs(z_score) - 1)))
        
        if random.random() < 0.01:  # 1%采样率
            logging.info(f"ScoreDistribution: code={code} score={score:.2f} normalized={normalized:.2f} z={z_score:.2f}")
        
        return np.clip(normalized, 0.0, 1.0)
    
    def _calculate_adjusted_score(self, dimension_scores: Dict[str, float]) -> float:
        """计算调整后的得分（优化版）"""
        try:
            # 获取当前市场状态的相关性矩阵
            correlation_matrix = self._correlation_matrix  # 直接使用类属性
            
            # 计算维度间的相关性调整
            adjusted_scores = {}
            for dim, score in dimension_scores.items():
                correlations = correlation_matrix.get(dim, {})
                if correlations:
                    # 使用相关性加权调整
                    adjustment = sum(
                        other_score * correlations.get(other_dim, 0)
                        for other_dim, other_score in dimension_scores.items()
                        if other_dim != dim
                    ) / len(correlations)
                    
                    # 动态调整权重
                    weight = self._weights.get(dim, 1.0)
                    adjusted_scores[dim] = (score * 0.7 + adjustment * 0.3) * weight
                else:
                    adjusted_scores[dim] = score * self._weights.get(dim, 1.0)
            
            # 使用加权平均计算最终得分
            total_weight = sum(self._weights.get(dim, 1.0) for dim in adjusted_scores)
            if total_weight == 0:
                return 0.5
                
            final_score = sum(score for score in adjusted_scores.values()) / total_weight
            
            # 修改非线性变换参数（关键调整点）
            if 0.45 <= final_score <= 0.55:
                final_score = 0.5 + (final_score - 0.5) * 1.0  # 中间区域保持原样
            elif final_score > 0.55:
                # 强势区域渐进放大
                strength = min((final_score - 0.55) / 0.45, 1.0)  # 0.55→0.0, 1.0→1.0
                final_score = 0.55 + strength**0.7 * 0.45  # 非线性放大
            else:
                # 弱势区域渐进放大
                weakness = min((0.45 - final_score) / 0.45, 1.0)  # 0.45→0.0, 0.0→1.0
                final_score = 0.45 - weakness**0.7 * 0.45
            
            return np.clip(final_score, 0.0, 1.0)
            
        except Exception as e:
            print(f"计算调整得分时出错: {str(e)}")
            # 发生错误时使用简单加权平均
            base_score = sum(
                score * self._weights.get(dim, 1.0) 
                for dim, score in dimension_scores.items()
            ) / sum(self._weights.get(dim, 1.0) for dim in dimension_scores)
            return np.clip(base_score, 0.0, 1.0)
    
    def calculate_profit_score(self, code: str) -> float:
        """计算ETF赚钱效应得分(优化版)
        
        Args:
            code: ETF代码
            
        Returns:
            float: 最终得分
        """
        try:
            # 自动检测并更新相关性矩阵
            market_status = self._detect_market_status()
            self.update_dynamic_correlation(market_status)
            
            # 检查缓存
            current_time = datetime.now()
            if (code in self._data_cache and code in self._last_update and
                (current_time - self._last_update[code]).seconds < self._cache_timeout):
                return self._data_cache[code]

            # 批量获取所需数据
            data = self._fetch_history_data(code)
            if data.empty:
                return 0.5

            # 并行计算各维度得分
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    'volume_price': executor.submit(self._calculate_volume_price_correlation, data),
                    'holding': executor.submit(self._calculate_holding_stability, code, data),
                    'arbitrage': executor.submit(self._calculate_arbitrage_impact, code),
                    'volume': executor.submit(self._calculate_volume_health, code),
                    'momentum': executor.submit(self._calculate_momentum_trend, data),
                    'volatility': executor.submit(self._calculate_volatility_quality, data)
                }

                # 收集结果
                dimension_scores = {
                    'volume_price_correlation': futures['volume_price'].result(),
                    'holding_stability': futures['holding'].result(),
                    'arbitrage_impact': futures['arbitrage'].result(),
                    'volume_health': futures['volume'].result(),
                    'momentum_trend': futures['momentum'].result(),
                    'volatility_quality': futures['volatility'].result()
                }

            # 使用相关性矩阵调整计算最终得分
            final_score = self._calculate_adjusted_score(dimension_scores)
            
            # 标准化得分
            normalized_score = self._normalize_score(code, final_score)
            
            # 更新缓存
            self._data_cache[code] = normalized_score
            self._last_update[code] = current_time
            
            return normalized_score

        except Exception as e:
            print(f"计算赚钱效应分数时出错: {str(e)}")
            return 0.5

    def clear_cache(self):
        """清除缓存数据"""
        self._data_cache.clear()
        self._last_update.clear()
        # 同时清空指标缓存
        self._indicator_cache.clear()
        print("[DEBUG] ETF分析引擎缓存已清空")

    def update_dynamic_correlation(self, market_status: str):
        """根据市场状态调整相关性系数"""
        # 市场状态划分：normal, high_volatility, low_volatility
        adjustment_map = {
            'high_volatility': {
                ('momentum_trend', 'volatility_quality'): -0.45,
                ('volume_price_correlation', 'holding_stability'): -0.40
            },
            'low_volatility': {
                ('arbitrage_impact', 'volume_health'): 0.25,
                ('momentum_trend', 'volume_price_correlation'): 0.75
            }
        }
        current_adjust = adjustment_map.get(market_status, {})
        for (dim1, dim2), value in current_adjust.items():
            self._correlation_matrix[dim1][dim2] = value
            self._correlation_matrix[dim2][dim1] = value

    def _detect_market_status(self) -> str:
        """带缓存的市场状态检测"""
        current_time = datetime.now()
        if (current_time - self._last_market_detection).seconds < self.market_status_refresh_interval:
            return self._last_market_status
            
        # 执行实际检测逻辑
        new_status = self._actual_market_detection()
        self._last_market_status = new_status
        self._last_market_detection = current_time
        return new_status

    def _actual_market_detection(self) -> str:
        """实际的市场状态检测逻辑"""
        index_data = self._fetch_history_data('sh000300')
        if len(index_data) < 30:
            return 'normal'
            
        volatility = index_data['收盘'].pct_change().std() * np.sqrt(252)
        
        if volatility > 0.25:
            return 'high_volatility'
        elif volatility < 0.15:
            return 'low_volatility'
        return 'normal'

    def batch_calculate_scores(self, codes: List[str]) -> Dict[str, float]:
        """批量计算多个ETF的得分"""
        # 单次检测市场状态
        market_status = self._detect_market_status()
        self.update_dynamic_correlation(market_status)
        
        results = {}
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_code = {executor.submit(self.calculate_profit_score, code): code for code in codes}
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                try:
                    results[code] = future.result()
                except Exception as e:
                    print(f"计算{code}得分时出错: {str(e)}")
                    results[code] = 0.5
        return results

    def get_profit_scores(self, code: str, end_date: str) -> pd.Series:
        """获取最近65天的赚钱效应得分"""
        cache_key = f"{code}_{end_date}"
        if cache_key in self._profit_score_cache:
            return self._profit_score_cache[cache_key]
            
        # 获取指定结束日期前的65个交易日数据
        data = self._fetch_history_data(code, end_date=end_date, days=self._cache_days)
        if data.empty:
            return pd.Series()
        
        # 按时间顺序计算每个交易日的得分
        scores = []
        for i in range(len(data)):
            # 截取到当前日期的数据
            current_data = data.iloc[:i+1]
            # 计算当日得分
            score = self._calculate_single_day_score(code, current_data)
            scores.append(score)
        
        series = pd.Series(scores, index=data.index, name='profit_score')
        self._profit_score_cache[cache_key] = series
        return series

    def _calculate_single_day_score(self, code: str, data: pd.DataFrame) -> float:
        """计算单日得分"""
        # 并行计算各维度得分
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {
                'volume_price': executor.submit(self._calculate_volume_price_correlation, data),
                'holding': executor.submit(self._calculate_holding_stability, code, data),
                'arbitrage': executor.submit(self._calculate_arbitrage_impact, code),
                'volume': executor.submit(self._calculate_volume_health, code),
                'momentum': executor.submit(self._calculate_momentum_trend, data),
                'volatility': executor.submit(self._calculate_volatility_quality, data)
            }
            dimension_scores = {k: v.result() for k, v in futures.items()}
        
        # 使用相关性矩阵调整计算最终得分
        final_score = self._calculate_adjusted_score(dimension_scores)
        return self._normalize_score(code, final_score)

    @timing_decorator
    def get_all_indicators(self, code: str, data: pd.DataFrame, end_date: str = None) -> Tuple[dict, dict]:
        """统一获取所有维度指标（带性能监控）"""
        try:
            # 日期截取逻辑
            if end_date and isinstance(data.index, pd.DatetimeIndex):
                data = data[data.index <= pd.to_datetime(end_date)]
            
            # 使用自适应的线程池大小
            with ThreadPoolExecutor(max_workers=self._thread_workers) as executor:
                futures = {
                    'volume_price_correlation': executor.submit(self._calculate_volume_price_correlation, data),
                    'holding_stability': executor.submit(self._calculate_holding_stability, code, data),
                    'arbitrage_impact': executor.submit(self._calculate_arbitrage_impact, code),
                    'volume_health': executor.submit(self._calculate_volume_health, code),
                    'momentum_trend': executor.submit(self._calculate_momentum_trend, data),
                    'volatility_quality': executor.submit(self._calculate_volatility_quality, data),
                }
                
                # 收集所有计算结果
                dimension_scores = {name: future.result() for name, future in futures.items()}
                
                # 计算最终得分
                final_score = self._calculate_adjusted_score(dimension_scores)
                normalized_score = self._normalize_score(code, final_score)
                
                # 将得分添加到返回字典中
                dimension_scores['profit_score'] = normalized_score
                
                # 返回空的市场意图字典
                market_intent = {
                    'probabilities': {},
                    'indicators': {}
                }
                
                return (dimension_scores, market_intent)
            
        except Exception as e:
            print(f"获取指标时出错: {str(e)}")
            dimension_scores = {
                'volume_price_correlation': 0.5,
                'holding_stability': 0.5,
                'arbitrage_impact': 0.5,
                'volume_health': 0.5,
                'momentum_trend': 0.5,
                'volatility_quality': 0.5,
                'profit_score': 0.5,
            }
            market_intent = {
                'probabilities': {},
                'indicators': {}
            }
            return (dimension_scores, market_intent)

        
    # 新增辅助方法
    def should_draw_volume_prediction(self):
        """判断是否需要绘制预测成交量线"""
        # 仅在工作日显示
        now = datetime.now()
        if now.weekday() >= 5:  # 周六周日
            return False
        
        # A股交易时间段判断(包含中午休息时间)
        morning_start = datetime(now.year, now.month, now.day, 9, 30)
        morning_end = datetime(now.year, now.month, now.day, 11, 30)
        afternoon_start = datetime(now.year, now.month, now.day, 13, 0)
        afternoon_end = datetime(now.year, now.month, now.day, 15, 0)
        
        return (morning_start <= now <= morning_end) or \
               (morning_end < now < afternoon_start) or \
               (afternoon_start <= now <= afternoon_end)


    def get_current_time_ratio(self):
        """获取当前时间在交易时段中的进度比例"""
        now = datetime.now()
        
        # 定义时间点
        morning_start = datetime(now.year, now.month, now.day, 9, 30)
        morning_end = datetime(now.year, now.month, now.day, 11, 30)
        afternoon_start = datetime(now.year, now.month, now.day, 13, 0)
        afternoon_end = datetime(now.year, now.month, now.day, 15, 0)
        
        if morning_start <= now <= morning_end:
            # 上午时段
            elapsed = (now - morning_start).total_seconds() / 60
            return min(elapsed / 120, 0.5)  # 上午2小时
            
        elif morning_end < now < afternoon_start:
            # 中午休息时段，固定显示上午结束时的进度
            return 0.5  # 保持在上午结束的位置
            
        elif afternoon_start <= now <= afternoon_end:
            # 下午时段
            elapsed = (now - afternoon_start).total_seconds() / 60
            return 0.5 + (elapsed / 120) * 0.5  # 下午2小时，从0.5开始
            
        return 0        
    

    def predict_final_volume(self,current_volume: float, time_percent: float) -> float:
        """
        改进版成交量预测模型（已考虑非连续交易时间）
        参数说明：
            time_percent: 基于有效交易时间(9:30-11:30,13:00-15:00)的进度百分比
        """
        # 模型参数
        alpha = 0.65
        beta = 0.015
        total_minutes = 240  # 4小时*60分钟

        # 计算实际交易分钟数
        traded_min = total_minutes * time_percent
        
        # 精确时间轴映射
        if traded_min <= 120:  # 上午时段
            current_hour = 9.5 + traded_min/60  # 9:30基准
        else:  # 下午时段
            pm_start = 13.0  # 13:00基准
            current_hour = pm_start + (traded_min-120)/60

        # 核心预测公式
        t = traded_min  # 使用实际交易分钟数
        u_component = alpha * (1 - math.exp(-beta * t))
        linear_component = (1 - alpha) * (t / total_minutes)
        denominator = max(u_component + linear_component, 0.01)
        
        predicted_total = current_volume / denominator

        # 动态时段修正（精确到分钟）
        if 9.5 <= current_hour < 10.5:  # 早盘前1小时
            predicted_total *= 1.2
        elif 14.5 <= current_hour < 15.0:  # 尾盘半小时
            predicted_total *= 1.5

        return round(predicted_total, 2)

    def _calculate_market_intent(self, data: pd.DataFrame) -> dict:
        """计算主力操盘意图"""
        # 在计算前添加数据有效性检查
        if data.empty or data.isnull().values.any():
            return {}
        
        try:
            # 获取最新数据点
            price_change = data['涨跌幅'].iloc[-1] / 100  # 转换为小数
            
            # 计算成本变化
            if '平均成本' in data.columns:
                market_cost_change = data['平均成本'].pct_change().iloc[-1]
            else:
                market_cost_change = 0
            
            # 计算换手率作为量能指标
            turnover_rate = data.get('换手率', pd.Series([0] * len(data))).iloc[-1]
            
            # 调用主力意图分析函数（移除量比参数）
            intent_result = analyze_market_intent_final(
                price_change,
                market_cost_change,
                0,  # 量比已移除
                0   # 前一日量比已移除
            )
            
            return intent_result
        except Exception as e:
            print(f"计算主力意图时出错: {str(e)}")
            return {
                'probabilities': {
                    '建仓': 0, '试盘': 0, '洗盘': 0,
                    '拉升': 0, '出货': 0, '反弹': 0, '砸盘': 0
                },
                'indicators': {
                    '成本压力比': 0,
                    '量能动量': 0,
                    '价格加速度': 0
                }
            }
    def has_stock_cyq_data(self, code: str) -> bool:
        """判断是否存在筹码数据"""
        if str(code).startswith('BK') or str(code).startswith('5'):
            return False
        else:
            return True
    def calculate_period_avg_cost(self, code: str, data: pd.DataFrame, period: str = 'day') -> pd.DataFrame:
        """
        计算不同周期的平均成本
        
        Args:
            code: ETF代码
            data: 原始K线数据
            period: 周期类型('day', 'week', 'month')
            
        Returns:
            添加了平均成本的DataFrame
        """
        try:
            # 获取日级别数据
            daily_data = self._fetch_history_data(code)
            if daily_data.empty:
                return data
            
            cyq_data = pd.DataFrame()
            # 获取日级别筹码数据
            if str(code).startswith('BK'):
                cyq_data = calculate_concept_avg_cost(code)
            elif self.has_stock_cyq_data(code):
                # 获取筹码数据
                cyq_data = ak.stock_cyq_em(symbol=code, adjust="qfq")
            
            if cyq_data.empty:
                return data
                
            # 处理筹码数据
            cyq_data['日期'] = pd.to_datetime(cyq_data['日期'])
            cyq_data = cyq_data.set_index('日期')
            
            # 确保数据包含平均成本列
            if '平均成本' not in cyq_data.columns:
                print("筹码数据中未找到平均成本列")
                return data
                
            if '成交量' not in data.columns:
                print("筹码数据中未找到成交量列")
                return data

            # 根据不同周期计算平均成本
            if period == 'week':
                # 合并日线数据和筹码数据
                daily_data = daily_data.merge(
                    cyq_data[['平均成本']],
                    how='left',
                    left_index=True,
                    right_index=True
                )
                
                # 使用成交量加权计算周平均成本
                def weighted_mean(group):
                    return np.average(
                        group['平均成本'],
                        weights=group['成交量'],
                        axis=0
                    )
                
                # 按周计算加权平均成本
                # 注意：和同花顺的数据不一致
                cost_weekly = daily_data.resample('W').apply(weighted_mean)
                
                # 将周度数据对齐到原始数据的索引
                data['平均成本'] = cost_weekly.reindex(data.index, method='ffill')
                
            elif period == 'month':
                # 使用每月最后一个交易日的平均成本
                cost_monthly = cyq_data['平均成本'].resample('M').last()
                # 将月度数据对齐到原始数据的索引
                data['平均成本'] = cost_monthly.reindex(data.index, method='ffill')
                
            else:  # 日线级别
                # 直接合并日线数据
                data = data.merge(
                    cyq_data[['平均成本']],
                    how='left',
                    left_index=True,
                    right_index=True
                )
                # 填充缺失值
                data['平均成本'] = data['平均成本'].ffill().bfill()
            
            return data
            
        except Exception as e:
            print(f"计算{period}周期平均成本时出错: {str(e)}")
            return data

    def get_chip_attributes(self, code: str) -> list:
        """获取筹码分析相关的属性配置
        
        Args:
            code: 股票代码
            
        Returns:
            list: 筹码分析属性列表
        """
        if str(code).startswith('BK'):
            return [
                {
                    'name': '平均成本',
                    'column': '平均成本',
                    'format': '.3f',
                    'default': np.nan
                }
            ]
        else:
            return [
                {
                    'name': '平均成本',
                    'column': '平均成本', 
                    'format': '.3f',
                    'default': np.nan
                },
                {
                    'name': '90集中度',
                    'column': '90集中度',
                    'format': '.3f', 
                    'default': np.nan
                }
            ]
    def get_latest_condition_trigger(self, code: str, conditions: List[ConditionBase]) -> Optional[Dict]:
        """检查最新的条件触发信息"""
        if code.startswith('BK'):
                print(f"板块代码 {code} 不支持条件触发检测")
                return None        
        try:
            # 使用load_data获取最近两周的数据，包含计算好的指标
            end_date = datetime.now()
            start_date = end_date - timedelta(days=14)  # 取最近2周数据
            
            data = self.load_data(
                code=code,
                symbol_name='',  # 非板块代码可以传空字符串
                period_mode='day',  # 使用日线数据
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                period_config={
                    'day': {
                        'ak_period': 'daily',
                        'buffer_ratio': '0.2',
                        'min_buffer': '3'
                    }
                }
            )
            
            if data.empty:
                return None
            
            latest_trigger = None
            n_days = 5  # 与 etf_kline_window.py 保持一致
            
            # 遍历所有条件
            for condition in conditions:
                # 遍历历史数据，从最新到最旧
                for i in range(len(data)-1, n_days-1, -1):  # 确保有足够的历史数据
                    # 构建数据序列（当前日期及其前n_days日）
                    data_sequence = []
                    for j in range(n_days + 1):  # n_days + 1 个数据点
                        idx = i - j  # 从当前日期往前取
                        if 0 <= idx < len(data):  # 确保索引有效
                            data_sequence.append(data.iloc[idx])
                        else:
                            break  # 如果索引无效，停止添加数据
                    
                    if len(data_sequence) != n_days + 1:  # 如果没有足够的数据点
                        continue
                        
                    # 检查条件
                    signal = condition.check(data_sequence)
                    
                    if signal.triggered:
                        trigger_time = data.index[i]
                        # 如果这是最新的触发，则更新
                        if latest_trigger is None or trigger_time > latest_trigger['trigger_time']:
                            desc_first_row = signal.description.split('\n')[0]
                            latest_trigger = {
                                'trigger_time': trigger_time,
                                'message': f"{trigger_time.strftime('%Y-%m-%d')}:{desc_first_row} {signal.change}",
                                'level': signal.level.value,
                                'score': signal.score
                            }
                        break  # 找到该条件的最新触发，跳出内层循环
            
            return latest_trigger
            
        except Exception as e:
            print(f"检测条件触发时出错: {str(e)}")
            return None

    def _calculate_bollinger_bands(self, data: pd.DataFrame, window: int = 20, num_std: float = 2) -> pd.DataFrame:
        """计算布林带指标"""
        try:
            if data is None or data.empty:
                return data
            key = ('boll', window, num_std, len(data), data.index[-1] if isinstance(data.index, pd.DatetimeIndex) else str(data.index[-1]))
            cached = self._indicator_cache.get(key)
            if cached is not None:
                df = data.copy()
                for col in ['MA20','BOLL_STD','BOLL_UPPER','BOLL_LOWER','BBW','BBW_PEAK','BBW_VALLEY','BBW_DROP','BBW_RISE','BBW_PEAK_DATE','BBW_VALLEY_DATE']:
                    if col in cached.columns:
                        df[col] = cached[col]
                return df
            # 计算移动平均线(中轨)
            data['MA20'] = data['收盘'].rolling(window=window, min_periods=1).mean()
            
            # 计算标准差 - 修复NaN问题
            data['BOLL_STD'] = data['收盘'].rolling(window=window, min_periods=1).std()
            
            # 计算上轨和下轨
            data['BOLL_UPPER'] = data['MA20'] + num_std * data['BOLL_STD']
            data['BOLL_LOWER'] = data['MA20'] - num_std * data['BOLL_STD']
            
            # 计算BBW指标
            data['BBW'] = (data['BOLL_UPPER'] - data['BOLL_LOWER']) / data['MA20']
            
            # 简化极值日期计算，避免apply中使用Timestamp
            # 直接使用滚动窗口的最大最小值，不计算具体日期
            data['BBW_PEAK_DATE'] = pd.NaT  # 暂时设为空值
            data['BBW_VALLEY_DATE'] = pd.NaT  # 暂时设为空值
            
            # 计算BBW的前期峰值和谷值
            data['BBW_PEAK'] = data['BBW'].rolling(window=90, min_periods=1).max()
            data['BBW_VALLEY'] = data['BBW'].rolling(window=90, min_periods=1).min()
            
            # 计算BBW相对峰值的跌幅和相对谷值的涨幅(百分比)
            data['BBW_DROP'] = ((data['BBW_PEAK'] - data['BBW']) / data['BBW_PEAK'] * 100).round(2)
            data['BBW_RISE'] = ((data['BBW'] - data['BBW_VALLEY']) / data['BBW_VALLEY'] * 100).round(2)
            
            # 使用bfill填充前面的空值
            for col in ['BOLL_UPPER', 'BOLL_LOWER', 'BBW', 'BBW_PEAK', 'BBW_VALLEY', 'BBW_DROP', 'BBW_RISE']:
                data[col] = data[col].bfill()
            
            # 写入缓存
            self._indicator_cache[key] = data[[
                'MA20','BOLL_STD','BOLL_UPPER','BOLL_LOWER','BBW','BBW_PEAK','BBW_VALLEY','BBW_DROP','BBW_RISE','BBW_PEAK_DATE','BBW_VALLEY_DATE'
            ]].copy()
            return data
            
        except Exception as e:
            print(f"计算布林带指标时出错: {str(e)}")
            return data

    def load_data(self, code: str, symbol_name: str, period_mode: str,
                 start_date: str, end_date: str, period_config: dict, 
                 ma_lines: list = None, force_refresh: bool = False) -> pd.DataFrame:
        """加载数据"""
        try:
            if ma_lines is None:
                ma_lines = [5, 10, 20, 250]  # 默认包含年线
            
            config = period_config[period_mode]
            
            # 转换日期格式
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
            # 计算时间范围（天数）
            time_range = (end_dt - start_dt).days
            
            # 计算缓冲天数
            buffer_days = int(config['min_buffer'])
            if period_mode == 'day':
                buffer_days = max(
                    int(float(config['buffer_ratio']) * time_range),
                    buffer_days,
                    250 * 2 # 只在日线模式下确保有足够数据计算年线
                )
            elif period_mode == 'week':
                buffer_weeks = max(
                    int(float(config['buffer_ratio']) * time_range / 7),
                    int(config['min_buffer'])
                )
                buffer_days = buffer_weeks * 7
            else:  # month
                buffer_months = max(
                    int(float(config['buffer_ratio']) * time_range / 30),
                    int(config['min_buffer'])
                )
                buffer_days = buffer_months * 30
            
            # 调整查询日期范围（加入缓冲）
            query_start = start_dt - timedelta(days=buffer_days)
            query_end = end_dt
            
            # 获取历史数据
            if str(code).startswith('BK'):
                hist_data = ak.stock_board_concept_hist_em(
                    symbol=symbol_name,
                    start_date=query_start.strftime("%Y%m%d"),
                    end_date=query_end.strftime("%Y%m%d")
                )
            elif str(code).startswith('5') or str(code).startswith('15'):
                hist_data = ak.fund_etf_hist_em(
                    symbol=code,
                    period=period_config[period_mode]['ak_period'],
                    start_date=query_start.strftime("%Y%m%d"),
                    end_date=query_end.strftime("%Y%m%d"),
                    adjust="qfq"
                )
            elif code == "1A0001" or code == "000001":
                # 使用指数历史数据接口
                print(f"[DEBUG] 获取指数历史数据: 代码={code}, 周期={period_config[period_mode]['ak_period']}, 开始日期={query_start.strftime('%Y%m%d')}, 结束日期={query_end.strftime('%Y%m%d')}")
                hist_data = ak.index_zh_a_hist(
                    symbol="000001",  # 上证指数代码
                    period=period_config[period_mode]['ak_period'],
                    start_date=query_start.strftime("%Y%m%d"),
                    end_date=query_end.strftime("%Y%m%d"),
                )
                print(f"[DEBUG] 指数历史数据获取结果: 长度={len(hist_data)}")
            else:
                hist_data = ak.stock_zh_a_hist(
                    symbol=code,
                    start_date=query_start.strftime("%Y%m%d"),
                    end_date=query_end.strftime("%Y%m%d"),
                    adjust="qfq"
                )
            
            if hist_data.empty:
                return pd.DataFrame()
            
            # 数据预处理
            hist_data['日期'] = pd.to_datetime(hist_data['日期'])
            hist_data = hist_data.set_index('日期')
            hist_data = hist_data.sort_index()
            
            # 周/月数据重采样
            if period_mode != 'day' and '周' in period_config[period_mode]['ak_period']:
                hist_data = hist_data.resample('W-Mon').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            
            # 计算MA均线
            for period in ma_lines:
                hist_data[f'MA{period}'] = hist_data['收盘'].rolling(
                    window=period,
                    min_periods=1
                ).mean().bfill()
            
            # 添加布林线计算 - 修改为使用新方法
            if 20 in ma_lines:  # 如果包含MA20
                hist_data = self._calculate_bollinger_bands(hist_data)
            
            # 计算KDJ指标
            hist_data = self._calculate_kdj(hist_data)
            

            # 截取时间范围
            cutoff_date = datetime.now() - timedelta(days=time_range)
            if period_mode == 'month':
                min_months = int(config['min_buffer'])
                buffer_months = max(
                    min_months,
                    int(time_range / 30 * float(config['buffer_ratio']))
                )
                cutoff_date = cutoff_date - relativedelta(months=buffer_months)
            
            hist_data = hist_data[hist_data.index >= cutoff_date]
            
            # 计算平均成本
            try:
                hist_data = self.calculate_period_avg_cost(
                    code,
                    hist_data,
                    period_mode
                ).round(3)
            except Exception as e:
                print(f"获取平均成本数据失败: {str(e)}")
                # 设置默认值
                hist_data['平均成本'] = hist_data['收盘'].rolling(20).mean().round(3)
            
            # 获取筹码数据
            if self.has_stock_cyq_data(code):
                try:
                    cyq_data = ak.stock_cyq_em(symbol=code, adjust="qfq")
                    if not cyq_data.empty:
                        cyq_data['日期'] = pd.to_datetime(cyq_data['日期'])
                        cyq_data = cyq_data.set_index('日期')
                        
                        # 确保数据列名正确
                        column_mapping = {
                            '90%低': '90成本-低',
                            '90%高': '90成本-高',
                            '70%低': '70成本-低',
                            '70%高': '70成本-高',
                            '90%集中度': '90集中度',
                            '70%集中度': '70集中度'
                        }
                        cyq_data = cyq_data.rename(columns=column_mapping)
                        
                        # 将数据对齐到hist_data的索引
                        aligned_data = cyq_data.reindex(hist_data.index, method='ffill')
                        for col in aligned_data.columns:
                            hist_data[col] = aligned_data[col]
                except Exception as e:
                    print(f"获取筹码数据失败: {str(e)}")
            
            return hist_data
            
        except Exception as e:
            print(f"加载数据时出错: {str(e)}")
            return pd.DataFrame()

    def _calculate_kdj(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算KDJ指标（带缓存）"""
        if data is None or data.empty:
            return data
        key = ('kdj', len(data), data.index[-1] if isinstance(data.index, pd.DatetimeIndex) else str(data.index[-1]))
        cached = self._indicator_cache.get(key)
        if cached is not None:
            df = data.copy()
            for col in ['K','D','J']:
                if col in cached.columns:
                    df[col] = cached[col]
            return df
        low_list = data['最低'].rolling(window=9, min_periods=1).min()
        high_list = data['最高'].rolling(window=9, min_periods=1).max()
        
        # 计算 RSV 值
        rsv = (data['收盘'] - low_list) / (high_list - low_list) * 100

        # --- 数据清洗 ----------------------------------------------------
        # 当最高价和最低价相等时, 分母为 0 会产生 inf; 另外也可能出现 NaN
        # 统一将非有限数替换为 NaN, 再用 0 进行填充, 以免 astype(int) 抛异常
        rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(0)

        # 计算 K、D、J 值; 先保持为 float, 清洗后再转 int
        k_series = rsv.ewm(alpha=1/3, adjust=False).mean()
        k_series = k_series.replace([np.inf, -np.inf], np.nan).fillna(0)

        d_series = k_series.ewm(alpha=1/3, adjust=False).mean()
        d_series = d_series.replace([np.inf, -np.inf], np.nan).fillna(0)

        j_series = (3 * k_series - 2 * d_series)
        j_series = j_series.replace([np.inf, -np.inf], np.nan).fillna(0)

        # 最终转为 int 类型
        data['K'] = k_series.round().astype(int)
        data['D'] = d_series.round().astype(int)
        data['J'] = j_series.round().astype(int)
        # 缓存
        self._indicator_cache[key] = data[['K','D','J']].copy()
        return data

    def calculate_rsi(self, df: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
        """计算RSI指标（带缓存）"""
        try:
            if df is None or df.empty:
                return df
            key = ('rsi', tuple(periods), len(df), df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else str(df.index[-1]))
            cached = self._indicator_cache.get(key)
            if cached is not None:
                result = df.copy()
                for col in cached.columns:
                    result[col] = cached[col]
                return result
            temp = df.copy()
            temp['price_change'] = temp['收盘'].diff()
            for period in periods:
                gains = temp['price_change'].where(temp['price_change'] > 0, 0)
                losses = -temp['price_change'].where(temp['price_change'] < 0, 0)
                alpha = 1.0 / period
                avg_gains = gains.ewm(alpha=alpha, adjust=False).mean()
                avg_losses = losses.ewm(alpha=alpha, adjust=False).mean()
                rs = avg_gains / avg_losses
                rsi = 100 - (100 / (1 + rs))
                rsi = rsi.replace([np.inf, -np.inf], np.nan).fillna(50)
                rsi = rsi.clip(0, 100)
                temp[f'RSI{period}'] = rsi
            temp = temp.drop(['price_change'], axis=1)
            # 缓存RSI列
            self._indicator_cache[key] = temp[[f'RSI{p}' for p in periods]].copy()
            result = df.copy()
            for p in periods:
                result[f'RSI{p}'] = temp[f'RSI{p}']
            return result
        except Exception:
            return df

def show_correlation_changes(engine, status):
    original_matrix = copy.deepcopy(engine._correlation_matrix)
    engine.update_dynamic_correlation(status)
    
    print(f"\n[{status}]模式矩阵调整：")
    for dim1 in original_matrix:
        for dim2 in original_matrix[dim1]:
            if original_matrix[dim1][dim2] != engine._correlation_matrix[dim1][dim2]:
                print(f"{dim1}-{dim2}: {original_matrix[dim1][dim2]} → {engine._correlation_matrix[dim1][dim2]}")


def main():
    """测试函数"""
    engine = ETFAnalysisEngine()
    test_codes = ["159869", "513560", "520600", "159873"]  # 测试多个ETF
    
    # 获取所有ETF列表
    try:
        import akshare as ak

        # 使用多API备用机制获取ETF数据
        from .etf_data_fetcher import get_etf_spot_data
        all_etfs = get_etf_spot_data(use_cache=True)
        etf_names = dict(zip(all_etfs['代码'], all_etfs['名称']))
    except Exception as e:
        print(f"获取ETF列表失败: {e}")
        etf_names = {}
    
    for code in test_codes:
        # 获取ETF名称 - 优先从ETF列表中获取
        etf_name = etf_names.get(code, "未知")
        if etf_name == "未知":
            try:
                # 如果从列表中未找到，尝试从实时数据获取
                current_data = engine._realtime_data.get_realtime_quotes(code)
                if current_data and '名称' in current_data:
                    etf_name = current_data['名称']
            except Exception as e:
                print(f"获取ETF {code} 名称失败: {e}")
        
        print(f"\nETF {code} - {etf_name} 赚钱效应分析结果:")
        
        # 获取历史数据
        data = engine._fetch_history_data(code)
        if not data.empty:
            # 并行计算各维度得分
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    'volume_price': executor.submit(engine._calculate_volume_price_correlation, data),
                    'holding': executor.submit(engine._calculate_holding_stability, code, data),
                    'arbitrage': executor.submit(engine._calculate_arbitrage_impact, code),
                    'volume': executor.submit(engine._calculate_volume_health, code),
                    'momentum': executor.submit(engine._calculate_momentum_trend, data),
                    'volatility': executor.submit(engine._calculate_volatility_quality, data)
                }

                # 收集结果
                dimension_scores = {
                    'volume_price_correlation': futures['volume_price'].result(),
                    'holding_stability': futures['holding'].result(),
                    'arbitrage_impact': futures['arbitrage'].result(),
                    'volume_health': futures['volume'].result(),
                    'momentum_trend': futures['momentum'].result(),
                    'volatility_quality': futures['volatility'].result()
                }

            # 使用与UI相同的计算流程
            # 1. 检测市场状态并更新相关性矩阵
            market_status = engine._detect_market_status()
            engine.update_dynamic_correlation(market_status)
            
            # 2. 计算调整后的得分
            final_score = engine._calculate_adjusted_score(dimension_scores)
            
            # 3. 标准化处理
            normalized_score = engine._normalize_score(code, final_score)
            
            # 打印各维度得分（保持原有格式）
            print(f"量价背离指数 (权重: {engine._weights['volume_price_correlation']:.0%}): {dimension_scores['volume_price_correlation']:.2f}")
            print(f"筹码稳定度   (权重: {engine._weights['holding_stability']:.0%}): {dimension_scores['holding_stability']:.2f}")
            print(f"套利影响因子 (权重: {engine._weights['arbitrage_impact']:.0%}): {dimension_scores['arbitrage_impact']:.2f}")
            print(f"量能结构健康 (权重: {engine._weights['volume_health']:.0%}): {dimension_scores['volume_health']:.2f}")
            print(f"动量趋势指标 (权重: {engine._weights['momentum_trend']:.0%}): {dimension_scores['momentum_trend']:.2f}")
            print(f"波动率质量   (权重: {engine._weights['volatility_quality']:.0%}): {dimension_scores['volatility_quality']:.2f}")
            
            # 打印最终得分（与UI显示一致）
            print(f"\n赚钱效应得分（调整后）: {final_score:.3f}")
            print(f"标准化赚钱指数: {normalized_score:.3f}")
        else:
            print("无法获取历史数据")
        print("-" * 50)

    # 使用示例
    show_correlation_changes(engine, 'high_volatility')
    show_correlation_changes(engine, 'low_volatility')

if __name__ == "__main__":
    main() 