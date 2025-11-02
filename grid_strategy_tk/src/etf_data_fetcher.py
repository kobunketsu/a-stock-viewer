"""
ETF数据获取器 - 多API备用机制
支持东财、同花顺、新浪三个数据源，自动切换备用API
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import akshare as ak
import pandas as pd
from etf_api_monitor import log_etf_api_request


class ETFDataFetcher:
    """ETF数据获取器，支持多API备用机制"""
    
    def __init__(self):
        self.api_stats = {
            'eastmoney': {'success': 0, 'failed': 0, 'last_error': None},
            'ths': {'success': 0, 'failed': 0, 'last_error': None},
            'sina': {'success': 0, 'failed': 0, 'last_error': None}
        }
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self.cache:
            return False
        cache_time, _ = self.cache[key]
        return (datetime.now() - cache_time).seconds < self.cache_timeout
    
    def _update_api_stats(self, api_name: str, success: bool, error: str = None):
        """更新API统计信息"""
        if success:
            self.api_stats[api_name]['success'] += 1
        else:
            self.api_stats[api_name]['failed'] += 1
            if error:
                self.api_stats[api_name]['last_error'] = error
    
    def _get_eastmoney_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """获取东财ETF数据
        @return: (成功标志, DataFrame, 错误信息)
        """
        try:
            print("[ETF数据] 尝试东财API...")
            start_time = time.perf_counter()
            
            df = ak.fund_etf_spot_em()
            
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 东财API成功，耗时: {elapsed:.2f}ms，数据行数: {len(df)}")
            
            # 记录监控数据
            log_etf_api_request('eastmoney', True, elapsed, data_count=len(df))
            
            self._update_api_stats('eastmoney', True)
            return True, df, ""
            
        except Exception as e:
            error_msg = str(e)
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 东财API失败: {error_msg}")
            
            # 记录监控数据
            log_etf_api_request('eastmoney', False, elapsed, error_msg)
            
            self._update_api_stats('eastmoney', False, error_msg)
            return False, pd.DataFrame(), error_msg
    
    def _get_ths_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """获取同花顺ETF数据
        @return: (成功标志, DataFrame, 错误信息)
        """
        try:
            print("[ETF数据] 尝试同花顺API...")
            start_time = time.perf_counter()
            
            # 获取当前日期
            today = datetime.now().strftime("%Y%m%d")
            df = ak.fund_etf_spot_ths(date=today)
            
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 同花顺API成功，耗时: {elapsed:.2f}ms，数据行数: {len(df)}")
            
            # 标准化列名以匹配东财格式
            df = self._standardize_ths_columns(df)
            
            # 记录监控数据
            log_etf_api_request('ths', True, elapsed, data_count=len(df))
            
            self._update_api_stats('ths', True)
            return True, df, ""
            
        except Exception as e:
            error_msg = str(e)
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 同花顺API失败: {error_msg}")
            
            # 记录监控数据
            log_etf_api_request('ths', False, elapsed, error_msg)
            
            self._update_api_stats('ths', False, error_msg)
            return False, pd.DataFrame(), error_msg
    
    def _get_sina_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """获取新浪ETF数据
        @return: (成功标志, DataFrame, 错误信息)
        """
        try:
            print("[ETF数据] 尝试新浪API...")
            start_time = time.perf_counter()
            
            df = ak.fund_etf_category_sina(symbol="ETF基金")
            
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 新浪API成功，耗时: {elapsed:.2f}ms，数据行数: {len(df)}")
            
            # 标准化列名以匹配东财格式
            df = self._standardize_sina_columns(df)
            
            # 记录监控数据
            log_etf_api_request('sina', True, elapsed, data_count=len(df))
            
            self._update_api_stats('sina', True)
            return True, df, ""
            
        except Exception as e:
            error_msg = str(e)
            elapsed = (time.perf_counter() - start_time) * 1000
            print(f"[ETF数据] 新浪API失败: {error_msg}")
            
            # 记录监控数据
            log_etf_api_request('sina', False, elapsed, error_msg)
            
            self._update_api_stats('sina', False, error_msg)
            return False, pd.DataFrame(), error_msg
    
    def _standardize_ths_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化同花顺数据列名以匹配东财格式"""
        if df.empty:
            return df
        
        # 创建列名映射
        column_mapping = {
            '基金代码': '代码',
            '基金名称': '名称',
            '当前-单位净值': '最新价',
            '前一日-单位净值': '昨收',
            '增长值': '涨跌额',
            '增长率': '涨跌幅'
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 添加缺失的列（用NaN填充）
        required_columns = ['代码', '名称', '最新价', '昨收', '涨跌额', '涨跌幅']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        return df
    
    def _standardize_sina_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化新浪数据列名以匹配东财格式"""
        if df.empty:
            return df
        
        # 创建列名映射
        column_mapping = {
            '代码': '代码',
            '名称': '名称',
            '最新价': '最新价',
            '昨收': '昨收',
            '涨跌额': '涨跌额',
            '涨跌幅': '涨跌幅'
        }
        
        # 重命名列
        df = df.rename(columns=column_mapping)
        
        # 添加缺失的列（用NaN填充）
        required_columns = ['代码', '名称', '最新价', '昨收', '涨跌额', '涨跌幅']
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        return df
    
    def get_etf_spot_data(self, use_cache: bool = True) -> pd.DataFrame:
        """获取ETF实时行情数据，支持多API备用
        
        @param use_cache: 是否使用缓存
        @return: DataFrame，包含ETF实时行情数据
        """
        cache_key = "etf_spot_data"
        
        # 检查缓存
        if use_cache and self._is_cache_valid(cache_key):
            print("[ETF数据] 使用缓存数据")
            _, cached_data = self.cache[cache_key]
            return cached_data.copy()
        
        # API调用顺序：东财 -> 同花顺 -> 新浪
        apis = [
            ("eastmoney", self._get_eastmoney_data),
            ("ths", self._get_ths_data),
            ("sina", self._get_sina_data)
        ]
        
        last_error = ""
        
        for api_name, api_func in apis:
            success, df, error = api_func()
            
            if success and not df.empty:
                # 缓存成功的数据
                self.cache[cache_key] = (datetime.now(), df.copy())
                print(f"[ETF数据] 使用{api_name}API获取数据成功")
                return df
            else:
                last_error = error
                print(f"[ETF数据] {api_name}API失败，尝试下一个...")
        
        # 所有API都失败
        print(f"[ETF数据] 所有API都失败，最后错误: {last_error}")
        return pd.DataFrame()
    
    def get_etf_by_code(self, code: str, use_cache: bool = True) -> Optional[Dict]:
        """根据代码获取特定ETF数据
        
        @param code: ETF代码
        @param use_cache: 是否使用缓存
        @return: Dict，包含ETF数据，如果未找到返回None
        """
        df = self.get_etf_spot_data(use_cache=use_cache)
        
        if df.empty:
            return None
        
        # 查找指定代码的ETF
        etf_data = df[df['代码'] == code]
        
        if etf_data.empty:
            return None
        
        return etf_data.iloc[0].to_dict()
    
    def get_api_stats(self) -> Dict:
        """获取API统计信息
        @return: Dict，包含各API的成功/失败统计
        """
        return self.api_stats.copy()
    
    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        print("[ETF数据] 缓存已清除")
    
    def print_api_stats(self):
        """打印API统计信息"""
        print("\n[ETF数据] API统计信息:")
        print("-" * 50)
        
        for api_name, stats in self.api_stats.items():
            total = stats['success'] + stats['failed']
            success_rate = (stats['success'] / total * 100) if total > 0 else 0
            
            print(f"{api_name:>12}: 成功 {stats['success']:>3} 次, "
                  f"失败 {stats['failed']:>3} 次, "
                  f"成功率 {success_rate:>5.1f}%")
            
            if stats['last_error']:
                print(f"{'':>12}  最后错误: {stats['last_error']}")
        
        print("-" * 50)


# 创建全局单例实例
etf_fetcher = ETFDataFetcher()


def get_etf_spot_data(use_cache: bool = True) -> pd.DataFrame:
    """获取ETF实时行情数据（便捷函数）
    
    @param use_cache: 是否使用缓存
    @return: DataFrame，包含ETF实时行情数据
    """
    return etf_fetcher.get_etf_spot_data(use_cache=use_cache)


def get_etf_by_code(code: str, use_cache: bool = True) -> Optional[Dict]:
    """根据代码获取特定ETF数据（便捷函数）
    
    @param code: ETF代码
    @param use_cache: 是否使用缓存
    @return: Dict，包含ETF数据，如果未找到返回None
    """
    return etf_fetcher.get_etf_by_code(code, use_cache=use_cache)


def print_etf_api_stats():
    """打印ETF API统计信息（便捷函数）"""
    etf_fetcher.print_api_stats()


if __name__ == "__main__":
    # 测试代码
    print("测试ETF数据获取器...")
    
    # 获取所有ETF数据
    df = get_etf_spot_data()
    print(f"获取到 {len(df)} 条ETF数据")
    
    if not df.empty:
        print("\n前5条数据:")
        print(df.head())
    
    # 测试特定ETF
    test_code = "159919"  # 沪深300ETF
    etf_data = get_etf_by_code(test_code)
    if etf_data:
        print(f"\n{test_code} 数据:")
        for key, value in etf_data.items():
            print(f"  {key}: {value}")
    else:
        print(f"\n未找到 {test_code} 的数据")
    
    # 打印统计信息
    print_etf_api_stats()
