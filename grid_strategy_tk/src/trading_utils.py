import time
import tkinter as tk
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import akshare as ak
import numpy as np
import pandas as pd
from pypinyin import lazy_pinyin


def calculate_ma_price(symbol: str, start_date: datetime, ma_period: int, security_type: str = "ETF") -> tuple:
    """
    计算均线价格
    @param symbol: 证券代码
    @param start_date: 开始日期
    @param ma_period: 均线周期
    @param security_type: 证券类型 ("ETF" 或 "STOCK")
    @return: (收盘价, 均线价格)的元组，如果计算失败则返回(None, None)
    """
    try:
        # 计算均线所需的开始日期
        start_date_for_ma = start_date - timedelta(days=ma_period * 2)
        start_date_str = start_date_for_ma.strftime('%Y-%m-%d')
        end_date_str = start_date.strftime('%Y-%m-%d')
        
        if security_type == "STOCK":
            df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date_str, end_date=end_date_str, adjust="qfq")
        elif security_type == "BOARD":
            df = ak.stock_board_concept_hist_em(symbol=symbol, start_date=start_date_str, end_date=end_date_str)
            # df = df.rename(columns={'日期':'trade_date', '收盘':'close'})
        else:
            df = ak.fund_etf_hist_em(symbol=symbol, start_date=start_date_str, end_date=end_date_str, adjust="qfq")
        
        if df.empty:
            print("未获取到任何数据")
            return None, None
        
        # 确保日期列为索引且按时间升序排列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
        elif 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date').sort_index()
        
        # 计算移动平均线
        df['MA'] = df['收盘'].rolling(window=ma_period).mean()
        
        # 获取开始日期的收盘价和均线价格
        target_date_data = df.loc[df.index <= start_date]
        if target_date_data.empty:
            print("目标日期没有数据")
            return None, None
            
        last_data = target_date_data.iloc[-1]
        close_price = float(last_data['收盘'])
        ma_price = float(last_data['MA'])
        
        return close_price, ma_price
    except Exception as e:
        print(f"计算均线价格时发生错误: {e}")
        return None, None

# 添加证券信息缓存
_symbol_info_cache: Dict[str, Tuple[Optional[str], str]] = {}

def get_symbol_info(symbol: str) -> Tuple[Optional[str], str]:
    """
    获取证券信息
    @param symbol: 证券代码
    @return: (证券名称, 证券类型)的元组，如果未找到则返回(None, "ETF")
    """
    # 检查缓存
    if symbol in _symbol_info_cache:
        value = _symbol_info_cache[symbol]
        if value[0] is not None:
            return value
    
    try:
        # 自动判断证券类型
        if symbol == "1A0001" or symbol == "000001":
            security_type = "INDEX"
        elif len(symbol) == 6:
            if symbol.startswith(("5", "15")):
                security_type = "ETF"
            elif symbol.startswith("BK"):
                security_type = "BOARD"
            else:
                security_type = "STOCK"
        else:
            security_type = "STOCK"
        
        result = None, security_type
        
        if security_type == "INDEX":
            # 指数类型，直接返回名称
            if symbol == "1A0001" or symbol == "000001":
                result = "上证指数", security_type
        elif security_type == "ETF":
            # 使用多API备用机制获取ETF数据
            try:
                from .etf_data_fetcher import get_etf_spot_data
                df = get_etf_spot_data(use_cache=True)
            except ImportError:
                # 回退到绝对导入
                try:
                    from etf_data_fetcher import get_etf_spot_data
                    df = get_etf_spot_data(use_cache=True)
                except ImportError:
                    # 回退到原始方法
                    df = ak.fund_etf_spot_em()
            if not df.empty and symbol in df['代码'].values:
                result = df[df['代码'] == symbol]['名称'].values[0], security_type
        elif security_type == "BOARD":
            df = ak.stock_board_concept_name_em()
            concept_df = df[df['板块代码'] == symbol]
            if not concept_df.empty:
                result = concept_df['板块名称'].values[0], security_type
        else:
            if symbol.startswith(("40", "42")):
                df = ak.stock_staq_net_stop()      
                if symbol in df['代码'].values:
                    stock_name = df[df['代码'] == symbol]['名称'].values[0]
                    result = stock_name, security_type                 
            else:
                df = ak.stock_info_a_code_name()
                if symbol in df['code'].values:
                    stock_name = df[df['code'] == symbol]['name'].values[0]
                    result = stock_name, security_type
       
            # df = ak.stock_info_bj_name_code()      
            # if symbol in df['证券代码'].values:
            #     stock_name = df[df['证券代码'] == symbol]['证券名称'].values[0]
            #     return stock_name, security_type                    
        
        # 缓存结果
        _symbol_info_cache[symbol] = result
        return result
        
    except Exception as e:
        print(f"获取证券信息失败: {e}")
        result = None, "ETF"
        # 缓存错误结果，避免重复查询
        _symbol_info_cache[symbol] = result
        return result

def clear_symbol_info_cache():
    """清理证券信息缓存"""
    global _symbol_info_cache
    _symbol_info_cache.clear()

def get_symbol_info_cache_size() -> int:
    """获取证券信息缓存大小"""
    return len(_symbol_info_cache)

def calculate_price_range(symbol: str, symbol_name: str, start_date: str, end_date: str, security_type: str = "ETF") -> Tuple[Optional[float], Optional[float]]:
    """
    计算价格范围
    @param symbol: 证券代码
    @param start_date: 开始日期
    @param end_date: 结束日期
    @param security_type: 证券类型
    @return: (最小价格, 最大价格)的元组，如果计算失败则返回(None, None)
    """
    try:
        if security_type == "ETF":
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
        elif security_type == "BOARD":
            df = ak.stock_board_concept_hist_em(
                symbol=symbol_name, 
                start_date=start_date.replace('-', ''), 
                end_date=end_date.replace('-', '')
            )
            # df = df.rename(columns={'日期':'trade_date', '收盘':'close'})
        else:
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq"
            )
            
        if df.empty:
            return None, None
            
        price_min = df['最低'].min()
        price_max = df['最高'].max()
        return price_min, price_max
        
    except Exception as e:
        print(f"计算价格范围失败: {e}")
        return None, None

def is_valid_symbol(symbol: str) -> bool:
    """
    检查证券代码是否有效
    @param symbol: 证券代码
    @return: 是否有效
    """
    try:
        # 指数代码判断
        if symbol == "1A0001" or symbol == "000001":
            return True
        # 新增概念板块判断
        elif len(symbol) == 6 and symbol.startswith("BK"):
            try:
                df = ak.stock_board_concept_name_em()
                return symbol in df['板块代码'].values
            except Exception:
                return False
        elif len(symbol) == 6 and symbol.startswith(("5", "15")):
            # ETF代码验证（使用多API备用机制）
            try:
                from .etf_data_fetcher import get_etf_spot_data
                df = get_etf_spot_data(use_cache=True)
            except ImportError:
                # 回退到绝对导入
                try:
                    from etf_data_fetcher import get_etf_spot_data
                    df = get_etf_spot_data(use_cache=True)
                except ImportError:
                    # 回退到原始方法
                    try:
                        df = ak.fund_etf_spot_em()
                    except Exception:
                        return False
                except Exception:
                    return False
            except Exception:
                # 如果都失败，返回False
                return False
            
            if df.empty:
                return False
            return symbol in df['代码'].values
        else:
            # 股票代码验证
            try:
                df = ak.stock_zh_a_spot_em()
                return symbol in df['代码'].values
            except Exception:
                return False
    except Exception:
        return False

def get_pinyin_initials(text: str) -> str:
    """
    获取文本的拼音首字母
    @param text: 中文文本
    @return: 拼音首字母字符串
    """
    return ''.join([p[0] for p in lazy_pinyin(text)])

def get_symbol_info_by_name(symbol_name: str) -> list:
    """
    根据证券名称或拼音首字母搜索证券信息
    @param symbol_name: 证券名称或拼音首字母
    @return: 包含(代码, 名称, 类型)元组的候选列表
    """
    try:
        results = []
        
        # ETF查询（使用多API备用机制）
        try:
            from .etf_data_fetcher import get_etf_spot_data
            df_etf = get_etf_spot_data(use_cache=True)
        except ImportError:
            # 回退到绝对导入
            try:
                from etf_data_fetcher import get_etf_spot_data
                df_etf = get_etf_spot_data(use_cache=True)
            except ImportError:
                # 回退到原始方法
                df_etf = ak.fund_etf_spot_em()
        
        etf_matches = df_etf[
            (df_etf['名称'].str.contains(symbol_name, na=False)) |
            (df_etf['名称'].apply(lambda x: get_pinyin_initials(x).lower() == symbol_name))
        ]
        results.extend([(row['代码'], row['名称'], "ETF") for _, row in etf_matches.iterrows()])
        
        # 股票查询
        df_stock = ak.stock_zh_a_spot_em()
        stock_matches = df_stock[
            (df_stock['名称'].str.contains(symbol_name, na=False)) |
            (df_stock['名称'].apply(lambda x: get_pinyin_initials(x).lower() == symbol_name))
        ]
        results.extend([(row['代码'], row['名称'], "STOCK") for _, row in stock_matches.iterrows()])
        
        # 概念板块查询
        df_concept = ak.stock_board_concept_name_em()
        concept_matches = df_concept[
            (df_concept['板块名称'].str.contains(symbol_name, na=False)) |
            (df_concept['板块名称'].apply(lambda x: get_pinyin_initials(x).lower() == symbol_name))
        ]
        results.extend([(row['板块代码'], row['板块名称'], "BOARD") for _, row in concept_matches.iterrows()])
        
        return results
        
    except Exception as e:
        print(f"根据名称获取证券信息失败: {e}")
        return []

