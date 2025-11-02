"""
ETF数据获取器 - 独立版本（不依赖akshare）
演示多API备用机制的概念和实现
"""

import random
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd


class MockETFDataFetcher:
    """ETF数据获取器模拟版本，用于演示多API备用机制"""
    
    def __init__(self):
        self.api_stats = {
            'eastmoney': {'success': 0, 'failed': 0, 'last_error': None},
            'ths': {'success': 0, 'failed': 0, 'last_error': None},
            'sina': {'success': 0, 'failed': 0, 'last_error': None}
        }
        self.cache = {}
        self.cache_timeout = 300  # 5分钟缓存
        
        # 模拟ETF数据
        self.mock_etf_data = pd.DataFrame({
            '代码': ['159919', '510300', '512880', '159915', '510500'],
            '名称': ['沪深300ETF', '沪深300ETF', '证券ETF', '创业板ETF', '中证500ETF'],
            '最新价': [4.5, 3.2, 1.8, 2.1, 6.7],
            'IOPV实时估值': [4.48, 3.19, 1.82, 2.09, 6.65],
            '基金折价率': [0.45, 0.31, -1.10, 0.48, 0.75],
            '涨跌额': [0.1, 0.05, -0.02, 0.08, 0.15],
            '涨跌幅': [2.27, 1.59, -1.10, 3.96, 2.29],
            '成交量': [1000000, 2000000, 500000, 800000, 1200000],
            '成交额': [4500000, 6400000, 900000, 1680000, 8040000],
            '开盘价': [4.4, 3.15, 1.82, 2.02, 6.55],
            '最高价': [4.52, 3.25, 1.85, 2.15, 6.75],
            '最低价': [4.38, 3.18, 1.78, 2.05, 6.60],
            '昨收': [4.4, 3.15, 1.82, 2.02, 6.55]
        })
    
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
    
    def _simulate_api_call(self, api_name: str, success_rate: float = 0.8) -> Tuple[bool, str]:
        """模拟API调用
        @param api_name: API名称
        @param success_rate: 成功率
        @return: (是否成功, 错误信息)
        """
        # 模拟网络延迟
        time.sleep(random.uniform(0.1, 0.5))
        
        # 模拟API成功率
        if random.random() < success_rate:
            return True, ""
        else:
            error_messages = {
                'eastmoney': 'Connection timeout',
                'ths': 'API rate limit exceeded', 
                'sina': 'Server internal error'
            }
            return False, error_messages.get(api_name, 'Unknown error')
    
    def _get_eastmoney_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """模拟获取东财ETF数据"""
        try:
            print("[ETF数据] 尝试东财API...")
            start_time = time.perf_counter()
            
            # 模拟API调用
            success, error_msg = self._simulate_api_call('eastmoney', 0.7)  # 70%成功率
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            if success:
                print(f"[ETF数据] 东财API成功，耗时: {elapsed:.2f}ms，数据行数: {len(self.mock_etf_data)}")
                self._update_api_stats('eastmoney', True)
                return True, self.mock_etf_data.copy(), ""
            else:
                print(f"[ETF数据] 东财API失败: {error_msg}")
                self._update_api_stats('eastmoney', False, error_msg)
                return False, pd.DataFrame(), error_msg
                
        except Exception as e:
            error_msg = str(e)
            print(f"[ETF数据] 东财API异常: {error_msg}")
            self._update_api_stats('eastmoney', False, error_msg)
            return False, pd.DataFrame(), error_msg
    
    def _get_ths_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """模拟获取同花顺ETF数据"""
        try:
            print("[ETF数据] 尝试同花顺API...")
            start_time = time.perf_counter()
            
            # 模拟API调用
            success, error_msg = self._simulate_api_call('ths', 0.6)  # 60%成功率
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            if success:
                print(f"[ETF数据] 同花顺API成功，耗时: {elapsed:.2f}ms，数据行数: {len(self.mock_etf_data)}")
                
                # 模拟数据格式转换
                df = self.mock_etf_data.copy()
                df = self._standardize_ths_columns(df)
                
                self._update_api_stats('ths', True)
                return True, df, ""
            else:
                print(f"[ETF数据] 同花顺API失败: {error_msg}")
                self._update_api_stats('ths', False, error_msg)
                return False, pd.DataFrame(), error_msg
                
        except Exception as e:
            error_msg = str(e)
            print(f"[ETF数据] 同花顺API异常: {error_msg}")
            self._update_api_stats('ths', False, error_msg)
            return False, pd.DataFrame(), error_msg
    
    def _get_sina_data(self) -> Tuple[bool, pd.DataFrame, str]:
        """模拟获取新浪ETF数据"""
        try:
            print("[ETF数据] 尝试新浪API...")
            start_time = time.perf_counter()
            
            # 模拟API调用
            success, error_msg = self._simulate_api_call('sina', 0.9)  # 90%成功率
            
            elapsed = (time.perf_counter() - start_time) * 1000
            
            if success:
                print(f"[ETF数据] 新浪API成功，耗时: {elapsed:.2f}ms，数据行数: {len(self.mock_etf_data)}")
                
                # 模拟数据格式转换
                df = self.mock_etf_data.copy()
                df = self._standardize_sina_columns(df)
                
                self._update_api_stats('sina', True)
                return True, df, ""
            else:
                print(f"[ETF数据] 新浪API失败: {error_msg}")
                self._update_api_stats('sina', False, error_msg)
                return False, pd.DataFrame(), error_msg
                
        except Exception as e:
            error_msg = str(e)
            print(f"[ETF数据] 新浪API异常: {error_msg}")
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
mock_etf_fetcher = MockETFDataFetcher()


def get_etf_spot_data(use_cache: bool = True) -> pd.DataFrame:
    """获取ETF实时行情数据（便捷函数）
    
    @param use_cache: 是否使用缓存
    @return: DataFrame，包含ETF实时行情数据
    """
    return mock_etf_fetcher.get_etf_spot_data(use_cache=use_cache)


def get_etf_by_code(code: str, use_cache: bool = True) -> Optional[Dict]:
    """根据代码获取特定ETF数据（便捷函数）
    
    @param code: ETF代码
    @param use_cache: 是否使用缓存
    @return: Dict，包含ETF数据，如果未找到返回None
    """
    return mock_etf_fetcher.get_etf_by_code(code, use_cache=use_cache)


def print_etf_api_stats():
    """打印ETF API统计信息（便捷函数）"""
    mock_etf_fetcher.print_api_stats()


if __name__ == "__main__":
    # 测试代码
    print("测试ETF数据获取器（模拟版本）...")
    
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
