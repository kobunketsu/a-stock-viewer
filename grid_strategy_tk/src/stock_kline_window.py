import csv
import json
import math
import os
import threading
import time as time_module  # 重命名time模块避免冲突
import tkinter as tk
import tkinter.font as tkfont
import traceback
from datetime import datetime, time, timedelta  # 保持datetime.time的导入
from tkinter import messagebox, scrolledtext, ttk  # 添加 scrolledtext 导入
from typing import Any, Dict, List, Optional, Tuple, Union

import akshare as ak
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from base_window import BaseWindow
from components.etf_radar_chart import ETFRadarChart
from components.high_price_digit_distribution_chart import \
    HighPriceDigitDistributionChart
from components.low_price_digit_distribution_chart import \
    LowPriceDigitDistributionChart
from conditions import (BBWChangeCondition, CostAndConcentrationCondition,
                        CostCrossMaCondition, CostCrossPriceBodyCondition,
                        CostPriceCompareCondition, InstitutionTradingCondition,
                        KdjCrossCondition, PriceAboveMA5Condition,
                        PriceBelowMA5Condition, SignalMark)
from dateutil.relativedelta import relativedelta
from intraday_signals import is_limit_up_down
from intraday_window import IntradayWindow  # 新增
from lhb_data_processor import lhb_processor
from locales.localization import l
from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.dates import AutoDateLocator, DateFormatter
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.text import Text
from matplotlib.ticker import FuncFormatter
from memo_manager import MemoManager
from services.export_service import ExportService
from stock_analysis_engine import ETFAnalysisEngine
from stock_section_analysis import calculate_concept_avg_cost
from trading_utils import (calculate_consecutive_trend_gain, clear_trend_cache,
                           detect_uptrend_patterns, get_symbol_info,
                           get_symbol_info_by_name, is_valid_symbol)
from window_manager import WindowManager

# 全局调试开关 - 控制资金营业部详情的打印
DEBUG_FUND_BROKER_DETAILS = False