def get_previous_close(symbol: str, trade_date: str, security_type: str = "STOCK") -> Optional[float]:
    """
    获取前一交易日的收盘价
    @param symbol: 证券代码
    @param trade_date: 当前交易日 (YYYY-MM-DD格式)
    @param security_type: 证券类型 ("ETF", "STOCK", "BOARD")
    @return: 前一交易日收盘价，如果获取失败返回None
    """
    try:
        from datetime import date, timedelta

        # 计算前一交易日
        current_date = date.fromisoformat(trade_date)
        prev_date = current_date - timedelta(days=1)
        
        # 跳过周末
        while prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
            prev_date -= timedelta(days=1)
        
        prev_date_str = prev_date.strftime('%Y-%m-%d')
        
        # 根据证券类型获取数据
        if security_type == "ETF":
            daily_data = ak.fund_etf_hist_em(
                symbol=symbol,
                start_date=prev_date_str.replace('-', ''),
                end_date=prev_date_str.replace('-', ''),
                adjust="qfq"
            )
        elif security_type == "BOARD":
            daily_data = ak.stock_board_concept_hist_em(
                symbol=symbol,
                start_date=prev_date_str.replace('-', ''),
                end_date=prev_date_str.replace('-', '')
            )
        elif security_type == "INDEX":
            # 使用指数历史数据接口
            print(f"[DEBUG] 获取指数历史数据: symbol={symbol}, start_date={prev_date_str.replace('-', '')}, end_date={prev_date_str.replace('-', '')}")
            daily_data = ak.index_zh_a_hist(
                symbol=symbol,
                start_date=prev_date_str.replace('-', ''),
                end_date=prev_date_str.replace('-', ''),
                adjust=""
            )
            print(f"[DEBUG] 指数历史数据获取结果: {len(daily_data)} 条记录")
            if not daily_data.empty:
                print(f"[DEBUG] 指数历史数据列名: {list(daily_data.columns)}")
                print(f"[DEBUG] 指数历史数据示例: {daily_data.head(2)}")
        else:  # STOCK
            daily_data = ak.stock_zh_a_hist(
                symbol=symbol,
                start_date=prev_date_str.replace('-', ''),
                end_date=prev_date_str.replace('-', ''),
                adjust="qfq"
            )
        
        if daily_data.empty:
            # 如果精确日期没有数据，尝试获取更宽范围的数据
            start_date = (prev_date - timedelta(days=10)).strftime('%Y-%m-%d')
            
            if security_type == "ETF":
                daily_data = ak.fund_etf_hist_em(
                    symbol=symbol,
                    start_date=start_date.replace('-', ''),
                    end_date=prev_date_str.replace('-', ''),
                    adjust="qfq"
                )
            elif security_type == "BOARD":
                daily_data = ak.stock_board_concept_hist_em(
                    symbol=symbol,
                    start_date=start_date.replace('-', ''),
                    end_date=prev_date_str.replace('-', '')
                )
            elif security_type == "INDEX":
                # 使用指数历史数据接口
                daily_data = ak.index_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date.replace('-', ''),
                    end_date=prev_date_str.replace('-', ''),
                    adjust=""
                )
            else:  # STOCK
                daily_data = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date.replace('-', ''),
                    end_date=prev_date_str.replace('-', ''),
                    adjust="qfq"
                )
            
            if not daily_data.empty:
                # 筛选出目标日期的数据
                daily_data['日期'] = pd.to_datetime(daily_data['日期'])
                target_date = pd.Timestamp(prev_date)
                daily_data = daily_data[daily_data['日期'] == target_date]
        
        if daily_data.empty:
            print(f"[DEBUG] 指数历史数据为空，无法获取收盘价")
            return None
        
        close_price = float(daily_data.iloc[-1]["收盘"])
        print(f"[DEBUG] 指数前一交易日收盘价: {close_price}")
        return close_price
        
    except Exception as e:
        print(f"获取前一交易日收盘价失败: {e}")
        return None

# 添加全局缓存和缓存时间
_market_data_cache: Dict[str, Any] = {
    'etf_data': None,
    'board_data': None, 
    'stock_data': None,
    'last_update': None
}
def print_market_data():
    """
    打印市场数据缓存中的股票数据
    """
    try:
        if _market_data_cache['stock_data'] is not None:
            df = _market_data_cache['stock_data']
            pd.set_option('display.max_rows', None)  # 显示所有行
            pd.set_option('display.max_columns', None)  # 显示所有列
            pd.set_option('display.width', None)  # 设置显示宽度为无限制
            print("股票数据形状:", df.shape)
            print("\n完整数据:")
            print(df)
            # 恢复显示设置
            pd.reset_option('display.max_rows')
            pd.reset_option('display.max_columns')
            pd.reset_option('display.width')
        else:
            print("股票数据缓存为空，请先更新市场数据")
    except Exception as e:
        print(f"打印市场数据时发生错误: {e}")

def _update_market_data():
    """
    更新市场数据缓存
    """
    try:
        # 使用多API备用机制获取ETF数据
        try:
            from etf_data_fetcher import get_etf_spot_data
            _market_data_cache['etf_data'] = get_etf_spot_data(use_cache=True)
            print("ETF数据更新成功")
        except Exception as e:
            print(f"ETF数据更新失败: {e}")
        
        # 获取板块数据
        try:
            _market_data_cache['board_data'] = ak.stock_board_industry_name_em()
            print("板块数据更新成功")
        except Exception as e:
            print(f"板块数据更新失败: {e}")

        # 获取股票数据
        try:
            spot_df = ak.stock_zh_a_spot_em()
            _market_data_cache['stock_data'] = spot_df
            print("股票数据更新成功")
        except Exception as e:
            print(f"股票数据更新失败: {e}")

        _market_data_cache['last_update'] = datetime.now()
        
    except Exception as e:
        print(f"更新市场数据失败: {e}")
def update_market_data():
    """
    更新市场数据缓存
    """
    try:
        # 检查缓存是否需要更新(每60秒更新一次)
        # now = datetime.now()
        # if (_market_data_cache['last_update'] is None or 
        #     (now - _market_data_cache['last_update']).seconds > 60):
        _update_market_data()
    except Exception as e:
        print(f"更新市场数据失败: {e}")

def get_realtime_quote(symbol):
    """
    获取实时行情数据
    @param symbol: 证券代码
    @return: 包含价格和涨跌幅的字典，如果获取失败返回None
    """
    try:
        # 根据代码判断证券类型
        if symbol == "1A0001" or symbol == "000001":  # 指数
            # 指数暂时返回None，因为指数没有实时行情数据
            return None
        elif len(symbol) == 6:
            if symbol.startswith(("1", "5")):  # ETF
                df = _market_data_cache['etf_data']
                if df is not None:
                    df = df[df['代码'] == symbol]
                    if not df.empty:
                        return {
                            'price': df['最新价'].iloc[0],
                            'change': f"{df['涨跌幅'].iloc[0]}%"
                        }
            elif symbol.startswith("8"):  # 板块
                df = _market_data_cache['board_data']
                if df is not None:
                    df = df[df['代码'] == symbol]
                    if not df.empty:
                        return {
                            'price': df['最新价'].iloc[0],
                            'change': f"{df['涨跌幅'].iloc[0]}%"
                        }
            else:  # 股票
                df = _market_data_cache['stock_data']
                if df is not None:
                    df = df[df['代码'] == symbol]
                    if not df.empty:
                        return {
                            'price': df['最新价'].iloc[0],
                            'change': f"{df['涨跌幅'].iloc[0]}%"
                        }
                
    except Exception as e:
        print(f"Error getting quote for {symbol}: {e}")
    return None 

    
class SymbolSelector(tk.Toplevel):
    """证券候选列表选择窗口"""
    def __init__(self, parent, candidates):
        super().__init__(parent)
        self.title("请选择证券")
        self.geometry("300x200")
        self.resizable(False, False)
        
        self.candidates = candidates
        self.selected_index = 0
        
        # 创建列表组件
        self.listbox = tk.Listbox(self)
        for item in self.candidates:
            self.listbox.insert(tk.END, f"{item[1]} ({item[0]})")
        self.listbox.pack(expand=True, fill=tk.BOTH)
        
        # 绑定键盘事件
        self.bind("<Up>", self._handle_up)
        self.bind("<Down>", self._handle_down)
        self.bind("<Return>", self._handle_confirm)
        self.listbox.select_set(0)
        
        # 窗口置顶
        self.attributes("-topmost", True)
        self.grab_set()
    
    def _handle_up(self, event):
        if self.selected_index > 0:
            self.selected_index -= 1
            self.listbox.select_clear(0, tk.END)
            self.listbox.select_set(self.selected_index)
            self.listbox.see(self.selected_index)
    
    def _handle_down(self, event):
        if self.selected_index < len(self.candidates)-1:
            self.selected_index += 1
            self.listbox.select_clear(0, tk.END)
            self.listbox.select_set(self.selected_index)
            self.listbox.see(self.selected_index)
    
    def _handle_confirm(self, event):
        self.destroy()
    
    def get_selected(self):
        if 0 <= self.selected_index < len(self.candidates):
            return self.candidates[self.selected_index]
        return None 


def get_historical_data(symbol: str, current_date: str, months_back: int, security_type: str) -> Optional[pd.DataFrame]:
    """获取历史数据"""
    try:
        from datetime import datetime, timedelta

        # 计算开始日期
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        start_dt = current_dt - timedelta(days=months_back * 30)
        start_date = start_dt.strftime('%Y-%m-%d')
        
        # 根据证券类型获取数据
        if security_type == "STOCK":
            df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date.replace('-', ''), end_date=current_date.replace('-', ''), adjust="qfq")
        elif security_type == "ETF":
            df = ak.fund_etf_hist_em(symbol=symbol, start_date=start_date, end_date=current_date, adjust="qfq")
        elif security_type == "BOARD":
            df = ak.stock_board_industry_hist_em(symbol=symbol, start_date=start_date, end_date=current_date, adjust="qfq")
        elif security_type == "INDEX":
            # 使用指数历史数据接口
            df = ak.index_zh_a_hist(symbol=symbol, start_date=start_date.replace('-', ''), end_date=current_date.replace('-', ''), adjust="")
        else:
            return None
        
        if df.empty:
            return None
        
        # 统一列名
        df.rename(columns={
            "日期": "日期",
            "开盘": "开盘", 
            "收盘": "收盘", 
            "最高": "最高",
            "最低": "最低",
            "成交量": "成交量"
        }, inplace=True)
        
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期').sort_index()
        
        return df
        
    except Exception as e:
        print(f"[DEBUG] 获取历史数据失败: {e}")
        return None

