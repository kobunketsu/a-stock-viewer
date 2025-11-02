from datetime import datetime
from typing import Dict, Optional

import akshare as ak
import pandas as pd


class ETFRealtimeData:
    """ETF实时数据获取类
    
    负责获取ETF的实时行情数据，包括IOPV、成交量、价格等信息。
    """
    
    def __init__(self):
        self._cache: Dict[str, Dict] = {}  # 数据缓存
        self._cache_time: Dict[str, datetime] = {}  # 缓存时间
    
    def get_realtime_quotes(self, code: str) -> Optional[Dict]:
        """获取ETF实时行情数据（使用多API备用机制）
        
        Args:
            code: ETF代码
            
        Returns:
            Dict: 实时行情数据字典
        """
        try:
            # 使用多API备用机制获取ETF实时行情
            from .etf_data_fetcher import get_etf_by_code
            data = get_etf_by_code(code, use_cache=True)
            
            if data is None:
                return None
            
            # 缓存数据
            self._cache[code] = data
            self._cache_time[code] = datetime.now()
            
            return data
            
        except Exception as e:
            print(f"获取实时数据失败: {e}")
            return None
    
    def get_iopv(self, code: str) -> Optional[float]:
        """获取ETF的IOPV(实时估值)
        
        Args:
            code: ETF代码
            
        Returns:
            float: IOPV值
        """
        data = self.get_realtime_quotes(code)
        if data and 'IOPV实时估值' in data:
            try:
                return float(data['IOPV实时估值'])
            except (ValueError, TypeError):
                return None
        return None
    
    def get_premium_ratio(self, code: str) -> Optional[float]:
        """获取ETF溢价率
        
        Args:
            code: ETF代码
            
        Returns:
            float: 溢价率(%)
        """
        data = self.get_realtime_quotes(code)
        if data and '基金折价率' in data:
            try:
                return -float(data['基金折价率'])  # 转换折价率为溢价率
            except (ValueError, TypeError):
                return None
        return None
    
    def get_volume_structure(self, code: str) -> Optional[Dict[str, float]]:
        """获取成交量结构数据
        
        Args:
            code: ETF代码
            
        Returns:
            Dict: 包含内外盘等信息的字典
        """
        data = self.get_realtime_quotes(code)
        if not data:
            return None
            
        result = {}
        try:
            # 提取内外盘
            if '外盘' in data and '内盘' in data:
                out_vol = float(data['外盘'])
                in_vol = float(data['内盘'])
                total_vol = out_vol + in_vol
                if total_vol > 0:
                    result['out_ratio'] = out_vol / total_vol
                    result['in_ratio'] = in_vol / total_vol
                
            return result
        except (ValueError, TypeError):
            return None
    
    def get_turnover_rate(self, code: str) -> Optional[float]:
        """获取换手率
        
        Args:
            code: ETF代码
            
        Returns:
            float: 换手率(%)
        """
        data = self.get_realtime_quotes(code)
        if data and '换手率' in data:
            try:
                return float(data['换手率'])
            except (ValueError, TypeError):
                return None
        return None

def main():
    """测试函数"""
    realtime = ETFRealtimeData()
    code = "159307"  # 红利低波100ETF
    
    # 测试实时数据获取
    quotes = realtime.get_realtime_quotes(code)
    if quotes:
        print(f"ETF {code} 实时行情:")
        print(f"IOPV: {realtime.get_iopv(code)}")
        print(f"溢价率: {realtime.get_premium_ratio(code)}%")
        print(f"换手率: {realtime.get_turnover_rate(code)}%")
        print("成交量结构:", realtime.get_volume_structure(code))
    else:
        print("获取数据失败")

if __name__ == "__main__":
    main() 