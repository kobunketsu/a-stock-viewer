"""
龙虎榜数据处理模块
负责获取和缓存龙虎榜机构买卖数据
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# 兼容两种导入路径
akshare_wrapper = None
ak_available = False
try:
    from akshare_wrapper import AKShareWrapper  # 直接位于 sys.path 根目录时
    akshare_wrapper = AKShareWrapper()
    ak_available = True
except Exception:
    try:
        from src.akshare_wrapper import AKShareWrapper  # 位于 src 包目录下时
        akshare_wrapper = AKShareWrapper()
        ak_available = True
    except Exception:
        akshare_wrapper = None
        ak_available = False
        logging.warning("akshare不可用，龙虎榜功能将不可用")


@dataclass
class LhbRecord:
    """龙虎榜记录数据类"""
    date: str
    code: str
    name: str
    close_price: float
    change_pct: float
    # 机构数据
    institution_buy_count: float
    institution_sell_count: float
    institution_buy_amount: float
    institution_sell_amount: float
    institution_net_amount: float
    institution_net_ratio: float  # 机构净买入占比
    # 游资数据
    hot_buy_count: float
    hot_sell_count: float
    hot_buy_amount: float
    hot_sell_amount: float
    hot_net_amount: float
    hot_net_ratio: float  # 游资净买入占比
    # 散户数据
    retail_buy_count: float
    retail_sell_count: float
    retail_buy_amount: float
    retail_sell_amount: float
    retail_net_amount: float
    retail_net_ratio: float  # 散户净买入占比
    # 营业部总数据（兼容旧接口）
    broker_buy_count: float
    broker_sell_count: float
    broker_buy_amount: float
    broker_sell_amount: float
    broker_net_amount: float
    broker_net_ratio: float  # 营业部净买入占比
    # 其他数据
    total_amount: float
    net_buy_ratio: float  # 主要判断依据的净买入占比
    turnover_rate: float
    market_cap: float
    reason: str
    signal_type: str  # "机构" 或 "营业部"，表示主要判断依据


class LhbDataProcessor:
    """龙虎榜数据处理器"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, LhbRecord]] = {}  # {date: {code: record}}
        self._cache_expiry = 3600  # 缓存1小时
        self._last_update: Dict[str, float] = {}  # 记录每个日期的最后更新时间
        # 资金来源缓存：(code, date) -> {amounts}
        self._fund_cache: Dict[tuple[str, str], Dict[str, float]] = {}
        
    def get_lhb_data_for_period(self, start_date: str, end_date: str) -> Dict[str, Dict[str, LhbRecord]]:
        """
        获取指定时间段的龙虎榜数据
        
        Args:
            start_date: 开始日期 "YYYYMMDD"
            end_date: 结束日期 "YYYYMMDD"
            
        Returns:
            {date: {code: LhbRecord}} 格式的数据
        """
        if not ak_available:
            logging.warning("akshare不可用，无法获取龙虎榜数据")
            return {}
            
        result = {}
        
        # 生成日期列表
        start_dt = datetime.strptime(start_date, "%Y%m%d")
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        current_dt = start_dt
        
        while current_dt <= end_dt:
            date_str = current_dt.strftime("%Y%m%d")
            
            # 检查缓存
            if self._is_cache_valid(date_str):
                if date_str in self._cache:
                    result[date_str] = self._cache[date_str]
            else:
                # 获取新数据
                date_data = self._fetch_lhb_data_for_date(date_str)
                if date_data:
                    self._cache[date_str] = date_data
                    self._last_update[date_str] = time.time()
                    result[date_str] = date_data
                    
            current_dt += timedelta(days=1)
            
        return result
    
    def _is_cache_valid(self, date_str: str) -> bool:
        """检查缓存是否有效"""
        if date_str not in self._last_update:
            return False
        return time.time() - self._last_update[date_str] < self._cache_expiry
    
    def _fetch_lhb_data_for_date(self, date_str: str) -> Dict[str, LhbRecord]:
        """
        获取指定日期的龙虎榜机构买卖数据
        
        Args:
            date_str: 日期字符串 "YYYYMMDD"
            
        Returns:
            {code: LhbRecord} 格式的数据
        """
        try:
            if not ak_available or akshare_wrapper is None:
                return {}
            
            # 使用akshare获取机构买卖每日统计数据
            df = akshare_wrapper.stock_lhb_jgmmtj_em(start_date=date_str, end_date=date_str)
            
            if df.empty:
                return {}
                
            records = {}
            for _, row in df.iterrows():
                code = row['代码']
                record = LhbRecord(
                    date=date_str,
                    code=code,
                    name=row['名称'],
                    close_price=float(row['收盘价']) if pd.notna(row['收盘价']) else 0.0,
                    change_pct=float(row['涨跌幅']) if pd.notna(row['涨跌幅']) else 0.0,
                    institution_buy_count=float(row['买方机构数']) if pd.notna(row['买方机构数']) else 0.0,
                    institution_sell_count=float(row['卖方机构数']) if pd.notna(row['卖方机构数']) else 0.0,
                    institution_buy_amount=float(row['机构买入总额']) if pd.notna(row['机构买入总额']) else 0.0,
                    institution_sell_amount=float(row['机构卖出总额']) if pd.notna(row['机构卖出总额']) else 0.0,
                    institution_net_amount=float(row['机构买入净额']) if pd.notna(row['机构买入净额']) else 0.0,
                    total_amount=float(row['市场总成交额']) if pd.notna(row['市场总成交额']) else 0.0,
                    net_buy_ratio=float(row['机构净买额占总成交额比']) if pd.notna(row['机构净买额占总成交额比']) else 0.0,
                    turnover_rate=float(row['换手率']) if pd.notna(row['换手率']) else 0.0,
                    market_cap=float(row['流通市值']) if pd.notna(row['流通市值']) else 0.0,
                    reason=str(row['上榜原因']) if pd.notna(row['上榜原因']) else ""
                )
                records[code] = record
                
            logging.info(f"获取{date_str}龙虎榜数据成功，共{len(records)}条记录")
            return records
            
        except Exception as e:
            logging.error(f"获取{date_str}龙虎榜数据失败: {str(e)}")
            return {}
    
    def get_institution_buy_signal(self, code: str, date: str) -> Optional[LhbRecord]:
        """
        检查指定股票在指定日期是否有机构买入信号
        
        Args:
            code: 股票代码
            date: 日期 "YYYYMMDD"
            
        Returns:
            如果有机构买入则返回LhbRecord，否则返回None
        """
        try:
            if not ak_available or akshare_wrapper is None:
                return None
            
            # 直接获取该股票的买入详情
            buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="买入")
            
            # 检查返回的数据是否为None，如果是则初始化为空DataFrame
            if buy_df is None:
                buy_df = pd.DataFrame()
            
            if buy_df.empty:
                return None
            
            # 计算买入总额和机构数量
            buy_amount = buy_df['买入金额'].sum() if '买入金额' in buy_df.columns else 0.0
            buy_count = len(buy_df) if not buy_df.empty else 0
            
            # 获取卖出详情用于计算净额
            sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="卖出")
            
            # 检查返回的数据是否为None，如果是则初始化为空DataFrame
            if sell_df is None:
                sell_df = pd.DataFrame()
                
            sell_amount = sell_df['卖出金额'].sum() if '卖出金额' in sell_df.columns else 0.0
            sell_count = len(sell_df) if not sell_df.empty else 0
            
            # 计算净额
            net_amount = buy_amount - sell_amount
            
            # 只有净买入为正时才算买入信号
            if net_amount > 0:
                # 获取股票基本信息（这里需要从其他接口获取，暂时使用默认值）
                return LhbRecord(
                    date=date,
                    code=code,
                    name="",  # 需要从其他接口获取
                    close_price=0.0,
                    change_pct=0.0,
                    institution_buy_count=float(buy_count),
                    institution_sell_count=float(sell_count),
                    institution_buy_amount=buy_amount,
                    institution_sell_amount=sell_amount,
                    institution_net_amount=net_amount,
                    total_amount=0.0,  # 需要从其他接口获取
                    net_buy_ratio=0.0,  # 需要计算
                    turnover_rate=0.0,
                    market_cap=0.0,
                    reason="机构买入"
                )
                
        except Exception as e:
            logging.error(f"获取机构买入信号失败 {code} {date}: {str(e)}")
            
        return None
    
    def get_institution_sell_signal(self, code: str, date: str) -> Optional[LhbRecord]:
        """
        检查指定股票在指定日期是否有机构卖出信号
        
        Args:
            code: 股票代码
            date: 日期 "YYYYMMDD"
            
        Returns:
            如果有机构卖出则返回LhbRecord，否则返回None
        """
        try:
            if not ak_available or akshare_wrapper is None:
                return None
            
            # 直接获取该股票的卖出详情
            sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="卖出")
            
            # 检查返回的数据是否为None，如果是则初始化为空DataFrame
            if sell_df is None:
                sell_df = pd.DataFrame()
            
            if sell_df.empty:
                return None
            
            # 计算卖出总额和机构数量
            sell_amount = sell_df['卖出金额'].sum() if '卖出金额' in sell_df.columns else 0.0
            sell_count = len(sell_df) if not sell_df.empty else 0
            
            # 获取买入详情用于计算净额
            buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="买入")
            
            # 检查返回的数据是否为None，如果是则初始化为空DataFrame
            if buy_df is None:
                buy_df = pd.DataFrame()
                
            buy_amount = buy_df['买入金额'].sum() if '买入金额' in buy_df.columns else 0.0
            buy_count = len(buy_df) if not buy_df.empty else 0
            
            # 计算净额
            net_amount = buy_amount - sell_amount
            
            # 只有净买入为负时才算卖出信号
            if net_amount < 0:
                return LhbRecord(
                    date=date,
                    code=code,
                    name="",  # 需要从其他接口获取
                    close_price=0.0,
                    change_pct=0.0,
                    institution_buy_count=float(buy_count),
                    institution_sell_count=float(sell_count),
                    institution_buy_amount=buy_amount,
                    institution_sell_amount=sell_amount,
                    institution_net_amount=net_amount,
                    total_amount=0.0,  # 需要从其他接口获取
                    net_buy_ratio=0.0,  # 需要计算
                    turnover_rate=0.0,
                    market_cap=0.0,
                    reason="机构卖出"
                )
                
        except Exception as e:
            logging.error(f"获取机构卖出信号失败 {code} {date}: {str(e)}")
            
        return None
    
    def get_institution_signal(self, code: str, date: str) -> Optional[LhbRecord]:
        """
        检查指定股票在指定日期是否有机构买卖信号
        
        Args:
            code: 股票代码
            date: 日期 "YYYYMMDD"
            
        Returns:
            如果有机构买卖信号则返回LhbRecord，否则返回None
        """
        try:
            if not ak_available or akshare_wrapper is None:
                return None
            
            # 1/2. 获取数据，失败时兜底为空字典，避免None下标错误
            institution_data = self._get_institution_data(code, date) or {}
            broker_data = self._get_broker_data(code, date) or {}
            
            # 3. 合并机构数据（统计机构 + 营业部机构）
            # 从统计接口获取的机构数据
            stat_institution_net = float(institution_data.get('net_amount', 0))
            # 从营业部解析的机构数据（包括沪深股通）
            broker_institution_net = float(broker_data.get('institution_net_amount', 0))
            # 合并后的机构净额
            total_institution_net = stat_institution_net + broker_institution_net
            
            # 判断信号类型和主要依据
            if total_institution_net != 0:
                # 有机构数据（统计+营业部机构）
                signal_type = "机构"
                net_amount = total_institution_net
                # 合并机构买卖数据
                buy_amount = float(institution_data.get('buy_amount', 0)) + float(broker_data.get('institution_buy_amount', 0))
                sell_amount = float(institution_data.get('sell_amount', 0)) + float(broker_data.get('institution_sell_amount', 0))
                buy_count = float(institution_data.get('buy_count', 0)) + float(broker_data.get('institution_buy_count', 0))
                sell_count = float(institution_data.get('sell_count', 0)) + float(broker_data.get('institution_sell_count', 0))
                # 计算合并后的占比
                total_volume = max(buy_amount + sell_amount, 1) * 2
                net_ratio = (net_amount / total_volume * 100) if total_volume > 0 else 0.0
                
                if net_amount > 0:
                    reason = "机构买入"
                else:
                    reason = "机构卖出"
                    
            elif broker_data and float(broker_data.get('net_amount', 0)) != 0:
                # 没有机构数据，使用营业部总数据
                signal_type = "营业部"
                net_amount = broker_data['net_amount']
                net_ratio = broker_data['net_ratio']
                buy_count = broker_data['buy_count']
                sell_count = broker_data['sell_count']
                buy_amount = broker_data['buy_amount']
                sell_amount = broker_data['sell_amount']
                
                if net_amount > 0:
                    reason = "营业部买入"
                else:
                    reason = "营业部卖出"
            else:
                # 都没有数据
                return None
            
            # 4. 构建LhbRecord
            return LhbRecord(
                date=date,
                code=code,
                name="",  # 需要从其他接口获取
                close_price=0.0,
                change_pct=0.0,
                # 机构数据（合并统计机构 + 营业部机构，包括沪深股通）
                institution_buy_count=buy_count,
                institution_sell_count=sell_count,
                institution_buy_amount=buy_amount,
                institution_sell_amount=sell_amount,
                institution_net_amount=total_institution_net,
                institution_net_ratio=net_ratio,
                # 游资数据
                hot_buy_count=float(broker_data.get('hot_buy_count', 0.0)),
                hot_sell_count=float(broker_data.get('hot_sell_count', 0.0)),
                hot_buy_amount=float(broker_data.get('hot_buy_amount', 0.0)),
                hot_sell_amount=float(broker_data.get('hot_sell_amount', 0.0)),
                hot_net_amount=float(broker_data.get('hot_net_amount', 0.0)),
                hot_net_ratio=float(broker_data.get('hot_net_ratio', 0.0)),
                # 散户数据
                retail_buy_count=float(broker_data.get('retail_buy_count', 0.0)),
                retail_sell_count=float(broker_data.get('retail_sell_count', 0.0)),
                retail_buy_amount=float(broker_data.get('retail_buy_amount', 0.0)),
                retail_sell_amount=float(broker_data.get('retail_sell_amount', 0.0)),
                retail_net_amount=float(broker_data.get('retail_net_amount', 0.0)),
                retail_net_ratio=float(broker_data.get('retail_net_ratio', 0.0)),
                # 营业部总数据（兼容旧接口）
                broker_buy_count=float(broker_data.get('buy_count', 0.0)),
                broker_sell_count=float(broker_data.get('sell_count', 0.0)),
                broker_buy_amount=float(broker_data.get('buy_amount', 0.0)),
                broker_sell_amount=float(broker_data.get('sell_amount', 0.0)),
                broker_net_amount=float(broker_data.get('net_amount', 0.0)),
                broker_net_ratio=float(broker_data.get('net_ratio', 0.0)),
                # 其他数据
                total_amount=0.0,  # 需要从其他接口获取
                net_buy_ratio=net_ratio,  # 主要判断依据的净买入占比
                turnover_rate=0.0,
                market_cap=0.0,
                reason=reason,
                signal_type=signal_type
            )
                
        except Exception as e:
            logging.error(f"获取机构买卖信号失败 {code} {date}: {str(e)}")
            
        return None
    
    def _get_institution_data(self, code: str, date: str) -> Optional[Dict]:
        """获取机构统计数据"""
        try:
            # 获取机构买卖每日统计数据
            df = akshare_wrapper.stock_lhb_jgmmtj_em(start_date=date, end_date=date)
            
            if df.empty:
                return None
            
            # 查找指定股票的数据
            stock_data = df[df['代码'] == code]
            if stock_data.empty:
                return None
            
            row = stock_data.iloc[0]
            
            # 提取机构数据
            buy_count = float(row['买方机构数']) if pd.notna(row['买方机构数']) else 0.0
            sell_count = float(row['卖方机构数']) if pd.notna(row['卖方机构数']) else 0.0
            buy_amount = float(row['机构买入总额']) if pd.notna(row['机构买入总额']) else 0.0
            sell_amount = float(row['机构卖出总额']) if pd.notna(row['机构卖出总额']) else 0.0
            net_amount = float(row['机构买入净额']) if pd.notna(row['机构买入净额']) else 0.0
            net_ratio = float(row['机构净买额占总成交额比']) if pd.notna(row['机构净买额占总成交额比']) else 0.0
            
            return {
                'buy_count': buy_count,
                'sell_count': sell_count,
                'buy_amount': buy_amount,
                'sell_amount': sell_amount,
                'net_amount': net_amount,
                'net_ratio': net_ratio
            }
            
        except Exception as e:
            logging.error(f"获取机构数据失败 {code} {date}: {str(e)}")
            return None
    
    def _get_broker_data(self, code: str, date: str) -> Optional[Dict]:
        """获取营业部详细数据，区分机构和散户"""
        try:
            # 获取买入和卖出详情
            buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="买入")
            sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=date, flag="卖出")
            
            # 检查返回的数据是否为None，如果是则初始化为空DataFrame
            if buy_df is None:
                buy_df = pd.DataFrame()
            if sell_df is None:
                sell_df = pd.DataFrame()
            
            # 区分游资和散户
            def is_retail_broker(broker_name: str) -> bool:
                """判断是否为散户营业部：名称包含"东方财富证券拉萨"视作散户营业部"""
                if not broker_name:
                    return False
                return "拉萨" in str(broker_name)
            
            # 分离机构、游资和散户数据
            if not buy_df.empty and '交易营业部名称' in buy_df.columns:
                # 根据营业部名称分类
                institution_buy_df = buy_df[buy_df['交易营业部名称'].apply(self._is_institution_broker)]
                retail_buy_df = buy_df[buy_df['交易营业部名称'].apply(is_retail_broker)]
                # 游资数据 = 非机构且非散户的营业部
                hot_buy_df = buy_df[~buy_df['交易营业部名称'].apply(self._is_institution_broker) & 
                                   ~buy_df['交易营业部名称'].apply(is_retail_broker)]
                
                institution_buy_amount = institution_buy_df['买入金额'].sum() if not institution_buy_df.empty else 0.0
                hot_buy_amount = hot_buy_df['买入金额'].sum() if not hot_buy_df.empty else 0.0
                retail_buy_amount = retail_buy_df['买入金额'].sum() if not retail_buy_df.empty else 0.0
                institution_buy_count = len(institution_buy_df)
                hot_buy_count = len(hot_buy_df)
                retail_buy_count = len(retail_buy_df)
            else:
                institution_buy_amount = 0.0
                hot_buy_amount = buy_df['买入金额'].sum() if '买入金额' in buy_df.columns else 0.0
                retail_buy_amount = 0.0
                institution_buy_count = 0
                hot_buy_count = len(buy_df) if not buy_df.empty else 0
                retail_buy_count = 0
            
            if not sell_df.empty and '交易营业部名称' in sell_df.columns:
                # 根据营业部名称分类
                institution_sell_df = sell_df[sell_df['交易营业部名称'].apply(self._is_institution_broker)]
                retail_sell_df = sell_df[sell_df['交易营业部名称'].apply(is_retail_broker)]
                # 游资数据 = 非机构且非散户的营业部
                hot_sell_df = sell_df[~sell_df['交易营业部名称'].apply(self._is_institution_broker) & 
                                     ~sell_df['交易营业部名称'].apply(is_retail_broker)]
                
                # 注意：卖出数据中买入金额字段实际上是卖出金额（负值）
                institution_sell_amount = institution_sell_df['买入金额'].sum() if not institution_sell_df.empty else 0.0
                hot_sell_amount = hot_sell_df['买入金额'].sum() if not hot_sell_df.empty else 0.0
                retail_sell_amount = retail_sell_df['买入金额'].sum() if not retail_sell_df.empty else 0.0
                institution_sell_count = len(institution_sell_df)
                hot_sell_count = len(hot_sell_df)
                retail_sell_count = len(retail_sell_df)
            else:
                institution_sell_amount = 0.0
                hot_sell_amount = sell_df['买入金额'].sum() if '买入金额' in sell_df.columns else 0.0
                retail_sell_amount = 0.0
                institution_sell_count = 0
                hot_sell_count = len(sell_df) if not sell_df.empty else 0
                retail_sell_count = 0
            
            # 计算各类资金净额
            institution_net_amount = institution_buy_amount - institution_sell_amount
            hot_net_amount = hot_buy_amount - hot_sell_amount
            retail_net_amount = retail_buy_amount - retail_sell_amount
            
            # 总净额 = 机构净额 + 游资净额 - 散户净额（散户作为反向指标）
            total_net_amount = institution_net_amount + hot_net_amount - retail_net_amount
            
            # 计算占比（使用总成交额估算）
            total_volume = max(institution_buy_amount + institution_sell_amount + hot_buy_amount + hot_sell_amount + retail_buy_amount + retail_sell_amount, 1) * 2
            institution_net_ratio = (institution_net_amount / total_volume * 100) if total_volume > 0 else 0.0
            hot_net_ratio = (hot_net_amount / total_volume * 100) if total_volume > 0 else 0.0
            retail_net_ratio = (retail_net_amount / total_volume * 100) if total_volume > 0 else 0.0
            total_net_ratio = (total_net_amount / total_volume * 100) if total_volume > 0 else 0.0
            
            return {
                # 机构数据（包含沪深股通）
                'institution_buy_count': float(institution_buy_count),
                'institution_sell_count': float(institution_sell_count),
                'institution_buy_amount': institution_buy_amount,
                'institution_sell_amount': institution_sell_amount,
                'institution_net_amount': institution_net_amount,
                'institution_net_ratio': institution_net_ratio,
                # 游资数据
                'hot_buy_count': float(hot_buy_count),
                'hot_sell_count': float(hot_sell_count),
                'hot_buy_amount': hot_buy_amount,
                'hot_sell_amount': hot_sell_amount,
                'hot_net_amount': hot_net_amount,
                'hot_net_ratio': hot_net_ratio,
                # 散户数据
                'retail_buy_count': float(retail_buy_count),
                'retail_sell_count': float(retail_sell_count),
                'retail_buy_amount': retail_buy_amount,
                'retail_sell_amount': retail_sell_amount,
                'retail_net_amount': retail_net_amount,
                'retail_net_ratio': retail_net_ratio,
                # 总数据（用于兼容旧接口）
                'buy_count': float(institution_buy_count + hot_buy_count + retail_buy_count),
                'sell_count': float(institution_sell_count + hot_sell_count + retail_sell_count),
                'buy_amount': institution_buy_amount + hot_buy_amount + retail_buy_amount,
                'sell_amount': institution_sell_amount + hot_sell_amount + retail_sell_amount,
                'net_amount': total_net_amount,
                'net_ratio': total_net_ratio
            }
            
        except Exception as e:
            logging.error(f"获取营业部数据失败 {code} {date}: {str(e)}")
            return None
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        self._last_update.clear()
        logging.info("龙虎榜数据缓存已清空")

    def get_fund_source_series(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取指定区间内三类资金(机构/游资/散户)的净买卖金额时间序列。
        返回列：['institution_net_amount', 'hot_net_amount', 'retail_net_amount']
        索引：DatetimeIndex (yyyy-mm-dd)
        入参日期可为 'YYYYMMDD' 或 'YYYY-MM-DD'，内部统一处理。
        """
        try:
            if not ak_available or akshare_wrapper is None:
                return pd.DataFrame()

            def normalize(d: str) -> str:
                d = str(d)
                return d.replace('-', '')[:8]

            s = normalize(start_date)
            e = normalize(end_date)
            if s > e:
                s, e = e, s

            # 优先获取该标的有龙虎榜数据的日期列表，减少无效请求
            dates_df = akshare_wrapper.stock_lhb_stock_detail_date_em(symbol=code)
            date_list: list[str] = []
            if dates_df is not None and not dates_df.empty:
                # 常见列名有 ['日期'] 或 ['交易日']，若都不匹配则尝试自动识别日期列
                if '日期' in dates_df.columns:
                    date_series = dates_df['日期']
                elif '交易日' in dates_df.columns:
                    date_series = dates_df['交易日']
                else:
                    # 自动识别：挑选能被 to_datetime 转换的列作为日期列
                    date_series = None
                    for col in dates_df.columns:
                        try:
                            parsed = pd.to_datetime(dates_df[col], errors='coerce')
                            if parsed.notna().sum() >= max(3, len(dates_df) // 2):
                                date_series = dates_df[col]
                                break
                        except Exception:
                            continue
                    if date_series is None:
                        # 兜底：直接返回空
                        return pd.DataFrame(columns=[
                            'institution_net_amount', 'hot_net_amount', 'retail_net_amount'
                        ])
                for v in date_series:
                    ds = normalize(str(v))
                    if s <= ds <= e:
                        date_list.append(ds)

            # 若无日期列表，兜底为空
            if not date_list:
                return pd.DataFrame(columns=[
                    'institution_net_amount', 'hot_net_amount', 'retail_net_amount'
                ])

            rows: list[dict[str, float | str]] = []
            for ds in sorted(set(date_list)):
                cache_key = (code, ds)
                cached = self._fund_cache.get(cache_key)
                if cached is None:
                    # 获取机构与营业部(游资/散户)数据
                    inst = self._get_institution_data(code, ds) or {}
                    broker = self._get_broker_data(code, ds) or {}

                    # 合并机构数据：统计机构 + 营业部机构（包括沪深股通）
                    stat_institution_net = float(inst.get('net_amount', 0.0))
                    broker_institution_net = float(broker.get('institution_net_amount', 0.0))
                    total_institution_net = stat_institution_net + broker_institution_net
                    
                    result = {
                        'institution_net_amount': total_institution_net,
                        'hot_net_amount': float(broker.get('hot_net_amount', 0.0)),
                        'retail_net_amount': float(broker.get('retail_net_amount', 0.0)),
                    }
                    self._fund_cache[cache_key] = result
                else:
                    result = cached

                rows.append({
                    'date': ds,
                    **result
                })

            if not rows:
                return pd.DataFrame(columns=[
                    'institution_net_amount', 'hot_net_amount', 'retail_net_amount'
                ])

            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
            df = df.set_index('date').sort_index()

            # 基于每日平均价格将净额转换为净股数（修正：使用每日股价而不是时间范围平均股价）
            try:
                ohlc = akshare_wrapper.stock_zh_a_hist(symbol=code, period='daily', start_date=s, end_date=e, adjust='')
                if ohlc is not None and not ohlc.empty:
                    if '日期' in ohlc.columns:
                        ohlc['日期'] = pd.to_datetime(ohlc['日期'])
                        ohlc = ohlc.set_index('日期')
                    
                    # 为每个日期计算当日平均股价
                    daily_prices = {}
                    for date in ohlc.index:
                        date_str = date.strftime('%Y%m%d')
                        row = ohlc.loc[date]
                        
                        # 优先使用成交额/成交量计算当日均价
                        daily_price = None
                        if '成交额' in row and '成交量' in row:
                            vol = float(row['成交量'])
                            amt = float(row['成交额'])
                            if vol > 0 and amt > 0:
                                daily_price = amt / vol
                                if daily_price > 0 and daily_price < 1000:  # 过滤异常价格
                                    daily_prices[date_str] = daily_price
                        
                        # 回退：使用OHLC均价
                        if daily_price is None or daily_price <= 0 or daily_price >= 1000:
                            ohlc_cols = ['开盘', '收盘', '最高', '最低']
                            if all(col in row for col in ohlc_cols):
                                daily_avg = sum(float(row[col]) for col in ohlc_cols) / len(ohlc_cols)
                                if daily_avg > 0 and daily_avg < 1000:
                                    daily_prices[date_str] = daily_avg
                        
                        # 最后回退：使用收盘价
                        if date_str not in daily_prices and '收盘' in row:
                            close_price = float(row['收盘'])
                            if close_price > 0 and close_price < 1000:
                                daily_prices[date_str] = close_price
                    
                    # 使用每日股价计算股数
                    for amount_col, shares_col in [
                        ('institution_net_amount', 'institution_net_shares'),
                        ('hot_net_amount', 'hot_net_shares'),
                        ('retail_net_amount', 'retail_net_shares'),
                    ]:
                        df[shares_col] = 0.0  # 初始化为0
                        
                        for idx, row in df.iterrows():
                            date_str = idx.strftime('%Y%m%d')
                            if date_str in daily_prices and daily_prices[date_str] > 0:
                                net_amount = float(row[amount_col])
                                df.at[idx, shares_col] = net_amount / daily_prices[date_str]
                            else:
                                # 如果当日没有股价，使用前一日股价或设为0
                                df.at[idx, shares_col] = 0.0
                                
            except Exception as e:
                # 遇到行情拉取或计算问题时跳过股数计算
                logging.warning(f"股数计算失败，使用金额数据: {str(e)}")
                pass

            return df
        except Exception as e:
            logging.error(f"获取资金来源时间序列失败 {code} {start_date}-{end_date}: {str(e)}")
            return pd.DataFrame()

    def get_hot_money_details(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取游资营业部在指定时间范围内的详情数据，包含积累净买卖
        
        Args:
            code: 股票代码
            start_date: 开始日期 "YYYYMMDD"
            end_date: 结束日期 "YYYYMMDD"
            
        Returns:
            DataFrame with columns: ['营业部名称', '净买入股数', '净买入金额']
        """
        try:
            def normalize(date_str: str) -> str:
                """标准化日期格式为YYYYMMDD"""
                date_str = str(date_str).replace('-', '').replace('/', '')[:8]
                if len(date_str) == 8 and date_str.isdigit():
                    return date_str
                try:
                    dt = pd.to_datetime(date_str)
                    return dt.strftime('%Y%m%d')
                except Exception:
                    return ''

            s, e = normalize(start_date), normalize(end_date)
            if not s or not e:
                return pd.DataFrame()
            if s > e:
                s, e = e, s

            # 获取该标的有龙虎榜数据的日期列表
            dates_df = akshare_wrapper.stock_lhb_stock_detail_date_em(symbol=code)
            date_list: list[str] = []
            
            if dates_df is not None and not dates_df.empty:
                # 提取日期列
                if '日期' in dates_df.columns:
                    date_series = dates_df['日期']
                elif '交易日' in dates_df.columns:
                    date_series = dates_df['交易日']
                else:
                    # 自动识别日期列
                    date_series = None
                    for col in dates_df.columns:
                        try:
                            parsed = pd.to_datetime(dates_df[col], errors='coerce')
                            if parsed.notna().sum() >= max(3, len(dates_df) // 2):
                                date_series = dates_df[col]
                                break
                        except Exception:
                            continue
                    if date_series is None:
                        return pd.DataFrame()
                
                # 筛选时间范围内的日期
                for v in date_series:
                    ds = normalize(str(v))
                    if s <= ds <= e:
                        date_list.append(ds)

            if not date_list:
                return pd.DataFrame()

            # 收集所有游资营业部数据
            broker_data: dict[str, dict[str, float]] = {}  # {营业部名称: {net_amount, net_shares}}
            
            for ds in sorted(set(date_list)):
                try:
                    # 获取买入和卖出详情
                    buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="买入")
                    sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="卖出")
                    
                    # 检查返回的数据是否为None，如果是则初始化为空DataFrame
                    if buy_df is None:
                        buy_df = pd.DataFrame()
                    if sell_df is None:
                        sell_df = pd.DataFrame()
                    
                    # 处理买入数据
                    if not buy_df.empty and '交易营业部名称' in buy_df.columns and '买入金额' in buy_df.columns:
                        for _, row in buy_df.iterrows():
                            broker_name = str(row['交易营业部名称'])
                            amount = float(row.get('买入金额', 0))
                            
                            # 过滤机构和散户营业部，只保留游资
                            if self._is_institution_broker(broker_name) or self._is_retail_broker(broker_name):
                                continue
                                
                            if broker_name not in broker_data:
                                broker_data[broker_name] = {'net_amount': 0.0, 'net_shares': 0.0}
                            broker_data[broker_name]['net_amount'] += amount
                    
                    # 处理卖出数据
                    if not sell_df.empty and '交易营业部名称' in sell_df.columns and '卖出金额' in sell_df.columns:
                        for _, row in sell_df.iterrows():
                            broker_name = str(row['交易营业部名称'])
                            amount = float(row.get('卖出金额', 0))
                            
                            # 过滤机构和散户营业部，只保留游资
                            if self._is_institution_broker(broker_name) or self._is_retail_broker(broker_name):
                                continue
                                
                            if broker_name not in broker_data:
                                broker_data[broker_name] = {'net_amount': 0.0, 'net_shares': 0.0}
                            broker_data[broker_name]['net_amount'] -= amount
                            
                except Exception as e:
                    print(f"获取{ds}日期的龙虎榜详情失败: {str(e)}")
                    continue

            if not broker_data:
                return pd.DataFrame()

            # 转换金额为股数（使用平均价格）
            try:
                ohlc = akshare_wrapper.stock_zh_a_hist(symbol=code, period='daily', start_date=s, end_date=e, adjust='')
                if ohlc is not None and not ohlc.empty:
                    if '日期' in ohlc.columns:
                        ohlc['日期'] = pd.to_datetime(ohlc['日期'])
                        ohlc = ohlc.set_index('日期')
                    
                    # 计算平均价格
                    avg_price = None
                    if '成交额' in ohlc.columns and '成交量' in ohlc.columns:
                        vol = ohlc['成交量'].replace(0, pd.NA).astype(float)
                        amt = ohlc['成交额'].astype(float)
                        with pd.option_context('mode.use_inf_as_na', True):
                            price_series = (amt / vol).ffill().bfill()
                            avg_price = price_series.mean()
                    
                    # 回退：使用OHLC均价
                    if avg_price is None or pd.isna(avg_price):
                        price_cols = ['开盘', '收盘', '最高', '最低']
                        available_cols = [col for col in price_cols if col in ohlc.columns]
                        if available_cols:
                            avg_price = ohlc[available_cols].mean().mean()
                    
                    # 转换金额为股数
                    if avg_price and not pd.isna(avg_price) and avg_price > 0:
                        for broker_name in broker_data:
                            broker_data[broker_name]['net_shares'] = broker_data[broker_name]['net_amount'] / avg_price
            except Exception as e:
                print(f"计算股数时出错: {str(e)}")

            # 构建结果DataFrame
            result_data = []
            for broker_name, data in broker_data.items():
                result_data.append({
                    '营业部名称': broker_name,
                    '净买入金额': data['net_amount'],
                    '净买入股数': data['net_shares']
                })

            if not result_data:
                return pd.DataFrame()

            df = pd.DataFrame(result_data)
            # 按净买入股数排序（绝对值）
            df['净买入股数绝对值'] = df['净买入股数'].abs()
            df = df.sort_values('净买入股数绝对值', ascending=False).drop('净买入股数绝对值', axis=1)
            
            return df.reset_index(drop=True)
            
        except Exception as e:
            logging.error(f"获取游资营业部详情失败 {code} {start_date}-{end_date}: {str(e)}")
            return pd.DataFrame()

    def _is_institution_broker(self, broker_name: str) -> bool:
        """判断是否为机构营业部"""
        if not broker_name:
            return False
        institution_keywords = ["机构", "基金", "保险", "社保", "QFII", "专用", "沪股通", "深股通"]
        return any(keyword in str(broker_name) for keyword in institution_keywords)
        
    def _is_retail_broker(self, broker_name: str) -> bool:
        """判断是否为散户营业部：名称包含"东方财富证券拉萨"视作散户营业部"""
        if not broker_name:
            return False
        return "拉萨" in str(broker_name)

    def format_broker_name(self, broker_name: str) -> str:
        """
        简化营业部名称显示，移除冗余信息，突出地址信息
        
        Args:
            broker_name: 原始营业部名称
            
        Returns:
            简化后的营业部名称
        """
        if not broker_name:
            return ""
        
        name = str(broker_name)
        
        # 移除常见的冗余词汇
        redundant_words = [
            "证券股份有限公司", "证券有限责任公司", "证券有限公司",
            "证券营业部", "证券", "股份有限公司", "有限责任公司", "有限公司"
        ]
        
        for word in redundant_words:
            name = name.replace(word, "")
        
        # 移除括号内的内容（通常是公司代码等）
        import re
        name = re.sub(r'\([^)]*\)', '', name)
        name = re.sub(r'（[^）]*）', '', name)
        
        # 移除数字和特殊字符
        name = re.sub(r'[0-9]+', '', name)
        name = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', name)
        
        # 如果名称过长，优先保留地址信息
        if len(name) > 8:
            # 查找常见地址关键词
            address_keywords = ["路", "街", "大道", "广场", "大厦", "中心", "区", "市", "省"]
            for keyword in address_keywords:
                if keyword in name:
                    # 找到地址关键词后，截取包含该关键词的部分
                    idx = name.find(keyword)
                    if idx > 0:
                        # 向前截取一些字符，向后截取到关键词
                        start = max(0, idx - 3)
                        end = min(len(name), idx + len(keyword) + 2)
                        name = name[start:end]
                        break
            
            # 如果还是太长，直接截取
            if len(name) > 8:
                name = name[:8] + ".."
        
        return name.strip()

    def get_fund_source_details(self, code: str, start_date: str, end_date: str) -> Dict[str, List[Dict]]:
        """
        获取指定时间范围内三类资金(机构/游资/散户)的营业部详细数据
        
        Args:
            code: 股票代码
            start_date: 开始日期 "YYYYMMDD"
            end_date: 结束日期 "YYYYMMDD"
            
        Returns:
            {
                'institution': [{'broker_name': '营业部名称', 'net_amount': 净买入金额, 'net_shares': 净买入股数, ...}],
                'hot': [{'broker_name': '营业部名称', 'net_amount': 净买入金额, 'net_shares': 净买入股数, ...}],
                'retail': [{'broker_name': '营业部名称', 'net_amount': 净买入金额, 'net_shares': 净买入股数, ...}]
            }
        """
        try:
            def normalize(date_str: str) -> str:
                """标准化日期格式为YYYYMMDD"""
                date_str = str(date_str).replace('-', '').replace('/', '')[:8]
                if len(date_str) == 8 and date_str.isdigit():
                    return date_str
                try:
                    dt = pd.to_datetime(date_str)
                    return dt.strftime('%Y%m%d')
                except Exception:
                    return ''

            s, e = normalize(start_date), normalize(end_date)
            if not s or not e:
                return {'institution': [], 'hot': [], 'retail': []}
            if s > e:
                s, e = e, s

            # 获取该标的有龙虎榜数据的日期列表
            dates_df = akshare_wrapper.stock_lhb_stock_detail_date_em(symbol=code)
            date_list: list[str] = []
            
            if dates_df is not None and not dates_df.empty:
                # 提取日期列
                if '日期' in dates_df.columns:
                    date_series = dates_df['日期']
                elif '交易日' in dates_df.columns:
                    date_series = dates_df['交易日']
                else:
                    # 自动识别日期列
                    date_series = None
                    for col in dates_df.columns:
                        try:
                            parsed = pd.to_datetime(dates_df[col], errors='coerce')
                            if parsed.notna().sum() >= max(3, len(dates_df) // 2):
                                date_series = dates_df[col]
                                break
                        except Exception:
                            continue
                    if date_series is None:
                        return {'institution': [], 'hot': [], 'retail': []}
                
                for v in date_series:
                    ds = normalize(str(v))
                    if s <= ds <= e:
                        date_list.append(ds)

            if not date_list:
                return {'institution': [], 'hot': [], 'retail': []}

            # 收集所有营业部数据
            institution_data = {}
            hot_data = {}
            retail_data = {}

            for ds in sorted(set(date_list)):
                try:
                    # 获取买入和卖出详情
                    buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="买入")
                    sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="卖出")
                    
                    # 检查返回的数据是否为None，如果是则初始化为空DataFrame
                    if buy_df is None:
                        buy_df = pd.DataFrame()
                    if sell_df is None:
                        sell_df = pd.DataFrame()
                    
                    # 处理买入数据
                    if not buy_df.empty and '交易营业部名称' in buy_df.columns:
                        for _, row in buy_df.iterrows():
                            broker_name = str(row['交易营业部名称'])
                            amount = float(row.get('买入金额', 0))
                            
                            # 分类营业部
                            if self._is_institution_broker(broker_name):
                                if broker_name not in institution_data:
                                    institution_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                institution_data[broker_name]['net_amount'] += amount
                                institution_data[broker_name]['buy_amount'] += amount
                                
                                # 记录每日买入交易
                                if ds not in institution_data[broker_name]['daily_trades']:
                                    institution_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                institution_data[broker_name]['daily_trades'][ds]['buy'] += amount
                            elif self._is_retail_broker(broker_name):
                                if broker_name not in retail_data:
                                    retail_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                retail_data[broker_name]['net_amount'] += amount
                                retail_data[broker_name]['buy_amount'] += amount
                                
                                # 记录每日买入交易
                                if ds not in retail_data[broker_name]['daily_trades']:
                                    retail_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                retail_data[broker_name]['daily_trades'][ds]['buy'] += amount
                            else:
                                # 游资营业部
                                if broker_name not in hot_data:
                                    hot_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                hot_data[broker_name]['net_amount'] += amount
                                hot_data[broker_name]['buy_amount'] += amount
                                
                                # 记录每日买入交易
                                if ds not in hot_data[broker_name]['daily_trades']:
                                    hot_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                hot_data[broker_name]['daily_trades'][ds]['buy'] += amount
                    
                    # 处理卖出数据
                    if not sell_df.empty and '交易营业部名称' in sell_df.columns:
                        for _, row in sell_df.iterrows():
                            broker_name = str(row['交易营业部名称'])
                            amount = float(row.get('卖出金额', 0))
                            
                            # 分类营业部
                            if self._is_institution_broker(broker_name):
                                if broker_name not in institution_data:
                                    institution_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                institution_data[broker_name]['net_amount'] -= amount
                                institution_data[broker_name]['sell_amount'] += amount
                                
                                # 记录每日卖出交易
                                if ds not in institution_data[broker_name]['daily_trades']:
                                    institution_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                institution_data[broker_name]['daily_trades'][ds]['sell'] += amount
                            elif self._is_retail_broker(broker_name):
                                if broker_name not in retail_data:
                                    retail_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                retail_data[broker_name]['net_amount'] -= amount
                                retail_data[broker_name]['sell_amount'] += amount
                                
                                # 记录每日卖出交易
                                if ds not in retail_data[broker_name]['daily_trades']:
                                    retail_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                retail_data[broker_name]['daily_trades'][ds]['sell'] += amount
                            else:
                                # 游资营业部
                                if broker_name not in hot_data:
                                    hot_data[broker_name] = {
                                        'broker_name': broker_name,
                                        'original_name': broker_name,
                                        'net_amount': 0.0,
                                        'net_shares': 0.0,
                                        'buy_amount': 0.0,
                                        'sell_amount': 0.0,
                                        'daily_trades': {}  # 添加每日交易记录
                                    }
                                hot_data[broker_name]['net_amount'] -= amount
                                hot_data[broker_name]['sell_amount'] += amount
                                
                                # 记录每日卖出交易
                                if ds not in hot_data[broker_name]['daily_trades']:
                                    hot_data[broker_name]['daily_trades'][ds] = {'buy': 0.0, 'sell': 0.0, 'buy_shares': 0.0, 'sell_shares': 0.0}
                                hot_data[broker_name]['daily_trades'][ds]['sell'] += amount
                            
                except Exception as e:
                    print(f"获取{ds}日期的龙虎榜详情失败: {str(e)}")
                    continue

            # 计算股数（按每天的价格分别计算）
            try:
                ohlc = akshare_wrapper.stock_zh_a_hist(symbol=code, period='daily', start_date=s, end_date=e, adjust='')
                if ohlc is not None and not ohlc.empty:
                    if '日期' in ohlc.columns:
                        ohlc['日期'] = pd.to_datetime(ohlc['日期'])
                        ohlc = ohlc.set_index('日期')
                    
                    # 创建日期到价格的映射
                    date_price_map = {}
                    
                    # 优先使用成交额/成交量计算每日均价
                    if '成交额' in ohlc.columns and '成交量' in ohlc.columns:
                        vol = ohlc['成交量'].replace(0, pd.NA).astype(float)
                        amt = ohlc['成交额'].astype(float)
                        
                        # 添加调试信息
                        print(f"成交量范围: {vol.min():.0f} - {vol.max():.0f}")
                        print(f"成交额范围: {amt.min():.0f} - {amt.max():.0f}")
                        
                        # 计算价格序列，处理无穷值
                        price_series = (amt / vol)
                        # 将无穷值转换为NaN
                        price_series = price_series.replace([np.inf, -np.inf], np.nan)
                        # 前向和后向填充
                        price_series = price_series.ffill().bfill()
                        
                        # 过滤异常价格（比如超过1000元的明显错误价格）
                        for date, price in price_series.items():
                            if not pd.isna(price) and price > 0 and price < 1000:  # 过滤异常高价
                                date_price_map[date.strftime('%Y%m%d')] = price
                    
                    # 回退：使用OHLC均价（更可靠）
                    if not date_price_map:
                        print("使用OHLC均价计算")
                        for date, row in ohlc.iterrows():
                            price_cols = ['开盘', '收盘', '最高', '最低']
                            available_cols = [col for col in price_cols if col in row.index]
                            if available_cols:
                                daily_avg = sum(float(row[col]) for col in available_cols) / len(available_cols)
                                if daily_avg > 0 and daily_avg < 1000:  # 过滤异常高价
                                    date_price_map[date.strftime('%Y%m%d')] = daily_avg
                    
                    # 如果还是没有有效价格，尝试直接使用收盘价
                    if not date_price_map and '收盘' in ohlc.columns:
                        print("使用收盘价计算")
                        for date, row in ohlc.iterrows():
                            close_price = float(row['收盘'])
                            if close_price > 0 and close_price < 1000:  # 过滤异常高价
                                date_price_map[date.strftime('%Y%m%d')] = close_price
                    
                    if date_price_map:
                        print(f"获取到 {len(date_price_map)} 个交易日的价格数据")
                        print(f"价格范围: {min(date_price_map.values()):.2f} - {max(date_price_map.values()):.2f} 元")
                        
                        # 显示前几个价格作为验证
                        sample_prices = list(date_price_map.items())[:5]
                        print("样本价格:")
                        for date, price in sample_prices:
                            print(f"  {date}: {price:.2f}元")
                        
                        # 按每天的价格分别计算股数
                        for data_dict in [institution_data, hot_data, retail_data]:
                            for broker_name in data_dict:
                                # 重置股数，重新计算
                                data_dict[broker_name]['net_shares'] = 0.0
                        
                        # 重新遍历每个日期的数据，按当天价格计算股数
                        for ds in sorted(set(date_list)):
                           
                                daily_price = date_price_map[ds]
                                
                                try:
                                    # 获取当天的买入和卖出详情
                                    buy_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="买入")
                                    sell_df = akshare_wrapper.stock_lhb_stock_detail_em(symbol=code, date=ds, flag="卖出")
                                    
                                    # 检查返回的数据是否为None，如果是则初始化为空DataFrame
                                    if buy_df is None:
                                        buy_df = pd.DataFrame()
                                    if sell_df is None:
                                        sell_df = pd.DataFrame()
                                    
                                    # 处理买入数据
                                    if not buy_df.empty and '交易营业部名称' in buy_df.columns:
                                        for _, row in buy_df.iterrows():
                                            broker_name = str(row['交易营业部名称'])
                                            amount = float(row.get('买入金额', 0))
                                            shares = amount / daily_price if daily_price > 0 else 0
                                            
                                            # 分类营业部并累加股数
                                            if self._is_institution_broker(broker_name):
                                                if broker_name in institution_data:
                                                    institution_data[broker_name]['net_shares'] += shares
                                            elif self._is_retail_broker(broker_name):
                                                if broker_name in retail_data:
                                                    retail_data[broker_name]['net_shares'] += shares
                                            else:
                                                if broker_name in hot_data:
                                                    hot_data[broker_name]['net_shares'] += shares
                                    
                                    # 处理卖出数据
                                    if not sell_df.empty and '交易营业部名称' in sell_df.columns:
                                        for _, row in sell_df.iterrows():
                                            broker_name = str(row['交易营业部名称'])
                                            amount = float(row.get('卖出金额', 0))
                                            shares = -amount / daily_price if daily_price > 0 else 0  # 卖出为负
                                            
                                            # 分类营业部并累加股数
                                            if self._is_institution_broker(broker_name):
                                                if broker_name in institution_data:
                                                    institution_data[broker_name]['net_shares'] += shares
                                            elif self._is_retail_broker(broker_name):
                                                if broker_name in retail_data:
                                                    retail_data[broker_name]['net_shares'] += shares
                                            else:
                                                if broker_name in hot_data:
                                                    hot_data[broker_name]['net_shares'] += shares
                                                
                                except Exception as e:
                                    print(f"计算{ds}日期股数时出错: {str(e)}")
                                    continue
                    else:
                        print("无法获取有效价格数据，股数显示为0")
                        return {'institution': [], 'hot': [], 'retail': []}
                else:
                    print(f"无法获取价格数据，股数显示为0")
            except Exception as e:
                print(f"计算股数时出错: {str(e)}")
            
            # 应用营业部名称简化
            for data_dict in [institution_data, hot_data, retail_data]:
                for broker_name in data_dict:
                    data_dict[broker_name]['broker_name'] = self.format_broker_name(broker_name)

            # 转换为列表并按净买入金额排序
            def sort_by_net_amount(data_dict):
                return sorted(data_dict.values(), key=lambda x: abs(x['net_amount']), reverse=True)

            result = {
                'institution': sort_by_net_amount(institution_data),
                'hot': sort_by_net_amount(hot_data),
                'retail': sort_by_net_amount(retail_data)
            }
            
            return result
            
        except Exception as e:
            logging.error(f"获取资金来源详情失败 {code} {start_date}-{end_date}: {str(e)}")
            return {'institution': [], 'hot': [], 'retail': []}


# 全局实例
lhb_processor = LhbDataProcessor() 