def get_current_price(symbol: str, current_date: str, security_type: str) -> Optional[float]:
    """获取当前价格"""
    try:
        # 获取最新交易日的数据
        if security_type == "STOCK":
            df = ak.stock_zh_a_hist(symbol=symbol, start_date=current_date.replace('-', ''), end_date=current_date.replace('-', ''), adjust="qfq")
        elif security_type == "ETF":
            df = ak.fund_etf_hist_em(symbol=symbol, start_date=current_date, end_date=current_date, adjust="qfq")
        elif security_type == "BOARD":
            df = ak.stock_board_industry_hist_em(symbol=symbol, start_date=current_date, end_date=current_date, adjust="qfq")
        elif security_type == "INDEX":
            # 使用指数历史数据接口
            df = ak.index_zh_a_hist(symbol=symbol, start_date=current_date.replace('-', ''), end_date=current_date.replace('-', ''), adjust="")
        else:
            return None
        
        if df.empty:
            # 如果当天没有数据（如9:30之前），尝试获取前一个交易日的数据
            print(f"[DEBUG] 当天({current_date})无数据，尝试获取前一个交易日数据")
            from datetime import date, datetime, timedelta

            # 使用交易日历获取真正的前一个交易日
            try:
                # 加载交易日历
                cal_df = ak.tool_trade_date_hist_sina()
                cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date']).dt.date
                if 'is_trading_day' in cal_df.columns:
                    cal_df = cal_df[cal_df['is_trading_day'] == 1]
                trade_calendar = set(cal_df['trade_date'])
                
                # 从交易日历中找到前一交易日
                current_date_obj = date.fromisoformat(current_date)
                sorted_dates = sorted(list(trade_calendar))
                current_idx = sorted_dates.index(current_date_obj) if current_date_obj in sorted_dates else -1
                
                if current_idx > 0:
                    prev_date = sorted_dates[current_idx - 1]
                    print(f"[DEBUG] 使用交易日历找到前一交易日: {prev_date}")
                else:
                    # 如果找不到当前日期或当前日期是第一个，则使用简单方法
                    prev_date = current_date_obj - timedelta(days=1)
                    while prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                        prev_date -= timedelta(days=1)
                    print(f"[DEBUG] 交易日历中未找到当前日期，使用简单方法计算前一交易日: {prev_date}")
                    
            except Exception as e:
                print(f"[DEBUG] 加载交易日历失败: {e}，使用简单方法")
                # 如果没有交易日历，使用简单方法
                current_date_obj = date.fromisoformat(current_date)
                prev_date = current_date_obj - timedelta(days=1)
                while prev_date.weekday() >= 5:  # 跳过周末
                    prev_date -= timedelta(days=1)
                print(f"[DEBUG] 使用简单方法计算前一交易日: {prev_date}")
            
            prev_date_str = prev_date.strftime('%Y-%m-%d')
            
            # 获取前一个交易日数据
            if security_type == "STOCK":
                df = ak.stock_zh_a_hist(symbol=symbol, start_date=prev_date_str.replace('-', ''), end_date=prev_date_str.replace('-', ''), adjust="qfq")
            elif security_type == "ETF":
                df = ak.fund_etf_hist_em(symbol=symbol, start_date=prev_date_str, end_date=prev_date_str, adjust="qfq")
            elif security_type == "BOARD":
                df = ak.stock_board_industry_hist_em(symbol=symbol, start_date=prev_date_str, end_date=prev_date_str, adjust="qfq")
            elif security_type == "INDEX":
                df = ak.index_zh_a_hist(symbol=symbol, start_date=prev_date_str.replace('-', ''), end_date=prev_date_str.replace('-', ''), adjust="")
            
            if df.empty:
                print(f"[DEBUG] 前一个交易日({prev_date_str})也无数据")
                return None
            
            print(f"[DEBUG] 使用前一个交易日({prev_date_str})收盘价作为当前价格")
        
        # 返回最新收盘价
        return float(df.iloc[-1]['收盘'])
        
    except Exception as e:
        print(f"[DEBUG] 获取当前价格失败: {e}")
        return None

