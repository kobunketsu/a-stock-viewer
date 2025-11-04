"""Intraday window for 1-minute chart and average cost"""

# 新建文件: 实现分时窗口

import os
import threading
import time as time_module
import tkinter as tk
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import akshare as ak
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from conditions import StockType
from consecutive_surge_signal import ConsecutiveSurgeBuySignal
# 导入分时信号系统
from intraday_signals import (IntradaySignalBase, IntradaySignalManager,
                              LimitUpConsecutiveBuySignal, RSIBuySignal,
                              RSIPlungeSellSignal, RSISellSignal,
                              RSISurgeBuySignal, SupportBreakdownSellSignal)
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
# 新增：导入ETF分析引擎用于获取布林带数据
from stock_analysis_engine import ETFAnalysisEngine
from window_manager import WindowManager  # 新增, 用于窗口置顶


class IntradayWindow:
    """//! 分时窗口(接口锁定)"""

    UPDATE_INTERVAL = 30  # 秒
    
    @staticmethod
    def _get_security_type(code: str) -> tuple:
        """
        获取证券类型和对应的数据接口代码
        :param code: 证券代码
        :return: (security_type, symbol) 元组
        """
        if code == "1A0001" or code == "000001":
            return "INDEX", "000001"
        elif len(code) == 6 and code.startswith(("5", "15")):
            return "ETF", code
        else:
            return "STOCK", code
    
    # 移动平均线周期配置（可调试修改）
    MA_SHORT_PERIOD = 25      # 短期均线周期
    MA_MID_PERIOD = 50        # 中期均线周期
    MA_BASE_PERIOD = 1250     # 基础均线周期（约等于日线MA5，可调试修改为其他值）
    
    # 全局变量：控制是否显示上一个交易日最后1小时数据
    SHOW_PREVIOUS_DAY_DATA = False  # 默认打开，显示上一个交易日数据

    def __init__(self, parent: tk.Widget, code: str, name: str, trade_date: Optional[date] = None, embed: bool = False, show_toolbar: bool = True, on_date_change_callback=None):
        """创建分时窗口
        :param parent: 父级 Tk 窗口
        :param code: 股票代码
        :param name: 股票名称
        :param trade_date: 目标交易日(默认自动检测最近一个交易日)
        :param embed: 是否嵌入模式
        :param show_toolbar: 是否显示工具栏（即使在嵌入模式下）
        :param on_date_change_callback: 日期变化时的回调函数，用于通知日K线图更新垂直贯穿线
        """
        self.parent = parent
        self.code = code
        self.name = name

        # 目标交易日 (若未指定则取最近交易日)
        self.trade_date: date = trade_date or self._get_latest_trade_date()
        self.trade_date_str: str = self.trade_date.strftime("%Y-%m-%d")

        # ------------------------- 窗口/容器 -------------------------
        self.is_embed = embed  # 标记是否嵌入模式
        self.show_toolbar = show_toolbar  # 是否显示工具栏
        self.on_date_change_callback = on_date_change_callback  # 日期变化回调函数
        if self.is_embed:
            # 直接使用传入的父级容器(Frame)作为绘图承载容器
            self.window = parent  # 在嵌入模式中, window 即为父级 Frame
        else:
            # 独立弹窗模式(与原实现保持一致)
            self.window = tk.Toplevel(parent)
            WindowManager.setup_window(self.window)
            self.window.title(f"{name}({code}) - 分时 {self.trade_date_str}")
            self.window.geometry("820x600")
        



        # 顶部工具栏显示逻辑
        if show_toolbar:
            toolbar = tk.Frame(self.window)
            toolbar.pack(fill=tk.X, padx=5, pady=0)  # 移除pady，最小化高度
            
            # 创建居中的交易日期标签
            self.date_label = tk.Label(toolbar, text=self.trade_date_str, font=('Helvetica', 9, 'bold'))
            self.date_label.pack(expand=True)
            
            # 高度比例切换按钮 - 放在工具栏最左侧
            self.ratio_btn = tk.Button(toolbar, text="▲", width=2, height=1, 
                                      command=self._toggle_height_ratio, 
                                      font=('Helvetica', 8))
            self.ratio_btn.place(relx=0.05, rely=0.5, anchor="w")  # 放置在工具栏最左侧
            
            # 交易日导航按钮 - 左按钮（紧贴日期文字左侧）
            self.prev_btn = tk.Button(toolbar, text="←", width=2, height=1, command=self._on_prev_day)
            self.prev_btn.place(relx=0.4, rely=0.5, anchor="e")  # 放置在日期左侧，垂直居中
            
            # 交易日导航按钮 - 右按钮（紧贴日期文字右侧）
            self.next_btn = tk.Button(toolbar, text="→", width=2, height=1, command=self._on_next_day)
            self.next_btn.place(relx=0.6, rely=0.5, anchor="w")  # 放置在日期右侧，垂直居中
            
            # 音效开关按钮
            self.audio_toggle_btn = tk.Button(toolbar, text="🔊", width=2, height=1, 
                                            command=self._toggle_audio, 
                                            font=('Helvetica', 8))
            self.audio_toggle_btn.place(relx=0.8, rely=0.5, anchor="w")  # 放置在右侧
            
            # 总成交量显示按钮
            self.volume_display_btn = tk.Button(toolbar, text="=", width=2, height=1, 
                                              command=self._toggle_volume_display, 
                                              font=('Helvetica', 8))
            self.volume_display_btn.place(relx=0.9, rely=0.5, anchor="w")  # 放置在音效按钮右侧

            # 交易日日历缓存
            self._trade_calendar = self._load_trade_calendar()
            self._update_nav_buttons()
        else:
            # 不显示工具栏，但仍需要初始化相关变量
            self.prev_btn = None
            self.next_btn = None
            self.audio_toggle_btn = None
            self._trade_calendar = self._load_trade_calendar()

        # 键盘快捷键绑定（在有工具栏的情况下）
        if show_toolbar:
            if self.is_embed:
                # 嵌入模式下，绑定到父窗口的根窗口，确保键盘事件能被正确捕获
                root_window = self.window.winfo_toplevel()
                root_window.bind("<Command-Left>", lambda e: self._on_prev_day())
                root_window.bind("<Command-Right>", lambda e: self._on_next_day())
                # 注意：不绑定Command+B到分时窗口，避免与主窗口的截图功能冲突
                print(f"[DEBUG] 嵌入模式：键盘快捷键已绑定到根窗口: {root_window}")
                
                # 额外绑定到当前容器，作为备用方案
                self.window.bind("<Command-Left>", lambda e: self._on_prev_day())
                self.window.bind("<Command-Right>", lambda e: self._on_next_day())
                # 添加音效开关快捷键 Command+Shift+A
                self.window.bind("<Command-Shift-A>", lambda e: self._toggle_audio())                
                # 注意：不绑定Command+B到分时窗口，避免与主窗口的截图功能冲突
                print(f"[DEBUG] 嵌入模式：键盘快捷键也已绑定到当前容器: {self.window}")
            else:
                # 独立窗口模式下，直接绑定到当前窗口
                self.window.bind("<Command-Left>", lambda e: self._on_prev_day())
                self.window.bind("<Command-Right>", lambda e: self._on_next_day())
                # 添加音效开关快捷键 Command+Shift+A
                self.window.bind("<Command-Shift-A>", lambda e: self._toggle_audio())
                # 注意：不绑定Command+B到分时窗口，避免与主窗口的截图功能冲突
                print(f"[DEBUG] 独立模式：键盘快捷键已绑定到当前窗口: {self.window}")

        # 图表
        # 嵌入模式下使用紧凑的图形尺寸，减少顶部和底部空白
        if self.is_embed:
            self.fig: Figure = Figure(figsize=(6, 1.5), dpi=100)  # 进一步减少高度，最小化空白
        else:
            self.fig: Figure = Figure(figsize=(8, 6.5), dpi=100)  # 减少高度，减少空白
        # 三个面板: 价格/成本/RSI，调整高度比例为4:1:3，让价格图更突出，RSI图包含成交量信息
        gs = self.fig.add_gridspec(3, 1, height_ratios=[4, 1, 3])  # 价格图高度为4，成本图为1，RSI图为3
        self.ax_price = self.fig.add_subplot(gs[0])
        # 成本图居中, RSI图在底部（包含成交量信息）
        self.ax_cost = self.fig.add_subplot(gs[1], sharex=self.ax_price)
        self.ax_rsi = self.fig.add_subplot(gs[2], sharex=self.ax_price)
        # 成交量子图单独创建，constraint到价格图表
        self.ax_volume = None  # 将在需要时动态创建
        
        # 立即设置紧凑布局，移除Y轴标签后减少左边距
        self.fig.subplots_adjust(
            left=0.02,    # 减少左边距，因为移除了Y轴标签
            right=0.92,   # 右边距，为y轴数值留出空间
            top=0.95,     # 上边距
            bottom=0.05,  # 底部边距，确保RSI图时间轴可见
            hspace=0.0375, # 子图间距，与K线图窗口保持一致
            wspace=0.02   # 子图水平间距，成交量子图和价格图之间的间距
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.window)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # 嵌入模式下, 由外部决定布局, 此处不再调用 geometry
        # if self.is_embed:
        #     # 让嵌入的 Frame 使用 pack 填满 (仅在Frame类型时)
        #     try:
        #         self.window.pack(fill=tk.BOTH, expand=True)
        #     except AttributeError:
        #         pass  # 如果不是Frame类型，忽略

        # 数据
        self.price_df: Optional[pd.DataFrame] = None
        self.cost_df: Optional[pd.DataFrame] = None
        self.ma5_price: Optional[float] = None
        self.ma10_price: Optional[float] = None
        self.ma20_price: Optional[float] = None
        self.rsi_df: Optional[pd.DataFrame] = None  # RSI数据
        self.kdj_df: Optional[pd.DataFrame] = None  # KDJ数据
        self.ma_short_values: Optional[pd.Series] = None  # 短期移动平均线数据
        self.ma_mid_values: Optional[pd.Series] = None    # 中期移动平均线数据
        self.ma_base_values: Optional[pd.Series] = None   # 基础移动平均线数据
        # 5分钟级别布林带数据
        self.bollinger_5min_upper: Optional[pd.Series] = None  # 5分钟布林带上轨
        self.bollinger_5min_lower: Optional[pd.Series] = None  # 5分钟布林带下轨
        self.bollinger_5min_middle: Optional[pd.Series] = None  # 5分钟布林带中轨(MA20)
        self.buy_signals: List[Dict[str, Any]] = []  # 买入信号列表，初始化为空列表而不是None
        self.sell_signals: List[Dict[str, Any]] = []  # 卖出信号列表，初始化为空列表而不是None
        # 买卖信号延迟检查相关属性
        self.buy_signal_pending: Optional[dict] = None  # 待确认的买入信号
        self.sell_signal_pending: Optional[dict] = None  # 待确认的卖出信号
        self.buy_signal_last_check: Optional[int] = None  # 上次检查买入信号的时间索引
        self.sell_signal_last_check: Optional[int] = None  # 上次检查卖出信号的时间索引

        # 路径
        self.cache_dir = os.path.join(os.path.dirname(__file__), "../data/cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cost_cache_file = os.path.join(
            self.cache_dir,
            f"intraday_cost_{self.code}_{self.trade_date_str}.csv",
        )
        self._load_cached_cost()
        
        # 新增：ETF分析引擎实例，用于获取布林带数据
        self.etf_engine = ETFAnalysisEngine()
        
        # 新增：支撑位和压力位相关属性
        self.support_level: Optional[float] = None
        self.resistance_level: Optional[float] = None
        self.support_type: Optional[str] = None
        self.resistance_type: Optional[str] = None
        self.position_status: Optional[str] = None
        self._support_resistance_calculated = False  # 新增：标记是否已计算

        # 新增：前高价格相关属性
        self.previous_high_price: Optional[float] = None
        self.previous_high_dual_prices: Optional[Dict] = None  # 双价格信息
        self._previous_high_calculated = False

        # 新增：前低价格相关属性
        self.previous_low_price: Optional[float] = None
        self.previous_low_dual_prices: Optional[Dict] = None  # 双价格信息
        self._previous_low_calculated = False

        # 新增：5分钟级别布林带相关属性
        self.bollinger_5min_data: Optional[pd.DataFrame] = None  # 5分钟布林带数据
        self.bollinger_upper: Optional[pd.Series] = None  # 布林带上轨
        self.bollinger_middle: Optional[pd.Series] = None  # 布林带中轨
        self.bollinger_lower: Optional[pd.Series] = None  # 布林带下轨
        self._bollinger_calculated = False  # 标记是否已计算布林带
        
        # 新增：看涨线相关属性
        self.bullish_line_price: Optional[float] = None  # 上个交易日布林带最高点
        self._bullish_line_calculated = False  # 标记是否已计算看涨线
        
        # 新增：看跌线相关属性
        self.bearish_line_price: Optional[float] = None  # 上个交易日布林带最低点
        self._bearish_line_calculated = False  # 标记是否已计算看跌线
        
        # 新增：5分钟K线突破/跌破布林带相关属性
        self.breakthrough_count: int = 0  # 突破次数（实体最高价在布林上轨之上）
        self.breakdown_count: int = 0     # 跌破次数（实体最低价在布林下轨之下）
        self._breakthrough_breakdown_calculated = False  # 标记是否已计算突破跌破次数
        
        # 布林带音效相关属性
        self.bollinger_breakthrough_signals: List[Dict[str, Any]] = []  # 布林带突破信号列表
        self.bollinger_breakdown_signals: List[Dict[str, Any]] = []     # 布林带跌破信号列表
        self.bollinger_breakthrough_consecutive_count = 0  # 布林带突破连续次数
        self.bollinger_breakdown_consecutive_count = 0     # 布林带跌破连续次数
        self.last_bollinger_signal_type = None  # 上一个布林带信号类型
        self._bollinger_signals_processed = False  # 标记布林带信号是否已处理
        
        # 新增：价格范围历史记录，用于防止阻力带和支撑带被裁切
        self._price_range_history: Optional[Dict[str, float]] = None  # 保存历史价格范围
        self._price_range_initialized = False  # 标记价格范围是否已初始化

        # 数据缓存和智能刷新机制
        self._data_cache = {}  # 数据缓存字典
        self._last_data_fetch_time = None  # 上次数据获取时间
        self._last_trade_date = None  # 上次交易的日期
        self._cache_valid_duration = 300  # 缓存有效时间（秒），5分钟
        self._force_refresh = False  # 强制刷新标志
        
        # 历史数据指标缓存机制
        self._historical_cache = {}  # 历史数据缓存字典
        self._cache_key = f"{self.code}_{self.trade_date_str}"  # 当前缓存键
        self._last_cache_key = None  # 上次缓存键，用于检测变更
        
        # UI事件重绘控制
        self._force_redraw = False  # 强制重绘标志
        self._ui_event_redraw = False  # UI事件触发重绘标志

        # 分时信号管理器 - 移到_update_data调用之前
        self.signal_manager = IntradaySignalManager()
        
        # 急涨急跌信号连续计数器和音效控制
        self.surge_signal_consecutive_count = 0  # 急涨信号连续次数
        self.plunge_signal_consecutive_count = 0  # 急跌信号连续次数
        self.last_signal_type = None  # 上一个信号类型，用于判断是否连续
        self.max_consecutive_audio = 1  # 最大连续音效次数
        
        # 音效开关状态
        self.audio_enabled = True  # 默认开启音效
        
        # 总成交量显示状态
        self.volume_display_enabled = False  # 默认关闭总成交量显示
        self.volume_display_lines = []  # 存储总成交量线条对象
        
        # 窗口状态控制
        self._is_destroyed = False  # 标记窗口是否已销毁
        
        # 前一交易日收盘价缓存
        self._cached_previous_close = None
        self._cached_previous_close_date = None
        
        # 配置默认分时信号 - 移到_update_data调用之前
        self._setup_default_signals()

        # 首次加载数据并绘制
        self._update_data()

        # 仅在今日交易日时启动定时刷新
        if self.trade_date == date.today():
            self._schedule_update()

        # 存储价格图右侧百分比轴引用，避免重复绘制
        self._ax_price_pct = None
        # 布局标记: 避免tight_layout多次调用导致子图被不断压缩
        self._tight_layout_done = False
        
        # 十字定位相关变量
        self.crosshair_lines: Optional[list] = None  # 存储十字定位线
        self.crosshair_text: Optional[list] = None   # 存储坐标文本
        self.current_panel: Optional[str] = None     # 当前鼠标所在面板
        
        # 高度比例相关变量
        self.height_ratio_mode: str = "7:3"  # 当前高度比例模式: "3:7" 或 "7:3"
        self.height_ratio_callback = None    # 高度比例变化回调函数
        
    # ------------------------------------------------------------------
    # 急涨急跌信号音效控制
    # ------------------------------------------------------------------
    def _is_surge_plunge_signal(self, signal_name: str) -> tuple[bool, str]:
        """判断是否为急涨急跌信号
        :param signal_name: 信号名称
        :return: (是否为急涨急跌信号, 信号类型: 'surge'/'plunge'/'other')
        """
        if '急涨' in signal_name or 'RSI急涨' in signal_name or 'RSISurge' in signal_name or '连涨' in signal_name:
            return True, 'surge'
        elif '急跌' in signal_name or 'RSI急跌' in signal_name or 'RSIPlunge' in signal_name:
            return True, 'plunge'
        else:
            return False, 'other'
    
    def _update_surge_plunge_counters(self, signal_type: str):
        """更新急涨急跌信号连续计数器
        :param signal_type: 信号类型 ('surge'/'plunge'/'other')
        """
        if signal_type == 'surge':
            if self.last_signal_type == 'surge':
                # 连续急涨信号
                self.surge_signal_consecutive_count += 1
            else:
                # 新的急涨信号序列开始
                self.surge_signal_consecutive_count = 1
                self.plunge_signal_consecutive_count = 0  # 重置急跌计数器
        elif signal_type == 'plunge':
            if self.last_signal_type == 'plunge':
                # 连续急跌信号
                self.plunge_signal_consecutive_count += 1
            else:
                # 新的急跌信号序列开始
                self.plunge_signal_consecutive_count = 1
                self.surge_signal_consecutive_count = 0  # 重置急涨计数器
        else:
            # 其他信号，重置所有计数器
            self.surge_signal_consecutive_count = 0
            self.plunge_signal_consecutive_count = 0
        
        self.last_signal_type = signal_type
    
    def _should_play_audio(self, signal_type: str) -> bool:
        """判断是否应该播放音效
        :param signal_type: 信号类型 ('surge'/'plunge'/'other')
        :return: 是否应该播放音效
        """
        if signal_type == 'surge':
            return self.surge_signal_consecutive_count <= self.max_consecutive_audio
        elif signal_type == 'plunge':
            return self.plunge_signal_consecutive_count <= self.max_consecutive_audio
        else:
            # 其他信号总是播放音效
            return True
    
    def _is_bollinger_signal_realtime(self, signal_timestamp: Optional[pd.Timestamp] = None, threshold_minutes: int = 2) -> bool:
        """判断布林带信号是否为实时信号
        :param signal_timestamp: 信号时间戳
        :param threshold_minutes: 实时信号阈值（分钟）
        :return: 是否为实时信号
        """
        try:
            if signal_timestamp is None:
                return False
                
            # 获取当前时间
            now = pd.Timestamp.now()
            
            # 计算时间差
            time_diff = now - signal_timestamp
            
            # 判断是否在阈值时间内
            return time_diff.total_seconds() <= threshold_minutes * 60
            
        except Exception as e:
            print(f"[ERROR] 判断布林带信号实时性失败: {e}")
            return False
    
    def _update_bollinger_signal_counters(self, signal_type: str):
        """更新布林带信号连续计数器
        :param signal_type: 信号类型 ('breakthrough'/'breakdown'/'other')
        """
        if signal_type == 'breakthrough':
            if self.last_bollinger_signal_type == 'breakthrough':
                # 连续突破信号
                self.bollinger_breakthrough_consecutive_count += 1
            else:
                # 新的突破信号序列开始
                self.bollinger_breakthrough_consecutive_count = 1
                self.bollinger_breakdown_consecutive_count = 0  # 重置跌破计数器
        elif signal_type == 'breakdown':
            if self.last_bollinger_signal_type == 'breakdown':
                # 连续跌破信号
                self.bollinger_breakdown_consecutive_count += 1
            else:
                # 新的跌破信号序列开始
                self.bollinger_breakdown_consecutive_count = 1
                self.bollinger_breakthrough_consecutive_count = 0  # 重置突破计数器
        else:
            # 其他信号，重置所有计数器
            self.bollinger_breakthrough_consecutive_count = 0
            self.bollinger_breakdown_consecutive_count = 0
        
        self.last_bollinger_signal_type = signal_type
    
    def _should_play_bollinger_audio(self, signal_type: str) -> bool:
        """判断是否应该播放布林带音效
        :param signal_type: 信号类型 ('breakthrough'/'breakdown'/'other')
        :return: 是否应该播放音效
        """
        if signal_type == 'breakthrough':
            return self.bollinger_breakthrough_consecutive_count <= self.max_consecutive_audio  # 只播放1次
        elif signal_type == 'breakdown':
            return self.bollinger_breakdown_consecutive_count <= self.max_consecutive_audio  # 只播放1次
        else:
            # 其他信号总是播放音效
            return True
    
    def _notify_plunge_signals_buy_signal_appeared(self):
        """通知连跌信号买入信号已出现"""
        if self.buy_signals:
            # 检查是否有任何买入信号（连涨、急涨、RSI低点做T买入等）
            has_buy_signal = any(
                '连涨' in sig.get('signal_type', '') or 
                '急涨' in sig.get('signal_type', '') or 
                'RSI' in sig.get('signal_type', '') or
                '买入' in sig.get('signal_type', '')
                for sig in self.buy_signals
            )
            
            if has_buy_signal:
                # 通知所有连跌信号买入信号已出现
                for signal in self.signal_manager.sell_signals:
                    if hasattr(signal, 'mark_buy_signal_appeared') and '连跌' in signal.name:
                        signal.mark_buy_signal_appeared()
                        print(f"[DEBUG] 已通知连跌信号买入信号出现: {signal.name}")
    
    def _notify_surge_signals_sell_signal_appeared(self):
        """通知连涨信号卖出信号已出现"""
        if self.sell_signals:
            # 检查是否有任何卖出信号（连跌、急跌、RSI高点做T卖出等）
            has_sell_signal = any(
                '连跌' in sig.get('signal_type', '') or 
                '急跌' in sig.get('signal_type', '') or 
                'RSI' in sig.get('signal_type', '') or
                '卖出' in sig.get('signal_type', '')
                for sig in self.sell_signals
            )
            
            if has_sell_signal:
                # 通知所有连涨信号卖出信号已出现
                for signal in self.signal_manager.buy_signals:
                    if hasattr(signal, 'mark_sell_signal_appeared') and '连涨' in signal.name:
                        signal.mark_sell_signal_appeared()
                        print(f"[DEBUG] 已通知连涨信号卖出信号出现: {signal.name}")

    # ------------------------------------------------------------------
    # 数据获取与缓存
    # ------------------------------------------------------------------
    def _load_cached_cost(self):
        """加载本地缓存的平均成本数据"""
        if os.path.isfile(self.cost_cache_file):
            try:
                self.cost_df = pd.read_csv(self.cost_cache_file, parse_dates=["time"])
            except Exception:
                self.cost_df = pd.DataFrame(columns=["time", "cost"])
        else:
            self.cost_df = pd.DataFrame(columns=["time", "cost"])

    def _append_cost_cache(self, timestamp: datetime, cost: float):
        """追加平均成本到缓存并持久化"""
        if self.cost_df is None:
            self.cost_df = pd.DataFrame(columns=["time", "cost"])
        # 避免重复
        if (self.cost_df["time"] == timestamp).any():
            return
        self.cost_df = pd.concat(
            [self.cost_df, pd.DataFrame({"time": [timestamp], "cost": [cost]})],
            ignore_index=True,
        )
        try:
            self.cost_df.to_csv(self.cost_cache_file, index=False)
        except Exception:
            pass

    def _calculate_5min_bollinger_bands(self, data: pd.DataFrame, window: int = 20, num_std: float = 2) -> pd.DataFrame:
        """计算5分钟级别布林带指标
        
        :param data: 5分钟K线数据
        :param window: 移动平均窗口期，默认20
        :param num_std: 标准差倍数，默认2
        :return: 包含布林带指标的DataFrame
        """
        try:
            # 使用trading_utils中的通用布林带计算函数
            from trading_utils import calculate_bollinger_bands
            return calculate_bollinger_bands(data, window, num_std)
            
        except Exception as e:
            print(f"计算5分钟布林带失败: {e}")
            import traceback
            traceback.print_exc()
            return data

    def _get_cached_bollinger_data(self, data: pd.DataFrame, window: int = 20, num_std: float = 2) -> pd.DataFrame:
        """获取布林带数据（带缓存机制）
        
        :param data: 5分钟K线数据
        :param window: 移动平均窗口期，默认20
        :param num_std: 标准差倍数，默认2
        :return: 包含布林带指标的DataFrame
        """
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 生成数据指纹用于缓存键
            data_fingerprint = f"{len(data)}_{data.index[0]}_{data.index[-1]}" if not data.empty else "empty"
            cache_key = f"bollinger_{data_fingerprint}_{window}_{num_std}"
            
            # 尝试从缓存获取
            cached_bollinger = self._get_cached_data('bollinger_data')
            if cached_bollinger is not None and 'data_fingerprint' in cached_bollinger:
                if cached_bollinger['data_fingerprint'] == data_fingerprint:
                    print(f"[DEBUG] 从缓存获取布林带数据: 数据长度={len(cached_bollinger['data'])}")
                    return cached_bollinger['data']
            
            # 计算布林带
            bollinger_data = self._calculate_5min_bollinger_bands(data, window, num_std)
            
            # 缓存结果
            if bollinger_data is not None and not bollinger_data.empty:
                cache_data = {
                    'data': bollinger_data,
                    'data_fingerprint': data_fingerprint,
                    'window': window,
                    'num_std': num_std
                }
                self._set_cached_data('bollinger_data', cache_data)
                print(f"[DEBUG] 布林带数据已缓存: 数据长度={len(bollinger_data)}")
            
            return bollinger_data
            
        except Exception as e:
            print(f"获取缓存布林带数据失败: {e}")
            # 降级到直接计算
            return self._calculate_5min_bollinger_bands(data, window, num_std)

    # ------------------------------------------------------------------
    # 定时任务
    # ------------------------------------------------------------------
    period = 1
    def _is_trading_time(self):
        """检查当前是否为交易时间"""
        try:
            from datetime import datetime
            
            now = datetime.now()
            
            # 检查是否为工作日
            if now.weekday() >= 5:  # 周六(5)和周日(6)不是交易日
                return False
            
            # 获取当前时间的小时和分钟
            current_time = (now.hour, now.minute)
            
            # 定义交易时间：上午9:30-11:30，下午13:00-15:00
            morning_start = (9, 30)
            morning_end = (11, 30)
            afternoon_start = (13, 0)
            afternoon_end = (15, 0)
            
            # 检查是否在上午交易时间
            if (current_time >= morning_start and current_time <= morning_end):
                return True
            
            # 检查是否在下午交易时间
            if (current_time >= afternoon_start and current_time <= afternoon_end):
                return True
            
            return False
        except Exception as e:
            print(f"[DEBUG] 检查交易时间失败: {e}")
            return True  # 如果检查出错，默认允许更新

    def _should_fetch_data(self):
        """判断是否需要获取新数据"""
        try:
            from datetime import datetime
            
            now = datetime.now()
            current_trade_date = self.trade_date_str
            
            # 如果强制刷新，直接返回True
            if self._force_refresh:
                print("[DEBUG] 强制刷新，需要获取新数据")
                return True
            
            # 如果交易日期发生变化，需要获取新数据
            if self._last_trade_date != current_trade_date:
                print(f"[DEBUG] 交易日期变化: {self._last_trade_date} -> {current_trade_date}，需要获取新数据")
                return True
            
            # 如果从未获取过数据，需要获取
            if self._last_data_fetch_time is None:
                print("[DEBUG] 首次获取数据")
                return True
            
            # 检查缓存是否过期
            time_since_last_fetch = (now - self._last_data_fetch_time).total_seconds()
            if time_since_last_fetch > self._cache_valid_duration:
                print(f"[DEBUG] 缓存过期({time_since_last_fetch:.1f}秒)，需要获取新数据")
                return True
            
            # 在交易时间内，需要更频繁更新
            if self._is_trading_time():
                # 交易时间内，每30秒更新一次
                if time_since_last_fetch > 30:
                    print(f"[DEBUG] 交易时间内，需要更新数据({time_since_last_fetch:.1f}秒)")
                    return True
            
            print(f"[DEBUG] 使用缓存数据，距离上次获取: {time_since_last_fetch:.1f}秒")
            return False
            
        except Exception as e:
            print(f"[DEBUG] 判断是否需要获取数据失败: {e}")
            return True  # 如果判断出错，默认获取数据

    def _update_cache_timestamp(self):
        """更新缓存时间戳"""
        from datetime import datetime
        self._last_data_fetch_time = datetime.now()
        self._last_trade_date = self.trade_date_str
        self._force_refresh = False

    def _get_cache_key(self, code: str = None, trade_date: str = None) -> str:
        """生成缓存键
        :param code: 股票代码，默认使用当前代码
        :param trade_date: 交易日，默认使用当前交易日
        :return: 缓存键
        """
        code = code or self.code
        trade_date = trade_date or self.trade_date_str
        return f"{code}_{trade_date}"

    def _is_cache_valid(self, cache_key: str, data_type: str) -> bool:
        """检查缓存是否有效
        :param cache_key: 缓存键
        :param data_type: 数据类型
        :return: 缓存是否有效
        """
        if cache_key not in self._historical_cache:
            return False
        
        if data_type not in self._historical_cache[cache_key]:
            return False
        
        cache_data = self._historical_cache[cache_key][data_type]
        if 'timestamp' not in cache_data:
            return False
        
        # 检查缓存是否过期（历史数据缓存时间更长）
        from datetime import datetime, timedelta
        cache_time = cache_data['timestamp']
        if isinstance(cache_time, str):
            cache_time = datetime.fromisoformat(cache_time)
        
        # 根据数据类型设置不同的缓存策略
        if data_type in ['previous_close', 'support_resistance', 'previous_high', 'previous_low', 'bullish_line', 'bearish_line']:
            # 完全静态的历史数据指标：当天不会变化，缓存1小时
            cache_duration = 3600  # 1小时
        elif data_type in ['ma_prices']:
            # 日级MA指标：基于日线数据，当天收盘前不会变化，缓存1小时
            cache_duration = 3600  # 1小时
        elif data_type in ['bollinger_data']:
            # 5分钟布林带：需要当日分时数据，会实时变化，缓存5分钟
            cache_duration = 300  # 5分钟
        else:
            # 其他数据：默认1小时
            cache_duration = 3600  # 1小时
        
        return (datetime.now() - cache_time).total_seconds() < cache_duration

    def _get_cached_data(self, data_type: str, cache_key: str = None) -> Optional[Any]:
        """获取缓存数据
        :param data_type: 数据类型
        :param cache_key: 缓存键，默认使用当前缓存键
        :return: 缓存数据，如果不存在或无效则返回None
        """
        cache_key = cache_key or self._cache_key
        
        if not self._is_cache_valid(cache_key, data_type):
            return None
        
        return self._historical_cache[cache_key][data_type]['data']

    def _set_cached_data(self, data_type: str, data: Any, cache_key: str = None):
        """设置缓存数据
        :param data_type: 数据类型
        :param data: 要缓存的数据
        :param cache_key: 缓存键，默认使用当前缓存键
        """
        from datetime import datetime
        
        cache_key = cache_key or self._cache_key
        
        if cache_key not in self._historical_cache:
            self._historical_cache[cache_key] = {}
        
        self._historical_cache[cache_key][data_type] = {
            'data': data,
            'timestamp': datetime.now().isoformat()
        }

    def _invalidate_cache(self, cache_key: str = None):
        """使缓存失效
        :param cache_key: 缓存键，默认使用当前缓存键
        """
        cache_key = cache_key or self._cache_key
        if cache_key in self._historical_cache:
            del self._historical_cache[cache_key]

    def _check_cache_key_change(self):
        """检查缓存键是否发生变化，如果变化则清理旧缓存"""
        current_key = self._get_cache_key()
        if self._last_cache_key and self._last_cache_key != current_key:
            print(f"[DEBUG] 缓存键变化: {self._last_cache_key} -> {current_key}，清理旧缓存")
            self._invalidate_cache(self._last_cache_key)
        self._last_cache_key = current_key
        self._cache_key = current_key

    def _clear_all_caches(self):
        """清理所有缓存数据"""
        try:
            # 清理历史数据缓存
            self._historical_cache.clear()
            
            # 清理旧缓存
            self._cached_previous_close = None
            self._cached_previous_close_date = None
            
            # 重置计算标记
            self._support_resistance_calculated = False
            self._previous_high_calculated = False
            self._previous_low_calculated = False
            self._bollinger_calculated = False
            self._bullish_line_calculated = False
            self._bearish_line_calculated = False
            self._breakthrough_breakdown_calculated = False
            self._bollinger_signals_processed = False
            
            # 重置价格范围历史
            self._price_range_history = None
            self._price_range_initialized = False
            
            print("[DEBUG] 所有缓存已清理")
            
        except Exception as e:
            print(f"[ERROR] 清理缓存失败: {e}")

    def _update_trade_date(self, new_trade_date: date):
        """更新交易日（带缓存清理）"""
        try:
            old_trade_date = self.trade_date
            old_trade_date_str = self.trade_date_str
            
            # 更新交易日
            self.trade_date = new_trade_date
            self.trade_date_str = new_trade_date.strftime("%Y-%m-%d")
            
            # 清理缓存（交易日变更时）
            self._clear_all_caches()
            print(f"[DEBUG] 交易日变更，清理所有缓存: {old_trade_date_str} -> {self.trade_date_str}")
            
            # 更新缓存键
            self._cache_key = self._get_cache_key()
            self._last_cache_key = None
            
            # 更新日期标签
            if hasattr(self, 'date_label') and self.date_label:
                self.date_label.config(text=self.trade_date_str)
            
            # 通知日K线图更新垂直贯穿线位置
            if self.on_date_change_callback:
                try:
                    self.on_date_change_callback(self.trade_date_str)
                except Exception as e:
                    print(f"调用日期变化回调函数失败: {e}")
            
            # 重新加载数据
            self._update_data()
            
        except Exception as e:
            print(f"[ERROR] 更新交易日失败: {e}")
            import traceback
            traceback.print_exc()

    def get_cache_status(self) -> dict:
        """获取缓存状态信息"""
        try:
            status = {
                'cache_key': self._cache_key,
                'last_cache_key': self._last_cache_key,
                'historical_cache_size': len(self._historical_cache),
                'cached_data_types': list(self._historical_cache.get(self._cache_key, {}).keys()) if self._cache_key in self._historical_cache else [],
                'previous_close_cached': self._cached_previous_close is not None,
                'support_resistance_calculated': self._support_resistance_calculated,
                'bollinger_calculated': self._bollinger_calculated,
                'cache_valid_duration': self._cache_valid_duration
            }
            return status
        except Exception as e:
            print(f"[ERROR] 获取缓存状态失败: {e}")
            return {}

    def test_cache_performance(self) -> dict:
        """测试缓存性能"""
        try:
            import time

            # 测试移动平均线缓存
            start_time = time.time()
            ma_result = self._get_ma_prices()
            ma_time = time.time() - start_time
            
            # 测试前一交易日收盘价缓存
            start_time = time.time()
            prev_close = self._get_previous_close()
            prev_close_time = time.time() - start_time
            
            # 测试支撑位压力位缓存
            start_time = time.time()
            self._calculate_support_resistance()
            sr_time = time.time() - start_time
            
            performance = {
                'ma_calculation_time': ma_time,
                'prev_close_calculation_time': prev_close_time,
                'support_resistance_calculation_time': sr_time,
                'total_time': ma_time + prev_close_time + sr_time,
                'cache_hit_ratio': self._calculate_cache_hit_ratio()
            }
            
            print(f"[DEBUG] 缓存性能测试结果: {performance}")
            return performance
            
        except Exception as e:
            print(f"[ERROR] 缓存性能测试失败: {e}")
            return {}

    def _calculate_cache_hit_ratio(self) -> float:
        """计算缓存命中率"""
        try:
            if not self._historical_cache:
                return 0.0
            
            total_requests = 0
            cache_hits = 0
            
            for cache_key, cache_data in self._historical_cache.items():
                for data_type, data_info in cache_data.items():
                    total_requests += 1
                    if 'timestamp' in data_info:
                        cache_hits += 1
            
            return cache_hits / total_requests if total_requests > 0 else 0.0
            
        except Exception as e:
            print(f"[ERROR] 计算缓存命中率失败: {e}")
            return 0.0

    def _schedule_update(self):
        """智能定时刷新，根据交易时间和数据变化情况优化调用频率"""
        # 检查窗口是否已销毁
        if self._is_destroyed:
            return
            
        if not self.window.winfo_exists():
            self._is_destroyed = True
            return

        # 智能判断是否需要获取数据
        need_update = self._should_fetch_data()
        is_trading_time = self._is_trading_time()
        
        if need_update:
            threading.Thread(target=self._update_data, daemon=True).start()
        elif is_trading_time:
            # 交易时间内，即使使用缓存数据也需要重绘（价格可能变化）
            threading.Thread(target=self._update_display_from_cache, daemon=True).start()
        else:
            # 非交易时间，检查是否有必要重绘
            if self._should_redraw():
                threading.Thread(target=self._update_display_from_cache, daemon=True).start()
        
        # 根据交易时间调整下次更新间隔
        next_interval = self._get_next_update_interval()
        self.window.after(next_interval * 1000, self._schedule_update)

    def _should_redraw(self) -> bool:
        """判断是否需要重绘（非交易时间优化）"""
        try:
            from datetime import datetime

            # 强制重绘标志（用于UI事件）
            if self._force_redraw or self._ui_event_redraw:
                self._force_redraw = False
                self._ui_event_redraw = False
                print("[DEBUG] 强制重绘：UI事件触发")
                return True
            
            # 如果窗口刚创建或数据刚更新，需要重绘
            if not hasattr(self, '_last_redraw_time'):
                self._last_redraw_time = datetime.now()
                return True
            
            # 检查距离上次重绘的时间
            now = datetime.now()
            time_since_last_redraw = (now - self._last_redraw_time).total_seconds()
            
            # 非交易时间，减少重绘频率
            if not self._is_trading_time():
                # 非交易时间：每5分钟重绘一次
                if time_since_last_redraw > 300:  # 5分钟
                    self._last_redraw_time = now
                    return True
                return False
            
            # 交易时间：保持原有频率
            return True
            
        except Exception as e:
            print(f"[DEBUG] 判断是否需要重绘失败: {e}")
            return True  # 出错时默认重绘

    def _get_next_update_interval(self) -> int:
        """根据交易时间获取下次更新间隔"""
        try:
            is_trading_time = self._is_trading_time()
            
            if is_trading_time:
                # 交易时间：30秒更新一次
                return 30
            else:
                # 非交易时间：5分钟更新一次
                return 300
                
        except Exception as e:
            print(f"[DEBUG] 获取更新间隔失败: {e}")
            return 30  # 默认30秒

    def destroy(self):
        """销毁窗口并停止所有定时任务"""
        self._is_destroyed = True
        if hasattr(self, 'window') and self.window.winfo_exists():
            self.window.destroy()

    def _update_display_from_cache(self):
        """使用缓存数据更新显示，不进行网络请求"""
        # 检查窗口是否已销毁
        if self._is_destroyed:
            return
            
        try:
            print("[DEBUG] 使用缓存数据更新显示")
            
            # 检查是否有缓存数据
            if not hasattr(self, 'price_df') or self.price_df is None or self.price_df.empty:
                print("[DEBUG] 无缓存数据可用，跳过显示更新")
                return
            
            # 只进行必要的计算，不进行网络请求
            self._calculate_indicators_from_cache()
            
            # 重新绘制图表
            if hasattr(self, 'window') and self.window and self.window.winfo_exists():
                self.window.after(0, self._draw)
                
        except Exception as e:
            print(f"[DEBUG] 使用缓存数据更新显示失败: {e}")

    def _calculate_indicators_from_cache(self):
        """从缓存数据计算指标，避免网络请求"""
        try:
            print("[DEBUG] 从缓存数据计算指标")
            
            # 只计算必要的指标，跳过需要网络请求的部分
            if hasattr(self, 'price_df') and self.price_df is not None and not self.price_df.empty:
                # 计算基础均线（如果有数据）
                if len(self.price_df) >= self.MA_BASE_PERIOD:
                    self.ma_base_values = self.price_df['close'].rolling(window=self.MA_BASE_PERIOD, min_periods=1).mean()
                else:
                    self.ma_base_values = None
                
                # 跳过需要网络请求的指标计算
                print("[DEBUG] 缓存模式：跳过需要网络请求的指标计算")
                
        except Exception as e:
            print(f"[DEBUG] 从缓存计算指标失败: {e}")

    def _update_data(self):
        """拉取分时价格与平均成本数据"""
        # 检查窗口是否已销毁
        if self._is_destroyed:
            return
            
        try:
            print("[DEBUG] 开始获取新数据")
            start_dt = f"{self.trade_date_str} 09:30:00"
            end_dt = f"{self.trade_date_str} 15:00:00"
            
            # 获取证券类型和对应的数据接口代码
            security_type, symbol = self._get_security_type(self.code)
            
            if security_type == "INDEX":
                # 使用指数分时数据接口
                print(f"[DEBUG] 获取指数分时数据: {self.code} -> {symbol}, 时间: {start_dt} 到 {end_dt}, 周期: {self.period}")
                price_df = ak.index_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),
                )
                print(f"[DEBUG] 指数分时数据获取结果: {len(price_df)} 条记录")
                if not price_df.empty:
                    print(f"[DEBUG] 指数分时数据列名: {list(price_df.columns)}")
            elif security_type == "ETF":
                # 使用ETF分时数据接口
                print(f"[DEBUG] 获取ETF分时数据: {self.code}, 时间: {start_dt} 到 {end_dt}, 周期: {self.period}")
                price_df = ak.fund_etf_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),
                    adjust="",
                )
                print(f"[DEBUG] ETF分时数据获取结果: {len(price_df)} 条记录")
                if not price_df.empty:
                    print(f"[DEBUG] ETF分时数据列名: {list(price_df.columns)}")
            else:
                # 使用股票分时数据接口
                print(f"[DEBUG] 获取股票分时数据: {self.code}, 时间: {start_dt} 到 {end_dt}, 周期: {self.period}")
                price_df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),  # 改为5分钟采样
                    adjust="",
                )
                print(f"[DEBUG] 股票分时数据获取结果: {len(price_df)} 条记录")
                if not price_df.empty:
                    print(f"[DEBUG] 股票分时数据列名: {list(price_df.columns)}")
                    print(f"[DEBUG] 股票分时数据前5行:")
                    print(price_df.head())
            
            # 如果分时数据为空（如9:25前），仍然需要计算支撑带和压力带
            if price_df.empty:
                print(f"[DEBUG] 分时数据为空，但继续计算支撑带和压力带")
                # 创建一个空的数据框，但继续执行后续的支撑带和压力带计算
                price_df = pd.DataFrame(columns=['datetime', 'open', 'close', 'high', 'low', 'volume'])
                price_df['datetime'] = pd.to_datetime(price_df['datetime'])
                price_df.set_index('datetime', inplace=True)
                self.price_df = price_df
                
                # 即使没有分时数据，也要计算支撑带和压力带
                if not self._support_resistance_calculated:
                    try:
                        print("[DEBUG] 分时数据为空，但仍计算支撑位和压力位")
                        self._calculate_support_resistance()
                    except Exception as e:
                        print(f"[DEBUG] 计算支撑位和压力位失败: {e}")
                
                # 计算前高前低价格
                self._calculate_previous_high_low_prices()
                
                # 即使没有分时数据，也要计算看涨线和看跌线
                if not self._bullish_line_calculated:
                    try:
                        print("[DEBUG] 分时数据为空，但仍计算看涨线")
                        self._calculate_bullish_line()
                    except Exception as e:
                        print(f"[DEBUG] 计算看涨线失败: {e}")
                
                if not self._bearish_line_calculated:
                    try:
                        print("[DEBUG] 分时数据为空，但仍计算看跌线")
                        self._calculate_bearish_line()
                    except Exception as e:
                        print(f"[DEBUG] 计算看跌线失败: {e}")
                
                # 绘图（显示支撑带和压力带，即使没有分时数据）
                self.window.after(0, self._draw)
                return
            # 调试：检查原始数据列名
            print(f"[DEBUG] 原始数据列名: {list(price_df.columns)}")
            print(f"[DEBUG] 原始数据前5行:")
            print(price_df.head())
            
            # 统一列 - 包含所有必要的列
            # 根据AKShare文档，不同证券类型的分时数据列名可能不同
            # 先检查实际的列名，然后进行映射
            print(f"[DEBUG] 实际列名: {list(price_df.columns)}")
            
            # 根据实际列名进行映射
            column_mapping = {}
            
            # 时间列映射
            if "时间" in price_df.columns:
                column_mapping["时间"] = "datetime"
            elif "datetime" in price_df.columns:
                column_mapping["datetime"] = "datetime"
            
            # 价格列映射 - 检查多种可能的列名
            price_columns = {
                "open": ["开盘", "开盘价", "open"],
                "close": ["收盘", "收盘价", "close"],
                "high": ["最高", "最高价", "high"],
                "low": ["最低", "最低价", "low"],
                "volume": ["成交量", "成交额", "volume", "vol"]
            }
            
            for target_col, possible_names in price_columns.items():
                for possible_name in possible_names:
                    if possible_name in price_df.columns:
                        column_mapping[possible_name] = target_col
                        break
            
            print(f"[DEBUG] 列名映射: {column_mapping}")
            
            # 应用列名映射
            if column_mapping:
                price_df.rename(columns=column_mapping, inplace=True)
            
            # 检查映射后是否有所需的列
            required_columns = ['open', 'close', 'high', 'low', 'volume']
            missing_columns = [col for col in required_columns if col not in price_df.columns]
            if missing_columns:
                print(f"[ERROR] 映射后仍缺少必要的列: {missing_columns}")
                print(f"[ERROR] 当前列名: {list(price_df.columns)}")
                # 尝试使用收盘价填充缺失的列
                if 'close' in price_df.columns:
                    for col in missing_columns:
                        if col != 'volume':
                            price_df[col] = price_df['close']
                        else:
                            price_df[col] = 0
                    print(f"[WARNING] 使用收盘价填充缺失的列: {missing_columns}")
                else:
                    print(f"[ERROR] 无法修复缺失的列，跳过数据处理")
                    return
            
            # 调试：检查映射后的数据
            print(f"[DEBUG] 映射后数据列名: {list(price_df.columns)}")
            print(f"[DEBUG] 映射后数据前5行:")
            print(price_df.head())
            print(f"[DEBUG] 映射后数据类型:")
            print(price_df.dtypes)
            
            # 最终验证：确保所有必要的列都存在且有效
            final_validation_passed = True
            for col in ['open', 'close', 'high', 'low', 'volume']:
                if col not in price_df.columns:
                    print(f"[ERROR] 最终验证失败：缺少列 {col}")
                    final_validation_passed = False
                elif price_df[col].isna().all():
                    print(f"[ERROR] 最终验证失败：列 {col} 全部为NaN")
                    final_validation_passed = False
                elif (price_df[col] == 0).all():
                    print(f"[WARNING] 列 {col} 全部为0，可能需要特殊处理")
            
            # 特殊处理：对于分时数据，akshare通常只提供收盘价，其他价格字段为0
            # 我们需要使用收盘价来填充开盘价、最高价和最低价
            if (price_df['open'] == 0).all() and (price_df['close'] != 0).any():
                print(f"[INFO] 检测到分时数据开盘价为0，使用收盘价填充开盘价、最高价和最低价")
                price_df['open'] = price_df['close']
                price_df['high'] = price_df['close']
                price_df['low'] = price_df['close']
                print(f"[INFO] 价格字段填充完成，收盘价范围: {price_df['close'].min():.4f} - {price_df['close'].max():.4f}")
            
            if not final_validation_passed:
                print(f"[ERROR] 数据验证失败，跳过后续处理")
                return
            price_df["datetime"] = pd.to_datetime(price_df["datetime"])
            price_df.set_index("datetime", inplace=True)
            
            # 如果启用显示上一个交易日数据，则合并上一个交易日最后1小时数据
            if self.SHOW_PREVIOUS_DAY_DATA:
                prev_day_last_hour = self._get_previous_day_last_hour_data()
                if prev_day_last_hour is not None and not prev_day_last_hour.empty:
                    # 将上一个交易日最后1小时数据添加到当前数据前面
                    combined_df = pd.concat([prev_day_last_hour, price_df])
                    self.price_df = combined_df
                    print(f"[DEBUG] 合并上一个交易日最后1小时数据，总数据长度: {len(combined_df)}")
                else:
                    self.price_df = price_df
                    print(f"[DEBUG] 未获取到上一个交易日最后1小时数据，使用当日数据")
            else:
                self.price_df = price_df
                print(f"[DEBUG] 未启用显示上一个交易日数据，使用当日数据")
            
            # 计算RSI指标
            try:
                from audio_notifier import (notify_buy_signal,
                                            notify_sell_signal)
                from indicators import (calculate_intraday_kdj,
                                        calculate_intraday_rsi, calculate_rsi)

                # 获取多个前一交易日的分时数据，确保有足够的历史数据计算RSI
                multiple_prev_data = self._get_multiple_previous_trading_days_intraday()
                
                if multiple_prev_data is not None and not multiple_prev_data.empty:
                    # 使用多个前一交易日的分时数据，确保有足够的历史数据
                    # 将多个前一交易日数据与当日数据合并
                    price_df_with_prev = pd.concat([multiple_prev_data, price_df])
                    print(f"[DEBUG] 成功合并多个前一交易日分时数据用于RSI计算")
                    print(f"[DEBUG] 多个前一交易日数据长度: {len(multiple_prev_data)}")
                    print(f"[DEBUG] 当日数据长度: {len(price_df)}")
                    print(f"[DEBUG] 合并后总长度: {len(price_df_with_prev)}")
                    print(f"[DEBUG] 多个前一交易日最后几个价格: {multiple_prev_data['close'].tail(3).values}")
                    print(f"[DEBUG] 当日开盘几个价格: {price_df['close'].head(3).values}")
                else:
                    # 如果无法获取多个前一交易日分时数据，尝试获取单个前一交易日数据
                    prev_intraday_df = self._get_previous_trading_day_intraday()
                    
                    if prev_intraday_df is not None and not prev_intraday_df.empty:
                        # 使用前一交易日的分时数据，确保有足够的历史数据
                        # 将前一交易日数据与当日数据合并
                        price_df_with_prev = pd.concat([prev_intraday_df, price_df])
                        print(f"[DEBUG] 成功合并前一交易日分时数据用于RSI计算")
                        print(f"[DEBUG] 前一交易日数据长度: {len(prev_intraday_df)}")
                        print(f"[DEBUG] 当日数据长度: {len(price_df)}")
                        print(f"[DEBUG] 合并后总长度: {len(price_df_with_prev)}")
                        print(f"[DEBUG] 前一交易日最后几个价格: {prev_intraday_df['close'].tail(3).values}")
                        print(f"[DEBUG] 当日开盘几个价格: {price_df['close'].head(3).values}")
                    else:
                        # 如果无法获取前一交易日分时数据，回退到使用收盘价
                        prev_close = self._get_previous_close()
                        if prev_close is not None:
                            # 创建包含前一日收盘价的数据框
                            prev_datetime = pd.Timestamp(f"{self.trade_date_str} 09:29:00")
                            prev_row = pd.DataFrame({
                                'open': [prev_close],
                                'close': [prev_close],
                                'volume': [0]
                            }, index=[prev_datetime])
                            
                            # 将前一日数据与当日数据合并
                            price_df_with_prev = pd.concat([prev_row, price_df])
                            print(f"[DEBUG] 使用前一交易日收盘价用于RSI计算，总数据点: {len(price_df_with_prev)}")
                            print(f"[DEBUG] 前一交易日收盘价: {prev_close}")
                        else:
                            price_df_with_prev = price_df
                            print(f"[DEBUG] 无法获取前一交易日数据，使用当日数据用于RSI计算，总数据点: {len(price_df_with_prev)}")

                # 修复：每日RSI独立计算，为每个交易日单独计算RSI
                # 计算当日RSI数据（使用Wilder平滑法，与5分钟RSI6保持一致）
                prev_close = self._get_previous_close()
                if prev_close is not None:
                    rsi_1min_6_today = calculate_intraday_rsi(price_df, period=6, price_col="close", 
                                                             session_start_time="09:30", previous_close=prev_close)
                else:
                    rsi_1min_6_today = calculate_intraday_rsi(price_df, period=6, price_col="close", 
                                                             session_start_time="09:30")
                
                # 12和24周期RSI仍使用EMA方法（保持原有逻辑）
                rsi_12_today = calculate_rsi(price_df, period=12, price_col="close")
                rsi_24_today = calculate_rsi(price_df, period=24, price_col="close")
                
                # 计算当日5分钟级别的RSI6（使用新的分时RSI计算方法）
                price_df_5min_today = price_df.resample('5T', offset='1T').agg({
                    'open': 'first',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
                
                # 获取历史数据用于5分钟RSI6计算
                historical_5min_data = self._get_historical_5min_data_for_rsi()
                
                if historical_5min_data is not None and not historical_5min_data.empty:
                    # 合并历史数据和当日数据
                    combined_5min_data = pd.concat([historical_5min_data, price_df_5min_today])
                    print(f"[DEBUG] 合并历史5分钟数据用于RSI计算，总长度: {len(combined_5min_data)}")
                    
                    # 使用合并后的数据计算5分钟RSI6
                    rsi_5min_6_combined = calculate_intraday_rsi(combined_5min_data, period=6, price_col="close", 
                                                               session_start_time="09:30")
                    
                    # 只保留当日部分的RSI数据
                    rsi_5min_6_today = rsi_5min_6_combined.iloc[len(historical_5min_data):]
                    print(f"[DEBUG] 使用历史数据计算5分钟RSI6，当日数据长度: {len(rsi_5min_6_today)}")
                else:
                    # 没有历史数据时，使用前一交易日收盘价
                    prev_close = self._get_previous_close()
                    if prev_close is not None:
                        rsi_5min_6_today = calculate_intraday_rsi(price_df_5min_today, period=6, price_col="close", 
                                                                 session_start_time="09:30", previous_close=prev_close)
                    else:
                        # 如果无法获取前一交易日收盘价，使用默认计算方式
                        rsi_5min_6_today = calculate_intraday_rsi(price_df_5min_today, period=6, price_col="close", 
                                                                 session_start_time="09:30")
                
                # 为信号计算保持数学准确性：使用前向填充
                rsi_5min_6_1min_today_signal = self._interpolate_5min_rsi_to_1min(rsi_5min_6_today, price_df.index, for_display_only=False)
                # 为显示效果：使用线性插值
                rsi_5min_6_1min_today_display = self._interpolate_5min_rsi_to_1min(rsi_5min_6_today, price_df.index, for_display_only=True)
                
                print(f"[DEBUG] 5分钟RSI6计算完成，数据长度: {len(price_df_5min_today)}")
                print(f"[DEBUG] 5分钟RSI6前5个值: {rsi_5min_6_today.head().values}")
                print(f"[DEBUG] 5分钟RSI6后5个值: {rsi_5min_6_today.tail().values}")
                
                print(f"[DEBUG] 当日RSI计算完成，数据长度: {len(price_df)}")
                
                # 计算上一个交易日的RSI数据（如果存在）
                prev_rsi_1min_6 = None
                prev_rsi_12 = None
                prev_rsi_24 = None
                prev_rsi_5min_6_1min = None
                
                if len(price_df_with_prev) > len(price_df):
                    # 有上一个交易日数据，独立计算其RSI
                    prev_day_data = price_df_with_prev.iloc[:len(price_df_with_prev) - len(price_df)]
                    print(f"[DEBUG] 上一个交易日数据长度: {len(prev_day_data)}")
                    print(f"[DEBUG] 上一个交易日价格范围: [{prev_day_data['close'].min():.2f}, {prev_day_data['close'].max():.2f}]")
                    
                    # 检查数据长度是否足够计算RSI
                    if len(prev_day_data) >= 6:
                        # 计算上一个交易日的RSI（使用Wilder平滑法，与当日RSI6保持一致）
                        prev_prev_close = self._get_previous_close_for_prev_day()
                        if prev_prev_close is not None:
                            prev_rsi_1min_6 = calculate_intraday_rsi(prev_day_data, period=6, price_col="close", 
                                                                   session_start_time="09:30", previous_close=prev_prev_close)
                        else:
                            prev_rsi_1min_6 = calculate_intraday_rsi(prev_day_data, period=6, price_col="close", 
                                                                   session_start_time="09:30")
                        print(f"[DEBUG] 上一个交易日RSI6前5个值: {prev_rsi_1min_6.head().values}")
                        print(f"[DEBUG] 上一个交易日RSI6后5个值: {prev_rsi_1min_6.tail().values}")
                        
                        if len(prev_day_data) >= 12:
                            prev_rsi_12 = calculate_rsi(prev_day_data, period=12, price_col="close")
                        else:
                            prev_rsi_12 = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                        
                        if len(prev_day_data) >= 24:
                            prev_rsi_24 = calculate_rsi(prev_day_data, period=24, price_col="close")
                        else:
                            prev_rsi_24 = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                        
                        # 计算上一个交易日的5分钟RSI（使用新的分时RSI计算方法）
                        prev_day_5min = prev_day_data.resample('5T', offset='1T').agg({
                            'open': 'first',
                            'close': 'last',
                            'volume': 'sum'
                        }).dropna()
                        
                        if not prev_day_5min.empty:
                            # 使用新的分时RSI计算方法，支持开盘阶段即时滚动输出
                            # 获取上一个交易日的前一交易日收盘价
                            prev_prev_close = None
                            if len(prev_day_data) > 0:
                                # 这里需要获取上一个交易日的前一交易日收盘价
                                # 暂时使用上一个交易日的第一根K线价格作为参考
                                prev_prev_close = prev_day_data.iloc[0]['close']
                            
                            if prev_prev_close is not None:
                                prev_rsi_5min_6 = calculate_intraday_rsi(prev_day_5min, period=6, price_col="close", 
                                                                       session_start_time="09:30", previous_close=prev_prev_close)
                            else:
                                prev_rsi_5min_6 = calculate_intraday_rsi(prev_day_5min, period=6, price_col="close", 
                                                                       session_start_time="09:30")
                            # 使用线性插值实现平滑过渡，与主流软件保持一致
                            prev_rsi_5min_6_1min = self._interpolate_5min_rsi_to_1min(prev_rsi_5min_6, prev_day_data.index)
                            print(f"[DEBUG] 上一个交易日5分钟RSI6计算完成，数据长度: {len(prev_day_5min)}")
                        else:
                            # 上一个交易日5分钟数据为空时，使用中性值
                            print(f"[DEBUG] 上一个交易日5分钟数据为空，使用中性值")
                            prev_rsi_5min_6_1min = pd.Series([50.0] * len(prev_day_data), index=prev_day_data.index)
                        
                        print(f"[DEBUG] 上一个交易日RSI计算完成")
                    else:
                        print(f"[DEBUG] 上一个交易日数据长度不足，无法计算RSI")
                        prev_rsi_1min_6 = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                        prev_rsi_12 = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                        prev_rsi_24 = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                        prev_rsi_5min_6_1min = pd.Series([np.nan] * len(prev_day_data), index=prev_day_data.index)
                
                # 使用当日RSI数据
                rsi_1min_6_display = rsi_1min_6_today
                rsi_12_display = rsi_12_today
                rsi_24_display = rsi_24_today
                print(f"[DEBUG] RSI计算完成，每日独立计算，互不影响")
                
                # 创建RSI数据框
                if self.SHOW_PREVIOUS_DAY_DATA and len(self.price_df) > len(price_df) and prev_rsi_1min_6 is not None:
                    # 有上一个交易日数据且已计算其RSI，创建包含两个交易日RSI的数据框
                    print(f"[DEBUG] 创建包含两个交易日RSI的数据框")
                    print(f"[DEBUG] 显示数据长度: {len(self.price_df)}, 当日数据长度: {len(price_df)}")
                    
                    # 检查数据长度匹配
                    prev_day_length = len(self.price_df) - len(price_df)
                    print(f"[DEBUG] 上一个交易日数据长度: {prev_day_length}")
                    print(f"[DEBUG] prev_rsi_1min_6长度: {len(prev_rsi_1min_6)}")
                    print(f"[DEBUG] rsi_1min_6_display长度: {len(rsi_1min_6_display)}")
                    print(f"[DEBUG] 总长度应该为: {len(prev_rsi_1min_6) + len(rsi_1min_6_display)}")
                    
                    # 确保数据长度匹配
                    if len(prev_rsi_1min_6) != prev_day_length:
                        print(f"[DEBUG] 警告：上一个交易日RSI长度不匹配，调整数据")
                        # 截取或填充数据以匹配长度
                        if len(prev_rsi_1min_6) > prev_day_length:
                            prev_rsi_1min_6 = prev_rsi_1min_6.iloc[-prev_day_length:]
                        else:
                            # 填充NaN值
                            padding = pd.Series([np.nan] * (prev_day_length - len(prev_rsi_1min_6)), 
                                              index=pd.date_range(str(prev_rsi_1min_6.index[0]), periods=prev_day_length - len(prev_rsi_1min_6), freq='1T'))
                            prev_rsi_1min_6 = pd.concat([padding, prev_rsi_1min_6])
                    
                    # 对其他RSI系列进行同样的处理
                    if prev_rsi_12 is not None and len(prev_rsi_12) != prev_day_length:
                        if len(prev_rsi_12) > prev_day_length:
                            prev_rsi_12 = prev_rsi_12.iloc[-prev_day_length:]
                        else:
                            padding = pd.Series([np.nan] * (prev_day_length - len(prev_rsi_12)), 
                                              index=pd.date_range(str(prev_rsi_12.index[0]), periods=prev_day_length - len(prev_rsi_12), freq='1T'))
                            prev_rsi_12 = pd.concat([padding, prev_rsi_12])
                    
                    if prev_rsi_24 is not None and len(prev_rsi_24) != prev_day_length:
                        if len(prev_rsi_24) > prev_day_length:
                            prev_rsi_24 = prev_rsi_24.iloc[-prev_day_length:]
                        else:
                            padding = pd.Series([np.nan] * (prev_day_length - len(prev_rsi_24)), 
                                              index=pd.date_range(str(prev_rsi_24.index[0]), periods=prev_day_length - len(prev_rsi_24), freq='1T'))
                            prev_rsi_24 = pd.concat([padding, prev_rsi_24])
                    
                    if prev_rsi_5min_6_1min is not None and len(prev_rsi_5min_6_1min) != prev_day_length:
                        if len(prev_rsi_5min_6_1min) > prev_day_length:
                            prev_rsi_5min_6_1min = prev_rsi_5min_6_1min.iloc[-prev_day_length:]
                        else:
                            padding = pd.Series([np.nan] * (prev_day_length - len(prev_rsi_5min_6_1min)), 
                                              index=pd.date_range(str(prev_rsi_5min_6_1min.index[0]), periods=prev_day_length - len(prev_rsi_5min_6_1min), freq='1T'))
                            prev_rsi_5min_6_1min = pd.concat([padding, prev_rsi_5min_6_1min])
                    
                    # 创建扩展的RSI数据框，包含上一个交易日的独立RSI数据
                    # 注意：RSI6_5min使用信号计算用的数据（前向填充），保持数学准确性
                    extended_rsi_df = pd.DataFrame({
                        'RSI6_1min': list(prev_rsi_1min_6.values) + list(rsi_1min_6_display.values),
                        'RSI6_5min': list(prev_rsi_5min_6_1min.values if prev_rsi_5min_6_1min is not None else [np.nan] * prev_day_length) + list(rsi_5min_6_1min_today_signal.values),
                        'RSI12': list(prev_rsi_12.values if prev_rsi_12 is not None else [np.nan] * prev_day_length) + list(rsi_12_display.values),
                        'RSI24': list(prev_rsi_24.values if prev_rsi_24 is not None else [np.nan] * prev_day_length) + list(rsi_24_display.values)
                    }, index=self.price_df.index)
                    
                    self.rsi_df = extended_rsi_df
                    
                    # 创建用于显示的RSI数据框（5分钟RSI使用线性插值）
                    self.rsi_df_display = pd.DataFrame({
                        'RSI6_1min': list(prev_rsi_1min_6.values) + list(rsi_1min_6_display.values),
                        'RSI6_5min': list(prev_rsi_5min_6_1min.values if prev_rsi_5min_6_1min is not None else [np.nan] * prev_day_length) + list(rsi_5min_6_1min_today_display.values),
                        'RSI12': list(prev_rsi_12.values if prev_rsi_12 is not None else [np.nan] * prev_day_length) + list(rsi_12_display.values),
                        'RSI24': list(prev_rsi_24.values if prev_rsi_24 is not None else [np.nan] * prev_day_length) + list(rsi_24_display.values)
                    }, index=self.price_df.index)
                    
                    print(f"[DEBUG] RSI数据已扩展，总长度: {len(self.rsi_df)}")
                    print(f"[DEBUG] 上一个交易日RSI6_1min值范围: [{prev_rsi_1min_6.min():.2f}, {prev_rsi_1min_6.max():.2f}]")
                    print(f"[DEBUG] 当日RSI6_1min值范围: [{rsi_1min_6_display.min():.2f}, {rsi_1min_6_display.max():.2f}]")
                else:
                    # 只有当日数据，创建仅包含当日RSI的数据框
                    # 注意：RSI6_5min使用信号计算用的数据（前向填充），保持数学准确性
                    self.rsi_df = pd.DataFrame({
                        'RSI6_1min': rsi_1min_6_display,    # 1分钟级别的RSI6
                        'RSI6_5min': rsi_5min_6_1min_today_signal,    # 5分钟级别的RSI6 (用于信号计算，前向填充)
                        'RSI12': rsi_12_display,
                        'RSI24': rsi_24_display
                    }, index=price_df.index)
                    
                    # 创建用于显示的RSI数据框（5分钟RSI使用线性插值）
                    self.rsi_df_display = pd.DataFrame({
                        'RSI6_1min': rsi_1min_6_display,    # 1分钟级别的RSI6
                        'RSI6_5min': rsi_5min_6_1min_today_display,    # 5分钟级别的RSI6 (用于显示，线性插值)
                        'RSI12': rsi_12_display,
                        'RSI24': rsi_24_display
                    }, index=price_df.index)
                    
                    print(f"[DEBUG] 创建仅包含当日RSI的数据框，长度: {len(self.rsi_df)}")
            except Exception as e:
                print(f"计算RSI指标失败: {e}")
                self.rsi_df = None
                self.kdj_df = None
            
            # 计算5分钟级别布林带（异步执行，避免阻塞）
            def calculate_bollinger_async():
                try:
                    print("[DEBUG] 开始计算5分钟级别布林带")
                    
                    # 获取历史5分钟数据用于布林带计算
                    historical_5min_data = self._get_historical_5min_data_for_bollinger()
                    
                    # 将当日1分钟数据转换为5分钟数据
                    today_5min_data = price_df.resample('5T', offset='1T').agg({
                        'open': 'first',
                        'close': 'last',
                        'high': 'max',
                        'low': 'min',
                        'volume': 'sum'
                    }).dropna()
                    
                    if historical_5min_data is not None and not historical_5min_data.empty:
                        # 合并历史数据和当日数据
                        combined_5min_data = pd.concat([historical_5min_data, today_5min_data])
                        print(f"[DEBUG] 合并历史5分钟数据用于布林带计算，总长度: {len(combined_5min_data)}")
                    else:
                        # 如果无法获取历史数据，使用当日数据
                        combined_5min_data = today_5min_data
                        print(f"[DEBUG] 使用当日5分钟数据计算布林带，长度: {len(combined_5min_data)}")
                    
                    # 计算布林带（带缓存机制）
                    bollinger_data = self._get_cached_bollinger_data(combined_5min_data)
                    
                    if bollinger_data is not None and not bollinger_data.empty:
                        # 只保留当日的数据用于显示
                        today_bollinger = bollinger_data.loc[today_5min_data.index]
                        
                        # 将5分钟布林带数据插值到1分钟级别
                        target_index = price_df.index
                        bollinger_upper = self._interpolate_5min_to_1min(today_bollinger['BOLL_UPPER'], target_index)
                        bollinger_middle = self._interpolate_5min_to_1min(today_bollinger['MA20'], target_index)
                        bollinger_lower = self._interpolate_5min_to_1min(today_bollinger['BOLL_LOWER'], target_index)
                        
                        # 在主线程中更新布林带数据
                        if self.window and self.window.winfo_exists():
                            self.window.after(0, lambda: self._update_bollinger_data(bollinger_upper, bollinger_middle, bollinger_lower))
                        
                        print(f"[DEBUG] 5分钟布林带计算完成，数据长度: {len(bollinger_upper)}")
                    else:
                        print("[DEBUG] 布林带计算失败，数据为空")
                        if self.window and self.window.winfo_exists():
                            self.window.after(0, lambda: setattr(self, '_bollinger_calculated', False))
                        
                except Exception as e:
                    print(f"计算5分钟布林带失败: {e}")
                    import traceback
                    traceback.print_exc()
                    if self.window and self.window.winfo_exists():
                        self.window.after(0, lambda: setattr(self, '_bollinger_calculated', False))
            
            # 在独立线程中计算布林带
            threading.Thread(target=calculate_bollinger_async, daemon=True).start()
            
            # 计算KDJ指标
            try:
                print(f"[DEBUG] 开始计算KDJ指标")
                
                # 使用当日数据计算KDJ (针对日内高低点捕捉优化参数)
                kdj_today = calculate_intraday_kdj(price_df, n=55, m1=21, m2=5, 
                                                 high_col="high", low_col="low", close_col="close")
                
                # 如果有上一个交易日数据，也计算其KDJ
                if self.SHOW_PREVIOUS_DAY_DATA and len(self.price_df) > len(price_df):
                    prev_day_length = len(self.price_df) - len(price_df)
                    prev_day_data = self.price_df.iloc[:prev_day_length]
                    
                    if not prev_day_data.empty:
                        prev_kdj = calculate_intraday_kdj(prev_day_data, n=55, m1=21, m2=5,
                                                        high_col="high", low_col="low", close_col="close")
                        
                        # 合并上一个交易日和当日的KDJ数据
                        self.kdj_df = pd.concat([prev_kdj, kdj_today], ignore_index=False)
                        print(f"[DEBUG] KDJ数据已扩展，总长度: {len(self.kdj_df)}")
                    else:
                        self.kdj_df = kdj_today
                        print(f"[DEBUG] 创建仅包含当日KDJ的数据框，长度: {len(self.kdj_df)}")
                else:
                    self.kdj_df = kdj_today
                    print(f"[DEBUG] 创建仅包含当日KDJ的数据框，长度: {len(self.kdj_df)}")
                    
            except Exception as e:
                print(f"计算KDJ指标失败: {e}")
                self.kdj_df = None
            
            # 计算移动平均线
            try:
                # 使用包含多个前一交易日数据的价格数据框计算MA指标，确保开盘阶段有足够的历史数据
                print(f"[DEBUG] 计算MA指标，合并后数据总长度: {len(price_df_with_prev)}")
                print(f"[DEBUG] 多个前一交易日数据长度: {len(price_df_with_prev) - len(price_df) if len(price_df_with_prev) > len(price_df) else 0}")
                
                # 短期均线: 25个1分钟周期的移动平均线
                ma_short_values = price_df_with_prev['close'].rolling(window=self.MA_SHORT_PERIOD, min_periods=1).mean()
                # 中期均线: 50个1分钟周期的移动平均线
                ma_mid_values = price_df_with_prev['close'].rolling(window=self.MA_MID_PERIOD, min_periods=1).mean()
                # 基础均线: 1250个1分钟周期的移动平均线（约等于日线MA5，可调试修改为其他值）
                ma_base_values = price_df_with_prev['close'].rolling(window=self.MA_BASE_PERIOD, min_periods=1).mean()
                
                # 关键修复：只取当日数据对应的MA值，但保持前一交易日数据的影响
                # 找到当日数据在合并数据中的起始位置
                if len(price_df_with_prev) > len(price_df):
                    # 有前一交易日数据
                    start_idx = len(price_df_with_prev) - len(price_df)
                    self.ma_short_values = ma_short_values.iloc[start_idx:]
                    self.ma_mid_values = ma_mid_values.iloc[start_idx:]
                    self.ma_base_values = ma_base_values.iloc[start_idx:]
                    print(f"[DEBUG] 从合并数据中提取当日MA值，起始索引: {start_idx}")
                else:
                    # 没有前一交易日数据，直接使用
                    self.ma_short_values = ma_short_values
                    self.ma_mid_values = ma_mid_values
                    self.ma_base_values = ma_base_values
                    print(f"[DEBUG] 直接使用当日MA值")
                
                print(f"[DEBUG] MA指标计算完成，数据长度: {len(self.ma_short_values)}")
                print(f"[DEBUG] 短期MA起始值: {self.ma_short_values.iloc[0]:.4f}")
                print(f"[DEBUG] 中期MA起始值: {self.ma_mid_values.iloc[0]:.4f}")
                
                # 如果显示数据包含上一个交易日数据，需要扩展MA数据以匹配显示数据
                if self.SHOW_PREVIOUS_DAY_DATA and len(self.price_df) > len(price_df):
                    print(f"[DEBUG] 显示数据包含上一个交易日数据，扩展MA数据以匹配显示数据")
                    print(f"[DEBUG] 显示数据长度: {len(self.price_df)}, 当日数据长度: {len(price_df)}")
                    
                    # 为上一个交易日数据计算MA值，而不是填充NaN
                    prev_day_length = len(self.price_df) - len(price_df)
                    
                    # 从完整的MA计算结果中提取上一个交易日的数据
                    if len(price_df_with_prev) > len(price_df):
                        # 有前一交易日数据用于计算，提取上一个交易日的MA值
                        calc_start_idx = len(price_df_with_prev) - len(price_df)
                        
                        # 从完整的MA计算结果中提取显示数据对应的部分
                        if prev_day_length <= calc_start_idx:
                            # 显示数据长度不超过计算数据，从末尾提取
                            display_start_idx = calc_start_idx - prev_day_length
                            prev_ma_short = ma_short_values.iloc[display_start_idx:calc_start_idx]
                            prev_ma_mid = ma_mid_values.iloc[display_start_idx:calc_start_idx]
                            prev_ma_base = ma_base_values.iloc[display_start_idx:calc_start_idx]
                            
                            print(f"[DEBUG] 提取显示用的上一个交易日MA数据，长度: {len(prev_ma_short)}")
                        else:
                            # 显示数据长度超过计算数据，用NaN填充
                            prev_day_index = self.price_df.index[:prev_day_length]
                            prev_ma_short = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                            prev_ma_mid = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                            prev_ma_base = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                            print(f"[DEBUG] 显示数据长度超过计算数据，创建NaN值")
                    else:
                        # 没有前一交易日数据，创建NaN值
                        prev_day_index = self.price_df.index[:prev_day_length]
                        prev_ma_short = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                        prev_ma_mid = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                        prev_ma_base = pd.Series([np.nan] * prev_day_length, index=prev_day_index)
                        print(f"[DEBUG] 没有前一交易日MA数据，创建NaN值")
                    
                    # 扩展MA数据，包含上一个交易日的MA数据
                    extended_ma_short = pd.Series(list(prev_ma_short.values) + list(self.ma_short_values.values), 
                                                 index=self.price_df.index)
                    extended_ma_mid = pd.Series(list(prev_ma_mid.values) + list(self.ma_mid_values.values), 
                                               index=self.price_df.index)
                    extended_ma_base = pd.Series(list(prev_ma_base.values) + list(self.ma_base_values.values), 
                                                index=self.price_df.index)
                    
                    self.ma_short_values = extended_ma_short
                    self.ma_mid_values = extended_ma_mid
                    self.ma_base_values = extended_ma_base
                    print(f"[DEBUG] MA数据已扩展，总长度: {len(self.ma_short_values)}")
                    print(f"[DEBUG] 上一个交易日MA25值: {prev_ma_short.values}")
                    print(f"[DEBUG] 当日MA25值: {self.ma_short_values.iloc[prev_day_length:].values}")
                
                # 计算5分钟级别布林带
                try:
                    print("[DEBUG] 开始计算5分钟级别布林带")
                    # 先将1分钟数据重采样为5分钟数据
                    price_5min = price_df.resample('5T', offset='1min').agg({
                        'open': 'first',
                        'close': 'last', 
                        'high': 'max',
                        'low': 'min',
                        'volume': 'sum'
                    }).dropna()
                    
                    if len(price_5min) < 20:  # 需要至少20个5分钟周期来计算布林带
                        print(f"[DEBUG] 5分钟数据不足({len(price_5min)}个周期)，无法计算布林带")
                        self.bollinger_5min_upper = None
                        self.bollinger_5min_lower = None
                        self.bollinger_5min_middle = None
                    else:
                        # 计算5分钟布林带
                        self.bollinger_5min_data = self._calculate_5min_bollinger_bands(price_5min)
                        
                        # 将5分钟布林带数据插值到1分钟级别（用于突破跌破计算）
                        self.bollinger_5min_upper = self._interpolate_5min_to_1min(self.bollinger_5min_data['BOLL_UPPER'], price_df.index)
                        self.bollinger_5min_lower = self._interpolate_5min_to_1min(self.bollinger_5min_data['BOLL_LOWER'], price_df.index)
                        self.bollinger_5min_middle = self._interpolate_5min_to_1min(self.bollinger_5min_data['MA20'], price_df.index)
                        
                        if self.bollinger_5min_data is not None:
                            print(f"[DEBUG] 5分钟布林带计算完成，原始数据长度: {len(self.bollinger_5min_data)}")
                            print(f"[DEBUG] 插值后数据长度: {len(self.bollinger_5min_upper) if self.bollinger_5min_upper is not None else 0}")
                            print(f"[DEBUG] 布林带上轨范围: [{self.bollinger_5min_data['BOLL_UPPER'].min():.3f}, {self.bollinger_5min_data['BOLL_UPPER'].max():.3f}]")
                            print(f"[DEBUG] 布林带下轨范围: [{self.bollinger_5min_data['BOLL_LOWER'].min():.3f}, {self.bollinger_5min_data['BOLL_LOWER'].max():.3f}]")
                        else:
                            print("[DEBUG] 5分钟布林带计算失败")
                except Exception as e:
                    print(f"[DEBUG] 计算5分钟布林带失败: {e}")
                    self.bollinger_5min_upper = None
                    self.bollinger_5min_lower = None
                    self.bollinger_5min_middle = None

                # 先计算支撑位和压力位（确保信号检测时有数据可用）
                if not self._support_resistance_calculated:
                    try:
                        print("[DEBUG] 在_update_data方法中计算支撑位和压力位")
                        self._calculate_support_resistance()
                    except Exception as e:
                        print(f"[DEBUG] 在_update_data方法中计算支撑位和压力位失败: {e}")
                        # 如果第一次计算失败，尝试再次计算（可能是网络延迟问题）
                        try:
                            print("[DEBUG] 第一次计算失败，尝试重新计算支撑位和压力位")
                            import time
                            time.sleep(1)  # 等待1秒后重试
                            self._calculate_support_resistance()
                        except Exception as e2:
                            print(f"[DEBUG] 重试计算支撑位和压力位仍然失败: {e2}")
                
                # 使用分时信号管理器检测买入和卖出信号
                data = {
                    'ma_short_values': self.ma_short_values,
                    'ma_mid_values': self.ma_mid_values,
                    'ma_base_values': self.ma_base_values,
                    'rsi_df': self.rsi_df,
                    'close_prices': price_df['close'],  # 使用原始当日数据
                    'open_prices': price_df['open'],    # 添加开盘价数据，用于连续连涨信号检测
                    'prev_close': self._get_previous_close(),
                    'bollinger_upper': self.bollinger_5min_upper,
                    'bollinger_middle': self.bollinger_5min_middle,
                    'bollinger_lower': self.bollinger_5min_lower,
                    'kdj_d_values': self.kdj_df['D'] if self.kdj_df is not None and not self.kdj_df.empty and 'D' in self.kdj_df.columns else None,  # 添加KDJ的D值数据
                    'price_df': price_df,  # 添加完整的价格数据框
                    'code': self.code  # 添加股票代码
                }
                
                print(f"[DEBUG] 准备检测信号，数据准备完成:")
                print(f"[DEBUG] - ma_short_values长度: {len(self.ma_short_values) if self.ma_short_values is not None else 'None'}")
                print(f"[DEBUG] - ma_mid_values长度: {len(self.ma_mid_values) if self.ma_mid_values is not None else 'None'}")
                print(f"[DEBUG] - close_prices长度: {len(price_df['close'])}")
                print(f"[DEBUG] - prev_close: {data['prev_close']}")
                print(f"[DEBUG] - support_level: {self.support_level}")
                print(f"[DEBUG] - resistance_level: {self.resistance_level}")
                # 检查布林带数据是否可用
                if self.bollinger_5min_upper is not None and self.bollinger_5min_middle is not None and self.bollinger_5min_lower is not None:
                    # 布林带数据可用，进行完整信号检测
                    basic_buy_signals = self.signal_manager.detect_buy_signals(data, price_df['close'])
                    basic_sell_signals = self.signal_manager.detect_sell_signals(data, price_df['close'])
                else:
                    # 布林带数据不可用，但连板信号、连涨信号和连跌信号不依赖当前交易日的布林带数据，可以先检测
                    print("[DEBUG] 布林带数据不可用，但检测连板信号、连涨信号和连跌信号（不依赖当前交易日布林带）")
                    # 检测不依赖布林带的信号
                    basic_buy_signals = []
                    for signal in self.signal_manager.buy_signals:
                        if hasattr(signal, 'name') and ('连板' in signal.name or '连涨' in signal.name):
                            # 检测连板信号和连涨信号
                            for i in range(len(price_df['close'])):
                                if signal.check_condition(data, i):
                                    signal_data = signal.create_signal_data(data, i)
                                    basic_buy_signals.append(signal_data)
                                    print(f"[DEBUG] 检测到买入信号: {signal_data.get('signal_type', 'Unknown')}")
                    
                    basic_sell_signals = []
                    for signal in self.signal_manager.sell_signals:
                        if hasattr(signal, 'name') and '连跌' in signal.name:
                            # 检测连跌信号
                            for i in range(len(price_df['close'])):
                                if signal.check_condition(data, i):
                                    signal_data = signal.create_signal_data(data, i)
                                    basic_sell_signals.append(signal_data)
                                    print(f"[DEBUG] 检测到卖出信号: {signal_data.get('signal_type', 'Unknown')}")
                
                # 检测支撑位跌破卖出信号和压力位突破买入信号（如果支撑位和压力位数据可用）
                if self.support_level is not None and self.resistance_level is not None:
                    # 添加支撑位和压力位数据到信号检测数据中
                    data['support_level'] = self.support_level
                    data['resistance_level'] = self.resistance_level
                    data['price_df'] = price_df  # 添加price_df用于5分钟价格计算
                    
                    print(f"[DEBUG] 开始检测支撑位和压力位信号:")
                    print(f"[DEBUG]  支撑位: {self.support_level:.3f} ({self.support_type})")
                    print(f"[DEBUG]  压力位: {self.resistance_level:.3f} ({self.resistance_type})")
                    print(f"[DEBUG]  位置状态: {self.position_status}")
                    
                    # 检测支撑位跌破卖出信号
                    support_breakdown_signals = self.signal_manager.detect_support_breakdown_signals(data, price_df['close'])
                    
                    # 检测压力位突破买入信号
                    resistance_breakthrough_signals = self.signal_manager.detect_resistance_breakthrough_signals(data, price_df['close'])
                    
                    # 合并所有卖出信号（延迟验证通过后才显示）
                    self.sell_signals = basic_sell_signals + support_breakdown_signals
                    
                    # 合并所有买入信号（延迟验证通过后才显示）
                    self.buy_signals = basic_buy_signals + resistance_breakthrough_signals
                    
                    print(f"[DEBUG] 支撑位跌破信号检测完成，检测到 {len(support_breakdown_signals)} 个信号")
                    print(f"[DEBUG] 压力位突破信号检测完成，检测到 {len(resistance_breakthrough_signals)} 个信号")
                elif self.support_level is not None:
                    # 只有支撑位数据，检测支撑位跌破卖出信号
                    data['support_level'] = self.support_level
                    print(f"[DEBUG] 开始检测支撑位跌破信号，支撑位: {self.support_level:.3f} ({self.support_type})")
                    support_breakdown_signals = self.signal_manager.detect_support_breakdown_signals(data, price_df['close'])
                    self.sell_signals = basic_sell_signals + support_breakdown_signals
                    self.buy_signals = basic_buy_signals
                    print(f"[DEBUG] 支撑位跌破信号检测完成，检测到 {len(support_breakdown_signals)} 个信号")
                elif self.resistance_level is not None:
                    # 只有压力位数据，检测压力位突破买入信号
                    data['resistance_level'] = self.resistance_level
                    print(f"[DEBUG] 开始检测压力位突破信号，压力位: {self.resistance_level:.3f} ({self.resistance_type})")
                    resistance_breakthrough_signals = self.signal_manager.detect_resistance_breakthrough_signals(data, price_df['close'])
                    self.buy_signals = basic_buy_signals + resistance_breakthrough_signals
                    self.sell_signals = basic_sell_signals
                    print(f"[DEBUG] 压力位突破信号检测完成，检测到 {len(resistance_breakthrough_signals)} 个信号")
                else:
                    # 如果没有支撑位和压力位数据，只使用基本信号
                    self.sell_signals = basic_sell_signals
                    self.buy_signals = basic_buy_signals
                    print(f"[DEBUG] 支撑位和压力位数据不可用，仅使用基本信号")
                
                # 通知连跌信号买入信号已出现
                self._notify_plunge_signals_buy_signal_appeared()
                
                # 通知连涨信号卖出信号已出现
                self._notify_surge_signals_sell_signal_appeared()
                
                # 重新验证待确认信号的有效性（60秒重新检测时）
                if self.buy_signals:
                    self.buy_signals = self.signal_manager.validate_wait_confirm_signals(data, self.buy_signals)
                if self.sell_signals:
                    self.sell_signals = self.signal_manager.validate_wait_confirm_signals(data, self.sell_signals)
                
                print(f"[DEBUG] 最终信号检测完成:")
                print(f"[DEBUG] - 买入信号数量: {len(self.buy_signals) if self.buy_signals else 0}")
                print(f"[DEBUG] - 卖出信号数量: {len(self.sell_signals) if self.sell_signals else 0}")
                
                # 检查连涨信号
                if self.buy_signals:
                    consecutive_signals = [sig for sig in self.buy_signals if '连涨' in sig.get('signal_type', '')]
                    print(f"[DEBUG] - 连涨信号数量: {len(consecutive_signals)}")
                    for i, sig in enumerate(consecutive_signals):
                        print(f"[DEBUG] - 连涨信号{i+1}: 索引={sig['index']}, 价格={sig['price']:.3f}, is_fake={sig['is_fake']}, wait_validate={sig['wait_validate']}")
                
                # 播放音频通知（仅在实时信号时）
                self._play_signal_audio_notifications()
            except Exception as e:
                print(f"计算移动平均线失败: {e}")
                self.ma25_values = None
                self.ma50_values = None
                self.buy_signals = []  # 设置为空列表而不是None

            # 更新窗口标题: 显示最后更新时间 (在有工具栏的情况下)
            if self.show_toolbar and hasattr(self.window, 'title'):
                update_time = datetime.now().strftime('%H:%M:%S')
                base_title = f"{self.name}({self.code}) - 分时 {self.trade_date_str}"
                # 类型检查：确保window是Toplevel类型
                if hasattr(self.window, 'title'):
                    def update_title():
                        # 使用类型转换避免类型检查错误
                        if hasattr(self.window, 'title'):
                            self.window.title(f"{base_title} [最后更新: {update_time}]")  # type: ignore
                    self.window.after(0, update_title)

            # 获取均线价格（仅在首次加载或交易日变化时获取）
            if self.ma5_price is None or self.ma10_price is None or self.ma20_price is None:
                self.ma5_price, self.ma10_price, self.ma20_price = self._get_ma_prices()

            # 新增：计算支撑位和压力位（确保第一次加载时就能显示）
            if not self._support_resistance_calculated:
                try:
                    print("[DEBUG] 在_update_data方法中计算支撑位和压力位")
                    self._calculate_support_resistance()
                except Exception as e:
                    print(f"[DEBUG] 在_update_data方法中计算支撑位和压力位失败: {e}")
            
            # 计算看涨线（上个交易日布林带最高点）
            if not self._bullish_line_calculated:
                try:
                    print("[DEBUG] 在_update_data方法中计算看涨线")
                    self._calculate_bullish_line()
                except Exception as e:
                    print(f"[DEBUG] 在_update_data方法中计算看涨线失败: {e}")
            
            # 计算看跌线（上个交易日布林带最低点）
            if not self._bearish_line_calculated:
                try:
                    print("[DEBUG] 在_update_data方法中计算看跌线")
                    self._calculate_bearish_line()
                except Exception as e:
                    print(f"[DEBUG] 在_update_data方法中计算看跌线失败: {e}")

            # 计算5分钟K线突破和跌破布林带次数
            # 在实时更新时重新计算，确保文字框显示最新数据
            try:
                print("[DEBUG] 在_update_data方法中计算突破跌破次数")
                # 重置计算标志，允许重新计算
                self._breakthrough_breakdown_calculated = False
                self._calculate_breakthrough_breakdown_count()
            except Exception as e:
                print(f"[DEBUG] 在_update_data方法中计算突破跌破次数失败: {e}")

            # 重新加载成本数据（当股票代码更新后）
            if self.cost_df is None:
                self._load_cached_cost()

            # 仅在今日才追加实时成本
            if self.trade_date == date.today():
                cost_val = self._get_latest_cost()
                if cost_val is not None:
                    self._append_cost_cache(datetime.now().replace(second=0, microsecond=0), cost_val)

            # 新增：计算前高价格（双价格）- 只使用前一个交易日的日级数据
            if not hasattr(self, '_previous_high_calculated') or not self._previous_high_calculated:
                try:
                    from trading_utils import (calculate_previous_high_price,
                                               get_previous_high_dual_prices)

                    # 导入增强的峰值检测算法
                    try:
                        from enhanced_peak_detection import (
                            detect_enhanced_peaks, get_enhanced_high_low)
                        use_enhanced_detection = True
                    except ImportError:
                        use_enhanced_detection = False
                        print(f"[DEBUG] 增强峰值检测模块未找到，使用原有算法")
                    
                    print(f"[DEBUG] 分时窗口 - 开始计算前高双价格: {self.code}")
                    
                    # 分时窗口只使用前一个交易日的日级前高前低数据
                    # 不检测当日分时数据中的临时高点/低点
                    print(f"[DEBUG] 分时窗口 - 只使用前一个交易日的日级前高前低数据")
                    
                    # 计算前高双价格（历史数据）
                    security_type, symbol = self._get_security_type(self.code)
                    
                    dual_prices = get_previous_high_dual_prices(
                        symbol=symbol,
                        current_date=self.trade_date_str,
                        months_back=12,  # 改为1年（12个月）
                        security_type=security_type
                    )
                    
                    if "error" not in dual_prices:
                        self.previous_high_dual_prices = dual_prices
                        self.previous_high_price = dual_prices['shadow_high_price']  # 保持兼容性
                        
                        print(f"[DEBUG] 分时窗口 - 前高双价格:")
                        print(f"[DEBUG]   当前价格: {dual_prices['current_price']:.3f}")
                        print(f"[DEBUG]   上影线最高价: {dual_prices['shadow_high_price']:.3f}")
                        print(f"[DEBUG]   实体最高价: {dual_prices['entity_high_price']:.3f}")
                        
                        if dual_prices['resistance_band']:
                            band = dual_prices['resistance_band']
                            print(f"[DEBUG]   阻力带: {band['lower']:.3f} - {band['upper']:.3f}")
                            print(f"[DEBUG]   阻力带日期: {band['date']}")
                            
                            # 计算阻力带宽度
                            band_width = band['upper'] - band['lower']
                            band_width_pct = (band_width / band['lower']) * 100
                            print(f"[DEBUG]   阻力带宽度: {band_width:.3f} ({band_width_pct:.2f}%)")
                    else:
                        print(f"[DEBUG] 分时窗口 - 前高双价格计算失败: {dual_prices['error']}")
                        self.previous_high_dual_prices = None
                        self.previous_high_price = None
                    
                    self._previous_high_calculated = True
                    
                except Exception as e:
                    print(f"[DEBUG] 分时窗口 - 计算前高双价格失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.previous_high_dual_prices = None
                    self.previous_high_price = None
                    self._previous_high_calculated = True

            # 新增：计算前低价格（双价格）- 只使用前一个交易日的日级数据
            if not hasattr(self, '_previous_low_calculated') or not self._previous_low_calculated:
                try:
                    from trading_utils import get_previous_low_dual_prices
                    
                    print(f"[DEBUG] 分时窗口 - 开始计算前低双价格: {self.code}")
                    
                    # 计算前低双价格
                    security_type, symbol = self._get_security_type(self.code)
                    
                    dual_prices = get_previous_low_dual_prices(
                        symbol=symbol,
                        current_date=self.trade_date_str,
                        months_back=12,  # 1年（12个月）
                        security_type=security_type
                    )
                    
                    if "error" not in dual_prices:
                        # 获取上个交易日收盘价进行验证
                        prev_close = self._get_previous_close()
                        
                        # 验证前低不能高于上个交易日收盘价
                        entity_low_price = dual_prices['entity_low_price']
                        shadow_low_price = dual_prices['shadow_low_price']
                        
                        if prev_close is not None:
                            if entity_low_price > prev_close:
                                print(f"[WARNING] 前低实体最低价({entity_low_price:.3f})高于上个交易日收盘价({prev_close:.3f})，跳过前低计算")
                                self.previous_low_dual_prices = None
                                self.previous_low_price = None
                            elif shadow_low_price > prev_close:
                                print(f"[WARNING] 前低下影线最低价({shadow_low_price:.3f})高于上个交易日收盘价({prev_close:.3f})，跳过前低计算")
                                self.previous_low_dual_prices = None
                                self.previous_low_price = None
                            else:
                                # 前低验证通过，保存数据
                                self.previous_low_dual_prices = dual_prices
                                self.previous_low_price = dual_prices['shadow_low_price']  # 保持兼容性
                                
                                print(f"[DEBUG] 分时窗口 - 前低双价格验证通过:")
                                print(f"[DEBUG]   上个交易日收盘价: {prev_close:.3f}")
                                print(f"[DEBUG]   当前价格: {dual_prices['current_price']:.3f}")
                                print(f"[DEBUG]   下影线最低价: {dual_prices['shadow_low_price']:.3f}")
                                print(f"[DEBUG]   实体最低价: {dual_prices['entity_low_price']:.3f}")
                                
                                if dual_prices['support_band']:
                                    band = dual_prices['support_band']
                                    print(f"[DEBUG]   支撑带: {band['lower']:.3f} - {band['upper']:.3f}")
                                    print(f"[DEBUG]   支撑带日期: {band['date']}")
                                    
                                    # 计算支撑带宽度
                                    band_width = band['upper'] - band['lower']
                                    band_width_pct = (band_width / band['lower']) * 100
                                    print(f"[DEBUG]   支撑带宽度: {band_width:.3f} ({band_width_pct:.2f}%)")
                        else:
                            print(f"[WARNING] 无法获取上个交易日收盘价，跳过前低验证")
                            # 无法验证时，仍然保存数据但给出警告
                            self.previous_low_dual_prices = dual_prices
                            self.previous_low_price = dual_prices['shadow_low_price']
                            
                            print(f"[DEBUG] 分时窗口 - 前低双价格（未验证）:")
                            print(f"[DEBUG]   当前价格: {dual_prices['current_price']:.3f}")
                            print(f"[DEBUG]   下影线最低价: {dual_prices['shadow_low_price']:.3f}")
                            print(f"[DEBUG]   实体最低价: {dual_prices['entity_low_price']:.3f}")
                    else:
                        print(f"[DEBUG] 分时窗口 - 前低双价格计算失败: {dual_prices['error']}")
                        self.previous_low_dual_prices = None
                        self.previous_low_price = None
                    
                    self._previous_low_calculated = True
                    
                except Exception as e:
                    print(f"[DEBUG] 分时窗口 - 计算前低双价格失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.previous_low_dual_prices = None
                    self.previous_low_price = None
                    self._previous_low_calculated = True

            # 更新缓存时间戳
            self._update_cache_timestamp()
            
            # 绘图
            self.window.after(0, self._draw)
            
            # 标记初始化完成，允许播放布林带音效
            self._initialization_complete = True

        except Exception as e:
            print(f"[IntradayWindow] 更新数据失败: {e}")
            # 即使出错也要标记初始化完成
            self._initialization_complete = True

    def _get_latest_cost(self) -> Optional[float]:
        try:
            cyq_df = ak.stock_cyq_em(symbol=self.code, adjust="qfq")
            if cyq_df.empty or "平均成本" not in cyq_df.columns:
                return None
            cost_val = float(cyq_df.iloc[-1]["平均成本"])
            return cost_val
        except Exception as e:
            print(f"获取平均成本失败: {e}")
            return None

    def _get_previous_close(self) -> Optional[float]:
        """获取前一交易日的收盘价（带缓存优化）"""
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 尝试从统一缓存获取
            cached_prev_close = self._get_cached_data('previous_close')
            if cached_prev_close is not None:
                print(f"[DEBUG] 从缓存获取前一交易日收盘价: {cached_prev_close}")
                return cached_prev_close
            
            # 检查旧缓存是否有效
            if (self._cached_previous_close is not None and 
                self._cached_previous_close_date == self.trade_date_str):
                print(f"[DEBUG] 从旧缓存获取前一交易日收盘价: {self._cached_previous_close}")
                return self._cached_previous_close
            
            from trading_utils import get_previous_close

            # 获取证券类型和对应的数据接口代码
            security_type, symbol = self._get_security_type(self.code)

            # 调用trading_utils中的通用函数
            prev_close = get_previous_close(
                symbol=symbol,
                trade_date=self.trade_date_str,
                security_type=security_type
            )
            
            # 缓存结果到统一缓存
            if prev_close is not None:
                self._set_cached_data('previous_close', prev_close)
                print(f"[DEBUG] 前一交易日收盘价已缓存: {prev_close}")
            
            # 保持旧缓存兼容性
            self._cached_previous_close = prev_close
            self._cached_previous_close_date = self.trade_date_str
            
            return prev_close
                
        except Exception as e:
            print(f"获取前一交易日收盘价失败: {e}")
            return None
    
    def _get_previous_close_for_volume_colors(self) -> Optional[float]:
        """获取相对于当前显示日期的前一交易日收盘价，用于成交量颜色判断"""
        try:
            from trading_utils import get_previous_close

            # 获取证券类型和对应的数据接口代码
            security_type, symbol = self._get_security_type(self.code)

            print(f"[DEBUG] 成交量颜色判断 - 调用get_previous_close: 证券={symbol}, 类型={security_type}, 交易日={self.trade_date_str}")
            
            # 调用trading_utils中的通用函数，使用当前显示的交易日
            prev_close = get_previous_close(
                symbol=symbol,
                trade_date=self.trade_date_str,
                security_type=security_type
            )
            
            print(f"[DEBUG] 成交量颜色判断 - get_previous_close返回: {prev_close}")
            return prev_close
                
        except Exception as e:
            print(f"获取前一交易日收盘价失败(成交量颜色): {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_previous_close_for_prev_day(self) -> Optional[float]:
        """获取前两个交易日收盘价（用于计算上一个交易日的RSI）"""
        try:
            from datetime import timedelta

            from trading_utils import get_previous_close

            # 计算前两个交易日
            prev_prev_date = self.trade_date - timedelta(days=2)
            # 跳过周末
            while prev_prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                prev_prev_date -= timedelta(days=1)
            
            prev_prev_date_str = prev_prev_date.strftime('%Y-%m-%d')
            security_type, symbol = self._get_security_type(self.code)
            return get_previous_close(symbol, prev_prev_date_str, security_type)
        except Exception as e:
            print(f"获取前两个交易日收盘价失败: {e}")
            return None
    
    def _interpolate_5min_rsi_to_1min(self, rsi_5min: pd.Series, target_index: pd.Index, for_display_only: bool = True) -> pd.Series:
        """将5分钟RSI数据插值到1分钟时间轴
        
        :param rsi_5min: 5分钟RSI数据
        :param target_index: 目标1分钟时间轴
        :param for_display_only: 是否仅用于显示（True=线性插值，False=前向填充保持数学准确性）
        :return: 插值后的1分钟RSI数据
        """
        try:
            if for_display_only:
                # 仅用于显示：使用线性插值实现平滑过渡
                rsi_1min = rsi_5min.reindex(target_index)
                rsi_1min_interpolated = rsi_1min.interpolate(method='linear')
                rsi_1min_interpolated = rsi_1min_interpolated.ffill().bfill()
                return rsi_1min_interpolated
            else:
                # 用于信号计算：使用前向填充保持数学准确性
                return rsi_5min.reindex(target_index, method='ffill')
            
        except Exception as e:
            print(f"5分钟RSI插值失败: {e}")
            # 降级到前向填充
            return rsi_5min.reindex(target_index, method='ffill')

    def _interpolate_5min_to_1min(self, data_5min: pd.Series, target_index: pd.Index) -> pd.Series:
        """
        将5分钟数据插值到1分钟级别，用于布林带等指标
        
        :param data_5min: 5分钟数据
        :param target_index: 目标1分钟时间索引
        :return: 1分钟数据
        """
        try:
            if data_5min.empty:
                return pd.Series(index=target_index, dtype=float)
            
            # 使用线性插值实现平滑过渡，避免锯齿形效果
            interpolated = data_5min.reindex(target_index)
            interpolated = interpolated.interpolate(method='linear')
            # 对首尾缺失值进行前向和后向填充
            interpolated = interpolated.ffill().bfill()
            return interpolated
            
        except Exception as e:
            print(f"5分钟数据插值失败: {e}")
            # 降级到前向填充
            return data_5min.reindex(target_index, method='ffill')

    def _merge_price_range(self, new_down_price: float, new_up_price: float) -> tuple[float, float]:
        """合并价格范围，确保新范围只能扩展不能缩小
        
        :param new_down_price: 新计算的下限价格
        :param new_up_price: 新计算的上限价格
        :return: 合并后的(下限价格, 上限价格)
        """
        try:
            # 如果没有历史记录，直接使用新范围
            if not self._price_range_initialized or self._price_range_history is None:
                self._price_range_history = {
                    'down_price': new_down_price,
                    'up_price': new_up_price
                }
                self._price_range_initialized = True
                print(f"[DEBUG] 价格范围初始化: {new_down_price:.3f} - {new_up_price:.3f}")
                return new_down_price, new_up_price
            
            # 获取历史范围
            hist_down = self._price_range_history['down_price']
            hist_up = self._price_range_history['up_price']
            
            # 合并范围：只能扩展，不能缩小
            merged_down = min(hist_down, new_down_price)  # 取更小的下限
            merged_up = max(hist_up, new_up_price)        # 取更大的上限
            
            # 更新历史记录
            self._price_range_history = {
                'down_price': merged_down,
                'up_price': merged_up
            }
            
            # 检查是否有变化
            if merged_down != hist_down or merged_up != hist_up:
                print(f"[DEBUG] 价格范围扩展:")
                print(f"[DEBUG]   历史范围: {hist_down:.3f} - {hist_up:.3f}")
                print(f"[DEBUG]   新计算范围: {new_down_price:.3f} - {new_up_price:.3f}")
                print(f"[DEBUG]   合并后范围: {merged_down:.3f} - {merged_up:.3f}")
            else:
                print(f"[DEBUG] 价格范围保持不变: {merged_down:.3f} - {merged_up:.3f}")
            
            return merged_down, merged_up
            
        except Exception as e:
            print(f"价格范围合并失败: {e}")
            import traceback
            traceback.print_exc()
            return new_down_price, new_up_price

    def _reset_price_range_history(self):
        """重置价格范围历史记录（在切换股票或交易日时调用）"""
        self._price_range_history = None
        self._price_range_initialized = False
        print("[DEBUG] 价格范围历史记录已重置")

    def _get_historical_5min_data_for_rsi(self) -> Optional[pd.DataFrame]:
        """获取历史5分钟数据用于RSI计算
        
        获取前一交易日的最后5根5分钟K线数据，用于确保5分钟RSI6计算的连续性。
        这样可以在开盘阶段就计算出准确的RSI6值。
        
        :return: 历史5分钟数据DataFrame，包含open, close, volume列
        """
        try:
            # 获取前一交易日的分时数据
            prev_day_data = self._get_previous_trading_day_intraday()
            
            if prev_day_data is None or prev_day_data.empty:
                print("[DEBUG] 无法获取前一交易日数据用于5分钟RSI计算")
                return None
            
            # 转换为5分钟K线数据
            prev_day_5min = prev_day_data.resample('5T', offset='1T').agg({
                'open': 'first',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            if prev_day_5min.empty:
                print("[DEBUG] 前一交易日5分钟数据为空")
                return None
            
            # 只取最后5根5分钟K线
            if len(prev_day_5min) >= 5:
                historical_data = prev_day_5min.tail(5)
                print(f"[DEBUG] 获取历史5分钟数据用于RSI计算，数据长度: {len(historical_data)}")
                print(f"[DEBUG] 历史5分钟数据时间范围: {historical_data.index[0]} 到 {historical_data.index[-1]}")
                print(f"[DEBUG] 历史5分钟收盘价: {historical_data['close'].tolist()}")
                return historical_data
            else:
                print(f"[DEBUG] 前一交易日5分钟数据不足5根，实际长度: {len(prev_day_5min)}")
                return prev_day_5min
                
        except Exception as e:
            print(f"获取历史5分钟数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_historical_5min_data_for_bollinger(self) -> Optional[pd.DataFrame]:
        """获取历史5分钟数据用于布林带计算
        
        获取多个前一交易日的5分钟K线数据，用于确保布林带计算的连续性。
        布林带需要20个周期的数据，所以需要获取足够的历史数据。
        
        :return: 历史5分钟数据DataFrame，包含open, close, high, low, volume列
        """
        try:
            # 获取多个前一交易日的分时数据
            multiple_prev_data = self._get_multiple_previous_trading_days_intraday()
            
            if multiple_prev_data is None or multiple_prev_data.empty:
                print("[DEBUG] 无法获取多个前一交易日数据用于5分钟布林带计算")
                return None
            
            # 转换为5分钟K线数据
            prev_days_5min = multiple_prev_data.resample('5T', offset='1T').agg({
                'open': 'first',
                'close': 'last',
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            if prev_days_5min.empty:
                print("[DEBUG] 多个前一交易日5分钟数据为空")
                return None
            
            print(f"[DEBUG] 获取历史5分钟数据用于布林带计算，数据长度: {len(prev_days_5min)}")
            print(f"[DEBUG] 历史5分钟数据时间范围: {prev_days_5min.index[0]} 到 {prev_days_5min.index[-1]}")
            return prev_days_5min
                
        except Exception as e:
            print(f"获取历史5分钟数据用于布林带计算失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _get_previous_trading_day_intraday(self) -> Optional[pd.DataFrame]:
        """获取前一交易日的分时数据，用于MA指标计算的连续性"""
        try:
            from datetime import timedelta

            # 使用交易日历来获取真正的前一交易日
            if hasattr(self, '_trade_calendar') and self._trade_calendar:
                # 从交易日历中找到前一交易日
                sorted_dates = sorted(list(self._trade_calendar))
                current_idx = sorted_dates.index(self.trade_date) if self.trade_date in sorted_dates else -1
                if current_idx > 0:
                    prev_date = sorted_dates[current_idx - 1]
                else:
                    # 如果找不到当前日期或当前日期是第一个，则使用简单方法
                    prev_date = self.trade_date - timedelta(days=1)
                    while prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                        prev_date -= timedelta(days=1)
            else:
                # 如果没有交易日历，使用简单方法
                prev_date = self.trade_date - timedelta(days=1)
                while prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                    prev_date -= timedelta(days=1)
            
            prev_date_str = prev_date.strftime("%Y-%m-%d")
            print(f"[DEBUG] 尝试获取前一交易日 {prev_date_str} 的分时数据")
            
            # 获取前一交易日的分时数据
            start_dt = f"{prev_date_str} 09:30:00"
            end_dt = f"{prev_date_str} 15:00:00"
            
            # 获取证券类型和对应的数据接口代码
            security_type, symbol = self._get_security_type(self.code)
            
            if security_type == "INDEX":
                # 使用指数分时数据接口
                prev_intraday_df = ak.index_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),
                )
            elif security_type == "ETF":
                # 使用ETF分时数据接口
                prev_intraday_df = ak.fund_etf_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),
                    adjust="",
                )
            else:
                # 使用股票分时数据接口
                prev_intraday_df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period=str(self.period),
                    adjust="",
                )
            
            if prev_intraday_df.empty:
                print(f"[DEBUG] 前一交易日 {prev_date_str} 没有分时数据，尝试获取日线数据")
                # 如果分时数据为空，尝试获取日线数据
                try:
                    # 获取证券类型和对应的数据接口代码
                    security_type, symbol = self._get_security_type(self.code)
                    
                    if security_type == "INDEX":
                        # 使用指数日线数据接口
                        daily_df = ak.index_zh_a_hist(
                            symbol=symbol,
                            start_date=prev_date_str.replace('-', ''),
                            end_date=prev_date_str.replace('-', ''),
                            adjust=""
                        )
                    elif security_type == "ETF":
                        # 使用ETF日线数据接口
                        daily_df = ak.fund_etf_hist_em(
                            symbol=symbol,
                            start_date=prev_date_str,
                            end_date=prev_date_str,
                            adjust="qfq"
                        )
                    else:
                        # 使用股票日线数据接口
                        daily_df = ak.stock_zh_a_hist(
                            symbol=symbol,
                            start_date=prev_date_str.replace('-', ''),
                            end_date=prev_date_str.replace('-', ''),
                            adjust="qfq"
                        )
                    if not daily_df.empty:
                        # 使用收盘价创建足够多的模拟分时数据点，确保能计算RSI
                        close_price = float(daily_df.iloc[-1]["收盘"])
                        # 创建最后1小时的模拟数据（60个1分钟数据点）
                        prev_times = pd.date_range(f"{prev_date_str} 14:00:00", f"{prev_date_str} 15:00:00", freq='1T')
                        prev_intraday_df = pd.DataFrame({
                            'open': [close_price] * len(prev_times),
                            'close': [close_price] * len(prev_times),
                            'volume': [0] * len(prev_times)
                        }, index=prev_times)
                        print(f"[DEBUG] 使用前一交易日收盘价 {close_price} 创建模拟分时数据，共 {len(prev_intraday_df)} 条记录")
                    else:
                        print(f"[DEBUG] 前一交易日 {prev_date_str} 也没有日线数据")
                        return None
                except Exception as e:
                    print(f"[DEBUG] 获取前一交易日日线数据失败: {e}")
                    return None
            else:
                print(f"[DEBUG] 成功获取前一交易日 {prev_date_str} 的分时数据，共 {len(prev_intraday_df)} 条记录")
            
            # 统一列名 - 包含所有必要的列
            if '时间' in prev_intraday_df.columns:
                prev_intraday_df.rename(columns={
                    "时间": "datetime", 
                    "开盘": "open", 
                    "收盘": "close", 
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume"
                }, inplace=True)
                prev_intraday_df["datetime"] = pd.to_datetime(prev_intraday_df["datetime"])
                prev_intraday_df.set_index("datetime", inplace=True)
            elif 'datetime' not in prev_intraday_df.columns:
                # 如果已经是正确的列名，只需要设置索引
                prev_intraday_df.set_index("datetime", inplace=True)
            
            print(f"[DEBUG] 前一交易日数据处理完成，最终数据长度: {len(prev_intraday_df)}")
            return prev_intraday_df
            
        except Exception as e:
            print(f"[DEBUG] 获取前一交易日分时数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_previous_day_last_hour_data(self) -> Optional[pd.DataFrame]:
        """获取上一个交易日最后1小时的分时数据"""
        try:
            # 获取上一个交易日的完整分时数据
            prev_day_data = self._get_previous_trading_day_intraday()
            if prev_day_data is None or prev_day_data.empty:
                return None
            
            # 筛选最后1小时的数据（14:00-15:00）
            last_hour_data = prev_day_data.between_time('14:00', '15:00')
            
            if last_hour_data.empty:
                print(f"[DEBUG] 上一个交易日最后1小时没有数据")
                return None
            
            print(f"[DEBUG] 获取到上一个交易日最后1小时数据，共 {len(last_hour_data)} 条记录")
            return last_hour_data
            
        except Exception as e:
            print(f"[DEBUG] 获取上一个交易日最后1小时数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _get_multiple_previous_trading_days_intraday(self) -> Optional[pd.DataFrame]:
        """获取多个前一交易日的分时数据，确保有足够的历史数据计算MA指标"""
        try:
            from datetime import timedelta
            
            all_prev_data = []
            current_date = self.trade_date
            
            # 获取前3个交易日的数据，确保有足够的历史数据
            for i in range(1, 4):  # 获取前1-3个交易日
                if hasattr(self, '_trade_calendar') and self._trade_calendar:
                    # 从交易日历中找到前i个交易日
                    sorted_dates = sorted(list(self._trade_calendar))
                    current_idx = sorted_dates.index(current_date) if current_date in sorted_dates else -1
                    if current_idx >= i:
                        prev_date = sorted_dates[current_idx - i]
                    else:
                        break
                else:
                    # 如果没有交易日历，使用简单方法
                    prev_date = current_date - timedelta(days=i)
                    while prev_date.weekday() >= 5:  # 5=Saturday, 6=Sunday
                        prev_date -= timedelta(days=1)
                
                prev_date_str = prev_date.strftime("%Y-%m-%d")
                print(f"[DEBUG] 尝试获取前{i}个交易日 {prev_date_str} 的分时数据")
                
                # 获取前一交易日的分时数据
                start_dt = f"{prev_date_str} 09:30:00"
                end_dt = f"{prev_date_str} 15:00:00"
                
                try:
                    # 获取证券类型和对应的数据接口代码
                    security_type, symbol = self._get_security_type(self.code)
                    
                    if security_type == "INDEX":
                        # 使用指数分时数据接口
                        prev_intraday_df = ak.index_zh_a_hist_min_em(
                            symbol=symbol,
                            start_date=start_dt,
                            end_date=end_dt,
                            period=str(self.period),
                        )
                    elif security_type == "ETF":
                        # 使用ETF分时数据接口
                        prev_intraday_df = ak.fund_etf_hist_min_em(
                            symbol=symbol,
                            start_date=start_dt,
                            end_date=end_dt,
                            period=str(self.period),
                            adjust="",
                        )
                    else:
                        # 使用股票分时数据接口
                        prev_intraday_df = ak.stock_zh_a_hist_min_em(
                            symbol=symbol,
                            start_date=start_dt,
                            end_date=end_dt,
                            period=str(self.period),
                            adjust="",
                        )
                    
                    if not prev_intraday_df.empty:
                        # 统一列名 - 包含所有必要的列
                        if '时间' in prev_intraday_df.columns:
                            prev_intraday_df.rename(columns={
                                "时间": "datetime", 
                                "开盘": "open", 
                                "收盘": "close", 
                                "最高": "high",
                                "最低": "low",
                                "成交量": "volume"
                            }, inplace=True)
                            prev_intraday_df["datetime"] = pd.to_datetime(prev_intraday_df["datetime"])
                            prev_intraday_df.set_index("datetime", inplace=True)
                        
                        all_prev_data.append(prev_intraday_df)
                        print(f"[DEBUG] 成功获取前{i}个交易日 {prev_date_str} 的分时数据，共 {len(prev_intraday_df)} 条记录")
                    else:
                        print(f"[DEBUG] 前{i}个交易日 {prev_date_str} 没有分时数据")
                        break
                        
                except Exception as e:
                    print(f"[DEBUG] 获取前{i}个交易日 {prev_date_str} 分时数据失败: {e}")
                    break
            
            if not all_prev_data:
                print(f"[DEBUG] 无法获取任何前一交易日分时数据")
                return None
            
            # 合并所有前一交易日数据
            combined_prev_data = pd.concat(all_prev_data)
            print(f"[DEBUG] 成功获取多个前一交易日数据，总长度: {len(combined_prev_data)}")
            
            return combined_prev_data
            
        except Exception as e:
            print(f"[DEBUG] 获取多个前一交易日分时数据失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _is_realtime_signal(self, signal_timestamp: Optional[pd.Timestamp] = None, threshold_minutes: int = 2) -> bool:
        """判断信号是否为实时信号
        
        :param signal_timestamp: 信号发生的时间戳，如果为None则使用最新数据时间
        :param threshold_minutes: 实时阈值（分钟），默认2分钟
        :return: True表示实时信号，False表示历史信号
        """
        try:
            from datetime import date, datetime, time, timedelta

            # 检查是否为今日
            today = date.today()
            if self.trade_date != today:
                return False
            
            # 如果没有提供信号时间戳，使用最新数据时间
            if signal_timestamp is None:
                if self.price_df is None or self.price_df.empty:
                    return False
                signal_timestamp = self.price_df.index[-1]
            
            # 确保signal_timestamp不为None
            if signal_timestamp is None:
                return False
            
            # 获取当前时间
            now = datetime.now()
            
            # 计算信号时间与当前时间的差值
            time_diff = abs((now - signal_timestamp).total_seconds())
            time_diff_minutes = time_diff / 60
            
            # 检查是否在阈值范围内
            is_within_threshold = time_diff_minutes <= threshold_minutes
            
            # 检查是否在交易时间内
            current_time = now.time()
            morning_start = time(9, 30)
            morning_end = time(11, 30)
            afternoon_start = time(13, 0)
            afternoon_end = time(15, 0)
            
            is_trading_time = (
                (morning_start <= current_time <= morning_end) or
                (afternoon_start <= current_time <= afternoon_end)
            )
            
            # 只有同时满足时间阈值和交易时间才认为是实时信号
            is_realtime = is_within_threshold and is_trading_time
            
            if is_realtime:
                print(f"🔄 实时信号检测: 信号时间={signal_timestamp.strftime('%H:%M:%S')}, "
                      f"当前时间={now.strftime('%H:%M:%S')}, "
                      f"时间差={time_diff_minutes:.1f}分钟")
            
            return is_realtime
            
        except Exception as e:
            print(f"判断实时信号状态失败: {e}")
            # 出错时默认不播放声音，避免误报
            return False

    def _get_ma_prices(self) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """获取5日线、10日线和20日线价格（带缓存机制）"""
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 尝试从缓存获取
            cached_ma = self._get_cached_data('ma_prices')
            if cached_ma is not None:
                print(f"[DEBUG] 从缓存获取MA价格: MA5={cached_ma[0]}, MA10={cached_ma[1]}, MA20={cached_ma[2]}")
                return cached_ma

            # 获取足够的历史数据来计算均线
            start_date = self.trade_date - timedelta(days=30)  # 30天应该足够计算20日线
            end_date = self.trade_date
            
            # 根据证券类型获取日线数据
            # 获取证券类型和对应的数据接口代码
            security_type, symbol = self._get_security_type(self.code)
            
            if security_type == "INDEX":
                # 使用指数历史数据接口
                print(f"[DEBUG] 获取指数日线数据用于MA计算: {self.code} -> {symbol}")
                df = ak.index_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust=""
                )
            elif security_type == "ETF":
                # 使用ETF历史数据接口
                print(f"[DEBUG] 获取ETF日线数据用于MA计算: {self.code}")
                df = ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust="qfq"
                )
            else:
                # 使用股票历史数据接口
                print(f"[DEBUG] 获取股票日线数据用于MA计算: {self.code}")
                df = ak.stock_zh_a_hist(
                    symbol=symbol,
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust="qfq"
                )
            
            if df.empty:
                print(f"[DEBUG] 获取数据为空，代码: {self.code}")
                return None, None, None
                
            # 确保日期列为索引且按时间升序排列
            df['日期'] = pd.to_datetime(df['日期'])
            df = df.set_index('日期').sort_index()
            
            # 计算5日线、10日线和20日线
            df['MA5'] = df['收盘'].rolling(window=5, min_periods=5).mean()
            df['MA10'] = df['收盘'].rolling(window=10, min_periods=10).mean()
            df['MA20'] = df['收盘'].rolling(window=20, min_periods=20).mean()
            
            # 获取目标交易日的均线价格
            target_data = df.loc[df.index <= pd.Timestamp(self.trade_date)]
            if target_data.empty:
                print(f"[DEBUG] 目标日期没有数据，目标日期: {self.trade_date}")
                return None, None, None
                
            last_row = target_data.iloc[-1]
            ma5_price = last_row['MA5'] if not pd.isna(last_row['MA5']) else None
            ma10_price = last_row['MA10'] if not pd.isna(last_row['MA10']) else None
            ma20_price = last_row['MA20'] if not pd.isna(last_row['MA20']) else None
            
            # 添加调试信息
            print(f"[DEBUG] MA5: {ma5_price}, MA10: {ma10_price}, MA20: {ma20_price}")
            print(f"[DEBUG] 目标日期: {self.trade_date}, 代码: {self.code}")
            print(f"[DEBUG] 数据行数: {len(df)}, 最后日期: {df.index[-1]}")
            
            # 缓存结果
            ma_result = (ma5_price, ma10_price, ma20_price)
            self._set_cached_data('ma_prices', ma_result)
            print(f"[DEBUG] MA价格已缓存: {ma_result}")
            
            return ma_result
            
        except Exception as e:
            print(f"获取均线价格失败: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None

    # ------------------------------------------------------------------
    # 绘图
    # ------------------------------------------------------------------
    def _draw(self):
        # 检查窗口是否已销毁
        if self._is_destroyed:
            return
            
        if self.price_df is None:
            return
        
        # 非交易时间优化：检查是否需要重绘
        if not self._is_trading_time():
            if not self._should_redraw():
                print("[DEBUG] 非交易时间，跳过重绘")
                return
        
        # 如果没有分时数据，仍然可以显示支撑带和压力带
        if self.price_df.empty:
            print("[DEBUG] 分时数据为空，但尝试显示支撑带和压力带")
            self._draw_support_resistance_only()
            return
        
        # 支撑位和压力位已在_update_data方法中计算，这里不需要重复计算
        if self._support_resistance_calculated:
            print("[DEBUG] 支撑位和压力位已在_update_data中计算，跳过重复计算")
        else:
            print("[DEBUG] 警告：支撑位和压力位未在_update_data中计算，尝试在绘制时计算")
            # 备用机制：如果支撑位和压力位仍未计算，尝试在绘制时计算
            try:
                self._calculate_support_resistance()
                print("[DEBUG] 在_draw方法中成功计算支撑位和压力位")
            except Exception as e:
                print(f"[DEBUG] 在_draw方法中计算支撑位和压力位失败: {e}")
                # 如果第一次计算失败，尝试再次计算（可能是网络延迟问题）
                try:
                    print("[DEBUG] 在_draw方法中第一次计算失败，尝试重新计算支撑位和压力位")
                    import time
                    time.sleep(1)  # 等待1秒后重试
                    self._calculate_support_resistance()
                    print("[DEBUG] 在_draw方法中重试计算支撑位和压力位成功")
                except Exception as e2:
                    print(f"[DEBUG] 在_draw方法中重试计算支撑位和压力位仍然失败: {e2}")
                    # 即使计算失败，也要确保有基本的买卖信号
                    if self.buy_signals is None:
                        print("[DEBUG] 买入信号为None，初始化为空列表")
                        self.buy_signals = []
                    if self.sell_signals is None:
                        print("[DEBUG] 卖出信号为None，初始化为空列表")
                        self.sell_signals = []
        
        # 重新计算突破跌破次数，确保显示与音效同步
        try:
            print("[DEBUG] 在_draw方法中重新计算突破跌破次数")
            # 重置计算标志，允许重新计算
            self._breakthrough_breakdown_calculated = False
            self._calculate_breakthrough_breakdown_count()
        except Exception as e:
            print(f"[DEBUG] 在_draw方法中计算突破跌破次数失败: {e}")

        # 清理
        self.ax_price.clear()
        self.ax_cost.clear()
        self.ax_rsi.clear()

        # --- 主图：分时价格 ---
        x_times = self.price_df.index
        prices = self.price_df["close"].values
        x_index = np.arange(len(prices))
        
        # 计算分割线位置（上一个交易日数据与当日数据的分界点）
        split_index = None
        if self.SHOW_PREVIOUS_DAY_DATA:
            # 找到当日数据的起始位置
            current_date_start = pd.Timestamp(f"{self.trade_date_str} 09:30:00")
            split_mask = x_times >= current_date_start
            if split_mask.any():
                split_index = np.where(split_mask)[0][0]
        
        # 先绘制5分钟K线柱子（不透明，绿跌红涨）
        self._plot_5min_candlesticks(x_index, x_times)
        
        # 再绘制分时价格曲线，叠加在柱子上
        self.ax_price.plot(x_index, prices, color="black", linewidth=1, label="分时价格")
        
        # 绘制分割线（如果存在上一个交易日数据）
        if split_index is not None and split_index > 0:
            self.ax_price.axvline(x=split_index, color="black", linestyle="-", linewidth=1, alpha=0.7, label="分割线")
        
        # 绘制移动平均线 - 移除分钟级MA5、MA10曲线
        # 注释掉分钟级移动平均线绘制
        # if self.ma_short_values is not None and not self.ma_short_values.isna().all():
        #     self.ax_price.plot(x_index, self.ma_short_values.values, color="skyblue", linewidth=1.2, alpha=0.8, label=f"MA{self.MA_SHORT_PERIOD}")
        # 
        # if self.ma_mid_values is not None and not self.ma_mid_values.isna().all():
        #     self.ax_price.plot(x_index, self.ma_mid_values.values, color="pink", linewidth=1.2, alpha=0.8, label=f"MA{self.MA_MID_PERIOD}")
        
        # 绘制基础均线（淡褐色）
        if self.ma_base_values is not None and not self.ma_base_values.isna().all():
            self.ax_price.plot(x_index, self.ma_base_values.values, color="#D2B48C", linewidth=1.5, alpha=0.9, label=f"MA{self.MA_BASE_PERIOD}")
        
        # 绘制5分钟级别布林带（中轨黄色版本，与同花顺一致）
        if self._bollinger_calculated and self.bollinger_5min_upper is not None:
            self._plot_bollinger_bands(x_index, prices.astype(float))
        
        # 绘制买入信号圆圈
        if self.buy_signals is not None and len(self.buy_signals) > 0:
            self._plot_buy_signals(x_index, prices.astype(float))
        
        # 绘制卖出信号圆圈
        if self.sell_signals is not None and len(self.sell_signals) > 0:
            self._plot_sell_signals(x_index, prices.astype(float))
        
        # 绘制最新价格RSI信息信号
        self._plot_latest_rsi_signal(x_index, prices.astype(float))

        # Y 轴范围改为当前走势已出现的最大涨跌幅 (绝对值)
        # 使用前一交易日收盘价作为基准，而不是当日开盘价
        prev_close = self._get_previous_close()
        if prev_close is None:
            # 如果无法获取前一交易日收盘价，则使用当日第一个价格作为备选
            prev_close = prices[0]
        
        # 计算绝对最大涨跌幅
        pct_changes = (np.array(prices) - prev_close) / prev_close
        max_abs_pct = float(np.max(np.abs(pct_changes))) if len(pct_changes) else 0.0
        # 若全部价格相同, 给予1%最小区间
        if max_abs_pct == 0:
            max_abs_pct = 0.01
        # 预留2%可视缓冲，并确保最小价格范围
        limit_pct = max_abs_pct * 1.02
        min_range_pct = 0.03  # 最小3%的价格范围，确保平均成本线有足够显示空间
        limit_pct = max(limit_pct, min_range_pct)
        
        # 考虑布林带范围，但使用稳定的方式避免频繁变动
        if self._bollinger_calculated and self.bollinger_5min_upper is not None and self.bollinger_5min_lower is not None:
            # 计算布林带的涨跌幅范围
            boll_upper_pct = (self.bollinger_5min_upper.max() - prev_close) / prev_close
            boll_lower_pct = (prev_close - self.bollinger_5min_lower.min()) / prev_close
            boll_max_pct = max(boll_upper_pct, boll_lower_pct)
            
            # 只有当布林带范围明显大于当前价格范围时才考虑扩展
            # 使用1.2倍作为阈值，避免频繁调整
            if boll_max_pct > limit_pct * 1.2:
                limit_pct = max(limit_pct, boll_max_pct * 1.1)  # 布林带范围加10%缓冲
                print(f"[DEBUG] 根据布林带扩展价格范围，布林带范围: {boll_max_pct:.3f}, 调整后范围: {limit_pct:.3f}")
        
        # 计算基础价格范围
        base_up_price = prev_close * (1 + limit_pct)
        base_down_price = prev_close * (1 - limit_pct)

        # 新增：检查支撑位、压力位、前高价格带和前低价格带是否需要扩展价格区间
        # 支撑位和压力位使用5%范围，前高/前低价格带使用10%范围
        five_point_pct = 0.05  # 5% - 用于支撑位和压力位
        ten_point_pct = 0.10   # 10% - 用于前高/前低价格带
        five_point_up = prev_close * (1 + five_point_pct)
        five_point_down = prev_close * (1 - five_point_pct)
        ten_point_up = prev_close * (1 + ten_point_pct)
        ten_point_down = prev_close * (1 - ten_point_pct)
        
        # 检查支撑位是否需要扩展价格区间（使用5%范围）
        if self.support_level is not None:
            if self.support_level < base_down_price and self.support_level >= five_point_down:
                # 支撑位在价格区间下方但在5%范围内，向下扩展
                base_down_price = self.support_level * 0.995  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：支撑位{self.support_level:.3f}在价格区间下方，向下扩展至{base_down_price:.3f}")
            elif self.support_level > base_up_price and self.support_level <= five_point_up:
                # 支撑位在价格区间上方但在5%范围内，向上扩展
                base_up_price = self.support_level * 1.005  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：支撑位{self.support_level:.3f}在价格区间上方，向上扩展至{base_up_price:.3f}")
        
        # 检查压力位是否需要扩展价格区间（使用5%范围）
        if self.resistance_level is not None:
            if self.resistance_level < base_down_price and self.resistance_level >= five_point_down:
                # 压力位在价格区间下方但在5%范围内，向下扩展
                base_down_price = self.resistance_level * 0.995  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：压力位{self.resistance_level:.3f}在价格区间下方，向下扩展至{base_down_price:.3f}")
            elif self.resistance_level > base_up_price and self.resistance_level <= five_point_up:
                # 压力位在价格区间上方但在5%范围内，向上扩展
                base_up_price = self.resistance_level * 1.005  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：压力位{self.resistance_level:.3f}在价格区间上方，向上扩展至{base_up_price:.3f}")
        
        # 检查当前平均成本是否需要扩展价格区间（使用10%范围）
        # 增加稳定性：只有当平均成本偏离当前范围超过2%时才调整，避免频繁切换
        current_cost = self._get_latest_cost()
        if current_cost is not None:
            cost_deviation_threshold = 0.02  # 2%的偏离阈值
            cost_down_threshold = base_down_price * (1 - cost_deviation_threshold)
            cost_up_threshold = base_up_price * (1 + cost_deviation_threshold)
            
            if current_cost < cost_down_threshold and current_cost >= ten_point_down:
                # 平均成本在价格区间下方但在10%范围内，且偏离超过2%，向下扩展
                base_down_price = current_cost * 0.995  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：当前平均成本{current_cost:.3f}在价格区间下方，向下扩展至{base_down_price:.3f}")
            elif current_cost > cost_up_threshold and current_cost <= ten_point_up:
                # 平均成本在价格区间上方但在10%范围内，且偏离超过2%，向上扩展
                base_up_price = current_cost * 1.005  # 留出0.5%的缓冲
                print(f"[DEBUG] 扩展价格区间：当前平均成本{current_cost:.3f}在价格区间上方，向上扩展至{base_up_price:.3f}")
        
        # 检查前高价格带是否需要扩展价格区间
        if hasattr(self, 'previous_high_dual_prices') and self.previous_high_dual_prices is not None:
            dual_prices = self.previous_high_dual_prices
            if dual_prices.get('resistance_band'):
                band = dual_prices['resistance_band']
                band_upper = band['upper']  # 上影线最高价
                band_lower = band['lower']  # 实体最高价
                
                # 计算前高价格带相对于前一交易日收盘价的涨幅
                band_upper_pct = (band_upper - prev_close) / prev_close
                band_lower_pct = (band_lower - prev_close) / prev_close
                
                print(f"[DEBUG] 前高价格带涨幅检查:")
                print(f"[DEBUG]   上边界涨幅: {band_upper_pct*100:.2f}%")
                print(f"[DEBUG]   下边界涨幅: {band_lower_pct*100:.2f}%")
                print(f"[DEBUG]   10%涨幅范围: {ten_point_down:.3f} - {ten_point_up:.3f}")
                
                # 修改逻辑：只要最低点（实体最高价）在10%阈值内，就显示包括最高点的完整价格范围
                if ten_point_down <= band_lower <= ten_point_up:
                    # 检查上边界是否需要扩展（显示完整的价格带，包括最高点）
                    if band_upper > base_up_price:
                        base_up_price = band_upper * 1.005  # 留出0.5%的缓冲
                        print(f"[DEBUG] 扩展价格区间：前高价格带最低点{band_lower:.3f}在10%范围内，向上扩展至最高点{band_upper:.3f}")
                    
                    # 检查下边界是否需要扩展
                    if band_lower < base_down_price:
                        base_down_price = band_lower * 0.995  # 留出0.5%的缓冲
                        print(f"[DEBUG] 扩展价格区间：前高价格带最低点{band_lower:.3f}在10%范围内，向下扩展至{base_down_price:.3f}")
                else:
                    print(f"[DEBUG] 前高价格带最低点{band_lower:.3f}不在10%涨幅范围内，不扩展显示区间")

        # 检查前低价格带是否需要扩展价格区间
        if hasattr(self, 'previous_low_dual_prices') and self.previous_low_dual_prices is not None:
            dual_prices = self.previous_low_dual_prices
            if dual_prices.get('support_band'):
                band = dual_prices['support_band']
                band_upper = band['upper']  # 实体最低价
                band_lower = band['lower']  # 下影线最低价
                
                # 计算前低价格带相对于前一交易日收盘价的跌幅
                band_upper_pct = (band_upper - prev_close) / prev_close
                band_lower_pct = (band_lower - prev_close) / prev_close
                
                print(f"[DEBUG] 前低价格带跌幅检查:")
                print(f"[DEBUG]   上边界跌幅: {band_upper_pct*100:.2f}%")
                print(f"[DEBUG]   下边界跌幅: {band_lower_pct*100:.2f}%")
                print(f"[DEBUG]   10%跌幅范围: {ten_point_down:.3f} - {ten_point_up:.3f}")
                
                # 修改逻辑：只要最高点（实体最低价）在10%阈值内，就显示包括最低点的完整价格范围
                if ten_point_down <= band_upper <= ten_point_up:
                    # 检查上边界是否需要扩展
                    if band_upper > base_up_price:
                        base_up_price = band_upper * 1.005  # 留出0.5%的缓冲
                        print(f"[DEBUG] 扩展价格区间：前低价格带最高点{band_upper:.3f}在10%范围内，向上扩展至{base_up_price:.3f}")
                    
                    # 检查下边界是否需要扩展（显示完整的价格带，包括最低点）
                    if band_lower < base_down_price:
                        base_down_price = band_lower * 0.995  # 留出0.5%的缓冲
                        print(f"[DEBUG] 扩展价格区间：前低价格带最高点{band_upper:.3f}在10%范围内，向下扩展至最低点{band_lower:.3f}")
                else:
                    print(f"[DEBUG] 前低价格带最高点{band_upper:.3f}不在10%跌幅范围内，不扩展显示区间")

        # 使用价格范围合并机制，确保新范围只能扩展不能缩小
        final_down_price, final_up_price = self._merge_price_range(base_down_price, base_up_price)
        
        # 设置轴范围
        self.ax_price.set_ylim(final_down_price, final_up_price)

        # 基准线（前一交易日收盘价）
        self.ax_price.axhline(prev_close, color="gray", linestyle="--", linewidth=0.8, label="前收盘")
        
        # 百分比背景填充区域：正负3%, 6%, 9%, 10%的分层背景
        # 正涨幅区域：3%~6%浅红色，6%~9%深红色，9%~10%全红色
        # 负跌幅区域：-3%~-6%浅绿色，-6%~-9%深绿色，-9%~-10%全绿色
        
        # 定义填充区域的颜色和范围
        positive_zones = [
            (3, 6, "#FE9999"),    # 浅红色 3%~6% (最浅)
            (6, 9, "#FF4C4C"),    # 深红色 6%~9% (中等)
            (9, 30, "#FF0000")    # 全红色 9%~10% (降低亮度)
        ]
        
        negative_zones = [
            (-6, -3, "#99FE99"),  # 浅绿色 -6%~-3% (最浅)
            (-9, -6, "#4CFF4C"),  # 深绿色 -9%~-6% (中等)
            (-30, -9, "#00CC00")  # 全绿色 -10%~-9% (降低亮度)
        ]
        
        # 绘制正涨幅背景填充
        for low_pct, high_pct, color in positive_zones:
            low_price = prev_close * (1 + low_pct / 100)
            high_price = prev_close * (1 + high_pct / 100)
            
            # 确保价格在当前Y轴范围内
            if final_down_price <= high_price and final_up_price >= low_price:
                # 裁剪到可见范围
                fill_low = max(low_price, final_down_price)
                fill_high = min(high_price, final_up_price)
                if fill_high > fill_low:
                    self.ax_price.axhspan(fill_low, fill_high, facecolor=color, alpha=0.2, zorder=0)
        
        # 绘制负跌幅背景填充
        for low_pct, high_pct, color in negative_zones:
            low_price = prev_close * (1 + low_pct / 100)
            high_price = prev_close * (1 + high_pct / 100)
            
            # 确保价格在当前Y轴范围内
            if final_down_price <= high_price and final_up_price >= low_price:
                # 裁剪到可见范围
                fill_low = max(low_price, final_down_price)
                fill_high = min(high_price, final_up_price)
                if fill_high > fill_low:
                    self.ax_price.axhspan(fill_low, fill_high, facecolor=color, alpha=0.2, zorder=0)
        
        # 5日线（蓝色虚线）、10日线（橙色虚线）和20日线（绿色虚线）
        if self.ma5_price is not None and final_down_price <= self.ma5_price <= final_up_price:
            self.ax_price.axhline(self.ma5_price, color="blue", linestyle="--", linewidth=1, alpha=0.8, label="5日线")
        if self.ma10_price is not None and final_down_price <= self.ma10_price <= final_up_price:
            self.ax_price.axhline(self.ma10_price, color="orange", linestyle="--", linewidth=1, alpha=0.8, label="10日线")
        if self.ma20_price is not None and final_down_price <= self.ma20_price <= final_up_price:
            self.ax_price.axhline(self.ma20_price, color="green", linestyle="--", linewidth=1, alpha=0.8, label="20日线")
        
        # 新增：绘制支撑位和压力位（与MA5、MA10保持一致）
        if self.support_level is not None and final_down_price <= self.support_level <= final_up_price:
            self.ax_price.axhline(self.support_level, color="red", linestyle="--", linewidth=1, alpha=0.8, label=f"支撑位({self.support_type})")
        if self.resistance_level is not None and final_down_price <= self.resistance_level <= final_up_price:
            self.ax_price.axhline(self.resistance_level, color="green", linestyle="--", linewidth=1, alpha=0.8, label=f"压力位({self.resistance_type})")
        
        # 新增：绘制看涨线和看跌线 - 根据开盘价和上一个交易日涨跌情况确定线型
        if (self.bullish_line_price is not None and final_down_price <= self.bullish_line_price <= final_up_price) or \
           (self.bearish_line_price is not None and final_down_price <= self.bearish_line_price <= final_up_price):
            
            # 确定线型
            bullish_style, bearish_style = self._determine_line_styles()
            
            # 计算图表宽度的1/4
            chart_width = len(x_index)
            line_length = chart_width / 4
            
            # 绘制看涨线
            if self.bullish_line_price is not None and final_down_price <= self.bullish_line_price <= final_up_price:
                self.ax_price.hlines(self.bullish_line_price, xmin=0, xmax=line_length, 
                                   color="red", linestyle=bullish_style, linewidth=2, alpha=0.9, label="看涨线")
            
            # 绘制看跌线
            if self.bearish_line_price is not None and final_down_price <= self.bearish_line_price <= final_up_price:
                self.ax_price.hlines(self.bearish_line_price, xmin=0, xmax=line_length, 
                                   color="green", linestyle=bearish_style, linewidth=2, alpha=0.9, label="看跌线")
        
        
        # 新增：绘制当前平均成本线（粉色虚线）
        current_cost = self._get_latest_cost()
        if current_cost is not None and final_down_price <= current_cost <= final_up_price:
            self.ax_price.axhline(current_cost, color="#FF69B4", linestyle="-", linewidth=2, alpha=0.8, label="当前平均成本")
        
        # 新增：绘制前高价格阻力带
        if hasattr(self, 'previous_high_dual_prices') and self.previous_high_dual_prices is not None:
            dual_prices = self.previous_high_dual_prices
            if dual_prices.get('resistance_band'):
                band = dual_prices['resistance_band']
                upper_price = band['upper']  # 上影线最高价
                lower_price = band['lower']  # 实体最高价
                
                # 确保阻力带在可见范围内
                if final_down_price <= upper_price <= final_up_price or final_down_price <= lower_price <= final_up_price:
                    # 计算最小可见高度（确保阻力带有足够的像素高度）
                    price_range = final_up_price - final_down_price
                    min_band_height = price_range * 0.01  # 至少占价格范围的1%
                    
                    # 如果两个价格相等或接近，扩展阻力带
                    if abs(upper_price - lower_price) < min_band_height:
                        center_price = (upper_price + lower_price) / 2
                        upper_price = center_price + min_band_height / 2
                        lower_price = center_price - min_band_height / 2
                        print(f"[DEBUG] 分时窗口 - 扩展阻力带以确保可见度: {lower_price:.3f} - {upper_price:.3f}")
                    
                    # 绘制阻力带（绿色填充，添加线条图案）
                    self.ax_price.axhspan(
                        lower_price, upper_price,
                        facecolor="green", alpha=0.3, zorder=1,
                        hatch='\\',  # 斜线填充
                        edgecolor='darkgreen',  # 边框颜色
                        linewidth=0.5,  # 边框宽度
                        label=f"前高阻力带({lower_price:.2f}-{upper_price:.2f})"
                    )
                    
                    print(f"[DEBUG] 分时窗口 - 绘制前高阻力带: {lower_price:.3f} - {upper_price:.3f}")
        
        # 保持兼容性：如果没有双价格数据，使用单一前高价格线
        elif hasattr(self, 'previous_high_price') and self.previous_high_price is not None:
            if final_down_price <= self.previous_high_price <= final_up_price:
                self.ax_price.axhline(
                    self.previous_high_price, 
                    color="purple", 
                    linestyle="--", 
                    linewidth=1.5, 
                    alpha=0.8, 
                    label=f"前高价格({self.previous_high_price:.2f})"
                )
                print(f"[DEBUG] 分时窗口 - 绘制前高价格线: {self.previous_high_price:.3f}")

        # 新增：绘制前低价格支撑带
        if hasattr(self, 'previous_low_dual_prices') and self.previous_low_dual_prices is not None:
            dual_prices = self.previous_low_dual_prices
            if dual_prices.get('support_band'):
                band = dual_prices['support_band']
                upper_price = band['upper']  # 实体最低价
                lower_price = band['lower']  # 下影线最低价
                
                # 检查支撑带是否在显示范围内
                if (final_down_price <= upper_price <= final_up_price or 
                    final_down_price <= lower_price <= final_up_price or
                    (lower_price < final_down_price and upper_price > final_up_price)):
                    
                    # 绘制支撑带（红色填充，添加线条图案）
                    self.ax_price.axhspan(
                        lower_price, upper_price,
                        facecolor="red", alpha=0.3, zorder=1,
                        hatch='/',  # 反斜线填充
                        edgecolor='darkred',  # 边框颜色
                        linewidth=0.5,  # 边框宽度
                        label=f"前低支撑带({lower_price:.2f}-{upper_price:.2f})"
                    )
                    
                    print(f"[DEBUG] 分时窗口 - 绘制前低支撑带: {lower_price:.3f} - {upper_price:.3f}")
        
        # 保持兼容性：如果没有双价格数据，使用单一前低价格线
        elif hasattr(self, 'previous_low_price') and self.previous_low_price is not None:
            if final_down_price <= self.previous_low_price <= final_up_price:
                self.ax_price.axhline(
                    self.previous_low_price, 
                    color="red", 
                    linestyle="--", 
                    linewidth=1.5, 
                    alpha=0.8, 
                    label=f"前低价格({self.previous_low_price:.2f})"
                )
                print(f"[DEBUG] 分时窗口 - 绘制前低价格线: {self.previous_low_price:.3f}")
        


        # 设置自定义价格刻度和标签
        price_ticks = []
        price_labels = []

        # 添加基准价
        price_ticks.append(prev_close)
        price_labels.append(f"{prev_close:.2f}")

        # 添加MA5、MA10和MA20的价格
        if self.ma5_price is not None and final_down_price <= self.ma5_price <= final_up_price:
            price_ticks.append(self.ma5_price)
            price_labels.append(f"{self.ma5_price:.2f}")

        if self.ma10_price is not None and final_down_price <= self.ma10_price <= final_up_price:
            price_ticks.append(self.ma10_price)
            price_labels.append(f"{self.ma10_price:.2f}")

        if self.ma20_price is not None and final_down_price <= self.ma20_price <= final_up_price:
            price_ticks.append(self.ma20_price)
            price_labels.append(f"{self.ma20_price:.2f}")
        
        # 添加基础均线的价格（如果可见）
        if self.ma_base_values is not None and not self.ma_base_values.isna().all():
            # 获取最新的基础均线值
            latest_ma_base = self.ma_base_values.iloc[-1]
            if final_down_price <= latest_ma_base <= final_up_price:
                price_ticks.append(latest_ma_base)
                price_labels.append(f"{latest_ma_base:.2f}")
        
        # 新增：添加支撑位和压力位的价格刻度
        if self.support_level is not None and final_down_price <= self.support_level <= final_up_price:
            price_ticks.append(self.support_level)
            price_labels.append(f"{self.support_level:.2f}")
        
        if self.resistance_level is not None and final_down_price <= self.resistance_level <= final_up_price:
            price_ticks.append(self.resistance_level)
            price_labels.append(f"{self.resistance_level:.2f}")
        
        # 新增：添加看涨线和看跌线的价格刻度
        if self.bullish_line_price is not None and final_down_price <= self.bullish_line_price <= final_up_price:
            price_ticks.append(self.bullish_line_price)
            price_labels.append(f"{self.bullish_line_price:.2f}")
        
        if self.bearish_line_price is not None and final_down_price <= self.bearish_line_price <= final_up_price:
            price_ticks.append(self.bearish_line_price)
            price_labels.append(f"{self.bearish_line_price:.2f}")

        # 设置刻度和标签
        if self.volume_display_enabled:
            # 总成交量显示模式：隐藏价格标签，在成交量子图中显示总成交量柱子
            self.ax_price.set_yticks(price_ticks)
            self.ax_price.set_yticklabels([""] * len(price_ticks), fontsize=8)  # 隐藏价格文字
            self.ax_price.grid(True, axis='y', linestyle="--", alpha=0.3)
            
            # 绘制总成交量横向柱子（会动态创建成交量子图）
            self._plot_volume_display_lines(x_index, x_times)
            
            # 显示成交量子图
            if self.ax_volume is not None:
                self.ax_volume.set_visible(True)
        else:
            # 正常模式：显示价格标签，隐藏成交量子图
            self.ax_price.set_yticks(price_ticks)
            self.ax_price.set_yticklabels(price_labels, fontsize=8)
            # 移除价格标签文字
            # self.ax_price.set_ylabel("价格", fontsize=8)
            self.ax_price.grid(True, axis='y', linestyle="--", alpha=0.3)
            
            # 隐藏成交量子图
            if self.ax_volume is not None:
                self.ax_volume.set_visible(False)

        # 右侧百分比轴: 若已有旧轴, 先移除避免重叠
        if self._ax_price_pct and self._ax_price_pct in self.fig.axes:
            try:
                self._ax_price_pct.remove()
            except Exception:
                pass

        ax_pct = self.ax_price.twinx()
        self._ax_price_pct = ax_pct
        ax_pct.set_ylim(
            (self.ax_price.get_ylim()[0] - prev_close) / prev_close * 100,
            (self.ax_price.get_ylim()[1] - prev_close) / prev_close * 100,
        )
        
        # 设置自定义刻度和标签
        y_ticks = []
        y_labels = []
        y_min, y_max = ax_pct.get_ylim()
        
        # 添加百分比刻度：3%, 6%, 9%
        for pct in [3, 6, 9]:
            if -pct >= y_min:
                y_ticks.append(-pct)
                y_labels.append(f"-{pct}%")
            if pct <= y_max:
                y_ticks.append(pct)
                y_labels.append(f"+{pct}%")
        
        # 添加MA5和MA10的刻度
        if self.ma5_price is not None and prev_close > 0:
            ma5_pct = (self.ma5_price - prev_close) / prev_close * 100
            if y_min <= ma5_pct <= y_max:
                y_ticks.append(ma5_pct)
                y_labels.append(f"MA5\n{ma5_pct:+.1f}%")
        
        if self.ma10_price is not None and prev_close > 0:
            ma10_pct = (self.ma10_price - prev_close) / prev_close * 100
            if y_min <= ma10_pct <= y_max:
                y_ticks.append(ma10_pct)
                y_labels.append(f"MA10\n{ma10_pct:+.1f}%")
        
        # 添加基础均线的刻度（如果可见）
        if self.ma_base_values is not None and not self.ma_base_values.isna().all() and prev_close > 0:
            latest_ma_base = self.ma_base_values.iloc[-1]
            ma_base_pct = (latest_ma_base - prev_close) / prev_close * 100
            if y_min <= ma_base_pct <= y_max:
                y_ticks.append(ma_base_pct)
                y_labels.append(f"MA{self.MA_BASE_PERIOD}\n{ma_base_pct:+.1f}%")
        
        # 新增：添加支撑位和压力位的百分比刻度
        if self.support_level is not None and prev_close > 0:
            support_pct = (self.support_level - prev_close) / prev_close * 100
            if y_min <= support_pct <= y_max:
                y_ticks.append(support_pct)
                y_labels.append(f"支撑位\n{support_pct:+.1f}%")
        
        if self.resistance_level is not None and prev_close > 0:
            resistance_pct = (self.resistance_level - prev_close) / prev_close * 100
            if y_min <= resistance_pct <= y_max:
                y_ticks.append(resistance_pct)
                y_labels.append(f"压力位\n{resistance_pct:+.1f}%")
        
        # 前高阻力带不在Y轴显示涨幅刻度
        # 保持兼容性：如果没有双价格数据，使用单一前高价格刻度
        elif hasattr(self, 'previous_high_price') and self.previous_high_price is not None and prev_close > 0:
            previous_high_pct = (self.previous_high_price - prev_close) / prev_close * 100
            if y_min <= previous_high_pct <= y_max:
                y_ticks.append(previous_high_pct)
                y_labels.append(f"前高价格\n{previous_high_pct:+.1f}%")

        # 前低支撑带不在Y轴显示涨幅刻度
        # 保持兼容性：如果没有双价格数据，使用单一前低价格刻度
        elif hasattr(self, 'previous_low_price') and self.previous_low_price is not None and prev_close > 0:
            previous_low_pct = (self.previous_low_price - prev_close) / prev_close * 100
            if y_min <= previous_low_pct <= y_max:
                y_ticks.append(previous_low_pct)
                y_labels.append(f"前低价格\n{previous_low_pct:+.1f}%")
        
        # 添加0%基准线
        if y_min <= 0 <= y_max:
            y_ticks.append(0)
            y_labels.append("0%")
        
        # 设置刻度和标签
        ax_pct.set_yticks(y_ticks)
        ax_pct.set_yticklabels(y_labels)
        ax_pct.tick_params(axis="y", labelcolor="gray", labelsize=8)

        # 添加突破和跌破次数显示
        self._plot_breakthrough_breakdown_count()

        # --- 幅图：平均成本 ---
        if self.cost_df is not None and not self.cost_df.empty:
            # 对齐索引
            cost_series = self._get_cost_series(x_times)
            self._plot_cost_panel(x_index, x_times, cost_series, split_index)

        # 成交量柱图已移至RSI面板中绘制

        # --- RSI指标图 ---
        if self.rsi_df is not None and not self.rsi_df.empty:
            self._plot_rsi_panel(x_index, x_times, split_index)

        # 在所有子图绘制完成后，最后设置时间轴刻度（确保不被覆盖）
        self._draw_time_grid(x_index, x_times)

        # 重新布局(仅首次调用), 避免重复tight_layout压缩导致子图越来越小
        if not getattr(self, "_tight_layout_done", False):
            # 使用与K线图窗口一致的紧凑布局设置
            self.fig.subplots_adjust(
                left=0.12,    # 左边距，为y轴标签留出空间
                right=0.92,   # 右边距，为y轴数值留出空间
                top=0.99,     # 上边距
                bottom=0.05,  # 底部inset设置为最小，减少空白
                hspace=0.0375   # 子图间距，与K线图窗口保持一致
            )
            self._tight_layout_done = True
        else:
            # 后续仅微调子图间距，保持紧凑布局
            self.fig.subplots_adjust(hspace=0.0375, top=0.99, bottom=0.05)
        
        # 绑定鼠标事件（仅在首次绘制时绑定）
        if not hasattr(self, '_mouse_events_bound'):
            self._bind_mouse_events()
            self._mouse_events_bound = True
        
        self.canvas.draw_idle()
        
        # 更新重绘时间戳
        from datetime import datetime
        self._last_redraw_time = datetime.now()

    def _on_window_configure(self, event):
        """处理窗口大小变动事件"""
        if event.widget == self.window:
            print("[DEBUG] 窗口大小变动，触发重绘")
            self._ui_event_redraw = True
            # 延迟重绘，避免频繁调用
            if hasattr(self, '_configure_timer'):
                self.window.after_cancel(self._configure_timer)
            self._configure_timer = self.window.after(100, self._trigger_redraw)

    def _on_window_focus(self, event):
        """处理窗口获得焦点事件"""
        print("[DEBUG] 窗口获得焦点，触发重绘")
        self._ui_event_redraw = True
        self._trigger_redraw()

    def _on_window_click(self, event):
        """处理窗口点击事件"""
        print("[DEBUG] 窗口点击，触发重绘")
        self._ui_event_redraw = True
        self._trigger_redraw()

    def _on_window_click_release(self, event):
        """处理窗口点击释放事件"""
        print("[DEBUG] 窗口点击释放，触发重绘")
        self._ui_event_redraw = True
        self._trigger_redraw()

    def _trigger_redraw(self):
        """触发重绘"""
        if not self._is_destroyed and hasattr(self, 'window') and self.window and self.window.winfo_exists():
            self.window.after(0, self._draw)

    def force_redraw(self):
        """强制重绘（公共方法，供外部调用）"""
        print("[DEBUG] 外部触发强制重绘")
        self._force_redraw = True
        if not self._is_destroyed and hasattr(self, 'window') and self.window and self.window.winfo_exists():
            self.window.after(0, self._draw)

    def _plot_cost_panel(self, x_index, x_times, cost_series, split_index=None):
        """绘制成本面板(供 _draw 与 _redraw_cost 复用)"""
        # 清除旧轴
        self.ax_cost.clear()
        # 若之前创建过 twin 轴，移除避免叠加
        if hasattr(self, "_ax_cost_pct") and self._ax_cost_pct in self.fig.axes:
            try:
                self._ax_cost_pct.remove()
            except Exception:
                pass
        
        # 确保成本数据与x_index对齐
        if len(cost_series) == len(x_index):
            cost_values = cost_series.values
        else:
            # 如果长度不匹配，重新对齐
            cost_values = cost_series.reindex(x_times).values
        
        # 主成本线: 使用实线
        self.ax_cost.plot(
            x_index,
            cost_values,
            color="orange",
            linewidth=1,
            linestyle="-",
            label="平均成本",
        )
        
        # 涨幅轴
        prev_cost = self._get_previous_trade_cost()
        if prev_cost is None:
            non_nan = cost_series.dropna()
            if len(non_nan) > 0:
                prev_cost = float(non_nan.iloc[0])
        prev_cost = prev_cost or 1.0
        pct_series = (cost_series - prev_cost) / prev_cost * 100
        ax_pct = self.ax_cost.twinx()
        self._ax_cost_pct = ax_pct
        # 仅保留右侧刻度，不绘制折线，避免视觉干扰
        ax_pct.plot(x_index, pct_series.values, alpha=0)  # 隐藏曲线
        ax_pct.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{y:.1f}%"))
        ax_pct.tick_params(axis="y", labelcolor="blue", labelsize=8)
        # 移除平均成本标签文字
        # self.ax_cost.set_ylabel("平均成本", fontsize=8)
        self.ax_cost.tick_params(axis='y', labelsize=8)
        self.ax_cost.grid(True, axis='y', linestyle="--", alpha=0.3)
        
        # 确保X轴范围与主图一致（使用固定时间范围）
        self._set_axis_xlim(self.ax_cost, x_times)
        
        # 绘制分割线（如果存在上一个交易日数据）
        if split_index is not None and split_index > 0:
            self.ax_cost.axvline(x=split_index, color="black", linestyle="-", linewidth=1, alpha=0.7)

        # ---------- 背景色区段 ----------
        # 仅对正涨幅区域着色，根据当前y轴上限裁剪
        y_max = ax_pct.get_ylim()[1]
        bands = [
            (1, 3, "#FFF9D1"),   # 淡黄色
            (3, 6, "#FFD59E"),  # 橙色(浅)
            (6, 20, "#FFA07A"), # 橙色
            (20, 100, "#DDA0DD") # 紫色
        ]
        for low, high, color in bands:
            if low >= y_max:
                break  # 超出可见范围
            band_low = max(low, 0)
            band_high = min(high, y_max)
            if band_high > band_low:
                ax_pct.axhspan(band_low, band_high, facecolor=color, alpha=0.2, zorder=0)

        # ---------- 当前价相对平均成本 ----------
        try:
            # 使用成本序列最后一个非NaN值对应的时间
            valid_idx = cost_series.last_valid_index()
            if valid_idx is not None and self.price_df is not None and valid_idx in self.price_df.index:
                # 使用Pandas的scalar值提取
                current_price = self.price_df.at[valid_idx, "close"]
                current_cost = cost_series.at[valid_idx]
                if pd.isna(current_price) or pd.isna(current_cost):
                    return
                if current_cost > 0:
                    diff_pct = float((current_price - current_cost) / current_cost * 100)
                    label_color = "#E74C3C" if diff_pct >= 0 else "#2ECC71"  # 红涨绿跌
                    self.ax_cost.text(
                        0.01,
                        0.95,
                        f"价差: {diff_pct:+.2f}%",
                        transform=self.ax_cost.transAxes,
                        fontsize=8,
                        color=label_color,
                        verticalalignment="top",
                        bbox=dict(facecolor="white", alpha=0.7, pad=2),
                    )

                    # 颜色说明标签 (底部显示, 字体稍大)
                    legend_y = 0.05
                    self.ax_cost.text(
                        0.01,
                        legend_y,
                        "黄色:可买入持有",
                        transform=self.ax_cost.transAxes,
                        fontsize=9,
                        color="#E5A800",
                        verticalalignment="bottom",
                    )
                    self.ax_cost.text(
                        0.25,
                        legend_y,
                        "橙色:只当日T",
                        transform=self.ax_cost.transAxes,
                        fontsize=9,
                        color="#FF8C00",
                        verticalalignment="bottom",
                    )
                    self.ax_cost.text(
                        0.45,
                        legend_y,
                        "红色:不可买入",
                        transform=self.ax_cost.transAxes,
                        fontsize=9,
                        color="#FF0000",
                        verticalalignment="bottom",
                    )
        except Exception:
            pass

    def _plot_rsi_panel(self, x_index, x_times, split_index=None):
        """绘制RSI面板"""
        # 清除旧轴
        self.ax_rsi.clear()
        
        # 检查RSI数据是否存在
        if self.rsi_df is None or self.rsi_df.empty:
            return
        
        # 使用显示用的RSI数据（5分钟RSI使用线性插值）
        rsi_df_to_plot = getattr(self, 'rsi_df_display', self.rsi_df)
        
        # 绘制KDJ D值曲线（褐色）
        if self.kdj_df is not None and not self.kdj_df.empty and 'D' in self.kdj_df.columns:
            d_values = self.kdj_df['D'].values
            if not pd.isna(d_values).all():
                self.ax_rsi.plot(x_index, d_values, color='brown', linewidth=1, label='KDJ-D')
        
        # 绘制RSI曲线（参考ETF K线窗口的颜色设置，不使用虚线）
        if 'RSI6_1min' in rsi_df_to_plot.columns:
            rsi6_1min_values = rsi_df_to_plot['RSI6_1min'].values
            if not pd.isna(rsi6_1min_values).all():
                self.ax_rsi.plot(x_index, rsi6_1min_values, color='blue', linewidth=1, label='RSI6(1min)')
                
                # 在RSI6起始点添加红色小圆点标记
                first_valid_idx = None
                for i, val in enumerate(rsi6_1min_values):
                    if not pd.isna(val):
                        first_valid_idx = i
                        break
                
                if first_valid_idx is not None:
                    self.ax_rsi.plot(x_index[first_valid_idx], rsi6_1min_values[first_valid_idx], 
                                   'ro', markersize=4, markeredgecolor='darkred', markeredgewidth=0.5,
                                   label='RSI6起始点' if first_valid_idx == 0 else '')
        
        if 'RSI6_5min' in rsi_df_to_plot.columns:
            rsi6_5min_values = rsi_df_to_plot['RSI6_5min'].values
            if not pd.isna(rsi6_5min_values).all():
                self.ax_rsi.plot(x_index, rsi6_5min_values, color='orange', linewidth=1, label='RSI6(5min)')
                
                # 在RSI6(5min)起始点添加红色小圆点标记
                first_valid_idx = None
                for i, val in enumerate(rsi6_5min_values):
                    if not pd.isna(val):
                        first_valid_idx = i
                        break
                
                if first_valid_idx is not None:
                    self.ax_rsi.plot(x_index[first_valid_idx], rsi6_5min_values[first_valid_idx], 
                                   'ro', markersize=4, markeredgecolor='darkred', markeredgewidth=0.5,
                                   label='RSI6(5min)起始点' if first_valid_idx == 0 else '')
        

        
        # 绘制成交量柱状图在RSI面板上
        if "volume" in self.price_df.columns:
            volumes = self.price_df["volume"].values
            if len(volumes) > 0:
                # 计算成交量颜色（红涨绿跌）
                colors_vol = []
                prev_close = self._get_previous_close_for_volume_colors()
                
                for i in range(len(volumes)):
                    if i == 0:
                        # 第一根柱子：与前一交易日收盘价比较
                        if prev_close is not None:
                            current_price = self.price_df["close"].iloc[i]
                            is_red = current_price >= prev_close
                            colors_vol.append("red" if is_red else "green")
                        else:
                            # 如果无法获取前一交易日收盘价，使用开盘价和收盘价比较
                            is_red = self.price_df["close"].iloc[i] >= self.price_df["open"].iloc[i]
                            colors_vol.append("red" if is_red else "green")
                    else:
                        # 后续柱子：与前一根柱子的收盘价比较
                        current_price = self.price_df["close"].iloc[i]
                        prev_price = self.price_df["close"].iloc[i-1]
                        is_red = current_price >= prev_price
                        colors_vol.append("red" if is_red else "green")
                
                # 计算成交量最大值，用于高度调整
                max_volume = np.max(volumes) if len(volumes) > 0 else 1
                
                # 绘制成交量柱状图
                # 红柱绘制在RSI80-100区域（颠倒绘制，最小值在RSI100），绿柱绘制在RSI0-20区域
                for i, (vol, color) in enumerate(zip(volumes, colors_vol)):
                    if vol > 0:  # 只绘制有成交量的柱子
                        # 计算柱子高度（基于RSI水平线位置）
                        if color == "red":
                            # 红柱：颠倒绘制，从RSI100向下到RSI80，高度按比例调整
                            height = (vol / max_volume) * 20  # 20是RSI80-100的区间
                            bottom = 100 - height  # 底部在RSI100减去高度，实现颠倒绘制
                        else:
                            # 绿柱：从RSI0到RSI20，高度按比例调整
                            height = (vol / max_volume) * 20  # 20是RSI0-20的区间
                            bottom = 0  # 底部在RSI0
                        
                        # 绘制单个柱子
                        self.ax_rsi.bar(i, height, bottom=bottom, color=color, alpha=0.6, width=0.8)
        
        # 绘制超买超卖水平线（参考ETF K线窗口的设置）
        self.ax_rsi.axhline(y=80, color='red', linestyle='--', alpha=0.2, linewidth=0.8)
        self.ax_rsi.axhline(y=20, color='green', linestyle='--', alpha=0.2, linewidth=0.8)
        
        # 设置Y轴范围
        self.ax_rsi.set_ylim(0, 100)
        
        # 添加RSI背景色：上半部淡红色(50-100)，下半部淡绿色(0-50)
        self.ax_rsi.axhspan(50, 100, facecolor='red', alpha=0.2, zorder=0)  # 上半部淡红色
        self.ax_rsi.axhspan(0, 50, facecolor='green', alpha=0.2, zorder=0)   # 下半部淡绿色
        
        # 移除RSI标签文字
        # self.ax_rsi.set_ylabel("RSI", fontsize=8)
        self.ax_rsi.tick_params(axis='y', labelsize=8)
        self.ax_rsi.grid(True, axis='y', linestyle="--", alpha=0.3)
        
        # 在图表左上角添加RSI和KDJ数值显示（参考平均成本的价差排版）
        if 'RSI6_1min' in rsi_df_to_plot.columns and 'RSI6_5min' in rsi_df_to_plot.columns:
            # 获取最新的RSI值（使用显示用的数据）
            latest_rsi6_1min = rsi_df_to_plot['RSI6_1min'].iloc[-1] if not pd.isna(rsi_df_to_plot['RSI6_1min'].iloc[-1]) else 0
            latest_rsi6_5min = rsi_df_to_plot['RSI6_5min'].iloc[-1] if not pd.isna(rsi_df_to_plot['RSI6_5min'].iloc[-1]) else 0
            
            # 获取最新的KDJ D值
            latest_d_value = 0
            if self.kdj_df is not None and not self.kdj_df.empty and 'D' in self.kdj_df.columns:
                latest_d_value = self.kdj_df['D'].iloc[-1] if not pd.isna(self.kdj_df['D'].iloc[-1]) else 0
            
            # 计算RSI相对中性线的偏离
            rsi6_1min_diff = latest_rsi6_1min - 50
            rsi6_5min_diff = latest_rsi6_5min - 50
            
            # 根据偏离程度选择颜色
            def get_rsi_color(diff):
                if diff > 20:  # 超买
                    return "#E74C3C"  # 红色
                elif diff < -20:  # 超卖
                    return "#2ECC71"  # 绿色
                else:  # 中性
                    return "#F39C12"  # 橙色
            
            # 分别显示RSI数值，使用对应的线条颜色，水平并列排列
            # RSI6(1min) 使用蓝色
            rsi_1min_text = f"RSI: {latest_rsi6_1min:.1f}"
            self.ax_rsi.text(
                0.01,
                0.95,
                rsi_1min_text,
                transform=self.ax_rsi.transAxes,
                fontsize=9,
                color='blue',  # 与RSI6(1min)线条颜色一致
                verticalalignment="top",
                bbox=dict(facecolor="white", alpha=0.7, pad=2)
            )
            
            # RSI6(5min) 使用紫色，水平并列排列
            rsi_5min_text = f"{latest_rsi6_5min:.1f}"
            self.ax_rsi.text(
                0.20,  # 水平向右移动，与RSI6(1min)并列
                0.95,
                rsi_5min_text,
                transform=self.ax_rsi.transAxes,
                fontsize=9,
                color='orange',  # 与RSI6(5min)线条颜色一致
                verticalalignment="top",
                bbox=dict(facecolor="white", alpha=0.7, pad=2)
            )
            
            # KDJ D值 使用褐色，水平并列排列
            d_text = f"D: {latest_d_value:.1f}"
            self.ax_rsi.text(
                0.40,  # 水平向右移动，与RSI6(5min)并列
                0.95,
                d_text,
                transform=self.ax_rsi.transAxes,
                fontsize=9,
                color='brown',  # 与KDJ-D线条颜色一致
                verticalalignment="top",
                bbox=dict(facecolor="white", alpha=0.7, pad=2)
            )
        
        # 确保X轴范围与主图一致（使用固定时间范围）
        self._set_axis_xlim(self.ax_rsi, x_times)
        
        # 绘制分割线（如果存在上一个交易日数据）
        if split_index is not None and split_index > 0:
            self.ax_rsi.axvline(x=split_index, color="black", linestyle="-", linewidth=1, alpha=0.7)



    def _get_cost_series(self, target_times):
        """返回与 target_times 对齐的平均成本序列，缺失值处理"""
        if self.cost_df is None or self.cost_df.empty:
            series = pd.Series(index=target_times, data=np.nan)
        else:
            df = self.cost_df.copy()
            df.set_index("time", inplace=True)
            series = df["cost"].reindex(target_times)



        return series

    # ---------  获取平均成本辅助 ----------


    def _get_previous_trade_cost(self) -> Optional[float]:
        """获取上一交易日收盘时平均成本"""
        try:
            # 获取上一交易日日期
            prev_date = self._get_latest_trade_date()  # 最近交易日(<= today)
            if prev_date >= self.trade_date:
                # 若 trade_date 就是最近交易日，则向前再找一天
                prev_date = self.trade_date - timedelta(days=1)
            # 向前回溯直到找到一个非周末日期
            while prev_date.weekday() >= 5:
                prev_date -= timedelta(days=1)

            cyq_df = ak.stock_cyq_em(symbol=self.code, adjust="qfq")
            if cyq_df.empty:
                return None
            cyq_df["日期"] = pd.to_datetime(cyq_df["日期"])
            row = cyq_df[cyq_df["日期"] == pd.Timestamp(prev_date)]
            if not row.empty:
                return float(row.iloc[-1]["平均成本"])
        except Exception:
            pass
        return None





    def _set_axis_xlim(self, ax, x_times):
        """设置轴的x轴范围，固定显示完整交易时间段 09:30-11:30, 13:00-15:00"""
        if ax is None:
            return
            
        # 固定时间范围：上午 09:30-11:30，下午 13:00-15:00
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        def _is_in_display_range(ts: datetime) -> bool:
            """判断时间是否在显示范围内（上午或下午交易时段）"""
            ts_time = ts.time()
            # 判断是否在上午时段 09:30-11:30 或下午时段 13:00-15:00
            in_morning = morning_start <= ts_time <= morning_end
            in_afternoon = afternoon_start <= ts_time <= afternoon_end
            return in_morning or in_afternoon

        # 计算显示范围对应的x轴范围
        display_start_idx = None
        display_end_idx = None
        
        for i, ts in enumerate(x_times):
            if _is_in_display_range(ts):
                if display_start_idx is None:
                    display_start_idx = i
                display_end_idx = i
        
        # 如果找不到显示范围的数据，使用默认范围
        if display_start_idx is None:
            display_start_idx = 0
        if display_end_idx is None:
            display_end_idx = len(x_times) - 1
            
        ax.set_xlim(display_start_idx, display_end_idx)

    def _draw_time_grid(self, x_index, x_times):
        """绘制时间轴刻度(每30分钟)，固定显示完整交易时间段 09:30-11:30, 13:00-15:00"""
        tick_positions: list[int] = []
        tick_labels: list[str] = []
        
        # 固定时间范围：上午 09:30-11:30，下午 13:00-15:00
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        def _is_in_display_range(ts: datetime) -> bool:
            """判断时间是否在显示范围内（上午或下午交易时段）"""
            ts_time = ts.time()
            # 判断是否在上午时段 09:30-11:30 或下午时段 13:00-15:00
            in_morning = morning_start <= ts_time <= morning_end
            in_afternoon = afternoon_start <= ts_time <= afternoon_end
            return in_morning or in_afternoon

        def _is_tick_time(ts: datetime) -> bool:
            """判断是否为刻度时间（每30分钟）"""
            return ts.minute % 30 == 0 and ts.second == 0

        # 生成刻度位置和标签
        for i, ts in enumerate(x_times):
            if not _is_in_display_range(ts):
                continue
            if _is_tick_time(ts):
                tick_positions.append(i)
                tick_labels.append(f"{ts.hour}:{ts.minute:02d}")

        # 计算显示范围对应的x轴范围
        display_start_idx = None
        display_end_idx = None
        
        for i, ts in enumerate(x_times):
            if _is_in_display_range(ts):
                if display_start_idx is None:
                    display_start_idx = i
                display_end_idx = i
        
        # 如果找不到显示范围的数据，使用默认范围
        if display_start_idx is None:
            display_start_idx = 0
        if display_end_idx is None:
            display_end_idx = len(x_times) - 1
            
        print(f"[DEBUG] 显示范围索引: {display_start_idx} - {display_end_idx}")

        # 设置X轴范围
        for ax in (self.ax_price, self.ax_cost, self.ax_rsi):
            if ax is None:
                continue
            ax.set_xlim(display_start_idx, display_end_idx)
            ax.set_xticks(tick_positions)
            # 只在最底部的RSI子图显示时间标签
            if ax is self.ax_rsi:
                ax.set_xticklabels(tick_labels, rotation=0, fontsize=8)
                ax.tick_params(axis='x', labelbottom=True)
            else:
                ax.set_xticklabels([])
                ax.tick_params(axis='x', labelbottom=False)
                # 强制隐藏可能残留的刻度标签
                for lbl in ax.get_xticklabels():
                    lbl.set_visible(False)

        # -------- 强调10:30垂直线 (仅成本图; 不在价格/成交量子图绘制垂直线) --------
        try:
            for i, ts in enumerate(x_times):
                if ts.hour == 10 and ts.minute == 15:
                    self.ax_cost.axvline(i, color="black", linewidth=1, alpha=0.7, zorder=2)
                    break
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI Callbacks
    # ------------------------------------------------------------------
    # 交易日导航
    # ------------------------------------------------------------------
    def _load_trade_calendar(self):
        """加载交易日历返回set[date]"""
        try:
            cal_df = ak.tool_trade_date_hist_sina()
            cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date']).dt.date
            if 'is_trading_day' in cal_df.columns:
                cal_df = cal_df[cal_df['is_trading_day'] == 1]
            return set(cal_df['trade_date'])
        except Exception:
            return set()

    def _get_adjacent_trade_date(self, current: date, step: int) -> Optional[date]:
        """step= -1 previous, 1 next; 返回相邻交易日"""
        cal = self._trade_calendar
        if not cal:
            return None
        d = current
        while True:
            d = d + timedelta(days=step)
            if d in cal:
                return d
            # 边界：超出当前日历范围
            if (step == -1 and d < min(cal)) or (step == 1 and d > max(cal)):
                return None

    def _on_prev_day(self):
        new_date = self._get_adjacent_trade_date(self.trade_date, -1)
        if new_date:
            self.trade_date = new_date
            self.trade_date_str = self.trade_date.strftime("%Y-%m-%d")
            
            # 更新日期标签
            if hasattr(self, 'date_label') and self.date_label:
                self.date_label.config(text=self.trade_date_str)
            
            # 通知日K线图更新垂直贯穿线位置
            if self.on_date_change_callback:
                try:
                    self.on_date_change_callback(self.trade_date_str)
                except Exception as e:
                    print(f"调用日期变化回调函数失败: {e}")
            
            # 重建缓存路径并加载
            self.cost_cache_file = os.path.join(
                self.cache_dir,
                f"intraday_cost_{self.code}_{self.trade_date_str}.csv",
            )
            self._load_cached_cost()
            # 清空均线价格缓存，强制重新获取
            self.ma5_price = None
            self.ma10_price = None
            self.ma20_price = None
            # 清空RSI数据缓存
            self.rsi_df = None
            self.kdj_df = None
            # 清空移动平均线数据缓存
            self.ma_short_values = None
            self.ma_mid_values = None
            self.ma_base_values = None
            # 清空分时买入信号数据缓存
            self.buy_signals = []
            # 清空分时卖出信号数据缓存
            self.sell_signals = []
            # 清除延迟检查状态
            self.buy_signal_pending = None
            self.sell_signal_pending = None
            self.buy_signal_last_check = None
            self.sell_signal_last_check = None
            # 清空分时信号管理器的待确认信号并重置所有信号状态
            self.signal_manager.clear_pending_signals()
            self.signal_manager.reset_all_signal_states()
            
            # 新增：清空支撑位和压力位数据，强制重新计算
            self.support_level = None
            self.resistance_level = None
            self.support_type = None
            self.resistance_type = None
            self.position_status = None
            self._support_resistance_calculated = False  # 重置计算标记
            
            # 新增：清空前高价格数据，强制重新计算
            self.previous_high_price = None
            self.previous_high_dual_prices = None
            self._previous_high_calculated = False
            
            # 新增：清空前低价格数据，强制重新计算
            self.previous_low_price = None
            self.previous_low_dual_prices = None
            self._previous_low_calculated = False
            
            # 新增：清空看涨线和看跌线数据，强制重新计算
            self.bullish_line_price = None
            self._bullish_line_calculated = False
            self.bearish_line_price = None
            self._bearish_line_calculated = False
            
            # 清空前一交易日收盘价缓存
            self._cached_previous_close = None
            self._cached_previous_close_date = None
            
            self._update_nav_buttons()
            self._update_data()

    def _on_next_day(self):
        new_date = self._get_adjacent_trade_date(self.trade_date, 1)
        if new_date:
            self.trade_date = new_date
            self.trade_date_str = self.trade_date.strftime("%Y-%m-%d")
            
            # 更新日期标签
            if hasattr(self, 'date_label') and self.date_label:
                self.date_label.config(text=self.trade_date_str)
            
            # 通知日K线图更新垂直贯穿线位置
            if self.on_date_change_callback:
                try:
                    self.on_date_change_callback(self.trade_date_str)
                except Exception as e:
                    print(f"调用日期变化回调函数失败: {e}")
            
            self.cost_cache_file = os.path.join(
                self.cache_dir,
                f"intraday_cost_{self.code}_{self.trade_date_str}.csv",
            )
            self._load_cached_cost()
            # 清空均线价格缓存，强制重新获取
            self.ma5_price = None
            self.ma10_price = None
            self.ma20_price = None
            # 清空RSI数据缓存
            self.rsi_df = None
            self.kdj_df = None
            # 清空移动平均线数据缓存
            self.ma_short_values = None
            self.ma_mid_values = None
            self.ma_base_values = None
            # 清空分时买入信号数据缓存
            self.buy_signals = []
            # 清空分时卖出信号数据缓存
            self.sell_signals = []
            # 清除延迟检查状态
            self.buy_signal_pending = None
            self.sell_signal_pending = None
            self.buy_signal_last_check = None
            self.sell_signal_last_check = None
            
            # 新增：清空支撑位和压力位数据，强制重新计算
            self.support_level = None
            self.resistance_level = None
            self.support_type = None
            self.resistance_type = None
            self.position_status = None
            self._support_resistance_calculated = False  # 重置计算标记
            
            # 新增：清空前高和前低价格数据，强制重新计算
            self.previous_high_price = None
            self.previous_high_dual_prices = None
            self._previous_high_calculated = False
            self.previous_low_price = None
            self.previous_low_dual_prices = None
            self._previous_low_calculated = False
            
            # 新增：清空看涨线和看跌线数据，强制重新计算
            self.bullish_line_price = None
            self._bullish_line_calculated = False
            self.bearish_line_price = None
            self._bearish_line_calculated = False
            
            # 清空前一交易日收盘价缓存
            self._cached_previous_close = None
            self._cached_previous_close_date = None
            
            self._update_nav_buttons()
            self._update_data()

    def _update_nav_buttons(self):
        # 检查按钮是否存在
        if self.prev_btn is None or self.next_btn is None:
            return
            
        latest = self._get_latest_trade_date()
        # 前一天是否存在
        self.prev_btn.config(state=tk.NORMAL if self._get_adjacent_trade_date(self.trade_date, -1) else tk.DISABLED)
        # 后一天存在且不超过最新
        if self.trade_date >= latest:
            self.next_btn.config(state=tk.DISABLED)
        else:
            has_next = self._get_adjacent_trade_date(self.trade_date, 1) is not None
            self.next_btn.config(state=tk.NORMAL if has_next else tk.DISABLED)

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def focus(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            self.window.focus_force()

    def _get_latest_trade_date(self) -> date:
        """自动探测最近一个交易日"""
        try:
            cal_df = ak.tool_trade_date_hist_sina()
            cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date'])
            # 过滤至今天之前(含今天)
            cal_df = cal_df[cal_df['trade_date'] <= pd.Timestamp(date.today())]
            # 若有交易日标记列, 仅保留交易日
            if 'is_trading_day' in cal_df.columns:
                cal_df = cal_df[cal_df['is_trading_day'] == 1]
            latest = cal_df['trade_date'].max()
            if pd.isna(latest):
                raise ValueError("未找到交易日历数据")
            return latest.date()
        except Exception as _:
            # 回退: 若周末则取最近周五
            today = date.today()
            weekday = today.weekday()  # 0=Mon
            if weekday >= 5:  # Sat/Sun
                return today - timedelta(days=weekday - 4)
            return today

    def _calculate_previous_high_low_prices(self):
        """计算前高前低价格（带缓存机制）"""
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 尝试从缓存获取前高价格
            cached_previous_high = self._get_cached_data('previous_high')
            if cached_previous_high is not None:
                print(f"[DEBUG] 从缓存获取前高价格: {cached_previous_high}")
                self.previous_high_price = cached_previous_high.get('price')
                self.previous_high_dual_prices = cached_previous_high.get('dual_prices')
                self._previous_high_calculated = True
                return
            
            # 计算前高价格（双价格）
            if not hasattr(self, '_previous_high_calculated') or not self._previous_high_calculated:
                try:
                    from trading_utils import get_previous_high_dual_prices
                    
                    print(f"[DEBUG] 分时窗口 - 开始计算前高双价格: {self.code}")
                    
                    # 计算前高双价格（历史数据）
                    security_type, symbol = self._get_security_type(self.code)
                    
                    dual_prices = get_previous_high_dual_prices(
                        symbol=symbol,
                        current_date=self.trade_date_str,
                        months_back=12,  # 改为1年（12个月）
                        security_type=security_type
                    )
                    
                    if "error" not in dual_prices:
                        self.previous_high_dual_prices = dual_prices
                        self.previous_high_price = dual_prices['shadow_high_price']  # 保持兼容性
                        
                        print(f"[DEBUG] 分时窗口 - 前高双价格:")
                        print(f"[DEBUG]   当前价格: {dual_prices['current_price']:.3f}")
                        print(f"[DEBUG]   上影线最高价: {dual_prices['shadow_high_price']:.3f}")
                        print(f"[DEBUG]   实体最高价: {dual_prices['entity_high_price']:.3f}")
                        
                        if dual_prices['resistance_band']:
                            band = dual_prices['resistance_band']
                            print(f"[DEBUG]   阻力带: {band['lower']:.3f} - {band['upper']:.3f}")
                            print(f"[DEBUG]   阻力带日期: {band['date']}")
                    else:
                        print(f"[DEBUG] 分时窗口 - 前高双价格计算失败: {dual_prices['error']}")
                        self.previous_high_dual_prices = None
                        self.previous_high_price = None
                    
                    # 缓存前高价格结果
                    if self.previous_high_price is not None:
                        high_cache_data = {
                            'price': self.previous_high_price,
                            'dual_prices': self.previous_high_dual_prices
                        }
                        self._set_cached_data('previous_high', high_cache_data)
                        print(f"[DEBUG] 前高价格已缓存: {high_cache_data}")
                    
                    self._previous_high_calculated = True
                    
                except Exception as e:
                    print(f"[DEBUG] 分时窗口 - 计算前高双价格失败: {e}")
                    self.previous_high_dual_prices = None
                    self.previous_high_price = None
                    self._previous_high_calculated = True

            # 尝试从缓存获取前低价格
            cached_previous_low = self._get_cached_data('previous_low')
            if cached_previous_low is not None:
                print(f"[DEBUG] 从缓存获取前低价格: {cached_previous_low}")
                self.previous_low_price = cached_previous_low.get('price')
                self.previous_low_dual_prices = cached_previous_low.get('dual_prices')
                self._previous_low_calculated = True
                return
            
            # 计算前低价格（双价格）
            if not hasattr(self, '_previous_low_calculated') or not self._previous_low_calculated:
                try:
                    from trading_utils import get_previous_low_dual_prices
                    
                    print(f"[DEBUG] 分时窗口 - 开始计算前低双价格: {self.code}")
                    
                    # 计算前低双价格
                    security_type, symbol = self._get_security_type(self.code)
                    
                    dual_prices = get_previous_low_dual_prices(
                        symbol=symbol,
                        current_date=self.trade_date_str,
                        months_back=12,  # 1年（12个月）
                        security_type=security_type
                    )
                    
                    if "error" not in dual_prices:
                        # 获取上个交易日收盘价进行验证
                        prev_close = self._get_previous_close()
                        
                        # 验证前低不能高于上个交易日收盘价
                        entity_low_price = dual_prices['entity_low_price']
                        shadow_low_price = dual_prices['shadow_low_price']
                        
                        if prev_close is not None:
                            if entity_low_price > prev_close:
                                print(f"[WARNING] 前低实体最低价({entity_low_price:.3f})高于上个交易日收盘价({prev_close:.3f})，跳过前低计算")
                                self.previous_low_dual_prices = None
                                self.previous_low_price = None
                            elif shadow_low_price > prev_close:
                                print(f"[WARNING] 前低下影线最低价({shadow_low_price:.3f})高于上个交易日收盘价({prev_close:.3f})，跳过前低计算")
                                self.previous_low_dual_prices = None
                                self.previous_low_price = None
                            else:
                                # 前低验证通过，保存数据
                                self.previous_low_dual_prices = dual_prices
                                self.previous_low_price = dual_prices['shadow_low_price']  # 保持兼容性
                                
                                print(f"[DEBUG] 分时窗口 - 前低双价格验证通过:")
                                print(f"[DEBUG]   上个交易日收盘价: {prev_close:.3f}")
                                print(f"[DEBUG]   当前价格: {dual_prices['current_price']:.3f}")
                                print(f"[DEBUG]   下影线最低价: {dual_prices['shadow_low_price']:.3f}")
                                print(f"[DEBUG]   实体最低价: {dual_prices['entity_low_price']:.3f}")
                        else:
                            print(f"[WARNING] 无法获取上个交易日收盘价，跳过前低验证")
                            # 无法验证时，仍然保存数据但给出警告
                            self.previous_low_dual_prices = dual_prices
                            self.previous_low_price = dual_prices['shadow_low_price']
                    else:
                        print(f"[DEBUG] 分时窗口 - 前低双价格计算失败: {dual_prices['error']}")
                        self.previous_low_dual_prices = None
                        self.previous_low_price = None
                    
                    # 缓存前低价格结果
                    if self.previous_low_price is not None:
                        low_cache_data = {
                            'price': self.previous_low_price,
                            'dual_prices': self.previous_low_dual_prices
                        }
                        self._set_cached_data('previous_low', low_cache_data)
                        print(f"[DEBUG] 前低价格已缓存: {low_cache_data}")
                    
                    self._previous_low_calculated = True
                    
                except Exception as e:
                    print(f"[DEBUG] 分时窗口 - 计算前低双价格失败: {e}")
                    self.previous_low_dual_prices = None
                    self.previous_low_price = None
                    self._previous_low_calculated = True
                    
        except Exception as e:
            print(f"[DEBUG] 计算前高前低价格失败: {e}")

    def _calculate_bullish_line(self):
        """计算看涨线（上个交易日布林带最高点）（带缓存机制）"""
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 尝试从缓存获取
            cached_bullish_line = self._get_cached_data('bullish_line')
            if cached_bullish_line is not None:
                print(f"[DEBUG] 从缓存获取看涨线价格: {cached_bullish_line}")
                self.bullish_line_price = cached_bullish_line
                self._bullish_line_calculated = True
                return
            
            if self._bullish_line_calculated:
                return
            
            print("[DEBUG] 开始计算看涨线")
            
            # 使用交易日期而不是依赖分时数据
            current_date = self.trade_date
            
            # 计算前一个交易日
            from datetime import timedelta
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:  # 跳过周末
                prev_date -= timedelta(days=1)
            
            prev_date_str = prev_date.strftime('%Y-%m-%d')
            
            # 获取证券类型和代码
            security_type, symbol = self._get_security_type(self.code)
            
            # 获取前一个交易日的分时数据计算布林带最高点
            start_dt = f"{prev_date_str} 09:30:00"
            end_dt = f"{prev_date_str} 15:00:00"
            
            import akshare as ak
            if security_type == "STOCK":
                prev_intraday_df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            elif security_type == "ETF":
                prev_intraday_df = ak.fund_etf_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            else:
                return
            
            if prev_intraday_df.empty:
                print(f"[DEBUG] 未获取到前一个交易日 {prev_date_str} 的分时数据")
                self._bullish_line_calculated = True
                return
            
            # 统一列名
            if '时间' in prev_intraday_df.columns:
                prev_intraday_df.rename(columns={
                    "时间": "datetime", 
                    "开盘": "open", 
                    "收盘": "close", 
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume"
                }, inplace=True)
                prev_intraday_df["datetime"] = pd.to_datetime(prev_intraday_df["datetime"])
                prev_intraday_df.set_index("datetime", inplace=True)
            
            # 计算1分钟布林带
            window = 20
            ma20 = prev_intraday_df['close'].rolling(window=window, min_periods=1).mean()
            std = prev_intraday_df['close'].rolling(window=window, min_periods=1).std()
            upper_band = ma20 + 2 * std
            
            # 使用peak检测找到最近一个高点
            bollinger_high = self._find_recent_peak(upper_band, peak_type="high")
            
            self.bullish_line_price = bollinger_high
            self._bullish_line_calculated = True
            
            print(f"[DEBUG] 看涨线计算完成: 前一个交易日 {prev_date_str} 布林带最近高点: {bollinger_high:.3f}")
            
            # 缓存看涨线结果
            self._set_cached_data('bullish_line', self.bullish_line_price)
            print(f"[DEBUG] 看涨线价格已缓存: {self.bullish_line_price}")
            
        except Exception as e:
            print(f"[ERROR] 计算看涨线失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _calculate_bearish_line(self):
        """计算看跌线（上个交易日布林带最低点）（带缓存机制）"""
        try:
            # 检查缓存键是否变化
            self._check_cache_key_change()
            
            # 尝试从缓存获取
            cached_bearish_line = self._get_cached_data('bearish_line')
            if cached_bearish_line is not None:
                print(f"[DEBUG] 从缓存获取看跌线价格: {cached_bearish_line}")
                self.bearish_line_price = cached_bearish_line
                self._bearish_line_calculated = True
                return
            
            if self._bearish_line_calculated:
                return
            
            print("[DEBUG] 开始计算看跌线")
            
            # 使用交易日期而不是依赖分时数据
            current_date = self.trade_date
            
            # 计算前一个交易日
            from datetime import timedelta
            prev_date = current_date - timedelta(days=1)
            while prev_date.weekday() >= 5:  # 跳过周末
                prev_date -= timedelta(days=1)
            
            prev_date_str = prev_date.strftime('%Y-%m-%d')
            
            # 获取证券类型和代码
            security_type, symbol = self._get_security_type(self.code)
            
            # 获取前一个交易日的分时数据计算布林带最低点
            start_dt = f"{prev_date_str} 09:30:00"
            end_dt = f"{prev_date_str} 15:00:00"
            
            import akshare as ak
            if security_type == "STOCK":
                prev_intraday_df = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            elif security_type == "ETF":
                prev_intraday_df = ak.fund_etf_hist_min_em(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    period="1",
                    adjust=""
                )
            else:
                return
            
            if prev_intraday_df.empty:
                print(f"[DEBUG] 未获取到前一个交易日 {prev_date_str} 的分时数据")
                self._bearish_line_calculated = True
                return
            
            # 统一列名
            if '时间' in prev_intraday_df.columns:
                prev_intraday_df.rename(columns={
                    "时间": "datetime", 
                    "开盘": "open", 
                    "收盘": "close", 
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume"
                }, inplace=True)
                prev_intraday_df["datetime"] = pd.to_datetime(prev_intraday_df["datetime"])
                prev_intraday_df.set_index("datetime", inplace=True)
            
            # 计算1分钟布林带
            window = 20
            ma20 = prev_intraday_df['close'].rolling(window=window, min_periods=1).mean()
            std = prev_intraday_df['close'].rolling(window=window, min_periods=1).std()
            lower_band = ma20 - 2 * std
            
            # 使用peak检测找到最近一个低点
            bollinger_low = self._find_recent_peak(lower_band, peak_type="low")
            
            self.bearish_line_price = bollinger_low
            self._bearish_line_calculated = True
            
            print(f"[DEBUG] 看跌线计算完成: 前一个交易日 {prev_date_str} 布林带最近低点: {bollinger_low:.3f}")
            
            # 缓存看跌线结果
            self._set_cached_data('bearish_line', self.bearish_line_price)
            print(f"[DEBUG] 看跌线价格已缓存: {self.bearish_line_price}")
            
        except Exception as e:
            print(f"[ERROR] 计算看跌线失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _calculate_breakthrough_breakdown_count(self):
        """计算5分钟K线突破和跌破布林带的次数"""
        # 移除检查，允许实时更新时重新计算
            
        # 清空布林带信号列表，避免重复播放
        self.bollinger_breakthrough_signals.clear()
        self.bollinger_breakdown_signals.clear()
        
        # 检查是否为初始化阶段，避免在窗口加载时播放音效
        # 但是仍然需要计算突破跌破次数用于显示
        is_initialization = not hasattr(self, '_initialization_complete') or not self._initialization_complete
        if is_initialization:
            if not hasattr(self, '_initialization_complete'):
                self._initialization_complete = False
            print("[DEBUG] 初始化阶段，跳过布林带音效播放，但继续计算突破跌破次数")
            
        try:
            if self.price_df is None or self.price_df.empty:
                print("[DEBUG] 价格数据为空，无法计算突破跌破次数")
                return
                
            if (self.bollinger_5min_upper is None or self.bollinger_5min_lower is None or 
                self.bollinger_5min_upper.empty or self.bollinger_5min_lower.empty):
                print("[DEBUG] 布林带数据为空，无法计算突破跌破次数")
                return
            
            # 使用trading_utils中的通用突破跌破检测函数
            from trading_utils import detect_bollinger_breakthrough_breakdown
            
            result = detect_bollinger_breakthrough_breakdown(
                price_data=self.price_df,
                bollinger_upper=self.bollinger_5min_upper,
                bollinger_lower=self.bollinger_5min_lower,
                resample_freq='5T',
                offset='1min'
            )
            
            # 更新计数器
            self.breakthrough_count = result['breakthrough_count']
            self.breakdown_count = result['breakdown_count']
            
            # 处理音效播放（仅限实时数据且非初始化阶段）
            for signal in result['breakthrough_signals']:
                self.bollinger_breakthrough_signals.append(signal)
                
                # 立刻播放突破音效和震动
                if (self.audio_enabled and not is_initialization and 
                    self._is_bollinger_signal_realtime(signal['timestamp'])):
                    try:
                        # 在单独线程中同时执行震动和音效，确保同步
                        def play_breakthrough_audio_and_shake():
                            try:
                                # 立即震动主K线图窗口
                                if hasattr(self, 'parent') and self.parent:
                                    main_window = self.parent.winfo_toplevel()
                                    if hasattr(main_window, 'winfo_exists') and main_window.winfo_exists():
                                        WindowManager.shake_window(main_window, duration=0.5, intensity=8)
                                        print(f"🔔 {self.name}({self.code}) 布林带突破震动提醒")
                                
                                # 播放音效
                                from audio_notifier import \
                                    notify_bollinger_breakthrough
                                notify_bollinger_breakthrough()
                                print(f"🔊 立刻播放布林带突破音效: {self.name}({self.code})")
                            except Exception as e:
                                print(f"播放布林带突破音效失败: {e}")
                        
                        # 启动震动和音效线程
                        import threading
                        threading.Thread(target=play_breakthrough_audio_and_shake, daemon=True).start()
                    except Exception as e:
                        print(f"启动布林带突破音效线程失败: {e}")
                elif self.audio_enabled and not is_initialization:
                    print(f"🔇 布林带突破信号非实时，跳过音效播放: {self.name}({self.code})")
                elif is_initialization:
                    print(f"🔇 初始化阶段，跳过布林带突破音效播放: {self.name}({self.code})")
            
            for signal in result['breakdown_signals']:
                self.bollinger_breakdown_signals.append(signal)
                
                # 立刻播放跌破音效和震动
                if (self.audio_enabled and not is_initialization and 
                    self._is_bollinger_signal_realtime(signal['timestamp'])):
                    try:
                        # 在单独线程中同时执行震动和音效，确保同步
                        def play_breakdown_audio_and_shake():
                            try:
                                # 立即震动主K线图窗口
                                if hasattr(self, 'parent') and self.parent:
                                    main_window = self.parent.winfo_toplevel()
                                    if hasattr(main_window, 'winfo_exists') and main_window.winfo_exists():
                                        WindowManager.shake_window(main_window, duration=0.5, intensity=8)
                                        print(f"🔔 {self.name}({self.code}) 布林带跌破震动提醒")
                                
                                # 播放音效
                                from audio_notifier import \
                                    notify_bollinger_breakdown
                                notify_bollinger_breakdown()
                                print(f"🔊 立刻播放布林带跌破音效: {self.name}({self.code})")
                            except Exception as e:
                                print(f"播放布林带跌破音效失败: {e}")
                        
                        # 启动震动和音效线程
                        import threading
                        threading.Thread(target=play_breakdown_audio_and_shake, daemon=True).start()
                    except Exception as e:
                        print(f"启动布林带跌破音效线程失败: {e}")
                elif self.audio_enabled and not is_initialization:
                    print(f"🔇 布林带跌破信号非实时，跳过音效播放: {self.name}({self.code})")
                elif is_initialization:
                    print(f"🔇 初始化阶段，跳过布林带跌破音效播放: {self.name}({self.code})")
            
            print(f"[DEBUG] 突破跌破次数计算完成: 突破={self.breakthrough_count}次, 跌破={self.breakdown_count}次")
            
        except Exception as e:
            print(f"[ERROR] 计算突破跌破次数失败: {e}")
            self.breakthrough_count = 0
            self.breakdown_count = 0
            
        self._breakthrough_breakdown_calculated = True

    def _plot_breakthrough_breakdown_count(self):
        """在价格图表上显示突破和跌破次数"""
        try:
            if not self._breakthrough_breakdown_calculated:
                print("[DEBUG] 突破跌破次数未计算，跳过显示")
                return
                
            # 获取价格图的范围
            y_min, y_max = self.ax_price.get_ylim()
            x_min, x_max = self.ax_price.get_xlim()
            
            # 计算显示位置
            chart_center_x = (x_min + x_max) / 2  # 图表中央X坐标
            chart_top_y = y_max - (y_max - y_min) * 0.05  # 图表顶部，留5%边距
            chart_bottom_y = y_min + (y_max - y_min) * 0.05  # 图表底部，留5%边距
            
            # 获取当前字体大小（与其他图表保持一致）
            current_fontsize = 8  # 默认字体大小，与其他图表保持一致
            
            # 绘制突破次数（顶部中央，红色粗体）- 始终显示
            breakthrough_text = f"破上轨: {self.breakthrough_count}次\n看涨，开口朝上追，否则等中轨"
            self.ax_price.text(
                chart_center_x, 
                chart_top_y, 
                breakthrough_text,
                ha='center', 
                va='top',
                fontsize=current_fontsize,
                color='red',
                weight='bold',
                bbox=dict(
                    facecolor='white', 
                    alpha=0.8, 
                    edgecolor='red',
                    linewidth=1,
                    pad=2
                )
            )
            print(f"[DEBUG] 显示突破次数: {self.breakthrough_count}次")
            
            # 绘制跌破次数（底部中央，绿色粗体）- 始终显示
            breakdown_text = f"破下轨: {self.breakdown_count}次\n看跌，开口朝下杀，否则等中轨"
            self.ax_price.text(
                chart_center_x, 
                chart_bottom_y, 
                breakdown_text,
                ha='center', 
                va='bottom',
                fontsize=current_fontsize,
                color='green',
                weight='bold',
                bbox=dict(
                    facecolor='white', 
                    alpha=0.8, 
                    edgecolor='green',
                    linewidth=1,
                    pad=2
                )
            )
            print(f"[DEBUG] 显示跌破次数: {self.breakdown_count}次")
                
        except Exception as e:
            print(f"[ERROR] 绘制突破跌破次数显示失败: {e}")
            import traceback
            traceback.print_exc()

    def _draw_support_resistance_only(self):
        """当没有分时数据时，只显示支撑带和压力带"""
        # 检查窗口是否已销毁
        if self._is_destroyed:
            return
            
        try:
            # 清理图表
            self.ax_price.clear()
            self.ax_cost.clear()
            self.ax_rsi.clear()
            
            # 获取前一交易日收盘价作为基准
            prev_close = self._get_previous_close()
            if prev_close is None:
                print("[DEBUG] 无法获取前一交易日收盘价，无法显示支撑带和压力带")
                return
            
            # 设置价格范围（基于前一交易日收盘价的±5%）
            price_range = prev_close * 0.05
            up_price = prev_close + price_range
            down_price = prev_close - price_range
            
            # 检查支撑位和压力位是否需要扩展价格区间
            if self.support_level is not None:
                if self.support_level < down_price:
                    down_price = self.support_level * 0.995
                elif self.support_level > up_price:
                    up_price = self.support_level * 1.005
            
            if self.resistance_level is not None:
                if self.resistance_level < down_price:
                    down_price = self.resistance_level * 0.995
                elif self.resistance_level > up_price:
                    up_price = self.resistance_level * 1.005
            
            # 设置轴范围
            self.ax_price.set_ylim(down_price, up_price)
            self.ax_price.set_xlim(0, 1)  # 设置一个简单的x轴范围
            
            # 绘制基准线（前一交易日收盘价）
            self.ax_price.axhline(prev_close, color="gray", linestyle="--", linewidth=0.8, label="前收盘")
            
            # 绘制支撑位和压力位
            if self.support_level is not None and down_price <= self.support_level <= up_price:
                self.ax_price.axhline(self.support_level, color="red", linestyle="--", linewidth=1, alpha=0.8, label=f"支撑位({self.support_type})")
            
            if self.resistance_level is not None and down_price <= self.resistance_level <= up_price:
                self.ax_price.axhline(self.resistance_level, color="green", linestyle="--", linewidth=1, alpha=0.8, label=f"压力位({self.resistance_type})")
            
            # 绘制看涨线和看跌线 - 根据开盘价和上一个交易日涨跌情况确定线型
            if (self.bullish_line_price is not None and down_price <= self.bullish_line_price <= up_price) or \
               (self.bearish_line_price is not None and down_price <= self.bearish_line_price <= up_price):
                
                # 确定线型
                bullish_style, bearish_style = self._determine_line_styles()
                
                # 计算图表宽度的1/4（在盘前显示时，使用一个固定的宽度）
                chart_width = 240  # 假设4小时交易时间，每分钟一个数据点
                line_length = chart_width / 4
                
                # 绘制看涨线
                if self.bullish_line_price is not None and down_price <= self.bullish_line_price <= up_price:
                    self.ax_price.hlines(self.bullish_line_price, xmin=0, xmax=line_length, 
                                       color="red", linestyle=bullish_style, linewidth=2, alpha=0.9, label="看涨线")
                
                # 绘制看跌线
                if self.bearish_line_price is not None and down_price <= self.bearish_line_price <= up_price:
                    self.ax_price.hlines(self.bearish_line_price, xmin=0, xmax=line_length, 
                                       color="green", linestyle=bearish_style, linewidth=2, alpha=0.9, label="看跌线")
            
            # 绘制前高价格阻力带
            if hasattr(self, 'previous_high_dual_prices') and self.previous_high_dual_prices is not None:
                dual_prices = self.previous_high_dual_prices
                if dual_prices.get('resistance_band'):
                    band = dual_prices['resistance_band']
                    upper_price = band['upper']  # 上影线最高价
                    lower_price = band['lower']  # 实体最高价
                    
                    # 确保阻力带在可见范围内
                    if down_price <= upper_price <= up_price or down_price <= lower_price <= up_price:
                        # 绘制阻力带（绿色填充，添加线条图案）
                        self.ax_price.axhspan(
                            lower_price, upper_price,
                            facecolor="green", alpha=0.3, zorder=1,
                            hatch='\\',  # 斜线填充
                            edgecolor='darkgreen',  # 边框颜色
                            linewidth=0.5,  # 边框宽度
                            label=f"前高阻力带({lower_price:.2f}-{upper_price:.2f})"
                        )
                        print(f"[DEBUG] 分时窗口 - 绘制前高价格线: {self.previous_high_price:.3f}")
            
            # 绘制前低价格支撑带
            if hasattr(self, 'previous_low_dual_prices') and self.previous_low_dual_prices is not None:
                dual_prices = self.previous_low_dual_prices
                if dual_prices.get('support_band'):
                    band = dual_prices['support_band']
                    upper_price = band['upper']  # 实体最低价
                    lower_price = band['lower']  # 下影线最低价
                    
                    # 检查支撑带是否在显示范围内
                    if (down_price <= upper_price <= up_price or 
                        down_price <= lower_price <= up_price or
                        (lower_price < down_price and upper_price > up_price)):
                        
                        # 绘制支撑带（红色填充，添加线条图案）
                        self.ax_price.axhspan(
                            lower_price, upper_price,
                            facecolor="red", alpha=0.3, zorder=1,
                            hatch='/',  # 反斜线填充
                            edgecolor='darkred',  # 边框颜色
                            linewidth=0.5,  # 边框宽度
                            label=f"前低支撑带({lower_price:.2f}-{upper_price:.2f})"
                        )
                        print(f"[DEBUG] 分时窗口 - 绘制前低支撑带: {lower_price:.3f} - {upper_price:.3f}")
            
            # 设置价格刻度和标签
            price_ticks = []
            price_labels = []
            
            # 添加基准价（前一交易日收盘价）
            price_ticks.append(prev_close)
            price_labels.append(f"{prev_close:.2f}")
            
            # 添加支撑位和压力位的价格刻度
            if self.support_level is not None and down_price <= self.support_level <= up_price:
                price_ticks.append(self.support_level)
                price_labels.append(f"{self.support_level:.2f}")
            
            if self.resistance_level is not None and down_price <= self.resistance_level <= up_price:
                price_ticks.append(self.resistance_level)
                price_labels.append(f"{self.resistance_level:.2f}")
            
            # 新增：添加看涨线和看跌线的价格刻度
            if self.bullish_line_price is not None and down_price <= self.bullish_line_price <= up_price:
                price_ticks.append(self.bullish_line_price)
                price_labels.append(f"{self.bullish_line_price:.2f}")
            
            if self.bearish_line_price is not None and down_price <= self.bearish_line_price <= up_price:
                price_ticks.append(self.bearish_line_price)
                price_labels.append(f"{self.bearish_line_price:.2f}")
            
            # 设置刻度和标签
            self.ax_price.set_yticks(price_ticks)
            self.ax_price.set_yticklabels(price_labels, fontsize=8)
            
            # 设置标题和标签
            self.ax_price.set_title(f"{self.name}({self.code}) - 分时 {self.trade_date_str} - 支撑带压力带预览", fontsize=10)
            self.ax_price.set_ylabel("价格", fontsize=9)
            self.ax_price.legend(loc='upper right', fontsize=8)
            self.ax_price.grid(True, alpha=0.3)
            
            # 隐藏x轴标签（因为没有时间数据）
            self.ax_price.set_xticks([])
            
            # 绘制图表
            self.canvas.draw()
            
            print("[DEBUG] 支撑带和压力带预览图绘制完成")
            
        except Exception as e:
            print(f"[DEBUG] 绘制支撑带和压力带预览图失败: {e}")
            import traceback
            traceback.print_exc()

    def _calculate_support_resistance(self):
        """计算支撑位和压力位（带缓存机制）
        
        支撑位和压力位计算规则:
        1. 基于上一交易日收盘价相对于MA20的位置
        2. 如果上一交易日收盘价 > MA20: MA20为支撑位，布林上轨为压力位
        3. 如果上一交易日收盘价 <= MA20: MA20为压力位，布林下轨为支撑位
        4. 支撑位和压力位每天重新计算，不依赖昨天的突破/跌破价格
        """
        # 检查缓存键是否变化
        self._check_cache_key_change()
        
        # 尝试从缓存获取
        cached_sr = self._get_cached_data('support_resistance')
        if cached_sr is not None:
            print(f"[DEBUG] 从缓存获取支撑位压力位: 支撑位={cached_sr['support_level']}, 压力位={cached_sr['resistance_level']}")
            self.support_level = cached_sr['support_level']
            self.resistance_level = cached_sr['resistance_level']
            self.support_type = cached_sr['support_type']
            self.resistance_type = cached_sr['resistance_type']
            self.position_status = cached_sr['position_status']
            self._support_resistance_calculated = True
            return
        
        max_retries = 1
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            try:
                print(f"[DEBUG] 尝试计算支撑位和压力位，第{attempt + 1}次尝试")
                print(f"[DEBUG] 股票代码: {self.code}, 交易日: {self.trade_date_str}")
                
                # 使用和K线图相同的方法获取数据（包含布林带计算）
                daily_data = self.etf_engine.load_data(
                    code=self.code,
                    symbol_name=self.name,
                    period_mode='day',
                    start_date=(self.trade_date - timedelta(days=60)).strftime('%Y-%m-%d'),
                    end_date=self.trade_date.strftime('%Y-%m-%d'),
                    period_config={
                        'day': {
                            'ak_period': 'daily',
                            'buffer_ratio': '0.2',
                            'min_buffer': '20'
                        }
                    },
                    ma_lines=[5, 10, 20, 250],  # 包含MA20用于布林带计算
                    force_refresh=False
                )
                
                if daily_data.empty:
                    print(f"[DEBUG] 第{attempt + 1}次尝试：无法获取 {self.code} 的历史数据")
                    if attempt < max_retries - 1:
                        print(f"[DEBUG] 等待{retry_delay}秒后重试...")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"[DEBUG] 所有尝试都失败，无法计算支撑位和压力位")
                        return
                
                # 检查是否包含布林带数据
                if 'MA20' not in daily_data.columns or 'BOLL_UPPER' not in daily_data.columns:
                    print(f"[DEBUG] 第{attempt + 1}次尝试：历史数据中缺少布林带指标")
                    print(f"[DEBUG] 可用列: {list(daily_data.columns)}")
                    if attempt < max_retries - 1:
                        print(f"[DEBUG] 等待{retry_delay}秒后重试...")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        print(f"[DEBUG] 所有尝试都失败，无法计算支撑位和压力位")
                        return
                
                # 获取最新交易日数据
                latest_daily = daily_data.iloc[-1]
                ma20 = latest_daily['MA20']
                boll_upper = latest_daily['BOLL_UPPER']
                boll_lower = latest_daily['BOLL_LOWER']
                
                # 获取上一个交易日的收盘价作为支撑位计算的基准价格
                if len(daily_data) > 1:
                    prev_close = daily_data.iloc[-2]['收盘']
                    prev_date = daily_data.index[-2].strftime('%Y-%m-%d')
                else:
                    # 如果没有上一个交易日数据，使用当前日线收盘价
                    prev_close = latest_daily['收盘']
                    prev_date = "无前一交易日数据"
                
                # 获取当前分时价格（用于显示和调试）
                if self.price_df is not None and not self.price_df.empty:
                    current_price = self.price_df['close'].iloc[-1]
                else:
                    # 如果没有分时数据，使用日线收盘价
                    current_price = latest_daily['收盘']
                
                print(f"[DEBUG] 支撑位和压力位计算成功（第{attempt + 1}次尝试）:")
                print(f"[DEBUG]  前一交易日({prev_date})收盘价: {prev_close:.3f}")
                print(f"[DEBUG]  当前分时价格: {current_price:.3f}")
                print(f"[DEBUG]  MA20(布林中轨): {ma20:.3f}")
                print(f"[DEBUG]  布林上轨: {boll_upper:.3f}")
                print(f"[DEBUG]  布林下轨: {boll_lower:.3f}")
                
                # 计算支撑位和压力位（基于上一交易日收盘价相对于MA20的位置）
                # 这是固定的算法，不依赖昨天的突破/跌破价格
                if prev_close > ma20:
                    # 上一交易日收盘价在MA20之上：MA20为支撑位，布林上轨为压力位
                    self.support_level = ma20
                    self.resistance_level = boll_upper
                    self.position_status = "上一交易日收盘价在20日线之上"
                    self.support_type = "MA20(布林中轨)"
                    self.resistance_type = "布林上轨"
                    print(f"[DEBUG]  判断逻辑: 前一交易日收盘价({prev_close:.3f}) > MA20({ma20:.3f})")
                else:
                    # 上一交易日收盘价在MA20之下：MA20为压力位，布林下轨为支撑位
                    self.support_level = boll_lower
                    self.resistance_level = ma20
                    self.position_status = "上一交易日收盘价在20日线之下"
                    self.support_type = "布林下轨"
                    self.resistance_type = "MA20(布林中轨)"
                    print(f"[DEBUG]  判断逻辑: 前一交易日收盘价({prev_close:.3f}) <= MA20({ma20:.3f})")
                
                print(f"[DEBUG]  位置状态: {self.position_status}")
                print(f"[DEBUG]  支撑位: {self.support_level:.3f} ({self.support_type})")
                print(f"[DEBUG]  压力位: {self.resistance_level:.3f} ({self.resistance_type})")
                
                # 计算距离和涨跌幅
                if self.price_df is not None and not self.price_df.empty:
                    distance_to_support = ((current_price - self.support_level) / current_price) * 100
                    distance_to_resistance = ((self.resistance_level - current_price) / current_price) * 100
                    
                    print(f"[DEBUG]  到支撑位距离: {distance_to_support:+.2f}%")
                    print(f"[DEBUG]  到压力位距离: {distance_to_resistance:+.2f}%")
                
                # 计算相对于前一交易日收盘价的涨跌幅
                if len(daily_data) > 1:
                    prev_close = daily_data.iloc[-2]['收盘']
                    support_change = (self.support_level - prev_close) / prev_close * 100
                    resistance_change = (self.resistance_level - prev_close) / prev_close * 100
                    
                    print(f"[DEBUG]  支撑位涨跌幅: {support_change:+.2f}%")
                    print(f"[DEBUG]  压力位涨跌幅: {resistance_change:+.2f}%")
                
                # 验证支撑位和压力位的合理性
                if self.support_level is not None and self.resistance_level is not None:
                    if self.support_level <= 0 or self.resistance_level <= 0:
                        print(f"[WARNING] 支撑位或压力位计算异常: 支撑位={self.support_level}, 压力位={self.resistance_level}")
                    
                    if self.support_level >= self.resistance_level:
                        print(f"[WARNING] 支撑位({self.support_level:.3f}) >= 压力位({self.resistance_level:.3f})，可能存在计算错误")
                
                print(f"[DEBUG] 支撑位和压力位计算完成")
                
                # 缓存结果
                sr_result = {
                    'support_level': self.support_level,
                    'resistance_level': self.resistance_level,
                    'support_type': self.support_type,
                    'resistance_type': self.resistance_type,
                    'position_status': self.position_status
                }
                self._set_cached_data('support_resistance', sr_result)
                print(f"[DEBUG] 支撑位压力位已缓存: {sr_result}")
                
                self._support_resistance_calculated = True  # 标记计算完成
                return  # 成功计算，退出重试循环
                
            except Exception as e:
                print(f"[DEBUG] 第{attempt + 1}次尝试计算支撑位和压力位时出错: {e}")
                import traceback
                traceback.print_exc()
                if attempt < max_retries - 1:
                    print(f"[DEBUG] 等待{retry_delay}秒后重试...")
                    import time
                    time.sleep(retry_delay)
                else:
                    print(f"[DEBUG] 所有{max_retries}次尝试都失败，无法计算支撑位和压力位")
                    # 即使计算失败，也要确保变量不为None
                    if self.support_level is None:
                        self.support_level = 0.0
                    if self.resistance_level is None:
                        self.resistance_level = 0.0
                    if self.support_type is None:
                        self.support_type = "未知"
                    if self.resistance_type is None:
                        self.resistance_type = "未知"
                    if self.position_status is None:
                        self.position_status = "计算失败"

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------
    def _capture_to_clipboard(self):
        """截取当前分时窗口到剪贴板 (macOS)"""
        try:
            # 抬到最前
            self.window.lift()
            self.window.update()

            x = self.window.winfo_rootx()
            y = self.window.winfo_rooty()
            w = self.window.winfo_width()
            h = self.window.winfo_height()

            # 小延迟保证渲染完成
            self.window.after(100, lambda: None)

            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            if img.mode == "RGBA":
                img = img.convert("RGB")

            import os
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            img.save(tmp.name, format="JPEG", quality=95)
            tmp.close()

            os.system(f"osascript -e 'set the clipboard to (read (POSIX file \"{tmp.name}\") as JPEG picture)'")
            os.unlink(tmp.name)
            print("capture_success")
        except Exception as e:
            print(f"capture_failed: {e}")
    
    def update_stock_code(self, new_code: str, new_name: str):
        """更新股票代码和名称，重新加载数据"""
        # 清理所有缓存（股票代码变更时）
        self._clear_all_caches()
        print(f"[DEBUG] 股票代码变更，清理所有缓存: {self.code} -> {new_code}")
        
        self.code = new_code
        self.name = new_name
        
        # 重新获取最新交易日
        self.trade_date = self._get_latest_trade_date()
        self.trade_date_str = self.trade_date.strftime("%Y-%m-%d")
        
        # 更新缓存键
        self._cache_key = self._get_cache_key()
        self._last_cache_key = None
        
        # 更新日期标签
        if hasattr(self, 'date_label') and self.date_label:
            self.date_label.config(text=self.trade_date_str)
        
        # 通知日K线图更新垂直贯穿线位置
        if self.on_date_change_callback:
            try:
                self.on_date_change_callback(self.trade_date_str)
            except Exception as e:
                print(f"调用日期变化回调函数失败: {e}")
        
        # 更新成本缓存文件路径
        self.cost_cache_file = os.path.join(
            self.cache_dir,
            f"intraday_cost_{new_code}_{self.trade_date_str}.csv",
        )
        
        # 更新窗口标题（在有工具栏的情况下）
        if hasattr(self, 'show_toolbar') and self.show_toolbar and hasattr(self.window, 'title'):
            # 类型转换以避免linter错误
            if hasattr(self.window, 'title'):
                # 使用类型断言确保类型安全
                if isinstance(self.window, tk.Toplevel):
                    self.window.title(f"{new_name}({new_code}) - 分时 {self.trade_date_str}")
        
        # 清空旧数据
        self.price_df = pd.DataFrame()
        self.cost_df = None  # 清空成本数据
        self.rsi_df = None
        self.kdj_df = None
        # 清空移动平均线数据
        self.ma_short_values = None
        self.ma_mid_values = None
        self.ma_base_values = None
        # 清空分时买入信号数据
        self.buy_signals = []
        # 清空分时卖出信号数据
        self.sell_signals = []
        # 清除延迟检查状态
        self.buy_signal_pending = None
        self.sell_signal_pending = None
        self.buy_signal_last_check = None
        self.sell_signal_last_check = None
        
        # 清空分时信号管理器的待确认信号并重置所有信号状态
        self.signal_manager.clear_pending_signals()
        self.signal_manager.reset_all_signal_states()
        
        # 新增：清空前高价格数据，强制重新计算
        self.previous_high_price = None
        self.previous_high_dual_prices = None
        self._previous_high_calculated = False
        
        # 新增：清空前低价格数据，强制重新计算
        self.previous_low_price = None
        self.previous_low_dual_prices = None
        self._previous_low_calculated = False
        
        # 新增：清空支撑位和压力位数据，强制重新计算
        self.support_level = None
        self.resistance_level = None
        self.support_type = None
        self.resistance_type = None
        self.position_status = None
        self._support_resistance_calculated = False  # 重置计算标记
        
        # 清空日线均线价格缓存，强制重新获取
        self.ma5_price = None
        self.ma10_price = None
        
        # 新增：清空看涨线和看跌线数据，强制重新计算
        self.bullish_line_price = None
        self._bullish_line_calculated = False
        self.bearish_line_price = None
        self._bearish_line_calculated = False
        
        # 重置价格范围历史记录
        self._reset_price_range_history()
        
        # 清空ETF分析引擎的缓存，确保获取新股票的最新数据
        if hasattr(self.etf_engine, 'clear_cache'):
            self.etf_engine.clear_cache()
            print(f"[DEBUG] 已清空ETF分析引擎缓存，切换股票: {new_code}")
        
        # 清空ETF分析引擎的指标缓存
        if hasattr(self.etf_engine, '_indicator_cache'):
            self.etf_engine._indicator_cache.clear()
            print(f"[DEBUG] 已清空ETF分析引擎指标缓存，切换股票: {new_code}")
        
        # 清空前一交易日收盘价缓存（股票代码变化时需要重新获取）
        self._cached_previous_close = None
        self._cached_previous_close_date = None
        
        # 重新加载数据并更新图表
        threading.Thread(target=self._update_data, daemon=True).start()
    

    
    # 旧的信号检测方法已移除，现在使用IntradaySignalManager统一处理
    
    def _play_signal_audio_notifications(self):
        """播放信号音频通知（仅在实时信号时，急涨急跌信号连续3次后停止音效）"""
        try:
            # 检查price_df是否存在
            if self.price_df is None or self.price_df.empty:
                return
            
            # 检查是否有实时信号需要播放音效
            has_realtime_buy_signal = False
            has_realtime_sell_signal = False
            has_realtime_bollinger_breakthrough = False
            has_realtime_bollinger_breakdown = False
            buy_signal_type = 'other'
            sell_signal_type = 'other'
            bollinger_signal_type = 'other'
            
            # 检查买入信号
            if self.buy_signals and len(self.buy_signals) > 0:
                for signal in self.buy_signals:
                    signal_index = signal.get('index', 0)
                    if signal_index < len(self.price_df['close']):
                        signal_timestamp = self.price_df['close'].index[signal_index]
                        if isinstance(signal_timestamp, pd.Timestamp) and self._is_realtime_signal(signal_timestamp):
                            has_realtime_buy_signal = True
                            # 识别信号类型
                            signal_name = signal.get('name', '')
                            _, signal_type = self._is_surge_plunge_signal(signal_name)
                            buy_signal_type = signal_type
                            break
            
            # 检查卖出信号
            if self.sell_signals and len(self.sell_signals) > 0:
                for signal in self.sell_signals:
                    signal_index = signal.get('index', 0)
                    if signal_index < len(self.price_df['close']):
                        signal_timestamp = self.price_df['close'].index[signal_index]
                        if isinstance(signal_timestamp, pd.Timestamp) and self._is_realtime_signal(signal_timestamp):
                            has_realtime_sell_signal = True
                            # 识别信号类型
                            signal_name = signal.get('name', '')
                            _, signal_type = self._is_surge_plunge_signal(signal_name)
                            sell_signal_type = signal_type
                            break
            
            # 检查布林带突破信号
            if self.bollinger_breakthrough_signals and len(self.bollinger_breakthrough_signals) > 0:
                for signal in self.bollinger_breakthrough_signals:
                    signal_timestamp = signal.get('timestamp')
                    if isinstance(signal_timestamp, pd.Timestamp) and self._is_bollinger_signal_realtime(signal_timestamp):
                        has_realtime_bollinger_breakthrough = True
                        bollinger_signal_type = 'breakthrough'
                        break
            
            # 检查布林带跌破信号
            if self.bollinger_breakdown_signals and len(self.bollinger_breakdown_signals) > 0:
                for signal in self.bollinger_breakdown_signals:
                    signal_timestamp = signal.get('timestamp')
                    if isinstance(signal_timestamp, pd.Timestamp) and self._is_bollinger_signal_realtime(signal_timestamp):
                        has_realtime_bollinger_breakdown = True
                        bollinger_signal_type = 'breakdown'
                        break
            
            # 更新急涨急跌信号连续计数器
            if has_realtime_buy_signal:
                self._update_surge_plunge_counters(buy_signal_type)
            elif has_realtime_sell_signal:
                self._update_surge_plunge_counters(sell_signal_type)
            
            # 更新布林带信号连续计数器
            if has_realtime_bollinger_breakthrough:
                self._update_bollinger_signal_counters('breakthrough')
            elif has_realtime_bollinger_breakdown:
                self._update_bollinger_signal_counters('breakdown')
            
            # 检查是否应该播放音效
            should_play_buy_audio = has_realtime_buy_signal and self._should_play_audio(buy_signal_type)
            should_play_sell_audio = has_realtime_sell_signal and self._should_play_audio(sell_signal_type)
            should_play_bollinger_breakthrough_audio = has_realtime_bollinger_breakthrough and self._should_play_bollinger_audio('breakthrough')
            should_play_bollinger_breakdown_audio = has_realtime_bollinger_breakdown and self._should_play_bollinger_audio('breakdown')
            
            # 如果有实时信号，立即震动主K线图窗口，然后播放音效（如果音效开启）
            if has_realtime_buy_signal or has_realtime_sell_signal or has_realtime_bollinger_breakthrough or has_realtime_bollinger_breakdown:
                # 在单独线程中同时执行震动和音效，确保同步
                def play_all_signals_audio_and_shake():
                    try:
                        # 立即震动主K线图窗口（通过parent获取根窗口）
                        if hasattr(self, 'parent') and self.parent:
                            # 获取主K线图窗口（根窗口）
                            main_window = self.parent.winfo_toplevel()
                            if hasattr(main_window, 'winfo_exists') and main_window.winfo_exists():
                                # 立即开始震动
                                WindowManager.shake_window(main_window, duration=0.5, intensity=8)
                                print(f"🔔 {self.name}({self.code}) 主K线图窗口震动提醒")
                        
                        # 检查音效开关状态
                        if not self.audio_enabled:
                            print(f"🔇 音效已关闭，跳过音效播放: {self.name}({self.code})")
                            return
                        
                        # 播放买入信号音效（如果应该播放）
                        if should_play_buy_audio:
                            try:
                                from audio_notifier import notify_buy_signal
                                notify_buy_signal()
                                print(f"🔊 播放买入信号音效: {self.name}({self.code}) (连续{self.surge_signal_consecutive_count if buy_signal_type == 'surge' else 'N/A'}次)")
                            except Exception as e:
                                print(f"播放买入信号音效失败: {e}")
                        elif has_realtime_buy_signal:
                            print(f"🔇 买入信号音效已跳过: {self.name}({self.code}) (连续{self.surge_signal_consecutive_count if buy_signal_type == 'surge' else 'N/A'}次，超过限制)")
                        
                        # 播放卖出信号音效（如果应该播放）
                        if should_play_sell_audio:
                            try:
                                from audio_notifier import notify_sell_signal
                                notify_sell_signal()
                                print(f"🔊 播放卖出信号音效: {self.name}({self.code}) (连续{self.plunge_signal_consecutive_count if sell_signal_type == 'plunge' else 'N/A'}次)")
                            except Exception as e:
                                print(f"播放卖出信号音效失败: {e}")
                        elif has_realtime_sell_signal:
                            print(f"🔇 卖出信号音效已跳过: {self.name}({self.code}) (连续{self.plunge_signal_consecutive_count if sell_signal_type == 'plunge' else 'N/A'}次，超过限制)")
                        
                        # 播放布林带突破音效（如果应该播放）
                        if should_play_bollinger_breakthrough_audio:
                            try:
                                from audio_notifier import \
                                    notify_bollinger_breakthrough
                                notify_bollinger_breakthrough()
                                print(f"🔊 播放布林带突破音效: {self.name}({self.code}) (连续{self.bollinger_breakthrough_consecutive_count}次)")
                            except Exception as e:
                                print(f"播放布林带突破音效失败: {e}")
                        elif has_realtime_bollinger_breakthrough:
                            print(f"🔇 布林带突破音效已跳过: {self.name}({self.code}) (连续{self.bollinger_breakthrough_consecutive_count}次，超过限制)")
                        
                        # 播放布林带跌破音效（如果应该播放）
                        if should_play_bollinger_breakdown_audio:
                            try:
                                from audio_notifier import \
                                    notify_bollinger_breakdown
                                notify_bollinger_breakdown()
                                print(f"🔊 播放布林带跌破音效: {self.name}({self.code}) (连续{self.bollinger_breakdown_consecutive_count}次)")
                            except Exception as e:
                                print(f"播放布林带跌破音效失败: {e}")
                        elif has_realtime_bollinger_breakdown:
                            print(f"🔇 布林带跌破音效已跳过: {self.name}({self.code}) (连续{self.bollinger_breakdown_consecutive_count}次，超过限制)")
                            
                    except Exception as e:
                        print(f"播放信号音效和震动失败: {e}")
                
                # 启动震动和音效线程
                import threading
                threading.Thread(target=play_all_signals_audio_and_shake, daemon=True).start()
                        
            # 标记布林带信号已处理
            self._bollinger_signals_processed = True
            
            # 标记初始化完成，允许播放布林带音效
            self._initialization_complete = True
            
        except Exception as e:
            print(f"播放信号音频通知失败: {e}")
            # 即使出错也要标记初始化完成
            self._initialization_complete = True
    
    def _toggle_audio(self):
        """切换音效开关状态"""
        try:
            # 切换音效状态
            self.audio_enabled = not self.audio_enabled
            
            # 更新按钮显示
            if hasattr(self, 'audio_toggle_btn') and self.audio_toggle_btn:
                if self.audio_enabled:
                    self.audio_toggle_btn.config(text="🔊")
                    print(f"🔊 音效已开启: {self.name}({self.code})")
                else:
                    self.audio_toggle_btn.config(text="🔇")
                    print(f"🔇 音效已关闭: {self.name}({self.code})")
            
            # 如果切换到开启状态，播放一次音效和震动作为反馈
            if self.audio_enabled:
                # 在单独线程中同时执行震动和音效，确保同步
                def play_test_audio_and_shake():
                    try:
                        # 震动主K线图窗口（通过parent获取根窗口）
                        if hasattr(self, 'parent') and self.parent:
                            main_window = self.parent.winfo_toplevel()
                            if hasattr(main_window, 'winfo_exists') and main_window.winfo_exists():
                                # 立即开始震动
                                WindowManager.shake_window(main_window, duration=0.5, intensity=8)
                                print("🔔 音效开关测试震动提醒")
                        
                        # 播放测试音效
                        from audio_notifier import notify_buy_signal
                        notify_buy_signal()
                        print("🔊 播放音效开启反馈音效")
                    except Exception as e:
                        print(f"播放音效开启反馈音效失败: {e}")
                
                # 启动震动和音效线程
                import threading
                threading.Thread(target=play_test_audio_and_shake, daemon=True).start()
                        
        except Exception as e:
            print(f"切换音效开关失败: {e}")
    
    def _toggle_volume_display(self):
        """切换总成交量显示状态"""
        try:
            # 切换总成交量显示状态
            self.volume_display_enabled = not self.volume_display_enabled
            
            # 更新按钮显示
            if hasattr(self, 'volume_display_btn') and self.volume_display_btn:
                if self.volume_display_enabled:
                    self.volume_display_btn.config(text="||")
                    print(f"|| 总成交量显示已开启: {self.name}({self.code})")
                else:
                    self.volume_display_btn.config(text="=")
                    print(f"= 总成交量显示已关闭: {self.name}({self.code})")
            
            # 重新绘制图表
            self._draw()
            
        except Exception as e:
            print(f"切换总成交量显示失败: {e}")
    
    def _toggle_height_ratio(self):
        """切换分时窗口和日线窗口的高度比例"""
        try:
            # 切换比例模式
            if self.height_ratio_mode == "3:7":
                self.height_ratio_mode = "7:3"
                print(f"[DEBUG] 切换到7:3比例模式")
            else:
                self.height_ratio_mode = "3:7"
                print(f"[DEBUG] 切换到3:7比例模式")
            
            # 更新按钮显示
            if hasattr(self, 'ratio_btn') and self.ratio_btn:
                self.ratio_btn.config(text="▲" if self.height_ratio_mode == "7:3" else "▼")
            
            # 调用回调函数通知K线窗口调整比例
            if self.height_ratio_callback:
                self.height_ratio_callback(self.height_ratio_mode)
            else:
                print(f"[WARNING] 高度比例回调函数未设置")
                
        except Exception as e:
            print(f"[ERROR] 切换高度比例失败: {str(e)}")
    
    def set_height_ratio_callback(self, callback):
        """设置高度比例变化回调函数
        :param callback: 回调函数，接收比例模式参数
        """
        self.height_ratio_callback = callback
    
    def _get_5min_center_position(self, x_index: np.ndarray, x_times: pd.Index, index: int) -> float:
        """获取5分钟K线的中心位置（与绘制逻辑保持一致）
        
        :param x_index: X轴索引数组
        :param x_times: 时间索引
        :param index: 当前1分钟数据索引
        :return: 5分钟K线的中心X位置
        """
        try:
            if self.price_df is None or self.price_df.empty:
                return float(x_index[index])
            
            # 将1分钟数据重采样为5分钟K线数据
            price_5min = self.price_df.resample('5T', offset='1T').agg({
                'open': 'first',
                'close': 'last', 
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            if price_5min.empty:
                return float(x_index[index])
            
            # 获取当前1分钟时间点对应的5分钟K线
            current_time = x_times[index]
            
            # 找到包含当前时间的5分钟K线
            for ts, row in price_5min.iterrows():
                # 检查当前时间是否在这个5分钟区间内
                if current_time >= ts and current_time < ts + pd.Timedelta(minutes=5):
                    # 使用与绘制逻辑相同的方法计算5分钟K线位置
                    # 找到最接近5分钟K线开始时间的1分钟时间点
                    time_diff = np.abs((x_times - ts).total_seconds())
                    closest_idx = np.argmin(time_diff)
                    
                    # 计算5分钟K线的中心位置
                    # 5分钟K线宽度为5个单位，中心位置 = 起始位置 + 宽度/2
                    width = 5.0  # 与绘制逻辑保持一致
                    center_x = x_index[closest_idx] + width / 2
                    
                    return float(center_x)
            
            # 如果没有找到对应的5分钟K线，返回原始位置
            return float(x_index[index])
            
        except Exception as e:
            print(f"[ERROR] 计算5分钟中心位置失败: {e}")
            return float(x_index[index])
    
    def _plot_buy_signals(self, x_index: np.ndarray, prices: np.ndarray):
        """绘制分时买入信号竖线和净涨幅标签
        
        :param x_index: X轴索引数组
        :param prices: 价格数组
        """
        if self.buy_signals is None or len(self.buy_signals) == 0:
            print("[DEBUG] 没有买入信号需要绘制")
            return
        
        print(f"[DEBUG] 开始绘制买入信号，信号数量: {len(self.buy_signals)}")
        
        # 检查连涨信号
        consecutive_signals = [sig for sig in self.buy_signals if '连涨' in sig.get('signal_type', '')]
        print(f"[DEBUG] 连涨信号数量: {len(consecutive_signals)}")
        for i, sig in enumerate(consecutive_signals):
            print(f"[DEBUG] 连涨信号{i+1}: 索引={sig['index']}, 价格={sig['price']:.3f}, is_fake={sig['is_fake']}, wait_validate={sig['wait_validate']}")
        
        try:
            # 获取图表的实际显示范围（包含所有子图）
            # 使用figure的bbox来获取整个图表的显示边界
            fig_bbox = self.fig.get_window_extent()
            chart_pixel_height = fig_bbox.height
            
            # 获取Y轴的数据范围
            y_min, y_max = self.ax_price.get_ylim()
            
            # 获取图表的完整显示范围（从图表底部到顶部）
            # 使用transData来转换坐标
            display_bottom = self.ax_price.transData.inverted().transform((0, 0))[1]
            display_top = self.ax_price.transData.inverted().transform((0, chart_pixel_height))[1]
            
            # 用于跟踪上一个信号是否为RSI急涨信号
            last_signal_was_rsi_surge = False
            
            for signal in self.buy_signals:
                index = signal['index']
                price = signal['price']
                net_gain = signal['net_gain']
                is_fake = signal.get('is_fake', False)
                
                # 计算当天股价相对于前一交易日收盘价的涨跌幅
                prev_close = self._get_previous_close()
                if prev_close is not None and prev_close > 0:
                    daily_change_pct = (price - prev_close) / prev_close * 100
                else:
                    daily_change_pct = 0.0
                
                # 获取信号状态
                wait_validate = signal.get('wait_validate', False)
                
                # 检查信号类型
                signal_type = signal.get('signal_type', '')
                print(f"[DEBUG] 绘制信号: 类型={signal_type}, 索引={index}, 价格={price:.3f}")
                if '突破压力位' in signal_type:
                    # 破压力买入信号：不显示竖线，只显示红色向上三角形
                    line_style = None  # 不绘制竖线
                    line_color = None
                    label_color = 'red'
                    is_fake = True  # 强制设置为fake类型
                elif '连板' in signal_type:
                    # 连板涨停买入信号：不绘制信号，只检测（涨停线已单独绘制）
                    line_style = None  # 不绘制竖线
                    line_color = None
                    label_color = 'red'
                elif 'RSI急涨' in signal_type:
                    # RSI急涨买入信号：使用特殊样式显示
                    rsi_rise = signal.get('rsi_rise', 0)
                    if pd.isna(rsi_rise):
                        rsi_rise = 0
                    
                    # 检查上一个信号是否为RSI急涨信号
                    should_skip_label = last_signal_was_rsi_surge
                    
                    # RSI急涨信号使用红色虚线，突出显示
                    line_style = '--'
                    line_color = 'red'  # RSI急涨使用红色虚线
                    label_color = 'red'
                elif '连涨' in signal_type:
                    # 连涨买入信号：使用配置参数
                    from consecutive_signal_config import get_surge_config
                    config = get_surge_config()
                    line_style = config['line_style']
                    line_color = config['line_color']
                    label_color = config['label_color']
                elif is_fake:
                    # 假分时买入信号：使用红色点线
                    line_style = '--'
                    line_color = 'red'
                    label_color = 'red'
                elif wait_validate:
                    # 待确认信号：使用红色虚线
                    line_style = '-'
                    line_color = 'red'
                    label_color = 'red'
                else:
                    # 正常分时买入信号：使用红色实线
                    line_style = '-'
                    line_color = 'red'
                    label_color = 'red'
                
                # 检查信号类型并设置相应的显示格式
                signal_type = signal.get('signal_type', '')
                if '突破压力位' in signal_type:
                    # 压力位突破买入信号：显示红色向上三角形
                    resistance_level = signal.get('resistance_level', 0)
                    if pd.isna(resistance_level):
                        resistance_level = 0
                    
                    # 标签格式：红色向上三角形
                    label_text = "▲"
                    
                    # 重置状态：当前信号不是RSI急涨信号
                    last_signal_was_rsi_surge = False
                elif '连板' in signal_type:
                    # 连板涨停买入信号：不显示标签（涨停线已单独绘制）
                    label_text = ""  # 不显示标签
                    
                    # 重置状态：当前信号不是RSI急涨信号
                    last_signal_was_rsi_surge = False
                elif 'RSI急涨' in signal_type:
                    # 标签格式：急涨买，但可能被跳过
                    if should_skip_label:
                        label_text = ""  # 不显示标签，只显示竖线
                    else:
                        label_text = "急涨买"
                    
                    # 更新状态：当前信号是RSI急涨信号
                    last_signal_was_rsi_surge = True
                elif '连涨' in signal_type:
                    # 连涨信号：使用配置参数
                    from consecutive_signal_config import get_surge_config
                    config = get_surge_config()
                    label_text = config['display_text']
                    
                    # 重置状态：当前信号不是RSI急涨信号
                    last_signal_was_rsi_surge = False
                elif 'RSI分时买入' in signal_type:
                    # RSI买入信号：显示"B{布林线位置比例}"
                    bollinger_ratio = self._calculate_bollinger_ratio(signal, index)
                    label_text = f"B{bollinger_ratio}"
                    
                    # 重置状态：当前信号不是RSI急涨信号
                    last_signal_was_rsi_surge = False
                else:
                    # 其他买入信号：显示涨幅+RSI
                    rsi_1min = signal.get('rsi_1min', 0)
                    if pd.isna(rsi_1min):
                        rsi_1min = 0
                    
                    # 标签格式：+xx%,R(xx)
                    label_text = f"{net_gain:+.1f}%,R({rsi_1min:.1f})"
                    
                    # 重置状态：当前信号不是RSI急涨信号
                    last_signal_was_rsi_surge = False
                
                # 绘制竖线，垂直撑满整个图表的显示区域（MA上穿信号不绘制竖线）
                if line_style is not None and line_color is not None:
                    from matplotlib.lines import Line2D

                    x_pos = float(x_index[index])
                    # 根据信号类型设置线条宽度
                    if '连涨' in signal_type:
                        from consecutive_signal_config import get_surge_config
                        config = get_surge_config()
                        line_width = config['line_width']
                    else:
                        line_width = 1  # 其他信号使用标准线条
                    
                    line = Line2D([x_pos, x_pos], [display_bottom, display_top],
                                 color=line_color, linewidth=line_width, linestyle=line_style, alpha=0.7, zorder=5)
                    self.ax_price.add_line(line)
                
                # 计算信号位置：压力位突破信号居中对齐5分钟价格柱子
                if '突破压力位' in signal_type:
                    # 使用5分钟K线的中心位置
                    x_pos = self._get_5min_center_position(x_index, self.price_df.index, index)
                else:
                    # 其他信号使用原始位置
                    x_pos = float(x_index[index])
                
                # 标签位置：在信号价格下方
                if '连涨' in signal_type:
                    # 连涨信号：使用配置参数
                    from consecutive_signal_config import get_surge_config
                    config = get_surge_config()
                    label_offset = -(y_max - y_min) * config['label_offset_ratio']
                else:
                    label_offset = (y_max - y_min) * 0.03  # 向下偏移3%的数据范围
                label_y = price - label_offset
                
                # 根据信号类型设置不同的标签样式
                bbox_style = dict(facecolor='white', alpha=0.4, pad=2)  # 降低透明度，避免影响K线显示
                
                # 为破压力线和破支撑线设置特殊样式
                if '突破压力位' in signal_type:
                    # 破压力买入信号：红色边框，增大字体，无背景框
                    bbox_style = None  # 不显示背景框
                    font_size = 12  # 增大字体
                elif '跌破支撑位' in signal_type:
                    # 破支撑卖出信号：绿色边框，增大字体，无背景框
                    bbox_style = None  # 不显示背景框
                    font_size = 12  # 增大字体
                elif '连涨' in signal_type:
                    # 连涨信号：使用配置参数
                    from consecutive_signal_config import get_surge_config
                    config = get_surge_config()
                    bbox_style = config['bbox_style']
                    font_size = config['font_size']
                    font_weight = config['font_weight']
                else:
                    # 其他信号保持原有样式
                    bbox_style.update(edgecolor='blue', linewidth=1)
                    font_size = 8
                    font_weight = 'normal'
                
                # 设置字体权重
                font_weight = font_weight if 'font_weight' in locals() else 'normal'
                
                self.ax_price.text(x_pos, label_y, 
                                  label_text, 
                                  ha='center', va='top',
                                  fontsize=font_size, color=label_color,
                                  fontweight=font_weight,
                                  bbox=bbox_style,
                                  zorder=6)
                
        except Exception as e:
            print(f"绘制分时买入信号时发生错误: {e}")
    
    def _plot_sell_signals(self, x_index: np.ndarray, prices: np.ndarray):
        """绘制分时卖出信号竖线和净涨跌幅标签
        
        :param x_index: X轴索引数组
        :param prices: 价格数组
        """
        if self.sell_signals is None or len(self.sell_signals) == 0:
            return
        
        try:
            # 获取图表的实际显示范围（包含所有子图）
            # 使用figure的bbox来获取整个图表的显示边界
            fig_bbox = self.fig.get_window_extent()
            chart_pixel_height = fig_bbox.height
            
            # 获取Y轴的数据范围
            y_min, y_max = self.ax_price.get_ylim()
            
            # 获取图表的完整显示范围（从图表底部到顶部）
            # 使用transData来转换坐标
            display_bottom = self.ax_price.transData.inverted().transform((0, 0))[1]
            display_top = self.ax_price.transData.inverted().transform((0, chart_pixel_height))[1]
            
            # 用于跟踪上一个信号是否为RSI急跌信号
            last_signal_was_rsi_plunge = False
            
            for signal in self.sell_signals:
                index = signal['index']
                price = signal['price']
                net_gain = signal['net_gain']
                is_fake = signal.get('is_fake', False)
                
                # 计算当天股价相对于前一交易日收盘价的涨跌幅
                prev_close = self._get_previous_close()
                if prev_close is not None and prev_close > 0:
                    daily_change_pct = (price - prev_close) / prev_close * 100
                else:
                    daily_change_pct = 0.0
                
                # 获取信号状态
                wait_validate = signal.get('wait_validate', False)
                
                # 根据信号状态、假信号和当天股价涨幅动态设置竖线颜色和样式
                if is_fake:
                    # 假分时卖出信号：使用绿色点线
                    line_style = '--'
                    line_color = 'green'
                    label_color = 'green'
                elif wait_validate:
                    # 待确认信号：使用绿色虚线
                    line_style = '-'
                    line_color = 'green'
                    label_color = 'green'
                else:
                    # 正常分时卖出信号：使用绿色实线
                    line_style = '-'
                    line_color = 'green'
                    label_color = 'green'
                
                # 检查信号类型并设置相应的显示样式
                signal_type = signal.get('signal_type', '')
                if '跌破支撑位' in signal_type:
                    # 支撑位跌破卖出信号：不显示竖线，只显示绿色向下三角形
                    support_level = signal.get('support_level', 0)
                    if pd.isna(support_level):
                        support_level = 0
                    
                    # 破支撑信号不显示竖线
                    line_style = None  # 不绘制竖线
                    line_color = None
                    label_color = 'green'
                    
                    # 标签格式：绿色向下三角形
                    label_text = "▼"
                    
                    # 重置状态：当前信号不是RSI急跌信号
                    last_signal_was_rsi_plunge = False
                elif '连跌' in signal_type:
                    # 连跌卖出信号：使用配置参数
                    from consecutive_signal_config import get_plunge_config
                    config = get_plunge_config()
                    line_style = config['line_style']
                    line_color = config['line_color']
                    label_color = config['label_color']
                    
                    # 标签格式：使用配置参数
                    label_text = config['display_text']
                    
                    # 重置状态：当前信号不是RSI急跌信号
                    last_signal_was_rsi_plunge = False
                elif 'RSI急跌' in signal_type:
                    # RSI急跌卖出信号：使用特殊样式显示
                    rsi_drop = signal.get('rsi_drop', 0)
                    if pd.isna(rsi_drop):
                        rsi_drop = 0
                    
                    # 检查上一个信号是否为RSI急跌信号
                    should_skip_label = last_signal_was_rsi_plunge
                    
                    # RSI急跌信号使用绿色虚线，突出显示
                    line_style = '--'
                    line_color = 'green'  # RSI急跌使用绿色虚线
                    label_color = 'green'
                    
                    # 标签格式：急跌卖，但可能被跳过
                    if should_skip_label:
                        label_text = ""  # 不显示标签，只显示竖线
                    else:
                        label_text = "急跌卖"
                    
                    # 更新状态：当前信号是RSI急跌信号
                    last_signal_was_rsi_plunge = True
                else:
                    # 普通RSI卖出信号：显示布林线位置比例
                    rsi_1min = signal.get('rsi_1min', 0)
                    if pd.isna(rsi_1min):
                        rsi_1min = 0
                    
                    # 标签格式：B{布林线位置比例}
                    bollinger_ratio = self._calculate_bollinger_ratio(signal, index)
                    label_text = f"B{bollinger_ratio}"
                    
                    # 重置状态：当前信号不是RSI急跌信号
                    last_signal_was_rsi_plunge = False
                
                # 绘制竖线，垂直撑满整个图表的显示区域
                from matplotlib.lines import Line2D

                x_pos = float(x_index[index])
                # 根据信号类型设置线条宽度
                if '连跌' in signal_type:
                    from consecutive_signal_config import get_plunge_config
                    config = get_plunge_config()
                    line_width = config['line_width']
                else:
                    line_width = 1  # 其他信号使用标准线条
                
                line = Line2D([x_pos, x_pos], [display_bottom, display_top],
                             color=line_color, linewidth=line_width, linestyle=line_style, alpha=0.7, zorder=5)
                self.ax_price.add_line(line)
                
                # 计算信号位置：支撑位跌破信号居中对齐5分钟价格柱子
                if '跌破支撑位' in signal_type:
                    # 使用5分钟K线的中心位置
                    x_pos = self._get_5min_center_position(x_index, self.price_df.index, index)
                else:
                    # 其他信号使用原始位置
                    x_pos = float(x_index[index])
                
                # 只有当标签文本不为空时才绘制标签
                if label_text:  # 只有非空标签才绘制
                    # 标签位置：在信号价格下方
                    if '连跌' in signal_type:
                        # 连跌信号：使用配置参数
                        from consecutive_signal_config import get_plunge_config
                        config = get_plunge_config()
                        label_offset = (y_max - y_min) * config['label_offset_ratio']
                    else:
                        label_offset = (y_max - y_min) * 0.03  # 向下偏移3%的数据范围
                    label_y = price - label_offset
                    
                    # 根据信号类型设置不同的标签样式
                    bbox_style = dict(facecolor='white', alpha=0.4, pad=2)  # 降低透明度，避免影响K线显示
                    
                    # 为破支撑线设置特殊样式
                    if '跌破支撑位' in signal_type:
                        # 破支撑卖出信号：绿色，增大字体，无背景框
                        bbox_style = None  # 不显示背景框
                        font_size = 12  # 增大字体
                    elif '连跌' in signal_type:
                        # 连跌信号：使用配置参数
                        from consecutive_signal_config import get_plunge_config
                        config = get_plunge_config()
                        bbox_style = config['bbox_style']
                        font_size = config['font_size']
                        font_weight = config['font_weight']
                    elif is_fake:
                        bbox_style.update(edgecolor="green", linewidth=1)  # 假信号边框不加粗，降低透明度
                        font_size = 8
                        font_weight = 'normal'
                    else:
                        bbox_style.update(edgecolor='blue', linewidth=1)    # 正常信号边框
                        font_size = 8
                        font_weight = 'normal'
                    
                    # 设置字体权重
                    font_weight = font_weight if 'font_weight' in locals() else 'normal'
                    
                    self.ax_price.text(x_pos, label_y, 
                                      label_text, 
                                      ha='center', va='top',
                                      fontsize=font_size, color=label_color,
                                      fontweight=font_weight,
                                      bbox=bbox_style,
                                      zorder=6)
                
        except Exception as e:
            print(f"绘制分时卖出信号时发生错误: {e}")
    
    # ------------------------------------------------------------------
    # 鼠标十字定位功能
    # ------------------------------------------------------------------
    
    def _bind_mouse_events(self):
        """绑定鼠标事件和窗口事件"""
        self.canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self.canvas.mpl_connect('axes_leave_event', self._on_leave)
        
        # 绑定窗口大小变动事件
        if hasattr(self, 'window') and self.window:
            self.window.bind('<Configure>', self._on_window_configure)
            self.window.bind('<FocusIn>', self._on_window_focus)
            self.window.bind('<Button-1>', self._on_window_click)
            self.window.bind('<ButtonRelease-1>', self._on_window_click_release)
    
    def _on_mouse_move(self, event):
        """处理鼠标移动事件"""
        if not event.inaxes:
            return
        
        # 移除旧的十字线和文本
        self._remove_crosshair()
        
        # 确定当前面板（处理twinx轴的情况）
        current_ax = event.inaxes
        if current_ax == self.ax_price or (hasattr(self, '_ax_price_pct') and current_ax == self._ax_price_pct):
            self.current_panel = 'price'
            y_format = '{:.3f}'
            # 使用主价格轴进行绘制
            target_ax = self.ax_price
        elif current_ax == self.ax_cost:
            self.current_panel = 'cost'
            y_format = '{:.3f}'
            target_ax = self.ax_cost
        # 成交量面板已移除，不再需要处理
        elif current_ax == self.ax_rsi:
            self.current_panel = 'rsi'
            y_format = '{:.1f}'
            target_ax = self.ax_rsi
        else:
            return
        
        # 获取数据点
        x_data = int(round(event.xdata))
        if self.price_df is None or x_data < 0 or x_data >= len(self.price_df):
            return
        
        # 绘制垂直线（跨越所有面板）
        self.crosshair_lines = []
        for ax in [self.ax_price, self.ax_cost, self.ax_rsi]:
            if ax is not None:
                line = ax.axvline(x=x_data, color='gray', linestyle='--', alpha=0.2)
                self.crosshair_lines.append(line)
        
        # 绘制水平线（仅在当前面板）
        line = target_ax.axhline(y=event.ydata, color='gray', linestyle='--', alpha=0.2)
        self.crosshair_lines.append(line)
        
        # 显示坐标值
        self.crosshair_text = []
        
        # 时间显示（所有面板都需要）
        if self.price_df is not None and x_data < len(self.price_df):
            time = self.price_df.index[x_data]
            time_str = time.strftime('%H:%M')
            
            # 获取对应时间的价格
            price = self.price_df.iloc[x_data]['close']
            price_str = f'{price:.3f}'
            
            # 时间-价格显示在X轴位置（底部）
            time_price_str = f'{time_str}-{price_str}'
            text = self.ax_price.text(x_data, self.ax_price.get_ylim()[0], 
                                    time_price_str,
                                    ha='center', va='top',
                                    bbox=dict(facecolor='white', alpha=0.8, pad=1))
            self.crosshair_text.append(text)
        
        # Y轴数值显示
        if isinstance(y_format, str):
            y_str = y_format.format(event.ydata)
        else:
            y_str = y_format(event.ydata)
        
        # 右侧数值提示
        text = target_ax.text(
            target_ax.get_xlim()[1], event.ydata,
            y_str,
            ha='left', va='center',
            bbox=dict(facecolor='white', alpha=0.8, pad=1)
        )
        self.crosshair_text.append(text)
        print(f"[DEBUG] 文本已添加到crosshair_text列表，当前列表长度: {len(self.crosshair_text)}")
        
        # 重绘画布
        self.canvas.draw_idle()
    
    def _on_leave(self, event):
        """处理鼠标离开事件"""
        self._remove_crosshair()
        self.canvas.draw_idle()
    
    def _remove_crosshair(self):
        """移除十字线和文本"""
        try:
            if self.crosshair_lines:
                for line in self.crosshair_lines:
                    line.remove()
                self.crosshair_lines = None
            
            if self.crosshair_text:
                for text in self.crosshair_text:
                    text.remove()
                self.crosshair_text = None
            
        except Exception as e:
            print(f"移除十字线时出错: {str(e)}") 

    # ------------------------------------------------------------------
    # 信号自定义接口
    # ------------------------------------------------------------------
    
    def add_buy_signal(self, signal: IntradaySignalBase):
        """添加自定义分时买入信号
        
        :param signal: 分时买入信号对象，继承自IntradaySignalBase
        """
        self.signal_manager.add_buy_signal(signal)
        print(f"已添加分时买入信号: {signal.name}")
    
    def add_sell_signal(self, signal: IntradaySignalBase):
        """添加自定义分时卖出信号
        
        :param signal: 分时卖出信号对象，继承自IntradaySignalBase
        """
        self.signal_manager.add_sell_signal(signal)
        print(f"已添加分时卖出信号: {signal.name}")
    
    def remove_buy_signal(self, signal_name: str):
        """移除指定名称的分时买入信号
        
        :param signal_name: 分时信号名称
        """
        for i, signal in enumerate(self.signal_manager.buy_signals):
            if signal.name == signal_name:
                del self.signal_manager.buy_signals[i]
                print(f"已移除分时买入信号: {signal_name}")
                return
        print(f"未找到分时买入信号: {signal_name}")
    
    def remove_sell_signal(self, signal_name: str):
        """移除指定名称的分时卖出信号
        
        :param signal_name: 分时信号名称
        """
        for i, signal in enumerate(self.signal_manager.sell_signals):
            if signal.name == signal_name:
                del self.signal_manager.sell_signals[i]
                print(f"已移除分时卖出信号: {signal_name}")
                return
        print(f"未找到分时卖出信号: {signal_name}")
    
    def list_signals(self):
        """列出所有已配置的分时信号"""
        print("当前配置的分时买入信号:")
        for signal in self.signal_manager.buy_signals:
            print(f"  - {signal.name} (延迟{signal.delay_minutes}分钟)")
        
        print("当前配置的分时卖出信号:")
        for signal in self.signal_manager.sell_signals:
            print(f"  - {signal.name} (延迟{signal.delay_minutes}分钟)")
    
    def clear_all_signals(self):
        """清空所有自定义分时信号，恢复默认配置"""
        self.signal_manager.buy_signals.clear()
        self.signal_manager.sell_signals.clear()
        self.signal_manager.clear_pending_signals()
        
        # 重新配置默认分时信号
        self._setup_default_signals()
        print("已清空所有自定义分时信号，恢复默认配置")

    def _setup_default_signals(self):
        # 添加默认分时买入信号
        self.signal_manager.add_buy_signal(RSIBuySignal())
        self.signal_manager.add_buy_signal(RSISurgeBuySignal())
        # 添加连板涨停买入信号
        self.signal_manager.add_buy_signal(LimitUpConsecutiveBuySignal())
        # 添加连续5次连涨买入信号
        self.signal_manager.add_buy_signal(ConsecutiveSurgeBuySignal())
        # 添加默认分时卖出信号
        self.signal_manager.add_sell_signal(RSISellSignal())
        self.signal_manager.add_sell_signal(RSIPlungeSellSignal())
        # 添加连续5次连跌卖出信号
        from consecutive_plunge_signal import ConsecutivePlungeSellSignal
        self.signal_manager.add_sell_signal(ConsecutivePlungeSellSignal())
    
    def _update_bollinger_data(self, bollinger_upper: pd.Series, bollinger_middle: pd.Series, bollinger_lower: pd.Series):
        """在主线程中更新布林带数据
        
        :param bollinger_upper: 布林带上轨数据
        :param bollinger_middle: 布林带中轨数据
        :param bollinger_lower: 布林带下轨数据
        """
        try:
            self.bollinger_5min_upper = bollinger_upper
            self.bollinger_5min_middle = bollinger_middle
            self.bollinger_5min_lower = bollinger_lower
            self._bollinger_calculated = True
            
            # 重新进行信号检测（因为现在布林带数据可用了）
            self._detect_signals_with_bollinger()
            
            # 重新绘制图表以显示布林带
            if hasattr(self, 'window') and self.window and self.window.winfo_exists():
                self.window.after(0, self._draw)
                
        except Exception as e:
            print(f"更新布林带数据失败: {e}")

    def _detect_signals_with_bollinger(self):
        """在布林带数据可用时重新检测信号"""
        try:
            if self.price_df is None or self.price_df.empty:
                print("[DEBUG] 价格数据不可用，跳过信号检测")
                return
            
            price_df = self.price_df
            
            # 准备信号检测数据（包含布林带数据）
            data = {
                'ma_short_values': self.ma_short_values,
                'ma_mid_values': self.ma_mid_values,
                'ma_base_values': self.ma_base_values,
                'rsi_df': self.rsi_df,
                'close_prices': price_df['close'],
                'open_prices': price_df['open'],  # 添加开盘价数据，连涨信号需要
                'prev_close': self._get_previous_close(),
                'bollinger_upper': self.bollinger_5min_upper,
                'bollinger_middle': self.bollinger_5min_middle,
                'bollinger_lower': self.bollinger_5min_lower,
                'kdj_d_values': self.kdj_df['D'] if self.kdj_df is not None and not self.kdj_df.empty and 'D' in self.kdj_df.columns else None,  # 添加KDJ的D值数据
                'price_df': price_df,  # 添加完整的价格数据框
                'code': self.code  # 添加股票代码
            }
            
            # 重置连涨信号状态，确保能够重新检测
            for signal in self.signal_manager.buy_signals:
                if hasattr(signal, 'reset_state') and '连涨' in signal.name:
                    signal.reset_state()
            
            # 重置连跌信号状态，确保能够重新检测
            for signal in self.signal_manager.sell_signals:
                if hasattr(signal, 'reset_state') and '连跌' in signal.name:
                    signal.reset_state()
            
            # 检测买入和卖出信号
            print("[DEBUG] 布林带数据可用，开始检测信号...")
            basic_buy_signals = self.signal_manager.detect_buy_signals(data, price_df['close'])
            basic_sell_signals = self.signal_manager.detect_sell_signals(data, price_df['close'])
            
            print(f"[DEBUG] 信号检测完成 - 买入信号: {len(basic_buy_signals)}, 卖出信号: {len(basic_sell_signals)}")
            if basic_buy_signals:
                for i, signal in enumerate(basic_buy_signals):
                    print(f"[DEBUG] 买入信号 {i+1}: {signal.get('signal_type', 'Unknown')}")
            
            # 更新信号列表
            self.buy_signals = basic_buy_signals
            self.sell_signals = basic_sell_signals
            
            # 播放音效通知
            self._play_signal_audio_notifications()
            
        except Exception as e:
            print(f"[ERROR] 布林带信号检测失败: {e}")
            import traceback
            traceback.print_exc()

    def _calculate_bollinger_ratio(self, signal: Dict[str, Any], index: int) -> str:
        """计算布林带位置比例
        公式：(布林线中轨 - 现价差值)/(布林线中轨 - 下轨差值)
        买入信号：直接显示比例值
        卖出信号：显示绝对值（正值）
        
        :param signal: 信号数据
        :param index: 信号索引
        :return: 布林带位置比例字符串
        """
        try:
            # 获取布林带数据
            if (self.bollinger_5min_upper is None or self.bollinger_5min_middle is None or 
                self.bollinger_5min_lower is None):
                return ""
            
            if index >= len(self.bollinger_5min_middle):
                return ""
            
            # 获取当前价格和布林带值
            current_price = signal.get('price', 0)
            middle_band = self.bollinger_5min_middle.iloc[index]
            lower_band = self.bollinger_5min_lower.iloc[index]
            
            # 使用trading_utils中的通用布林带比例计算函数
            from trading_utils import calculate_bollinger_ratio
            return calculate_bollinger_ratio(current_price, middle_band, lower_band)
                
        except Exception as e:
            print(f"[ERROR] 计算布林带比例失败: {e}")
            return ""

    def _plot_bollinger_bands(self, x_index: np.ndarray, prices: np.ndarray):
        """绘制5分钟级别布林带
        
        :param x_index: X轴索引数组
        :param prices: 价格数组
        """
        try:
            if not self._bollinger_calculated or self.bollinger_5min_upper is None:
                return
            
            # 获取当前价格（用于判断线型）
            current_price = prices[-1] if len(prices) > 0 else 0
            middle_price = self.bollinger_5min_middle.iloc[-1] if len(self.bollinger_5min_middle) > 0 else 0
            
            # 根据当前价格相对于中轨的位置确定线型
            if current_price > middle_price:
                # 价格在中轨上方：上轨实线，下轨虚线
                upper_linestyle = '-'
                lower_linestyle = '--'
            else:
                # 价格在中轨下方：上轨虚线，下轨实线
                upper_linestyle = '--'
                lower_linestyle = '-'
            
            # 绘制布林带上轨（粉红色，参照K线图设置）
            self.ax_price.plot(x_index, self.bollinger_5min_upper.values, 
                             color='#FF69B4',  # 粉红色
                             linewidth=1,
                             alpha=0.6,
                             linestyle=upper_linestyle,
                             label='布林上轨')
            
            # 绘制布林带中轨（黄色）
            self.ax_price.plot(x_index, self.bollinger_5min_middle.values, 
                             color='#FFD700',  # 金黄色
                             linewidth=1,
                             alpha=0.7,
                             linestyle='-',
                             label='布林中轨')
            
            # 绘制布林带下轨（皇家蓝，参照K线图设置）
            self.ax_price.plot(x_index, self.bollinger_5min_lower.values, 
                             color='#4169E1',  # 皇家蓝
                             linewidth=1,
                             alpha=0.6,
                             linestyle=lower_linestyle,
                             label='布林下轨')
            
            print(f"[DEBUG] 布林带绘制完成，当前价格: {current_price:.3f}, 中轨: {middle_price:.3f}")
            print(f"[DEBUG] 线型设置 - 上轨: {upper_linestyle}, 下轨: {lower_linestyle}")
            
        except Exception as e:
            print(f"绘制布林带失败: {e}")
            import traceback
            traceback.print_exc()

    def _plot_latest_rsi_signal(self, x_index: np.ndarray, prices: np.ndarray):
        """绘制最新价格RSI信息信号
        
        :param x_index: X轴索引数组
        :param prices: 价格数组
        """
        # 注释掉RSI文字框的显示，不再在分时价格图表上显示RSI指标的两个文字框
        return
        
        # 以下代码已被注释，如需恢复RSI文字框显示，请取消注释
        """
        try:
            # 检查RSI数据是否存在
            if self.rsi_df is None or self.rsi_df.empty:
                return
            
            # 获取最新价格位置
            latest_index = len(prices) - 1
            latest_price = prices[latest_index]
            
            # 获取最新的RSI值
            latest_rsi6_1min = None
            latest_rsi6_5min = None
            
            if 'RSI6_1min' in self.rsi_df.columns:
                latest_rsi6_1min = self.rsi_df['RSI6_1min'].iloc[-1]
                if pd.isna(latest_rsi6_1min):
                    latest_rsi6_1min = 0  # 与_plot_rsi_panel保持一致
            
            if 'RSI6_5min' in self.rsi_df.columns:
                latest_rsi6_5min = self.rsi_df['RSI6_5min'].iloc[-1]
                if pd.isna(latest_rsi6_5min):
                    latest_rsi6_5min = 0  # 与_plot_rsi_panel保持一致
            
            # 如果两个RSI值都不可用，则不显示
            if (latest_rsi6_1min is None or latest_rsi6_1min == 0) and (latest_rsi6_5min is None or latest_rsi6_5min == 0):
                return
            
            # 获取Y轴范围用于定位
            y_min, y_max = self.ax_price.get_ylim()
            
            # 标签位置：在最新价格上方
            label_offset = (y_max - y_min) * 0.03  # 向上偏移3%的数据范围
            label_y = latest_price + label_offset
            
            # 确保标签在Y轴范围内
            if label_y > y_max:
                label_y = y_max - (y_max - y_min) * 0.02  # 如果超出上边界，放在上边界下方2%
            
            # 计算两个文字框的位置（垂直并排，左边对齐价格图表右侧，紧密相连）
            x_pos = float(x_index[latest_index])
            box_height = (y_max - y_min) * 0.015  # 文字框高度为价格范围的1.5%（缩小）
            
            # 获取价格图表的右边界位置（数据坐标）
            # 计算绘图区域右边界，排除轴标签区域
            try:
                # 获取轴的边界框
                ax_pos = self.ax_price.get_position()
                # 获取figure的宽度
                fig_width = self.fig.get_figwidth() * self.fig.dpi
                
                # 计算绘图区域的实际像素宽度（不包括轴标签）
                plot_width_pixels = (ax_pos.x1 - ax_pos.x0) * fig_width
                
                # 估算Y轴标签的宽度（假设为40像素）
                y_axis_label_width = 40
                
                # 计算绘图区域右边界在figure坐标系中的位置
                plot_right_fig = ax_pos.x0 + (plot_width_pixels - y_axis_label_width) / fig_width
                
                # 将figure坐标转换为数据坐标
                xlim = self.ax_price.get_xlim()
                # 计算数据坐标范围
                data_range = xlim[1] - xlim[0]
                # 计算绘图区域右边界对应的数据坐标
                chart_right = xlim[0] + (plot_right_fig - ax_pos.x0) / (ax_pos.x1 - ax_pos.x0) * data_range
                
                print(f"[DEBUG] 绘图区域计算: ax_pos={ax_pos}, fig_width={fig_width}, plot_width_pixels={plot_width_pixels}")
                print(f"[DEBUG] plot_right_fig={plot_right_fig}, chart_right={chart_right}")
                
            except Exception as e:
                print(f"计算绘图区域边界失败，使用备用方法: {e}")
                # 备用方法：使用get_xlim()
                chart_right = self.ax_price.get_xlim()[1]
            
            # 绘制1分钟RSI文字框（上方）
            if latest_rsi6_1min is not None and latest_rsi6_1min != 0:
                rsi6_1min_converted = int(latest_rsi6_1min - 50) * 2
                # 使用固定宽度格式，确保文字框宽度一致
                if rsi6_1min_converted >= 0:
                    rsi6_1min_text = f"+{rsi6_1min_converted:02d}"  # 正数: +01, +10
                else:
                    rsi6_1min_text = f"{rsi6_1min_converted:03d}"   # 负数: -01, -09
                
                # 1分钟RSI文字框样式（蓝色边框，根据转换值设置填充色）
                if rsi6_1min_converted >= 60:
                    fill_color = 'darkred'  # 深红色：数值超过60
                elif rsi6_1min_converted >= 0:
                    fill_color = 'red'      # 红色：数值在0-60之间
                elif rsi6_1min_converted <= -60:
                    fill_color = 'darkgreen'  # 深绿色：数值低于-60
                else:
                    fill_color = 'green'    # 绿色：数值在-60到0之间
                bbox_style_1min = dict(
                    facecolor=fill_color, 
                    alpha=1, 
                    pad=0.1,  # 添加内边距
                    edgecolor='blue', 
                    linewidth=2,  # 加厚边框宽度
                    boxstyle="round,pad=0.1"  # 设置圆角样式，添加内边距
                )
                
                # 上方框的位置：左边对齐价格图表右侧，向上偏移避免遮住价格曲线
                vertical_offset = (y_max - y_min) * 0.2  # 向上偏移20%的价格范围
                box_spacing = (y_max - y_min) * 0.025  # 两个文字框之间的间距
                upper_y = label_y + vertical_offset + box_spacing
                
                self.ax_price.text(
                    chart_right, 
                    upper_y, 
                    rsi6_1min_text, 
                    ha='left',  # 左对齐，让文字框左侧贴着价格图表右侧
                    va='bottom',  # 底部对齐，这样底边会贴着下方框的顶边
                    fontsize=9,  # 再放大字号
                    color='white',
                    bbox=bbox_style_1min,
                    zorder=7  # 确保在其他元素之上
                )
            
            # 绘制5分钟RSI文字框（下方）
            if latest_rsi6_5min is not None and latest_rsi6_5min != 0:
                rsi6_5min_converted = int(latest_rsi6_5min - 50) * 2
                # 使用固定宽度格式，确保文字框宽度一致
                if rsi6_5min_converted >= 0:
                    rsi6_5min_text = f"+{rsi6_5min_converted:02d}"  # 正数: +01, +10
                else:
                    rsi6_5min_text = f"{rsi6_5min_converted:03d}"   # 负数: -01, -09
                
                # 5分钟RSI文字框样式（紫色边框，根据转换值设置填充色）
                if rsi6_5min_converted >= 60:
                    fill_color = 'darkred'  # 深红色：数值超过60
                elif rsi6_5min_converted >= 0:
                    fill_color = 'red'      # 红色：数值在0-60之间
                elif rsi6_5min_converted <= -60:
                    fill_color = 'darkgreen'  # 深绿色：数值低于-60
                else:
                    fill_color = 'green'    # 绿色：数值在-60到0之间
                bbox_style_5min = dict(
                    facecolor=fill_color, 
                    alpha=1, 
                    pad=0.1,  # 添加内边距
                    edgecolor='orange', 
                    linewidth=2,  # 加厚边框宽度
                    boxstyle="round,pad=0.1"  # 设置圆角样式，添加内边距
                )
                
                # 下方框的位置：左边对齐价格图表右侧，向上偏移避免遮住价格曲线
                lower_y = label_y + vertical_offset
                
                self.ax_price.text(
                    chart_right, 
                    lower_y, 
                    rsi6_5min_text, 
                    ha='left',  # 左对齐，让文字框左侧贴着价格图表右侧
                    va='top',  # 顶部对齐，这样顶边会贴着上方框的底边
                    fontsize=9,  # 再放大字号
                    color='white',
                    bbox=bbox_style_5min,
                    zorder=7  # 确保在其他元素之上
                )
            
            print(f"[DEBUG] 分时窗口 - 绘制最新RSI信息信号:")
            print(f"[DEBUG]   基准位置: x={x_index[latest_index]}, y={label_y:.3f}")
            print(f"[DEBUG]   图表右边界: {chart_right:.3f}")
            print(f"[DEBUG]   框高度: {box_height:.3f}")
            print(f"[DEBUG]   垂直偏移: {vertical_offset:.3f}")
            print(f"[DEBUG]   框间距: {box_spacing:.3f}")
            if latest_rsi6_1min is not None:
                rsi6_1min_converted = int((latest_rsi6_1min - 50) * 2)
                # 使用相同的固定宽度格式
                if rsi6_1min_converted >= 0:
                    rsi6_1min_debug_text = f"+{rsi6_1min_converted:02d}"
                else:
                    rsi6_1min_debug_text = f"{rsi6_1min_converted:03d}"
                print(f"[DEBUG]   RSI6(1min): 原始值={latest_rsi6_1min:.1f}, 转换值={rsi6_1min_debug_text}, 位置=({chart_right:.3f}, {upper_y:.3f}), 对齐=left,bottom, 字号=9")
            if latest_rsi6_5min is not None:
                rsi6_5min_converted = int((latest_rsi6_5min - 50) * 2)
                # 使用相同的固定宽度格式
                if rsi6_5min_converted >= 0:
                    rsi6_5min_debug_text = f"+{rsi6_5min_converted:02d}"
                else:
                    rsi6_5min_debug_text = f"{rsi6_5min_converted:03d}"
                print(f"[DEBUG]   RSI6(5min): 原始值={latest_rsi6_5min:.1f}, 转换值={rsi6_5min_debug_text}, 位置=({chart_right:.3f}, {lower_y:.3f}), 对齐=left,top, 字号=9")
            
        except Exception as e:
            print(f"绘制最新RSI信息信号时发生错误: {e}")
            import traceback
            traceback.print_exc()
        """

    def force_refresh_data(self):
        """强制刷新数据，忽略缓存"""
        print("[DEBUG] 强制刷新数据")
        self._force_refresh = True
        # 立即触发数据更新
        if hasattr(self, 'window') and self.window and self.window.winfo_exists():
            threading.Thread(target=self._update_data, daemon=True).start()

    def set_cache_duration(self, duration_seconds: int):
        """设置缓存有效时间
        
        :param duration_seconds: 缓存有效时间（秒）
        """
        self._cache_valid_duration = duration_seconds
        print(f"[DEBUG] 缓存有效时间设置为: {duration_seconds}秒")

    def get_cache_status(self):
        """获取缓存状态信息"""
        from datetime import datetime
        now = datetime.now()
        
        if self._last_data_fetch_time is None:
            return "无缓存数据"
        
        time_since_last_fetch = (now - self._last_data_fetch_time).total_seconds()
        is_trading = self._is_trading_time()
        
        return {
            "last_fetch_time": self._last_data_fetch_time.strftime("%H:%M:%S"),
            "time_since_last_fetch": f"{time_since_last_fetch:.1f}秒",
            "is_trading_time": is_trading,
            "cache_duration": f"{self._cache_valid_duration}秒",
            "force_refresh": self._force_refresh,
            "last_trade_date": self._last_trade_date
        }
    
    def _plot_5min_candlesticks(self, x_index: np.ndarray, x_times: pd.Index):
        """绘制5分钟K线柱子（半透明，绿跌红涨）
        :param x_index: X轴索引数组
        :param x_times: 时间索引
        """
        try:
            if self.price_df is None or self.price_df.empty:
                return
            
            # 调试：检查原始数据
            print(f"[DEBUG] 原始price_df列名: {list(self.price_df.columns)}")
            print(f"[DEBUG] 原始price_df前5行数据:")
            print(self.price_df.head())
            print(f"[DEBUG] 原始price_df数据类型:")
            print(self.price_df.dtypes)
            
            # 检查必要的列是否存在
            required_columns = ['open', 'close', 'high', 'low', 'volume']
            missing_columns = [col for col in required_columns if col not in self.price_df.columns]
            if missing_columns:
                print(f"[ERROR] 缺少必要的列: {missing_columns}")
                return
            
            # 验证数据质量
            print(f"[DEBUG] 重采样前数据验证:")
            print(f"[DEBUG] open列非空值数量: {self.price_df['open'].notna().sum()}")
            print(f"[DEBUG] close列非空值数量: {self.price_df['close'].notna().sum()}")
            print(f"[DEBUG] high列非空值数量: {self.price_df['high'].notna().sum()}")
            print(f"[DEBUG] low列非空值数量: {self.price_df['low'].notna().sum()}")
            print(f"[DEBUG] volume列非空值数量: {self.price_df['volume'].notna().sum()}")
            
            # 检查是否有足够的有效数据
            if self.price_df['close'].notna().sum() < 5:
                print(f"[ERROR] 有效收盘价数据不足，无法进行5分钟重采样")
                return
            
            # 将1分钟数据重采样为5分钟K线数据
            # 使用offset='1min'对齐同花顺的时间方式：09:31-09:35, 09:36-09:40, 09:41-09:45
            price_5min = self.price_df.resample('5T', offset='1min').agg({
                'open': 'first',
                'close': 'last', 
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            # 调整时间戳以匹配同花顺的显示方式：09:31->09:35, 09:36->09:40, 09:41->09:45
            adjusted_timestamps = []
            for ts in price_5min.index:
                # 将时间戳向前调整4分钟，使09:31->09:35, 09:36->09:40, 09:41->09:45
                adjusted_ts = ts + pd.Timedelta(minutes=4)
                adjusted_timestamps.append(adjusted_ts)
            price_5min.index = adjusted_timestamps
            
            # 特殊处理：如果开盘价为0，使用前一根K线的收盘价作为开盘价
            if (price_5min['open'] == 0).any():
                print(f"[INFO] 检测到5分钟K线开盘价为0，进行修复...")
                # 使用前向填充，但第一根K线使用收盘价
                price_5min['open'] = price_5min['open'].replace(0, np.nan)
                price_5min['open'] = price_5min['open'].fillna(method='ffill')
                # 如果第一根K线的开盘价仍然为NaN，使用收盘价
                price_5min['open'] = price_5min['open'].fillna(price_5min['close'])
                print(f"[INFO] 5分钟K线开盘价修复完成")
            
            # 验证重采样后的数据
            print(f"[DEBUG] 重采样后数据验证:")
            print(f"[DEBUG] 5分钟数据行数: {len(price_5min)}")
            if not price_5min.empty:
                print(f"[DEBUG] 开盘价范围: {price_5min['open'].min():.4f} - {price_5min['open'].max():.4f}")
                print(f"[DEBUG] 收盘价范围: {price_5min['close'].min():.4f} - {price_5min['close'].max():.4f}")
                print(f"[DEBUG] 最高价范围: {price_5min['high'].min():.4f} - {price_5min['high'].max():.4f}")
                print(f"[DEBUG] 最低价范围: {price_5min['low'].min():.4f} - {price_5min['low'].max():.4f}")
                
                # 检查是否有异常的开盘价（为0或NaN）
                zero_open_count = (price_5min['open'] == 0).sum()
                nan_open_count = price_5min['open'].isna().sum()
                print(f"[DEBUG] 开盘价为0的数量: {zero_open_count}")
                print(f"[DEBUG] 开盘价为NaN的数量: {nan_open_count}")
                
                if zero_open_count > 0 or nan_open_count > 0:
                    print(f"[WARNING] 发现异常的开盘价，尝试修复...")
                    # 使用前一根K线的收盘价作为开盘价
                    price_5min['open'] = price_5min['open'].replace(0, np.nan)
                    price_5min['open'] = price_5min['open'].fillna(method='ffill')
                    # 如果第一根K线的开盘价仍然为NaN，使用收盘价
                    price_5min['open'] = price_5min['open'].fillna(price_5min['close'])
                    print(f"[DEBUG] 修复后开盘价范围: {price_5min['open'].min():.4f} - {price_5min['open'].max():.4f}")
            
            if price_5min.empty:
                print("[DEBUG] 5分钟K线数据为空，跳过绘制")
                return
            
            print(f"[DEBUG] 开始绘制5分钟K线柱子，数据点: {len(price_5min)}")
            print(f"[DEBUG] 5分钟K线数据前5行:")
            print(price_5min.head())
            print(f"[DEBUG] 5分钟K线开盘价范围: {price_5min['open'].min():.4f} - {price_5min['open'].max():.4f}")
            print(f"[DEBUG] 5分钟K线收盘价范围: {price_5min['close'].min():.4f} - {price_5min['close'].max():.4f}")
            
            # 计算5分钟K线在1分钟时间轴上的位置和宽度
            # 将5分钟时间戳映射到1分钟时间轴的位置
            x_5min_positions = []
            x_5min_widths = []
            
            for ts in price_5min.index:
                # 找到最接近的1分钟时间点
                time_diff = np.abs((x_times - ts).total_seconds())
                closest_idx = np.argmin(time_diff)
                
                # 修正位置计算：5分钟K线应该覆盖前5分钟的数据
                # 例如：09:35 K线应该覆盖09:31-09:35，中心在09:33
                # 09:35对应索引5，09:31-09:35对应索引1-5，中心在索引3
                # 所以位置应该是 closest_idx - 4，但需要确保不超出范围
                adjusted_pos = max(0, closest_idx - 4)
                x_5min_positions.append(adjusted_pos)
                
                # 计算5分钟在时间轴上的实际宽度
                # 5分钟 = 5个1分钟单位，但需要考虑时间轴的实际密度
                # 如果时间轴是连续的，5分钟应该占据5个单位宽度
                width = 5.0  # 5分钟 = 5个1分钟单位
                x_5min_widths.append(width)
            
            x_5min_positions = np.array(x_5min_positions)
            x_5min_widths = np.array(x_5min_widths)
            
            # 绘制每个5分钟K线柱子
            for i, (ts, row) in enumerate(price_5min.iterrows()):
                if i >= len(x_5min_positions):
                    continue
                    
                x_pos = x_5min_positions[i]
                width = x_5min_widths[i]
                open_price = row['open']
                close_price = row['close']
                high_price = row['high']
                low_price = row['low']
                
                # 数据验证和修复
                if pd.isna(open_price) or open_price == 0:
                    print(f"[WARNING] 第{i}根K线开盘价异常: {open_price}，使用收盘价替代")
                    open_price = close_price
                
                if pd.isna(close_price) or close_price == 0:
                    print(f"[WARNING] 第{i}根K线收盘价异常: {close_price}，跳过绘制")
                    continue
                
                if pd.isna(high_price) or high_price == 0:
                    high_price = max(open_price, close_price)
                
                if pd.isna(low_price) or low_price == 0:
                    low_price = min(open_price, close_price)
                
                # 确保价格数据的合理性
                if high_price < max(open_price, close_price):
                    high_price = max(open_price, close_price)
                if low_price > min(open_price, close_price):
                    low_price = min(open_price, close_price)
                
                # 判断涨跌：绿跌红涨
                is_up = close_price >= open_price
                alpha = 1.0  # 不透明
                
                # 绘制K线实体（开盘价到收盘价）
                body_height = abs(close_price - open_price)
                body_bottom = min(open_price, close_price)
                
                # 计算柱子的中心位置（matplotlib的bar函数默认x是中心位置）
                center_x = x_pos + width / 2
                
                # 如果开盘价和收盘价相等，绘制一条横线
                if body_height == 0:
                    # 十字星：开盘价=收盘价
                    line_color = '#FF6666' if is_up else '#66CC66'
                    self.ax_price.plot([center_x - width*0.4, center_x + width*0.4], 
                                     [open_price, open_price], 
                                     color=line_color, alpha=alpha, linewidth=2)
                else:
                    # 正常K线实体
                    if is_up:
                        # 红柱子：使用红边框，白色填充
                        self.ax_price.bar(center_x, body_height, bottom=body_bottom, 
                                        width=width*0.8, color='white', alpha=alpha, 
                                        edgecolor='#FF6666', linewidth=1.0)
                    else:
                        # 绿柱子：使用绿色填充
                        self.ax_price.bar(center_x, body_height, bottom=body_bottom, 
                                        width=width*0.8, color='#66CC66', alpha=alpha, 
                                        edgecolor='#66CC66', linewidth=0.5)
                
                # 绘制上下影线
                # 影线从K线柱子的中心开始
                
                # 上影线（最高价到实体顶部）
                if high_price > max(open_price, close_price):
                    shadow_color = '#FF6666' if is_up else '#66CC66'
                    self.ax_price.plot([center_x, center_x], 
                                     [max(open_price, close_price), high_price], 
                                     color=shadow_color, alpha=alpha, linewidth=1)
                
                # 下影线（最低价到实体底部）
                if low_price < min(open_price, close_price):
                    shadow_color = '#FF6666' if is_up else '#66CC66'
                    self.ax_price.plot([center_x, center_x], 
                                     [min(open_price, close_price), low_price], 
                                     color=shadow_color, alpha=alpha, linewidth=1)
            
            print(f"[DEBUG] 5分钟K线柱子绘制完成，共绘制{len(price_5min)}个柱子")
            
        except Exception as e:
            print(f"[ERROR] 绘制5分钟K线柱子失败: {str(e)}")
            import traceback
            traceback.print_exc()

    def _find_recent_peak(self, data_series: pd.Series, peak_type: str = "high") -> float:
        """找到数据序列中的最近一个峰值点（增强版）
        
        特殊处理15:00收盘价作为全天极值的情况：
        - 如果15:00收盘价是全天最高/最低点，即使无法被检测为peak，也会被作为峰值处理
        - 这解决了涨停/跌停时15:00收盘价无法被检测为peak的问题
        
        :param data_series: 数据序列
        :param peak_type: 峰值类型 ("high" 或 "low")
        :return: 最近峰值点的价格
        """
        try:
            import numpy as np
            from scipy.signal import find_peaks

            # 移除NaN值
            clean_data = data_series.dropna()
            if clean_data.empty:
                print(f"[DEBUG] 数据序列为空，无法找到峰值")
                return data_series.max() if peak_type == "high" else data_series.min()
            
            data_array = clean_data.values.astype(np.float64)
            
            # 检查15:00收盘价是否为全天极值
            last_value = data_array[-1]
            is_extreme = False
            
            if peak_type == "high":
                is_extreme = (last_value == data_array.max())
            else:
                is_extreme = (last_value == data_array.min())
            
            print(f"[DEBUG] 15:00收盘价 {last_value:.3f} 是否为全天{peak_type}极值: {is_extreme}")
            
            if peak_type == "high":
                # 寻找高点
                peaks, properties = find_peaks(
                    data_array,
                    prominence=data_array.std() * 0.05,  # 峰值突出度至少为价格标准差的5%
                    distance=3  # 峰值之间至少间隔3个数据点（3分钟）
                )
                
                print(f"[DEBUG] 标准peak检测找到 {len(peaks)} 个高点峰值")
                
                # 特殊处理：如果15:00收盘价是全天最高点且未被检测为峰值
                if is_extreme:
                    if len(peaks) == 0:
                        # 没有检测到峰值，直接使用15:00收盘价
                        print(f"[DEBUG] 没有检测到峰值，使用15:00收盘价作为峰值")
                        return float(last_value)
                    else:
                        # 检测到了峰值，比较15:00收盘价与最近峰值
                        recent_peak = data_array[peaks[-1]]
                        if last_value > recent_peak:
                            print(f"[DEBUG] 15:00收盘价 {last_value:.3f} 高于最近峰值 {recent_peak:.3f}，使用15:00收盘价")
                            return float(last_value)
                        else:
                            print(f"[DEBUG] 使用最近峰值 {recent_peak:.3f}")
                            return float(recent_peak)
                else:
                    # 正常情况，使用标准peak检测结果
                    if len(peaks) == 0:
                        print(f"[DEBUG] 未找到明显的高点峰值，使用最高价")
                        return float(data_array.max())
                    
                    # 获取峰值对应的价格和索引
                    peak_prices = data_array[peaks]
                    peak_indices = clean_data.index[peaks]
                    
                    print(f"[DEBUG] 找到 {len(peaks)} 个高点峰值:")
                    for i, (idx, price) in enumerate(zip(peak_indices, peak_prices)):
                        print(f"[DEBUG]   高点{i+1}: {idx} - {price:.3f}")
                    
                    # 返回最近的一个高点（最后一个）
                    recent_peak_price = float(peak_prices[-1])
                    recent_peak_time = peak_indices[-1]
                    print(f"[DEBUG] 最近高点: {recent_peak_time} - {recent_peak_price:.3f}")
                    
                    return recent_peak_price
                
            else:  # peak_type == "low"
                # 寻找低点（取负值检测）
                peaks, properties = find_peaks(
                    -data_array,  # 取负值检测低点
                    prominence=data_array.std() * 0.05,
                    distance=3
                )
                
                print(f"[DEBUG] 标准peak检测找到 {len(peaks)} 个低点峰值")
                
                # 特殊处理：如果15:00收盘价是全天最低点且未被检测为峰值
                if is_extreme:
                    if len(peaks) == 0:
                        # 没有检测到峰值，直接使用15:00收盘价
                        print(f"[DEBUG] 没有检测到峰值，使用15:00收盘价作为峰值")
                        return float(last_value)
                    else:
                        # 检测到了峰值，比较15:00收盘价与最近峰值
                        recent_peak = data_array[peaks[-1]]
                        if last_value < recent_peak:
                            print(f"[DEBUG] 15:00收盘价 {last_value:.3f} 低于最近峰值 {recent_peak:.3f}，使用15:00收盘价")
                            return float(last_value)
                        else:
                            print(f"[DEBUG] 使用最近峰值 {recent_peak:.3f}")
                            return float(recent_peak)
                else:
                    # 正常情况，使用标准peak检测结果
                    if len(peaks) == 0:
                        print(f"[DEBUG] 未找到明显的低点峰值，使用最低价")
                        return float(data_array.min())
                    
                    # 获取峰值对应的价格和索引
                    peak_prices = data_array[peaks]
                    peak_indices = clean_data.index[peaks]
                    
                    print(f"[DEBUG] 找到 {len(peaks)} 个低点峰值:")
                    for i, (idx, price) in enumerate(zip(peak_indices, peak_prices)):
                        print(f"[DEBUG]   低点{i+1}: {idx} - {price:.3f}")
                    
                    # 返回最近的一个低点（最后一个）
                    recent_peak_price = float(peak_prices[-1])
                    recent_peak_time = peak_indices[-1]
                    print(f"[DEBUG] 最近低点: {recent_peak_time} - {recent_peak_price:.3f}")
                    
                    return recent_peak_price
                
        except ImportError:
            print(f"[DEBUG] scipy未安装，使用简单方法找峰值")
            if peak_type == "high":
                return float(data_series.max())
            else:
                return float(data_series.min())
        except Exception as e:
            print(f"[ERROR] 峰值检测失败: {str(e)}")
            # 备用方案
            if peak_type == "high":
                return float(data_series.max())
            else:
                return float(data_series.min())

    def _get_opening_price(self) -> Optional[float]:
        """获取开盘价（9:25或9:30）"""
        try:
            if self.price_df is None or self.price_df.empty:
                return None
            
            # 尝试获取9:25的开盘价
            opening_time_925 = self._get_time_x_coordinate("09:25")
            if opening_time_925 is not None and opening_time_925 < len(self.price_df):
                opening_price = self.price_df.iloc[int(opening_time_925)]['close']
                print(f"[DEBUG] 获取9:25开盘价: {opening_price:.3f}")
                return float(opening_price)
            
            # 如果9:25没有数据，尝试9:30
            opening_time_930 = self._get_time_x_coordinate("09:30")
            if opening_time_930 is not None and opening_time_930 < len(self.price_df):
                opening_price = self.price_df.iloc[int(opening_time_930)]['close']
                print(f"[DEBUG] 获取9:30开盘价: {opening_price:.3f}")
                return float(opening_price)
            
            # 如果都没有，使用第一个数据点
            if len(self.price_df) > 0:
                opening_price = self.price_df.iloc[0]['close']
                print(f"[DEBUG] 使用第一个数据点作为开盘价: {opening_price:.3f}")
                return float(opening_price)
            
            return None
            
        except Exception as e:
            print(f"[ERROR] 获取开盘价失败: {str(e)}")
            return None

    def _get_previous_day_change(self) -> Optional[str]:
        """获取上一个交易日的涨跌情况
        
        :return: 'up'表示上涨, 'down'表示下跌, 'flat'表示平价, None表示无法获取
        """
        try:
            # 获取前一交易日收盘价
            prev_close = self._get_previous_close()
            if prev_close is None:
                return None
            
            # 获取当前开盘价
            opening_price = self._get_opening_price()
            if opening_price is None:
                return None
            
            # 计算涨跌
            change_pct = (opening_price - prev_close) / prev_close * 100
            
            if change_pct > 0.1:  # 涨幅超过0.1%认为是上涨
                return 'up'
            elif change_pct < -0.1:  # 跌幅超过0.1%认为是下跌
                return 'down'
            else:  # 涨跌幅在±0.1%以内认为是平价
                return 'flat'
                
        except Exception as e:
            print(f"[ERROR] 获取上一个交易日涨跌情况失败: {str(e)}")
            return None

    def _determine_line_styles(self) -> tuple[str, str]:
        """根据开盘价位置确定看涨线和看跌线的线型
        
        判断逻辑：
        1. 开盘价 > 看涨线：看涨趋势有效，看涨线实线，看跌线虚线
        2. 开盘价 < 看跌线：看跌趋势有效，看涨线虚线，看跌线实线
        3. 看跌线 ≤ 开盘价 ≤ 看涨线：根据距离哪条线更近判断趋势
           - 距离看涨线更近：看涨线实线，看跌线虚线
           - 距离看跌线更近：看涨线虚线，看跌线实线
           - 距离相等：两条线都是虚线（趋势不明）
        
        :return: (看涨线线型, 看跌线线型) 元组，'solid'表示实线，'dashed'表示虚线
        """
        try:
            # 获取开盘价
            opening_price = self._get_opening_price()
            if opening_price is None:
                print("[DEBUG] 无法获取开盘价，使用默认实线")
                return 'solid', 'solid'
            
            # 获取看涨线和看跌线价格
            bullish_price = self.bullish_line_price
            bearish_price = self.bearish_line_price
            
            if bullish_price is None or bearish_price is None:
                print("[DEBUG] 看涨线或看跌线价格为空，使用默认实线")
                return 'solid', 'solid'
            
            print(f"[DEBUG] 开盘价: {opening_price:.3f}, 看涨线: {bullish_price:.3f}, 看跌线: {bearish_price:.3f}")
            
            # 判断开盘价位置
            if opening_price > bullish_price:
                # 开盘价在看涨线上方，看涨趋势有效，看涨线实线，看跌线虚线
                print("[DEBUG] 开盘价在看涨线上方，看涨趋势有效，看涨线实线，看跌线虚线")
                return 'solid', 'dashed'
            elif opening_price < bearish_price:
                # 开盘价在看跌线下方，看跌趋势有效，看涨线虚线，看跌线实线
                print("[DEBUG] 开盘价在看跌线下方，看跌趋势有效，看涨线虚线，看跌线实线")
                return 'dashed', 'solid'
            else:
                # 开盘价在中间区域（在看涨线和看跌线之间），根据距离哪条线更近来判断
                distance_to_bullish = abs(opening_price - bullish_price)
                distance_to_bearish = abs(opening_price - bearish_price)
                
                print(f"[DEBUG] 开盘价在中间区域，距离看涨线: {distance_to_bullish:.3f}, 距离看跌线: {distance_to_bearish:.3f}")
                
                if distance_to_bullish < distance_to_bearish:
                    # 距离看涨线更近，看涨趋势有效，看涨线实线，看跌线虚线
                    print("[DEBUG] 距离看涨线更近，看涨趋势有效，看涨线实线，看跌线虚线")
                    return 'solid', 'dashed'
                elif distance_to_bearish < distance_to_bullish:
                    # 距离看跌线更近，看跌趋势有效，看涨线虚线，看跌线实线
                    print("[DEBUG] 距离看跌线更近，看跌趋势有效，看涨线虚线，看跌线实线")
                    return 'dashed', 'solid'
                else:
                    # 距离相等，趋势不明，都是虚线
                    print("[DEBUG] 距离看涨线和看跌线相等，趋势不明，都是虚线")
                    return 'dashed', 'dashed'
                    
        except Exception as e:
            print(f"[ERROR] 确定线型失败: {str(e)}")
            return 'solid', 'solid'

    def _get_time_x_coordinate(self, time_str: str) -> Optional[float]:
        """获取指定时间对应的x坐标
        
        :param time_str: 时间字符串，格式如 "09:40"
        :return: x坐标值，如果无法计算则返回None
        """
        try:
            if self.price_df is None or self.price_df.empty:
                return None
            
            # 解析时间字符串
            from datetime import datetime
            target_time = datetime.strptime(time_str, "%H:%M").time()
            
            # 获取当前交易日日期
            current_date = self.price_df.index[0].date()
            
            # 创建目标时间戳
            target_datetime = datetime.combine(current_date, target_time)
            target_timestamp = pd.Timestamp(target_datetime)
            
            # 查找最接近的时间点
            time_diff = abs(self.price_df.index - target_timestamp)
            closest_idx = time_diff.argmin()
            closest_time = self.price_df.index[closest_idx]
            
            # 计算x坐标（使用与_draw方法相同的逻辑）
            # x_index = np.arange(len(prices))，所以x坐标就是索引位置
            x_coordinate = float(closest_idx)
            
            print(f"[DEBUG] 时间{time_str}对应的x坐标: {x_coordinate} (时间: {closest_time})")
            return x_coordinate
            
        except Exception as e:
            print(f"[ERROR] 计算时间x坐标失败: {str(e)}")
            return None
    
    def _plot_volume_display_lines(self, x_index, x_times):
        """在成交量子图中绘制各价格的总成交量横向柱子
        :param x_index: X轴索引数组
        :param x_times: 时间索引
        """
        try:
            # 清除之前的总成交量柱子
            for bar in self.volume_display_lines:
                if hasattr(bar, 'remove'):
                    bar.remove()
            self.volume_display_lines.clear()
            
            if self.price_df is None or self.price_df.empty or "volume" not in self.price_df.columns:
                return
            
            # 计算各价格的总成交量
            volume_by_price = self._calculate_volume_by_price()
            
            if not volume_by_price:
                return
            
            # 动态创建成交量子图，constraint到价格图表
            if self.ax_volume is None:
                # 获取价格图的位置
                price_pos = self.ax_price.get_position()
                
                # 创建成交量子图，位置在价格图左侧
                self.ax_volume = self.fig.add_axes([
                    price_pos.x0 - 0.08,  # 在价格图左侧
                    price_pos.y0,         # 与价格图底部对齐
                    0.06,                 # 宽度
                    price_pos.height      # 高度与价格图一致
                ])
            
            # 设置成交量子图的Y轴范围与价格图一致
            y_min, y_max = self.ax_price.get_ylim()
            self.ax_volume.set_ylim(y_min, y_max)
            
            # 设置成交量子图的X轴范围（0到最大成交量）
            max_volume = max(data['total_volume'] for data in volume_by_price.values())
            self.ax_volume.set_xlim(0, max_volume * 1.1)  # 留10%的边距
            
            # 设置成交量子图的边框和坐标轴
            self.ax_volume.set_xticks([])
            self.ax_volume.set_yticks([])
            # 显示所有边框
            self.ax_volume.spines['top'].set_visible(True)
            self.ax_volume.spines['right'].set_visible(True)
            self.ax_volume.spines['bottom'].set_visible(True)
            self.ax_volume.spines['left'].set_visible(True)
            # 设置边框样式
            for spine in self.ax_volume.spines.values():
                spine.set_linewidth(1)
                spine.set_color('gray')
                spine.set_alpha(0.1)
            
            # 计算0.25%涨幅在图表中对应的高度
            chart_height = y_max - y_min
            
            # 获取前一交易日收盘价作为基准
            prev_close = self._get_previous_close()
            if prev_close is None or prev_close <= 0:
                prev_close = np.mean(self.price_df["close"].values)
            
            # 计算0.25%涨幅对应的价格差
            bin_size_pct = 0.25  # 0.25%
            bin_size_price = prev_close * bin_size_pct / 100
            
            # 计算0.25%涨幅在Y轴上的高度
            bin_height = bin_size_price / (y_max - y_min) * chart_height
            
            print(f"[DEBUG] 成交量子图 - 图表高度: {chart_height:.2f}, 0.25%涨幅价格差: {bin_size_price:.4f}, bin高度: {bin_height:.2f}")
            print(f"[DEBUG] 成交量子图 - X轴范围: 0 到 {max_volume * 1.1:.0f}")
            
            # 为每个价格绘制总成交量横向柱子（右对齐向左延伸）
            for price, volume_data in volume_by_price.items():
                if volume_data['total_volume'] > 0:
                    # 柱子长度等于成交量
                    bar_length = volume_data['total_volume']
                    
                    # 计算柱子位置（右对齐向左延伸）
                    bar_right = max_volume * 1.1  # 右边缘对齐成交量子图右边缘
                    bar_left = bar_right - bar_length  # 左边缘根据成交量计算
                    
                    print(f"[DEBUG] 价格{price:.2f}: 成交量={volume_data['total_volume']:.0f}, 柱子长度={bar_length:.2f}")
                    print(f"[DEBUG] 柱子位置: 左={bar_left:.2f}, 右={bar_right:.2f}")
                    
                    # 确定柱子颜色（正差值红色，负差值绿色）
                    color = 'red' if volume_data['net_volume'] >= 0 else 'green'
                    
                    # 使用bin的中心价格作为Y坐标
                    bin_center_price = volume_data['bin_center']
                    
                    # 绘制横向柱子（使用barh方法，右对齐向左延伸）
                    bar = self.ax_volume.barh(bin_center_price, bar_length, 
                                            height=bin_height, left=bar_left,
                                            color=color, alpha=0.8, edgecolor='black', linewidth=0.5)
                    self.volume_display_lines.append(bar[0])
            
            print(f"[DEBUG] 已绘制{len(self.volume_display_lines)}个总成交量柱子")
            
        except Exception as e:
            print(f"[ERROR] 绘制总成交量柱子失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _calculate_volume_by_price(self):
        """按0.25%涨幅一个bin计算各价格区间的总成交量
        :return: 字典，键为价格区间中心，值为成交量数据
        """
        try:
            volume_by_price = {}
            
            if self.price_df is None or self.price_df.empty or "volume" not in self.price_df.columns:
                return volume_by_price
            
            # 获取价格和成交量数据
            prices = self.price_df["close"].values
            volumes = self.price_df["volume"].values
            
            # 获取前一交易日收盘价作为基准
            prev_close = self._get_previous_close()
            if prev_close is None or prev_close <= 0:
                print("[WARNING] 无法获取前一交易日收盘价，使用当前价格范围计算")
                prev_close = np.mean(prices)
            
            # 计算价格范围
            price_min = np.min(prices)
            price_max = np.max(prices)
            
            # 按0.25%涨幅创建价格bins
            bin_size_pct = 0.25  # 0.25%
            bin_size_price = prev_close * bin_size_pct / 100
            
            # 计算bin的数量和范围
            min_bin = int((price_min - prev_close) / bin_size_price) - 1
            max_bin = int((price_max - prev_close) / bin_size_price) + 1
            
            print(f"[DEBUG] 价格范围: {price_min:.2f} - {price_max:.2f}")
            print(f"[DEBUG] 基准价格: {prev_close:.2f}, bin大小: {bin_size_price:.4f}")
            print(f"[DEBUG] bin范围: {min_bin} - {max_bin}, 共{max_bin - min_bin + 1}个bin")
            
            # 为每个bin计算成交量
            for bin_idx in range(min_bin, max_bin + 1):
                bin_center_price = prev_close + bin_idx * bin_size_price
                bin_lower = bin_center_price - bin_size_price / 2
                bin_upper = bin_center_price + bin_size_price / 2
                
                # 找到属于该bin的数据点
                in_bin = (prices >= bin_lower) & (prices < bin_upper)
                
                if np.any(in_bin):
                    # 计算该bin的总成交量
                    total_volume = np.sum(volumes[in_bin])
                    
                    # 计算买卖量差值
                    bin_prices = prices[in_bin]
                    bin_volumes = volumes[in_bin]
                    
                    if len(bin_prices) > 1:
                        # 计算价格变化方向
                        price_changes = np.diff(bin_prices)
                        buy_volume = np.sum(bin_volumes[1:][price_changes >= 0])
                        sell_volume = np.sum(bin_volumes[1:][price_changes < 0])
                        net_volume = buy_volume - sell_volume
                    else:
                        # 只有一个数据点，无法计算买卖差值
                        net_volume = 0
                        buy_volume = 0
                        sell_volume = 0
                    
                    volume_by_price[bin_center_price] = {
                        'total_volume': total_volume,
                        'net_volume': net_volume,
                        'buy_volume': buy_volume,
                        'sell_volume': sell_volume,
                        'bin_center': bin_center_price,
                        'bin_range': (bin_lower, bin_upper)
                    }
            
            print(f"[DEBUG] 生成了{len(volume_by_price)}个成交量bin")
            return volume_by_price
            
        except Exception as e:
            print(f"[ERROR] 计算各价格总成交量失败: {e}")
            import traceback
            traceback.print_exc()
            return {}