"""增强的前高前低检测算法

解决当前算法在当日数据未完全形成时无法检测前高前低的问题
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.signal import find_peaks


class EnhancedPeakDetector:
    """增强的峰值检测器
    
    支持多种数据类型的峰值检测：
    1. 日线数据：完整的历史peak检测
    2. 分时数据：当日部分数据的peak检测
    3. 实时数据：当前价格的突破检测
    """
    
    def __init__(self):
        self.detection_cache = {}  # 检测结果缓存
    
    def detect_peaks(self, 
                    data: pd.DataFrame, 
                    data_type: str = "daily",
                    current_price: Optional[float] = None,
                    lookback_days: int = 12) -> Dict[str, Any]:
        """
        检测价格数据的峰值（高点）和谷值（低点）
        
        :param data: 价格数据，必须包含'最高'、'最低'、'开盘'、'收盘'列
        :param data_type: 数据类型 ("daily", "intraday", "realtime")
        :param current_price: 当前价格（用于实时检测）
        :param lookback_days: 回看天数
        :return: 包含峰值信息的字典
        """
        try:
            if data.empty:
                return {"error": "数据为空"}
            
            # 根据数据类型选择检测策略
            if data_type == "daily":
                return self._detect_daily_peaks(data, lookback_days)
            elif data_type == "intraday":
                return self._detect_intraday_peaks(data, current_price)
            elif data_type == "realtime":
                if current_price is None:
                    return {"error": "实时检测需要提供当前价格"}
                return self._detect_realtime_peaks(data, current_price)
            else:
                return {"error": f"不支持的数据类型: {data_type}"}
                
        except Exception as e:
            return {"error": f"峰值检测失败: {str(e)}"}
    
    def _detect_daily_peaks(self, data: pd.DataFrame, lookback_days: int) -> Dict[str, Any]:
        """检测日线数据的峰值（原有算法优化版）"""
        try:
            # 获取最近lookback_days的数据
            recent_data = data.tail(lookback_days) if len(data) > lookback_days else data
            
            # 获取当前价格
            current_price = recent_data['收盘'].iloc[-1]
            
            # 计算双价格序列
            entity_high_prices = np.maximum(recent_data['开盘'].values, recent_data['收盘'].values).astype(np.float64)
            shadow_high_prices = recent_data['最高'].values.astype(np.float64)
            entity_low_prices = np.minimum(recent_data['开盘'].values, recent_data['收盘'].values).astype(np.float64)
            shadow_low_prices = recent_data['最低'].values.astype(np.float64)
            
            # 检测高点
            high_peaks = self._find_peaks_optimized(
                shadow_high_prices, 
                prominence_factor=0.1,
                distance=5,  # 日线数据保持5个交易日间隔
                min_prominence=shadow_high_prices.std() * 0.05  # 降低最小突出度要求
            )
            
            # 检测低点
            low_peaks = self._find_peaks_optimized(
                -shadow_low_prices,  # 取负值检测低点
                prominence_factor=0.1,
                distance=5,
                min_prominence=shadow_low_prices.std() * 0.05
            )
            
            # 筛选比当前价格高的高点和比当前价格低的低点
            higher_peaks = self._filter_peaks_by_price(
                high_peaks, entity_high_prices, recent_data.index, current_price, "higher"
            )
            lower_peaks = self._filter_peaks_by_price(
                low_peaks, entity_low_prices, recent_data.index, current_price, "lower"
            )
            
            return {
                "data_type": "daily",
                "current_price": current_price,
                "high_peaks": higher_peaks,
                "low_peaks": lower_peaks,
                "total_peaks_found": len(high_peaks) + len(low_peaks),
                "higher_peaks_count": len(higher_peaks),
                "lower_peaks_count": len(lower_peaks)
            }
            
        except Exception as e:
            return {"error": f"日线峰值检测失败: {str(e)}"}
    
    def _detect_intraday_peaks(self, data: pd.DataFrame, current_price: Optional[float]) -> Dict[str, Any]:
        """检测分时数据的峰值（当日部分数据）"""
        try:
            if current_price is None:
                current_price = data['close'].iloc[-1] if 'close' in data.columns else data['收盘'].iloc[-1]
            
            # 分时数据使用不同的列名
            if 'close' in data.columns:
                # 分时数据格式
                high_prices = (data['high'].values if 'high' in data.columns else data['close'].values).astype(np.float64)
                low_prices = (data['low'].values if 'low' in data.columns else data['close'].values).astype(np.float64)
                close_prices = data['close'].values.astype(np.float64)
            else:
                # 日线数据格式
                high_prices = data['最高'].values.astype(np.float64)
                low_prices = data['最低'].values.astype(np.float64)
                close_prices = data['收盘'].values.astype(np.float64)
            
            # 分时数据使用更短的检测窗口和更低的阈值
            high_peaks = self._find_peaks_optimized(
                high_prices,
                prominence_factor=0.05,  # 降低突出度要求
                distance=10,  # 10个数据点间隔（约10分钟）
                min_prominence=high_prices.std() * 0.02  # 进一步降低最小突出度
            )
            
            low_peaks = self._find_peaks_optimized(
                -low_prices,  # 取负值检测低点
                prominence_factor=0.05,
                distance=10,
                min_prominence=low_prices.std() * 0.02
            )
            
            # 筛选峰值
            higher_peaks = self._filter_peaks_by_price(
                high_peaks, high_prices, data.index, current_price, "higher"
            )
            lower_peaks = self._filter_peaks_by_price(
                low_peaks, low_prices, data.index, current_price, "lower"
            )
            
            return {
                "data_type": "intraday",
                "current_price": current_price,
                "high_peaks": higher_peaks,
                "low_peaks": lower_peaks,
                "total_peaks_found": len(high_peaks) + len(low_peaks),
                "higher_peaks_count": len(higher_peaks),
                "lower_peaks_count": len(lower_peaks),
                "is_partial_data": True  # 标记为部分数据
            }
            
        except Exception as e:
            return {"error": f"分时峰值检测失败: {str(e)}"}
    
    def _detect_realtime_peaks(self, data: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """检测实时数据的突破（当前价格是否形成新高/新低）"""
        try:
            if current_price is None:
                return {"error": "实时检测需要提供当前价格"}
            
            # 获取历史最高价和最低价
            if '最高' in data.columns:
                historical_high = float(data['最高'].max())
                historical_low = float(data['最低'].min())
            elif 'high' in data.columns:
                historical_high = float(data['high'].max())
                historical_low = float(data['low'].min())
            else:
                historical_high = float(data['close'].max())
                historical_low = float(data['close'].min())
            
            # 检测突破
            new_high = current_price > historical_high
            new_low = current_price < historical_low
            
            # 计算突破幅度
            high_breakout_ratio = (current_price - historical_high) / historical_high * 100 if historical_high > 0 else 0
            low_breakout_ratio = (historical_low - current_price) / historical_low * 100 if historical_low > 0 else 0
            
            return {
                "data_type": "realtime",
                "current_price": current_price,
                "historical_high": historical_high,
                "historical_low": historical_low,
                "new_high": new_high,
                "new_low": new_low,
                "high_breakout_ratio": high_breakout_ratio,
                "low_breakout_ratio": low_breakout_ratio,
                "is_breakout": new_high or new_low
            }
            
        except Exception as e:
            return {"error": f"实时突破检测失败: {str(e)}"}
    
    def _find_peaks_optimized(self, 
                             data: np.ndarray, 
                             prominence_factor: float = 0.1,
                             distance: int = 5,
                             min_prominence: Optional[float] = None) -> List[int]:
        """优化的峰值检测算法"""
        try:
            if len(data) < 3:
                return []
            
            # 计算动态prominence
            data_std = float(np.std(data))
            prominence = max(data_std * prominence_factor, min_prominence or data_std * 0.01)
            
            # 使用find_peaks检测峰值
            peaks, properties = find_peaks(
                data,
                prominence=prominence,
                distance=distance
            )
            
            return peaks.tolist()
            
        except Exception as e:
            print(f"[DEBUG] 峰值检测优化失败: {e}")
            return []
    
    def _filter_peaks_by_price(self, 
                              peaks: List[int], 
                              prices: np.ndarray, 
                              dates: pd.Index, 
                              current_price: float, 
                              comparison: str) -> List[Dict[str, Any]]:
        """根据价格筛选峰值"""
        filtered_peaks = []
        
        for peak_idx in peaks:
            if peak_idx >= len(prices):
                continue
                
            peak_price = float(prices[peak_idx])
            peak_date = dates[peak_idx]
            
            # 根据比较类型筛选
            if comparison == "higher" and peak_price > current_price:
                filtered_peaks.append({
                    "index": peak_idx,
                    "price": float(peak_price),
                    "date": peak_date.strftime('%Y-%m-%d') if hasattr(peak_date, 'strftime') else str(peak_date),
                    "higher_than_current": True
                })
            elif comparison == "lower" and peak_price < current_price:
                filtered_peaks.append({
                    "index": peak_idx,
                    "price": float(peak_price),
                    "date": peak_date.strftime('%Y-%m-%d') if hasattr(peak_date, 'strftime') else str(peak_date),
                    "lower_than_current": True
                })
        
        return filtered_peaks
    
    def get_latest_high_low(self, 
                           data: pd.DataFrame, 
                           data_type: str = "daily",
                           current_price: Optional[float] = None) -> Dict[str, Any]:
        """获取最近的前高和前低价格"""
        try:
            detection_result = self.detect_peaks(data, data_type, current_price)
            
            if "error" in detection_result:
                return detection_result
            
            # 获取最近的高点和低点
            latest_high = None
            latest_low = None
            
            if detection_result.get("high_peaks"):
                # 按日期排序，获取最近的高点
                high_peaks = detection_result["high_peaks"]
                high_peaks.sort(key=lambda x: x["date"], reverse=True)
                latest_high = high_peaks[0]
            
            if detection_result.get("low_peaks"):
                # 按日期排序，获取最近的低点
                low_peaks = detection_result["low_peaks"]
                low_peaks.sort(key=lambda x: x["date"], reverse=True)
                latest_low = low_peaks[0]
            
            return {
                "current_price": detection_result.get("current_price"),
                "latest_high": latest_high,
                "latest_low": latest_low,
                "data_type": data_type,
                "is_partial_data": detection_result.get("is_partial_data", False)
            }
            
        except Exception as e:
            return {"error": f"获取最近高低点失败: {str(e)}"}


# 全局检测器实例
_peak_detector = EnhancedPeakDetector()


def detect_enhanced_peaks(data: pd.DataFrame, 
                         data_type: str = "daily",
                         current_price: Optional[float] = None) -> Dict[str, Any]:
    """便捷的峰值检测函数"""
    return _peak_detector.detect_peaks(data, data_type, current_price)


def get_enhanced_high_low(data: pd.DataFrame, 
                         data_type: str = "daily",
                         current_price: Optional[float] = None) -> Dict[str, Any]:
    """便捷的获取最近高低点函数"""
    return _peak_detector.get_latest_high_low(data, data_type, current_price)
