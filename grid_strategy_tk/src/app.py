import os
import sys

# 添加项目根目录到系统路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

# 添加StockETFQuery目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
stock_etf_path = os.path.join(os.path.dirname(current_dir), "StockETFQuery")
sys.path.append(stock_etf_path)

import io
import json
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
# 之后再导入stock_price_query
from StockETFQuery.stock_price_query import (analyze_monthly_performance,
                                             find_similar_etf_gains,
                                             get_all_etf_monthly_data)

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base_window import BaseWindow
# 在文件开头导入新类
from etf_analysis_window import ETFAnalysisWindow
from locales.localization import l
from shortcuts_manager import ShortcutsManager
from trading_utils import (calculate_ma_price, calculate_price_range,
                           get_symbol_info, get_symbol_info_by_name,
                           is_valid_symbol)
from watchlist_window import WatchlistWindow


class MainWindow(BaseWindow):
    def __init__(self, root):
        super().__init__(root)
        self.root = root  # 必须保留对根窗口的引用
        self.total_trials = 0
        self.current_trial = 0
        self.progress = None
        self.percent_label = None
        self.label = None
        self.time_label = None
        self.eta_label = None
        self.start_time = None
        self.is_closed = False
        self.trade_details = None
        self.captured_output = []
        
        # 将变量声明为None，稍后在create_window中初始化
        self.symbol_var = None
        self.symbol_name_var = None
        self.start_date_var = None
        self.end_date_var = None
        self.ma_period_var = None
        self.ma_protection_var = None
        self.initial_positions_var = None
        self.initial_cash_var = None
        self.min_buy_times_var = None
        self.price_range_min_var = None
        self.price_range_max_var = None
        self.n_trials_var = None
        self.top_n_var = None
        
        # 添加分段回测相关变量的初始化
        self.enable_segments = None
        self.profit_calc_method_var = None
        self.connect_segments = None
        self.segment_label = None
        self.segment_mode_combo = None
        self.segment_days_label = None
        self.connect_checkbox = None
        
        self.sort_ascending = False
        self.current_results = []
        
        # 修改配置文件路径
        self.config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "grid_strategy_config.json")
        self.optimization_running = False
        self.start_button = None
        self.error_message = None
        
        self.etf_analysis = None  # 添加ETF分析窗口引用
        self.shortcuts_manager = None  # 初始化为None
        self.watchlist_window = None  # 添加自选列表窗口引用
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=l("settings"), menu=settings_menu)
        
        # 添加快捷键设置选项
        settings_menu.add_command(
            label=l("shortcut_settings"),
            command=lambda: self.shortcuts_manager.show_settings()
        )
        
        # 添加自选列表选项
        settings_menu.add_command(
            label=l("watchlist")+"(⌘L)",
            command=self.show_watchlist
        )
        self.root.bind("<Command-l>", lambda e: self.show_watchlist())
        
        # 添加网格优化器选项
        settings_menu.add_command(
            label=l("grid_optimizer")+"(⌘G)", 
            command=self.show_grid_optimizer
        )
        self.root.bind("<Command-g>", lambda e: self.show_grid_optimizer())
        
        # 添加截图选项
        settings_menu.add_command(
            label=l("capture_to_clipboard")+"(⌘b)", 
            command=self.capture_all_windows_to_clipboard
        )
        self.root.bind("<Command-b>", lambda e: self.capture_all_windows_to_clipboard())
        
        # 添加分隔线
        settings_menu.add_separator()
        
        # 添加退出选项
        settings_menu.add_command(
            label=l("quit")+"(⌘Q)",
            command=self.quit_app
        )
        self.root.bind("<Command-q>", lambda e: self.quit_app())
    
    def create_window(self):
        """创建主窗口"""
        self.window = self.root  # 主窗口使用传入的root
        self.window.title(l("app_title"))
        self.window.geometry("300x800")
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 初始化变量前先加载配置
        self.load_config()
        
        # 如果没有加载到配置，使用默认值初始化变量
        self.symbol_var = tk.StringVar(self.root, value=getattr(self, 'symbol', "159300"))
        self.symbol_name_var = tk.StringVar(self.root, value=getattr(self, 'symbol_name', ""))
        self.start_date_var = tk.StringVar(self.root, value=getattr(self, 'start_date', "2024-10-10"))
        self.end_date_var = tk.StringVar(self.root, value=getattr(self, 'end_date', "2024-12-20"))
        self.ma_period_var = tk.StringVar(self.root, value=getattr(self, 'ma_period', "55"))
        self.ma_protection_var = tk.BooleanVar(self.root, value=getattr(self, 'ma_protection', True))
        self.initial_positions_var = tk.StringVar(self.root, value=getattr(self, 'initial_positions', "0"))
        self.initial_cash_var = tk.StringVar(self.root, value=getattr(self, 'initial_cash', "100000"))
        self.min_buy_times_var = tk.StringVar(self.root, value=getattr(self, 'min_buy_times', "2"))
        self.price_range_min_var = tk.StringVar(value=getattr(self, 'price_range_min', "3.9"))
        self.price_range_max_var = tk.StringVar(value=getattr(self, 'price_range_max', "4.3"))
        self.n_trials_var = tk.StringVar(value=getattr(self, 'n_trials', "100"))
        self.top_n_var = tk.StringVar(value=getattr(self, 'top_n', "5"))
        self.profit_calc_method_var = tk.StringVar(self.root, value=getattr(self, 'profit_calc_method', "mean"))
        self.connect_segments_var = tk.BooleanVar(self.root, value=getattr(self, 'connect_segments', False))
        
        # 初始化快捷键管理器
        self.shortcuts_manager = ShortcutsManager(self.root)
        
        # 创建主布局框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 新增顶部工具栏
        toolbar_frame = ttk.Frame(main_frame)
        toolbar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        
        # 第一组按钮（左侧）
        left_toolbar = ttk.Frame(toolbar_frame)
        left_toolbar.pack(side=tk.LEFT)
        
        etf_compare_btn = ttk.Button(
            left_toolbar, 
            text=f"ETF对比 ({self.shortcuts_manager.get_shortcut_display('etf_compare')})", 
            command=self.show_etf_comparison
        )
        etf_compare_btn.pack(side=tk.LEFT, padx=2)
        
        # 添加K线按钮
        kline_btn = ttk.Button(
            left_toolbar,
            text=f"K线图 ({self.shortcuts_manager.get_shortcut_display('kline')})",
            command=self.show_kline_chart
        )
        kline_btn.pack(side=tk.LEFT, padx=2)
        
        # 绑定快捷键
        self.bind_shortcuts()
        
        # 工具栏分隔线
        ttk.Separator(toolbar_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=5, fill=tk.Y)
        
        # 第二组按钮（右侧）
        right_toolbar = ttk.Frame(toolbar_frame)
        right_toolbar.pack(side=tk.RIGHT)
        # 这里可以继续添加其他功能按钮
        
        # 左侧参数面板
        params_frame = ttk.LabelFrame(main_frame, text=l("param_settings"), padding=10)
        params_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # 参数输入控件
        self.create_parameter_inputs(params_frame)
        
        # 中间结果板
        results_frame = ttk.LabelFrame(main_frame, text=l("optimization_results"), padding=10)
        results_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 添加排序按钮
        sort_frame = ttk.Frame(results_frame)
        sort_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.sort_ascending = False
        self.sort_button = ttk.Button(
            sort_frame, 
            text=l("profit_rate_sort").format("↑" if self.sort_ascending else "↓"), 
            command=self.toggle_sort
        )
        self.sort_button.pack(side=tk.LEFT)
        
        # 创建参数组合列表的画布和滚动条
        self.results_canvas = tk.Canvas(results_frame)
        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_canvas.yview)
        self.results_canvas.configure(yscrollcommand=scrollbar.set)
        
        # 创建参数组合的容器
        self.params_container = ttk.Frame(self.results_canvas)
        self.results_canvas.create_window((0, 0), window=self.params_container, anchor=tk.NW)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 右侧交易详情面板
        details_frame = ttk.LabelFrame(main_frame, text=l("trade_details"), padding=10)
        details_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建交易详情区域
        self.create_trade_details_area(details_frame)
        
        # 底部进度面板
        progress_frame = ttk.LabelFrame(self.root, text=l("optimization_progress"), padding=10)
        progress_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
        
        # 创建进度相关控件
        self.create_progress_widgets(progress_frame)
        
        # 设置窗口始终置顶
        self.root.attributes('-topmost', True)
        
        # 绑定窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # 在create_window方法末尾添加Command+W快捷键绑定
        self.root.bind('<Command-w>', lambda e: self._on_closing())
        
        # 默认隐藏主窗口
        self.window.withdraw()
    
    def create_parameter_inputs(self, parent):
        """创建参数输入控件"""
        # 设置左侧面板的宽度
        parent.configure(width=200)
        
        
        # 证券代码输入框
        ttk.Label(parent, text=l("symbol_code")).grid(row=0, column=0, sticky=tk.W, pady=2)
        symbol_entry = ttk.Entry(parent, textvariable=self.symbol_var, width=12)
        symbol_entry.grid(row=0, column=1, sticky=tk.W, pady=2)
        symbol_entry.bind('<FocusOut>', lambda e: self.validate_symbol(symbol_entry))
        
        # 证券名称输入框
        ttk.Label(parent, text=l("symbol_name")).grid(row=1, column=0, sticky=tk.W, pady=2)
        symbol_name_entry = ttk.Entry(parent, textvariable=self.symbol_name_var, width=12)
        symbol_name_entry.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # 绑定事件
        symbol_entry.bind('<FocusOut>', lambda e: self.update_symbol_info('code'))
        symbol_entry.bind('<Return>', lambda e: self.update_symbol_info('code'))
        symbol_name_entry.bind('<FocusOut>', lambda e: self.update_symbol_info('name'))
        symbol_name_entry.bind('<Return>', lambda e: self.update_symbol_info('name'))
        
        # 初始化证券信息
        self.update_symbol_info('code')
        
        # 其他参数输入框从第3行开始
        ttk.Label(parent, text=l("start_date")).grid(row=2, column=0, sticky=tk.W, pady=2)
        start_date_entry = ttk.Entry(parent, textvariable=self.start_date_var, width=12)
        start_date_entry.grid(row=2, column=1, sticky=tk.W, pady=2)
        start_date_entry.bind('<FocusOut>', lambda e: self.validate_date(start_date_entry))
        
        ttk.Label(parent, text=l("end_date")).grid(row=3, column=0, sticky=tk.W, pady=2)
        end_date_entry = ttk.Entry(parent, textvariable=self.end_date_var, width=12)
        end_date_entry.grid(row=3, column=1, sticky=tk.W, pady=2)
        end_date_entry.bind('<FocusOut>', lambda e: self.validate_date(end_date_entry))
        
        ttk.Label(parent, text=l("month_filter")).grid(row=4, column=0, sticky=tk.W, pady=2)
        self.month_filter_var = tk.StringVar()
        month_filter_entry = ttk.Entry(parent, textvariable=self.month_filter_var, width=12)
        month_filter_entry.grid(row=4, column=1, sticky=tk.W, pady=2)
        month_filter_entry.bind('<FocusOut>', lambda e: self.validate_month_filter())
        
        ttk.Label(parent, text=l("ma_period")).grid(row=5, column=0, sticky=tk.W, pady=2)
        ma_period_entry = ttk.Entry(parent, textvariable=self.ma_period_var, width=12)
        ma_period_entry.grid(row=5, column=1, sticky=tk.W, pady=2)
        
        ttk.Checkbutton(parent, text=l("ma_protection"), variable=self.ma_protection_var).grid(
            row=6, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(parent, text=l("initial_positions")).grid(row=7, column=0, sticky=tk.W, pady=2)
        initial_pos_entry = ttk.Entry(parent, textvariable=self.initial_positions_var, width=12)
        initial_pos_entry.grid(row=7, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(parent, text=l("initial_cash")).grid(row=8, column=0, sticky=tk.W, pady=2)
        initial_cash_entry = ttk.Entry(parent, textvariable=self.initial_cash_var, width=12)
        initial_cash_entry.grid(row=8, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(parent, text=l("min_buy_times")).grid(row=9, column=0, sticky=tk.W, pady=2)
        min_buy_entry = ttk.Entry(parent, textvariable=self.min_buy_times_var, width=12)
        min_buy_entry.grid(row=9, column=1, sticky=tk.W, pady=2)
        
        # 价格范围框架
        price_range_frame = ttk.LabelFrame(parent, text=l("price_range"), padding=5)
        price_range_frame.grid(row=10, column=0, columnspan=2, sticky=tk.EW, pady=5)
        
        ttk.Label(price_range_frame, text=l("min_value")).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.price_min_entry = ttk.Entry(price_range_frame, textvariable=self.price_range_min_var, width=6)
        self.price_min_entry.grid(row=0, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(price_range_frame, text=l("max_value")).grid(row=0, column=2, sticky=tk.W, pady=2, padx=(5,0))
        self.price_max_entry = ttk.Entry(price_range_frame, textvariable=self.price_range_max_var, width=6)
        self.price_max_entry.grid(row=0, column=3, sticky=tk.W, pady=2)
        
        
        # 优化设置
        ttk.Label(parent, text=l("optimization_trials")).grid(row=11, column=0, sticky=tk.W, pady=2)
        n_trials_entry = ttk.Entry(parent, textvariable=self.n_trials_var, width=12)
        n_trials_entry.grid(row=11, column=1, sticky=tk.W, pady=2)
        
        ttk.Label(parent, text=l("display_top_n_results")).grid(row=12, column=0, sticky=tk.W, pady=2)
        top_n_entry = ttk.Entry(parent, textvariable=self.top_n_var, width=12)
        top_n_entry.grid(row=12, column=1, sticky=tk.W, pady=2)
        
        # 添加分隔线
        ttk.Separator(parent, orient='horizontal').grid(
            row=13, column=0, columnspan=2, sticky='ew', pady=10)

        # 分段回测设置框架
        segments_frame = ttk.LabelFrame(parent, text=l("segmented_backtest_settings"), padding=5)
        segments_frame.grid(row=14, column=0, columnspan=2, sticky=tk.EW, pady=5)
        
        # 分段回测开关
        self.enable_segments = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            segments_frame,
            text=l("segmented_backtest"),
            variable=self.enable_segments,
            command=self.toggle_segment_options
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # 分段收益计算模
        self.segment_label = ttk.Label(segments_frame, text=l("calculation_method"))
        self.segment_label.grid(row=1, column=0, sticky=tk.W, pady=2)
        
        self.segment_mode = tk.StringVar(value=l("mean"))
        self.segment_mode_combo = ttk.Combobox(
            segments_frame, 
            textvariable=self.segment_mode,
            values=[l("mean"), l("median")],
            state="readonly",
            width=12
        )
        self.segment_mode_combo.grid(row=1, column=1, sticky=tk.W, pady=2)
        
        # 添加天数显示标签
        self.segment_days_label = ttk.Label(segments_frame, text="")
        self.segment_days_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # 资金持仓衔接选项
        self.connect_segments = tk.BooleanVar(value=False)
        self.connect_checkbox = ttk.Checkbutton(
            segments_frame,
            text=l("connect_cash_and_positions"),
            variable=self.connect_segments
        )
        self.connect_checkbox.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # 绑定最少买入次数变化事件
        self.min_buy_times_var.trace_add('write', self.update_segment_days)
        
        # 开始优化按钮
        self.start_button = ttk.Button(
            parent, 
            text=l("start_optimization") + " (⌘↩)", 
            command=self.toggle_optimization
        )
        self.start_button.grid(row=15, column=0, columnspan=2, pady=10, sticky=tk.EW)
        # 绑定快捷键
        self.root.bind('<Command-Return>', lambda e: self.start_optimization() if not self.optimization_running else self.cancel_optimization())  # macOS
        

        # 初始化控件状态
        self.toggle_segment_options()
        
        # 为所有输入框添加焦点事件处理
        all_entries = [
            symbol_entry, start_date_entry, end_date_entry, ma_period_entry,
            initial_pos_entry, initial_cash_entry, min_buy_entry,
            self.price_min_entry, self.price_max_entry, n_trials_entry, top_n_entry,
            month_filter_entry
        ]
        
        for entry in all_entries:
            # 绑定点击事件和Tab键事件到同一个处理函数
            entry.bind('<Button-1>', lambda e, widget=entry: self.handle_entry_focus(e, widget))
            entry.bind('<Tab>', lambda e, widget=entry: self.handle_entry_focus(e, widget))
            # 添加焦点进入事件处理
            entry.bind('<FocusIn>', lambda e, widget=entry: self.handle_focus_in(e, widget))
    
    def create_progress_widgets(self, parent):
        """创建进度相关控件"""
        self.label = ttk.Label(parent, text=l("waiting_to_start"), font=('Arial', 10))
        self.label.pack(pady=5)
        
        self.progress = ttk.Progressbar(parent, orient="horizontal", length=300, mode="determinate")
        self.progress.pack(pady=5)
        
        self.percent_label = ttk.Label(parent, text="0%", font=('Arial', 10))
        self.percent_label.pack(pady=2)
        
        # 初始化时间显示
        self.time_label = ttk.Label(parent, text=l("elapsed_time_format").format("0:00:00"), font=('Arial', 10))
        self.time_label.pack(pady=2)
        
        self.eta_label = ttk.Label(parent, text=l("estimated_remaining_format").format("--:--:--"), font=('Arial', 10))
        self.eta_label.pack(pady=2)
    
    def start_optimization(self, event=None):
        """开始优化按钮的回调函数"""
        # 重置错误信息
        self.error_message = None
        
        try:
            # 如果已经在运行，直接返回
            if self.optimization_running:
                return
            
            # 获取并验证参数
            symbol = self.symbol_var.get().strip()
            if not symbol:
                self.error_message = l("please_enter_symbol_code")
                return
            
            # 验证证券代码是否有效
            if not self.is_valid_symbol(symbol):
                self.error_message = l("please_enter_valid_symbol_code")
                return
            
            # 自动判断证券类型
            if len(symbol) == 6 and symbol.startswith("8"):
                security_type = "BOARD"
            elif len(symbol) == 6 and symbol.startswith(("1", "5")):
                security_type = "ETF"
            else:
                security_type = "STOCK"
            
            # 验证日期格式
            try:
                start_date = datetime.strptime(self.start_date_var.get().strip(), '%Y-%m-%d')
                end_date = datetime.strptime(self.end_date_var.get().strip(), '%Y-%m-%d')
            except ValueError:
                self.error_message = l("invalid_date_format")
                return
            
            # 新增月份过滤检查
            month_filter = None
            if self.month_filter_var.get().strip():
                month_filter = int(self.month_filter_var.get().strip())
                if 1 <= month_filter <= 12:
                    # 检查时间范围是否包含该月份
                    start_year = start_date.year
                    end_year = end_date.year
                    valid = False
                    for year in range(start_year, end_year + 1):
                        test_date = datetime(year, month_filter, 1)
                        if start_date <= test_date <= end_date:
                            valid = True
                            break
                    if not valid:
                        self.error_message = f"时间范围{start_date}至{end_date}不包含{month_filter}月"
                        return
            
            # 验证其他参数
            try:
                ma_period = int(self.ma_period_var.get())
                if ma_period <= 0:
                    self.error_message = l("ma_period_must_be_greater_than_0")
                    return
                
                ma_protection = self.ma_protection_var.get()
                
                initial_positions = int(self.initial_positions_var.get())
                if initial_positions < 0:
                    self.error_message = l("initial_positions_must_be_greater_than_or_equal_to_0")
                    return
                
                initial_cash = int(self.initial_cash_var.get())
                if initial_cash < 0:
                    self.error_message = l("initial_cash_must_be_greater_than_or_equal_to_0")
                    return
                
                min_buy_times = int(self.min_buy_times_var.get())
                if min_buy_times <= 0:
                    self.error_message = l("min_buy_times_must_be_greater_than_0")
                    return
                
                price_range_min = float(self.price_range_min_var.get())
                price_range_max = float(self.price_range_max_var.get())
                if price_range_min >= price_range_max:
                    self.error_message = l("price_range_min_must_be_less_than_price_range_max")
                    return
                
                n_trials = int(self.n_trials_var.get())
                if n_trials <= 0:
                    self.error_message = l("n_trials_must_be_greater_than_0")
                    return
                
                top_n = int(self.top_n_var.get())
                if top_n <= 0:
                    self.error_message = l("top_n_must_be_greater_than_0")
                    return
                
                price_range = (price_range_min, price_range_max)
            except ValueError as e:
                self.error_message = str(e)
                return
            
            # 更新UI状态
            self.optimization_running = True
            self.start_button.configure(text=l("cancel_optimization") + " (⌘↩)")
            self.optimization_running = True
            
            # 更新总试验次数
            self.total_trials = int(n_trials * 1.5)
            self.progress["maximum"] = self.total_trials
            
            # 重置进度
            self.current_trial = 0
            self.progress["value"] = 0
            self.percent_label["text"] = "0%"
            self.start_time = datetime.now()
            self.label["text"] = l("optimizing_parameters")
            
            # 清空之前结果显示
            for widget in self.params_container.winfo_children():
                widget.destroy()
            
            # 清空交易详情
            self.trade_details.config(state='normal')
            self.trade_details.delete('1.0', tk.END)
            self.trade_details.config(state='disabled')
            
            # 创建优化实例
            from stock_grid_optimizer import GridStrategyOptimizer  # 避免循环导入
            optimizer = GridStrategyOptimizer(
                symbol=symbol,
                security_type=security_type,  # 传递自动判断的证券类型
                start_date=start_date,
                end_date=end_date,
                ma_period=ma_period,
                ma_protection=ma_protection,
                initial_positions=initial_positions,
                initial_cash=initial_cash,
                min_buy_times=min_buy_times,
                price_range=price_range,
                profit_calc_method=self.profit_calc_method_var.get() if self.enable_segments.get() else None,
                connect_segments=self.connect_segments_var.get() if self.enable_segments.get() else False
            )
            
            # 进度窗口传递给优化器
            optimizer.progress_window = self
            
            def run_optimization():
                try:
                    # 运行优化
                    results = optimizer.optimize(n_trials=n_trials)
                    
                    if results and not self.is_closed and self.optimization_running:
                        # 在主线程中更新UI
                        def update_ui():
                            if not self.is_closed:
                                self.label["text"] = l("optimization_complete")
                                self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
                                self.optimization_running = False
                                # 显示优化结果
                                self.display_optimization_results(results)
                        
                        self.root.after(0, update_ui)
                        
                except Exception as e:
                    if not self.is_closed:
                        self.root.after(0, lambda: self.start_button.configure(text=l("start_optimization") + " (⌘↩)"))
                        self.optimization_running = False
                finally:
                    # 确保状态正确置
                    if not self.is_closed:
                        self.root.after(0, lambda: self.start_button.configure(text=l("start_optimization") + " (⌘↩)"))
                        self.optimization_running = False
            
            # 在新线程中运行优化
            self.optimization_thread = threading.Thread(target=run_optimization)
            self.optimization_thread.daemon = True
            self.optimization_thread.start()
            
        except ValueError as e:
            self.error_message = str(e)
            self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
            self.optimization_running = False
        except Exception as e:
            self.error_message = l("optimization_start_failed") + f": {str(e)}"
            self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
            self.optimization_running = False
    
    def capture_output(self, text):
        """捕获并存储输出文本"""
        self.captured_output.append(text)
    
    def display_trade_details(self, trial):
        """显示特定参数组合的策略详情"""
        # 清空现有内容
        self.trade_details.config(state='normal')
        self.trade_details.delete('1.0', tk.END)
        
        # 创建策略实例
        from grid_strategy import GridStrategy
        strategy = GridStrategy(
            symbol=self.symbol_var.get().strip(),
            symbol_name=self.symbol_name_var.get().strip()
        )
        
        # 使用format_trial_details方法获取显示内容
        output_lines = strategy.format_trial_details(trial)
        
        # 显示内容
        for line in output_lines:
            self.trade_details.insert(tk.END, line + "\n")
        
        # 设置为只读并滚动到顶部
        self.trade_details.config(state='disabled')
        self.trade_details.see('1.0')
    
    def enable_trade_details_button(self):
        """启用易详情按钮"""
        if self.view_trades_btn:
            self.view_trades_btn.state(['!disabled'])
    
    def _on_closing(self):
        """网格优化器窗口关闭时的处理"""
        try:
            self.save_config()  # 保存配置
        except Exception as e:
            print(f"{l('error_saving_config')}: {e}")
        finally:
            # 只隐藏窗口,不退出程序
            self.window.withdraw()
    
    def _check_thread_and_close(self):
        """查优化线程束，如果结束则关闭窗口"""
        if not self.optimization_thread.is_alive():
            self.root.destroy()
        else:
            self.root.after(100, self._check_thread_and_close)
    
    def update_progress(self, current, total=None):
        """更新进度显示（线程安全）"""
        if total is None:
            total = self.total_trials
            
        def _update():
            percent = int((current / total) * 100)
            self.progress["value"] = percent
            self.percent_label["text"] = f"{percent}%"
            self.time_label["text"] = l("elapsed_time_format").format(str(datetime.now() - self.start_time).split('.')[0])
            self.eta_label["text"] = l("estimated_remaining_format").format(str((datetime.now() - self.start_time) * (100 / percent - 1)).split('.')[0])
        
        self.root.after(0, _update)  # 使用after方法确保在主线程更新
    
    def close(self):
        """关闭窗口"""
        if self.root is not None and not self.is_closed:
            self.is_closed = True
            self.root.destroy() 
        
    def update_label(self, text):
        """更新标签文本"""
        if self.root and not self.is_closed:
            try:
                self.label["text"] = text
                self.root.update()
            except tk.TclError:
                pass  # 忽略窗口已关闭的错误
    
    def increase_font_size(self, event=None):
        """增加字体大小"""
        if self.trade_details:
            try:
                # 获取当前字体配置
                current_font = self.trade_details['font']
                if isinstance(current_font, str):
                    # 果是字符串格式，解析字体名称和大小
                    font_name = current_font.split()[0]
                    size = int(current_font.split()[-1])
                else:
                    # 如果是元组格式，直接获取字体名称和大小
                    font_name, size = current_font.split()[0], int(current_font.split()[1])
                
                # 增加字体大小（最大限制为30）
                new_size = min(size + 1, 30)
                self.trade_details.configure(font=(font_name, new_size))
            except Exception as e:
                print(f"{l('error_adjusting_font_size')}: {e}")
    
    def decrease_font_size(self, event=None):
        """减小字体大小"""
        if self.trade_details:
            try:
                # 获取当前字体配置
                current_font = self.trade_details['font']
                if isinstance(current_font, str):
                    # 如果是字符串格式，解析字体名称和大小
                    font_name = current_font.split()[0]
                    size = int(current_font.split()[-1])
                else:
                    # 如果是元组格式，直接获取字体名称和大小
                    font_name, size = current_font.split()[0], int(current_font.split()[1])
                
                # 减小字体大小（最小限制为6）
                new_size = max(size - 1, 6)
                self.trade_details.configure(font=(font_name, new_size))
            except Exception as e:
                print(f"{l('error_adjusting_font_size')}: {e}")
    
    def focus_search(self, event=None):
        """聚焦到搜索框"""
        self.search_entry.focus_set()
        return "break"
    
    def search_text(self, direction='down'):
        """搜索文本"""
        search_term = self.search_var.get()
        if not search_term:
            self.search_count_label.config(text="")
            return
        
        content = self.trade_details.get("1.0", tk.END)
        matches = content.lower().count(search_term.lower())
        self.search_count_label.config(text=f"{l('found')} {matches} {l('matches')}")
        
        if matches > 0:
            # 获取当前光标位置
            current_pos = self.trade_details.index(tk.INSERT)
            
            # 根据搜索方向设置开始位置
            if direction == 'down':
                start_pos = current_pos
                search_direction = tk.SEL_FIRST
            else:
                start_pos = "1.0"
                search_direction = tk.SEL_LAST
            
            # 清除现有选择
            self.trade_details.tag_remove('sel', '1.0', tk.END)
            
            # 搜索文本
            pos = self.trade_details.search(
                search_term, 
                start_pos, 
                nocase=True, 
                stopindex=tk.END if direction == 'down' else current_pos
            )
            
            if pos:
                # 选中找到的文本
                line, char = pos.split('.')
                end_pos = f"{line}.{int(char) + len(search_term)}"
                self.trade_details.tag_add('sel', pos, end_pos)
                self.trade_details.mark_set(tk.INSERT, search_direction)
                self.trade_details.see(pos)
            else:
                # 如果没找到，从头/尾开始搜索
                start = "1.0" if direction == 'down' else tk.END
                pos = self.trade_details.search(search_term, start, nocase=True)
                if pos:
                    line, char = pos.split('.')
                    end_pos = f"{line}.{int(char) + len(search_term)}"
                    self.trade_details.tag_add('sel', pos, end_pos)
                    self.trade_details.mark_set(tk.INSERT, search_direction)
                    self.trade_details.see(pos)
    
    def scroll_to_end(self, event=None):
        """滚动到文本末尾"""
        if self.trade_details:
            self.trade_details.see(tk.END)
            # 将插入点移动到最后
            self.trade_details.mark_set(tk.INSERT, tk.END)
            return 'break'  # 阻止事件继续传播
    
    def scroll_to_start(self, event=None):
        """滚动到文本开始"""
        if self.trade_details:
            self.trade_details.see('1.0')
            # 将插入点移动到
            self.trade_details.mark_set(tk.INSERT, '1.0')
            return 'break'  # 阻止事件继续传播
    
    def display_strategy_details(self, strategy_params):
        """显示特定参数组合的策略详情"""
        # 清空现有内容
        self.trade_details.config(state='normal')
        self.trade_details.delete('1.0', tk.END)
        
        # 获取时间段
        start_date = datetime.strptime(self.start_date_var.get().strip(), '%Y-%m-%d')
        end_date = datetime.strptime(self.end_date_var.get().strip(), '%Y-%m-%d')
        
        # 获取是否启用多段回测
        enable_segments = self.enable_segments.get()
        segments = None
        
        if enable_segments:
            # 使用segment_utils中的方法构建时段
            from segment_utils import build_segments
            segments = build_segments(
                start_date=start_date,
                end_date=end_date,
                min_buy_times=int(self.min_buy_times_var.get())
            )
        
        # 创建策略实例
        from grid_strategy import GridStrategy
        strategy = GridStrategy(
            symbol=self.symbol_var.get().strip(),
            symbol_name=self.symbol_name_var.get().strip()
        )
        
        # 设置初始资金和持仓
        strategy.initial_cash = float(self.initial_cash_var.get())
        strategy.initial_positions = int(self.initial_positions_var.get())
        # 设置基准价格和价格范围
        strategy.base_price = float(self.price_range_min_var.get())
        strategy.price_range = (
            float(self.price_range_min_var.get()),
            float(self.price_range_max_var.get())
        )
        
        # 在获取时间段后添加月份过滤处理
        try:
            month_filter = int(self.month_filter_var.get().strip()) if self.month_filter_var.get().strip() else None
        except ValueError:
            month_filter = None

        # 修改策略调用部分
        results = strategy.run_strategy_details(
            strategy_params=strategy_params,
            start_date=start_date,
            end_date=end_date,
            segments=segments,
            month_filter=month_filter  # 添加月份过滤参数
        )
        
        # 使用format_trade_details方法获取显示内容
        output_lines = strategy.format_trade_details(
            results=results,
            enable_segments=enable_segments,
            segments=segments,
            profit_calc_method=self.profit_calc_method_var.get()
        )
        
        # 显示内容
        for line in output_lines:
            self.trade_details.insert(tk.END, line + "\n")
        
        # 设置为只读并滚动到顶部
        self.trade_details.config(state='disabled')
        self.trade_details.see('1.0')
    
    def toggle_sort(self):
        """切换排序方向并重新显示结果"""
        self.sort_ascending = not self.sort_ascending
        self.sort_button.config(text=f"{l('profit_rate')} {'↑' if self.sort_ascending else '↓'}")
        if hasattr(self, 'current_results'):
            self.display_optimization_results(self.current_results)
    
    def display_optimization_results(self, results):
        """显示优化结果"""
        # 保存当前结果以供排序使用
        self.current_results = results
        
        # 清空现有结果
        for widget in self.params_container.winfo_children():
            widget.destroy()
        
        # 获取前N个结果
        top_n = int(self.top_n_var.get())
        
        # 过滤掉收益率<=0的结果并排序
        valid_trials = [trial for trial in results["sorted_trials"] if -trial.value > 0]
        
        # 按收益率排序（注意trial.value是负的收益率）
        # 默认降序排序（收益率从高到低）
        sorted_trials = sorted(valid_trials, key=lambda t: t.value, reverse=True)
        if not self.sort_ascending:  # 如果是降序，再次反转
            sorted_trials.reverse()
        
        # 限制显示数量
        display_trials = sorted_trials[:top_n]
        
        if not display_trials:
            # 如果没有有效结果，显示提示信息
            ttk.Label(
                self.params_container, 
                text=l("no_parameter_combinations_with_profit_greater_than_0_found"),
                font=('Arial', 10)
            ).pack(pady=10)
            return
        
        # 参数名称映射
        param_names = {
            'up_sell_rate': l('up_sell'),
            'up_callback_rate': l('up_callback'),            
            'down_buy_rate': l('down_buy'),
            'down_rebound_rate': l('down_rebound'),
            'shares_per_trade': l('shares_per_trade')
        }
        
        # 显示每个结果
        for i, trial in enumerate(display_trials, 1):
            profit_rate = -trial.value
            params = trial.params
            
            # 创建结果框架
            result_frame = ttk.LabelFrame(
                self.params_container,
                text=l("parameter_combination_format").format(i, profit_rate)  # 移除 * 100，因为 profit_rate 已经是百分比形式
            )
            result_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 添加参数信息
            param_text = ""
            # 按照param_names的顺序显示参数
            for key in param_names.keys():
                value = params[key]
                if key == 'shares_per_trade':
                    param_text += f"{param_names[key]}: {value:,}\n"
                else:
                    param_text += f"{param_names[key]}: {value*100:.2f}%\n"
            
            param_text += f"{l('trade_count')}: {trial.user_attrs.get('trade_count', 'N/A')}"
            
            param_label = ttk.Label(result_frame, text=param_text, justify=tk.LEFT)
            param_label.pack(padx=5, pady=5)
            
            # 添加查看详情按钮
            # 添加查看按钮
            detail_button = ttk.Button(result_frame, text=l("view_details"), 
                      command=lambda p=trial.params: self.display_strategy_details(p)).pack(
                          side=tk.RIGHT, padx=5)

        
        # 更新画布滚动区
        self.params_container.update_idletasks()
        self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
    
    def create_trade_details_area(self, parent):
        """创建交易详情显示区域"""
        # 创建搜索框架
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(search_frame, text=l("search")).pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.search_count_label = ttk.Label(search_frame, text="")
        self.search_count_label.pack(side=tk.LEFT, padx=5)
        
        # 创建文本框
        self.trade_details = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            width=50,
            height=25,
            font=('Courier', 11)
        )
        self.trade_details.pack(fill=tk.BOTH, expand=True)
        self.trade_details.config(state='disabled')
        
        # 绑定搜索相关事件
        self.search_var.trace_add('write', lambda *args: self.search_text())
        self.root.bind('<Command-f>', self.focus_search)
        self.search_entry.bind('<Return>', lambda e: self.search_text('down'))
        self.search_entry.bind('<Shift-Return>', lambda e: self.search_text('up'))

    def update_symbol_info(self, source='code'):
        """
        更新证券信息
        @param source: 'code' 表示从代码更新名称，'name' 表示从名称更新代码
        """
        try:
            # 获取当前日期范围
            start_date = self.start_date_var.get().strip()
            end_date = self.end_date_var.get().strip()
            
            if source == 'code':
                symbol = self.symbol_var.get().strip()
                if not symbol:
                    self.symbol_name_var.set("")
                    return
                
                # 获取证券信息
                name, security_type = get_symbol_info(symbol)
                if name is None:
                    self.symbol_name_var.set(l("symbol_not_found"))
                    return
                
                self.symbol_name_var.set(name)
                
                # 检查是否是新的证券代码
                old_symbol = self.load_config_value('symbol')
                is_new_symbol = not os.path.exists(self.config_file) or symbol != old_symbol
                
                if is_new_symbol:
                    # 先尝试从配置文件中取该证券的价格范围
                    config_data = self.load_symbol_config(symbol)
                    if config_data:
                        self.price_range_min_var.set(config_data.get('price_range_min', ''))
                        self.price_range_max_var.set(config_data.get('price_range_max', ''))
                        print(f"{l('loaded_price_range_from_config')}: {config_data.get('price_range_min')} - {config_data.get('price_range_max')}")
                    else:
                        # 如果配置文件中没有，则使用历史数据计算价格范围
                        price_min, price_max = calculate_price_range(symbol, start_date, end_date, security_type)
                        if price_min is not None and price_max is not None:
                            self.price_range_min_var.set(f"{price_min:.3f}")
                            self.price_range_max_var.set(f"{price_max:.3f}")
                            print(f"{l('updated_price_range')}: {price_min:.3f} - {price_max:.3f}")
                
            else:  # source == 'name'
                name = self.symbol_name_var.get().strip()
                if not name:
                    self.symbol_var.set("")
                    return
                
                # 使用新的方法获取证券信息
                symbol, symbol_name, security_type = get_symbol_info_by_name(name)
                
                if symbol is not None:
                    self.symbol_var.set(symbol)
                    self.symbol_name_var.set(symbol_name)
                    
                    # 检查是否是新的证券代码
                    if not os.path.exists(self.config_file) or symbol != self.load_config_value('symbol'):
                        # 计算价格范围
                        price_min, price_max = calculate_price_range(symbol, symbol_name, start_date, end_date, security_type)
                        if price_min is not None and price_max is not None:
                            self.price_range_min_var.set(f"{price_min:.3f}")
                            self.price_range_max_var.set(f"{price_max:.3f}")
                            print(f"{l('updated_price_range')}: {price_min:.3f} - {price_max:.3f}")
                else:
                    print(f"{l('no_symbol_found_format').format(name)}")
                
        except Exception as e:
            print(f"{l('failed_to_update_symbol_info')}: {e}")
            if source == 'code':
                self.symbol_name_var.set(l("symbol_not_found"))
            else:
                self.symbol_var.set("")
    
    def handle_entry_focus(self, event, widget):
        """处理输入框的焦点事件"""
        def delayed_focus():
            if widget.winfo_exists():  # 确保widget然存在
                widget.focus_set()
                widget.selection_range(0, tk.END)  # 选中所有本
                # 强制更新UI
                widget.update_idletasks()
        
        # 清除可能存在的待处理的焦点事件
        if hasattr(self, '_focus_after_id'):
            self.root.after_cancel(self._focus_after_id)
        
        # 设置新的延迟焦点事件
        self._focus_after_id = self.root.after(10, delayed_focus)
        return "break"  # 阻止事件继续传播

    def handle_focus_in(self, event, widget):
        """处理输入框获得焦点时的事件"""
        widget.selection_range(0, tk.END)  # 选中所有文本
        # 强制更新UI
        widget.update_idletasks()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    
                # 将配置值设置为类属性，跳过None值
                for key, value in config.items():
                    if value is not None:
                        setattr(self, key, value)
                        
                # 加载多段回测设置
                # if 'profit_calc_method' in config and config['profit_calc_method'] is not None:
                #     self.profit_calc_method_var.set(config['profit_calc_method'])
                # if 'connect_segments' in config and config['connect_segments'] is not None:
                #     self.connect_segments_var.set(config['connect_segments'])
                    
                print(l("loaded_config_file"))
        except Exception as e:
            print(f"{l('failed_to_load_config_file')}: {e}")
    
    def save_config(self):
        """保存配置到文件"""
        if not self.validate_all_inputs():
            print(l("error_saving_config"), l("invalid_parameters_cannot_save_config"))
            return

        config = {
            "symbol": str(self.symbol_var.get()),
            "symbol_name": self.symbol_name_var.get(),
            "start_date": self.start_date_var.get(),
            "end_date": self.end_date_var.get(),
            "ma_period": self.ma_period_var.get(),
            "ma_protection": self.ma_protection_var.get(),
            "initial_positions": self.initial_positions_var.get(),
            "initial_cash": self.initial_cash_var.get(),
            "min_buy_times": self.min_buy_times_var.get(),
            "price_range_min": self.price_range_min_var.get(),
            "price_range_max": self.price_range_max_var.get(),
            "n_trials": self.n_trials_var.get(),
            "top_n": self.top_n_var.get(),
            "profit_calc_method": self.profit_calc_method_var.get(),
            "connect_segments": self.connect_segments_var.get()
        }

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            print(l("config_saved"))
        except Exception as e:
            print(f"{l('error_saving_config')}: {e}")
    
    def load_config_value(self, key):
        """获取配置文件中的特定值"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get(key)
        except Exception:
            pass
        return None
    
    def toggle_optimization(self):
        """切换优化状态（开始/取消）"""
        if not self.optimization_running:
            # 开始优化
            self.start_optimization()
            self.start_button.configure(text=l("cancel_optimization") + " (⌘↩)")
            self.optimization_running = True
        else:
            # 取消优化
            self.cancel_optimization()
            self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
            self.optimization_running = False
    
    def cancel_optimization(self):
        """取消优化"""
        self.optimization_running = False
        self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
        self.label.configure(text=l("optimization_cancelled"))
        self.progress.configure(value=0)
        self.percent_label.configure(text="0%")

    def load_symbol_config(self, symbol):
        """
        从配置文件中加载特定证券的配置信息
        @param symbol: 证券代码
        @return: 配置信息字典或None
        """
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if config.get('symbol') == symbol:
                        return {
                            'price_range_min': config.get('price_range_min'),
                            'price_range_max': config.get('price_range_max')
                        }
        except Exception as e:
            print(f"{l('failed_to_load_symbol_config')}: {e}")
        return None

    def toggle_segment_options(self):
        """切换分段回测选项的启用状态"""
        enabled = self.enable_segments.get()
        
        # 更新控件状态
        self.segment_label.config(state='normal' if enabled else 'disabled')
        self.segment_mode_combo.config(state='readonly' if enabled else 'disabled')
        self.connect_checkbox.config(state='normal' if enabled else 'disabled')
        
        # 更新天数显示
        self.update_segment_days()

    def update_segment_days(self, *args):
        """更新分段天数显示"""
        if self.enable_segments.get():
            try:
                min_buy_times = int(self.min_buy_times_var.get())
                from segment_utils import get_segment_days
                days = get_segment_days(min_buy_times)
                self.segment_days_label.config(text=f"{l('days_per_segment')}: {days} {l('trading_days')}")
            except ValueError:
                self.segment_days_label.config(text="")
        else:
            self.segment_days_label.config(text="")

    def validate_symbol(self, entry):
        """验证证券代码"""
        symbol = str(entry.get()).strip()  # 强制转换为字符串
        if not symbol:
            self.error_message = l("please_enter_symbol_code")
            return False
        # ...后续校验逻辑...

    def validate_date(self, entry):
        """验证日期格式"""
        date_str = entry.get().strip()
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            entry.config(foreground='black')
        except ValueError:
            entry.config(foreground='red')
            messagebox.showerror(l("input_error"), l("invalid_date_format"))

    def is_valid_symbol(self, symbol):
        """检查证券代码是否有效"""
        return is_valid_symbol(symbol)

    def validate_all_inputs(self):
        """验证所有输入框的内容"""
        # 验证证券代码
        if not self.is_valid_symbol(self.symbol_var.get()):
            return False
        # 验证日期
        try:
            datetime.strptime(self.start_date_var.get(), '%Y-%m-%d')
            datetime.strptime(self.end_date_var.get(), '%Y-%m-%d')
        except ValueError:
            return False
        # 验证其他参数（如有需要）
        # ... 其他验证逻辑 ...
        return True

    def cleanup(self):
        """清理优化状态"""
        self.optimization_running = False
        if self.root and not self.is_closed:
            self.start_button.configure(text=l("start_optimization") + " (⌘↩)")
            self.label["text"] = l("optimization_cancelled")
            self.progress.configure(value=0)
            self.percent_label.configure(text="0%")
            self.time_label["text"] = f"{l('elapsed_time')}: 0:00:00"
            self.eta_label["text"] = f"{l('estimated_remaining')}: --:--:--"
            self.root.update()

    def validate_month_filter(self):
        month = self.month_filter_var.get().strip()
        if month:
            try:
                month = int(month)
                if 1 <= month <= 12:
                    return True
                else:
                    messagebox.showerror(l("input_error"), l("month_must_be_1_to_12"))
                    self.month_filter_var.set("")
                    return False
            except ValueError:
                messagebox.showerror(l("input_error"), l("invalid_month_format"))
                self.month_filter_var.set("")
                return False
        return True

    def show_etf_comparison(self):
        """ETF对比分析入口方法"""
        if not self.etf_analysis:
            self.etf_analysis = ETFAnalysisWindow(self)
        self.etf_analysis.show_etf_comparison()

    def show_kline_chart(self):
        """显示当前选中证券的K线图"""
        symbol = self.symbol_var.get().strip()
        symbol_name = self.symbol_name_var.get().strip()
        
        if not symbol:
            messagebox.showwarning("提示", "请先输入证券代码")
            return
        
        # 创建K线窗口实例
        from stock_kline_window import ETFKLineWindow
        kline_window = ETFKLineWindow(self.root)
        kline_window.show(symbol, symbol_name)

    def bind_shortcuts(self):
        """绑定所有快捷键"""
        if self.shortcuts_manager:
            # ETF对比快捷键
            etf_key = self.shortcuts_manager.get_shortcut_key('etf_compare')
            if etf_key:
                # 将快捷键中的大写字母转换为小写
                key_parts = etf_key.split('-')
                if len(key_parts) > 1:
                    # 如果是组合键（如Command-V），将最后一个字母转为小写
                    key_parts[-1] = key_parts[-1].lower()
                    key_binding = f"<{'-'.join(key_parts)}>"
                else:
                    # 如果是单个键，直接转为小写
                    key_binding = f"<{etf_key.lower()}>"
                
                self.root.bind(key_binding, lambda e: self.show_etf_comparison())
                print(f"Bound ETF compare shortcut: {key_binding}")
            else:
                print("Warning: ETF compare shortcut not configured")
            
            # 开始优化快捷键
            opt_key = self.shortcuts_manager.get_shortcut_key('start_optimization')
            if opt_key:
                self.root.bind(f"<{opt_key}>", lambda e: self.start_optimization() 
                             if not self.optimization_running else self.cancel_optimization())
                print(f"Bound optimization shortcut: <{opt_key}>")
            else:
                print("Warning: Optimization shortcut not configured")
            
            # 搜索快捷键
            search_key = self.shortcuts_manager.get_shortcut_key('search')
            if search_key:
                self.root.bind(f"<{search_key}>", self.focus_search)
                print(f"Bound search shortcut: <{search_key}>")
            else:
                print("Warning: Search shortcut not configured")

            # K线图快捷键
            kline_key = self.shortcuts_manager.get_shortcut_key('kline')
            if kline_key:
                # 将快捷键中的大写字母转换为小写
                key_parts = kline_key.split('-')
                if len(key_parts) > 1:
                    key_parts[-1] = key_parts[-1].lower()
                    key_binding = f"<{'-'.join(key_parts)}>"
                else:
                    key_binding = f"<{kline_key.lower()}>"
                
                self.root.bind(key_binding, lambda e: self.show_kline_chart())
                print(f"Bound kline chart shortcut: {key_binding}")
            else:
                print("Warning: Kline chart shortcut not configured")

    def show_watchlist(self):
        """显示自选列表窗口"""
        if not self.watchlist_window:
            self.watchlist_window = WatchlistWindow(self.root)
        self.watchlist_window.show()

    def show_grid_optimizer(self):
        """显示网格优化器窗口"""
        # 显示主窗口
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def quit_app(self):
        """退出应用程序"""
        try:
            self.save_config()  # 保存配置
            
            # 关闭所有窗口
            if self.watchlist_window:
                self.watchlist_window.close()
            if self.etf_analysis:
                self.etf_analysis.close()
            
            # 销毁主窗口
            if self.root:
                self.root.quit()
                self.root.destroy()
            
        except Exception as e:
            print(f"{l('error_quitting_app')}: {e}")
    
    def capture_all_windows_to_clipboard(self):
        """截取所有相关窗口到剪贴板（包括主窗口、K线图窗口和分时窗口）"""
        try:
            import os
            import tempfile

            from PIL import ImageGrab

            # 获取所有需要截图的窗口
            windows_to_capture = []
            
            # 1. 主窗口
            if self.root.winfo_exists():
                windows_to_capture.append({
                    'window': self.root,
                    'name': '主窗口'
                })
            
            # 2. 查找所有K线图窗口
            for child in self.root.winfo_children():
                if hasattr(child, 'winfo_class') and child.winfo_class() == 'Toplevel':
                    # 检查是否是K线图窗口
                    if hasattr(child, 'title') and 'K线图' in child.title():
                        windows_to_capture.append({
                            'window': child,
                            'name': 'K线图窗口'
                        })
                        
                        # 3. 查找该K线图窗口的分时窗口
                        for kline_child in child.winfo_children():
                            if hasattr(kline_child, 'winfo_class') and kline_child.winfo_class() == 'Toplevel':
                                if hasattr(kline_child, 'title') and '分时' in kline_child.title():
                                    windows_to_capture.append({
                                        'window': kline_child,
                                        'name': '分时窗口'
                                    })
            
            if not windows_to_capture:
                print("没有找到需要截图的窗口")
                return
            
            # 计算所有窗口的边界框
            min_x = float('inf')
            min_y = float('inf')
            max_x = float('-inf')
            max_y = float('-inf')
            
            for window_info in windows_to_capture:
                window = window_info['window']
                if window.winfo_exists():
                    x = window.winfo_rootx()
                    y = window.winfo_rooty()
                    w = window.winfo_width()
                    h = window.winfo_height()
                    
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    max_x = max(max_x, x + w)
                    max_y = max(max_y, y + h)
                    
                    print(f"[DEBUG] {window_info['name']}: x={x}, y={y}, w={w}, h={h}")
            
            if min_x == float('inf'):
                print("没有有效的窗口可以截图")
                return
            
            # 确保所有窗口都在最前面
            for window_info in windows_to_capture:
                window = window_info['window']
                if window.winfo_exists():
                    window.lift()
                    window.update()
            
            # 等待一下确保窗口完全显示
            self.root.after(200)
            
            # 截取整个区域
            bbox = (int(min_x), int(min_y), int(max_x), int(max_y))
            print(f"[DEBUG] 截图区域: {bbox}")
            
            image = ImageGrab.grab(bbox=bbox)
            
            # 转换为RGB模式(去除alpha通道)
            if image.mode == 'RGBA':
                image = image.convert('RGB')
            
            # 创建临时文件保存图片
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            image.save(temp_file.name, format='JPEG', quality=95)
            temp_file.close()
            
            # 使用osascript将图片复制到剪贴板
            os.system(f"osascript -e 'set the clipboard to (read (POSIX file \"{temp_file.name}\") as JPEG picture)'")
            
            # 删除临时文件
            os.unlink(temp_file.name)
            
            print("capture_success - 已截取所有窗口")
            
        except Exception as e:
            print(f"capture_failed: {str(e)}")
            import traceback
            traceback.print_exc()


# 修改create_main_window函数名为create_main_window
def create_main_window():
    root = tk.Tk()
    window = MainWindow(root)
    window.show()  # 使用BaseWindow的show方法
    
    # 启动时打开自选列表窗口
    window.show_watchlist()
    
    return window

if __name__ == "__main__":
    main_window = create_main_window()
    main_window.root.mainloop()