def calculate_previous_high_price(symbol: str, current_date: str, months_back: int = 12, security_type: str = "STOCK") -> Optional[float]:
    """
    计算股票的前高价格（增强版）
    
    从当前价格开始回溯，找到比当前价格高的1年内所有的局部价格高点，
    把最近的一个高点作为前高价格。
    
    增强功能：
    1. 支持当日分时数据的前高检测
    2. 降低peak检测的严格性，支持部分数据检测
    3. 提供多种检测策略
    
    @param symbol: 股票代码
    @param current_date: 当前日期 (格式: YYYY-MM-DD)
    @param months_back: 回溯月数，默认12个月（1年）
    @param security_type: 证券类型 ("STOCK", "ETF", "BOARD")
    @return: 前高价格，如果未找到则返回None
    """
    try:
        from datetime import datetime, timedelta

        import numpy as np

        # 导入增强的峰值检测算法
        try:
            from enhanced_peak_detection import (detect_enhanced_peaks,
                                                 get_enhanced_high_low)
            use_enhanced_detection = True
        except ImportError:
            use_enhanced_detection = False
            print(f"[DEBUG] 增强峰值检测模块未找到，使用原有算法")

        # 计算开始日期
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        start_dt = current_dt - timedelta(days=months_back * 30)  # 大约3个月
        start_date_str = start_dt.strftime('%Y-%m-%d')
        
        print(f"[DEBUG] 计算前高价格 - 股票: {symbol}, 当前日期: {current_date}")
        print(f"[DEBUG] 回溯开始日期: {start_date_str}, 回溯月数: {months_back}")
        
        # 获取历史数据
        if security_type == "STOCK":
            df = ak.stock_zh_a_hist(
                symbol=symbol, 
                start_date=start_date_str.replace('-', ''), 
                end_date=current_date.replace('-', ''), 
                adjust="qfq"
            )
        elif security_type == "ETF":
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                start_date=start_date_str.replace('-', ''),
                end_date=current_date.replace('-', ''),
                adjust="qfq"
            )
        elif security_type == "BOARD":
            # 对于板块，需要先获取板块名称
            symbol_name, _ = get_symbol_info(symbol)
            if not symbol_name:
                print(f"[DEBUG] 无法获取板块名称: {symbol}")
                return None
            df = ak.stock_board_concept_hist_em(
                symbol=symbol_name,
                start_date=start_date_str.replace('-', ''),
                end_date=current_date.replace('-', '')
            )
        else:
            print(f"[DEBUG] 不支持的证券类型: {security_type}")
            return None
        
        if df.empty:
            print(f"[DEBUG] 未获取到历史数据: {symbol}")
            return None
        
        # 确保日期列为索引且按时间升序排列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
        elif 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date').sort_index()
        
        print(f"[DEBUG] 获取到 {len(df)} 条历史数据")
        print(f"[DEBUG] 数据日期范围: {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
        
        # 获取当前价格（最新收盘价）
        current_price = df['收盘'].iloc[-1]
        print(f"[DEBUG] 当前价格: {current_price:.3f}")
        
        # 优先使用增强检测算法
        if use_enhanced_detection:
            try:
                print(f"[DEBUG] 使用增强峰值检测算法")
                result = get_enhanced_high_low(df, "daily", current_price)
                
                if "error" not in result and result.get("latest_high"):
                    latest_high = result["latest_high"]
                    print(f"[DEBUG] 增强算法找到前高: {latest_high['price']:.3f} (日期: {latest_high['date']})")
                    return float(latest_high['price'])
                else:
                    print(f"[DEBUG] 增强算法未找到前高，回退到原有算法")
            except Exception as e:
                print(f"[DEBUG] 增强检测算法失败: {e}，回退到原有算法")
        
        # 找到比当前价格高的所有数据点
        higher_prices = df[df['收盘'] > current_price]
        
        if higher_prices.empty:
            print(f"[DEBUG] 在 {months_back} 个月内未找到比当前价格更高的价格点")
            return None
        
        print(f"[DEBUG] 找到 {len(higher_prices)} 个比当前价格更高的数据点")
        
        # 使用scipy的find_peaks来找到局部高点（原有算法）
        try:
            from scipy.signal import find_peaks

            # 获取双价格序列：实体最高价和上影线最高价
            entity_high_prices = np.maximum(df['开盘'].values, df['收盘'].values)  # 实体最高价
            shadow_high_prices = df['最高'].values  # 上影线最高价
            
            print(f"[DEBUG] 双价格计算:")
            print(f"[DEBUG]   实体最高价范围: {np.min(entity_high_prices):.3f} - {np.max(entity_high_prices):.3f}")
            print(f"[DEBUG]   上影线最高价范围: {np.min(shadow_high_prices):.3f} - {np.max(shadow_high_prices):.3f}")
            
            # 使用上影线最高价进行峰值检测（更准确的高点识别）
            shadow_high_prices_array = np.array(shadow_high_prices)
            peaks, properties = find_peaks(
                shadow_high_prices_array, 
                prominence=shadow_high_prices_array.std() * 0.1,  # 峰值突出度至少为价格标准差的10%
                distance=5  # 峰值之间至少间隔5个交易日
            )
            
            if len(peaks) == 0:
                print(f"[DEBUG] 未找到明显的局部高点")
                # 如果没有找到明显的峰值，使用最高价作为备选
                max_price = df['最高'].max()
                max_date = df[df['最高'] == max_price].index[0]
                print(f"[DEBUG] 使用最高价作为前高: {max_price:.3f} (日期: {max_date.strftime('%Y-%m-%d')})")
                return float(max_price)
            
            # 获取峰值对应的双价格和日期
            peak_shadow_prices = shadow_high_prices[peaks]
            peak_entity_prices = entity_high_prices[peaks]
            peak_dates = df.index[peaks]
            
            print(f"[DEBUG] 找到 {len(peaks)} 个局部高点:")
            for i, (date, shadow_price, entity_price) in enumerate(zip(peak_dates, peak_shadow_prices, peak_entity_prices)):
                print(f"[DEBUG]   高点{i+1}: {date.strftime('%Y-%m-%d')} - 上影线:{shadow_price:.3f}, 实体:{entity_price:.3f}")
            
            # 筛选出比当前价格高的峰值（使用实体最高价判断）
            higher_peaks = []
            for i, entity_price in enumerate(peak_entity_prices):
                if entity_price > current_price:
                    higher_peaks.append((peak_dates[i], peak_shadow_prices[i], entity_price))
                    print(f"[DEBUG]   高点{i+1}高于当前价格: {peak_dates[i].strftime('%Y-%m-%d')} - 实体:{entity_price:.3f} > {current_price:.3f} (上影线:{peak_shadow_prices[i]:.3f})")
            
            if not higher_peaks:
                print(f"[DEBUG] 所有局部高点都不比当前价格高")
                return None
            
            # 按日期排序，找到最近的高点
            higher_peaks.sort(key=lambda x: x[0])
            latest_high_date, latest_shadow_price, latest_entity_price = higher_peaks[-1]
            
            print(f"[DEBUG] 最近的高点: {latest_high_date.strftime('%Y-%m-%d')}")
            print(f"[DEBUG]   上影线最高价: {latest_shadow_price:.3f}")
            print(f"[DEBUG]   实体最高价: {latest_entity_price:.3f}")
            
            # 检查最近的高点是否是当前交易日
            current_date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
            
            # 如果最近的高点是当前交易日，则使用上一个更高的前高
            if latest_high_date.date() == current_date_obj:
                print(f"[DEBUG] 最近的高点是当前交易日，检查是否有更早的前高")
                if len(higher_peaks) > 1:
                    # 使用上一个更高的前高
                    prev_high_date, prev_shadow_price, prev_entity_price = higher_peaks[-2]
                    print(f"[DEBUG] 使用上一个更高的前高: {prev_high_date.strftime('%Y-%m-%d')}")
                    print(f"[DEBUG]   上影线最高价: {prev_shadow_price:.3f}")
                    print(f"[DEBUG]   实体最高价: {prev_entity_price:.3f}")
                    print(f"[DEBUG] 前高价格计算完成: 上影线={prev_shadow_price:.3f}, 实体={prev_entity_price:.3f}")
                    return float(prev_shadow_price)
                else:
                    print(f"[DEBUG] 没有更早的前高，返回None")
                    return None
            
            print(f"[DEBUG] 前高价格计算完成: 上影线={latest_shadow_price:.3f}, 实体={latest_entity_price:.3f}")
            
            # 返回上影线最高价作为主要的前高价格
            return float(latest_shadow_price)
            
        except ImportError:
            print(f"[DEBUG] scipy未安装，使用简化算法")
            # 如果没有scipy，使用简化算法
            # 找到比当前价格高的最高价
            higher_prices_sorted = higher_prices.sort_values('最高', ascending=False)
            highest_shadow_price = higher_prices_sorted['最高'].iloc[0]
            highest_entity_price = max(higher_prices_sorted['开盘'].iloc[0], higher_prices_sorted['收盘'].iloc[0])
            highest_date = higher_prices_sorted.index[0]
            
            print(f"[DEBUG] 简化算法找到的双价格: {highest_date.strftime('%Y-%m-%d')}")
            print(f"[DEBUG]   上影线最高价: {highest_shadow_price:.3f}")
            print(f"[DEBUG]   实体最高价: {highest_entity_price:.3f}")
            return float(highest_shadow_price)
        
    except Exception as e:
        print(f"[DEBUG] 计算前高价格时发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_previous_high_dual_prices(symbol: str, current_date: str, months_back: int = 12, security_type: str = "STOCK") -> Dict:
    """获取前高价格的双价格信息（实体最高价和上影线最高价）
    
    :param symbol: 股票代码
    :param current_date: 当前日期 (格式: YYYY-MM-DD)
    :param months_back: 回溯月数，默认12个月（1年）
    :param security_type: 证券类型 ("STOCK", "ETF", "BOARD")
    :return: 包含双价格信息的字典
    """
    try:
        # 获取历史数据
        df = get_historical_data(symbol, current_date, months_back, security_type)
        if df is None or df.empty:
            return {"error": "无法获取历史数据"}
        
        # 获取当前价格
        current_price = get_current_price(symbol, current_date, security_type)
        if current_price is None:
            return {"error": "无法获取当前价格"}
        
        # 筛选比当前价格高的数据
        higher_prices = df[df['最高'] > current_price]
        
        if higher_prices.empty:
            return {
                "error": f"在 {months_back} 个月内未找到比当前价格更高的价格点",
                "current_price": current_price,
                "shadow_high_price": None,
                "entity_high_price": None,
                "resistance_band": None
            }
        
        # 使用scipy找到局部高点
        try:
            from scipy.signal import find_peaks

            # 获取双价格序列
            entity_high_prices = np.maximum(df['开盘'].values, df['收盘'].values)
            shadow_high_prices = df['最高'].values
            
            # 使用上影线最高价进行峰值检测
            shadow_high_prices_array = np.array(shadow_high_prices)
            peaks, properties = find_peaks(
                shadow_high_prices_array, 
                prominence=shadow_high_prices_array.std() * 0.1,
                distance=5
            )
            
            if len(peaks) > 0:
                # 获取峰值对应的双价格
                peak_shadow_prices = shadow_high_prices[peaks]
                peak_entity_prices = entity_high_prices[peaks]
                peak_dates = df.index[peaks]
                
                # 筛选出比当前价格高的峰值（使用实体最高价判断）
                higher_peaks = []
                for i, entity_price in enumerate(peak_entity_prices):
                    if entity_price > current_price:
                        higher_peaks.append((peak_dates[i], peak_shadow_prices[i], entity_price))
                
                if higher_peaks:
                    # 按日期排序，找到最近的高点
                    higher_peaks.sort(key=lambda x: x[0])
                    latest_date, latest_shadow_price, latest_entity_price = higher_peaks[-1]
                    
                    # 检查最近的高点是否是当前交易日
                    current_date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
                    
                    # 如果最近的高点是当前交易日，则使用上一个更高的前高
                    if latest_date.date() == current_date_obj:
                        if len(higher_peaks) > 1:
                            # 使用上一个更高的前高
                            latest_date, latest_shadow_price, latest_entity_price = higher_peaks[-2]
                        else:
                            return {
                                "error": "最近的高点是当前交易日，但没有更早的前高",
                                "current_price": current_price,
                                "shadow_high_price": None,
                                "entity_high_price": None,
                                "resistance_band": None
                            }
                    
                    # 计算阻力带
                    resistance_band = {
                        "upper": float(latest_shadow_price),  # 上影线最高价
                        "lower": float(latest_entity_price),  # 实体最高价
                        "date": latest_date.strftime('%Y-%m-%d')
                    }
                    
                    return {
                        "current_price": current_price,
                        "shadow_high_price": float(latest_shadow_price),
                        "entity_high_price": float(latest_entity_price),
                        "resistance_band": resistance_band,
                        "message": f"找到前高双价格: 上影线={latest_shadow_price:.3f}, 实体={latest_entity_price:.3f}"
                    }
            
            # 如果没有找到明显的峰值，使用最高价
            max_shadow_price = df['最高'].max()
            max_entity_price = max(df['开盘'].max(), df['收盘'].max())
            max_date = df[df['最高'] == max_shadow_price].index[0]
            
            resistance_band = {
                "upper": float(max_shadow_price),
                "lower": float(max_entity_price),
                "date": max_date.strftime('%Y-%m-%d')
            }
            
            return {
                "current_price": current_price,
                "shadow_high_price": float(max_shadow_price),
                "entity_high_price": float(max_entity_price),
                "resistance_band": resistance_band,
                "message": f"使用最高价作为前高双价格: 上影线={max_shadow_price:.3f}, 实体={max_entity_price:.3f}"
            }
            
        except ImportError:
            # 简化算法
            higher_prices_sorted = higher_prices.sort_values('最高', ascending=False)
            highest_shadow_price = higher_prices_sorted['最高'].iloc[0]
            highest_entity_price = max(higher_prices_sorted['开盘'].iloc[0], higher_prices_sorted['收盘'].iloc[0])
            highest_date = higher_prices_sorted.index[0]
            
            resistance_band = {
                "upper": float(highest_shadow_price),
                "lower": float(highest_entity_price),
                "date": highest_date.strftime('%Y-%m-%d')
            }
            
            return {
                "current_price": current_price,
                "shadow_high_price": float(highest_shadow_price),
                "entity_high_price": float(highest_entity_price),
                "resistance_band": resistance_band,
                "message": f"简化算法找到的前高双价格: 上影线={highest_shadow_price:.3f}, 实体={highest_entity_price:.3f}"
            }
        
    except Exception as e:
        return {"error": f"计算前高双价格时发生错误: {e}"}

def get_previous_high_analysis(symbol: str, current_date: str, months_back: int = 12, security_type: str = "STOCK") -> Dict:
    """
    获取前高价格的详细分析信息
    
    @param symbol: 股票代码
    @param current_date: 当前日期 (格式: YYYY-MM-DD)
    @param months_back: 回溯月数，默认12个月（1年）
    @param security_type: 证券类型
    @return: 包含分析结果的字典
    """
    try:
        from datetime import datetime, timedelta

        import numpy as np

        # 计算开始日期
        current_dt = datetime.strptime(current_date, '%Y-%m-%d')
        start_dt = current_dt - timedelta(days=months_back * 30)
        start_date_str = start_dt.strftime('%Y-%m-%d')
        
        # 获取历史数据
        if security_type == "STOCK":
            df = ak.stock_zh_a_hist(
                symbol=symbol, 
                start_date=start_date_str.replace('-', ''), 
                end_date=current_date.replace('-', ''), 
                adjust="qfq"
            )
        elif security_type == "ETF":
            df = ak.fund_etf_hist_em(
                symbol=symbol,
                start_date=start_date_str.replace('-', ''),
                end_date=current_date.replace('-', ''),
                adjust="qfq"
            )
        else:
            return {"error": f"不支持的证券类型: {security_type}"}
        
        if df.empty:
            return {"error": "未获取到历史数据"}
        
        # 确保日期列为索引且按时间升序排列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
        elif 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.set_index('trade_date').sort_index()
        
        # 获取当前价格
        current_price = df['收盘'].iloc[-1]
        
        # 找到比当前价格高的所有数据点
        higher_prices = df[df['收盘'] > current_price]
        
        result = {
            "symbol": symbol,
            "current_date": current_date,
            "current_price": float(current_price),
            "analysis_period": f"{start_date_str} 到 {current_date}",
            "total_trading_days": len(df),
            "higher_price_days": len(higher_prices),
            "previous_high_price": None,
            "previous_high_date": None,
            "all_high_points": [],
            "price_statistics": {
                "highest_price": float(df['最高'].max()),
                "lowest_price": float(df['最低'].min()),
                "average_price": float(df['收盘'].mean()),
                "price_volatility": float(df['收盘'].std())
            }
        }
        
        if higher_prices.empty:
            result["message"] = f"在 {months_back} 个月内未找到比当前价格更高的价格点"
            return result
        
        # 使用scipy找到局部高点
        try:
            from scipy.signal import find_peaks

            # 使用实体最高价（开盘价和收盘价中的较高者）进行峰值检测
            entity_high_prices = np.maximum(df['开盘'].values, df['收盘'].values)
            entity_high_prices_array = np.array(entity_high_prices)
            peaks, properties = find_peaks(
                entity_high_prices_array, 
                prominence=entity_high_prices_array.std() * 0.1,
                distance=5
            )
            
            if len(peaks) > 0:
                peak_entity_prices = entity_high_prices[peaks]
                peak_shadow_prices = df['最高'].values[peaks]  # 保留上影线最高价用于显示
                peak_dates = df.index[peaks]
                
                # 记录所有高点
                for date, entity_price, shadow_price in zip(peak_dates, peak_entity_prices, peak_shadow_prices):
                    result["all_high_points"].append({
                        "date": date.strftime('%Y-%m-%d'),
                        "price": float(entity_price),  # 使用实体最高价
                        "shadow_price": float(shadow_price),  # 保留上影线最高价信息
                        "higher_than_current": entity_price > current_price  # 使用实体最高价判断
                    })
                
                # 找到比当前价格高的最近高点（使用实体最高价判断）
                higher_peaks = [(peak_dates[i], peak_entity_prices[i], peak_shadow_prices[i]) for i, entity_price in enumerate(peak_entity_prices) if entity_price > current_price]
                
                if higher_peaks:
                    higher_peaks.sort(key=lambda x: x[0])
                    latest_high_date, latest_entity_price, latest_shadow_price = higher_peaks[-1]
                    
                    # 检查最近的高点是否是当前交易日
                    current_date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
                    
                    # 如果最近的高点是当前交易日，则使用上一个更高的前高
                    if latest_high_date.date() == current_date_obj:
                        if len(higher_peaks) > 1:
                            # 使用上一个更高的前高
                            latest_high_date, latest_entity_price, latest_shadow_price = higher_peaks[-2]
                            result["message"] = f"找到前高价格: {latest_entity_price:.3f} (实体最高价, 日期: {latest_high_date.strftime('%Y-%m-%d')}, 上影线: {latest_shadow_price:.3f}) [使用上一个前高，因为最近的高点是当前交易日]"
                        else:
                            result["message"] = "最近的高点是当前交易日，但没有更早的前高"
                            return result
                    else:
                        result["message"] = f"找到前高价格: {latest_entity_price:.3f} (实体最高价, 日期: {latest_high_date.strftime('%Y-%m-%d')}, 上影线: {latest_shadow_price:.3f})"
                    
                    result["previous_high_price"] = float(latest_entity_price)  # 使用实体最高价
                    result["previous_high_date"] = latest_high_date.strftime('%Y-%m-%d')
                else:
                    result["message"] = "所有局部高点都不比当前价格高"
            else:
                # 如果没有找到明显的峰值，使用实体最高价
                entity_high_prices = np.maximum(df['开盘'].values, df['收盘'].values)
                max_entity_price = np.max(entity_high_prices)
                max_entity_idx = np.argmax(entity_high_prices)
                max_date = df.index[max_entity_idx]
                max_shadow_price = df['最高'].iloc[max_entity_idx]
                
                result["previous_high_price"] = float(max_entity_price)
                result["previous_high_date"] = max_date.strftime('%Y-%m-%d')
                result["message"] = f"使用实体最高价作为前高: {max_entity_price:.3f} (日期: {max_date.strftime('%Y-%m-%d')}, 上影线: {max_shadow_price:.3f})"
                
        except ImportError:
            # 简化算法 - 使用实体最高价
            entity_high_prices = np.maximum(higher_prices['开盘'].values, higher_prices['收盘'].values)
            max_entity_idx = np.argmax(entity_high_prices)
            highest_entity_price = entity_high_prices[max_entity_idx]
            highest_date = higher_prices.index[max_entity_idx]
            highest_shadow_price = higher_prices['最高'].iloc[max_entity_idx]
            
            result["previous_high_price"] = float(highest_entity_price)
            result["previous_high_date"] = highest_date.strftime('%Y-%m-%d')
            result["message"] = f"简化算法找到的实体最高价: {highest_entity_price:.3f} (日期: {highest_date.strftime('%Y-%m-%d')}, 上影线: {highest_shadow_price:.3f})"
        
        return result
        
    except Exception as e:
        return {"error": f"分析过程中发生错误: {str(e)}"}


def get_previous_low_dual_prices(symbol: str, current_date: str, months_back: int = 12, security_type: str = "STOCK") -> Dict:
    """获取前低价格的双价格信息（实体最低价和下影线最低价）
    
    :param symbol: 股票代码
    :param current_date: 当前日期 (格式: YYYY-MM-DD)
    :param months_back: 回溯月数，默认12个月（1年）
    :param security_type: 证券类型 ("STOCK", "ETF", "BOARD")
    :return: 包含双价格信息的字典
    """
    try:
        # 获取历史数据
        df = get_historical_data(symbol, current_date, months_back, security_type)
        if df is None or df.empty:
            return {"error": "无法获取历史数据"}
        
        # 获取当前价格
        current_price = get_current_price(symbol, current_date, security_type)
        if current_price is None:
            return {"error": "无法获取当前价格"}
        
        # 筛选比当前价格低的数据
        lower_prices = df[df['最低'] < current_price]
        
        if lower_prices.empty:
            return {
                "error": f"在 {months_back} 个月内未找到比当前价格更低的价格点",
                "current_price": current_price,
                "shadow_low_price": None,
                "entity_low_price": None,
                "support_band": None
            }
        
        # 使用scipy找到局部低点
        try:
            from scipy.signal import find_peaks

            # 获取双价格序列
            entity_low_prices = np.minimum(df['开盘'].values, df['收盘'].values)
            shadow_low_prices = df['最低'].values
            
            # 使用下影线最低价进行峰值检测（取负值找最低点）
            shadow_low_prices_array = np.array(shadow_low_prices)
            peaks, properties = find_peaks(
                -shadow_low_prices_array,  # 取负值找最低点
                prominence=shadow_low_prices_array.std() * 0.1,
                distance=5
            )
            
            if len(peaks) > 0:
                # 获取峰值对应的双价格
                peak_shadow_prices = shadow_low_prices[peaks]
                peak_entity_prices = entity_low_prices[peaks]
                peak_dates = df.index[peaks]
                
                # 筛选出比当前价格低的峰值（使用实体最低价判断）
                lower_peaks = []
                for i, entity_price in enumerate(peak_entity_prices):
                    if entity_price < current_price:
                        lower_peaks.append((peak_dates[i], peak_shadow_prices[i], entity_price))
                
                if lower_peaks:
                    # 按日期排序，找到最近的低点
                    lower_peaks.sort(key=lambda x: x[0])
                    latest_date, latest_shadow_price, latest_entity_price = lower_peaks[-1]
                    
                    # 检查最近的低点是否是当前交易日
                    current_date_obj = datetime.strptime(current_date, '%Y-%m-%d').date()
                    
                    # 如果最近的低点是当前交易日，则使用上一个更低的前低
                    if latest_date.date() == current_date_obj:
                        if len(lower_peaks) > 1:
                            # 使用上一个更低的前低
                            latest_date, latest_shadow_price, latest_entity_price = lower_peaks[-2]
                        else:
                            return {
                                "error": "最近的低点是当前交易日，但没有更早的前低",
                                "current_price": current_price,
                                "shadow_low_price": None,
                                "entity_low_price": None,
                                "support_band": None
                            }
                    
                    # 计算支撑带
                    support_band = {
                        "upper": float(latest_entity_price),  # 实体最低价
                        "lower": float(latest_shadow_price),  # 下影线最低价
                        "date": latest_date.strftime('%Y-%m-%d')
                    }
                    
                    return {
                        "current_price": current_price,
                        "shadow_low_price": float(latest_shadow_price),
                        "entity_low_price": float(latest_entity_price),
                        "support_band": support_band,
                        "message": f"找到前低双价格: 下影线={latest_shadow_price:.3f}, 实体={latest_entity_price:.3f}"
                    }
            
            # 如果没有找到明显的峰值，使用最低价
            min_shadow_price = df['最低'].min()
            min_entity_price = min(df['开盘'].min(), df['收盘'].min())
            min_date = df[df['最低'] == min_shadow_price].index[0]
            
            support_band = {
                "upper": float(min_entity_price),
                "lower": float(min_shadow_price),
                "date": min_date.strftime('%Y-%m-%d')
            }
            
            return {
                "current_price": current_price,
                "shadow_low_price": float(min_shadow_price),
                "entity_low_price": float(min_entity_price),
                "support_band": support_band,
                "message": f"使用最低价作为前低双价格: 下影线={min_shadow_price:.3f}, 实体={min_entity_price:.3f}"
            }
            
        except ImportError:
            # 如果没有scipy，使用简化算法
            print("[DEBUG] scipy不可用，使用简化算法计算前低双价格")
            
            # 找到最低价
            min_shadow_price = df['最低'].min()
            min_entity_price = min(df['开盘'].min(), df['收盘'].min())
            min_date = df[df['最低'] == min_shadow_price].index[0]
            
            support_band = {
                "upper": float(min_entity_price),
                "lower": float(min_shadow_price),
                "date": min_date.strftime('%Y-%m-%d')
            }
            
            result = {
                "current_price": current_price,
                "shadow_low_price": float(min_shadow_price),
                "entity_low_price": float(min_entity_price),
                "support_band": support_band
            }
            
            result["message"] = f"简化算法找到的实体最低价: {min_entity_price:.3f} (日期: {min_date.strftime('%Y-%m-%d')}, 下影线: {min_shadow_price:.3f})"
        
        return result
        
    except Exception as e:
        print(f"[DEBUG] 获取前低双价格失败: {e}")
        import traceback
        traceback.print_exc()
        return {"error": f"计算前低双价格时发生错误: {e}"}


def detect_uptrend_patterns(data: pd.DataFrame, cache_key: str = None, cache_data: dict = None, period_mode: str = 'day') -> List[Dict[str, Any]]:
    """
    检测上涨趋势模式（纯计算函数）
    定义：在下跌或平盘K线后，连续出现指定数量的上涨单位
    返回：趋势信息列表，每个趋势包含开始索引、结束索引、涨幅等信息
    
    Args:
        data: K线数据DataFrame，必须包含'开盘'、'收盘'、'最高'、'最低'列
        cache_key: 缓存键，用于检查缓存
        cache_data: 缓存数据字典，包含'trends_cache'、'trends_cache_code'、'trends_cache_date_range'
        period_mode: 周期模式，支持'day'、'week'、'month'、'quarter'、'year'、'5min'
    
    Returns:
        趋势信息列表，每个趋势包含以下字段：
        - start_idx: 趋势开始索引
        - end_idx: 趋势结束索引（第N个上涨单位）
        - start_date: 趋势开始日期
        - end_date: 趋势结束日期
        - start_low: 趋势开始实体最低价
        - end_high: 趋势结束实体最高价
        - trend_gain: 趋势涨幅（绝对数值）
        - trend_gain_pct: 趋势涨幅百分比
        - expected_gain: 预期涨幅（等于趋势涨幅）
        - expected_price: 预期价格
        - consecutive_days: 连续上涨天数
    """
    # 检查缓存是否有效
    if cache_data and cache_key:
        current_date_range = (data.index[0], data.index[-1]) if not data.empty else None
        cache_key_with_period = f"{cache_key}_{period_mode}"
        
        if (cache_data.get('trends_cache') is not None and 
            cache_data.get('trends_cache_code') == cache_key_with_period and 
            cache_data.get('trends_cache_date_range') == current_date_range):
            print(f"[DEBUG] 使用缓存的趋势数据: {len(cache_data['trends_cache'])} 个趋势 (周期: {period_mode})")
            return cache_data['trends_cache']
    
    # 根据周期模式确定连续上涨天数要求
    period_requirements = {
        'day': 4,      # 日线：4个连续上涨交易日
        'week': 4,     # 周线：4个连续上涨周
        'month': 4,    # 月线：4个连续上涨月
        'quarter': 4,  # 季线：3个连续上涨季度
        'year': 4,     # 年线：2个连续上涨年
        '5min': 4      # 5分钟线：4个连续上涨5分钟K线
    }
    
    required_consecutive_days = period_requirements.get(period_mode, 4)
    min_data_length = required_consecutive_days + 1
    
    trends = []
    
    if data is None or data.empty or len(data) < min_data_length:
        print(f"[DEBUG] 数据不足，需要至少 {min_data_length} 个数据点 (周期: {period_mode})")
        return trends
    
    try:
        # 计算每个交易日的涨跌状态
        # 上涨：收盘价 > 开盘价 或 涨停板（收盘价 = 开盘价 且 最高价 > 前一日收盘价）
        # 下跌：收盘价 < 开盘价 或 跌停板（收盘价 = 开盘价 且 最高价 < 前一日收盘价）
        # 平盘：收盘价 = 开盘价 且 最高价 = 前一日收盘价
        is_up = data['收盘'] > data['开盘']
        is_down = data['收盘'] < data['开盘']
        is_flat = data['收盘'] == data['开盘']
        
        # 处理涨停板和跌停板情况
        for i in range(1, len(data)):
            if is_flat.iloc[i]:  # 开盘价等于收盘价
                prev_close = data.iloc[i-1]['收盘']
                current_high = data.iloc[i]['最高']
                current_low = data.iloc[i]['最低']
                
                if current_high > prev_close:
                    # 涨停板：最高价高于前一日收盘价
                    is_up.iloc[i] = True
                    is_flat.iloc[i] = False
                elif current_low < prev_close:
                    # 跌停板：最低价低于前一日收盘价
                    is_down.iloc[i] = True
                    is_flat.iloc[i] = False
        
        i = 0
        while i < len(data) - required_consecutive_days:  # 至少需要required_consecutive_days个数据点来形成趋势
            # 检查当前K线是否为下跌或平盘
            if is_down.iloc[i] or is_flat.iloc[i]:
                # 检查后续required_consecutive_days个数据点是否都是上涨
                consecutive_up_count = 0
                j = i + 1
                
                while j < len(data) and is_up.iloc[j]:
                    consecutive_up_count += 1
                    j += 1
                
                # 如果连续上涨天数 >= required_consecutive_days，则检测到上涨趋势
                if consecutive_up_count >= required_consecutive_days:
                    trend_start_idx = i
                    trend_end_idx = i + required_consecutive_days  # 固定为第required_consecutive_days个上涨数据点
                    
                    # 计算趋势涨幅
                    # 开始日实体最低价（开盘价和收盘价中的较低者）
                    start_low = min(data.iloc[trend_start_idx]['开盘'], data.iloc[trend_start_idx]['收盘'])
                    # 结束日实体最高价（开盘价和收盘价中的较高者）
                    end_high = max(data.iloc[trend_end_idx]['开盘'], data.iloc[trend_end_idx]['收盘'])
                    
                    trend_gain = end_high - start_low
                    # 涨幅计算：基于结束日的收盘价作为基准
                    end_close = data.iloc[trend_end_idx]['收盘']
                    trend_gain_pct = (trend_gain / end_close) * 100
                    
                    # 计算预期涨幅（等于趋势涨幅）
                    expected_gain = trend_gain
                    expected_price = data.iloc[trend_end_idx]['收盘'] + expected_gain
                    
                    trend_info = {
                        'start_idx': trend_start_idx,
                        'end_idx': trend_end_idx,
                        'start_date': data.index[trend_start_idx],
                        'end_date': data.index[trend_end_idx],
                        'start_low': start_low,
                        'end_high': end_high,
                        'trend_gain': trend_gain,
                        'trend_gain_pct': trend_gain_pct,
                        'expected_gain': expected_gain,
                        'expected_price': expected_price,
                        'consecutive_days': consecutive_up_count
                    }
                    
                    trends.append(trend_info)
                    print(f"[DEBUG] 检测到上涨趋势 ({period_mode}): {trend_info['start_date'].strftime('%Y-%m-%d')} 到 {trend_info['end_date'].strftime('%Y-%m-%d')}, "
                          f"涨幅: {trend_gain:.3f} ({trend_gain_pct:.1f}%), 预期价格: {expected_price:.3f}, 连续{consecutive_up_count}个{period_mode}")
                    
                    # 跳过已检测的趋势，继续寻找下一个趋势
                    # 从趋势结束日的下一天开始继续检测
                    i = trend_end_idx + 1
                else:
                    i += 1
            else:
                i += 1
        
        print(f"[DEBUG] 总共检测到 {len(trends)} 个上涨趋势 (周期: {period_mode})")
        
        # 更新缓存
        if cache_data and cache_key:
            current_date_range = (data.index[0], data.index[-1]) if not data.empty else None
            cache_key_with_period = f"{cache_key}_{period_mode}"
            cache_data['trends_cache'] = trends
            cache_data['trends_cache_code'] = cache_key_with_period
            cache_data['trends_cache_date_range'] = current_date_range
        
        return trends
        
    except Exception as e:
        print(f"[ERROR] 检测上涨趋势失败: {e}")
        import traceback
        traceback.print_exc()
        return trends


def clear_trend_cache(cache_data: dict):
    """
    清除趋势检测缓存
    
    Args:
        cache_data: 缓存数据字典
    """
    if cache_data:
        cache_data['trends_cache'] = None
        cache_data['trends_cache_code'] = None
        cache_data['trends_cache_date_range'] = None
        print("[DEBUG] 已清除趋势检测缓存")


def calculate_ma5_deviation(symbol: str) -> str:
    """
    计算现价相对5日线的偏离度(涨跌幅)
    
    Args:
        symbol: 股票代码
        
    Returns:
        str: 偏离度字符串，如"+2.5%"或"-1.8%"，计算失败返回"error"
    """
    try:
        from datetime import datetime, timedelta

        import akshare as ak
        import pandas as pd

        # 获取最近一年的历史数据
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
        
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust='qfq')
        
        if df.empty or len(df) < 5:
            print(f"MA5偏离度计算失败 {symbol}: 数据不足，需要至少5天数据")
            return 'error'
        
        # 确保日期列为索引且按时间升序排列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
        
        # 计算5日移动平均线
        df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
        
        # 获取最新收盘价和MA5
        latest_close = df['收盘'].iloc[-1]
        latest_ma5 = df['MA5'].iloc[-1]
        
        if pd.isna(latest_ma5):
            print(f"MA5偏离度计算失败 {symbol}: MA5值为NaN")
            return 'error'
        
        # 计算偏离度(涨跌幅)
        deviation = ((latest_close - latest_ma5) / latest_ma5) * 100
        
        # 确保负值也能正确显示
        if deviation >= 0:
            return f"+{deviation:.1f}%"
        else:
            return f"{deviation:.1f}%"
        
    except Exception as e:
        print(f"计算MA5偏离度失败 {symbol}: {e}")
        return 'error'


def calculate_next_day_limit_up_ma5_deviation(symbol: str) -> str:
    """
    计算次日板MA5偏离度
    
    基于当日实时价格作为收盘价，计算下一个交易日涨停的情况下，
    涨停价对次日MA5的偏离度
    
    计算逻辑：
    1. 将当日实时价格作为当日收盘价
    2. 基于当日实时价格计算次日涨停价
    3. 将次日涨停价作为次日收盘价
    4. 基于包含次日涨停价的5天数据计算次日MA5
    5. 计算涨停价对次日MA5的偏离度
    
    Args:
        symbol: 股票代码
        
    Returns:
        str: 次日板MA5偏离度字符串，如"+2.5%"或"-1.8%"，计算失败返回"error"
    """
    try:
        from datetime import datetime, timedelta

        import akshare as ak
        import pandas as pd
        from src.conditions import StockType

        # 获取最近一年的历史数据（不包含当日）
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        end_date = yesterday.strftime('%Y%m%d')
        start_date = (today - timedelta(days=365)).strftime('%Y%m%d')
        
        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust='qfq')
        
        if df.empty or len(df) < 4:  # 至少需要4天历史数据
            print(f"次日板MA5偏离度计算失败 {symbol}: 数据不足，需要至少4天历史数据")
            return 'error'
        
        # 确保日期列为索引且按时间升序排列
        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
        
        # 获取实时价格作为当日收盘价
        current_date_str = today.strftime('%Y-%m-%d')
        current_price = get_current_price(symbol, current_date_str, "STOCK")
        
        if current_price is None:
            print(f"次日板MA5偏离度计算失败 {symbol}: 无法获取实时价格")
            return 'error'
        
        # 将实时价格作为当日收盘价添加到数据中
        current_date = today.date()
        df.loc[current_date, '收盘'] = current_price
        
        # 计算5日移动平均线（包含当日实时价格）
        df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
        
        # 获取当日收盘价（实时价格）和MA5
        current_close = current_price
        current_ma5 = df['MA5'].iloc[-1]
        
        if pd.isna(current_ma5):
            print(f"次日板MA5偏离度计算失败 {symbol}: MA5值为NaN")
            return 'error'
        
        # 获取股票名称用于判断股票类型
        stock_name = df.get('名称', ['']).iloc[-1] if '名称' in df.columns else ''
        
        # 判断股票类型并获取涨停阈值
        stock_type = StockType.get_type(symbol, stock_name)
        limit_threshold = stock_type.limit_threshold
        
        # 计算涨停价（基于当日实时价格）
        limit_up_price = current_close * (1 + limit_threshold / 100)
        
        # 计算次日的MA5（假设次日涨停）
        # 需要添加次日作为新的交易日，将涨停价作为次日收盘价
        next_day = today + timedelta(days=1)
        next_day_date = next_day.date()
        
        # 创建包含次日涨停价的新数据
        new_close_prices = df['收盘'].copy()
        new_close_prices.loc[next_day_date] = limit_up_price  # 添加次日涨停价
        
        # 重新计算MA5（基于包含次日涨停价的5天数据）
        new_ma5 = new_close_prices.rolling(window=5, min_periods=5).mean().iloc[-1]
        
        if pd.isna(new_ma5):
            print(f"次日板MA5偏离度计算失败 {symbol}: 新MA5值为NaN")
            return 'error'
        
        # 计算涨停价对新MA5的偏离度
        deviation = ((limit_up_price - new_ma5) / new_ma5) * 100
        
        # 确保负值也能正确显示
        if deviation >= 0:
            return f"+{deviation:.1f}%"
        else:
            return f"{deviation:.1f}%"
        
    except Exception as e:
        print(f"计算次日板MA5偏离度失败 {symbol}: {e}")
        return 'error'


