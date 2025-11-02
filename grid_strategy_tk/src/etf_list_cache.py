"""
ETF列表缓存管理器
用于缓存ETF列表数据，避免频繁调用API
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import akshare as ak
import pandas as pd


class ETFListCache:
    """ETF列表缓存管理器"""
    
    def __init__(self, cache_file: str = "config/etf_list_cache.json"):
        self.cache_file = cache_file
        self.cache_timeout = 24 * 60 * 60  # 24小时缓存有效期
        self.etf_list_cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """加载缓存数据"""
        default_cache = {
            "version": "v1.3.0",
            "timestamp": 0,
            "etf_list": [],
            "etf_159_list": []
        }
        
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    # 检查缓存版本
                    if cache_data.get("version") == default_cache["version"]:
                        return cache_data
                    else:
                        print("ETF列表缓存版本不匹配，将重新获取")
                        return default_cache
        except Exception as e:
            print(f"加载ETF列表缓存失败: {str(e)}")
        
        return default_cache
    
    def _save_cache(self, etf_list: pd.DataFrame, etf_159_list: pd.DataFrame):
        """保存缓存数据"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            
            # 转换为可序列化的格式
            etf_list_data = etf_list.to_dict('records') if not etf_list.empty else []
            etf_159_list_data = etf_159_list.to_dict('records') if not etf_159_list.empty else []
            
            cache_data = {
                "version": "v1.3.0",
                "timestamp": time.time(),
                "etf_list": etf_list_data,
                "etf_159_list": etf_159_list_data
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            print(f"ETF列表缓存已保存: {len(etf_list_data)}个ETF, {len(etf_159_list_data)}个159ETF")
            
        except Exception as e:
            print(f"保存ETF列表缓存失败: {str(e)}")
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.etf_list_cache:
            return False
        
        # 检查是否有数据（空列表也算有效，表示已清空）
        etf_list = self.etf_list_cache.get("etf_list", [])
        if etf_list is None:
            return False
        
        cache_time = self.etf_list_cache.get("timestamp", 0)
        current_time = time.time()
        
        # 如果缓存被清空（timestamp为0），则无效
        if cache_time == 0:
            return False
        
        # 检查是否超过缓存有效期
        if current_time - cache_time > self.cache_timeout:
            print(f"ETF列表缓存已过期: {current_time - cache_time:.0f}秒前")
            return False
        
        return True
    
    def _dataframe_from_cache(self, data: List[Dict]) -> pd.DataFrame:
        """从缓存数据创建DataFrame"""
        if not data:
            return pd.DataFrame()
        
        try:
            df = pd.DataFrame(data)
            # 保持代码作为列，不设置为索引，以便后续访问
            return df
        except Exception as e:
            print(f"从缓存创建DataFrame失败: {str(e)}")
            return pd.DataFrame()
    
    def get_etf_list_optimized(self, force_refresh: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        获取优化的ETF列表数据（只包含必要字段）
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (所有ETF列表, 159开头的ETF列表)
        """
        # 检查缓存是否有效
        if not force_refresh and self._is_cache_valid():
            print("使用优化的ETF列表缓存数据")
            etf_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_list", []))
            etf_159_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_159_list", []))
            return etf_list, etf_159_list
        
        # 缓存无效或强制刷新，重新获取数据
        print("重新获取ETF列表数据...")
        try:
            # 获取所有ETF
            etf_list = ak.fund_etf_spot_em()
            
            if etf_list.empty:
                print("获取ETF列表失败，返回空数据")
                return pd.DataFrame(), pd.DataFrame()
            
            # 筛选159开头的ETF
            etf_159 = etf_list[etf_list['代码'].str.startswith('159')]
            
            # 只保留代码和名称字段，价格数据由趋势缓存管理
            display_columns = ['代码', '名称']
            etf_list_optimized = etf_list[display_columns].copy() if all(col in etf_list.columns for col in display_columns) else etf_list
            etf_159_optimized = etf_159[display_columns].copy() if all(col in etf_159.columns for col in display_columns) else etf_159
            
            print(f"成功获取ETF数据: 总计{len(etf_list_optimized)}个ETF, 159开头{len(etf_159_optimized)}个")
            
            # 保存到缓存
            self._save_cache(etf_list_optimized, etf_159_optimized)
            
            return etf_list_optimized, etf_159_optimized
            
        except Exception as e:
            print(f"获取ETF列表失败: {str(e)}")
            
            # 如果获取失败，尝试使用缓存数据（即使过期）
            etf_list_data = self.etf_list_cache.get("etf_list", [])
            if etf_list_data and len(etf_list_data) > 0:
                print("使用过期缓存数据作为备用")
                etf_list = self._dataframe_from_cache(etf_list_data)
                etf_159_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_159_list", []))
                return etf_list, etf_159_list
            
            print("无可用缓存数据，返回空DataFrame")
            return pd.DataFrame(), pd.DataFrame()
    
    def get_etf_list(self, force_refresh: bool = False) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        获取ETF列表数据
        
        Args:
            force_refresh: 是否强制刷新缓存
            
        Returns:
            Tuple[pd.DataFrame, pd.DataFrame]: (所有ETF列表, 159开头的ETF列表)
        """
        # 检查缓存是否有效
        if not force_refresh and self._is_cache_valid():
            print("使用ETF列表缓存数据")
            etf_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_list", []))
            etf_159_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_159_list", []))
            return etf_list, etf_159_list
        
        # 缓存无效或强制刷新，重新获取数据
        print("重新获取ETF列表数据...")
        try:
            # 获取所有ETF
            etf_list = ak.fund_etf_spot_em()
            
            if etf_list.empty:
                print("获取ETF列表失败，返回空数据")
                return pd.DataFrame(), pd.DataFrame()
            
            # 筛选159开头的ETF
            etf_159 = etf_list[etf_list['代码'].str.startswith('159')]
            
            print(f"成功获取ETF数据: 总计{len(etf_list)}个ETF, 159开头{len(etf_159)}个")
            
            # 保存到缓存
            self._save_cache(etf_list, etf_159)
            
            return etf_list, etf_159
            
        except Exception as e:
            print(f"获取ETF列表失败: {str(e)}")
            
            # 如果获取失败，尝试使用缓存数据（即使过期）
            etf_list_data = self.etf_list_cache.get("etf_list", [])
            if etf_list_data and len(etf_list_data) > 0:
                print("使用过期缓存数据作为备用")
                etf_list = self._dataframe_from_cache(etf_list_data)
                etf_159_list = self._dataframe_from_cache(self.etf_list_cache.get("etf_159_list", []))
                return etf_list, etf_159
            
            print("无可用缓存数据，返回空DataFrame")
            return pd.DataFrame(), pd.DataFrame()
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        if not self.etf_list_cache:
            return {"status": "no_cache", "message": "无缓存数据"}
        
        cache_time = self.etf_list_cache.get("timestamp", 0)
        if cache_time == 0:
            return {"status": "no_cache", "message": "无缓存数据"}
        
        current_time = time.time()
        age_seconds = current_time - cache_time
        age_hours = age_seconds / 3600
        
        etf_count = len(self.etf_list_cache.get("etf_list", []))
        etf_159_count = len(self.etf_list_cache.get("etf_159_list", []))
        
        return {
            "status": "cached",
            "cache_time": datetime.fromtimestamp(cache_time).strftime("%Y-%m-%d %H:%M:%S"),
            "age_hours": round(age_hours, 2),
            "etf_count": etf_count,
            "etf_159_count": etf_159_count,
            "is_valid": self._is_cache_valid()
        }
    
    def clear_cache(self):
        """清除缓存"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            self.etf_list_cache = {
                "version": "v1.3.0",
                "timestamp": 0,
                "etf_list": [],
                "etf_159_list": []
            }
            print("ETF列表缓存已清除")
        except Exception as e:
            print(f"清除ETF列表缓存失败: {str(e)}")


# 全局缓存实例
_etf_list_cache = None

def get_etf_list_cache() -> ETFListCache:
    """获取全局ETF列表缓存实例"""
    global _etf_list_cache
    if _etf_list_cache is None:
        _etf_list_cache = ETFListCache()
    return _etf_list_cache