class ETFKLineWindow(BaseWindow):
    """ETF K线图显示窗口"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.chart_frame = None
        self.chart_canvas = None
        self.data_cache = {}
        self.current_code = None
        self.current_symbol_name = None
        self.current_data = None
        self.ma_lines: List[int] = [5, 10, 20, 250]  # 添加250日均线(年线)
        self.time_range: int = 60  # 默认显示60天数据
        self.is_loading: bool = False
        self.analysis_engine = ETFAnalysisEngine()  # 添加分析引擎
        self.radar_chart: Optional[ETFRadarChart] = None  # 雷达图实例
        self.period_mode: str = 'day'  # 新增周期状态变量
        self.period_config: Dict[str, Dict[str, Union[int, str, float]]] = {
            'day': {
                'range': 60, 
                'ak_period': 'daily',
                'default_zoom': 1.0,
                'buffer_ratio': 0.3,  # 30%缓冲
                'min_buffer': 9  # 最小需要9天数据计算KDJ
            },
            'week': {
                'range': 24*7, 
                'ak_period': 'weekly',
                'default_zoom': 0.6,
                'buffer_ratio': 0.5,  # 50%缓冲
                'min_buffer': 9  # 最小需要9周数据计算KDJ
            },
            'month': {
                'range': 12*30,  # 12个月
                'ak_period': 'monthly',
                'default_zoom': 1.0,  # 改为1.0，默认显示12个月
                'buffer_ratio': 0.75,  # 75%缓冲
                'min_buffer': 9  # 最小需要9个月数据计算KDJ
            }
        }
        
        # 初始化Matplotlib中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']  # 设置中文字体
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        
        self.crosshair_lines: Optional[List[Any]] = None  # 存储十字定位线，允许混合Artist
        
        # 分时图对应的日K线图垂直贯穿线
        self.intraday_date_vertical_line: Optional[Line2D] = None  # 存储分时图对应日期的垂直贯穿线
        self.intraday_date_str: Optional[str] = None  # 当前分时图显示的日期
        self.crosshair_text: Optional[List[Text]] = None   # 存储坐标文本
        self.current_panel: Optional[str] = None    # 当前鼠标所在面板
        
        # 添加字体配置
        self.font = {'family': 'Arial Unicode MS', 'size': 8}
        plt.rc('font', **self.font)  # 设置全局字体
        

        
        # 初始化图表相关的实例变量
        self.ax1: Optional[Axes] = None  # K线图
        self.ax2: Optional[Axes] = None  # 成交量
        self.ax3: Optional[Axes] = None  # RSI
        self.ax4: Optional[Axes] = None  # 筹码集中度
        self.ax5: Optional[Axes] = None  # 成本涨幅面板
        self.ax_fund: Optional[Axes] = None  # 资金来源净股数
        self._fund_source_df: Optional[pd.DataFrame] = None  # 金额
        self._fund_source_shares_df: Optional[pd.DataFrame] = None  # 股数
        # 资金来源子图序列缓存（与交易日等长，用于鼠标提示）
        self._fund_inst_series: Optional[np.ndarray] = None
        self._fund_hot_series: Optional[np.ndarray] = None
        self._fund_retail_series: Optional[np.ndarray] = None
        self._fund_use_shares: bool = True
        
        # 添加debug模式开关
        self.debug_mode: bool = False  # 设置为True开启debug模式
        
        # 新增分析进度相关变量
        self.is_analyzing_indicators: bool = False
        self.indicators_progress: int = 0
        self.market_intent: Dict[str, float] = {}
        self._current_indicators: Dict[str, float] = {}  # 存储当前指标数据
        self._current_selected_data: Optional[pd.Series] = None  # 存储当前选中数据
        self._current_selected_date: Optional[pd.Timestamp] = None  # 存储当前选中日期
        self.current_index: Optional[int] = None  # 跟踪当前选中位置
        
        self.last_y: float = 0  # 初始化y坐标
        self._last_update_source = None  # 添加标记，记录最后一次更新的来源
        self._last_update_time = 0  # 添加时间戳，防止过于频繁的更新
        
        # 初始化条件列表 - 按优先级从高到低排序
        self.conditions = [
            InstitutionTradingCondition(),     # 优先级 110
            # KdjCrossCondition(),           # 优先级 100 - 已移除KDJ金叉死叉信号
            # BBWChangeCondition(),          # 优先级 95
            CostAndConcentrationCondition(), # 优先级 90
            PriceBelowMA5Condition(),      # 优先级 88
            PriceAboveMA5Condition(),      # 优先级 88
            CostCrossPriceBodyCondition(),  # 优先级 82
            CostCrossMaCondition(),        # 优先级 80
            CostPriceCompareCondition(),    # 优先级 75
        ]
        
        # 添加Command+W快捷键绑定
        # self.window.bind('<Command-w>', lambda e: self.window.destroy())
        
        # 添加窗口关闭协议
        # self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)
        
        # 添加备忘录管理器
        self.memo_manager = MemoManager()
        self.current_symbol = None
        self.signal_valid_days = 3  # 信号有效期天数
        
        # 添加快捷键绑定⌘1
        # self.window.bind("<Command-1>", self.open_intraday_window)
        
        # 新增异步加载相关变量
        self._async_fund_task: Optional[threading.Thread] = None  # 资金来源异步任务
        self._async_cost_task: Optional[threading.Thread] = None  # 成本涨幅信号异步任务
        self._async_cancelled: bool = False  # 异步任务取消标志
        self._fund_loading_text: Optional[Text] = None  # 资金来源加载提示文本
        self._cost_loading_text: Optional[Text] = None  # 成本涨幅加载提示文本
        self._force_refresh_cyq: bool = False  # 筹码数据强制刷新标志
        
        # 新增：前高价格相关属性
        self.previous_high_price: Optional[float] = None
        self._previous_high_calculated = False
        
        # 新增：趋势检测缓存相关属性
        self._trends_cache: Optional[List[Dict[str, Any]]] = None
        self._trends_cache_code: Optional[str] = None
        self._trends_cache_date_range: Optional[tuple] = None
        
    def show(self, code: str, name: str):
        """显示K线图窗口"""
        # 如果切换了股票，取消之前的异步任务并清除缓存
        if self.current_code != code:
            self._cancel_async_tasks()
            # 清除分析引擎缓存，确保新股票获取最新数据
            if hasattr(self.analysis_engine, '_indicator_cache'):
                self.analysis_engine._indicator_cache.clear()
                print(f"切换股票，已清除分析引擎缓存: {code}")
            
            # 新增：清空前高价格数据，强制重新计算
            self.previous_high_price = None
            self._previous_high_calculated = False
            
            # 新增：清除趋势检测缓存，强制重新计算
            cache_data = {
                'trends_cache': self._trends_cache,
                'trends_cache_code': self._trends_cache_code,
                'trends_cache_date_range': self._trends_cache_date_range
            }
            clear_trend_cache(cache_data)
            self._trends_cache = cache_data['trends_cache']
            self._trends_cache_code = cache_data['trends_cache_code']
            self._trends_cache_date_range = cache_data['trends_cache_date_range']
            print(f"切换股票，已清除趋势检测缓存: {code}")
            
            # 新增：清空阻力带数据，强制重新计算
            self.resistance_band_upper = None
            self.resistance_band_lower = None
            
        self.current_code = code
        self.current_symbol_name = name
        self.current_symbol = code  # 添加这行，确保备忘录功能正常工作
        
        # 获取筹码分析属性（指数不获取筹码属性）
        is_index = str(code or "") in ["1A0001", "000001"]
        if not is_index:
            self.chip_attributes = self.analysis_engine.get_chip_attributes(code)
        else:
            self.chip_attributes = []
        
        if self.window is None:
            # 创建新窗口
            self.create_window()
            if self.window is not None:
                WindowManager.setup_window(self.window)  # 设置新窗口
            # 默认隐藏侧边栏
            self.toggle_sidebar()  # 确保在创建窗口后立即隐藏侧边栏
        else:
            # 更新现有窗口标题
            self.window.title(f"{self.current_symbol_name}({self.current_code}) - K线图")
            WindowManager.bring_to_front(self.window)  # 将已有窗口带到前面
            
            # 清除现有月度图表
            # for widget in self.monthly_chart_frame.winfo_children():
            #     widget.destroy()
        
        # 加载并显示K线数据
        self.load_data_and_show()
        
        # 加载备忘录内容
        self.load_memo()

    def create_window(self):
        """创建K线图窗口"""
        self.window = tk.Toplevel(self.parent)
        self.window.title(f"{self.current_symbol_name}({self.current_code}) - K线图")
        
        # 获取屏幕宽度和高度
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 设置窗口宽度为屏幕宽度的80%
        window_width = int(screen_width * 0.3)
        window_height = int(screen_height * 0.9)
        
        # 设置窗口大小和位置(居中)
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 添加截图快捷键绑定 - 使用基类的截图功能
        self.window.bind("<Command-b>", lambda e: self.capture_to_clipboard())
        
        # 创建工具栏
        toolbar = ttk.Frame(self.window)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # 添加搜索框
        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=tk.LEFT, padx=2)
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=15)
        search_entry.pack(side=tk.LEFT)
        
        # 绑定搜索事件
        search_entry.bind('<Return>', self.on_search_enter)
        
        # 添加放大镜按钮
        search_button = ttk.Label(search_frame, text="+")  # 改为加号
        search_button.pack(side=tk.LEFT, padx=(2, 0))
        search_button.bind('<Button-1>', self.add_to_watchlist)  # 修改绑定函数
        
        # 放大缩小按钮
        ttk.Button(toolbar, text="放大", width=8, command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="缩小", width=8, command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        
        # 在缩放按钮旁添加导出按钮
        self.export_button = ttk.Button(
            toolbar, 
            text="导出数据",
            command=self.export_chart_data
        )
        self.export_button.pack(side=tk.LEFT, padx=2)
        
        # 在工具栏添加周期切换按钮组
        period_frame = ttk.Frame(toolbar)
        period_frame.pack(side=tk.LEFT, padx=5)
        ttk.Button(period_frame, text="日线", command=lambda: self.set_period('day')).pack(side=tk.LEFT)
        ttk.Button(period_frame, text="周线", command=lambda: self.set_period('week')).pack(side=tk.LEFT)
        ttk.Button(period_frame, text="月线", command=lambda: self.set_period('month')).pack(side=tk.LEFT)
        
        # 新增刷新按钮
        refresh_btn = ttk.Button(
            toolbar,
            text="刷新 (⌘R)",
            command=self.refresh_data
        )
        refresh_btn.pack(side=tk.LEFT, padx=2)
        
        # 绑定快捷键
        self.window.bind("<Command-r>", lambda e: self.refresh_data())
        # 绑定Command+1快捷键 (数字键)，需使用 Key-1 避免被解释为鼠标按键1
        self.window.bind("<Command-Key-1>", self.open_intraday_window)
        # 兼容旧写法保留一次但标注已废弃（可根据测试删除）
        # self.window.bind("<Command-1>", self.open_intraday_window)  # type: ignore
                
        # 在原有按钮后添加计算按钮


        # 创建加载提示标签
        self.loading_label = ttk.Label(toolbar, text="")
        self.loading_label.pack(side=tk.RIGHT, padx=5)

        # 添加侧边栏控制按钮 - 放在最右侧
        self.sidebar_button = ttk.Button(
            toolbar,
            text="≡",  # 使用三条横线表示菜单图标
            width=3,
            command=self.toggle_sidebar
        )
        self.sidebar_button.pack(side=tk.RIGHT, padx=2)
        # 绑定快捷键
        self.window.bind("<Command-m>", lambda e: self.toggle_sidebar())        
        # 初始化侧边栏状态
        self.sidebar_visible = True  # 设置为True,这样第一次toggle时会隐藏
        
        # 创建水平分割的主容器
        self.main_container_h = ttk.PanedWindow(self.window, orient=tk.HORIZONTAL)
        self.main_container_h.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建左侧容器
        left_container = ttk.Frame(self.main_container_h)
        self.main_container_h.add(left_container, weight=4)  # 左侧占4份
        
        # 创建右侧信息面板
        self.info_frame = ttk.Frame(self.main_container_h)
        self.main_container_h.add(self.info_frame, weight=1)  # 右侧占1份
        
        # 创建信息表格
        self.create_info_table()
        
        # 原有的垂直分割容器移到左侧
        self.main_container = ttk.PanedWindow(left_container, orient=tk.VERTICAL)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建k线图容器
        self.chart_frame = ttk.Frame(self.main_container)
        self.main_container.add(self.chart_frame, weight=3)  # K线图占3份

        # 创建分时图容器
        self.indicator_container = ttk.PanedWindow(self.main_container, orient=tk.HORIZONTAL)
        self.main_container.add(self.indicator_container, weight=7)  # 分时图占7份，实现3:7比例（对应7:3显示）

        # --- 嵌入分时图容器 ---
        self.intraday_frame = ttk.Frame(self.indicator_container)
        self.indicator_container.add(self.intraday_frame, weight=1)
        from intraday_window import IntradayWindow

        # 显式转换为str以满足静态类型检查器
        self._intraday_window = IntradayWindow(
            self.intraday_frame, 
            str(self.current_code or ""), 
            str(self.current_symbol_name or ""), 
            embed=True, 
            show_toolbar=True,
            on_date_change_callback=self._on_intraday_date_change
        )
        
        # 设置分时窗口的高度比例变化回调
        self._intraday_window.set_height_ratio_callback(self._on_height_ratio_change)

        # 以下高价/低价分布图及月度图已废弃, 保留代码供参考
        # self.high_price_digit_frame = ttk.Frame(self.indicator_container)
        # self.indicator_container.add(self.high_price_digit_frame, weight=1)
        # self.high_price_digit_chart = HighPriceDigitDistributionChart(self.high_price_digit_frame)
        # self.high_price_digit_chart.frame.pack(fill=tk.BOTH, expand=True)

        # self.low_price_digit_frame = ttk.Frame(self.indicator_container)
        # self.indicator_container.add(self.low_price_digit_frame, weight=1)
        # self.low_price_digit_chart = LowPriceDigitDistributionChart(self.low_price_digit_frame)
        # self.low_price_digit_chart.frame.pack(fill=tk.BOTH, expand=True)

        # self.monthly_frame = ttk.Frame(self.indicator_container)
        # self.indicator_container.add(self.monthly_frame, weight=1)
        # self.monthly_title_frame = ttk.Frame(self.monthly_frame)
        # self.monthly_title_frame.pack(fill=tk.X, padx=5, pady=2)
        # self.monthly_chart_frame = ttk.Frame(self.monthly_frame)
        # self.monthly_chart_frame.pack(fill=tk.BOTH, expand=True, padx=5)

        # set_sash_positions 函数 (已移除)
        # def set_sash_positions():
        #     pass
        # self.window.after(50, set_sash_positions)

        # # 默认隐藏侧边栏 # <--- 注释掉或删除这一行
        # self.toggle_sidebar()

        # 在工具栏添加刷新按钮
        toolbar = ttk.Frame(self.window)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        # 在窗口创建完成后设置快捷键和关闭协议
        self.setup_window()  # 调用基类的setup_window方法

    def load_data_and_show(self, force_refresh=False):
        """加载数据并显示图表"""
        # 只有在非强制刷新时才检查loading状态
        if not force_refresh and self.is_loading:
            return
            
        # 设置筹码数据强制刷新标志
        if force_refresh:
            self._force_refresh_cyq = True
            # 清除趋势检测缓存，确保获取最新数据
            self._clear_trend_cache()
            # 清除分析引擎缓存，确保获取最新数据
            if hasattr(self.analysis_engine, '_indicator_cache'):
                self.analysis_engine._indicator_cache.clear()
                print(f"已清除分析引擎缓存，强制刷新: {self.current_code}")
            
            # 阻力带现在每次图表更新都重新计算，无需标志控制
            print(f"强制刷新数据，将重新计算前高阻力带: {self.current_code}")
            
        self.is_loading = True
        if hasattr(self, 'loading_label'):
            self.loading_label.configure(text="正在加载数据...")
        
        # 重置按钮状态
        

        
        def fetch_data():
            try:
                # 计算时间范围时额外向前获取数据用于计算指标
                end_date = datetime.now()
                
                # 为了计算布林线，需要额外20天的数据
                extra_days = 20  
                display_days = int(self.time_range)
                total_days = display_days + extra_days
                
                start_date = end_date - timedelta(days=total_days)
                
                # 调用分析引擎加载数据
                print(f"[DEBUG] 加载K线数据: 代码={self.current_code}, 名称={self.current_symbol_name}, 开始日期={start_date.strftime('%Y-%m-%d')}, 结束日期={end_date.strftime('%Y-%m-%d')}")
                print(f"[DEBUG] 分析引擎状态: {type(self.analysis_engine)}")
                
                try:
                    self.current_data = self.analysis_engine.load_data(
                        code=str(self.current_code or ""),
                        symbol_name=str(self.current_symbol_name or ""),
                        period_mode=self.period_mode,
                        start_date=start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d'),
                        period_config=self.period_config,
                        ma_lines=self.ma_lines,
                        force_refresh=force_refresh
                    )
                    print(f"[DEBUG] K线数据加载结果: 长度={len(self.current_data) if self.current_data is not None else 0}")
                    if self.current_data is not None and not self.current_data.empty:
                        print(f"[DEBUG] K线数据列名: {list(self.current_data.columns)}")
                        print(f"[DEBUG] K线数据时间范围: {self.current_data.index[0]} 到 {self.current_data.index[-1]}")
                    else:
                        print("[DEBUG] K线数据为空或None")
                except Exception as load_error:
                    print(f"[DEBUG] K线数据加载异常: {load_error}")
                    import traceback
                    traceback.print_exc()
                    raise load_error
                
                # 计算RSI指标（基于固定历史数据范围，确保一致性）
                if self.current_data is not None and not self.current_data.empty:
                    # 为了确保RSI计算的一致性，使用固定的历史数据范围
                    # 获取足够的历史数据用于RSI计算（至少100个交易日）
                    rsi_start_date = end_date - timedelta(days=150)  # 确保有足够的历史数据
                    rsi_data = self.analysis_engine.load_data(
                        code=str(self.current_code or ""),
                        symbol_name=str(self.current_symbol_name or ""),
                        period_mode=self.period_mode,
                        start_date=rsi_start_date.strftime('%Y-%m-%d'),
                        end_date=end_date.strftime('%Y-%m-%d'),
                        period_config=self.period_config,
                        ma_lines=self.ma_lines,
                        force_refresh=False  # 不强制刷新，使用缓存
                    )
                    
                    if rsi_data is not None and not rsi_data.empty:
                        # 基于完整历史数据计算RSI（引擎带缓存）
                        rsi_data = self.analysis_engine.calculate_rsi(rsi_data)
                        # 将RSI结果合并到当前数据中
                        for col in ['RSI6', 'RSI12', 'RSI24']:
                            if col in rsi_data.columns:
                                self.current_data[col] = rsi_data[col].tail(len(self.current_data))
                    else:
                        # 如果获取历史数据失败，使用当前数据计算RSI（引擎带缓存）
                        self.current_data = self.analysis_engine.calculate_rsi(self.current_data)
                
                # 在主线程中更新图表
                if self.window and self.window.winfo_exists():
                    self.window.after(0, self.update_chart)
                    self.window.after(0, lambda: self.show_latest_trading_data())
                    
                self._check_condition_trigger()
                
            except Exception as e:
                if self.window and self.window.winfo_exists():
                    self.window.after(0, lambda e=e: messagebox.showerror("错误", f"获取数据失败: {str(e)}"))
            finally:
                self.is_loading = False
                if hasattr(self, 'loading_label') and self.window and self.window.winfo_exists():
                    self.window.after(0, lambda: self.loading_label.configure(text=""))
        
        # 启动数据获取线程
        threading.Thread(target=fetch_data, daemon=True).start()

        # 异步拉取资金来源时间序列
        def fetch_fund_source():
            try:
                if self.current_data is None or self.current_data.empty:
                    return
                start_dt = self.current_data.index[0]
                end_dt = self.current_data.index[-1]
                start_str = start_dt.strftime('%Y%m%d')
                end_str = end_dt.strftime('%Y%m%d')
                
                # 不再使用get_fund_source_series API，直接使用营业部详细数据计算
                # 在绘制时实时计算，确保数据准确性
                self._fund_source_df = None  # 清空旧数据
                if self.window and self.window.winfo_exists():
                    self.window.after(0, self.update_chart)
            except Exception as e:
                print(f"资金来源数据获取失败: {str(e)}")

        threading.Thread(target=fetch_fund_source, daemon=True).start()
        
        # 获取并显示月度数据
        # try:
        #     monthly_data, year_range, _ = analyze_monthly_performance(self.current_code)
        #     self.create_monthly_chart(monthly_data, year_range)
        # except Exception as e:
        #     print(f"加载月度数据失败: {str(e)}")
        
    def update_chart(self):
        """更新图表"""
        try:
            # 检查窗口是否存在
            if not self.window or not self.window.winfo_exists():
                print("[DEBUG] K线图窗口不存在，跳过更新")
                return

            if self.current_data is None or self.current_data.empty:
                print("[DEBUG] K线图数据为空，跳过更新")
                return
            
            # 判断是否为指数
            is_index = str(self.current_code or "") in ["1A0001", "000001"]
            
            print(f"[DEBUG] 开始更新K线图，数据长度: {len(self.current_data)}")

            # 若资金来源数据未就绪，或不包含当前可见区末尾日期，尝试异步获取一次（调试输出）
            need_fetch_fund = False
            if self._fund_source_df is None:
                need_fetch_fund = True
            elif getattr(self._fund_source_df, 'empty', True):
                need_fetch_fund = True
            else:
                try:
                    last_idx_date = pd.Timestamp(self.current_data.index[-1]).strftime('%Y-%m-%d')
                    have_last = any(pd.Timestamp(d).strftime('%Y-%m-%d') == last_idx_date for d in self._fund_source_df.index)
                    if not have_last:
                        need_fetch_fund = True
                except Exception:
                    need_fetch_fund = True

            if need_fetch_fund and self.current_code:
                try:
                    print(f"[fund] 使用营业部详细数据重新计算资金来源")
                except Exception:
                    pass
                # 不再异步获取，直接在绘制时计算

            # 清除现有图表
            if hasattr(self, 'chart_canvas') and self.chart_canvas is not None:
                try:
                    widget = self.chart_canvas.get_tk_widget()
                    if widget.winfo_exists():  # 检查widget是否存在
                        widget.destroy()
                except Exception as e:
                    print(f"清除图表时出错: {str(e)}")

            try:
                # 创建新图表时设置固定的图表大小和边距
                fig = Figure(figsize=(10, 8), dpi=100)
                # 使用固定的边距替代constrained_layout，底部inset设置为最小
                fig.subplots_adjust(
                    left=0.12,    # 增加左边距,为y轴标签留出空间
                    right=0.92,   # 增加右边距,为y轴数值留出空间
                    top=0.95,     # 上边距
                    bottom=0.02,  # 底部inset设置为最小，减少空白
                    hspace=0.15   # 减少子图间距，进一步减少空白
                )

                # 修改GridSpec配置，新增资金来源子图
                gs = gridspec.GridSpec(7, 1, height_ratios=[3,1,1,1,1,1,1])
                
                # K线图
                self.ax1 = fig.add_subplot(gs[0, :])
                # 成交量图
                self.ax2 = fig.add_subplot(gs[1, :], sharex=self.ax1)
                # RSI图
                self.ax3 = fig.add_subplot(gs[2, :], sharex=self.ax1)
                # 成本涨幅图
                self.ax5 = fig.add_subplot(gs[3, :], sharex=self.ax1)
                # MA5偏离度图
                self.ax7 = fig.add_subplot(gs[4, :], sharex=self.ax1)
                # 筹码集中度图
                self.ax4 = fig.add_subplot(gs[5, :], sharex=self.ax1)
                # 资金来源子图
                self.ax_fund = fig.add_subplot(gs[6, :], sharex=self.ax1)
                
                # 获取数据
                data = self.current_data

                # 新增：计算前高价格
                if not hasattr(self, '_previous_high_calculated') or not self._previous_high_calculated:
                    try:
                        from trading_utils import (
                            calculate_previous_high_price,
                            get_previous_high_analysis)
                        
                        print(f"[DEBUG] K线窗口 - 开始计算前高价格: {self.current_code}")
                        
                        # 获取当前显示的最新日期
                        if data is not None and not data.empty:
                            latest_date = data.index[-1].strftime('%Y-%m-%d')
                            
                            # 计算前高价格
                            previous_high = calculate_previous_high_price(
                                symbol=self.current_code,
                                current_date=latest_date,
                                months_back=12,  # 改为1年（12个月）
                                security_type="ETF"  # 或根据实际证券类型调整
                            )
                            
                            if previous_high is not None:
                                self.previous_high_price = previous_high
                                print(f"[DEBUG] K线窗口 - 前高价格: {previous_high:.3f}")
                                
                                # 获取详细分析信息
                                analysis = get_previous_high_analysis(
                                    symbol=self.current_code,
                                    current_date=latest_date,
                                    months_back=12,  # 改为1年（12个月）
                                    security_type="ETF"
                                )
                                
                                if "error" not in analysis:
                                    print(f"[DEBUG] K线窗口 - 前高分析:")
                                    print(f"[DEBUG]   当前价格: {analysis['current_price']:.3f}")
                                    print(f"[DEBUG]   前高价格: {analysis['previous_high_price']:.3f}")
                                    print(f"[DEBUG]   前高日期: {analysis['previous_high_date']}")
                                    print(f"[DEBUG]   分析期间: {analysis['analysis_period']}")
                                    print(f"[DEBUG]   找到 {len(analysis['all_high_points'])} 个局部高点")
                                    
                                    # 显示前几个高点
                                    for i, point in enumerate(analysis['all_high_points'][:3]):
                                        status = "高于当前价" if point['higher_than_current'] else "低于当前价"
                                        print(f"[DEBUG]     高点{i+1}: {point['date']} - {point['price']:.3f} ({status})")
                                else:
                                    print(f"[DEBUG] K线窗口 - 前高分析失败: {analysis['error']}")
                            else:
                                print(f"[DEBUG] K线窗口 - 未找到前高价格")
                                self.previous_high_price = None
                            
                            self._previous_high_calculated = True
                            
                    except Exception as e:
                        print(f"[DEBUG] K线窗口 - 计算前高价格失败: {e}")
                        import traceback
                        traceback.print_exc()
                        self.previous_high_price = None
                        self._previous_high_calculated = True

                # 新增：计算阻力带（使用前高阻力带，与分时窗口一致）
                try:
                    print(f"[DEBUG] K线窗口 - 开始计算前高阻力带: {self.current_code}")
                    
                    # 获取最近一个交易日的日期
                    if data is not None and not data.empty:
                        latest_date = data.index[-1].strftime('%Y-%m-%d')
                        
                        print(f"[DEBUG] K线窗口 - 前高阻力带计算基准:")
                        print(f"[DEBUG]   最新交易日: {latest_date}")
                        
                        # 使用前高双价格计算阻力带（与分时窗口相同的逻辑）
                        from trading_utils import get_previous_high_dual_prices

                        # 根据股票代码判断证券类型
                        if self.current_code.startswith(("5", "15")):
                            security_type = "ETF"
                        elif self.current_code in ["1A0001", "000001"]:
                            security_type = "BOARD"
                        else:
                            security_type = "STOCK"
                        
                        dual_prices = get_previous_high_dual_prices(
                            symbol=self.current_code,
                            current_date=latest_date,
                            months_back=12,  # 1年
                            security_type=security_type
                        )
                        
                        if "error" not in dual_prices and dual_prices.get("resistance_band"):
                            resistance_band = dual_prices["resistance_band"]
                            self.resistance_band_upper = resistance_band["upper"]  # 上影线最高价
                            self.resistance_band_lower = resistance_band["lower"]  # 实体最高价
                            
                            print(f"[DEBUG] K线窗口 - 前高阻力带计算完成:")
                            print(f"[DEBUG]   上影线最高价: {self.resistance_band_upper:.3f}")
                            print(f"[DEBUG]   实体最高价: {self.resistance_band_lower:.3f}")
                            print(f"[DEBUG]   阻力带日期: {resistance_band['date']}")
                        else:
                            print(f"[DEBUG] K线窗口 - 前高阻力带计算失败: {dual_prices.get('error', '未知错误')}")
                            self.resistance_band_upper = None
                            self.resistance_band_lower = None
                    else:
                        print(f"[DEBUG] K线窗口 - 数据为空，无法计算前高阻力带")
                        self.resistance_band_upper = None
                        self.resistance_band_lower = None
                        
                except Exception as e:
                    print(f"[DEBUG] K线窗口 - 计算前高阻力带失败: {e}")
                    import traceback
                    traceback.print_exc()
                    self.resistance_band_upper = None
                    self.resistance_band_lower = None

                # 创建交易日索引
                trading_dates = data.index.values
                x_index = np.arange(len(trading_dates))

                # 计算K线颜色
                colors = ['red' if data.iloc[i]['收盘'] >= data.iloc[i]['开盘'] 
                         else 'green' for i in range(len(data))]

                # 绘制K线
                for i in range(len(data)):
                    # K线实体
                    self.ax1.vlines(x_index[i], data.iloc[i]['最低'], data.iloc[i]['最高'], 
                              color=colors[i], linewidth=1)
                    # K线影线
                    if colors[i] == 'red':
                        self.ax1.add_patch(Rectangle(
                            (x_index[i] - 0.25, data.iloc[i]['开盘']),
                            0.5,
                            data.iloc[i]['收盘'] - data.iloc[i]['开盘'],
                            facecolor=colors[i],
                            edgecolor=colors[i]
                        ))
                    else:
                        self.ax1.add_patch(Rectangle(
                            (x_index[i] - 0.25, data.iloc[i]['收盘']),
                            0.5,
                            data.iloc[i]['开盘'] - data.iloc[i]['收盘'],
                            facecolor=colors[i],
                            edgecolor=colors[i]
                        ))

                # 绘制MA均线
                for period in self.ma_lines:
                    self.ax1.plot(x_index, data[f'MA{period}'], 
                            linewidth=1, 
                            alpha=0.8)
                
                # 检测上涨趋势并绘制预期涨幅柱子
                try:
                    trends = self._detect_uptrend_patterns(data)
                    if trends:
                        self._plot_expected_gain_bars(data, x_index, trends)
                        print(f"[DEBUG] K线图 - 已绘制 {len(trends)} 个上涨趋势的预期涨幅柱子")
                    else:
                        print("[DEBUG] K线图 - 未检测到上涨趋势")
                except Exception as e:
                    print(f"[ERROR] K线图 - 趋势检测和绘制失败: {e}")
                    import traceback
                    traceback.print_exc()
                
                # 新增：绘制前高价格线
                # 前高价格带只在分时图上显示，K线图不显示
                
                # 添加布林线 - 根据支撑位和压力位动态调整线型
                if 20 in self.ma_lines and 'BOLL_UPPER' in data.columns:
                    # 计算支撑位和压力位
                    support_level, resistance_level, support_type, resistance_type = self._calculate_support_resistance_for_kline(data)
                    
                    # 根据支撑位和压力位确定布林线的线型
                    upper_linestyle = '--'  # 默认虚线
                    lower_linestyle = '--'  # 默认虚线
                    
                    if support_type == "布林下轨":
                        lower_linestyle = '-'  # 下轨作为支撑位时使用实线
                        print(f"[DEBUG] K线图：布林下轨作为支撑位，使用实线")
                    elif resistance_type == "布林下轨":
                        lower_linestyle = '-'  # 下轨作为压力位时使用实线
                        print(f"[DEBUG] K线图：布林下轨作为压力位，使用实线")
                    
                    if resistance_type == "布林上轨":
                        upper_linestyle = '-'  # 上轨作为压力位时使用实线
                        print(f"[DEBUG] K线图：布林上轨作为压力位，使用实线")
                    elif support_type == "布林上轨":
                        upper_linestyle = '-'  # 上轨作为支撑位时使用实线
                        print(f"[DEBUG] K线图：布林上轨作为支撑位，使用实线")
                    
                    # 绘制上轨
                    self.ax1.plot(x_index, data['BOLL_UPPER'], 
                            color='#FF69B4',  # 粉红色
                            linewidth=1,
                            alpha=0.6,
                            linestyle=upper_linestyle)
                    # 绘制下轨
                    self.ax1.plot(x_index, data['BOLL_LOWER'],
                            color='#4169E1',  # 皇家蓝
                            linewidth=1, 
                            alpha=0.6,
                            linestyle=lower_linestyle)
                    
                    # 在右侧Y轴上标记布林带相对最新收盘价的涨跌幅
                    latest_close = data['收盘'].iloc[-1]  # 最新交易日收盘价
                    latest_boll_upper = data['BOLL_UPPER'].iloc[-1]  # 最新布林上轨
                    latest_boll_lower = data['BOLL_LOWER'].iloc[-1]  # 最新布林下轨
                    
                    # 计算布林上轨涨跌幅
                    upper_change = ((latest_boll_upper - latest_close) / latest_close) * 100
                    # 计算布林下轨涨跌幅
                    lower_change = ((latest_boll_lower - latest_close) / latest_close) * 100
                    
                    # 在Y轴右侧添加布林上轨涨跌幅标记
                    self.ax1.text(
                        1.01,  # 右侧位置（贴边Y轴）
                        latest_boll_upper,  # Y轴位置
                        f'{upper_change:+.1f}%',  # 涨跌幅文本（带正负号）
                        transform=self.ax1.get_yaxis_transform(),  # 使用Y轴变换
                        ha='left', va='center',  # 左对齐，垂直居中
                        fontsize=8, color='#FF69B4', weight='bold',  # 与上轨颜色一致
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='#FF69B4')
                    )
                    
                    # 在Y轴右侧添加布林下轨涨跌幅标记
                    self.ax1.text(
                        1.01,  # 右侧位置（贴边Y轴）
                        latest_boll_lower,  # Y轴位置
                        f'{lower_change:+.1f}%',  # 涨跌幅文本（带正负号）
                        transform=self.ax1.get_yaxis_transform(),  # 使用Y轴变换
                        ha='left', va='center',  # 左对齐，垂直居中
                        fontsize=8, color='#4169E1', weight='bold',  # 与下轨颜色一致
                        bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='#4169E1')
                    )
                    
                    print(f"[DEBUG] K线图 - 布林带涨跌幅标记: 上轨{upper_change:+.1f}%, 下轨{lower_change:+.1f}%")
                    
                    # 存储支撑位和压力位信息，供分时图回调使用
                    self.current_support_level = support_level
                    self.current_resistance_level = resistance_level
                    self.current_support_type = support_type
                    self.current_resistance_type = resistance_type
                    
                    # 在右侧Y轴上标记平均成本相对最新收盘价的涨跌幅
                    if not is_index and '平均成本' in data.columns:
                        latest_avg_cost = data['平均成本'].iloc[-1]  # 最新平均成本
                        if not pd.isna(latest_avg_cost):
                            # 计算平均成本涨跌幅
                            avg_cost_change = ((latest_avg_cost - latest_close) / latest_close) * 100
                            
                            # 在Y轴右侧添加平均成本涨跌幅标记
                            self.ax1.text(
                                1.01,  # 右侧位置（贴边Y轴）
                                latest_avg_cost,  # Y轴位置
                                f'{avg_cost_change:+.1f}%',  # 涨跌幅文本（带正负号）
                                transform=self.ax1.get_yaxis_transform(),  # 使用Y轴变换
                                ha='left', va='center',  # 左对齐，垂直居中
                                fontsize=8, color='#FF69B4', weight='bold',  # 粉色，与平均成本线颜色一致
                                bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='#FF69B4')
                            )
                            
                            print(f"[DEBUG] K线图 - 平均成本涨跌幅标记: {avg_cost_change:+.1f}%")

                # 新增：绘制前高阻力带（与分时窗口样式一致）
                if hasattr(self, 'resistance_band_upper') and hasattr(self, 'resistance_band_lower'):
                    if self.resistance_band_upper is not None and self.resistance_band_lower is not None:
                        try:
                            # 获取K线数据的价格范围
                            price_min = data['最低'].min()
                            price_max = data['最高'].max()
                            
                            # 计算包含前高阻力带和筹码集中度的完整价格范围
                            all_prices = [price_min, price_max, self.resistance_band_upper, self.resistance_band_lower]
                            
                            # 添加筹码集中度价格范围
                            if '70成本-低' in data.columns and '90成本-高' in data.columns:
                                cost_70_low = data['70成本-低'].min()
                                cost_90_high = data['90成本-高'].max()
                                all_prices.extend([cost_70_low, cost_90_high])
                                print(f"[DEBUG] K线图 - 筹码集中度范围: 70低={cost_70_low:.3f}, 90高={cost_90_high:.3f}")
                            
                            extended_min = min(all_prices)
                            extended_max = max(all_prices)
                            
                            # 添加适当的边距
                            price_range = extended_max - extended_min
                            margin = price_range * 0.1  # 10%边距
                            visible_min = extended_min - margin
                            visible_max = extended_max + margin
                            
                            print(f"[DEBUG] K线图 - 价格范围计算:")
                            print(f"[DEBUG]   K线最低价: {price_min:.3f}")
                            print(f"[DEBUG]   K线最高价: {price_max:.3f}")
                            print(f"[DEBUG]   前高上影线: {self.resistance_band_upper:.3f}")
                            print(f"[DEBUG]   前高实体: {self.resistance_band_lower:.3f}")
                            print(f"[DEBUG]   扩展最低价: {extended_min:.3f}")
                            print(f"[DEBUG]   扩展最高价: {extended_max:.3f}")
                            print(f"[DEBUG]   可见范围: {visible_min:.3f} - {visible_max:.3f}")
                            
                            # 绘制前高阻力带（绿色填充，添加线条图案，与分时窗口样式一致）
                            self.ax1.axhspan(
                                self.resistance_band_lower, self.resistance_band_upper,
                                facecolor="green", alpha=0.3, zorder=1,
                                hatch='\\',  # 斜线填充
                                edgecolor='darkgreen',  # 边框颜色
                                linewidth=0.5  # 边框宽度
                                # 移除label，不显示在图例中
                            )
                            
                            # 绘制前高阻力带边界线（上下都用绿色实线）
                            self.ax1.axhline(
                                self.resistance_band_upper, 
                                color="green", 
                                linestyle="-",  # 实线
                                linewidth=1, 
                                alpha=0.8
                                # 移除label，不显示在图例中
                            )
                            self.ax1.axhline(
                                self.resistance_band_lower, 
                                color="green",  # 改为绿色
                                linestyle="-",  # 实线
                                linewidth=1, 
                                alpha=0.8
                                # 移除label，不显示在图例中
                            )
                            
                            # 设置Y轴范围，确保前高阻力带可见
                            self.ax1.set_ylim(visible_min, visible_max)
                            
                            # 在右侧Y轴上标记前高阻力带相对最近收盘价的涨幅
                            latest_close = data['收盘'].iloc[-1]  # 最近交易日收盘价
                            
                            # 计算涨幅百分比
                            upper_increase = ((self.resistance_band_upper - latest_close) / latest_close) * 100
                            lower_increase = ((self.resistance_band_lower - latest_close) / latest_close) * 100
                            
                            # 计算阻力带高度和窗口高度比例
                            resistance_band_height = self.resistance_band_upper - self.resistance_band_lower
                            window_height = visible_max - visible_min
                            height_ratio = resistance_band_height / window_height
                            
                            # 根据阻力带高度动态调整文字框位置
                            if height_ratio < 0.05:  # 阻力带很窄，使用固定偏移避免重叠
                                # 上影线文字框：向上偏移
                                upper_y_offset = 0.02  # 2%的窗口高度偏移
                                lower_y_offset = -0.02  # 2%的窗口高度偏移
                                print(f"[DEBUG] K线图 - 阻力带较窄({height_ratio:.3f})，使用固定偏移避免重叠")
                            else:  # 阻力带较宽，使用相对位置
                                upper_y_offset = 0.01  # 1%的窗口高度偏移
                                lower_y_offset = -0.01  # 1%的窗口高度偏移
                                print(f"[DEBUG] K线图 - 阻力带较宽({height_ratio:.3f})，使用相对位置")
                            
                            # 计算文字框的Y轴位置
                            upper_text_y = self.resistance_band_upper + (upper_y_offset * window_height)
                            lower_text_y = self.resistance_band_lower + (lower_y_offset * window_height)
                            
                            # 确保文字框在可见范围内
                            upper_text_y = min(upper_text_y, visible_max - 0.01 * window_height)
                            lower_text_y = max(lower_text_y, visible_min + 0.01 * window_height)
                            
                            # 在Y轴右侧添加涨幅标记
                            # 顶部位置：前高上影线涨幅
                            self.ax1.text(
                                1.01,  # 右侧位置（贴边Y轴）
                                upper_text_y,  # 动态调整的Y轴位置
                                f'+{upper_increase:.1f}%',  # 涨幅文本
                                transform=self.ax1.get_yaxis_transform(),  # 使用Y轴变换
                                ha='left', va='center',  # 左对齐，垂直居中
                                fontsize=8, color='red', weight='bold',
                                bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='red')
                            )
                            
                            # 底部位置：前高实体涨幅
                            self.ax1.text(
                                1.01,  # 右侧位置（贴边Y轴）
                                lower_text_y,  # 动态调整的Y轴位置
                                f'+{lower_increase:.1f}%',  # 涨幅文本
                                transform=self.ax1.get_yaxis_transform(),  # 使用Y轴变换
                                ha='left', va='center',  # 左对齐，垂直居中
                                fontsize=8, color='red', weight='bold',
                                bbox=dict(boxstyle="round,pad=0.2", facecolor='white', alpha=0.8, edgecolor='red')
                            )
                            
                            print(f"[DEBUG] K线图 - 绘制前高阻力带: {self.resistance_band_lower:.3f} - {self.resistance_band_upper:.3f}")
                            print(f"[DEBUG] K线图 - 已设置Y轴范围: {visible_min:.3f} - {visible_max:.3f}")
                            print(f"[DEBUG] K线图 - 前高涨幅标记: 上影线+{upper_increase:.1f}%, 实体+{lower_increase:.1f}%")
                                
                        except Exception as e:
                            print(f"[DEBUG] K线图 - 绘制前高阻力带失败: {e}")
                            import traceback
                            traceback.print_exc()

                # 计算并显示日线、周线和月线连阳(阴)信息
                try:
                    # 计算日线连阳(阴)，包括前一个周期状态
                    day_up, day_down, prev_day_up, prev_day_down = self._calculate_consecutive_days(data, 'day')
                    # 计算周线连阳(阴)，包括前一个周期状态
                    week_up, week_down, prev_week_up, prev_week_down = self._calculate_consecutive_days(data, 'week')
                    # 计算月线连阳(阴)，包括前一个周期状态
                    month_up, month_down, prev_month_up, prev_month_down = self._calculate_consecutive_days(data, 'month')
                    
                    # 格式化前一个周期显示文本
                    prev_day_text = f"{prev_day_up}连阳" if prev_day_up > 0 else f"{prev_day_down}连阴" if prev_day_down > 0 else "0连阳(阴)"
                    prev_week_text = f"{prev_week_up}连阳" if prev_week_up > 0 else f"{prev_week_down}连阴" if prev_week_down > 0 else "0连阳(阴)"
                    prev_month_text = f"{prev_month_up}连阳" if prev_month_up > 0 else f"{prev_month_down}连阴" if prev_month_down > 0 else "0连阳(阴)"
                    
                    # 格式化当前周期显示文本
                    current_day_text = f"{day_up}连阳" if day_up > 0 else f"{day_down}连阴" if day_down > 0 else "0连阳(阴)"
                    current_week_text = f"{week_up}连阳" if week_up > 0 else f"{week_down}连阴" if week_down > 0 else "0连阳(阴)"
                    current_month_text = f"{month_up}连阳" if month_up > 0 else f"{month_down}连阴" if month_down > 0 else "0连阳(阴)"
                    
                    # 计算趋势涨幅信息（仅在4连阳时显示）
                    day_trend_info = ""
                    week_trend_info = ""
                    month_trend_info = ""
                    
                    # 检查日线趋势：当前趋势或上一个趋势是否有4连阳
                    if day_up >= 4:
                        # 当前趋势满足4连阳条件
                        try:
                            day_gain_pct, day_current_price, day_target_price = calculate_consecutive_trend_gain(data, 'day')
                            print(f"[DEBUG] 日线趋势计算(当前): 连阳{day_up}天, 涨幅{day_gain_pct:.2f}%, 当前价格{day_current_price:.3f}, 目标价格{day_target_price:.3f}")
                            if day_gain_pct != 0:  # 只要涨幅不为0就显示
                                day_trend_info = f", 趋势{day_target_price:.2f} {day_gain_pct:+.1f}%"
                                print(f"[DEBUG] 日线趋势信息: {day_trend_info}")
                            else:
                                print(f"[DEBUG] 日线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 日线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    elif prev_day_up >= 4:
                        # 当前趋势不满足，但上一个趋势满足4连阳条件
                        try:
                            # 计算上一个趋势的趋势价格和涨幅
                            day_gain_pct, day_current_price, day_target_price = self._calculate_previous_trend_gain(data, 'day', prev_day_up)
                            print(f"[DEBUG] 日线趋势计算(上一个): 连阳{prev_day_up}天, 涨幅{day_gain_pct:.2f}%, 当前价格{day_current_price:.3f}, 目标价格{day_target_price:.3f}")
                            if day_gain_pct != 0:  # 只要涨幅不为0就显示
                                day_trend_info = f", 趋势{day_target_price:.2f} {day_gain_pct:+.1f}%"
                                print(f"[DEBUG] 日线趋势信息(上一个): {day_trend_info}")
                            else:
                                print(f"[DEBUG] 日线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 日线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 检查周线趋势：当前趋势或上一个趋势是否有4连阳
                    if week_up >= 4:
                        # 当前趋势满足4连阳条件
                        try:
                            week_gain_pct, week_current_price, week_target_price = calculate_consecutive_trend_gain(data, 'week')
                            print(f"[DEBUG] 周线趋势计算(当前): 连阳{week_up}天, 涨幅{week_gain_pct:.2f}%, 当前价格{week_current_price:.3f}, 目标价格{week_target_price:.3f}")
                            if week_gain_pct != 0:  # 修改条件：只要涨幅不为0就显示
                                week_trend_info = f", 趋势{week_target_price:.2f} {week_gain_pct:+.1f}%"
                                print(f"[DEBUG] 周线趋势信息: {week_trend_info}")
                            else:
                                print(f"[DEBUG] 周线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 周线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    elif prev_week_up >= 4:
                        # 当前趋势不满足，但上一个趋势满足4连阳条件
                        try:
                            # 计算上一个趋势的趋势价格和涨幅
                            week_gain_pct, week_current_price, week_target_price = self._calculate_previous_trend_gain(data, 'week', prev_week_up)
                            print(f"[DEBUG] 周线趋势计算(上一个): 连阳{prev_week_up}天, 涨幅{week_gain_pct:.2f}%, 当前价格{week_current_price:.3f}, 目标价格{week_target_price:.3f}")
                            if week_gain_pct != 0:  # 只要涨幅不为0就显示
                                week_trend_info = f", 趋势{week_target_price:.2f} {week_gain_pct:+.1f}%"
                                print(f"[DEBUG] 周线趋势信息(上一个): {week_trend_info}")
                            else:
                                print(f"[DEBUG] 周线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 周线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 检查月线趋势：当前趋势或上一个趋势是否有4连阳
                    if month_up >= 4:
                        # 当前趋势满足4连阳条件
                        try:
                            # 获取扩展数据用于月线趋势计算
                            extended_data = self._get_extended_data_for_monthly_calculation()
                            month_gain_pct, month_current_price, month_target_price = calculate_consecutive_trend_gain(data, 'month', extended_data)
                            print(f"[DEBUG] 月线趋势计算(当前): 连阳{month_up}天, 涨幅{month_gain_pct:.2f}%, 当前价格{month_current_price:.3f}, 目标价格{month_target_price:.3f}")
                            if month_gain_pct != 0:  # 修改条件：只要涨幅不为0就显示
                                month_trend_info = f", 趋势{month_target_price:.2f} {month_gain_pct:+.1f}%"
                                print(f"[DEBUG] 月线趋势信息: {month_trend_info}")
                            else:
                                print(f"[DEBUG] 月线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 月线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    elif prev_month_up >= 4:
                        # 当前趋势不满足，但上一个趋势满足4连阳条件
                        try:
                            # 计算上一个趋势的趋势价格和涨幅
                            month_gain_pct, month_current_price, month_target_price = self._calculate_previous_trend_gain(data, 'month', prev_month_up)
                            print(f"[DEBUG] 月线趋势计算(上一个): 连阳{prev_month_up}天, 涨幅{month_gain_pct:.2f}%, 当前价格{month_current_price:.3f}, 目标价格{month_target_price:.3f}")
                            if month_gain_pct != 0:  # 只要涨幅不为0就显示
                                month_trend_info = f", 趋势{month_target_price:.2f} {month_gain_pct:+.1f}%"
                                print(f"[DEBUG] 月线趋势信息(上一个): {month_trend_info}")
                            else:
                                print(f"[DEBUG] 月线趋势涨幅为0，不显示趋势信息")
                        except Exception as e:
                            print(f"[DEBUG] 月线趋势计算失败: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # 计算各周期涨跌幅
                    daily_change = self._calculate_daily_change_percentage(data)
                    weekly_change = self._calculate_weekly_change_percentage(data)
                    monthly_change = self._calculate_monthly_change_percentage(data)
                    
                    # 组合显示文本 - 先显示前一个状态，再显示当前状态，最后显示趋势信息
                    day_display = f"日线{prev_day_text},{current_day_text},今日{daily_change}{day_trend_info}"
                    week_display = f"周线{prev_week_text},{current_week_text},本周{weekly_change}{week_trend_info}"
                    month_display = f"月线{prev_month_text},{current_month_text},本月{monthly_change}{month_trend_info}"
                    
                    # 计算颜色
                    day_color = self._get_consecutive_color(prev_day_up, prev_day_down, day_up, day_down)
                    week_color = self._get_consecutive_color(prev_week_up, prev_week_down, week_up, week_down)
                    month_color = self._get_consecutive_color(prev_month_up, prev_month_down, month_up, month_down)
                    
                    # 在K线图左上角显示日线连阳(阴)信息
                    self.ax1.text(
                        0.01, 0.99,  # 最顶部位置
                        day_display,
                        transform=self.ax1.transAxes,
                        color=day_color,
                        fontsize=8,
                        verticalalignment='top',
                        bbox=dict(
                            facecolor='white',
                            alpha=0.8,
                            pad=4,  # 增加内边距
                            edgecolor='#CCCCCC'
                        )
                    )
                    
                    # 在日线文字框下方显示周线连阳(阴)信息
                    self.ax1.text(
                        0.01, 0.90,  # 日线下方
                        week_display,
                        transform=self.ax1.transAxes,
                        color=week_color,
                        fontsize=8,
                        verticalalignment='top',
                        bbox=dict(
                            facecolor='white',
                            alpha=0.8,
                            pad=4,  # 增加内边距
                            edgecolor='#CCCCCC'
                        )
                    )
                    
                    # 在周线文字框下方显示月线连阳(阴)信息
                    self.ax1.text(
                        0.01, 0.81,  # 周线下方
                        month_display,
                        transform=self.ax1.transAxes,
                        color=month_color,
                        fontsize=8,
                        verticalalignment='top',
                        bbox=dict(
                            facecolor='white',
                            alpha=0.8,
                            pad=4,  # 增加内边距
                            edgecolor='#CCCCCC'
                        )
                    )
                    
                    print(f"[DEBUG] K线图 - 连阳(阴)信息: {day_display}, {week_display}, {month_display}")
                    
                except Exception as e:
                    print(f"[DEBUG] K线图 - 计算连阳(阴)信息失败: {e}")

                # 创建成交量的第二个Y轴，并调整位置
                ax2_twin = self.ax2.twinx()
                ax2_twin.spines['right'].set_position(('axes', 1.0))  # 将Y轴对齐到图表右侧
                
                # 绘制成交量柱状图
                self.ax2.bar(x_index, data['成交量'], width=0.6, color=colors, alpha=0.7)
                
                # 如果需要显示预测成交量
                if self.analysis_engine.should_draw_volume_prediction():
                    # 获取最新的成交量数据
                    latest_volume = data['成交量'].iloc[-1]
                    # 使用predict_final_volume方法计算预测成交量
                    predicted_volume = self.analysis_engine.predict_final_volume(latest_volume, self.analysis_engine.get_current_time_ratio())
                    
                    # 在最后一个位置绘制预测成交量柱形图
                    self.ax2.bar(x_index[-1], predicted_volume, width=0.6, color='#FFA500', alpha=0.3)  # 改为橙色
                
                # 在成交量面板左上角添加成交量值的文本标注
                last_volume = data['成交量'].iloc[-1]
                volume_text = f"{int(last_volume/10000)}万" if last_volume >= 10000 else str(int(last_volume))
                self.ax2.text(
                    0.01, 0.95,
                    f'成交量: {volume_text}',
                    transform=self.ax2.transAxes,
                    color='#666666',
                    fontsize=8,
                    verticalalignment='top',
                    bbox=dict(
                        facecolor='white',
                        alpha=0.5,
                        pad=3
                    )
                )
                
                
                
                
                # 设置成交量y轴的格式化器
                def volume_formatter(x, p):
                    """将成交量格式化为整数万为单位"""
                    return f"{int(x / 10000)}万" if x >= 10000 else str(int(x))
                
                self.ax2.yaxis.set_major_formatter(FuncFormatter(volume_formatter))

                # 绘制RSI指标
                self.ax3.plot(x_index, data['RSI6'], color='blue', label='RSI6', linewidth=1)
                self.ax3.plot(x_index, data['RSI12'], color='orange', label='RSI12', linewidth=1)
                self.ax3.plot(x_index, data['RSI24'], color='green', label='RSI24', linewidth=1)
                
                # 添加RSI的超买超卖线
                self.ax3.axhline(y=70, color='red', linestyle='--', alpha=0.5, linewidth=0.8)
                self.ax3.axhline(y=30, color='green', linestyle='--', alpha=0.5, linewidth=0.8)
                self.ax3.axhline(y=50, color='gray', linestyle='-', alpha=0.3, linewidth=0.5)
                
                # 添加RSI背景填充：50以下绿色，50以上红色，半透明0.2
                y_min, y_max = 0, 100
                self.ax3.axhspan(y_min, 50, color='#90EE90', alpha=0.2, zorder=0)  # 绿色背景，50以下
                self.ax3.axhspan(50, y_max, color='#FFB6C1', alpha=0.2, zorder=0)  # 红色背景，50以上
                
                # 设置RSI图表的Y轴范围
                self.ax3.set_ylim(0, 100)
                self.ax3.set_ylabel('RSI')
                # 在绘制MA均线后添加成本线绘制（指数不显示平均成本线）
                is_index = str(self.current_code or "") in ["1A0001", "000001"]
                if not is_index and self.analysis_engine.has_stock_cyq_data(str(self.current_code or "")) and '平均成本' in data.columns:
                    valid_cost = data['平均成本'].dropna()
                    if not valid_cost.empty:
                        print(f"开始绘制{self.period_mode}周期平均成本线...")
                        print(f"有效成本数据点数: {len(valid_cost)}")
                        # 找到有效数据的起始索引
                        start_idx = data.index.get_loc(valid_cost.index[0])
                        self.ax1.plot(x_index[start_idx:], valid_cost.values,
                                color='#FF69B4',  # 使用更醒目的颜色
                                linestyle='-',
                                linewidth=1.8,
                                alpha=0.8,
                                zorder=3)  # 确保显示在最上层
                        print("平均成本线绘制完成")
                        
                        # 如果强制刷新，打印调试信息
                        if getattr(self, '_force_refresh_cyq', False):
                            print(f"强制刷新模式: 平均成本线已更新")
                # 计算平均成本日涨幅（保留原始比例，指数不计算）
                if not is_index and '平均成本' in data.columns:
                    cost_change = data['平均成本'].pct_change() * 100  # 百分比变化
                    cost_change = cost_change.replace([np.inf, -np.inf], np.nan).ffill()

                    # 计算累计成本涨幅（只累加正涨幅，且过滤掉涨幅<0.5%的）
                    cumulative_positive_change = cost_change.copy()
                    cumulative_positive_change[cost_change < 1.1] = 0  # 将负涨幅和小于1%的涨幅设为0
                    cumulative_positive_change = cumulative_positive_change.cumsum()  # 累计求和

                    # 绘制成本涨幅线
                    self.ax5.plot(x_index, cost_change, 
                            color='#2E86C1', 
                            linewidth=1.2,
                            alpha=0.7)

                    # 累计正涨幅曲线与区域填充已移除，根据需求仅保留累积值标识

                    # 在图表左侧添加累计正涨幅标识
                    if not cumulative_positive_change.empty:
                        latest_cumulative = cumulative_positive_change.iloc[-1]
                        self.ax5.text(
                            0.02, 0.95,
                            f'累计正涨幅: {latest_cumulative:.2f}%',
                            transform=self.ax5.transAxes,
                            color='#E74C3C',
                            fontsize=8,
                            fontweight='bold',
                            verticalalignment='top',
                            bbox=dict(
                                facecolor='white',
                                alpha=0.8,
                                pad=5,
                                edgecolor='#E74C3C',
                                linewidth=1
                            )
                        )

                    # 填充日涨幅正负区域（透明度降低，避免与累计线重叠）
                    self.ax5.fill_between(x_index, cost_change, 0, 
                                    where=(cost_change >= 0), 
                                    facecolor='#FF6B6B', alpha=0.2)  # 浅红色填充正区域
                    self.ax5.fill_between(x_index, cost_change, 0,
                                    where=(cost_change < 0), 
                                    facecolor='#2ECC71', alpha=0.2)  # 绿色填充负区域

                    # 成本涨幅图信号点异步加载 - 先显示加载状态，然后异步加载数据
                    # 显示加载状态
                    self._show_cost_loading()
                    
                    # 设置基本的子图格式
                    self.ax5.set_ylabel('成本涨幅(%)', fontsize=8)
                    self.ax5.grid(True, axis='y', linestyle='--', alpha=0.3)

                    # 设置y轴不归一化
                    self.ax5.set_ylim(auto=True)
                    self.ax5.axhline(0, color='gray', linestyle='--', linewidth=0.8)
                    self.ax5.grid(True, axis='y', linestyle='--', alpha=0.3)

                # 隐藏ax3和ax5的x轴标签
                plt.setp(self.ax3.get_xticklabels(), visible=False)
                plt.setp(self.ax5.get_xticklabels(), visible=False)

                # 调整子图间距
                gs.update(hspace=0.08)  # 减小垂直间距

                # 设置x轴刻度和标签
                def format_date(x, p):
                    # 更严格的边界检查，确保x是整数且在有效范围内
                    if (trading_dates is not None and len(trading_dates) > 0 and 
                        isinstance(x, (int, float)) and x >= 0 and x < len(trading_dates)):
                        try:
                            # 确保x是整数且不超出边界
                            x_int = int(round(x))
                            if x_int >= len(trading_dates):
                                x_int = len(trading_dates) - 1
                            elif x_int < 0:
                                x_int = 0
                            
                            date = pd.Timestamp(trading_dates[x_int])
                            if self.period_mode == 'week':
                                return f"{date.year}-W{date.week}"
                            elif self.period_mode == 'month':
                                return date.strftime('%Y-%m')
                            return date.strftime('%Y-%m-%d')
                        except (IndexError, KeyError, ValueError) as e:
                            print(f"[DEBUG] format_date错误: {e}, x={x}, trading_dates_length={len(trading_dates)}")
                            return ''
                    return ''

                # 只显示三个时间点（开始、中间、结束）
                n_dates = len(trading_dates)
                tick_positions = [
                    0,                  # 开始位置
                    n_dates // 2,      # 中间位置
                    n_dates - 1        # 结束位置
                ]

                # 分开设置不同类型图表的x轴
                # 设置K线、成交量、KDJ、成本涨幅、MA5偏离度、筹码集中度、资金来源的x轴 (移除量比增幅)
                # 指数不显示筹码集中度图，所以ax4可能为None
                axes_to_format = [self.ax1, self.ax2, self.ax3, self.ax5, self.ax7, self.ax_fund]
                if self.ax4 is not None:
                    axes_to_format.append(self.ax4)
                for ax in axes_to_format:
                    ax.xaxis.set_major_formatter(FuncFormatter(format_date))
                    ax.set_xticks(tick_positions)
                    ax.set_xlim(-0.5, len(trading_dates) - 0.5)

                # 只在主K线图显示水平时间轴标签
                plt.setp(self.ax1.get_xticklabels(), rotation=0, ha='center')  # 修改为水平显示
                # 隐藏其他子图的时间轴标签
                plt.setp(self.ax2.get_xticklabels(), visible=False)
                plt.setp(self.ax3.get_xticklabels(), visible=False)
                plt.setp(self.ax5.get_xticklabels(), visible=False)
                # plt.setp(self.ax6.get_xticklabels(), visible=False)  # 量比增幅图已移除
                plt.setp(self.ax7.get_xticklabels(), visible=False)
                plt.setp(self.ax4.get_xticklabels(), visible=False)
                if self.ax_fund is not None:
                    plt.setp(self.ax_fund.get_xticklabels(), visible=False)

                # 添加仅水平网格（不绘制垂直网格）
                self.ax1.grid(True, axis='y', linestyle='--', alpha=0.3)
                self.ax2.grid(True, axis='y', linestyle='--', alpha=0.3)
                self.ax3.grid(True, axis='y', linestyle='--', alpha=0.3)
                self.ax5.grid(True, axis='y', linestyle='--', alpha=0.3)
                # self.ax6.grid(True, axis='y', linestyle='--', alpha=0.3)  # 量比增幅图已移除
                self.ax7.grid(True, axis='y', linestyle='--', alpha=0.3)
                self.ax4.grid(True, axis='y', linestyle='--', alpha=0.3)
                if self.ax_fund is not None:
                    self.ax_fund.grid(True, axis='y', linestyle='--', alpha=0.3)

                # 调整图例位置
                self.ax1.legend(
                    loc='upper left', 
                    bbox_to_anchor=(0.01, 0.99),
                    ncol=2,  # 分两列显示
                    fontsize=8,
                    columnspacing=0.8
                )

                # 设置标题时预留更多空间
                self.ax1.set_title(
                    f"{self.current_symbol_name} {self.current_code}",
                    pad=10,  # 增加标题与图表的距离
                    y=1.0    # 标题垂直位置
                )

                # RSI文本框位置微调
                if not data.empty:
                    last_rsi6 = data['RSI6'].iloc[-1]
                    last_rsi12 = data['RSI12'].iloc[-1]
                    last_rsi24 = data['RSI24'].iloc[-1]
                    rsi_text = f"RSI6:{last_rsi6:.1f} 12:{last_rsi12:.1f} 24:{last_rsi24:.1f}"
                    self.ax3.text(
                        0.01, 0.95, 
                        rsi_text,
                        transform=self.ax3.transAxes,
                        verticalalignment='top',
                        bbox=dict(
                            facecolor='white',
                            alpha=0.8,
                            pad=3  # 增加文本框内边距
                        )
                    )


                # 在绘制完其他图表后，添加筹码集中度图表（指数不显示筹码数据）
                is_index = str(self.current_code or "") in ["1A0001", "000001"]
                if not is_index and self.analysis_engine.has_stock_cyq_data(str(self.current_code or "")):
                    # 获取筹码数据 - 根据force_refresh状态决定是否强制刷新
                    try:
                        # 检查是否需要强制刷新筹码数据
                        force_refresh_cyq = getattr(self, '_force_refresh_cyq', False)
                        if force_refresh_cyq:
                            print(f"强制刷新筹码数据: {self.current_code}")
                            # 清除可能的缓存
                            if hasattr(ak, '_cache') and hasattr(ak._cache, 'clear'):
                                try:
                                    ak._cache.clear()
                                except:
                                    pass
                        
                        cyq_data = ak.stock_cyq_em(symbol=str(self.current_code or ""), adjust="qfq")
                        
                        # 重置强制刷新标志
                        if force_refresh_cyq:
                            self._force_refresh_cyq = False
                            
                    except Exception as e:
                        print(f"获取筹码数据失败: {str(e)}")
                        cyq_data = pd.DataFrame()
                    if not cyq_data.empty:
                        cyq_data['日期'] = pd.to_datetime(cyq_data['日期'])
                        cyq_data = cyq_data.set_index('日期')
                        
                        # 对齐数据时间范围
                        aligned_data = cyq_data.reindex(data.index, method='ffill')
                        
                        # 在K线图上绘制成本区间线和填充
                        # 90成本区间 - 黄色
                        self.ax1.plot(x_index, aligned_data['90成本-高'], 
                                     color='#FFD700',  # 金色
                                     linewidth=1,
                                     alpha=0.6,
                                     label='90%成本区间')
                        self.ax1.plot(x_index, aligned_data['90成本-低'],
                                     color='#9370DB',  # 中紫色
                                     linewidth=1,
                                     alpha=0.6)
                        
                        # 70成本区间 - 紫色
                        self.ax1.plot(x_index, aligned_data['70成本-高'],
                                     color='#9370DB',  # 中紫色
                                     linewidth=1,
                                     alpha=0.6,
                                     label='70%成本区间')
                        self.ax1.plot(x_index, aligned_data['70成本-低'],
                                     color='#9370DB',  # 中紫色
                                     linewidth=1,
                                     alpha=0.6)
                        
                        # 添加成本区间填充
                        # 高位区间填充
                        self.ax1.fill_between(list(x_index),
                                            aligned_data['70成本-高'].astype(float).tolist(),
                                            aligned_data['90成本-高'].astype(float).tolist(),
                                            color='#FFD700',  # 金色
                                            alpha=0.3)
                        
                        # 低位区间填充
                        self.ax1.fill_between(list(x_index),
                                            aligned_data['70成本-低'].astype(float).tolist(),
                                            aligned_data['90成本-低'].astype(float).tolist(),
                                            color='#9370DB',  # 中紫色
                                            alpha=0.3)
                
                # 计算并绘制聪明线和笨蛋线（对所有股票都显示，不依赖于筹码数据）
                # 计算3日价格涨幅指标
                price_change_3d = self._calculate_3day_price_change(data)
                
                # 计算3日实体涨幅指标（笨蛋线）
                entity_change_3d = self._calculate_3day_entity_change(data)
                
                # 计算3日聪明盈利指标（聪明线）
                smart_profit_3d = self._calculate_3day_smart_profit(data)
                
                # 绘制3日实体最差盈利图（笨蛋线 - 蓝色）
                self.ax4.plot(x_index, entity_change_3d, 
                             color='#4169E1',  # 皇家蓝色
                             label='笨蛋线（3日实体最差盈利）',
                             linewidth=1.5)
                
                # 绘制3日聪明盈利图（聪明线 - 绿色）
                self.ax4.plot(x_index, smart_profit_3d, 
                             color='#32CD32',  # 酸橙绿色
                             label='聪明线（3日聪明盈利）',
                             linewidth=1.5)
                
                # 红色线暂时隐藏，但保留计算代码
                # self.ax4.plot(x_index, price_change_3d, 
                #              color='#FF6347',  # 番茄红色
                #              label='3日价格最差盈利',
                #              linewidth=1.5)
                
                # 动态设置Y轴范围（考虑笨蛋线和聪明线的范围）
                all_values = pd.concat([entity_change_3d, smart_profit_3d])
                min_value = all_values.min()
                max_value = all_values.max()
                y_margin = max(abs(min_value), abs(max_value)) * 0.1  # 添加10%的边距
                self.ax4.set_ylim(
                    min_value - y_margin,
                    max_value + y_margin
                )
                
                # 添加零基准线
                self.ax4.axhline(y=0, color='#808080', linestyle='--', alpha=0.5, linewidth=1)
                
                # 背景填充：0%以下填充绿色，0%以上填充红色
                # 获取Y轴范围
                y_min, y_max = self.ax4.get_ylim()
                
                # 0%以下区域填充绿色（半透明0.2）
                self.ax4.axhspan(y_min, 0, color='#90EE90', alpha=0.2, zorder=0)
                
                # 0%以上区域填充红色（半透明0.2）
                self.ax4.axhspan(0, y_max, color='#FFB6C1', alpha=0.2, zorder=0)
                
                # 设置y轴格式化函数
                def price_change_formatter(x, p):
                    return f'{x*100:.2f}%'  # 显示百分比数值
                
                self.ax4.yaxis.set_major_formatter(FuncFormatter(price_change_formatter))
                
                # 添加网格
                self.ax4.grid(True, axis='y', linestyle='--', alpha=0.3)
                
                # 由于数值已直接显示在左侧标注中，这里不再显示图例
                # self.ax4.legend(loc='upper left',
                #                   bbox_to_anchor=(0.01, 0.99),
                #                   fontsize=8)
                
                # 设置x轴格式
                self.ax4.xaxis.set_major_formatter(FuncFormatter(format_date))
                self.ax4.set_xticks(tick_positions)
                self.ax4.set_xlim(-0.5, len(trading_dates) - 0.5)
                
                # 添加最新值标注（显示笨蛋线和聪明线数值，正确转换为百分比）
                last_entity_change = entity_change_3d.iloc[-1]
                last_smart_profit = smart_profit_3d.iloc[-1]
                self.ax4.text(
                    0.01, 0.95,
                    f'笨蛋线: {last_entity_change*100:.2f}%\n聪明线: {last_smart_profit*100:.2f}%',
                    transform=self.ax4.transAxes,
                    fontsize=8,
                    horizontalalignment='left',
                    verticalalignment='top',
                    bbox=dict(facecolor='white', alpha=0.8, pad=3)
                )
                
                # 保存axes引用
                self.ax1 = self.ax1
                self.ax2 = self.ax2
                self.ax3 = self.ax3
                self.ax4 = self.ax4  # 替换原来的ax_profit

                # 创建画布并显示
                self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
                self.chart_canvas.draw()
                canvas_widget = self.chart_canvas.get_tk_widget()
                canvas_widget.pack(fill=tk.BOTH, expand=True)
                
                # 绘制分时图对应日期的垂直贯穿线
                self._update_intraday_date_vertical_line()

                # 等待widget完成布局
                self.window.update_idletasks()

                # 固定画布大小
                if canvas_widget.winfo_exists():  # 再次检查widget是否存在
                    width = canvas_widget.winfo_width()
                    height = canvas_widget.winfo_height()
                    canvas_widget.configure(width=width, height=height)

                # 绑定鼠标事件
                self._bind_mouse_events()

                # 在这里绑定键盘事件
                self._bind_keyboard_events()

                # 在K线图之后添加指标分析（暂时不调用）
                # self.start_indicators_analysis()            

                # 量比增幅图表已移除


                # 在绘制布林带的部分修改垂直线绘制逻辑，使用信号标记来判断
                for i in range(len(data)):
                    # 检查当前位置是否有存储的警示信息
                    warning_text = data.iloc[i].get('warning_text', '')
                    
                    # 通过warning_text判断信号类型，而不是直接检查BBW指标
                    if warning_text and '布林顶向下' in warning_text:
                        # 获取当前点的布林上轨值
                        if 'BOLL_UPPER' in data.columns:
                            upper_band = data['BOLL_UPPER'].iloc[i]
                            
                            # 获取前20个交易日的最高价
                            start_idx = max(0, i-20)
                            prev_high = data['最高'].iloc[start_idx:i+1].max()
                            
                            # 绘制从布林上轨到前高点的垂直线
                            self.ax1.vlines(
                                x=x_index[i],
                                ymin=upper_band,
                                ymax=prev_high,
                                color='#4169E1',
                                linestyle='--',
                                linewidth=1,
                                alpha=0.8,
                                zorder=3
                            )
                            
                            # 在垂直线顶部添加标记点
                            self.ax1.plot(
                                x_index[i], 
                                prev_high,
                                'v',  # 倒三角形标记
                                color='#4169E1',
                                markersize=8,
                                alpha=0.8,
                                zorder=4
                            )
                    
                    # 检查布林底信号
                    elif warning_text and '布林底向上' in warning_text:
                        # 获取当前点的布林下轨值
                        if 'BOLL_LOWER' in data.columns:
                            lower_band = data['BOLL_LOWER'].iloc[i]
                            
                            # 获取前20个交易日的最低价
                            start_idx = max(0, i-20)
                            prev_low = data['最低'].iloc[start_idx:i+1].min()
                            
                            # 绘制从布林下轨到前低点的垂直线
                            self.ax1.vlines(
                                x=x_index[i],
                                ymin=prev_low,
                                ymax=lower_band,
                                color='#FF4500', 
                                linestyle='--',
                                linewidth=1,
                                alpha=0.8,
                                zorder=3
                            )
                            
                            # 在垂直线底部添加标记点
                            self.ax1.plot(
                                x_index[i], 
                                prev_low,
                                '^',  # 正三角形标记
                                color='#FF4500',
                                markersize=8,
                                alpha=0.8,
                                zorder=4
                            )

                # 在筹码集中度图之前添加MA5偏离度图
                # 计算MA5偏离度
                data['MA5'] = data['收盘'].rolling(window=5, min_periods=5).mean()
                data['MA5_UP_DEV'] = data.apply(lambda x: ((x['最高'] - x['MA5'])/x['MA5']*100) if x['最高'] > x['MA5'] else 0, axis=1)
                data['MA5_DOWN_DEV'] = data.apply(lambda x: ((x['最低'] - x['MA5'])/x['MA5']*100) if x['最低'] < x['MA5'] else 0, axis=1)
                
                # 绘制MA5偏离度图
                self.ax7.fill_between(x_index, data['MA5_UP_DEV'], 0, 
                                    where=(data['MA5_UP_DEV'] > 0),
                                    color='red', alpha=0.3, label='上偏离')
                self.ax7.fill_between(x_index, data['MA5_DOWN_DEV'], 0,
                                    where=(data['MA5_DOWN_DEV'] < 0),
                                    color='green', alpha=0.3, label='下偏离')
                
                # 设置y轴格式为百分比
                self.ax7.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:.1f}%'))
                
                # 添加网格和标签
                self.ax7.grid(True, axis='y', linestyle='--', alpha=0.3)
                self.ax7.set_ylabel('MA5偏离度')
                
                # 由于数值已直接显示在左侧标注中，这里不再显示图例
                # self.ax7.legend(
                #     loc='upper left',
                #     bbox_to_anchor=(0.01, 0.99),
                #     fontsize=8,
                #     framealpha=0.8,
                #     ncol=1
                # )
                
                # 添加最新值标注（移到左侧）
                last_up = data['MA5_UP_DEV'].iloc[-1]
                last_down = data['MA5_DOWN_DEV'].iloc[-1]
                self.ax7.text(
                    0.01, 0.95,
                    f'MA5偏离度 上: {last_up:.1f}%  下: {last_down:.1f}%',
                    transform=self.ax7.transAxes,
                    fontsize=8,
                    horizontalalignment='left',
                    verticalalignment='top',
                    bbox=dict(facecolor='white', alpha=0.8, pad=3)
                )
                
                # 隐藏MA5偏离度图的x轴标签
                plt.setp(self.ax7.get_xticklabels(), visible=False)

                # 资金来源子图异步加载 - 先显示加载状态，然后异步加载数据
                if self.ax_fund is not None:
                    # 显示加载状态
                    self._show_fund_loading()
                
                    # 设置基本的子图格式
                    self.ax_fund.set_ylabel('资金来源(股)', fontsize=8)
                    self.ax_fund.grid(True, axis='y', linestyle='--', alpha=0.3)
                            
                # 设置x轴格式
                def format_date(x, p):
                    # 更严格的边界检查，确保x是整数且在有效范围内
                    if (data is not None and not data.empty and len(x_index) > 0 and
                        isinstance(x, (int, float)) and x >= 0 and x < len(x_index)):
                        try:
                            # 确保x是整数且不超出边界
                            x_int = int(round(x))
                            if x_int >= len(data.index):
                                x_int = len(data.index) - 1
                            elif x_int < 0:
                                x_int = 0
                            
                            date = pd.Timestamp(data.index[x_int])
                            if self.period_mode == 'week':
                                return f"{date.year}-W{date.week}"
                            elif self.period_mode == 'month':
                                return date.strftime('%Y-%m')
                            return date.strftime('%Y-%m-%d')
                        except (IndexError, KeyError, ValueError) as e:
                            print(f"[DEBUG] format_date错误: {e}, x={x}, data_length={len(data) if data is not None else 0}")
                            return ''
                    return ''
                
                n_dates = len(x_index)
                tick_positions = [0, n_dates // 2, n_dates - 1]
                self.ax_fund.xaxis.set_major_formatter(FuncFormatter(format_date))
                self.ax_fund.set_xticks(tick_positions)
                self.ax_fund.set_xlim(-0.5, len(x_index) - 0.5)
                
                # 隐藏x轴标签
                plt.setp(self.ax_fund.get_xticklabels(), visible=False)

                # 启动异步加载任务 - 资金来源图和成本涨幅图信号点
                self._start_async_loading(data, x_index)

            except Exception as e:
                print(f"更新图表时出错: {str(e)}")

        except Exception as e:
            print(f"更新图表时出错: {str(e)}")

    def _bind_mouse_events(self):
        self.chart_canvas.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.chart_canvas.mpl_connect('button_press_event', self.on_click)
        self.chart_canvas.mpl_connect('axes_leave_event', self.on_leave)
        
    def on_mouse_move(self, event):
        """处理鼠标移动事件"""
        if not event.inaxes:
            return
        
        # 移除旧的十字线和文本
        self.remove_crosshair()
        
        # 确定当前面板
        if event.inaxes == self.ax1:
            self.current_panel = 'price'
            y_axis = self.ax1.yaxis
            y_format = '{:.3f}'
        elif event.inaxes == self.ax2:
            self.current_panel = 'volume'
            y_axis = self.ax2.yaxis
            y_format = lambda x: f'{x/10000:.2f}万'
        elif event.inaxes == self.ax3:
            self.current_panel = 'rsi'
            y_axis = self.ax3.yaxis
            y_format = '{:.1f}'
        elif event.inaxes == self.ax4:
            self.current_panel = 'score'
            y_axis = self.ax4.yaxis
            y_format = '{:.3f}'
        elif event.inaxes == self.ax5:
            self.current_panel = 'cost_change'
            y_axis = self.ax5.yaxis
            y_format = '{:.2f}%'  # 成本涨幅百分比格式
        elif hasattr(self, 'ax_fund') and event.inaxes == self.ax_fund:
            self.current_panel = 'fund'
            y_axis = self.ax_fund.yaxis
            # 根据单位切换格式
            if getattr(self, '_fund_use_shares', True):
                y_format = lambda x: f'{x/1e4:.2f}万股'
            else:
                y_format = lambda x: f'{x/1e6:.2f}百万元'
        # elif event.inaxes == self.ax6:  # 量比增幅图已移除
        #     self.current_panel = 'volume_change'
        #     y_axis = self.ax6.yaxis 
        #     y_format = '{:.2f}%'  # 量比增幅百分比格式
        elif event.inaxes == self.ax7:
            self.current_panel = 'ma5_deviation'
            y_axis = self.ax7.yaxis
            y_format = '{:.2f}%'  # 5日偏离度百分比格式                    
        else:
            return
        
        # 获取数据点
        x_data = int(round(event.xdata))
        if x_data < 0 or x_data >= len(self.current_data):
            return
        
        # 绘制垂直线（跨越所有面板）
        self.crosshair_lines = []
        for ax in [self.ax1, self.ax2, self.ax3, self.ax5, self.ax4] + ([self.ax_fund] if getattr(self, 'ax_fund', None) is not None else []):
            line = ax.axvline(x=x_data, color='gray', linestyle='--', alpha=0.5)
            self.crosshair_lines.append(line)
        
        # 绘制水平线（仅在当前面板）
        line = event.inaxes.axhline(y=event.ydata, color='gray', linestyle='--', alpha=0.5)
        self.crosshair_lines.append(line)
        
        # 显示坐标值
        self.crosshair_text = []
        
        # X轴坐标（时间）- 固定在K线图时间轴位置
        date = self.current_data.index[x_data]
        date_str = date.strftime('%Y-%m-%d')
        if self.period_mode == 'week':
            date_str = f"{date.year}-W{date.week}"
        elif self.period_mode == 'month':
            date_str = date.strftime('%Y-%m')
        
        text = self.ax1.text(x_data, self.ax1.get_ylim()[0], 
                            date_str,
                            ha='center', va='top',
                            bbox=dict(facecolor='white', alpha=0.8, pad=1))
        self.crosshair_text.append(text)
        
        # Y轴坐标值 - 在当前面板对应的Y轴位置
        if isinstance(y_format, str):
            y_str = y_format.format(event.ydata)
        else:
            y_str = y_format(event.ydata)

        # 添加警示信息显示逻辑
        if self.current_panel == 'cost_change' and hasattr(self, 'current_data'):
            x_data = int(round(event.xdata))
            if 0 <= x_data < len(self.current_data):
                warning_text = self.current_data.iloc[x_data].get('warning_text', '')
                if warning_text and warning_text != 'nan':
                    # 修改这里
                    # y_str = f"{y_str}\n{warning_text}"  <-- 原有逻辑
                    
                    # 新逻辑: 在图表顶部中间显示
                    # 多行彩色渲染（居中对齐，按字体动态行距，默认黑色）
                    lines = [ln for ln in str(warning_text).split('\n') if ln]
                    if lines and hasattr(self, 'chart_canvas') and self.chart_canvas:
                        fig = self.chart_canvas.figure
                        dpi = fig.get_dpi()
                        fig_h_in = fig.get_size_inches()[1]
                        axes_frac_h = self.ax5.get_position().height
                        axes_h_px = axes_frac_h * fig_h_in * dpi
                        font_pt = 8
                        text_h_px = font_pt * dpi / 72.0
                        line_gap = (text_h_px / axes_h_px) * 1.35
                        y_start = 0.95
                        # 背景块覆盖中部区域
                        block_height = len(lines) * line_gap + 0.02
                        bg_x = 0.05
                        bg_w = 0.90
                        bg_y = y_start - len(lines)*line_gap - 0.01
                        bg = Rectangle(
                            (bg_x, bg_y),
                            bg_w,
                            block_height,
                            transform=self.ax5.transAxes,
                            facecolor='dimgray',
                            alpha=0.8,
                            edgecolor='none'
                        )
                        self.ax5.add_patch(bg)
                        # 将背景加入可移除元素列表
                        if self.crosshair_lines is None:
                            self.crosshair_lines = []
                        self.crosshair_lines.append(bg)
                        for idx, line in enumerate(lines):
                            if line.startswith('机构净买') or line.startswith('散户净卖'):
                                fg = 'red'
                            elif line.startswith('机构净卖') or line.startswith('散户净买'):
                                fg = 'green'
                            elif line.startswith('游资净买'):
                                fg = 'orange'
                            elif line.startswith('游资净卖'):
                                fg = 'yellow'
                            else:
                                fg = 'black'
                            t = self.ax5.text(
                                0.5, y_start - idx*line_gap,
                                line,
                                ha='center', va='top',
                                transform=self.ax5.transAxes,
                                fontsize=font_pt,
                                color=fg,
                                zorder=101
                            )
                            self.crosshair_text.append(t)

        # 右侧数值提示（默认显示当前面板 y 值）
        right_text = y_str
        # 若为资金子图，拼接三路资金值（三行显示）
        if self.current_panel == 'fund' and self._fund_inst_series is not None and 0 <= x_data < len(self._fund_inst_series):
            inst_v = float(self._fund_inst_series[x_data])
            hot_v = float(self._fund_hot_series[x_data]) if self._fund_hot_series is not None else 0.0
            retail_v = float(self._fund_retail_series[x_data]) if self._fund_retail_series is not None else 0.0
            if self._fund_use_shares:
                fmt = lambda v: f'{v/1e4:.2f}万股'
            else:
                fmt = lambda v: f'{v/1e6:.2f}百万元'
            right_text = f'机：{fmt(inst_v)}\n游：{fmt(hot_v)}\n散：{fmt(retail_v)}'

        if self.current_panel == 'fund' and getattr(self, 'ax_fund', None) is not None:
            text = self.ax_fund.text(
                0.5, 0.98,
                right_text,
                transform=self.ax_fund.transAxes,
                ha='center', va='top',
                bbox=dict(facecolor='white', alpha=0.8, pad=1)
            )
            self.crosshair_text.append(text)
        else:
            text = event.inaxes.text(
                event.inaxes.get_xlim()[1], event.ydata,
                right_text,
                ha='left', va='center',
                bbox=dict(facecolor='white', alpha=0.8, pad=1)
            )
            self.crosshair_text.append(text)
        
        # 使用普通的draw方法重绘
        self.chart_canvas.draw()

    def remove_crosshair(self):
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
            
            # 使用draw_idle()代替draw()
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()
            
        except Exception as e:
            print(f"移除十字线时出错: {str(e)}")

    def on_leave(self, event):
        """处理鼠标离开事件"""
        self.remove_crosshair()
        self.chart_canvas.draw()

    def on_click(self, event):
        """处理鼠标点击事件"""
        if event.inaxes in [self.ax1, self.ax2, self.ax3, self.ax4, self.ax5]:
            # 获取点击位置对应的数据点
            x_data = int(round(event.xdata))
            if x_data < 0 or x_data >= len(self.current_data):
                return
            
            # 检查是否应该更新
            current_time = time_module.time()
            if (self._last_update_source == 'keyboard' and 
                current_time - self._last_update_time < 0.5):  # 500ms内不响应鼠标点击
                return
            
            # 更新当前选中索引
            self.current_index = x_data
            self._last_update_source = 'mouse'
            self._last_update_time = current_time
            
            # 获取对应的数据行
            data = self.current_data.iloc[x_data]
            date = self.current_data.index[x_data]
            
            # 存储当前选中数据
            self._current_selected_data = data
            self._current_selected_date = date
            
            # 更新信息显示
            display_data = self.get_formatted_display_data(data, date)
            self.update_info_table(display_data)
            
            # 更新雷达图
            self.update_radar_chart(date)

    def zoom_in(self):
        """放大显示范围"""
        min_time_range = 10
        if self.time_range > min_time_range:  # 最小显示20天
            # 取消之前的异步任务
            self._cancel_async_tasks()
            # 清除趋势检测缓存
            self._clear_trend_cache()
            self.time_range = max(min_time_range, int(self.time_range * 0.7))
            self.load_data_and_show()
            
    def zoom_out(self):
        """缩小显示范围"""
        if self.time_range < 365:  # 最大显示1年
            # 取消之前的异步任务
            self._cancel_async_tasks()
            # 清除趋势检测缓存
            self._clear_trend_cache()
            self.time_range = min(365, int(self.time_range * 1.5))
            self.load_data_and_show() 

    def zoom_last_trading_days(self, n: int = 20) -> None:
        """将时间轴缩放到最近 n 个交易日范围。"""
        try:
            if self.current_data is None or len(self.current_data.index) == 0:
                return
            # 取消之前的异步任务
            self._cancel_async_tasks()
            # 直接通过时间窗口参数控制
            self.time_range = max(1, int(n))
            self.load_data_and_show()
        except Exception as e:
            print(f"缩放到最近{n}个交易日失败: {str(e)}")

    def export_chart_data(self) -> None:
        """导出K线图数据"""
        try:
            if self.current_code is None:
                messagebox.showerror("导出失败", "没有可导出的数据")
                return
                
            merged_file = ExportService.export_chart_data(self.current_code)
            if merged_file:
                # 获取导出目录路径
                export_dir = os.path.dirname(merged_file)
                
                # 弹出成功消息并询问是否打开导出目录
                if messagebox.askyesno("导出成功", 
                                    f"数据已合并导出到: {merged_file}\n是否打开导出目录?"):
                    # 使用macOS的open命令打开文件夹
                    import subprocess
                    subprocess.run(['open', export_dir])
            else:
                messagebox.showerror("导出失败", "导出过程中发生错误")
                
        except Exception as e:
            messagebox.showerror("导出失败", f"导出过程中发生错误:\n{str(e)}")

    def get_visible_data(self):
        """获取当前显示范围的数据"""
        if not hasattr(self, "ax") or not self.ax:
            return pd.DataFrame()
        
        # 获取当前显示范围
        x_min, x_max = self.ax.get_xlim()
        
        # 转换为日期索引
        visible_range = self.data.index[int(x_min):int(x_max)]
        
        # 返回可见范围内的数据
        return self.data.loc[visible_range]

    def set_period(self, period):
        """设置周期"""
        # 取消之前的异步任务
        self._cancel_async_tasks()
        # 清除趋势检测缓存
        self._clear_trend_cache()
        
        self.period_mode = period
        config = self.period_config[period]
        self.time_range = int(config['range'] * config['default_zoom'])  # 应用默认缩放
        # 强制刷新数据，确保时间范围变化时重新计算和显示
        self.load_data_and_show(force_refresh=True)
        
        # 重置MA计算周期（可选）
        if period == 'week':
            self.ma_lines = [5, 10, 20]  # 5周/10周/20周均线
        elif period == 'month':
            self.ma_lines = [5, 10, 20]  # 5月/10月/20月均线
        else:
            self.ma_lines = [5, 10, 20]  # 恢复日线默认

    def create_info_table(self):
        """创建信息显示表格"""
        # 修改后的display_order
        display_order = [
            '日期', '开盘', '最高', '最低', '收盘',
            '涨跌幅', '振幅', '成交量', '成交额',
            '换手率',  # 新增这两行
            'MA5', 'MA10', 'MA20',
            'RSI6', 'RSI12', 'RSI24',
            '平均成本',  # 新增位置
            '得分',
            '量价相关性', 
            '筹码稳定度',
            '套利影响',
            '量能健康度',
            '动量趋势',
            '波动质量'
        ]
        
        # 创建表格，增加change列
        columns = ('item', 'value', 'change')
        self.info_table = ttk.Treeview(
            self.info_frame, 
            columns=columns,
            show='tree',  # 改为tree模式,不显示列头
            height=15
        )
        
        # 设置自适应列宽
        self.info_table.column('#0', width=0, stretch=tk.NO)  # 隐藏树形图标列
        self.info_table.column('item', width=120, stretch=tk.YES)  # 项目列可拉伸
        self.info_table.column('value', width=100, stretch=tk.YES)  # 数值列可拉伸
        self.info_table.column('change', width=80, stretch=tk.YES)  # 增幅列可拉伸
        
        # 添加初始行（新增得分指标）
        items = [
            '日期', '开盘', '最高', '最低', '收盘',
            '涨跌幅', '振幅', '成交量', '成交额',
            'MA5', 'MA10', 'MA20',
            'RSI6', 'RSI12', 'RSI24',  # 只保留单独的RSI值
            '得分',
            '量价相关性', 
            '筹码稳定度',
            '套利影响',
            '量能健康度',
            '动量趋势',
            '波动质量'
        ]
        
        # 初始化表格内容
        for item in items:
            self.info_table.insert('', tk.END, values=(item, '-', '-'))
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(
            self.info_frame, 
            orient=tk.VERTICAL, 
            command=self.info_table.yview
        )
        self.info_table.configure(yscrollcommand=scrollbar.set)
        
        # 放置表格和滚动条
        self.info_table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 移除分隔线
        # ttk.Separator(self.info_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # 添加备忘录框架
        memo_frame = ttk.LabelFrame(self.info_frame, text="备忘录")
        memo_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建备忘录文本框，调整字体大小
        self.memo_text = scrolledtext.ScrolledText(
            memo_frame,
            wrap=tk.WORD,
            width=30,
            height=10,
            font=('Arial', 12)  # 调整字体大小为12
        )
        self.memo_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 添加底部状态栏
        status_frame = ttk.Frame(memo_frame)
        status_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # 调整最后修改时间标签的字体大小
        self.last_modified_label = ttk.Label(
            status_frame, 
            text="", 
            font=('Arial', 10),  # 调整字体大小为10
            foreground='gray'
        )
        self.last_modified_label.pack(side=tk.LEFT)
        
        # 添加保存按钮
        save_btn = ttk.Button(
            status_frame, 
            text="保存", 
            command=self.save_memo,
            width=10
        )
        save_btn.pack(side=tk.RIGHT)
        
        # 绑定自动保存事件
        self.memo_text.bind('<FocusOut>', lambda e: self.save_memo())

    def update_info_table(self, data=None):
        """更新信息表格"""
        # 检查是否应该更新
        if (self._last_update_source == 'keyboard' and 
            hasattr(self, '_current_selected_data')):
            # 使用当前索引的数据
            data = self.get_formatted_display_data(
                self.current_data.iloc[self.current_index],
                self.current_data.index[self.current_index]
            )
        elif data is None and hasattr(self, '_current_selected_data'):
            data = self.get_formatted_display_data(
                self._current_selected_data,
                self._current_selected_date
            )
        
        # 获取上一个交易日的数据和指标
        prev_data = None
        prev_indicators = None
        if self.current_index is not None and self.current_index > 0:
            # 获取上一个交易日的基础数据
            prev_data = self.get_formatted_display_data(
                self.current_data.iloc[self.current_index - 1],
                self.current_data.index[self.current_index - 1]
            )
            
            # 获取上一个交易日的指标数据
            prev_date = self.current_data.index[self.current_index - 1]
            prev_data_subset = self.current_data.loc[:prev_date]
            if self._validate_data_format(prev_data_subset):
                prev_indicators, prev_market_intent = self.analysis_engine.get_all_indicators (
                    code=self.current_code,
                    data=prev_data_subset,
                    end_date=prev_date.strftime('%Y-%m-%d')
                )
        
        # 清除现有表格数据
        self.info_table.delete(*self.info_table.get_children())
        
        # 添加标题行
        self.info_table.insert("", "end", values=('指标分析', '', ''))
        
        
        # 修改calculate_change函数中的返回格式
        def calculate_change(current, previous, key):
            """修改涨跌幅计算函数"""
            try:
                # 处理带单位的数值（如"万"）
                unit_multiplier = 1
                if '万' in str(current[key]):
                    unit_multiplier = 10000
                if '%' in str(current[key]):
                    unit_multiplier = 1  # 百分比单独处理
                
                curr_val = float(str(current[key]).replace('万', '').replace('%', '')) * unit_multiplier
                prev_val = float(str(previous[key]).replace('万', '').replace('%', '')) * unit_multiplier
                
                # 处理平均成本没有单位的情况
                if key == '平均成本':
                    unit_multiplier = 1
                
                if prev_val == 0:
                    return '-'
                change = ((curr_val - prev_val) / prev_val) * 100
                return f"{change:.2f}"
            except (ValueError, TypeError, KeyError):
                return '-'
        
        # 填充新数据（合并K线数据和雷达图指标）
        # 判断是否为指数，指数不显示平均成本
        is_index = str(self.current_code or "") in ["1A0001", "000001"]
        
        merged_data = {
            **data,
            '平均成本': f"{data.get('平均成本', '-')}" if not is_index else '-',
            'BBW': f"{data.get('BBW', '-')}",
            '得分': f"{self._current_indicators.get('profit_score', 0):.3f}",
            '量价相关性': f"{self._current_indicators.get('volume_price_correlation', 0):.3f}",
            '筹码稳定度': f"{self._current_indicators.get('holding_stability', 0):.3f}",
            '套利影响': f"{self._current_indicators.get('arbitrage_impact', 0):.3f}",
            '量能健康度': f"{self._current_indicators.get('volume_health', 0):.3f}",
            '动量趋势': f"{self._current_indicators.get('momentum_trend', 0):.3f}",
            '波动质量': f"{self._current_indicators.get('volatility_quality', 0):.3f}"
        }
        
        # 创建包含上一个交易日指标的数据字典
        prev_merged_data = None
        if prev_data and prev_indicators:
            prev_merged_data = {
                **prev_data,  # 原有K线数据
                '得分': f"{prev_indicators.get('profit_score', 0):.3f}",  # 添加上一个时间点的得分
                '量价相关性': f"{prev_indicators.get('volume_price_correlation', 0):.3f}",
                '筹码稳定度': f"{prev_indicators.get('holding_stability', 0):.3f}",
                '套利影响': f"{prev_indicators.get('arbitrage_impact', 0):.3f}",
                '量能健康度': f"{prev_indicators.get('volume_health', 0):.3f}",
                '动量趋势': f"{prev_indicators.get('momentum_trend', 0):.3f}",
                '波动质量': f"{prev_indicators.get('volatility_quality', 0):.3f}"
            }
        
        # 修改display_order,删除BBW变动率
        display_order = [
            '日期', '开盘', '最高', '最低', '收盘',
            '涨跌幅', '振幅', '成交量', '成交额',
            '换手率',  # 新增这两行
            'MA5', 'MA10', 'MA20',
            'RSI6', 'RSI12', 'RSI24',  # 只保留单独的RSI值
            '平均成本',  # 新增字段
            'BBW',       # BBW指标(包含变动率)
            '得分',
            '量价相关性', 
            '筹码稳定度',
            '套利影响',
            '量能健康度',
            '动量趋势',
            '波动质量'
        ]
        
        for key in display_order:
            value = merged_data.get(key, '-')
            # 特殊处理百分比显示
            if key in ['涨跌幅', '振幅'] and value != '-':
                value = f"{float(value):.3f}%"
            # 计算增幅
            change = calculate_change(merged_data, prev_merged_data, key) if prev_merged_data else '-'
            self.info_table.insert("", "end", values=(key, value, change))

        # 自动调整列宽
        def auto_size_columns():
            font = tkfont.Font()
            for col in self.info_table['columns']:
                max_len = max(
                    [len(str(self.info_table.set(item, col))) for item in self.info_table.get_children()] +
                    [len(str(self.info_table.heading(col)['text']))]
                )
                # 根据字体宽度计算列宽，增加10像素缓冲
                self.info_table.column(col, width=int(font.measure("0"*max_len) * 0.8) + 10)
        
        auto_size_columns()

        # 更新主力意图图表
        # if self.market_intent:
        #     self.intent_chart.update_data(self.market_intent)

        # 确保在更新主力意图图表前先获取数据
        # try:
        #     if self.current_data is not None and len(self.current_data) > 0:
        #         # 获取当前选中日期的数据子集
        #         selected_date = self.current_data.index[-1]  # 默认使用最新日期
        #         if self._current_selected_date is not None:
        #             selected_date = self._current_selected_date
                
        #         data_subset = self.current_data.loc[:selected_date]
                
        #         # 计算主力意图数据
        #         if self._validate_data_format(data_subset):
        #             intent_data = self.analysis_engine._calculate_market_intent(data_subset)
        #             if intent_data:
        #                 # 更新到当前指标中
        #                 if not self._current_indicators:
        #                     self._current_indicators = {}
        #                 self.market_intent = intent_data
                        
        #                 # 更新图表
        #                 self.intent_chart.update_data(intent_data)
        #             else:
        #                 print("无法计算主力意图数据")
        #         else:
        #             print("数据格式验证失败")
        # except Exception as e:
        #     print(f"更新主力意图数据时出错: {str(e)}")

    def calculate_rsi(self, df, periods=[6, 12, 24]):
        """计算RSI指标，支持多个周期（使用指数移动平均）"""
        try:
            start_time = time_module.time()
            
            # 计算价格变化
            df['price_change'] = df['收盘'].diff()
            
            # 分别计算每个周期的RSI
            for period in periods:
                # 计算上涨和下跌
                gains = df['price_change'].where(df['price_change'] > 0, 0)
                losses = -df['price_change'].where(df['price_change'] < 0, 0)
                
                # 使用指数移动平均（EMA）计算平均上涨和下跌
                alpha = 1.0 / period
                avg_gains = gains.ewm(alpha=alpha, adjust=False).mean()
                avg_losses = losses.ewm(alpha=alpha, adjust=False).mean()
                
                # 计算相对强弱
                rs = avg_gains / avg_losses
                rsi = 100 - (100 / (1 + rs))
                
                # 处理无效值
                rsi = rsi.replace([np.inf, -np.inf], np.nan).fillna(50)
                
                # 将RSI值限制在0-100范围内
                rsi = rsi.clip(0, 100)
                
                # 添加到数据框
                df[f'RSI{period}'] = rsi
            
            # 删除中间计算列
            df = df.drop(['price_change'], axis=1)
            
            cleanup_time = time_module.time()
            print(f"RSI - 总计算耗时: {(cleanup_time - start_time):.3f}秒")
            print("-" * 30)
            
            return df
            
        except Exception as e:
            print(f"计算RSI指标时发生错误: {str(e)}")
            return df

    def calculate_kdj(self, df, n=9, m1=3, m2=3):
        """计算KDJ指标"""
        try:
            start_time = time_module.time()
            
            # 计算N日内的最高价和最低价
            df['low_n'] = df['最低'].rolling(window=n).min()
            df['high_n'] = df['最高'].rolling(window=n).max()
            
            rolling_time = time_module.time()
            print(f"KDJ - 计算最高最低价耗时: {(rolling_time - start_time):.3f}秒")
            
            # 计算RSV
            df['RSV'] = (df['收盘'] - df['low_n']) / (df['high_n'] - df['low_n']) * 100
            
            rsv_time = time_module.time()
            print(f"KDJ - 计算RSV耗时: {(rsv_time - rolling_time):.3f}秒")
            
            # 计算K、D、J值
            df['K'] = df['RSV'].ewm(alpha=1/m1, adjust=False).mean()
            df['D'] = df['K'].ewm(alpha=1/m2, adjust=False).mean()
            df['J'] = 3 * df['K'] - 2 * df['D']
            
            kdj_time = time_module.time()
            print(f"KDJ - 计算KDJ值耗时: {(kdj_time - rsv_time):.3f}秒")
            
            # 删除中间计算列
            df = df.drop(['low_n', 'high_n', 'RSV'], axis=1)
            
            # 处理无效值
            df[['K', 'D', 'J']] = df[['K', 'D', 'J']].fillna(np.nan)
            
            cleanup_time = time_module.time()
            print(f"KDJ - 清理数据耗时: {(cleanup_time - kdj_time):.3f}秒")
            print(f"KDJ - 总计算耗时: {(cleanup_time - start_time):.3f}秒")
            print("-" * 30)
            
            return df
            
        except Exception as e:
            print(f"计算KDJ指标时发生错误: {str(e)}")
            return df



    def start_indicators_analysis(self):
        """启动指标分析任务"""
        def analysis_task():
            try:
                # 获取分析结果
                indicators = self.analysis_engine.get_all_indicators(
                    code=self.current_code,
                    data=self.current_data
                )[0]
                # 更新雷达图（如果存在）
                if self.window and self.window.winfo_exists() and self.radar_chart is not None:
                    self.window.after(0, lambda: self.radar_chart.update_data(indicators))
            except Exception as e:
                print(f"指标分析失败: {str(e)}")
                if self.radar_chart is not None:
                    self.window.after(0, lambda err=str(e): self.radar_chart.show_error(err))
            finally:
                self.is_analyzing_indicators = False
        
        threading.Thread(target=analysis_task, daemon=True).start()

    def get_formatted_display_data(self, data: pd.Series, date: pd.Timestamp) -> Dict:
        """格式化显示数据"""
        try:
            # 判断是否为指数
            is_index = str(self.current_code or "") in ["1A0001", "000001"]
            formatted_data = {
                '日期': date.strftime('%Y-%m-%d'),
                '开盘': f"{data['开盘']:.3f}",
                '最高': f"{data['最高']:.3f}",
                '最低': f"{data['最低']:.3f}",
                '收盘': f"{data['收盘']:.3f}",
                '平均成本': f"{data['平均成本']:.3f}",
                'BBW': f"{data['BBW']:.3f}",
                '涨跌幅': f"{data.get('涨跌幅', '-')}",
                '振幅': f"{data.get('振幅', '-')}",
                '成交量': f"{data['成交量']/10000:.2f}万",
                '成交额': f"{data.get('成交额', '-')}",
                '换手率': f"{data.get('换手率', 0):.2f}%",
                'MA5': f"{data.get('MA5', '-'):.3f}",
                'MA10': f"{data.get('MA10', '-'):.3f}",
                'MA20': f"{data.get('MA20', '-'):.3f}",
                'MA250': f"{data.get('MA250', '-'):.3f}",  # 添加年线
                'RSI6': f"{data.get('RSI6', 0):.1f}",
                'RSI12': f"{data.get('RSI12', 0):.1f}",
                'RSI24': f"{data.get('RSI24', 0):.1f}"
            }
            
            # 添加筹码属性（指数不添加筹码属性）
            if not is_index:
                for attr in self.chip_attributes:
                    value = data.get(attr['column'], attr['default'])
                    if not pd.isna(value):
                        formatted_data[attr['name']] = f"{value:{attr['format']}}"
                    else:
                        formatted_data[attr['name']] = '-'
            
            # 计算主力区间和散户区间
            if all(key in data for key in ['70成本-低', '90成本-低', '70成本-高', '90成本-高', '收盘']):
                current_price = data['收盘']
                main_range = (data['70成本-低'] - data['90成本-低']) / current_price
                retail_range = (data['90成本-高'] - data['70成本-高']) / current_price
                
                formatted_data['主力区间'] = f"{main_range:.4f}"
                formatted_data['散户区间'] = f"{retail_range:.4f}"
            else:
                formatted_data['主力区间'] = '-'
                formatted_data['散户区间'] = '-'
            
            return formatted_data
            
        except Exception as e:
            print(f"格式化显示数据时出错: {str(e)}")
            return {}

    def show_latest_trading_data(self):
        """显示最新交易日数据"""
        try:
            if self.current_data is None or self.current_data.empty:
                return
            
            # 获取最新的数据行
            latest_data = self.current_data.iloc[-1]
            latest_date = self.current_data.index[-1]
            
            # 使用统一的格式化方法
            display_data = self.get_formatted_display_data(latest_data, latest_date)
            
            # 更新信息表格
            if display_data:
                self.update_info_table(display_data)
            
        except Exception as e:
            print(f"显示最新交易日数据时出错: {str(e)}")

    def update_radar_chart(self, selected_date):
        """根据选中日期更新雷达图"""
        if self.is_analyzing_indicators:
            return
            
        self.is_analyzing_indicators = True
        self.indicators_progress = 0
        
        # 检查雷达图是否存在，如果不存在则跳过雷达图相关操作
        if self.radar_chart is None:
            print("雷达图组件已移除，跳过雷达图更新")
            self.is_analyzing_indicators = False
            return
        
        # 在雷达图区域显示加载提示
        self.radar_chart.show_loading("分析中...")
        
        def analysis_task():
            try:
                # 截取到选中日期的数据
                data_subset = self.current_data.loc[:selected_date]
                
                # 验证数据格式
                if not self._validate_data_format(data_subset):
                    raise ValueError("数据格式校验失败")
                
                # 直接获取分析结果
                indicators, market_intent = self.analysis_engine.get_all_indicators(
                    code=self.current_code,
                    data=data_subset,
                    end_date=selected_date.strftime('%Y-%m-%d')
                )
                self._current_indicators = indicators
                
                # 在主线程更新雷达图（如果存在）
                if self.window and self.window.winfo_exists():
                    if self.radar_chart is not None:
                        self.window.after(0, lambda: self.radar_chart.update_data(indicators))
                        self.window.after(0, lambda: self.radar_chart.hide_loading())
                    self.window.after(0, self.update_info_table)
                
            except Exception as e:
                print(f"指标分析失败: {str(e)}")
                if self.radar_chart is not None:
                    self.window.after(0, lambda err=str(e): self.radar_chart.show_error(err))
            finally:
                self.is_analyzing_indicators = False
        
        threading.Thread(target=analysis_task, daemon=True).start()

    def _validate_data_format(self, data):
        """验证数据格式是否符合分析引擎要求"""
        required_columns = ['开盘', '最高', '最低', '收盘', '成交量']
        return all(col in data.columns for col in required_columns)

    def _bind_keyboard_events(self):
        """绑定键盘事件"""
        # 使用chart_canvas的widget来绑定键盘事件
        canvas_widget = self.chart_canvas.get_tk_widget()
        canvas_widget.bind('<Left>', self._on_left_key)
        canvas_widget.bind('<Right>', self._on_right_key)
        # 确保canvas可以接收键盘焦点
        canvas_widget.configure(takefocus=1)
        
        # 添加缩放快捷键
        canvas_widget.bind('<Command-minus>', lambda e: self.zoom_out())  # Command + '-' 缩小
        canvas_widget.bind('<Command-equal>', lambda e: self.zoom_in())   # Command + '=' 放大
        # Command + '0' 缩放到最近30个交易日
        canvas_widget.bind('<Command-0>', lambda e: self.zoom_last_trading_days(20))

    def _on_left_key(self, event):
        """处理左键事件"""
        if not self.current_data is None and len(self.current_data) > 0:
            if self.current_index is None:
                self.current_index = len(self.current_data) - 1
            elif self.current_index > 0:
                self.current_index -= 1
                self._last_update_source = 'keyboard'  # 标记更新来源
                self._last_update_time = time_module.time()
                self._update_by_index(self.current_index)

    def _on_right_key(self, event):
        """处理右键事件"""
        if not self.current_data is None and len(self.current_data) > 0:
            if self.current_index is None:
                self.current_index = 0
            elif self.current_index < len(self.current_data) - 1:
                self.current_index += 1
                self._last_update_source = 'keyboard'  # 标记更新来源
                self._last_update_time = time_module.time()
                self._update_by_index(self.current_index)

    def _update_by_index(self, index):
        """根据索引更新显示"""
        if self.current_data is None or len(self.current_data) == 0:
            return
            
        x = self._get_x_coordinate(index)
        # 获取对应数据点的中间价作为y坐标
        y = (self.current_data.iloc[index]['最高'] + self.current_data.iloc[index]['最低']) / 2
        # 使用蓝色虚线绘制十字线
        self._draw_crosshair(x, y, is_keyboard=True)
        
        # 获取当前日期并更新数据
        current_date = self.current_data.index[index]
        self._current_selected_date = current_date
        self._current_selected_data = self.current_data.iloc[index]
        
        # 更新显示数据和雷达图
        display_data = self.get_formatted_display_data(self._current_selected_data, current_date)
        self.update_info_table(display_data)
        
        # 添加数据有效性检查
        if not pd.isnull(current_date) and not self.current_data.iloc[index].isnull().any():
            self.update_radar_chart(current_date)
        else:
            print("检测到无效数据，跳过更新")

    def _draw_crosshair(self, x, y, is_keyboard=False):
        """绘制十字线"""
        try:
            # 移除旧的十字线和文本
            self.remove_crosshair()
            
            if not hasattr(self, 'ax1') or self.ax1 is None:
                return
            
            # 获取当前图表的边界
            x_min, x_max = self.ax1.get_xlim()
            y_min, y_max = self.ax1.get_ylim()
            
            # 创建十字线和文本时使用固定的zorder确保层级关系
            self.crosshair_lines = []
            for ax in [self.ax1, self.ax2, self.ax3, self.ax5, self.ax4]:
                line = ax.axvline(x=x, color='blue' if is_keyboard else 'gray', 
                                linestyle='--' if is_keyboard else '-', alpha=0.5,
                                zorder=100)  # 设置较高的zorder确保显示在数据之上
                self.crosshair_lines.append(line)
            
            # 水平线只在K线图面板显示
            line = self.ax1.axhline(y=y, color='blue' if is_keyboard else 'gray',
                                   linestyle='--' if is_keyboard else '-', alpha=0.5,
                                   zorder=100)
            self.crosshair_lines.append(line)
            
            # 显示坐标值
            self.crosshair_text = []
            
            # 获取对应的日期
            x_index = int(round(x))
            if 0 <= x_index < len(self.current_data):
                date = self.current_data.index[x_index]
                date_str = date.strftime('%Y-%m-%d')
                if self.period_mode == 'week':
                    date_str = f"{date.year}-W{date.week}"
                elif self.period_mode == 'month':
                    date_str = date.strftime('%Y-%m')
                
                # 调整日期文本位置,确保不被遮挡
                text = self.ax1.text(
                    x, self.ax1.get_ylim()[0],
                    date_str,
                    ha='center', 
                    va='bottom',  # 改为底部对齐
                    bbox=dict(
                        facecolor='white',
                        alpha=0.8,
                        pad=2,  # 增加内边距
                        edgecolor='none'
                    ),
                    zorder=101,
                    transform=self.ax1.transData  # 使用数据坐标系
                )
                self.crosshair_text.append(text)
                
                # 调整价格文本位置
                text = self.ax1.text(
                    self.ax1.get_xlim()[1], y,
                    f"{y:.3f}",
                    ha='right',  # 改为右对齐
                    va='center',
                    bbox=dict(
                        facecolor='white',
                        alpha=0.8,
                        pad=2,
                        edgecolor='none'
                    ),
                    zorder=101,
                    transform=self.ax1.transData
                )
                self.crosshair_text.append(text)
            
                # 在成本涨幅面板添加警示信息显示（居中对齐，按字体动态行距，默认黑色）
                warning_text = self.current_data.iloc[x_index].get('warning_text', '')
                if warning_text and hasattr(self, 'chart_canvas') and self.chart_canvas:
                    lines = [ln for ln in str(warning_text).split('\n') if ln]
                    if lines:
                        fig = self.chart_canvas.figure
                        dpi = fig.get_dpi()
                        fig_h_in = fig.get_size_inches()[1]
                        axes_frac_h = self.ax5.get_position().height
                        axes_h_px = axes_frac_h * fig_h_in * dpi
                        font_pt = 8
                        text_h_px = font_pt * dpi / 72.0
                        line_gap = (text_h_px / axes_h_px) * 1.6
                        y_start = 0.93
                        block_height = len(lines) * line_gap + 0.02
                        bg_x = 0.05
                        bg_w = 0.90
                        bg_y = y_start - len(lines)*line_gap - 0.01
                        bg = Rectangle(
                            (bg_x, bg_y),
                            bg_w,
                            block_height,
                            transform=self.ax5.transAxes,
                            facecolor='dimgray',
                            alpha=0.8,
                            edgecolor='none',
                            zorder=100
                        )
                        self.ax5.add_patch(bg)
                        if self.crosshair_lines is None:
                            self.crosshair_lines = []
                        self.crosshair_lines.append(bg)
                        for idx, line in enumerate(lines):
                            if line.startswith('机构净买') or line.startswith('散户净卖'):
                                fg = 'red'
                            elif line.startswith('机构净卖') or line.startswith('散户净买'):
                                fg = 'green'
                            elif line.startswith('游资净买'):
                                fg = 'orange'
                            elif line.startswith('游资净卖'):
                                fg = 'yellow'
                            else:
                                fg = 'black'
                            t = self.ax5.text(
                                0.5, y_start - idx*line_gap,
                                line,
                                ha='center',
                                va='top',
                                transform=self.ax5.transAxes,
                                fontsize=font_pt,
                                color=fg,
                                zorder=101
                            )
                            self.crosshair_text.append(t)
            
            # 使用draw_idle()代替draw(),避免完整重绘
            self.chart_canvas.draw_idle()
            
        except Exception as e:
            print(f"绘制十字线时出错: {str(e)}")

    def _get_x_coordinate(self, index):
        """将数据索引转换为画布x坐标"""
        if not self.current_data.empty:
            # 获取数据范围
            x_min, x_max = self.ax1.get_xlim()
            # 计算每个数据点的宽度
            bar_width = (x_max - x_min) / len(self.current_data)
            # 计算对应索引的x坐标中心点
            return x_min + (index + 0.5) * bar_width
        return 0

    def _get_index_from_x(self, x):
        """将x坐标转换为数据索引"""
        if not self.current_data.empty:
            # 获取数据范围
            x_min, x_max = self.ax1.get_xlim()
            # 计算每个数据点的宽度
            bar_width = (x_max - x_min) / len(self.current_data)
            # 计算对应的索引
            return int((x - x_min) // bar_width)
        return 0

    def on_closing(self):
        """窗口关闭处理"""
        # 取消所有异步任务
        self._cancel_async_tasks()
        
        # 销毁分时窗口
        if hasattr(self, '_intraday_window') and self._intraday_window is not None:
            self._intraday_window.destroy()
            self._intraday_window = None
        
        WindowManager.setup_window_close(self.window)  # 关闭前的清理
        self.window.destroy()
        self.window = None

    def refresh_data(self, event=None):
        """刷新最新数据"""
        if self.is_loading:
            return
        
        # 取消之前的异步任务
        self._cancel_async_tasks()
        # 清除趋势检测缓存
        self._clear_trend_cache()
        
        self.is_loading = True
        try:
            # 修改后的刷新逻辑，直接强制重新加载数据
            self.load_data_and_show(force_refresh=True)
            
            # 更新窗口标题显示刷新时间
            if self.window and self.window.winfo_exists():
                self.window.title(
                    f"{self.current_symbol_name}({self.current_code}) - K线图 " 
                    f"[最后更新: {datetime.now().strftime('%H:%M:%S')}]"
                )
        except Exception as e:
            messagebox.showerror("刷新错误", f"数据刷新失败: {str(e)}")
        finally:
            self.is_loading = False

    def _adjust_zoom(self, factor):
        """实际缩放逻辑"""
        if hasattr(self, 'ax1'):
            xlim = self.ax1.get_xlim()
            center = np.mean(xlim)
            new_width = (xlim[1] - xlim[0]) * factor
            self.ax1.set_xlim(center - new_width/2, center + new_width/2)
            self.canvas.draw()

    def update_loading_progress(self, current: int, total: int):
        """
        更新加载进度显示（线程安全）
        :param current: 当前进度
        :param total: 总数
        """
        if hasattr(self, 'loading_label'):
            progress = int((current / total) * 100)
            # 使用after方法确保在主线程更新UI
            self.loading_label.after(0, lambda: self.loading_label.configure(text=f"{progress}%"))

    # 添加创建月度图表的方法
    def create_monthly_chart(self, monthly_data: dict, year_range: str, market_data: dict = None):
        """创建月度涨幅图表"""
        # 检查是否为退市股票，如果是则跳过计算
        if str(self.current_code).startswith(('40', '42')):
            return
            
        # 清空现有图表
        if hasattr(self, 'monthly_ax'):
            self.monthly_ax.clear()
        
        # 创建月度图表区域
        if not hasattr(self, 'monthly_ax'):
            # 使用简单的subplot创建，不依赖gs
            self.monthly_ax = self.figure.add_subplot(3, 1, 3)  # 第三行，第一列
        
        try:
            # 准备数据
            months = list(monthly_data.keys())
            returns = list(monthly_data.values())
            
            # 创建柱状图
            bars = self.monthly_ax.bar(months, returns, color='skyblue', alpha=0.7)
            
            # 设置颜色：正收益为绿色，负收益为红色
            for bar, return_val in zip(bars, returns):
                if return_val > 0:
                    bar.set_color('lightgreen')
                elif return_val < 0:
                    bar.set_color('lightcoral')
            
            # 设置标题和标签
            self.monthly_ax.set_title(f'月度涨幅分布 ({year_range})', fontsize=8)
            self.monthly_ax.set_xlabel('月份')
            self.monthly_ax.set_ylabel('涨幅 (%)')
            
            # 旋转x轴标签以避免重叠
            self.monthly_ax.tick_params(axis='x', rotation=45)
            
            # 添加网格
            self.monthly_ax.grid(True, alpha=0.3)
            
            # 添加零线
            self.monthly_ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
            
            # 在柱状图上添加数值标签
            for i, (month, return_val) in enumerate(zip(months, returns)):
                self.monthly_ax.text(i, return_val + (0.5 if return_val >= 0 else -0.5), 
                                   f'{return_val:.1f}%', 
                                   ha='center', va='bottom' if return_val >= 0 else 'top',
                                   fontsize=8)
            
            # 调整布局，底部inset设置为最小
            self.figure.tight_layout(pad=0.1)
            # 进一步减少底部空白
            self.figure.subplots_adjust(bottom=0.02)
            
            # 刷新画布
            self.chart_canvas.draw_idle()
            
        except Exception as e:
            print(f"创建月度图表时出错: {str(e)}")
            # 如果出错，显示错误信息
            self.monthly_ax.clear()
            self.monthly_ax.text(0.5, 0.5, f'月度数据加载失败\n{str(e)}', 
                                ha='center', va='center', transform=self.monthly_ax.transAxes)
            self.chart_canvas.draw_idle()


    def _set_default_chip_values(self, data):
        """设置默认的筹码属性值（指数不设置）"""
        is_index = str(self.current_code or "") in ["1A0001", "000001"]
        if not is_index:
            for attr in self.chip_attributes:
                data[attr['column']] = attr['default']

    def on_search_enter(self, event=None):
        """处理搜索回车事件"""
        symbol = str(self.search_var.get()).strip()  # 强制转换为字符串
        if not symbol:
            return
        
        try:
            # 如果输入的是代码
            if symbol.isdigit():
                name, _ = get_symbol_info(symbol)
                if name is None:
                    messagebox.showerror(l("error"), l("symbol_not_found"))
                    return
            else:
                # 如果输入的是名称
                result = get_symbol_info_by_name(symbol)
                if result is None:
                    messagebox.showerror(l("error"), l("symbol_not_found"))
                    return                
                symbol = result[0][0]  # 获取代码
                name = result[0][1]    # 获取名称
            
            # 如果切换了股票，取消之前的异步任务并清除缓存
            if self.current_code != symbol:
                self._cancel_async_tasks()
                # 清除趋势检测缓存，确保新股票获取最新数据
                self._clear_trend_cache()
                # 清除分析引擎缓存，确保新股票获取最新数据
                if hasattr(self.analysis_engine, '_indicator_cache'):
                    self.analysis_engine._indicator_cache.clear()
                    print(f"搜索切换股票，已清除分析引擎缓存: {symbol}")
                print(f"搜索切换股票，已清除趋势检测缓存: {symbol}")
            
            # 更新当前股票
            self.current_code = symbol
            self.current_symbol_name = name
            self.current_symbol = symbol  # 同步更新current_symbol
            
            # 更新窗口标题
            self.window.title(f"{self.current_symbol_name}({self.current_code}) - K线图")
            
            # 加载并显示K线数据 - 强制刷新以确保获取新股票的数据
            self.load_data_and_show(force_refresh=True)
            
            # 更新分时图（如果存在）
            if hasattr(self, '_intraday_window') and self._intraday_window is not None:
                try:
                    self._intraday_window.update_stock_code(symbol, name)
                except Exception as e:
                    print(f"更新分时图失败: {str(e)}")
            
            # 加载备忘录内容
            self.load_memo()  # 确保加载新的备忘录内容
            
            # 清空搜索框
            self.search_var.set("")
            
        except Exception as e:
            messagebox.showerror(l("error"), str(e))

    def _check_condition_trigger(self):
        """检查并打印最新的条件触发信息"""
        trigger_info = self.analysis_engine.get_latest_condition_trigger(self.current_code, self.conditions)
        if trigger_info:
            print(f"\n[{self.current_code}] {trigger_info['message']}")
        else:
            print(f"\n[{self.current_code}] 近期未触发任何条件")

    def load_memo(self):
        """加载备忘录内容"""
        if not self.current_symbol:
            return
            
        print(f"[{self.current_symbol}] 正在加载备忘录...")
        memo_data = self.memo_manager.load_memo(self.current_symbol)
        self.memo_text.delete('1.0', tk.END)
        self.memo_text.insert('1.0', memo_data['content'])
        
        # 更新最后修改时间
        if memo_data['last_modified']:
            self.last_modified_label.config(
                text=f"最后修改: {memo_data['last_modified']}"
            )
            print(f"[{self.current_symbol}] 备忘录加载完成，最后修改时间: {memo_data['last_modified']}")
        else:
            self.last_modified_label.config(text="")
            print(f"[{self.current_symbol}] 备忘录为空")
            
    def save_memo(self, event=None):
        """保存备忘录内容"""
        if not self.current_symbol:
            return
            
        content = self.memo_text.get('1.0', tk.END).strip()
        print(f"[{self.current_symbol}] 正在保存备忘录...")
        
        if self.memo_manager.save_memo(self.current_symbol, content):
            # 更新最后修改时间
            memo_data = self.memo_manager.load_memo(self.current_symbol)
            self.last_modified_label.config(
                text=f"最后修改: {memo_data['last_modified']}"
            )
            print(f"[{self.current_symbol}] 备忘录保存成功")
        else:
            print(f"[{self.current_symbol}] 备忘录保存失败")

    def add_to_watchlist(self, event=None):
        """将当前股票添加到默认自选列表"""
        if not self.current_code or not self.current_symbol_name:
            return
            
        try:
            # 获取主窗口的watchlist实例 - 修改这里的访问方式
            watchlist_window = self.parent.watchlist_window  # self.parent 是 App 实例
            
            # 检查股票是否已在默认列表中
            if self.current_code in watchlist_window.watchlists["默认"]:
                messagebox.showinfo("提示", "该股票已在默认列表中")
                return
                
            # 添加到默认列表
            watchlist_window.watchlists["默认"].append(self.current_code)
            watchlist_window.save_watchlists()
            
            # 如果当前显示的是默认列表,则刷新显示
            if watchlist_window.current_list == "默认":
                watchlist_window.load_list_data()
                
            messagebox.showinfo("成功", f"已将 {self.current_symbol_name}({self.current_code}) 添加到默认列表")
            
        except Exception as e:
            messagebox.showerror("错误", f"添加失败: {str(e)}")

    def toggle_sidebar(self):
        """切换侧边栏显示状态"""
        try:
            if self.sidebar_visible:
                # 隐藏侧边栏
                self.main_container_h.forget(self.info_frame)
                self.sidebar_button.configure(text="≡")
                self.sidebar_visible = False
            else:
                # 检查 info_frame 是否已经在 main_container_h 中
                pane_info = self.main_container_h.panes()
                if str(self.info_frame) not in pane_info:
                    # 显示侧边栏
                    self.main_container_h.add(self.info_frame, weight=1)
                self.sidebar_button.configure(text="×")
                self.sidebar_visible = True
        except Exception as e:
            print(f"切换侧边栏时出错: {str(e)}")

    def _update_low_price_digit_chart(self):
        """获取近一年日线数据，计算最低价末位(分)分布并更新图表"""
        if not self.current_code:
            return

        # 检查是否为退市股票，如果是则跳过计算
        if str(self.current_code).startswith(('40', '42')):
            if hasattr(self, 'low_price_digit_chart') and self.low_price_digit_chart:
                self.low_price_digit_chart.show_message("退市股票不计算此指标")
            return

        if not hasattr(self, 'low_price_digit_chart') or self.low_price_digit_chart is None:
             print("Error: low_price_digit_chart is not initialized.")
             return

        self.low_price_digit_chart.show_loading() # 显示加载状态

        def calculation_task():
            try:
                # 1. 获取近一年日线数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                # 使用缓存或引擎获取数据
                daily_data = self.analysis_engine.load_data(
                    code=self.current_code,
                    symbol_name=self.current_symbol_name,
                    period_mode='day', # 强制日线
                    start_date=start_date.strftime('%Y-%m-%d'), # 固定开始日期
                    end_date=end_date.strftime('%Y-%m-%d'),   # 固定结束日期
                    period_config=self.period_config,  # 传递完整的周期配置
                    ma_lines=[5, 10, 20, 60],  # <--- 修改：使用固定的日线MA周期，而不是self.ma_lines
                    force_refresh=False
                )

                if daily_data is None or daily_data.empty or '最低' not in daily_data.columns:
                    raise ValueError(l("failed_to_get_daily_data")) # 获取日线数据失败

                # 2. 计算分布
                # 确保数据至少有一年，如果不足则使用全部数据
                if len(daily_data) > 252:
                    target_data = daily_data.iloc[-252:]
                else:
                    target_data = daily_data

                low_prices = target_data['最低'].dropna() # 移除NaN值
                if low_prices.empty:
                     raise ValueError(l("no_valid_low_price_data")) # 无有效最低价数据

                # 转换成分，取模10
                low_prices_cents = (low_prices * 100).round().astype(int)
                last_digits = low_prices_cents % 10

                # 统计频率并计算概率
                digit_counts = last_digits.value_counts().sort_index()
                # 确保0-9都存在
                digit_counts = digit_counts.reindex(range(10), fill_value=0)

                total_days = len(last_digits)
                if total_days > 0:
                    digit_distribution = digit_counts / total_days
                else:
                    # 创建一个全零的Series以避免错误
                    digit_distribution = pd.Series([0.0] * 10, index=range(10))

                # 3. 更新图表 (在主线程中)
                if self.window and self.window.winfo_exists():
                    if hasattr(self, 'low_price_digit_chart') and self.low_price_digit_chart:
                        self.window.after(0, lambda: self.low_price_digit_chart.update_data(
                            digit_distribution,
                            start_date=start_date.strftime('%Y-%m-%d'),
                            end_date=end_date.strftime('%Y-%m-%d')
                        ))

            except Exception as e:
                error_msg = f"{l('error_calculating_distribution')}: {str(e)}" # 计算分布时出错
                print(error_msg)
                if self.window and self.window.winfo_exists():
                     # 再次检查 self.low_price_digit_chart 是否存在
                    if hasattr(self, 'low_price_digit_chart') and self.low_price_digit_chart:
                        self.window.after(0, lambda msg=error_msg: self.low_price_digit_chart.show_error(msg))

        # 启动后台线程执行计算
        threading.Thread(target=calculation_task, daemon=True).start()

    def _update_high_price_digit_chart(self):
        """获取近一年日线数据，计算最高价末位(分)分布并更新图表"""
        if not self.current_code:
            return

        # 检查是否为退市股票，如果是则跳过计算
        if str(self.current_code).startswith(('40', '42')):
            if hasattr(self, 'high_price_digit_chart') and self.high_price_digit_chart:
                self.high_price_digit_chart.show_message("退市股票不计算此指标")
            return

        if not hasattr(self, 'high_price_digit_chart') or self.high_price_digit_chart is None:
            print("Error: high_price_digit_chart is not initialized.")
            return

        self.high_price_digit_chart.show_loading()

        def calculation_task():
            try:
                # 1. 获取近一年日线数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=365)
                daily_data = self.analysis_engine.load_data(
                    code=self.current_code,
                    symbol_name=self.current_symbol_name,
                    period_mode='day', # 强制日线
                    start_date=start_date.strftime('%Y-%m-%d'), # 固定开始日期
                    end_date=end_date.strftime('%Y-%m-%d'),   # 固定结束日期
                    period_config=self.period_config, # 传递完整的周期配置
                    ma_lines=[5, 10, 20, 60], # <--- 修改：使用固定的日线MA周期，而不是self.ma_lines
                    force_refresh=False
                )

                if daily_data is None or daily_data.empty or '最高' not in daily_data.columns:
                    raise ValueError(l("failed_to_get_daily_data"))

                # 2. 计算分布
                if len(daily_data) > 252:
                    target_data = daily_data.iloc[-252:]
                else:
                    target_data = daily_data

                high_prices = target_data['最高'].dropna()
                if high_prices.empty:
                    raise ValueError(l("no_valid_high_price_data"))

                # 转换成分，取模10
                high_prices_cents = (high_prices * 100).round().astype(int)
                last_digits = high_prices_cents % 10

                # 统计频率并计算概率
                digit_counts = last_digits.value_counts().sort_index()
                digit_counts = digit_counts.reindex(range(10), fill_value=0)

                total_days = len(last_digits)
                if total_days > 0:
                    digit_distribution = digit_counts / total_days
                else:
                    digit_distribution = pd.Series([0.0] * 10, index=range(10))

                # 3. 更新图表
                if self.window and self.window.winfo_exists():
                    if hasattr(self, 'high_price_digit_chart') and self.high_price_digit_chart:
                        self.window.after(0, lambda: self.high_price_digit_chart.update_data(
                            digit_distribution,
                            start_date=start_date.strftime('%Y-%m-%d'),
                            end_date=end_date.strftime('%Y-%m-%d')
                        ))

            except Exception as e:
                error_msg = f"{l('error_calculating_distribution')}: {str(e)}"
                print(error_msg)
                if self.window and self.window.winfo_exists():
                    if hasattr(self, 'high_price_digit_chart') and self.high_price_digit_chart:
                        self.window.after(0, lambda msg=error_msg: self.high_price_digit_chart.show_error(msg))

        # 启动后台线程执行计算
        threading.Thread(target=calculation_task, daemon=True).start()

    def clear_charts_and_info(self):
        """清空所有图表和信息显示"""
        # 清空K线图区域
        if hasattr(self, 'figure'):
            for ax in self.figure.get_axes():
                ax.clear()
            self.chart_canvas.draw_idle()

        # 清空信息表格
        if hasattr(self, 'info_table'):
            for item in self.info_table.get_children():
                self.info_table.delete(item)

        # 清空最低价分布图
        # if hasattr(self, 'low_price_digit_chart') and self.low_price_digit_chart: # <--- 确认检查新图表
        #     self.low_price_digit_chart.show_message(l("select_stock_first")) # 请先选择股票

        # 清空最高价分布图
        # if hasattr(self, 'high_price_digit_chart') and self.high_price_digit_chart:
        #     self.high_price_digit_chart.show_message(l("select_stock_first"))

        # 清空备忘录 (可选)
        # if hasattr(self, 'memo_text'):
        #     self.memo_text.delete('1.0', tk.END)

        # 重置内部状态
        self.current_data = None
        self._current_indicators = {}
        self.market_intent = {}
        self._current_selected_data = None
        
        # 清除趋势检测缓存
        self._clear_trend_cache()
        self._current_selected_date = None
        self.is_analyzing_indicators = False
        # 可以在这里添加更多需要重置的状态变量

    def print_broker_details_to_console(self):
        """打印营业部详细数据到控制台"""
        # 检查全局调试开关
        if not DEBUG_FUND_BROKER_DETAILS:
            return
            
        if not self.current_code:
            print("请先选择股票代码")
            return
            
        try:
            from lhb_data_processor import lhb_processor

            # 获取当前显示时间范围
            if self.current_data is not None and not self.current_data.empty:
                start_date = self.current_data.index[0].strftime('%Y%m%d')
                end_date = self.current_data.index[-1].strftime('%Y%m%d')
                
            print(f"\n{'='*80}")
            print(f"营业部详细数据 - {self.current_code} ({self.current_symbol_name})")
            print(f"时间范围: {start_date} 至 {end_date}")
            print(f"{'='*80}")
            
            # 获取营业部详细数据
            broker_details = lhb_processor.get_fund_source_details(
                    str(self.current_code), start_date, end_date
                )
                
            if not broker_details or not any(broker_details.values()):
                print("未获取到营业部详细数据")
                return
            
            # 打印机构营业部数据
            institution_brokers = broker_details.get('institution', [])
            if institution_brokers:
                print(f"\n【机构营业部】 (共{len(institution_brokers)}家)")
                print(f"{'-'*60}")
                for i, broker in enumerate(institution_brokers, 1):  # 显示所有机构营业部
                    broker_name = broker['broker_name']
                    net_amount = broker['net_amount']
                    net_shares = broker['net_shares']
                    buy_amount = broker['buy_amount']
                    sell_amount = broker['sell_amount']
                    
                    # 格式化显示
                    direction = "+" if net_amount > 0 else ""
                    if abs(net_amount) >= 100000000:  # 1亿
                        amount_text = f"{net_amount/100000000:.2f}亿"
                    elif abs(net_amount) >= 10000:  # 1万
                        amount_text = f"{net_amount/10000:.1f}万"
                    else:
                        amount_text = f"{int(net_amount)}"
                    
                    if abs(net_shares) >= 10000:
                        shares_text = f"{net_shares/10000:.1f}万股"
                    else:
                        shares_text = f"{int(net_shares/1000)}千股" if abs(net_shares) >= 1000 else f"{int(net_shares)}股"
                    
                    print(f"{i:2d}. {broker_name:<12} {direction}{amount_text:>10}元 ({shares_text:>8})")
                    print(f"     买入: {buy_amount:>12,.0f}元  卖出: {sell_amount:>12,.0f}元")
                    
                    # 显示每日交易明细
                    if 'daily_trades' in broker and broker['daily_trades']:
                        print(f"     每日交易明细:")
                        for date_str, trades in sorted(broker['daily_trades'].items()):
                            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            buy_amt = trades.get('buy', 0)
                            sell_amt = trades.get('sell', 0)
                            buy_shares = trades.get('buy_shares', 0)
                            sell_shares = trades.get('sell_shares', 0)
                            
                            # 获取当日股价
                            try:
                                # 从当前K线数据中获取股价，避免重复调用API
                                daily_price = 0.0
                                if self.current_data is not None and not self.current_data.empty:
                                    # 将日期字符串转换为datetime
                                    target_date = pd.to_datetime(date_str, format='%Y%m%d')
                                    
                                    # 在current_data中查找对应日期
                                    if target_date in self.current_data.index:
                                        row = self.current_data.loc[target_date]
                                        
                                        # 优先使用成交额/成交量计算均价
                                        if '成交额' in row and '成交量' in row:
                                            vol = float(row['成交量'])
                                            amt = float(row['成交额'])
                                            if vol > 0 and amt > 0:
                                                avg_price = amt / vol
                                                if avg_price > 0 and avg_price < 1000:
                                                    daily_price = avg_price
                                        
                                        # 回退：使用OHLC均价
                                        if daily_price == 0:
                                            ohlc_cols = ['开盘', '收盘', '最高', '最低']
                                            if all(col in row for col in ohlc_cols):
                                                daily_avg = sum(float(row[col]) for col in ohlc_cols) / len(ohlc_cols)
                                                if daily_avg > 0 and daily_avg < 1000:
                                                    daily_price = daily_avg
                                        
                                        # 最后回退：使用收盘价
                                        if daily_price == 0 and '收盘' in row:
                                            close_price = float(row['收盘'])
                                            if close_price > 0 and close_price < 1000:
                                                daily_price = close_price
                            except Exception:
                                daily_price = 0.0
                            
                            if buy_amt > 0 or sell_amt > 0:
                                # 计算净买入金额和股数
                                net_amt = buy_amt - sell_amt
                                net_direction = "+" if net_amt > 0 else ""
                                net_amt_abs = abs(net_amt)
                                
                                # 格式化净买入金额显示
                                if net_amt_abs >= 100000000:  # 1亿
                                    net_amt_text = f"{net_amt_abs/100000000:.2f}亿"
                                elif net_amt_abs >= 10000:  # 1万
                                    net_amt_text = f"{net_amt_abs/10000:.1f}万"
                                else:
                                    net_amt_text = f"{int(net_amt_abs)}"
                                
                                # 计算基于平均股价的股数
                                calculated_shares = 0
                                if daily_price > 0:
                                    calculated_shares = net_amt / daily_price
                            
                                # 格式化股数显示
                                if abs(calculated_shares) >= 10000:
                                    shares_text = f"{calculated_shares/10000:.1f}万股"
                                elif abs(calculated_shares) >= 1000:
                                    shares_text = f"{int(calculated_shares/1000)}千股"
                                else:
                                    shares_text = f"{int(calculated_shares)}股"
                                
                                # 显示净买入信息（用数值符号表示方向）
                                print(f"       {date_display}: 净买入{net_direction}{net_amt_text}元 ({shares_text})")
                                
                                # 添加平均股价信息（用于计算股数）
                                price_info = f" [平均股价: {daily_price:.2f}元]" if daily_price > 0 else " [平均股价: 未知]"
                                print(f"         {price_info}")
            else:
                print("\n【机构营业部】: 无数据")
            
            # 打印游资营业部数据
            hot_brokers = broker_details.get('hot', [])
            if hot_brokers:
                print(f"\n【游资营业部】 (共{len(hot_brokers)}家)")
                print(f"{'-'*60}")
                for i, broker in enumerate(hot_brokers, 1):  # 显示所有游资营业部
                    broker_name = broker['broker_name']
                    net_amount = broker['net_amount']
                    net_shares = broker['net_shares']
                    buy_amount = broker['buy_amount']
                    sell_amount = broker['sell_amount']
                    
                    # 格式化显示
                    direction = "+" if net_amount > 0 else ""
                    if abs(net_amount) >= 100000000:  # 1亿
                        amount_text = f"{net_amount/100000000:.2f}亿"
                    elif abs(net_amount) >= 10000:  # 1万
                        amount_text = f"{net_amount/10000:.1f}万"
                    else:
                        amount_text = f"{int(net_amount)}"
                    
                    if abs(net_shares) >= 10000:
                        shares_text = f"{net_shares/10000:.1f}万股"
                    else:
                        shares_text = f"{int(net_shares/1000)}千股" if abs(net_shares) >= 1000 else f"{int(net_shares)}股"
                    
                    print(f"{i:2d}. {broker_name:<12} {direction}{amount_text:>10}元 ({shares_text:>8})")
                    print(f"     买入: {buy_amount:>12,.0f}元  卖出: {sell_amount:>12,.0f}元")
                    
                    # 显示每日交易明细
                    if 'daily_trades' in broker and broker['daily_trades']:
                        print(f"     每日交易明细:")
                        for date_str, trades in sorted(broker['daily_trades'].items()):
                            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            buy_amt = trades.get('buy', 0)
                            sell_amt = trades.get('sell', 0)
                            buy_shares = trades.get('buy_shares', 0)
                            sell_shares = trades.get('sell_shares', 0)
                            
                            # 获取当日股价
                            try:
                                # 从当前K线数据中获取股价，避免重复调用API
                                daily_price = 0.0
                                if self.current_data is not None and not self.current_data.empty:
                                    # 将日期字符串转换为datetime
                                    target_date = pd.to_datetime(date_str, format='%Y%m%d')
                                    
                                    # 在current_data中查找对应日期
                                    if target_date in self.current_data.index:
                                        row = self.current_data.loc[target_date]
                                        
                                        # 优先使用成交额/成交量计算均价
                                        if '成交额' in row and '成交量' in row:
                                            vol = float(row['成交量'])
                                            amt = float(row['成交额'])
                                            if vol > 0 and amt > 0:
                                                avg_price = amt / vol
                                                if avg_price > 0 and avg_price < 1000:
                                                    daily_price = avg_price
                                        
                                        # 回退：使用OHLC均价
                                        if daily_price == 0:
                                            ohlc_cols = ['开盘', '收盘', '最高', '最低']
                                            if all(col in row for col in ohlc_cols):
                                                daily_avg = sum(float(row[col]) for col in ohlc_cols) / len(ohlc_cols)
                                                if daily_avg > 0 and daily_avg < 1000:
                                                    daily_price = daily_avg
                                        
                                        # 最后回退：使用收盘价
                                        if daily_price == 0 and '收盘' in row:
                                            close_price = float(row['收盘'])
                                            if close_price > 0 and close_price < 1000:
                                                daily_price = close_price
                            except Exception:
                                daily_price = 0.0
                            
                            if buy_amt > 0 or sell_amt > 0:
                                # 计算净买入金额和股数
                                net_amt = buy_amt - sell_amt
                                net_direction = "+" if net_amt > 0 else ""
                                net_amt_abs = abs(net_amt)
                                
                                # 格式化净买入金额显示
                                if net_amt_abs >= 100000000:  # 1亿
                                    net_amt_text = f"{net_amt_abs/100000000:.2f}亿"
                                elif net_amt_abs >= 10000:  # 1万
                                    net_amt_text = f"{net_amt_abs/10000:.1f}万"
                                else:
                                    net_amt_text = f"{int(net_amt_abs)}"
                                
                                # 计算基于平均股价的股数
                                calculated_shares = 0
                                if daily_price > 0:
                                    calculated_shares = net_amt / daily_price
                                
                                # 格式化股数显示
                                if abs(calculated_shares) >= 10000:
                                    shares_text = f"{calculated_shares/10000:.1f}万股"
                                elif abs(calculated_shares) >= 1000:
                                    shares_text = f"{int(calculated_shares/1000)}千股"
                                else:
                                    shares_text = f"{int(calculated_shares)}股"
                                
                                # 显示净买入信息（用数值符号表示方向）
                                print(f"       {date_display}: 净买入{net_direction}{net_amt_text}元 ({shares_text})")
                                
                                # 添加平均股价信息（用于计算股数）
                                price_info = f" [平均股价: {daily_price:.2f}元]" if daily_price > 0 else " [平均股价: 未知]"
                                print(f"         {price_info}")
            else:
                print("\n【游资营业部】: 无数据")
            
            # 打印散户营业部数据
            retail_brokers = broker_details.get('retail', [])
            if retail_brokers:
                print(f"\n【散户营业部】 (共{len(retail_brokers)}家)")
                print(f"{'-'*60}")
                for i, broker in enumerate(retail_brokers, 1):  # 显示所有散户营业部
                    broker_name = broker['broker_name']
                    net_amount = broker['net_amount']
                    net_shares = broker['net_shares']
                    buy_amount = broker['buy_amount']
                    sell_amount = broker['sell_amount']
                    
                    # 格式化显示
                    direction = "+" if net_amount > 0 else ""
                    if abs(net_amount) >= 100000000:  # 1亿
                        amount_text = f"{net_amount/100000000:.2f}亿"
                    elif abs(net_amount) >= 10000:  # 1万
                        amount_text = f"{net_amount/10000:.1f}万"
                    else:
                        amount_text = f"{int(net_amount)}"
                    
                    if abs(net_shares) >= 10000:
                        shares_text = f"{net_shares/10000:.1f}万股"
                    else:
                        shares_text = f"{int(net_shares/1000)}千股" if abs(net_shares) >= 1000 else f"{int(net_shares)}股"
                    
                    print(f"{i:2d}. {broker_name:<12} {direction}{amount_text:>10}元 ({shares_text:>8})")
                    print(f"     买入: {buy_amount:>12,.0f}元  卖出: {sell_amount:>12,.0f}元")
                    
                    # 显示每日交易明细
                    if 'daily_trades' in broker and broker['daily_trades']:
                        print(f"     每日交易明细:")
                        for date_str, trades in sorted(broker['daily_trades'].items()):
                            date_display = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                            buy_amt = trades.get('buy', 0)
                            sell_amt = trades.get('sell', 0)
                            buy_shares = trades.get('buy_shares', 0)
                            sell_shares = trades.get('sell_shares', 0)
                            
                            # 获取当日股价
                            try:
                                # 从当前K线数据中获取股价，避免重复调用API
                                daily_price = 0.0
                                if self.current_data is not None and not self.current_data.empty:
                                    # 将日期字符串转换为datetime
                                    target_date = pd.to_datetime(date_str, format='%Y%m%d')
                                    
                                    # 在current_data中查找对应日期
                                    if target_date in self.current_data.index:
                                        row = self.current_data.loc[target_date]
                                        
                                        # 优先使用成交额/成交量计算均价
                                        if '成交额' in row and '成交量' in row:
                                            vol = float(row['成交量'])
                                            amt = float(row['成交额'])
                                            if vol > 0 and amt > 0:
                                                avg_price = amt / vol
                                                if avg_price > 0 and avg_price < 1000:
                                                    daily_price = avg_price
                                        
                                        # 回退：使用OHLC均价
                                        if daily_price == 0:
                                            ohlc_cols = ['开盘', '收盘', '最高', '最低']
                                            if all(col in row for col in ohlc_cols):
                                                daily_avg = sum(float(row[col]) for col in ohlc_cols) / len(ohlc_cols)
                                                if daily_avg > 0 and daily_avg < 1000:
                                                    daily_price = daily_avg
                                        
                                        # 最后回退：使用收盘价
                                        if daily_price == 0 and '收盘' in row:
                                            close_price = float(row['收盘'])
                                            if close_price > 0 and close_price < 1000:
                                                daily_price = close_price
                            except Exception:
                                daily_price = 0.0
                            
                            if buy_amt > 0 or sell_amt > 0:
                                # 计算净买入金额和股数
                                net_amt = buy_amt - sell_amt
                                net_direction = "+" if net_amt > 0 else ""
                                net_amt_abs = abs(net_amt)
                                
                                # 格式化净买入金额显示
                                if net_amt_abs >= 100000000:  # 1亿
                                    net_amt_text = f"{net_amt_abs/100000000:.2f}亿"
                                elif net_amt_abs >= 10000:  # 1万
                                    net_amt_text = f"{net_amt_abs/10000:.1f}万"
                                else:
                                    net_amt_text = f"{int(net_amt_abs)}"
                                
                                # 计算基于平均股价的股数
                                calculated_shares = 0
                                if daily_price > 0:
                                    calculated_shares = net_amt / daily_price
                                
                                # 格式化股数显示
                                if abs(calculated_shares) >= 10000:
                                    shares_text = f"{calculated_shares/10000:.1f}万股"
                                elif abs(calculated_shares) >= 1000:
                                    shares_text = f"{int(calculated_shares/1000)}千股"
                                else:
                                    shares_text = f"{int(calculated_shares)}股"
                                
                                # 显示净买入信息（用数值符号表示方向）
                                print(f"       {date_display}: 净买入{net_direction}{net_amt_text}元 ({shares_text})")
                                
                                # 添加平均股价信息（用于计算股数）
                                price_info = f" [平均股价: {daily_price:.2f}元]" if daily_price > 0 else " [平均股价: 未知]"
                                print(f"         {price_info}")
            else:
                print("\n【散户营业部】: 无数据")
            
            # 打印汇总信息
            print(f"\n{'='*80}")
            print("数据汇总:")
            total_institution = len(institution_brokers)
            total_hot = len(hot_brokers)
            total_retail = len(retail_brokers)
            
            if total_institution > 0:
                total_institution_net = sum(b.get('net_amount', 0) for b in institution_brokers)
                total_institution_shares = sum(b.get('net_shares', 0) for b in institution_brokers)
                print(f"  机构营业部: {total_institution}家, 净买入: {total_institution_net:>12,.0f}元 ({total_institution_shares:>10,.0f}股)")
            
            if total_hot > 0:
                total_hot_net = sum(b.get('net_amount', 0) for b in hot_brokers)
                total_hot_shares = sum(b.get('net_shares', 0) for b in hot_brokers)
                print(f"  游资营业部: {total_hot}家, 净买入: {total_hot_net:>12,.0f}元 ({total_hot_shares:>10,.0f}股)")
            
            if total_retail > 0:
                total_retail_net = sum(b.get('net_amount', 0) for b in retail_brokers)
                total_retail_shares = sum(b.get('net_shares', 0) for b in retail_brokers)
                print(f"  散户营业部: {total_retail}家, 净买入: {total_retail_net:>12,.0f}元 ({total_retail_shares:>10,.0f}股)")
            
            print(f"{'='*80}")
                
        except Exception as e:
            print(f"获取营业部详细数据失败: {str(e)}")

    def _on_intraday_date_change(self, new_date_str: str):
        """分时图日期变化时的回调函数，用于更新日K线图上的垂直贯穿线位置和布林线显示"""
        try:
            print(f"分时图日期变化: {new_date_str}")
            
            # 更新分时图对应的日期
            self.intraday_date_str = new_date_str
            
            # 如果当前有K线图数据，立即更新垂直贯穿线和布林线显示
            if self.current_data is not None and not self.current_data.empty:
                self._update_intraday_date_vertical_line()
                # 重新计算并更新布林线显示
                self._update_bollinger_bands_display()
            
        except Exception as e:
            print(f"处理分时图日期变化回调失败: {e}")

    def _on_height_ratio_change(self, ratio_mode: str):
        """分时窗口高度比例变化时的回调函数
        :param ratio_mode: 比例模式 "3:7" 或 "7:3"
        """
        try:
            print(f"分时窗口高度比例变化: {ratio_mode}")
            
            # 延迟执行，确保窗口完全渲染
            def adjust_ratio():
                try:
                    # 获取PanedWindow的总高度
                    total_height = self.main_container.winfo_height()
                    if total_height <= 0:
                        print(f"[WARNING] PanedWindow高度无效: {total_height}")
                        return
                    
                    # 根据比例模式调整PanedWindow的分割位置
                    if ratio_mode == "3:7":
                        # 3:7比例: K线图占70%，分时图占30%
                        sash_position = int(total_height * 0.7)
                        self.main_container.sashpos(0, sash_position)
                        print(f"[DEBUG] 设置高度比例为3:7 (K线图:分时图), 分割位置: {sash_position}")
                    elif ratio_mode == "7:3":
                        # 7:3比例: K线图占30%，分时图占70%
                        sash_position = int(total_height * 0.3)
                        self.main_container.sashpos(0, sash_position)
                        print(f"[DEBUG] 设置高度比例为7:3 (K线图:分时图), 分割位置: {sash_position}")
                    else:
                        print(f"[WARNING] 未知的比例模式: {ratio_mode}")
                except Exception as e:
                    print(f"调整比例失败: {e}")
            
            # 延迟100ms执行，确保窗口完全渲染
            self.window.after(100, adjust_ratio)
                
        except Exception as e:
            print(f"处理高度比例变化回调失败: {e}")

    def _update_intraday_date_vertical_line(self):
        """更新分时图对应日期的垂直贯穿线"""
        try:
            # 移除旧的垂直贯穿线
            if self.intraday_date_vertical_line is not None:
                try:
                    self.intraday_date_vertical_line.remove()
                    self.intraday_date_vertical_line = None
                except Exception:
                    pass
            
            # 如果没有分时图日期或没有K线图数据，直接返回
            if not self.intraday_date_str or self.current_data is None or self.current_data.empty:
                return
            
            # 在K线图中找到对应日期的位置
            target_date = pd.Timestamp(self.intraday_date_str)
            
            # 查找日期在K线图数据中的索引
            date_found = False
            for i, date in enumerate(self.current_data.index):
                if pd.Timestamp(date).date() == target_date.date():
                    # 找到对应日期，绘制垂直贯穿线
                    line_x = i
                    date_found = True
                    break
            
            if date_found and hasattr(self, 'ax1') and self.ax1 is not None:
                # 在所有子图上绘制垂直贯穿线
                y_min, y_max = self.ax1.get_ylim()
                
                # 绘制细线，使用虚线样式，颜色为深蓝色，透明度适中
                self.intraday_date_vertical_line = self.ax1.axvline(
                    x=line_x, 
                    color='#0066CC', 
                    linestyle='--', 
                    linewidth=1.2, 
                    alpha=0.8, 
                    zorder=10,
                    label=f'分时图日期: {self.intraday_date_str}'
                )
                
                # 刷新画布
                if hasattr(self, 'chart_canvas') and self.chart_canvas:
                    self.chart_canvas.draw_idle()
                
                print(f"在日K线图上绘制分时图对应日期垂直贯穿线: 位置={line_x}, 日期={self.intraday_date_str}")
            else:
                print(f"未找到分时图对应日期 {self.intraday_date_str} 在K线图中的位置")
                
        except Exception as e:
            print(f"更新分时图对应日期垂直贯穿线失败: {e}")

    def _update_bollinger_bands_display(self):
        """更新布林线显示，根据分时图日期变化重新计算支撑位和压力位"""
        try:
            if not hasattr(self, 'ax1') or self.current_data is None or self.current_data.empty:
                return
            
            # 重新计算支撑位和压力位
            support_level, resistance_level, support_type, resistance_type = self._calculate_support_resistance_for_kline(self.current_data)
            
            if support_level is None or resistance_level is None:
                print(f"[DEBUG] 无法计算支撑位和压力位，跳过布林线更新")
                return
            
            # 根据分时图日期，计算该日期的支撑位和压力位
            # 这里我们需要根据分时图的日期来重新计算，而不是使用最新的数据
            if self.intraday_date_str:
                try:
                    # 将分时图日期转换为pandas时间戳
                    intraday_date = pd.Timestamp(self.intraday_date_str)
                    
                    # 找到该日期在K线数据中的位置
                    date_mask = self.current_data.index.date == intraday_date.date()
                    if date_mask.any():
                        # 获取该日期的数据
                        target_data = self.current_data[date_mask]
                        if not target_data.empty:
                            # 重新计算该日期的支撑位和压力位
                            target_support, target_resistance, target_support_type, target_resistance_type = self._calculate_support_resistance_for_kline(target_data)
                            
                            if target_support is not None and target_resistance is not None:
                                support_level = target_support
                                resistance_level = target_resistance
                                support_type = target_support_type
                                resistance_type = target_resistance_type
                                print(f"[DEBUG] 根据分时图日期 {self.intraday_date_str} 重新计算支撑位和压力位")
                except Exception as e:
                    print(f"[DEBUG] 根据分时图日期重新计算支撑位和压力位失败: {e}")
            
            # 更新存储的支撑位和压力位信息
            self.current_support_level = support_level
            self.current_resistance_level = resistance_level
            self.current_support_type = support_type
            self.current_resistance_type = resistance_type
            
            # 重新绘制布林线（这里需要重新绘制整个K线图，因为matplotlib不支持单独更新线条样式）
            print(f"[DEBUG] 分时图日期变化，重新绘制K线图以更新布林线显示")
            self.update_chart()
            
        except Exception as e:
            print(f"[DEBUG] 更新布林线显示失败: {e}")

    def open_intraday_window(self, event=None):
        """打开或聚焦分时窗口 (⌘1)"""
        if self.current_code is None:
            return
        try:
            if (not hasattr(self, '_intraday_window') or
                self._intraday_window is None or
                not self._intraday_window.window.winfo_exists()):
                self._intraday_window = IntradayWindow(
            self.parent, 
            self.current_code, 
            self.current_symbol_name, 
            show_toolbar=True,
            on_date_change_callback=self._on_intraday_date_change
        )
            else:
                self._intraday_window.focus()
        except Exception as e:
            print(f"打开分时窗口失败: {e}")

    def _calculate_support_resistance_for_kline(self, data):
        """计算K线图的支撑位和压力位
        
        支撑位和压力位计算规则:
        1. 基于最新交易日收盘价相对于MA20的位置
        2. 如果最新收盘价 > MA20: MA20为支撑位，布林上轨为压力位
        3. 如果最新收盘价 <= MA20: MA20为压力位，布林下轨为支撑位
        
        :param data: K线数据
        :return: (support_level, resistance_level, support_type, resistance_type)
        """
        try:
            if data.empty or 'MA20' not in data.columns or 'BOLL_UPPER' not in data.columns or 'BOLL_LOWER' not in data.columns:
                return None, None, None, None
            
            # 获取最新交易日数据
            latest_data = data.iloc[-1]
            ma20 = latest_data['MA20']
            boll_upper = latest_data['BOLL_UPPER']
            boll_lower = latest_data['BOLL_LOWER']
            latest_close = latest_data['收盘']
            
            print(f"[DEBUG] K线图支撑位压力位计算:")
            print(f"[DEBUG]  最新收盘价: {latest_close:.3f}")
            print(f"[DEBUG]  MA20: {ma20:.3f}")
            print(f"[DEBUG]  布林上轨: {boll_upper:.3f}")
            print(f"[DEBUG]  布林下轨: {boll_lower:.3f}")
            
            # 计算支撑位和压力位（基于最新收盘价相对于MA20的位置）
            if latest_close > ma20:
                # 最新收盘价在MA20之上：MA20为支撑位，布林上轨为压力位
                support_level = ma20
                resistance_level = boll_upper
                support_type = "MA20(布林中轨)"
                resistance_type = "布林上轨"
                print(f"[DEBUG]  判断逻辑: 最新收盘价({latest_close:.3f}) > MA20({ma20:.3f})")
            else:
                # 最新收盘价在MA20之下：MA20为压力位，布林下轨为支撑位
                support_level = boll_lower
                resistance_level = ma20
                support_type = "布林下轨"
                resistance_type = "MA20(布林中轨)"
                print(f"[DEBUG]  判断逻辑: 最新收盘价({latest_close:.3f}) <= MA20({ma20:.3f})")
            
            print(f"[DEBUG]  支撑位: {support_level:.3f} ({support_type})")
            print(f"[DEBUG]  压力位: {resistance_level:.3f} ({resistance_type})")
            
            return support_level, resistance_level, support_type, resistance_type
            
        except Exception as e:
            print(f"[DEBUG] K线图计算支撑位和压力位失败: {e}")
            return None, None, None, None

    def _get_extended_data_for_monthly_calculation(self) -> Optional[pd.DataFrame]:
        """
        获取扩展的历史数据用于月线连阳(阴)计算
        获取过去1年的数据，确保有足够的数据进行准确的月线计算
        
        Returns:
            扩展的历史数据DataFrame，如果获取失败返回None
        """
        try:
            if not self.current_code:
                return None
            
            # 获取过去1年的数据用于月线计算
            end_date = datetime.now()
            start_date = end_date - timedelta(days=365)  # 1年数据
            
            print(f"[DEBUG] 获取扩展数据用于月线计算: {self.current_code}, 从{start_date.strftime('%Y-%m-%d')}到{end_date.strftime('%Y-%m-%d')}")
            
            # 使用分析引擎获取扩展数据
            extended_data = self.analysis_engine.load_data(
                code=str(self.current_code),
                symbol_name=str(self.current_symbol_name or ""),
                period_mode='day',  # 使用日线数据
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                period_config=self.period_config,
                ma_lines=self.ma_lines,
                force_refresh=True  # 强制刷新获取最新数据
            )
            
            if extended_data is not None and not extended_data.empty:
                print(f"[DEBUG] 成功获取扩展数据，长度: {len(extended_data)}")
                return extended_data
            else:
                print(f"[DEBUG] 扩展数据为空")
                return None
                
        except Exception as e:
            print(f"[DEBUG] 获取扩展数据失败: {e}")
            return None

    def _get_consecutive_color(self, prev_up: int, prev_down: int, current_up: int, current_down: int) -> str:
        """
        根据连阳(阴)情况计算显示颜色
        
        Args:
            prev_up: 前一个周期连阳天数
            prev_down: 前一个周期连阴天数
            current_up: 当前周期连阳天数
            current_down: 当前周期连阴天数
            
        Returns:
            颜色代码
        """
        # 检查最近2周期是否有>=4的连阳
        if prev_up >= 4 or current_up >= 4:
            return 'red'  # 红色表示连阳>=4
        
        # 检查最近2周期是否有>=4的连阴
        if prev_down >= 4 or current_down >= 4:
            return 'green'  # 绿色表示连阴>=4
        
        # 默认颜色
        return '#333333'


    def _detect_uptrend_patterns(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        检测上涨趋势模式（调用计算函数）
        定义：在下跌或平盘K线后，连续出现4个上涨的交易日
        返回：趋势信息列表，每个趋势包含开始索引、结束索引、涨幅等信息
        """
        # 准备缓存数据
        cache_data = {
            'trends_cache': self._trends_cache,
            'trends_cache_code': self._trends_cache_code,
            'trends_cache_date_range': self._trends_cache_date_range
        }
        
        # 调用计算函数
        trends = detect_uptrend_patterns(
            data=data,
            cache_key=getattr(self, 'current_code', None),
            cache_data=cache_data,
            period_mode=getattr(self, 'period_mode', 'day')
        )
        
        # 更新实例缓存
        self._trends_cache = cache_data['trends_cache']
        self._trends_cache_code = cache_data['trends_cache_code']
        self._trends_cache_date_range = cache_data['trends_cache_date_range']
        
        return trends

    def _clear_trend_cache(self):
        """清除趋势检测缓存"""
        cache_data = {
            'trends_cache': self._trends_cache,
            'trends_cache_code': self._trends_cache_code,
            'trends_cache_date_range': self._trends_cache_date_range
        }
        clear_trend_cache(cache_data)
        self._trends_cache = cache_data['trends_cache']
        self._trends_cache_code = cache_data['trends_cache_code']
        self._trends_cache_date_range = cache_data['trends_cache_date_range']

    def _plot_expected_gain_bars(self, data: pd.DataFrame, x_index: np.ndarray, trends: List[Dict[str, Any]]):
        """
        绘制预期涨幅柱子
        在上涨趋势最后一个交易日的价格柱子实体垂直顶部绘制红色斜纹填充的预期涨幅柱子
        """
        if not trends:
            return
        
        try:
            for trend in trends:
                end_idx = trend['end_idx']
                expected_price = trend['expected_price']
                current_close = data.iloc[end_idx]['收盘']
                
                # 计算预期涨幅柱子的位置和大小
                x_pos = x_index[end_idx]
                y_bottom = current_close  # 从当前收盘价开始
                y_top = expected_price    # 到预期价格结束
                width = 0.3  # 柱子宽度
                
                # 绘制蓝色填充的预期涨幅柱子
                rect = Rectangle(
                    (x_pos - width/2, y_bottom),  # (x, y) 左下角位置
                    width,                        # 宽度
                    y_top - y_bottom,             # 高度
                    facecolor='blue',             # 蓝色填充
                    alpha=0.6,                    # 透明度
                    edgecolor='darkblue',         # 深蓝色边框
                    linewidth=1,                  # 边框宽度
                    zorder=10                     # 确保在其他元素之上
                )
                
                self.ax1.add_patch(rect)
                
                # 在柱子顶部添加价格和涨幅标签（合并为一个文字框）
                gain_pct = trend['trend_gain_pct']
                label_text = f'{expected_price:.2f}\n+{gain_pct:.1f}%'
                self.ax1.text(
                    x_pos, y_top + (y_top - y_bottom) * 0.05,  # 在柱子顶部稍微上方
                    label_text,
                    ha='center', va='bottom',
                    fontsize=7, color='blue', weight='bold',
                    bbox=dict(
                        boxstyle="round,pad=0.3",
                        facecolor='white',
                        alpha=0.9,
                        edgecolor='blue',
                        linewidth=1
                    )
                )
                
                print(f"[DEBUG] 绘制预期涨幅柱子: 位置={x_pos}, 当前价格={current_close:.2f}, 预期价格={expected_price:.2f}, 涨幅={gain_pct:.1f}%")
                
        except Exception as e:
            print(f"[ERROR] 绘制预期涨幅柱子失败: {e}")
            import traceback
            traceback.print_exc()

    def _calculate_previous_trend_gain(self, data: pd.DataFrame, period: str, prev_consecutive_up: int) -> tuple:
        """
        计算上一个趋势的趋势价格和涨幅
        
        Args:
            data: 包含OHLC数据的DataFrame
            period: 周期类型，'day'表示日线，'week'表示周线，'month'表示月线
            prev_consecutive_up: 上一个趋势的连阳天数
            
        Returns:
            tuple: (连阳涨幅百分比, 当前周期收盘价, 趋势目标价格)
        """
        try:
            if data is None or data.empty or prev_consecutive_up < 4:
                return (0.0, 0.0, 0.0)
            
            # 确保数据按日期排序
            data_sorted = data.sort_index()
            
            # 根据周期重采样数据
            if period == 'day':
                period_data = data_sorted.copy()
            elif period == 'week':
                period_data = data_sorted.resample('W').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            elif period == 'month':
                period_data = data_sorted.resample('M').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            else:
                return (0.0, 0.0, 0.0)
            
            if period_data.empty or len(period_data) < prev_consecutive_up + 1:
                return (0.0, 0.0, 0.0)
            
            # 计算涨跌状态，基于前后两个交易日的收盘价比较
            is_up = pd.Series([False] * len(period_data), index=period_data.index)
            is_down = pd.Series([False] * len(period_data), index=period_data.index)
            
            # 从第二个交易日开始比较收盘价
            for i in range(1, len(period_data)):
                current_close = period_data.iloc[i]['收盘']
                prev_close = period_data.iloc[i-1]['收盘']
                
                if current_close > prev_close:
                    # 上涨：当前收盘价高于前一日收盘价
                    is_up.iloc[i] = True
                else:
                    # 下跌或平盘：当前收盘价低于或等于前一日收盘价，统一算作阴线
                    is_down.iloc[i] = True
            
            # 找到上一个趋势的位置
            # 从最新数据开始向前找到当前趋势的起始位置
            current_consecutive_up = 0
            current_consecutive_down = 0
            
            for i in range(len(period_data) - 1, -1, -1):
                if is_up.iloc[i]:  # 上涨
                    if current_consecutive_down > 0:  # 如果之前是连阴，则重置
                        break
                    current_consecutive_up += 1
                else:  # 下跌或平盘，统一算作阴线
                    if current_consecutive_up > 0:  # 如果之前是连阳，则重置
                        break
                    current_consecutive_down += 1
            
            # 计算上一个趋势的起始位置
            current_start = len(period_data) - 1
            if current_consecutive_up > 0:
                current_start = len(period_data) - current_consecutive_up
            elif current_consecutive_down > 0:
                current_start = len(period_data) - current_consecutive_down
            
            # 上一个趋势的结束位置就是当前趋势的起始位置
            prev_trend_end = current_start
            prev_trend_start = prev_trend_end - prev_consecutive_up
            
            if prev_trend_start < 0 or prev_trend_end <= prev_trend_start:
                return (0.0, 0.0, 0.0)
            
            # 计算上一个趋势的4连阳涨幅
            # 取上一个趋势中最早的4个连阳周期
            trend_data = []
            for i in range(prev_trend_start, prev_trend_end):
                if is_up.iloc[i]:
                    trend_data.append({
                        'index': i,
                        '开盘': period_data['开盘'].iloc[i],
                        '收盘': period_data['收盘'].iloc[i],
                        '日期': period_data.index[i]
                    })
            
            if len(trend_data) < 4:
                return (0.0, 0.0, 0.0)
            
            # 取最早的4个连阳周期
            four_consecutive_data = trend_data[-4:]
            
            # 计算4连阳涨幅
            start_low = min(four_consecutive_data[0]['开盘'], four_consecutive_data[0]['收盘'])
            end_high = max(four_consecutive_data[-1]['开盘'], four_consecutive_data[-1]['收盘'])
            trend_gain = end_high - start_low
            
            # 当前周期收盘价，确保为数值类型
            current_price = float(period_data['收盘'].iloc[-1])
            
            # 趋势目标价格 = 第4个连阳周期收盘价 + 4连阳涨幅
            fourth_close = float(four_consecutive_data[-1]['收盘'])
            target_price = fourth_close + trend_gain
            
            # 涨幅计算：目标价格相对于当前价格的涨幅百分比
            if current_price > 0:
                trend_gain_pct = ((target_price - current_price) / current_price) * 100
            else:
                trend_gain_pct = 0.0
            
            # 根据周期类型确定显示单位
            period_unit = "天" if period == 'day' else "周" if period == 'week' else "月"
            date_format = '%Y-%m-%d' if period == 'day' else '%Y-%m'
            
            print(f"[DEBUG] 上一个{period}线连阳涨幅计算: 连阳{prev_consecutive_up}{period_unit}, 计算4连阳涨幅{trend_gain_pct:.2f}%")
            print(f"[DEBUG]   第1{period_unit}(最早): {four_consecutive_data[0]['日期'].strftime(date_format)} 实体最低价: {start_low:.3f}")
            print(f"[DEBUG]   第4{period_unit}(第4个): {four_consecutive_data[-1]['日期'].strftime(date_format)} 实体最高价: {end_high:.3f}")
            print(f"[DEBUG]   4连阳涨幅: {trend_gain:.3f}")
            print(f"[DEBUG]   第4{period_unit}收盘价: {fourth_close:.3f}")
            print(f"[DEBUG]   当前价格: {current_price:.3f}")
            print(f"[DEBUG]   目标价格: {target_price:.3f} (第4{period_unit}收盘价 + 4连阳涨幅)")
            
            return (trend_gain_pct, current_price, target_price)
            
        except Exception as e:
            print(f"[DEBUG] 计算上一个{period}线连阳涨幅失败: {e}")
            return (0.0, 0.0, 0.0)

    def _calculate_consecutive_days(self, data: pd.DataFrame, period: str = 'week') -> tuple:
        """
        计算指定周期的连阳(阴)天数，包括前一个周期的状态
        
        Args:
            data: 包含OHLC数据的DataFrame
            period: 周期类型，'week'表示周线，'month'表示月线
            
        Returns:
            tuple: (当前连阳天数, 当前连阴天数, 前一个周期连阳天数, 前一个周期连阴天数)
        """
        try:
            if data is None or data.empty:
                return (0, 0, 0, 0)
            
            # 确保数据按日期排序
            data_sorted = data.sort_index()
            
            # 对于月线计算，如果数据不足12个月，尝试获取更多历史数据
            if period == 'month' and len(data_sorted) < 365:  # 少于一年的数据
                try:
                    # 获取更多历史数据用于月线计算
                    extended_data = self._get_extended_data_for_monthly_calculation()
                    if extended_data is not None and not extended_data.empty:
                        # 合并数据，去重并排序
                        combined_data = pd.concat([data_sorted, extended_data])
                        combined_data = combined_data[~combined_data.index.duplicated(keep='last')]
                        data_sorted = combined_data.sort_index()
                        print(f"[DEBUG] 月线计算使用扩展数据，总长度: {len(data_sorted)}")
                except Exception as e:
                    print(f"[DEBUG] 获取扩展数据失败，使用原始数据: {e}")
                    pass
            
            if period == 'day':
                # 日线数据直接使用原始数据
                period_data = data_sorted.copy()
            elif period == 'week':
                # 计算周线数据
                period_data = data_sorted.resample('W').agg({
                    '开盘': 'first',
                    '最高': 'max', 
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            elif period == 'month':
                # 计算月线数据
                period_data = data_sorted.resample('M').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min', 
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            else:
                return (0, 0, 0, 0)
            
            if period_data.empty:
                return (0, 0, 0, 0)
            
            # 计算涨跌状态，基于前后两个交易日的收盘价比较
            is_up = pd.Series([False] * len(period_data), index=period_data.index)
            is_down = pd.Series([False] * len(period_data), index=period_data.index)
            is_flat = pd.Series([False] * len(period_data), index=period_data.index)
            
            # 从第二个交易日开始比较收盘价
            for i in range(1, len(period_data)):
                current_close = period_data.iloc[i]['收盘']
                prev_close = period_data.iloc[i-1]['收盘']
                
                if current_close > prev_close:
                    # 上涨：当前收盘价高于前一日收盘价
                    is_up.iloc[i] = True
                else:
                    # 下跌或平盘：当前收盘价低于或等于前一日收盘价，统一算作阴线
                    is_down.iloc[i] = True
            
            # 从最新数据开始向前计算连阳(阴)天数
            current_consecutive_up = 0
            current_consecutive_down = 0
            prev_consecutive_up = 0
            prev_consecutive_down = 0
            
            # 先计算当前连阳(阴)状态
            for i in range(len(period_data) - 1, -1, -1):
                if is_up.iloc[i]:  # 上涨（收盘价高于前一日）
                    if current_consecutive_down > 0:  # 如果之前是连阴，则重置
                        break
                    current_consecutive_up += 1
                else:  # 下跌或平盘（收盘价低于或等于前一日），统一算作阴线
                    if current_consecutive_up > 0:  # 如果之前是连阳，则重置
                        break
                    current_consecutive_down += 1
            
            # 计算前一个周期的状态
            if len(period_data) > 1:
                # 找到当前连阳(阴)的起始位置
                current_start = len(period_data) - 1
                if current_consecutive_up > 0:
                    current_start = len(period_data) - current_consecutive_up
                elif current_consecutive_down > 0:
                    current_start = len(period_data) - current_consecutive_down
                
                # 如果当前连阳(阴)不是从第一个周期开始，则计算前一个周期
                if current_start > 0:
                    # 从当前连阳(阴)起始位置向前计算前一个周期
                    prev_consecutive_up = 0
                    prev_consecutive_down = 0
                    
                    for i in range(current_start - 1, -1, -1):
                        if is_up.iloc[i]:  # 上涨（收盘价高于前一日）
                            if prev_consecutive_down > 0:  # 如果之前是连阴，则重置
                                break
                            prev_consecutive_up += 1
                        else:  # 下跌或平盘（收盘价低于或等于前一日），统一算作阴线
                            if prev_consecutive_up > 0:  # 如果之前是连阳，则重置
                                break
                            prev_consecutive_down += 1
            
            return (current_consecutive_up, current_consecutive_down, prev_consecutive_up, prev_consecutive_down)
            
        except Exception as e:
            print(f"[DEBUG] 计算{period}线连阳(阴)失败: {e}")
            return (0, 0, 0, 0)
    
    def _calculate_weekly_change_percentage(self, data: pd.DataFrame) -> str:
        """
        计算当前周涨跌幅百分比
        
        Args:
            data: 包含OHLC数据的DataFrame
            
        Returns:
            str: 周涨跌幅百分比字符串，如 "+5.23%" 或 "-3.45%"
        """
        try:
            if data is None or data.empty:
                return "0.00%"
            
            # 确保数据按日期排序
            data_sorted = data.sort_index()
            
            # 计算周线数据
            period_data = data_sorted.resample('W').agg({
                '开盘': 'first',
                '最高': 'max', 
                '最低': 'min',
                '收盘': 'last',
                '成交量': 'sum'
            }).dropna()
            
            if len(period_data) < 2:
                return "0.00%"
            
            # 获取当前周和上一周的收盘价
            current_week_close = period_data.iloc[-1]['收盘']
            prev_week_close = period_data.iloc[-2]['收盘']
            
            # 计算涨跌幅百分比
            change_pct = ((current_week_close - prev_week_close) / prev_week_close) * 100
            
            # 格式化字符串
            if change_pct >= 0:
                return f"+{change_pct:.2f}%"
            else:
                return f"{change_pct:.2f}%"
                
        except Exception as e:
            print(f"[DEBUG] 计算周涨跌幅失败: {e}")
            return "0.00%"
    
    def _calculate_daily_change_percentage(self, data: pd.DataFrame) -> str:
        """
        计算当前日涨跌幅百分比
        
        Args:
            data: 包含OHLC数据的DataFrame
            
        Returns:
            str: 日涨跌幅百分比字符串，如 "+2.15%" 或 "-1.85%"
        """
        try:
            if data is None or data.empty:
                return "0.00%"
            
            # 确保数据按日期排序
            data_sorted = data.sort_index()
            
            if len(data_sorted) < 2:
                return "0.00%"
            
            # 获取当前日和上一日的收盘价
            current_day_close = data_sorted.iloc[-1]['收盘']
            prev_day_close = data_sorted.iloc[-2]['收盘']
            
            # 计算涨跌幅百分比
            change_pct = ((current_day_close - prev_day_close) / prev_day_close) * 100
            
            # 格式化字符串
            if change_pct >= 0:
                return f"+{change_pct:.2f}%"
            else:
                return f"{change_pct:.2f}%"
                
        except Exception as e:
            print(f"[DEBUG] 计算日涨跌幅失败: {e}")
            return "0.00%"
    
    def _calculate_monthly_change_percentage(self, data: pd.DataFrame) -> str:
        """
        计算当前月涨跌幅百分比
        
        Args:
            data: 包含OHLC数据的DataFrame
            
        Returns:
            str: 月涨跌幅百分比字符串，如 "+8.45%" 或 "-5.23%"
        """
        try:
            if data is None or data.empty:
                return "0.00%"
            
            # 确保数据按日期排序
            data_sorted = data.sort_index()
            
            # 计算月线数据
            period_data = data_sorted.resample('M').agg({
                '开盘': 'first',
                '最高': 'max', 
                '最低': 'min',
                '收盘': 'last',
                '成交量': 'sum'
            }).dropna()
            
            if len(period_data) < 2:
                return "0.00%"
            
            # 获取当前月和上一月的收盘价
            current_month_close = period_data.iloc[-1]['收盘']
            prev_month_close = period_data.iloc[-2]['收盘']
            
            # 计算涨跌幅百分比
            change_pct = ((current_month_close - prev_month_close) / prev_month_close) * 100
            
            # 格式化字符串
            if change_pct >= 0:
                return f"+{change_pct:.2f}%"
            else:
                return f"{change_pct:.2f}%"
                
        except Exception as e:
            print(f"[DEBUG] 计算月涨跌幅失败: {e}")
            return "0.00%"

    def _calculate_3day_price_change(self, data: pd.DataFrame) -> pd.Series:
        """
        计算3日价格最差盈利指标
        
        指标定义：
        1. 取当日股票价格和3个交易日前的股票价格
        2. 计算价格下沿：min(最高价, 最低价) - 当日最低价
        3. 计算价格上沿：max(最高价, 最低价) - 3日前最高价
        4. 计算最差盈利 = (当日价格下沿 - 3日前价格上沿) / 3日前价格上沿
        5. 表示3天前追高的买家在今天最低点卖出时是否能盈利
        
        Args:
            data: 包含价格数据的DataFrame，必须包含'最高'和'最低'列
            
        Returns:
            3日价格最差盈利的Series，单位为小数（0.05表示5%）
        """
        try:
            if '最高' not in data.columns or '最低' not in data.columns:
                print("[WARNING] 数据中缺少'最高'或'最低'列，无法计算3日价格最差盈利")
                return pd.Series([0] * len(data), index=data.index)
            
            # 获取当日和3个交易日前的最高价和最低价
            current_high = data['最高'].copy()
            current_low = data['最低'].copy()
            high_3d_ago = current_high.shift(3)
            low_3d_ago = current_low.shift(3)
            
            # 计算价格下沿：当日最低价
            current_price_low = current_low
            
            # 计算价格上沿：3日前最高价
            price_high_3d_ago = high_3d_ago
            
            # 计算最差盈利：(当日价格下沿 - 3日前价格上沿) / 3日前价格上沿
            price_change_3d = (current_price_low - price_high_3d_ago) / price_high_3d_ago
            
            # 处理NaN值（前3个交易日没有数据）
            price_change_3d = price_change_3d.fillna(0)
            
            # 处理无穷值
            price_change_3d = price_change_3d.replace([np.inf, -np.inf], 0)
            
            # 检查是否有非零值
            non_zero_count = (price_change_3d != 0).sum()
            print(f"[DEBUG] 3日价格最差盈利计算完成，数据长度: {len(price_change_3d)}, 非零值: {non_zero_count}")
            print(f"[DEBUG] 最差盈利范围: {price_change_3d.min():.4f} 到 {price_change_3d.max():.4f}")
            
            return price_change_3d
            
        except Exception as e:
            print(f"[ERROR] 计算3日价格最差盈利时出错: {e}")
            import traceback
            traceback.print_exc()
            # 返回全零序列作为fallback
            return pd.Series([0] * len(data), index=data.index)

    def _calculate_3day_entity_change(self, data: pd.DataFrame) -> pd.Series:
        """
        计算3日实体最差盈利指标（笨蛋线）
        
        指标定义：
        1. 取当日和3个交易日前的开盘价和收盘价
        2. 计算实体下沿：min(开盘价, 收盘价) - 当日实体下沿
        3. 计算实体上沿：max(开盘价, 收盘价) - 3日前实体上沿
        4. 计算最差盈利 = (当日实体下沿 - 3日前实体上沿) / 3日前实体上沿
        5. 表示3天前追高的买家在今天实体最低点卖出时是否能盈利
        
        Args:
            data: 包含价格数据的DataFrame，必须包含'开盘'和'收盘'列
            
        Returns:
            3日实体最差盈利的Series，单位为小数（0.05表示5%）
        """
        try:
            if '开盘' not in data.columns or '收盘' not in data.columns:
                print("[WARNING] 数据中缺少'开盘'或'收盘'列，无法计算3日实体最差盈利")
                return pd.Series([0] * len(data), index=data.index)
            
            # 获取当日和3个交易日前的开盘价和收盘价
            current_open = data['开盘'].copy()
            current_close = data['收盘'].copy()
            open_3d_ago = current_open.shift(3)
            close_3d_ago = current_close.shift(3)
            
            # 计算实体下沿：当日实体下沿 = min(开盘价, 收盘价)
            current_entity_low = np.minimum(current_open, current_close)
            
            # 计算实体上沿：3日前实体上沿 = max(开盘价, 收盘价)
            entity_high_3d_ago = np.maximum(open_3d_ago, close_3d_ago)
            
            # 计算最差盈利：(当日实体下沿 - 3日前实体上沿) / 3日前实体上沿
            entity_change_3d = (current_entity_low - entity_high_3d_ago) / entity_high_3d_ago
            
            # 处理NaN值（前3个交易日没有数据）
            entity_change_3d = entity_change_3d.fillna(0)
            
            # 处理无穷值
            entity_change_3d = entity_change_3d.replace([np.inf, -np.inf], 0)
            
            # 检查是否有非零值
            non_zero_count = (entity_change_3d != 0).sum()
            print(f"[DEBUG] 3日实体最差盈利计算完成，数据长度: {len(entity_change_3d)}, 非零值: {non_zero_count}")
            print(f"[DEBUG] 最差盈利范围: {entity_change_3d.min():.4f} 到 {entity_change_3d.max():.4f}")
            
            return entity_change_3d
            
        except Exception as e:
            print(f"[ERROR] 计算3日实体最差盈利时出错: {e}")
            import traceback
            traceback.print_exc()
            # 返回全零序列作为fallback
            return pd.Series([0] * len(data), index=data.index)

    def _calculate_3day_smart_profit(self, data: pd.DataFrame) -> pd.Series:
        """
        计算3日聪明盈利指标（聪明线）
        
        指标定义：
        1. 取当日和3个交易日前的开盘价和收盘价
        2. 计算当前实体高点：max(开盘价, 收盘价)
        3. 计算3日前实体低点：min(开盘价, 收盘价)
        4. 计算聪明盈利 = (当前实体高点 - 3日前实体低点) / 3日前实体低点
        5. 表示3天前低点买入的买家在今天实体最高点卖出时的盈利情况
        
        Args:
            data: 包含价格数据的DataFrame，必须包含'开盘'和'收盘'列
            
        Returns:
            3日聪明盈利的Series，单位为小数（0.05表示5%）
        """
        try:
            if '开盘' not in data.columns or '收盘' not in data.columns:
                print("[WARNING] 数据中缺少'开盘'或'收盘'列，无法计算3日聪明盈利")
                return pd.Series([0] * len(data), index=data.index)
            
            # 获取当日和3个交易日前的开盘价和收盘价
            current_open = data['开盘'].copy()
            current_close = data['收盘'].copy()
            open_3d_ago = current_open.shift(3)
            close_3d_ago = current_close.shift(3)
            
            # 计算当前实体高点：max(开盘价, 收盘价)
            current_entity_high = np.maximum(current_open, current_close)
            
            # 计算3日前实体低点：min(开盘价, 收盘价)
            entity_low_3d_ago = np.minimum(open_3d_ago, close_3d_ago)
            
            # 计算聪明盈利：(当前实体高点 - 3日前实体低点) / 3日前实体低点
            smart_profit_3d = (current_entity_high - entity_low_3d_ago) / entity_low_3d_ago
            
            # 处理NaN值（前3个交易日没有数据）
            smart_profit_3d = smart_profit_3d.fillna(0)
            
            # 处理无穷值
            smart_profit_3d = smart_profit_3d.replace([np.inf, -np.inf], 0)
            
            # 检查是否有非零值
            non_zero_count = (smart_profit_3d != 0).sum()
            print(f"[DEBUG] 3日聪明盈利计算完成，数据长度: {len(smart_profit_3d)}, 非零值: {non_zero_count}")
            print(f"[DEBUG] 聪明盈利范围: {smart_profit_3d.min():.4f} 到 {smart_profit_3d.max():.4f}")
            
            return smart_profit_3d
            
        except Exception as e:
            print(f"[ERROR] 计算3日聪明盈利时出错: {e}")
            import traceback
            traceback.print_exc()
            # 返回全零序列作为fallback
            return pd.Series([0] * len(data), index=data.index)

    def _cancel_async_tasks(self):
        """取消所有异步任务"""
        self._async_cancelled = True
        
        # 等待任务完成
        if self._async_fund_task and self._async_fund_task.is_alive():
            try:
                self._async_fund_task.join(timeout=0.5)  # 增加超时时间
                if self._async_fund_task.is_alive():
                    print(f"警告: 资金来源异步任务未能及时结束")
            except Exception as e:
                print(f"取消资金来源异步任务时出错: {str(e)}")
                
        if self._async_cost_task and self._async_cost_task.is_alive():
            try:
                self._async_cost_task.join(timeout=0.5)  # 增加超时时间
                if self._async_cost_task.is_alive():
                    print(f"警告: 成本涨幅异步任务未能及时结束")
            except Exception as e:
                print(f"取消成本涨幅异步任务时出错: {str(e)}")
        
        # 重置任务引用
        self._async_fund_task = None
        self._async_cost_task = None
        
        # 重置取消标志
        self._async_cancelled = False
        
        # 清理资金来源相关缓存
        self._fund_source_df = None
        self._fund_source_shares_df = None
        self._fund_inst_series = None
        self._fund_hot_series = None
        self._fund_retail_series = None
        
        print(f"已取消所有异步任务并清理缓存: {self.current_code}")

    def _show_fund_loading(self):
        """在资金来源子图上显示加载状态"""
        if self.ax_fund is not None:
            # 清除旧的加载文本
            if self._fund_loading_text:
                self._fund_loading_text.remove()
                self._fund_loading_text = None
            
            # 显示加载提示
            self._fund_loading_text = self.ax_fund.text(
                0.5, 0.5,
                "加载中...",
                transform=self.ax_fund.transAxes,
                ha='center',
                va='center',
                fontsize=8,
                color='gray',
                bbox=dict(
                    facecolor='white',
                    alpha=0.8,
                    pad=10,
                    edgecolor='gray'
                )
            )
            
            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()

    def _show_cost_loading(self):
        """在成本涨幅子图上显示加载状态"""
        if self.ax5 is not None:
            # 清除旧的加载文本
            if self._cost_loading_text:
                self._cost_loading_text.remove()
                self._cost_loading_text = None
            
            # 显示加载提示
            self._cost_loading_text = self.ax5.text(
                0.5, 0.5,
                "加载中...",
                transform=self.ax5.transAxes,
                ha='center',
                va='center',
                fontsize=8,
                color='gray',
                bbox=dict(
                    facecolor='white',
                    alpha=0.8,
                    pad=10,
                    edgecolor='gray'
                )
            )
            
            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()

    def _hide_fund_loading(self):
        """隐藏资金来源子图的加载状态"""
        if self._fund_loading_text:
            self._fund_loading_text.remove()
            self._fund_loading_text = None
            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()

    def _hide_cost_loading(self):
        """隐藏成本涨幅子图的加载状态"""
        if self._cost_loading_text:
            self._cost_loading_text.remove()
            self._cost_loading_text = None
            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()

    def _async_load_fund_source(self, data: pd.DataFrame, x_index: np.ndarray):
        """异步加载资金来源数据"""
        try:
            # 检查任务是否被取消
            if self._async_cancelled:
                print(f"资金来源异步任务已被取消: {self.current_code}")
                return
                
            # 验证数据有效性
            if data is None or data.empty:
                print(f"资金来源异步任务数据无效: {self.current_code}")
                return
                
            if DEBUG_FUND_BROKER_DETAILS:
                print(f"异步加载资金来源数据 - {self.current_code} ({self.current_symbol_name})")
                print(f"{'='*80}")
            
            # 获取当前显示时间范围
            start_dt = data.index[0]
            end_dt = data.index[-1]
            start_str = start_dt.strftime('%Y%m%d')
            end_str = end_dt.strftime('%Y%m%d')
            
            # 将交易日期映射到K线索引
            date_to_idx = {d.strftime('%Y-%m-%d'): i for i, d in enumerate(data.index)}

            # 事件日 -> 值 的映射（使用营业部详细数据计算）
            inst_events: dict[int, float] = {}
            hot_events: dict[int, float] = {}
            retail_events: dict[int, float] = {}
            
            # 事件日 -> 营业部详细信息的映射
            inst_broker_details: dict[int, list] = {}
            hot_broker_details: dict[int, list] = {}
            retail_broker_details: dict[int, list] = {}
            
            # 遍历每个交易日，获取营业部详细数据并计算股数
            event_count = 0
            for i, date in enumerate(data.index):
                # 频繁检查任务是否被取消
                if self._async_cancelled:
                    print(f"资金来源异步任务在遍历过程中被取消: {self.current_code}")
                    return
                    
                date_str = date.strftime('%Y%m%d')
                try:
                    # 获取该日期的营业部详细数据
                    broker_details = lhb_processor.get_fund_source_details(
                        str(self.current_code), date_str, date_str
                    )
                    
                    # 计算机构净买入股数
                    inst_net_shares = 0
                    if 'institution' in broker_details and broker_details['institution']:
                        for broker in broker_details['institution']:
                            inst_net_shares += broker.get('net_shares', 0)
                        if inst_net_shares != 0:
                            inst_events[i] = inst_net_shares
                            inst_broker_details[i] = broker_details['institution']
                            event_count += 1
                    
                    # 计算游资净买入股数
                    hot_net_shares = 0
                    if 'hot' in broker_details and broker_details['hot']:
                        for broker in broker_details['hot']:
                            hot_net_shares += broker.get('net_shares', 0)
                        if hot_net_shares != 0:
                            hot_events[i] = hot_net_shares
                            hot_broker_details[i] = broker_details['hot']
                            event_count += 1
                    
                    # 计算散户净买入股数
                    retail_net_shares = 0
                    if 'retail' in broker_details and broker_details['retail']:
                        for broker in broker_details['retail']:
                            retail_net_shares += broker.get('net_shares', 0)
                        if retail_net_shares != 0:
                            retail_events[i] = retail_net_shares
                            retail_broker_details[i] = broker_details['retail']
                            event_count += 1
                            
                except Exception as e:
                    print(f"获取{date_str}营业部详情失败: {str(e)}")
                    continue
            
            if self._async_cancelled:
                return
                
            if DEBUG_FUND_BROKER_DETAILS:
                print(f"龙虎榜事件日数量: 机构={len(inst_events)}, 游资={len(hot_events)}, 散户={len(retail_events)}")
                print()

            if inst_events or hot_events or retail_events:
                # 台阶式：在无数据的日期延续前一个值；当以"股数"展示时采用累计求和
                total_points = len(data.index)
                inst_series = np.zeros(total_points, dtype=float)
                hot_series = np.zeros(total_points, dtype=float)
                retail_series = np.zeros(total_points, dtype=float)

                curr_inst = 0.0
                curr_hot = 0.0
                curr_retail = 0.0
                # 现在所有数据都是股数，使用累计模式
                use_shares = True
                for i in range(total_points):
                    # 累计模式（股数）
                    if i in inst_events:
                        curr_inst += inst_events[i]
                    if i in hot_events:
                        curr_hot += hot_events[i]
                    if i in retail_events:
                        curr_retail += retail_events[i]
                    inst_series[i] = curr_inst
                    hot_series[i] = curr_hot
                    retail_series[i] = curr_retail

                # 标签固定为股数
                lbl_inst = '机构净股'
                lbl_hot = '游资净股'
                lbl_retail = '散户净股'

                # 在主线程中更新图表
                if self.window and self.window.winfo_exists() and not self._async_cancelled:
                    self.window.after(0, lambda: self._update_fund_chart(
                        x_index, inst_series, hot_series, retail_series, 
                        inst_events, hot_events, retail_events,
                        inst_broker_details, hot_broker_details, retail_broker_details,
                        use_shares
                    ))
            else:
                # 如果没有数据，也要隐藏加载状态
                print(f"资金来源异步任务未获取到数据: {self.current_code}")
                if self.window and self.window.winfo_exists():
                    self.window.after(0, self._hide_fund_loading)
                    
        except Exception as e:
            print(f"异步加载资金来源数据失败: {str(e)}")
            # 在主线程中隐藏加载状态
            if self.window and self.window.winfo_exists():
                self.window.after(0, self._hide_fund_loading)

    def _async_load_cost_signals(self, data: pd.DataFrame, x_index: np.ndarray):
        """异步加载成本涨幅图信号点"""
        try:
            if self._async_cancelled:
                return
                
            print(f"异步加载成本涨幅信号点 - {self.current_code} ({self.current_symbol_name})")
            
            # 计算平均成本日涨幅（指数不计算）
            is_index = str(self.current_code or "") in ["1A0001", "000001"]
            if not is_index and '平均成本' in data.columns:
                cost_change = data['平均成本'].pct_change() * 100  # 百分比变化
                cost_change = cost_change.replace([np.inf, -np.inf], np.nan).ffill()

                # 添加条件标记
                for i in range(len(data)):
                    if self._async_cancelled:
                        return
                        
                    # 构建数据序列（当前+前n_days日）
                    n_days = 5  # 可配置参数
                    seq_length = n_days + 1  # 需要n_days+1个数据点
                    start_idx = max(0, i-seq_length+1)
                    data_sequence = [data.iloc[i-j] for j in range(0, seq_length)] if i >= seq_length-1 else []
                    
                    if not data_sequence:
                        continue
                    
                    # 检查所有条件
                    reasons = []
                    marker_color = ''
                    marker_signal = None
                    highest_priority = 0
                    # 为了性能，仅对最近N根K线检查资金来源类信号；N取当前缩放显示的时间范围
                    recent_check_window = min(len(data), int(self.time_range))
                    for condition in self.conditions:
                        # 避免对历史所有K线触发耗时的龙虎榜检查
                        try:
                            from conditions import \
                                InstitutionTradingCondition as _InstCond
                            if isinstance(condition, _InstCond) and i < len(data) - recent_check_window:
                                continue
                        except Exception:
                            pass
                        signal = condition.check(data_sequence)
                        if signal.triggered:
                            reasons.append(signal.description)
                            # 根据优先级选择标记颜色
                            if condition.priority > highest_priority:
                                marker_color = signal.mark.value
                                marker_signal = signal
                                highest_priority = condition.priority

                    if reasons and marker_signal:
                        # 存储警示信息到数据点
                        data.at[data.index[i], 'warning_text'] = '\n'.join(reasons)

            # 在主线程中更新图表
            if self.window and self.window.winfo_exists() and not self._async_cancelled:
                self.window.after(0, lambda: self._update_cost_signals(data, x_index))
                
        except Exception as e:
            print(f"异步加载成本涨幅信号点失败: {str(e)}")
            # 在主线程中隐藏加载状态
            if self.window and self.window.winfo_exists():
                self.window.after(0, self._hide_cost_loading)

    def _update_fund_chart(self, x_index: np.ndarray, inst_series: np.ndarray, 
                          hot_series: np.ndarray, retail_series: np.ndarray,
                          inst_events: dict, hot_events: dict, retail_events: dict,
                          inst_broker_details: dict, hot_broker_details: dict, 
                          retail_broker_details: dict, use_shares: bool):
        """更新资金来源子图"""
        try:
            if self.ax_fund is None:
                return
                
            # 隐藏加载状态
            self._hide_fund_loading()
            
            # 清除现有内容
            self.ax_fund.clear()
            
            # 计算当日三股资金方持有股数最大值，确定背景色
            latest_inst = inst_series[-1] if len(inst_series) > 0 else 0
            latest_hot = hot_series[-1] if len(hot_series) > 0 else 0
            latest_retail = retail_series[-1] if len(retail_series) > 0 else 0
            
            # 取绝对值进行比较（因为可能是负数）
            abs_inst = latest_inst
            abs_hot = latest_hot
            abs_retail = latest_retail
            
            # 确定最大持有股数的一方
            max_shares = max(abs_inst, abs_hot, abs_retail)
            
            # 根据最大持有股数的一方设置背景色
            if max_shares == abs_inst:
                background_color = 'red'  # 机构（红色）
            elif max_shares == abs_hot:
                background_color = 'orange'  # 游资（黄色）
            else:
                background_color = 'green'  # 散户（绿色）
            
            # 设置背景色（半透明0.5）
            self.ax_fund.set_facecolor(background_color)
            # 使用get_facecolor()获取当前背景色，然后设置透明度
            current_facecolor = self.ax_fund.get_facecolor()
            if hasattr(current_facecolor, '__iter__') and len(current_facecolor) >= 4:
                # 如果颜色包含alpha通道，直接修改
                current_facecolor = list(current_facecolor)
                current_facecolor[3] = 0.5  # 设置alpha为0.5
                self.ax_fund.set_facecolor(current_facecolor)
            else:
                # 如果没有alpha通道，使用RGBA格式
                if background_color == 'red':
                    self.ax_fund.set_facecolor((1.0, 0.0, 0.0, 0.5))  # 红色，alpha=0.5
                elif background_color == 'orange':
                    self.ax_fund.set_facecolor((1.0, 0.65, 0.0, 0.5))  # 橙色，alpha=0.5
                else:  # green
                    self.ax_fund.set_facecolor((0.0, 1.0, 0.0, 0.5))  # 绿色，alpha=0.5
            
            # 重新绘制资金来源图
            x_all = np.arange(len(x_index))
            self.ax_fund.step(x_all, inst_series, where='post', color='red', linewidth=1.2, label='机构净股')
            self.ax_fund.step(x_all, hot_series, where='post', color='orange', linewidth=1.2, label='游资净股')
            self.ax_fund.step(x_all, retail_series, where='post', color='green', linewidth=1.2, label='散户净股')
            self.ax_fund.axhline(0, color='gray', linestyle='--', linewidth=0.8, alpha=0.6)
            self.ax_fund.grid(True, axis='y', linestyle='--', alpha=0.3)
            
            # 添加包含最新数值的左侧标注
            
            if use_shares:
                # 股数显示成万股
                inst_text = f"机构: {latest_inst/1e4:.1f}万股"
                hot_text = f"游资: {latest_hot/1e4:.1f}万股"
                retail_text = f"散户: {latest_retail/1e4:.1f}万股"
            else:
                # 金额单位转为百万元
                inst_text = f"机构: {latest_inst/1e6:.1f}百万元"
                hot_text = f"游资: {latest_hot/1e6:.1f}百万元"
                retail_text = f"散户: {latest_retail/1e6:.1f}百万元"
            
            # 在左侧显示三行文本
            combined_text = f"{inst_text}\n{hot_text}\n{retail_text}"
            self.ax_fund.text(
                0.01, 0.95,
                combined_text,
                transform=self.ax_fund.transAxes,
                fontsize=8,
                horizontalalignment='left',
                verticalalignment='top',
                bbox=dict(facecolor='white', alpha=0.8, pad=3)
            )
            
            # 存储序列以支持鼠标交互
            self._fund_inst_series = inst_series
            self._fund_hot_series = hot_series
            self._fund_retail_series = retail_series
            self._fund_use_shares = use_shares

            if use_shares:
                # 股数显示成万股
                self.ax_fund.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x/1e4:.1f}万股'))
                self.ax_fund.set_ylabel('资金来源(股)', fontsize=8)
            else:
                # 金额单位转为百万元
                self.ax_fund.yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x/1e6:.1f}百万元'))
                self.ax_fund.set_ylabel('资金来源(金额)', fontsize=8)
            
            # 设置x轴格式
            def format_date(x, p):
                # 更严格的边界检查，确保x是整数且在有效范围内
                if (self.current_data is not None and not self.current_data.empty and len(x_index) > 0 and
                    isinstance(x, (int, float)) and x >= 0 and x < len(x_index)):
                    try:
                        # 确保x是整数且不超出边界
                        x_int = int(round(x))
                        if x_int >= len(self.current_data.index):
                            x_int = len(self.current_data.index) - 1
                        elif x_int < 0:
                            x_int = 0
                        
                        date = pd.Timestamp(self.current_data.index[x_int])
                        if self.period_mode == 'week':
                            return f"{date.year}-W{date.week}"
                        elif self.period_mode == 'month':
                            return date.strftime('%Y-%m')
                        return date.strftime('%Y-%m-%d')
                    except (IndexError, KeyError, ValueError) as e:
                        print(f"[DEBUG] format_date错误: {e}, x={x}, data_length={len(self.current_data) if self.current_data is not None else 0}")
                        return ''
                return ''
            
            n_dates = len(x_index)
            tick_positions = [0, n_dates // 2, n_dates - 1]
            self.ax_fund.xaxis.set_major_formatter(FuncFormatter(format_date))
            self.ax_fund.set_xticks(tick_positions)
            self.ax_fund.set_xlim(-0.5, len(x_index) - 0.5)
            
            # 隐藏x轴标签
            plt.setp(self.ax_fund.get_xticklabels(), visible=False)
            
            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()
                
        except Exception as e:
            print(f"更新资金来源子图失败: {str(e)}")

    def _update_cost_signals(self, data: pd.DataFrame, x_index: np.ndarray):
        """更新成本涨幅图信号点"""
        try:
            if self.ax5 is None:
                return
                
            # 隐藏加载状态
            self._hide_cost_loading()
            
            # 计算平均成本日涨幅（指数不计算）
            is_index = str(self.current_code or "") in ["1A0001", "000001"]
            if not is_index and '平均成本' in data.columns:
                cost_change = data['平均成本'].pct_change() * 100  # 百分比变化
                cost_change = cost_change.replace([np.inf, -np.inf], np.nan).ffill()

                # 添加条件标记
                for i in range(len(data)):
                    # 检查当前位置是否有存储的警示信息
                    warning_text = data.iloc[i].get('warning_text', '')
                    
                    if warning_text and warning_text != 'nan':
                        # 检查所有条件
                        reasons = []
                        marker_color = ''
                        marker_signal = None
                        highest_priority = 0
                        
                        # 构建数据序列（当前+前n_days日）
                        n_days = 5  # 可配置参数
                        seq_length = n_days + 1  # 需要n_days+1个数据点
                        start_idx = max(0, i-seq_length+1)
                        data_sequence = [data.iloc[i-j] for j in range(0, seq_length)] if i >= seq_length-1 else []
                        
                        if not data_sequence:
                            continue
                        
                        # 检查所有条件
                        for condition in self.conditions:
                            signal = condition.check(data_sequence)
                            if signal.triggered:
                                reasons.append(signal.description)
                                # 根据优先级选择标记颜色
                                if condition.priority > highest_priority:
                                    marker_color = signal.mark.value
                                    marker_signal = signal
                                    highest_priority = condition.priority

                        if reasons and marker_signal:
                            # 是否包含资金来源条目
                            text_all = "\n".join(reasons)
                            has_fund_info = any(k in text_all for k in [
                                '机构净买', '机构净卖', '游资净买', '游资净卖', '散户净买', '散户净卖'
                            ])
                            
                            # 颜色解析
                            if marker_signal.mark == SignalMark.ORANGE_DOT:
                                point_color = 'orange'
                            elif marker_signal.mark == SignalMark.YELLOW_DOT:
                                point_color = 'yellow'
                            elif marker_color.startswith('r'):
                                point_color = 'red'
                            elif marker_color.startswith('g'):
                                point_color = 'green'
                            else:
                                point_color = 'white'
                            
                            # 形状: 若包含资金来源信息, 则用三角形(买:^ 卖:v), 否则沿用圆点
                            if has_fund_info:
                                # 三角方向跟随最大势力自身方向：橙/红=上，黄/绿=下
                                tri = '^' if marker_signal.mark in [SignalMark.ORANGE_DOT, SignalMark.RED_DOT] else 'v'
                                self.ax5.plot(
                                    x_index[i], cost_change.iloc[i],
                                    marker=tri,
                                    linestyle='None',
                                    color=point_color,
                                    markersize=8,
                                    alpha=0.8,
                                    zorder=5
                                )
                            else:
                                # 圆点
                                if marker_signal.mark in [SignalMark.ORANGE_DOT, SignalMark.YELLOW_DOT]:
                                    self.ax5.plot(
                                        x_index[i], cost_change.iloc[i],
                                        marker='o',
                                        linestyle='None',
                                        color=point_color,
                                        markersize=8,
                                        alpha=0.7,
                                        zorder=5
                                    )
                                else:
                                    self.ax5.plot(
                                        x_index[i], cost_change.iloc[i],
                                        marker_color,
                                        markersize=8,
                                        alpha=0.7,
                                        zorder=5
                                    )
                            
                            # 对买入(红色、橙色)和卖出(绿色、黄色)信号绘制水平线
                            should_draw_line = (marker_color in ['ro', 'go'] or 
                                              marker_signal.mark in [SignalMark.ORANGE_DOT, SignalMark.YELLOW_DOT])
                            if should_draw_line:
                                # 添加水平有效期线
                                valid_end = min(i + self.signal_valid_days, len(x_index))  # 确保不超出数据范围
                                
                                # 确定线条颜色
                                if marker_signal.mark == SignalMark.ORANGE_DOT:
                                    line_color = 'orange'
                                elif marker_signal.mark == SignalMark.YELLOW_DOT:
                                    line_color = 'yellow'
                                else:
                                    line_color = marker_color.replace('o', '')  # 使用与标记点相同的颜色,去掉'o'标记符
                                
                                self.ax5.hlines(y=cost_change.iloc[i],  # y坐标值
                                                xmin=x_index[i],  # 起始x坐标
                                                xmax=x_index[valid_end-1],  # 结束x坐标
                                                color=line_color,
                                                linestyles='solid',  # 实线样式
                                                linewidth=1,  # 线宽
                                                alpha=0.5,  # 透明度
                                                zorder=4)  # 确保在标记点下方
                            
                            # 存储警示信息到数据点
                            data.at[data.index[i], 'warning_text'] = '\n'.join(reasons)

            # 刷新画布
            if hasattr(self, 'chart_canvas') and self.chart_canvas:
                self.chart_canvas.draw_idle()
                
        except Exception as e:
            print(f"更新成本涨幅图信号点失败: {str(e)}")

    def _start_async_loading(self, data: pd.DataFrame, x_index: np.ndarray):
        """启动异步加载任务"""
        try:
            # 取消之前的异步任务
            self._cancel_async_tasks()
            
            # 验证数据有效性
            if data is None or data.empty:
                print(f"无法启动异步加载，数据无效: {self.current_code}")
                return
                
            # 显示加载状态
            self._show_fund_loading()
            self._show_cost_loading()
            
                    # 启动资金来源异步任务
            self._async_fund_task = threading.Thread(
                target=self._async_load_fund_source,
                args=(data, x_index),
                daemon=True,
                name=f"fund_source_{self.current_code}"
            )
            self._async_fund_task.start()
            print(f"已启动资金来源异步任务: {self.current_code}")
            
            # 启动成本涨幅信号异步任务
            self._async_cost_task = threading.Thread(
                target=self._async_load_cost_signals,
                args=(data, x_index),
                daemon=True,
                name=f"cost_signals_{self.current_code}"
            )
            self._async_cost_task.start()
            print(f"已启动成本涨幅信号异步任务: {self.current_code}")
            
            # 设置超时检查，确保任务不会无限期运行
            def check_timeout():
                if (self._async_fund_task and self._async_fund_task.is_alive()) or \
                   (self._async_cost_task and self._async_cost_task.is_alive()):
                    print(f"异步任务超时，强制取消: {self.current_code}")
                    self._async_cancelled = True
                    self._hide_fund_loading()
                    self._hide_cost_loading()
            
            # 30秒后检查超时
            if self.window and self.window.winfo_exists():
                self.window.after(30000, check_timeout)
            
        except Exception as e:
            print(f"启动异步加载任务失败: {str(e)}")
            # 隐藏加载状态
            self._hide_fund_loading()
            self._hide_cost_loading()


# 使用说明：
# 要启用资金营业部详情的调试信息打印，请将文件顶部的 DEBUG_FUND_BROKER_DETAILS 设置为 True
# 例如：DEBUG_FUND_BROKER_DETAILS = True
# 
# 调试信息包括：
# - 资金子图股数计算过程
# - 龙虎榜事件日数量统计
# - 机构/游资/散户股数累计事件详情
# - 营业部详细交易信息
# - 数据一致性检查结果
# 
# 注意：已移除KDJ金叉死叉信号，成本涨幅图表中不再显示KDJ相关信号点