def calculate_bollinger_bands(data: pd.DataFrame, window: int = 20, num_std: float = 2) -> pd.DataFrame:
    """
    计算布林带指标
    
    Args:
        data: K线数据DataFrame，必须包含'close'列
        window: 移动平均窗口期，默认20
        num_std: 标准差倍数，默认2
        
    Returns:
        包含布林带指标的DataFrame，包含'MA20', 'BOLL_STD', 'BOLL_UPPER', 'BOLL_LOWER'列
    """
    try:
        if data is None or data.empty:
            print("[DEBUG] 数据为空，无法计算布林带")
            return data
        
        # 确保有足够的收盘价数据
        if 'close' not in data.columns:
            print("[DEBUG] 数据缺少收盘价列")
            return data
        
        # 复制数据避免修改原始数据
        result = data.copy()
        
        # 计算移动平均线(中轨)
        result['MA20'] = result['close'].rolling(window=window, min_periods=1).mean()
        
        # 计算标准差
        result['BOLL_STD'] = result['close'].rolling(window=window, min_periods=1).std()
        
        # 计算上轨和下轨
        result['BOLL_UPPER'] = result['MA20'] + num_std * result['BOLL_STD']
        result['BOLL_LOWER'] = result['MA20'] - num_std * result['BOLL_STD']
        
        print(f"[DEBUG] 布林带计算完成，数据长度: {len(result)}")
        print(f"[DEBUG] 布林带中轨范围: {result['MA20'].min():.3f} - {result['MA20'].max():.3f}")
        print(f"[DEBUG] 布林带上轨范围: {result['BOLL_UPPER'].min():.3f} - {result['BOLL_UPPER'].max():.3f}")
        print(f"[DEBUG] 布林带下轨范围: {result['BOLL_LOWER'].min():.3f} - {result['BOLL_LOWER'].max():.3f}")
        
        return result
        
    except Exception as e:
        print(f"计算布林带失败: {e}")
        import traceback
        traceback.print_exc()
        return data


def detect_bollinger_breakthrough_breakdown(price_data: pd.DataFrame, 
                                          bollinger_upper: pd.Series, 
                                          bollinger_lower: pd.Series,
                                          resample_freq: str = '5T',
                                          offset: str = '1min') -> Dict[str, Any]:
    """
    检测布林带突破和跌破信号
    
    Args:
        price_data: 1分钟K线数据，包含'open', 'close', 'high', 'low'列
        bollinger_upper: 布林带上轨数据
        bollinger_lower: 布林带下轨数据
        resample_freq: 重采样频率，默认'5T'（5分钟）
        offset: 重采样偏移，默认'1min'
        
    Returns:
        包含突破和跌破信息的字典：
        {
            'breakthrough_count': int,  # 突破次数
            'breakdown_count': int,     # 跌破次数
            'breakthrough_signals': List[Dict],  # 突破信号列表
            'breakdown_signals': List[Dict]      # 跌破信号列表
        }
    """
    try:
        if price_data is None or price_data.empty:
            print("[DEBUG] 价格数据为空，无法计算突破跌破次数")
            return {'breakthrough_count': 0, 'breakdown_count': 0, 'breakthrough_signals': [], 'breakdown_signals': []}
            
        if (bollinger_upper is None or bollinger_lower is None or 
            bollinger_upper.empty or bollinger_lower.empty):
            print("[DEBUG] 布林带数据为空，无法计算突破跌破次数")
            return {'breakthrough_count': 0, 'breakdown_count': 0, 'breakthrough_signals': [], 'breakdown_signals': []}
            
        # 将1分钟数据重采样为指定频率K线数据
        price_resampled = price_data.resample(resample_freq, offset=offset).agg({
            'open': 'first',
            'close': 'last', 
            'high': 'max',
            'low': 'min',
            'volume': 'sum'
        }).dropna()
        
        if price_resampled.empty:
            print(f"[DEBUG] {resample_freq}K线数据为空，无法计算突破跌破次数")
            return {'breakthrough_count': 0, 'breakdown_count': 0, 'breakthrough_signals': [], 'breakdown_signals': []}
            
        # 调整时间戳以匹配布林带数据的时间轴
        adjusted_timestamps = []
        for ts in price_resampled.index:
            adjusted_ts = ts + pd.Timedelta(minutes=4)
            adjusted_timestamps.append(adjusted_ts)
        price_resampled.index = adjusted_timestamps
        
        # 初始化计数器和信号列表
        breakthrough_count = 0
        breakdown_count = 0
        breakthrough_signals = []
        breakdown_signals = []
        
        # 遍历每个K线，检查突破和跌破
        for i, (ts, row) in enumerate(price_resampled.iterrows()):
            try:
                # 获取对应的布林带数据
                # 由于布林带数据已经插值到1分钟级别，我们需要找到对应的1分钟时间点
                adjusted_ts = ts + pd.Timedelta(minutes=4)  # 调整时间戳
                
                # 找到最接近的1分钟时间点
                time_diff = np.abs((bollinger_upper.index - adjusted_ts).total_seconds())
                closest_idx = np.argmin(time_diff)
                
                if closest_idx < len(bollinger_upper) and closest_idx < len(bollinger_lower):
                    upper_band = bollinger_upper.iloc[closest_idx]
                    lower_band = bollinger_lower.iloc[closest_idx]
                    
                    # 检查数据有效性
                    if pd.isna(upper_band) or pd.isna(lower_band):
                        continue
                        
                    open_price = row['open']
                    close_price = row['close']
                    high_price = row['high']
                    low_price = row['low']
                    
                    # 数据验证
                    if (pd.isna(open_price) or pd.isna(close_price) or 
                        pd.isna(high_price) or pd.isna(low_price) or
                        open_price == 0 or close_price == 0):
                        continue
                        
                    # 计算K线实体的最高价和最低价
                    entity_high = max(open_price, close_price)  # 实体最高价
                    entity_low = min(open_price, close_price)   # 实体最低价
                    
                    # 检查突破：实体最高价在布林上轨之上，或跳空高开（开盘价直接超过上轨）
                    is_breakthrough = (entity_high > upper_band) or (open_price > upper_band)
                    if is_breakthrough:
                        breakthrough_count += 1
                        if entity_high > upper_band:
                            print(f"[DEBUG] 突破检测: 时间={ts}, 实体最高价={entity_high:.3f}, 上轨={upper_band:.3f}")
                        else:
                            print(f"[DEBUG] 跳空高开突破检测: 时间={ts}, 开盘价={open_price:.3f}, 上轨={upper_band:.3f}")
                        
                        # 添加突破信号到列表
                        breakthrough_signal = {
                            'timestamp': ts,
                            'price': entity_high if entity_high > upper_band else open_price,
                            'upper_band': upper_band,
                            'type': 'breakthrough',
                            'is_gap_up': open_price > upper_band and entity_high <= upper_band
                        }
                        breakthrough_signals.append(breakthrough_signal)
                        
                    # 检查跌破：实体最低价在布林下轨之下，或跳空低开（开盘价直接低于下轨）
                    is_breakdown = (entity_low < lower_band) or (open_price < lower_band)
                    if is_breakdown:
                        breakdown_count += 1
                        if entity_low < lower_band:
                            print(f"[DEBUG] 跌破检测: 时间={ts}, 实体最低价={entity_low:.3f}, 下轨={lower_band:.3f}")
                        else:
                            print(f"[DEBUG] 跳空低开跌破检测: 时间={ts}, 开盘价={open_price:.3f}, 下轨={lower_band:.3f}")
                        
                        # 添加跌破信号到列表
                        breakdown_signal = {
                            'timestamp': ts,
                            'price': entity_low if entity_low < lower_band else open_price,
                            'lower_band': lower_band,
                            'type': 'breakdown',
                            'is_gap_down': open_price < lower_band and entity_low >= lower_band
                        }
                        breakdown_signals.append(breakdown_signal)
                        
            except Exception as e:
                print(f"[WARNING] 处理K线数据时出错: {e}")
                continue
                
        print(f"[DEBUG] 突破跌破次数计算完成: 突破={breakthrough_count}次, 跌破={breakdown_count}次")
        
        return {
            'breakthrough_count': breakthrough_count,
            'breakdown_count': breakdown_count,
            'breakthrough_signals': breakthrough_signals,
            'breakdown_signals': breakdown_signals
        }
        
    except Exception as e:
        print(f"[ERROR] 计算突破跌破次数失败: {e}")
        return {'breakthrough_count': 0, 'breakdown_count': 0, 'breakthrough_signals': [], 'breakdown_signals': []}


def calculate_bollinger_ratio(current_price: float, 
                            middle_band: float, 
                            lower_band: float) -> str:
    """
    计算布林带位置比例
    公式：(布林线中轨 - 现价差值)/(布林线中轨 - 下轨差值)
    
    Args:
        current_price: 当前价格
        middle_band: 布林带中轨
        lower_band: 布林带下轨
        
    Returns:
        布林带位置比例字符串，如"0.25"或""
    """
    try:
        # 检查数据有效性
        if (pd.isna(current_price) or pd.isna(middle_band) or pd.isna(lower_band) or
            current_price <= 0 or middle_band <= 0 or lower_band <= 0):
            return ""
        
        # 计算比例：(中轨 - 现价) / (中轨 - 下轨)
        if middle_band != lower_band:
            ratio = (middle_band - current_price) / (middle_band - lower_band)
            # 返回绝对值，去掉括号
            return f"{abs(ratio):.2f}"
        else:
            return ""
            
    except Exception as e:
        print(f"[ERROR] 计算布林带比例失败: {e}")
        return ""


def calculate_consecutive_trend_gain(data: pd.DataFrame, period: str = 'week', extended_data: pd.DataFrame = None) -> tuple:
    """
    计算指定周期的连阳涨幅，用于趋势预测
    
    Args:
        data: 包含OHLC数据的DataFrame
        period: 周期类型，'day'表示日线，'week'表示周线，'month'表示月线
        extended_data: 扩展的历史数据，用于月线计算（可选）
        
    Returns:
        tuple: (连阳涨幅百分比, 当前周期收盘价, 趋势目标价格)
    """
    try:
        if data is None or data.empty:
            return (0.0, 0.0, 0.0)
        
        # 确保数据按日期排序
        data_sorted = data.sort_index()
        
        # 对于月线计算，优先使用传入的扩展数据
        if period == 'month' and extended_data is not None and not extended_data.empty:
            print(f"[DEBUG] 使用传入的扩展数据进行月线计算: 扩展数据长度{len(extended_data)}")
            # 合并数据，去重并排序
            combined_data = pd.concat([data_sorted, extended_data])
            combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
            data_sorted = combined_data.sort_index()
            print(f"[DEBUG] 月线计算使用扩展数据，总长度: {len(data_sorted)}")
        elif period == 'month' and len(data_sorted) < 365:  # 少于一年的数据且没有扩展数据
            try:
                print(f"[DEBUG] 获取扩展数据用于月线计算: 数据长度{len(data_sorted)}，尝试获取更多历史数据")
                # 获取更多历史数据用于月线计算
                extended_data = get_historical_data(
                    data.index[0].strftime('%Y-%m-%d'), 
                    data.index[-1].strftime('%Y-%m-%d'), 
                    24,  # 24个月
                    "ETF"  # 默认类型，可以根据需要调整
                )
                if extended_data is not None and not extended_data.empty:
                    # 合并数据，去重并排序
                    combined_data = pd.concat([data_sorted, extended_data])
                    combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
                    data_sorted = combined_data.sort_index()
                    print(f"[DEBUG] 成功获取扩展数据，长度: {len(extended_data)}")
                    print(f"[DEBUG] 月线计算使用扩展数据，总长度: {len(data_sorted)}")
                else:
                    print(f"[DEBUG] 扩展数据为空，使用原始数据进行月线计算")
            except Exception as e:
                print(f"[DEBUG] 获取扩展数据失败，使用原始数据进行月线计算: {e}")
                # 即使获取扩展数据失败，也继续使用原始数据进行计算
                pass
        
        # 确保数据足够进行重采样
        if period == 'month' and len(data_sorted) < 30:  # 至少需要30天的数据
            print(f"[DEBUG] 数据不足进行月线计算，数据长度: {len(data_sorted)}")
            return (0.0, 0.0, 0.0)
        elif period == 'day' and len(data_sorted) < 4:  # 至少需要4天的数据
            print(f"[DEBUG] 数据不足进行日线计算，数据长度: {len(data_sorted)}")
            return (0.0, 0.0, 0.0)
        
        if period == 'day':
            # 日线数据直接使用原始数据
            period_data = data_sorted.copy()
            print(f"[DEBUG] 日线数据准备完成，数据长度: {len(period_data)}")
        elif period == 'week':
            # 计算周线数据
            period_data = data_sorted.resample('W').agg({
                '开盘': 'first',
                '最高': 'max',
                '最低': 'min',
                '收盘': 'last',
                '成交量': 'sum'
            }).dropna()
            print(f"[DEBUG] 周线重采样完成，数据长度: {len(period_data)}")
        elif period == 'month':
            # 计算月线数据
            print(f"[DEBUG] 开始月线重采样，原始数据长度: {len(data_sorted)}")
            print(f"[DEBUG] 原始数据日期范围: {data_sorted.index[0]} 到 {data_sorted.index[-1]}")
            period_data = data_sorted.resample('M').agg({
                '开盘': 'first',
                '最高': 'max',
                '最低': 'min', 
                '收盘': 'last',
                '成交量': 'sum'
            }).dropna()
            print(f"[DEBUG] 月线重采样完成，数据长度: {len(period_data)}")
            if not period_data.empty:
                print(f"[DEBUG] 月线数据日期范围: {period_data.index[0]} 到 {period_data.index[-1]}")
        else:
            print(f"[DEBUG] 不支持的周期类型: {period}")
            return (0.0, 0.0, 0.0)
        
        if period_data.empty:
            print(f"[DEBUG] {period}线重采样后数据为空，返回0")
            return (0.0, 0.0, 0.0)
        
        # 计算涨跌状态，基于前后两个交易日的收盘价比较
        is_up = pd.Series([False] * len(period_data), index=period_data.index)
        is_down = pd.Series([False] * len(period_data), index=period_data.index)
        
        # 从第二个交易日开始比较收盘价
        for i in range(1, len(period_data)):
            current_close = float(period_data.iloc[i]['收盘'])
            prev_close = float(period_data.iloc[i-1]['收盘'])
            
            if current_close > prev_close:
                # 上涨：当前收盘价高于前一日收盘价
                is_up.iloc[i] = True
            else:
                # 下跌或平盘：当前收盘价低于或等于前一日收盘价，统一算作阴线
                is_down.iloc[i] = True
        
        # 从最新数据开始向前计算连阳天数
        consecutive_up = 0
        consecutive_up_data = []
        
        for i in range(len(period_data) - 1, -1, -1):
            if is_up.iloc[i]:  # 上涨（收盘价高于前一日）
                consecutive_up += 1
                consecutive_up_data.append({
                    'index': i,
                    '开盘': float(period_data['开盘'].iloc[i]),
                    '收盘': float(period_data['收盘'].iloc[i]),
                    '涨跌': float(period_data['收盘'].iloc[i]) - float(period_data['收盘'].iloc[i-1]) if i > 0 else 0,
                    '日期': period_data.index[i]
                })
            else:  # 下跌或平盘，结束连阳
                break
        
        # 如果连阳天数不足4天，返回0
        if consecutive_up < 4:
            return (0.0, 0.0, 0.0)
        
        # 计算4连阳的涨幅（即使当前是5连阳、6连阳等，也要计算4连阳的涨幅）
        # 取最早的4个连阳周期的数据（从最早的连阳周期开始）
        # consecutive_up_data是从最新到最早排列的，所以取最后4个（最早的4个）
        four_consecutive_data = consecutive_up_data[-4:]
        
        # 计算4连阳涨幅（使用与日级趋势涨幅相同的算法）
        # 开始日实体最低价（第1个连阳周期的开盘价和收盘价中的较低者）
        start_low = min(four_consecutive_data[-1]['开盘'], four_consecutive_data[-1]['收盘'])
        # 结束日实体最高价（第4个连阳周期的开盘价和收盘价中的较高者）
        end_high = max(four_consecutive_data[0]['开盘'], four_consecutive_data[0]['收盘'])
        
        trend_gain = end_high - start_low
        
        # 当前周期收盘价，确保为数值类型
        current_price = float(period_data['收盘'].iloc[-1])
        
        # 趋势目标价格 = 第4个月收盘价 + 4连阳涨幅
        # 注意：这里应该使用第4个月收盘价作为基准，而不是当前价格
        fourth_month_close = float(four_consecutive_data[0]['收盘'])
        target_price = fourth_month_close + trend_gain
        
        # 涨幅计算：目标价格相对于当前价格的涨幅百分比
        if current_price > 0:
            trend_gain_pct = ((target_price - current_price) / current_price) * 100
        else:
            trend_gain_pct = 0.0
        
        # 根据周期类型确定显示单位
        period_unit = "天" if period == 'day' else "周" if period == 'week' else "月"
        date_format = '%Y-%m-%d' if period == 'day' else '%Y-%m'
        
        print(f"[DEBUG] {period}线连阳涨幅计算: 当前连阳{consecutive_up}{period_unit}, 计算4连阳涨幅{trend_gain_pct:.2f}%")
        print(f"[DEBUG]   第1{period_unit}(最早): {four_consecutive_data[-1]['日期'].strftime(date_format)} 实体最低价: {start_low:.3f}")
        print(f"[DEBUG]   第4{period_unit}(第4个): {four_consecutive_data[0]['日期'].strftime(date_format)} 实体最高价: {end_high:.3f}")
        print(f"[DEBUG]   4连阳涨幅: {trend_gain:.3f}")
        print(f"[DEBUG]   第4{period_unit}收盘价: {fourth_month_close:.3f}")
        print(f"[DEBUG]   当前价格: {current_price:.3f}")
        print(f"[DEBUG]   目标价格: {target_price:.3f} (第4{period_unit}收盘价 + 4连阳涨幅)")
        
        return (trend_gain_pct, current_price, target_price)
        
    except Exception as e:
        print(f"[DEBUG] 计算{period}线连阳涨幅失败: {e}")
        return (0.0, 0.0, 0.0)


def get_latest_bollinger_breakthrough_type(price_data: pd.DataFrame, 
                                         bollinger_upper: pd.Series, 
                                         bollinger_lower: pd.Series,
                                         resample_freq: str = '5T',
                                         offset: str = '1min') -> str:
    """
    获取最近一次布林带突破的类型
    
    Args:
        price_data: 1分钟K线数据，包含'open', 'close', 'high', 'low'列
        bollinger_upper: 布林带上轨数据
        bollinger_lower: 布林带下轨数据
        resample_freq: 重采样频率，默认'5T'（5分钟）
        offset: 重采样偏移，默认'1min'
        
    Returns:
        最近一次突破类型: 'breakthrough'（涨波上轨突破）、'breakdown'（跌波下轨跌破）、'none'（无突破）
    """
    try:
        if price_data is None or price_data.empty:
            return 'none'
            
        # 重采样到5分钟K线数据
        price_resampled = price_data.resample(resample_freq, offset=offset).agg({
            'open': 'first',
            'high': 'max', 
            'low': 'min',
            'close': 'last'
        }).dropna()
        
        if price_resampled.empty:
            return 'none'
        
        # 按时间倒序检查，找到最近的一次突破
        latest_breakthrough_type = 'none'
        latest_breakthrough_time = None
        
        # 从最新的数据开始检查
        for i, (ts, row) in enumerate(price_resampled.iloc[::-1].iterrows()):
            try:
                # 获取对应的布林带数据
                adjusted_ts = ts + pd.Timedelta(minutes=4)  # 调整时间戳
                
                # 找到最接近的1分钟时间点
                time_diff = np.abs((bollinger_upper.index - adjusted_ts).total_seconds())
                closest_idx = np.argmin(time_diff)
                
                if closest_idx < len(bollinger_upper) and closest_idx < len(bollinger_lower):
                    upper_band = bollinger_upper.iloc[closest_idx]
                    lower_band = bollinger_lower.iloc[closest_idx]
                    
                    # 检查数据有效性
                    if pd.isna(upper_band) or pd.isna(lower_band):
                        continue
                        
                    open_price = row['open']
                    close_price = row['close']
                    high_price = row['high']
                    low_price = row['low']
                    
                    # 数据验证
                    if (pd.isna(open_price) or pd.isna(close_price) or 
                        pd.isna(high_price) or pd.isna(low_price) or
                        open_price == 0 or close_price == 0):
                        continue
                        
                    # 计算K线实体的最高价和最低价
                    entity_high = max(open_price, close_price)  # 实体最高价
                    entity_low = min(open_price, close_price)   # 实体最低价
                    
                    # 检查突破：实体最高价在布林上轨之上，或跳空高开（开盘价直接超过上轨）
                    is_breakthrough = (entity_high > upper_band) or (open_price > upper_band)
                    if is_breakthrough:
                        latest_breakthrough_type = 'breakthrough'
                        latest_breakthrough_time = ts
                        print(f"[DEBUG] 找到最近突破: 时间={ts}, 实体最高价={entity_high:.3f}, 上轨={upper_band:.3f}")
                        break
                    
                    # 检查跌破：实体最低价在布林下轨之下，或跳空低开（开盘价直接低于下轨）
                    is_breakdown = (entity_low < lower_band) or (open_price < lower_band)
                    if is_breakdown:
                        latest_breakthrough_type = 'breakdown'
                        latest_breakthrough_time = ts
                        print(f"[DEBUG] 找到最近跌破: 时间={ts}, 实体最低价={entity_low:.3f}, 下轨={lower_band:.3f}")
                        break
                        
            except Exception as e:
                print(f"[WARNING] 处理K线数据时出错: {e}")
                continue
        
        print(f"[DEBUG] 最近一次布林带突破类型: {latest_breakthrough_type}")
        return latest_breakthrough_type
        
    except Exception as e:
        print(f"[ERROR] 获取最近布林带突破类型失败: {e}")
        return 'none'