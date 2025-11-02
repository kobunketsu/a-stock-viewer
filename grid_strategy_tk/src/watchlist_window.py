import gc
import json
import multiprocessing
import os
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from queue import Empty, Queue
from tkinter import messagebox, simpledialog, ttk

import akshare as ak
import pypinyin  # 添加拼音支持
import trading_utils
from akshare_wrapper import akshare
from base_window import BaseWindow
from conditions import (CostAndConcentrationCondition, CostCrossMaCondition,
                        CostCrossPriceBodyCondition, CostPriceCompareCondition,
                        InstitutionTradingCondition, KdjCrossCondition,
                        OversoldCondition, PriceAboveMA5Condition,
                        PriceBelowMA5Condition, Signal, SignalLevel,
                        SignalMark)
from locales.localization import l
from stock_analysis_engine import ETFAnalysisEngine
from stock_kline_window import ETFKLineWindow
from trading_utils import (get_realtime_quote, get_symbol_info,
                           get_symbol_info_by_name)
from window_manager import WindowManager


class WatchlistWindow(BaseWindow):
    def __init__(self, parent):
        super().__init__(parent)
        self.current_list = "默认"
        self.watchlists = {
            "默认": [], 
            "板块": [],
            "买入信号": [],  # 新增买入信号列表
            "卖出信号": [],  # 新增卖出信号列表
            "超跌": [],     # 新增超跌列表
            "退市": [],     # 新增退市列表
            "龙虎榜": []    # 新增龙虎榜列表
        }
        self.symbols = {}
        self.grid_rows = 1  # 默认1行
        self.grid_cols = 5  # 默认4列
        self.search_after_id = None  # 用于延迟搜索
        self.original_items = []  # 保存原始列表项
        # 添加缓存字典，用于保存每个列表的数据
        self.list_cache = {}  # {list_name: [(name, code, price, change), ...]}
        # 添加分析引擎
        from stock_analysis_engine import ETFAnalysisEngine
        self.analysis_engine = ETFAnalysisEngine()
        # 添加加载控制标志
        self.loading_boards = False
        self.loading_etf = False
        # 添加信号列表缓存
        self.signal_cache = {
            "买入信号": {"timestamp": None, "data": []},
            "卖出信号": {"timestamp": None, "data": []},
            "超跌": {"timestamp": None, "data": []},
            "退市": {"timestamp": None, "data": []},
            "龙虎榜": {"timestamp": None, "data": []}
        }
        self.cache_timeout = 300  # 缓存超时时间(秒)
        
        # 添加信息列和信号列显示控制变量
        self.show_info_columns = False  # 默认不显示信息和信号列内容
        self.show_trend_columns = False  # 默认不显示趋势列内容
        
        # 设置线程池大小
        self.max_workers = 1 #multiprocessing.cpu_count()
        
        # 添加需要排除的股票代码前缀
        self.excluded_prefixes = {
            '8',    # 北交所
            '688',  # 科创板
            '689',  # 科创板
            '51',   # ETF基金
            '15',   # ETF基金
            '16',   # ETF基金
            '56',   # 期权
            '90',   # B股
            '201',  # 债券
            '202',  # 债券
            '203',  # 债券
            '204',  # 债券
        }
        
        # 添加交易时间配置
        self.trading_hours = {
            'start': (9, 30),  # 上午开盘时间 9:30
            'end': (15, 0)     # 下午收盘时间 15:00
        }
        
        # 添加缓存文件路径
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        self.signal_cache_file = os.path.join(config_dir, "signal_cache.json")
        
        # 初始化信号缓存
        self.signal_cache = self.load_signal_cache()
        
        self.industry_cache = {}  # 缓存行业数据
        
        # 趋势数据缓存
        self.trend_cache = {}  # 缓存趋势计算结果
        self.trend_cache_file = os.path.join(config_dir, "trend_cache.json")
        self.trend_cache_timeout = 24 * 60 * 60  # 趋势缓存超时时间(24小时)
        
        # 算法版本号 - 当修改趋势判断算法参数时，需要更新此版本号
        self.version = "v1.3.0"  # 当前算法版本号 - 新增次日板MA5偏离度计算
        
        # API调用限制配置
        self.api_config = {
            'max_concurrent_requests': 3,  # 最大并发请求数
            'request_delay': 0.5,  # 请求间隔（秒）
            'batch_size': 10,  # 批处理大小
            'max_retries': 3,  # 最大重试次数
            'retry_delay': 1.0,  # 重试延迟（秒）
            'max_consecutive_errors': 5,  # 最大连续错误次数，超过则取消计算
        }
        
        # 加载趋势缓存
        self.trend_cache = self.load_trend_cache()
        
        # 清除旧版本缓存
        self.clear_old_version_cache()
        
        self.load_watchlists()
        
    def create_window(self):
        """创建自选列表窗口"""
        self.window = tk.Toplevel(self.parent)
        self.window.title(l("watchlist"))
        self.window.geometry("800x600")
        
        # 创建主框架
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 顶部工具栏
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        # 列表选择下拉框
        self.list_var = tk.StringVar(value=self.current_list)
        self.list_combo = ttk.Combobox(
            toolbar, 
            textvariable=self.list_var,
            values=self.get_watchlist_names(),  # 使用动态获取的列表名称
            state="readonly",
            width=15
        )
        self.list_combo.pack(side=tk.LEFT, padx=5)
        self.list_combo.bind('<<ComboboxSelected>>', self.on_list_changed)
        
        # 创建正方形按钮，宽高1:1
        style = ttk.Style()
        style.configure('Square.TButton', width=1.5)  # 设置宽度为3个字符宽度
        ttk.Button(toolbar, text="⚙️", command=self.classify_selected, style='Square.TButton').pack(side=tk.LEFT, padx=2)
        
        # 新建列表按钮
        ttk.Button(toolbar, text=l("new_list"), command=self.create_new_list).pack(side=tk.LEFT, padx=2)
        
        # 删除列表按钮
        ttk.Button(toolbar, text=l("delete_list"), command=self.delete_current_list).pack(side=tk.LEFT, padx=2)
        
        # 删除选中按钮
        ttk.Button(toolbar, text=l("delete_selected"), command=self.delete_selected).pack(side=tk.LEFT, padx=2)
        
        # 刷新按钮
        ttk.Button(toolbar, text=l("refresh")+"(⌘R)", command=self.refresh_data).pack(side=tk.LEFT, padx=2)
        # 绑定快捷键
        self.window.bind("<Command-r>", lambda e: self.refresh_data())        
        
        # 刷新信息按钮
        ttk.Button(toolbar, text="信息(⌘I)", command=self.refresh_info_columns).pack(side=tk.LEFT, padx=2)
        # 绑定快捷键
        self.window.bind("<Command-i>", lambda e: self.refresh_info_columns())
        
        # 刷新趋势按钮
        ttk.Button(toolbar, text="趋势(⌘T)", command=self.refresh_trend_columns).pack(side=tk.LEFT, padx=2)
        # 绑定快捷键
        self.window.bind("<Command-t>", lambda e: self.refresh_trend_columns())
        
        # K线图按钮
        ttk.Button(toolbar, text=l("show_klines")+"(⌘K)", command=self.show_selected_klines).pack(side=tk.LEFT, padx=2)
        # 绑定快捷键
        self.window.bind("<Command-k>", lambda e: self.show_selected_klines())        

        # 网格大小设置
        grid_frame = ttk.Frame(toolbar)
        grid_frame.pack(side=tk.LEFT, padx=(10,2))
        
        ttk.Label(grid_frame, text=l("grid_size")).pack(side=tk.LEFT)
        
        # 行设置
        ttk.Label(grid_frame, text="行").pack(side=tk.LEFT, padx=(5,2))
        self.grid_rows_var = tk.StringVar(value=str(self.grid_rows))
        rows_combo = ttk.Combobox(
            grid_frame,
            textvariable=self.grid_rows_var,
            values=["1", "2", "3", "4", "5"],
            state="readonly",
            width=2
        )
        rows_combo.pack(side=tk.LEFT)
        rows_combo.bind('<<ComboboxSelected>>', self.on_grid_size_changed)
        
        # 列设置
        ttk.Label(grid_frame, text="列").pack(side=tk.LEFT, padx=(5,2))
        self.grid_cols_var = tk.StringVar(value=str(self.grid_cols))
        cols_combo = ttk.Combobox(
            grid_frame,
            textvariable=self.grid_cols_var,
            values=["1", "2", "3", "4","5"],
            state="readonly",
            width=2
        )
        cols_combo.pack(side=tk.LEFT)
        cols_combo.bind('<<ComboboxSelected>>', self.on_grid_size_changed)
        
        # 搜索框架
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame).pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 绑定搜索事件
        self.search_var.trace_add("write", self.on_search_changed)
        search_entry.bind('<Return>', self.on_search_enter)
        
        # 添加放大镜按钮
        search_button = ttk.Label(search_frame, text="🔍")
        search_button.pack(side=tk.LEFT, padx=(2, 0))
        search_button.bind('<Button-1>', self.add_symbol)  # 点击放大镜也触发搜索
        
        # 添加缓存管理按钮
        cache_button = ttk.Button(search_frame, text="缓存管理", command=self.show_cache_management)
        cache_button.pack(side=tk.LEFT, padx=(5, 0))
        
        # 创建一个容器框架来包含表格和统计栏
        table_container = ttk.Frame(main_frame)
        table_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建表格和滚动条的框架
        tree_frame = ttk.Frame(table_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建表格
        columns = ("name", "code", "industry", "change", "cost_change", "ma5_deviation", "next_day_limit_up_ma5_deviation", "intraday_trend", "day_trend", "week_trend", "month_trend", "holders", "capita", "message", "level")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # 设置列标题并绑定点击事件
        self.tree.heading("name", text=l("symbol_name"), command=lambda: self.sort_treeview("name"))
        self.tree.heading("code", text=l("symbol_code"), command=lambda: self.sort_treeview("code"))
        self.tree.heading("industry", text=l("industry"), command=lambda: self.sort_treeview("industry"))
        self.tree.heading("change", text=l("price_change"), command=lambda: self.sort_treeview("change"))
        self.tree.heading("cost_change", text="股价成本涨幅", command=lambda: self.sort_treeview("cost_change"))
        self.tree.heading("ma5_deviation", text="MA5偏离", command=lambda: self.sort_treeview("ma5_deviation"))
        self.tree.heading("next_day_limit_up_ma5_deviation", text="次日板MA5偏离", command=lambda: self.sort_treeview("next_day_limit_up_ma5_deviation"))
        self.tree.heading("intraday_trend", text="日内趋势", command=lambda: self.sort_treeview("intraday_trend"))
        self.tree.heading("day_trend", text="日趋势", command=lambda: self.sort_treeview("day_trend"))
        self.tree.heading("week_trend", text="周趋势", command=lambda: self.sort_treeview("week_trend"))
        self.tree.heading("month_trend", text="月趋势", command=lambda: self.sort_treeview("month_trend"))
        self.tree.heading("holders", text="股东增幅", command=lambda: self.sort_treeview("holders"))
        self.tree.heading("capita", text="持股增幅", command=lambda: self.sort_treeview("capita"))
        self.tree.heading("message", text=l("message"), command=lambda: self.sort_treeview("message"))
        self.tree.heading("level", text=l("signal_level"), command=lambda: self.sort_treeview("level"))
        
        # 设置列宽
        self.tree.column("name", width=100)
        self.tree.column("code", width=80)
        self.tree.column("industry", width=100)
        self.tree.column("change", width=80)
        self.tree.column("cost_change", width=100)
        self.tree.column("ma5_deviation", width=80)
        self.tree.column("next_day_limit_up_ma5_deviation", width=120)
        self.tree.column("intraday_trend", width=100)
        self.tree.column("day_trend", width=80)
        self.tree.column("week_trend", width=80)
        self.tree.column("month_trend", width=80)
        self.tree.column("holders", width=80)
        self.tree.column("capita", width=80)
        self.tree.column("message", width=200)
        self.tree.column("level", width=80)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 放置表格和滚动条
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 设置表格可以获得焦点，以便响应键盘事件
        self.tree.focus_set()
        
        # 创建统计栏框架，放在表格下方
        self.stats_frame = ttk.Frame(table_container)
        self.stats_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 创建统计标签，使其填充整个统计栏
        self.stats_label = ttk.Label(self.stats_frame, text="", anchor=tk.W)
        self.stats_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 绑定选中项变化事件
        self.tree.bind('<<TreeviewSelect>>', self.on_selection_changed)
        
        # 绑定回车键事件到表格
        self.tree.bind('<Return>', lambda e: self.show_selected_klines())
        
        # 初始化排序状态
        self.sort_reverse = False
        self.last_sort_column = None
        
        # 配置标签颜色
        self.tree.tag_configure('buy', foreground='#FF4444')  # 买入信号绿色
        self.tree.tag_configure('sell', foreground='#44CC44')  # 卖出信号红色
        
        # 延迟加载当前列表数据，避免启动时自动调用板块数据更新
        # 只在用户主动切换列表时才加载数据
        if self.current_list not in ["板块", "ETF"]:
            self.load_list_data()
        
        # 在setup_window之前添加复制快捷键绑定
        self.window.bind("<Command-c>", self.copy_selected_to_clipboard)
        
        # 设置窗口快捷键和关闭协议
        self.setup_window()
        
    def load_watchlists(self):
        """从文件加载自选列表数据"""
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        self.watchlist_file = os.path.join(config_dir, "watchlists.json")
        
        # 确保配置目录存在
        os.makedirs(config_dir, exist_ok=True)
        
        # 初始化默认列表结构
        self.watchlists = {
            "默认": [],
            "板块": [],
            "买入信号": [],
            "卖出信号": [],
            "超跌": [],
            "退市": []
        }
        
        if os.path.exists(self.watchlist_file):
            try:
                with open(self.watchlist_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.symbols = data.get("symbols", {})
                    saved_lists = data.get("lists", {"默认": []})
                    
                    # 合并保存的列表，但保留信号列表为空
                    for list_name, symbols in saved_lists.items():
                        if list_name not in ["板块", "买入信号", "卖出信号", "超跌", "退市"]:
                            self.watchlists[list_name] = symbols
                    
                    self.current_list = data.get("current", "默认")
                    
                    if not self.symbols:
                        self._convert_old_format()
            except Exception as e:
                print(f"Error loading watchlists: {e}")
    
    def _convert_old_format(self):
        """转换旧格式数据到新格式"""
        self.symbols = {}
        for list_name, symbols in self.watchlists.items():
            for symbol in symbols:
                if symbol not in self.symbols:
                    name, _ = get_symbol_info(symbol)
                    self.symbols[symbol] = {
                        "name": name,
                        "lists": [list_name]
                    }
                else:
                    self.symbols[symbol]["lists"].append(list_name)
    
    def save_watchlists(self):
        """保存自选列表数据到文件，不保存板块列表"""
        try:
            # 过滤掉板块列表和动态列表
            lists_to_save = {k: v for k, v in self.watchlists.items() if k not in ["板块", "退市"]}
            
            data = {
                "symbols": self.symbols,
                "lists": lists_to_save,
                "current": self.current_list
            }
            with open(self.watchlist_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Error saving watchlists: {e}")
    
    def _load_list_data_internal(self):
        """内部加载列表数据的实现"""
        # 清空原始数据
        self.original_items = []
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 如果是板块列表，特殊处理
        if self.current_list == "板块":
            self.load_board_data()
            return
        
        # 如果是ETF列表，特殊处理
        if self.current_list == "ETF":
            self.load_etf_data()
            return
        
        # 其他列表的正常处理
        symbols = self.watchlists.get(self.current_list, [])
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在加载数据... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                percent = int((current / total) * 100)
                progress_label["text"] = f"正在加载数据... {percent}%"
            self.window.after(0, _update)
        
        def update_tree_item(symbol, name, price, change):
            """更新表格项"""
            def _update():
                try:
                    # 获取行业信息
                    industry = self.get_stock_industry(symbol)
                    
                    # 获取股东/持股增幅
                    holders_change, capita_change = self.get_latest_holders_count(symbol)
                    
                    # 根据控制变量决定是否加载信息列内容
                    if self.show_info_columns:
                        # 创建分析引擎实例
                        analysis_engine = ETFAnalysisEngine()
                        # 获取条件触发信息
                        conditions = [
                            # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                            CostAndConcentrationCondition(),
                            CostCrossMaCondition(),
                            CostPriceCompareCondition(),
                            CostCrossPriceBodyCondition()
                        ]

                        trigger_info = analysis_engine.get_latest_condition_trigger(symbol, conditions)
                        message = trigger_info['message'] if trigger_info else ''
                        level = trigger_info.get('level', '') if trigger_info else ''
                    else:
                        # 默认情况下信息列和信号列留空
                        message = ''
                        level = ''
                    
                    # 根据控制变量决定是否加载趋势列内容
                    if self.show_trend_columns:
                        day_trend, week_trend, month_trend, ma5_deviation, cost_change = self.calculate_trend_gains(symbol)
                    else:
                        # 默认情况下趋势列留空
                        day_trend = ''
                        week_trend = ''
                        month_trend = ''
                        ma5_deviation = ''
                        cost_change = ''
                    
                    
                    item_values = (name, symbol, industry, change, cost_change, ma5_deviation, day_trend, week_trend, month_trend, holders_change, capita_change, message, level)
                    item = self.tree.insert("", tk.END, values=item_values)
                    self.original_items.append(item_values)
                    
                    # 根据信号等级设置行颜色
                    if level:
                        if level == SignalLevel.BUY.value:
                            self.tree.item(item, tags=('buy',))
                        elif level == SignalLevel.BULLISH.value:
                            self.tree.item(item, tags=('bullish',))
                        elif level == SignalLevel.SELL.value:
                            self.tree.item(item, tags=('sell',))
                        elif level == SignalLevel.BEARISH.value:
                            self.tree.item(item, tags=('bearish',))
                except Exception as e:
                    print(f"更新表格项时出错: {str(e)}")
                    # 发生错误时仍然添加项，但使用默认值
                    item_values = (name, symbol, '', '--', '-', '', '', '', '--', '--', '', '')  # 占位
                    item = self.tree.insert("", tk.END, values=item_values)
                    self.original_items.append(item_values)
                
            self.window.after(0, _update)
        
        def fetch_data():
            """获取数据的线程函数"""    
            try:
                total = len(symbols)


                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {}
                    
                    for symbol in symbols:
                        # 检查是否为板块代码
                        if str(symbol).startswith('BK'):
                            # 对于板块代码，使用不同的数据获取方法
                            futures[symbol] = (
                                executor.submit(lambda: (symbol, None)),  # 名称直接使用代码
                                executor.submit(self.get_board_quote, symbol)  # 获取板块行情
                            )
                        else:
                            # 普通股票代码使用原有方法
                            futures[symbol] = (
                                executor.submit(get_symbol_info, symbol),
                                executor.submit(get_realtime_quote, symbol)
                            )
                    
                    for i, symbol in enumerate(symbols, 1):
                        try:
                            info_future, quote_future = futures[symbol]
                            
                            if str(symbol).startswith('BK'):
                                # 处理板块数据
                                _, _ = info_future.result()  # 忽略返回值
                                quote = quote_future.result()
                                if quote is not None:
                                    name = quote.get('name', symbol)  # 使用行情中的名称
                                    change = quote.get('change', '--')
                                else:
                                    name = symbol
                                    change = '--'
                            else:
                                # 处理普通股票数据
                                name, _ = info_future.result()
                                quote = quote_future.result()
                                change = quote.get('change', '--') if quote else '--'
                            
                            update_tree_item(symbol, name, None, change)
                            update_progress(i, total)
                            
                        except Exception as e:
                            print(f"Error loading data for {symbol}: {e}")
                            update_tree_item(symbol, "加载失败", None, "--")
                
                def cleanup():
                    progress_label.destroy()
                    # 更新缓存
                    self.list_cache[self.current_list] = self.original_items.copy()
                    # 如果有排序设置，应用排序
                    if self.last_sort_column:
                        self.sort_treeview(self.last_sort_column)
                    # 更新统计信息
                    self.update_statistics()
                self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error():
                    messagebox.showerror("错误", f"加载数据失败: {str(e)}")
                    progress_label.destroy()
                    # 即使出错也更新统计
                    self.update_statistics()
                self.window.after(0, show_error)
        
        threading.Thread(target=fetch_data, daemon=True).start()

    def get_board_quote(self, board_code):
        """获取板块行情数据"""
        try:
            today = datetime.now().strftime("%Y%m%d")
            # 通过板块代码获取板块名称
            boards = ak.stock_board_concept_name_em()
            board_info = boards[boards['板块代码'] == board_code]
            
            if not board_info.empty:
                name = board_info.iloc[0]['板块名称']
                # 获取板块行情
                hist_data = ak.stock_board_concept_hist_em(
                    symbol=name,
                    period="daily",
                    start_date=today,
                    end_date=today,
                    adjust=""
                )
                
                if not hist_data.empty:
                    return {
                        'name': name,
                        'change': hist_data.iloc[-1]['涨跌幅']
                    }
            
            return {'name': board_code, 'change': '--'}
            
        except Exception as e:
            print(f"获取板块行情失败: {str(e)}")
            return {'name': board_code, 'change': '--'}

    def add_symbol(self, event=None):
        """添加新股票到列表"""
        symbol = str(self.search_var.get()).strip()  # 强制转换为字符串
        if not symbol:
            return
        
        # 如果当前是板块列表、ETF列表或信号列表，不允许添加
        if self.current_list in ['板块', 'ETF', '买入信号', '卖出信号', '超跌', '龙虎榜']:
            messagebox.showinfo(l("info"), l("cannot_add_to_this_list"))
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
            
            # 检查是否已存在
            if symbol in self.watchlists[self.current_list]:
                messagebox.showinfo(l("info"), l("symbol_already_exists"))
                return
            
            # 添加到列表
            self.watchlists[self.current_list].append(symbol)
            self.save_watchlists()
            
            # 清除当前列表缓存
            if self.current_list in self.list_cache:
                del self.list_cache[self.current_list]
            
            # 刷新显示
            self.load_list_data()
            
            # 清空搜索框
            self.search_var.set("")
            
        except Exception as e:
            messagebox.showerror(l("error"), str(e))
    
    def delete_selected(self):
        """删除选中的股票"""
        selected = self.tree.selection()
        if not selected:
            return
        
        if messagebox.askyesno(l("confirm"), l("confirm_delete_selected")):
            # 使用集合避免重复
            symbols_to_delete = set()
            
            for item in selected:
                values = self.tree.item(item)["values"]
                # 提取股票代码，确保是6位格式
                raw_code = str(values[1])
                # 处理龙虎榜的#前缀和点号
                if raw_code.startswith('#'):
                    # 龙虎榜股票代码，去掉#前缀
                    symbol = raw_code[1:]
                elif '.' in raw_code:
                    # 如果代码包含点号（如000006.SZ），取点号前的部分
                    symbol = raw_code.split('.')[0]
                else:
                    symbol = raw_code
                # 确保代码是6位格式
                symbol = symbol.zfill(6)
                
                symbols_to_delete.add(symbol)
            
            # 统一处理删除操作
            for symbol in symbols_to_delete:
                # 从当前列表中移除（处理可能存在的不同格式）
                current_list = self.watchlists[self.current_list]
                # 查找可能存在的不同格式代码
                matching_codes = [code for code in current_list if code.endswith(symbol)]
                
                for code in matching_codes:
                    current_list.remove(code)
                    
                    # 更新symbols数据
                    if code in self.symbols:
                        # 从股票所属的列表中移除当前列表
                        if self.current_list in self.symbols[code]["lists"]:
                            self.symbols[code]["lists"].remove(self.current_list)
                        
                        # 如果股票不再属于任何列表，则完全删除
                        if not self.symbols[code]["lists"]:
                            del self.symbols[code]
            
            # 保存更新后的数据
            self.save_watchlists()
            
            # 清除当前列表的缓存
            if self.current_list in self.list_cache:
                del self.list_cache[self.current_list]
            
            # 重新加载数据（强制刷新）
            self.load_list_data()
    
    def refresh_data(self):
        """刷新数据"""
        # 清除当前列表的缓存
        if self.current_list in self.list_cache:
            del self.list_cache[self.current_list]
        
        # 清除信号列表缓存
        if self.current_list in ["买入信号", "卖出信号", "超跌"]:
            if self.current_list in self.signal_cache:
                del self.signal_cache[self.current_list]
                # 保存更新后的缓存
                self.save_signal_cache()
        
        # 重新加载数据
        self.load_list_data()
        
        # 如果启用了信息列显示，则更新所有项的条件触发信息
        if self.show_info_columns:
            self.update_info_columns()

    def refresh_info_columns(self):
        """刷新信息列和信号列"""
        # 启用信息列显示
        self.show_info_columns = True
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在刷新信息列... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                try:
                    # 检查窗口和标签是否仍然存在
                    if self.window and progress_label.winfo_exists():
                        percent = int((current / total) * 100)
                        progress_label["text"] = f"正在刷新信息列... {percent}%"
                except tk.TclError:
                    # 如果组件已被销毁，忽略错误
                    pass
            self.window.after(0, _update)
        
        def update_info_columns():
            """更新信息列和信号列"""
            try:
                items = self.tree.get_children()
                total = len(items)
                
                for i, item in enumerate(items, 1):
                    try:
                        values = self.tree.item(item)["values"]
                        symbol = str(values[1])
                        
                        # 创建分析引擎实例
                        analysis_engine = ETFAnalysisEngine()
                        
                        # 获取最新的条件触发信息
                        conditions = [
                            # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                            CostAndConcentrationCondition(),
                            CostCrossMaCondition(),
                            CostPriceCompareCondition(),
                            CostCrossPriceBodyCondition()
                        ]
                        trigger_info = analysis_engine.get_latest_condition_trigger(symbol, conditions)
                        message = trigger_info['message'] if trigger_info else ''
                        level = trigger_info.get('level', '') if trigger_info else ''
                        
                        # 更新消息列和信号等级列 (按新列顺序)
                        new_values = list(values)
                        while len(new_values) < 8:
                            new_values.append('')
                        new_values[6] = message  # 消息列
                        new_values[7] = level   # 信号等级列
                        self.tree.item(item, values=new_values)
                        
                        # 根据信号等级设置行颜色
                        if level:
                            if level == SignalLevel.BUY.value:
                                self.tree.item(item, tags=('buy',))
                            elif level == SignalLevel.BULLISH.value:
                                self.tree.item(item, tags=('bullish',))
                            elif level == SignalLevel.SELL.value:
                                self.tree.item(item, tags=('sell',))
                            elif level == SignalLevel.BEARISH.value:
                                self.tree.item(item, tags=('bearish',))
                        
                        # 更新进度
                        update_progress(i, total)
                        
                    except Exception as item_error:
                        print(f"处理项目 {i} 时出错: {str(item_error)}")
                        continue
                
                # 清理进度显示
                def cleanup():
                    try:
                        if progress_label.winfo_exists():
                            progress_label.destroy()
                    except tk.TclError:
                        pass
                self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error():
                    try:
                        messagebox.showerror("错误", f"刷新信息列失败: {str(e)}")
                        if progress_label.winfo_exists():
                            progress_label.destroy()
                    except tk.TclError:
                        pass
                self.window.after(0, show_error)
        
        # 在后台线程中执行更新
        threading.Thread(target=update_info_columns, daemon=True).start()

    def refresh_trend_columns(self):
        """刷新趋势列"""
        # 检查窗口是否存在
        if not hasattr(self, 'window') or self.window is None:
            print("窗口未初始化，无法刷新趋势列")
            return
            
        # 启用趋势列显示
        self.show_trend_columns = True
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在刷新趋势列... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                try:
                    # 检查窗口和标签是否仍然存在
                    if self.window and progress_label.winfo_exists():
                        percent = int((current / total) * 100)
                        progress_label["text"] = f"正在刷新趋势列... {percent}%"
                except tk.TclError:
                    # 如果组件已被销毁，忽略错误
                    pass
            self.window.after(0, _update)
        
        def update_trend_columns():
            """更新趋势列"""
            try:
                # 检查tree是否存在
                if not hasattr(self, 'tree') or self.tree is None:
                    print("表格未初始化，跳过趋势列更新")
                    return
                    
                items = self.tree.get_children()
                total = len(items)
                
                # API调用限制参数
                max_concurrent_requests = self.api_config['max_concurrent_requests']
                request_delay = self.api_config['request_delay']
                batch_size = self.api_config['batch_size']
                max_consecutive_errors = self.api_config['max_consecutive_errors']
                
                # 连续错误计数器
                consecutive_errors = 0
                cancelled = False
                
                print(f"开始批量计算趋势，共{total}个项目，使用{max_concurrent_requests}个并发线程")
                
                # 分批处理
                for batch_start in range(0, total, batch_size):
                    # 检查是否已取消
                    if cancelled:
                        print("计算已取消，停止处理")
                        break
                        
                    batch_end = min(batch_start + batch_size, total)
                    batch_items = items[batch_start:batch_end]
                    
                    print(f"处理批次 {batch_start//batch_size + 1}: 项目 {batch_start+1}-{batch_end}")
                    
                    # 使用线程池处理当前批次
                    with ThreadPoolExecutor(max_workers=max_concurrent_requests) as executor:
                        futures = {}
                        
                        for i, item in enumerate(batch_items):
                            values = self.tree.item(item)["values"]
                            # 确保代码是6位格式，处理龙虎榜的#前缀
                            raw_code = str(values[1])
                            if raw_code.startswith('#'):
                                # 龙虎榜股票代码，去掉#前缀
                                symbol = raw_code[1:]
                            elif '.' in raw_code:
                                symbol = raw_code.split('.')[0]
                            else:
                                symbol = raw_code
                            symbol = symbol.zfill(6)
                            
                            # 提交任务到线程池
                            future = executor.submit(self.calculate_trend_gains, symbol)
                            futures[future] = (item, values, batch_start + i + 1, symbol)
                        
                        # 收集结果
                        batch_errors = 0
                        for future in as_completed(futures):
                            item, values, item_index, symbol = futures[future]
                            
                            try:
                                # 获取计算结果
                                day_trend, week_trend, month_trend, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, cost_change = future.result()
                                
                                # 检查是否有错误
                                if any(trend == 'error' for trend in [day_trend, week_trend, month_trend, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, cost_change]):
                                    batch_errors += 1
                                
                                # 更新趋势列 (按新列顺序)
                                new_values = list(values)
                                while len(new_values) < 15:
                                    new_values.append('')
                                
                                # 确保证券代码为6位格式
                                new_values[1] = symbol.zfill(6)
                                
                                # 获取当前价格和涨幅信息
                                try:
                                    from datetime import datetime, timedelta

                                    import akshare as ak
                                    from src.trading_utils import \
                                        get_current_price

                                    # 获取当前日期
                                    current_date = datetime.now().strftime('%Y-%m-%d')
                                    
                                    # 获取当前价格
                                    current_price = get_current_price(symbol, current_date, "STOCK")
                                    if current_price and current_price > 0:
                                        # 获取前一交易日数据
                                        end_date = datetime.now().strftime('%Y%m%d')
                                        start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
                                        
                                        df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust='qfq')
                                        if not df.empty and len(df) >= 2:
                                            prev_close = float(df['收盘'].iloc[-2])  # 前一交易日收盘价
                                            change_pct = ((current_price - prev_close) / prev_close) * 100
                                            change_str = f"{change_pct:+.2f}%"
                                        else:
                                            change_str = new_values[3]  # 保持原有涨幅
                                    else:
                                        change_str = new_values[3]  # 保持原有涨幅
                                except Exception as e:
                                    print(f"获取涨幅失败 {symbol}: {e}")
                                    change_str = new_values[3]  # 保持原有涨幅
                                
                                new_values[3] = change_str        # 涨幅列
                                new_values[4] = cost_change       # 股价成本涨幅列
                                new_values[5] = ma5_deviation     # MA5偏离度列
                                new_values[6] = next_day_limit_up_ma5_deviation  # 次日板MA5偏离度列
                                new_values[7] = intraday_trend    # 日内趋势列
                                new_values[8] = day_trend         # 日趋势列
                                new_values[9] = week_trend        # 周趋势列
                                new_values[10] = month_trend      # 月趋势列
                                self.tree.item(item, values=new_values)
                                
                                # 更新进度
                                update_progress(item_index, total)
                                
                            except Exception as item_error:
                                print(f"处理项目 {item_index} 时出错: {str(item_error)}")
                                batch_errors += 1
                                # 设置错误值
                                new_values = list(values)
                                while len(new_values) < 15:
                                    new_values.append('')
                                
                                # 确保证券代码为6位格式
                                new_values[1] = symbol.zfill(6)
                                
                                # 保持原有涨幅，其他列设为error
                                new_values[3] = new_values[3] if len(new_values) > 3 else '-'  # 保持原有涨幅
                                new_values[4] = 'error'    # 股价成本涨幅列
                                new_values[5] = 'error'    # MA5偏离度列
                                new_values[6] = 'error'    # 次日板MA5偏离度列
                                new_values[7] = 'error'    # 日内趋势列
                                new_values[8] = 'error'    # 日趋势列
                                new_values[9] = 'error'    # 周趋势列
                                new_values[10] = 'error'    # 月趋势列
                                self.tree.item(item, values=new_values)
                                update_progress(item_index, total)
                        
                        # 更新连续错误计数
                        if batch_errors > 0:
                            consecutive_errors += batch_errors
                            print(f"批次 {batch_start//batch_size + 1} 有 {batch_errors} 个错误，连续错误总数: {consecutive_errors}")
                        else:
                            consecutive_errors = 0  # 重置连续错误计数
                        
                        # 检查是否超过最大连续错误数
                        if consecutive_errors >= max_consecutive_errors:
                            print(f"连续错误数达到 {max_consecutive_errors}，取消后续计算")
                            cancelled = True
                            break
                    
                    # 批次间延迟，避免API频繁调用
                    if batch_end < total and not cancelled:
                        print(f"批次完成，等待{request_delay}秒后处理下一批次...")
                        time.sleep(request_delay)
                
                # 清理进度显示
                def cleanup():
                    try:
                        if progress_label.winfo_exists():
                            if cancelled:
                                progress_label["text"] = f"计算已取消 (连续错误数: {consecutive_errors})"
                                # 延迟3秒后销毁
                                self.window.after(3000, progress_label.destroy)
                            else:
                                progress_label.destroy()
                    except tk.TclError:
                        pass
                self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error():
                    try:
                        if hasattr(self, 'window') and self.window:
                            messagebox.showerror("错误", f"刷新趋势列失败: {str(e)}")
                        if progress_label.winfo_exists():
                            progress_label.destroy()
                    except tk.TclError:
                        pass
                if hasattr(self, 'window') and self.window:
                    self.window.after(0, show_error)
        
        # 在后台线程中执行更新
        threading.Thread(target=update_trend_columns, daemon=True).start()

    def calculate_intraday_trend(self, symbol: str) -> str:
        """计算日内趋势（5分钟级别布林带突破跌破次数）
        
        Args:
            symbol: 股票代码
            
        Returns:
            str: 日内趋势字符串，格式为"破上轨{次数}下轨{次数}"，如"破上轨2下轨1"
        """
        try:
            from datetime import datetime, timedelta

            import akshare as ak
            import pandas as pd
            from trading_utils import (calculate_bollinger_bands,
                                       detect_bollinger_breakthrough_breakdown)

            # 获取最近一个交易日的5分钟数据
            today = datetime.now()
            # 如果是周末，获取上周五的数据
            if today.weekday() >= 5:  # 周六(5)或周日(6)
                days_back = today.weekday() - 4  # 周六回退1天，周日回退2天
                target_date = today - timedelta(days=days_back)
            else:
                target_date = today
            
            # 获取最近一个交易日的1分钟数据并转换为5分钟数据（与分时图保持一致）
            try:
                # 尝试获取当日1分钟数据
                df_1min = ak.stock_zh_a_hist_min_em(symbol=symbol, period="1", adjust="qfq")
                if df_1min.empty:
                    # 如果没有1分钟数据，直接返回'-'
                    print(f"没有1分钟数据 {symbol}")
                    return '-'
            except Exception as e:
                print(f"获取1分钟数据失败 {symbol}: {e}")
                return '-'
            
            if df_1min.empty:
                return '-'
            
            # 转换列名为英文（akshare返回的是中文列名）
            if '收盘' in df_1min.columns:
                df_1min['close'] = df_1min['收盘']
            if '开盘' in df_1min.columns:
                df_1min['open'] = df_1min['开盘']
            if '最高' in df_1min.columns:
                df_1min['high'] = df_1min['最高']
            if '最低' in df_1min.columns:
                df_1min['low'] = df_1min['最低']
            if '成交量' in df_1min.columns:
                df_1min['volume'] = df_1min['成交量']
            
            # 确保数据格式正确
            if '时间' in df_1min.columns:
                df_1min['时间'] = pd.to_datetime(df_1min['时间'])
                df_1min = df_1min.set_index('时间').sort_index()
                
                # 只使用最近一个交易日的数据
                unique_dates = df_1min.index.date
                latest_date = unique_dates[-1]
                df_1min = df_1min[df_1min.index.date == latest_date]
                print(f"[DEBUG] 使用最近交易日 {latest_date} 的1分钟数据，共 {len(df_1min)} 条记录")
                
            elif '日期' in df_1min.columns:
                df_1min['日期'] = pd.to_datetime(df_1min['日期'])
                df_1min = df_1min.set_index('日期').sort_index()
                
                # 只使用最近一个交易日的数据
                unique_dates = df_1min.index.date
                latest_date = unique_dates[-1]
                df_1min = df_1min[df_1min.index.date == latest_date]
                print(f"[DEBUG] 使用最近交易日 {latest_date} 的1分钟数据，共 {len(df_1min)} 条记录")
            
            # 转换为5分钟K线数据（与分时图保持一致）
            df_5min = df_1min.resample('5T', offset='1T').agg({
                'open': 'first',
                'close': 'last',
                'high': 'max',
                'low': 'min',
                'volume': 'sum'
            }).dropna()
            
            if df_5min.empty:
                print(f"[DEBUG] 转换5分钟数据后为空 {symbol}")
                return '-'
            
            print(f"[DEBUG] 转换后5分钟数据，共 {len(df_5min)} 条记录")
            
            # 获取历史5分钟数据用于布林带计算（与分时图保持一致）
            historical_5min_data = self._get_historical_5min_data_for_bollinger(symbol)
            
            # 合并历史数据和当日数据用于布林带计算（与分时图保持一致）
            if historical_5min_data is not None and not historical_5min_data.empty:
                combined_5min_data = pd.concat([historical_5min_data, df_5min])
                print(f"[DEBUG] 合并历史5分钟数据用于布林带计算，总长度: {len(combined_5min_data)}")
            else:
                combined_5min_data = df_5min
                print(f"[DEBUG] 使用当日5分钟数据计算布林带，长度: {len(combined_5min_data)}")
            
            # 计算布林带
            bollinger_data = calculate_bollinger_bands(combined_5min_data, window=20, num_std=2)
            
            if bollinger_data.empty or 'BOLL_UPPER' not in bollinger_data.columns:
                return '-'
            
            # 只保留当日的数据用于突破跌破检测
            if len(bollinger_data) > len(df_5min):
                today_bollinger = bollinger_data.loc[df_5min.index]
            else:
                today_bollinger = bollinger_data
            
            # 检测突破跌破
            result = detect_bollinger_breakthrough_breakdown(
                price_data=df_5min,
                bollinger_upper=today_bollinger['BOLL_UPPER'],
                bollinger_lower=today_bollinger['BOLL_LOWER'],
                resample_freq='5T',
                offset='1min'
            )
            
            breakthrough_count = result['breakthrough_count']
            breakdown_count = result['breakdown_count']
            
            return f"破上轨{breakthrough_count}下轨{breakdown_count}"
            
        except Exception as e:
            print(f"计算日内趋势失败 {symbol}: {e}")
            return '-'
    
    def _load_trade_calendar(self):
        """加载交易日历返回set[date]（与分时图保持一致）"""
        try:
            import pandas as pd
            cal_df = ak.tool_trade_date_hist_sina()
            cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date']).dt.date
            if 'is_trading_day' in cal_df.columns:
                cal_df = cal_df[cal_df['is_trading_day'] == 1]
            return set(cal_df['trade_date'])
        except Exception:
            return set()

    def _get_historical_5min_data_for_bollinger(self, symbol: str):
        """获取历史5分钟数据用于布林带计算（与分时图保持一致）
        
        :param symbol: 股票代码
        :return: 历史5分钟数据DataFrame
        """
        try:
            from datetime import datetime, timedelta

            import akshare as ak
            import pandas as pd

            # 获取当前日期
            today = datetime.now().date()
            if today.weekday() >= 5:  # 周末
                days_back = today.weekday() - 4
                current_date = today - timedelta(days=days_back)
            else:
                current_date = today
            
            # 加载交易日历（与分时图保持一致）
            trade_calendar = self._load_trade_calendar()
            
            # 获取前1个交易日的数据，确保有足够的历史数据（1个交易日有48个5分钟K线，足够布林带计算）
            if trade_calendar:
                # 使用交易日历来获取真正的前一交易日
                sorted_dates = sorted(list(trade_calendar))
                current_idx = sorted_dates.index(current_date) if current_date in sorted_dates else -1
                if current_idx >= 1:
                    prev_date = sorted_dates[current_idx - 1]
                else:
                    # 如果找不到当前日期或当前日期是第一个，则使用简单方法
                    prev_date = current_date - timedelta(days=1)
                    while prev_date.weekday() >= 5:  # 跳过周末
                        prev_date -= timedelta(days=1)
            else:
                # 如果没有交易日历，使用简单方法
                prev_date = current_date - timedelta(days=1)
                while prev_date.weekday() >= 5:  # 跳过周末
                    prev_date -= timedelta(days=1)
            
            prev_date_str = prev_date.strftime("%Y-%m-%d")
            print(f"[DEBUG] 尝试获取前1个交易日 {prev_date_str} 的1分钟数据")
            
            try:
                # 获取前一交易日的1分钟数据（与分时图保持一致）
                prev_1min_data = ak.stock_zh_a_hist_min_em(
                    symbol=symbol,
                    start_date=f"{prev_date_str} 09:30:00",
                    end_date=f"{prev_date_str} 15:00:00",
                    period="1",
                    adjust="qfq"
                )
                
                if not prev_1min_data.empty:
                    # 转换列名为英文
                    if '收盘' in prev_1min_data.columns:
                        prev_1min_data['close'] = prev_1min_data['收盘']
                    if '开盘' in prev_1min_data.columns:
                        prev_1min_data['open'] = prev_1min_data['开盘']
                    if '最高' in prev_1min_data.columns:
                        prev_1min_data['high'] = prev_1min_data['最高']
                    if '最低' in prev_1min_data.columns:
                        prev_1min_data['low'] = prev_1min_data['最低']
                    if '成交量' in prev_1min_data.columns:
                        prev_1min_data['volume'] = prev_1min_data['成交量']
                    
                    # 设置时间索引
                    if '时间' in prev_1min_data.columns:
                        prev_1min_data['时间'] = pd.to_datetime(prev_1min_data['时间'])
                        prev_1min_data = prev_1min_data.set_index('时间').sort_index()
                    
                    # 转换为5分钟K线数据（与分时图保持一致）
                    prev_5min_data = prev_1min_data.resample('5T', offset='1T').agg({
                        'open': 'first',
                        'close': 'last',
                        'high': 'max',
                        'low': 'min',
                        'volume': 'sum'
                    }).dropna()
                    
                    if not prev_5min_data.empty:
                        print(f"[DEBUG] 成功获取前1个交易日 {prev_date_str} 的5分钟数据，共 {len(prev_5min_data)} 条记录")
                        return prev_5min_data
                    else:
                        print(f"[DEBUG] 前1个交易日 {prev_date_str} 转换5分钟数据后为空")
                else:
                    print(f"[DEBUG] 前1个交易日 {prev_date_str} 没有1分钟数据")
                    
            except Exception as e:
                print(f"[DEBUG] 获取前1个交易日 {prev_date_str} 数据失败: {e}")
            
            print(f"[DEBUG] 无法获取历史5分钟数据 {symbol}")
            return None
                
        except Exception as e:
            print(f"[DEBUG] 获取历史5分钟数据失败 {symbol}: {e}")
            return None

    def calculate_trend_gains(self, symbol: str) -> tuple:
        """计算股票的趋势涨幅、MA5偏离度和股价成本涨幅
        
        Args:
            symbol: 股票代码
            
        Returns:
            tuple: (日趋势涨幅, 周趋势涨幅, 月趋势涨幅, MA5偏离度, 次日板MA5偏离度, 日内趋势, 股价成本涨幅)
        """
        # 首先检查缓存
        cached_data = self.get_cached_trend_data(symbol)
        if cached_data is not None:
            print(f"使用缓存数据: {symbol}")
            # 检查缓存数据是否包含新的字段
            if len(cached_data) == 5:
                # 旧版本缓存，添加默认值
                cached_data = cached_data + ('-',)
            if len(cached_data) == 6:
                # 缺少日内趋势字段，添加默认值
                cached_data = cached_data + ('-',)
            if len(cached_data) == 7:
                # 包含所有字段，直接返回
                return cached_data
            # 如果字段数量不是7，添加缺失的字段
            while len(cached_data) < 7:
                cached_data = cached_data + ('-',)
            return cached_data
        
        # API调用限制和重试机制
        max_retries = self.api_config['max_retries']
        retry_delay = self.api_config['retry_delay']
        
        for attempt in range(max_retries):
            try:
                from datetime import datetime, timedelta

                import akshare as ak
                import pandas as pd
                from src.stock_kline_window import ETFKLineWindow
                from src.trading_utils import calculate_consecutive_trend_gain

                # 添加请求间延迟，避免API频繁调用
                if attempt > 0:
                    time.sleep(retry_delay * attempt)
                
                # 获取股票历史数据
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y%m%d')
                
                df = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date, end_date=end_date, adjust='qfq')
                
                if df.empty:
                    print(f"获取股票数据失败，数据为空: {symbol}")
                    return ('error', 'error', 'error', 'error', 'error', 'error', 'error')
                
                # 确保日期列为索引且按时间升序排列
                if '日期' in df.columns:
                    df['日期'] = pd.to_datetime(df['日期'])
                    df = df.set_index('日期').sort_index()
                
                # 直接使用trading_utils中的函数计算连阳连阴，避免在后台线程中创建Tkinter组件
                # 使用静态方法或直接调用计算函数，避免创建窗口实例
                
                # 计算各周期的连阳连阴 - 直接调用静态方法
                day_up, day_down, prev_day_up, prev_day_down = self._calculate_consecutive_days_static(df, 'day')
                week_up, week_down, prev_week_up, prev_week_down = self._calculate_consecutive_days_static(df, 'week')
                month_up, month_down, prev_month_up, prev_month_down = self._calculate_consecutive_days_static(df, 'month')
                
                # 计算趋势涨幅
                day_trend = self._get_trend_gain_static(df, 'day', day_up, prev_day_up)
                week_trend = self._get_trend_gain_static(df, 'week', week_up, prev_week_up)
                month_trend = self._get_trend_gain_static(df, 'month', month_up, prev_month_up)
                print(f"[DEBUG] {symbol} 趋势计算结果: 日={day_trend}, 周={week_trend}, 月={month_trend}, 连阳天数: 日={day_up}, 周={week_up}, 月={month_up}")
                
                # 计算MA5偏离度
                from trading_utils import (
                    calculate_ma5_deviation,
                    calculate_next_day_limit_up_ma5_deviation)
                ma5_deviation = calculate_ma5_deviation(symbol)
                print(f"[DEBUG] {symbol} MA5偏离度计算结果: {ma5_deviation}")
                
                # 计算次日板MA5偏离度
                next_day_limit_up_ma5_deviation = calculate_next_day_limit_up_ma5_deviation(symbol)
                print(f"[DEBUG] {symbol} 次日板MA5偏离度计算结果: {next_day_limit_up_ma5_deviation}")
                
                # 计算日内趋势
                intraday_trend = self.calculate_intraday_trend(symbol)
                print(f"[DEBUG] {symbol} 日内趋势计算结果: {intraday_trend}")
                
                # 保存到缓存
                # 计算股价成本涨幅
                cost_change = self.calculate_cost_change(symbol)
                
                self.save_trend_data(symbol, day_trend, week_trend, month_trend, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, cost_change)
                
                return (day_trend, week_trend, month_trend, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, cost_change)
                
            except Exception as e:
                print(f"计算趋势涨幅失败 {symbol} (尝试 {attempt + 1}/{max_retries}): {e}")
                
                # 如果是连接错误，进行重试
                if "Connection aborted" in str(e) or "RemoteDisconnected" in str(e):
                    if attempt < max_retries - 1:
                        print(f"连接错误，{retry_delay * (attempt + 1)}秒后重试...")
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    else:
                        print(f"重试次数用尽，返回错误: {symbol}")
                        return ('error', 'error', 'error', 'error', 'error', 'error', 'error')
                else:
                    # 其他错误直接返回
                    return ('error', 'error', 'error', 'error', 'error', 'error', 'error')
        
        # 如果所有重试都失败
        print(f"所有重试都失败: {symbol}")
        return ('error', 'error', 'error', 'error', 'error', 'error', 'error')
    
    def _get_trend_gain(self, data, period: str, current_up: int, prev_up: int, window) -> str:
        """获取趋势涨幅字符串
        
        Args:
            data: 股票数据
            period: 周期类型
            current_up: 当前连阳天数
            prev_up: 上一个连阳天数
            window: ETFKLineWindow实例
            
        Returns:
            str: 趋势涨幅字符串，如"+5.2%"或"-"
        """
        try:
            from src.trading_utils import calculate_consecutive_trend_gain
            # 使用统一配置获取最小连阳天数要求
            from trend_config import get_min_consecutive_days
            min_consecutive_days = get_min_consecutive_days(period)
            
            # 检查当前趋势是否有足够连阳
            if current_up >= min_consecutive_days:
                gain_pct, current_price, target_price = calculate_consecutive_trend_gain(data, period)
                if gain_pct != 0:
                    return f"{gain_pct:+.1f}%"
            # 检查上一个趋势是否有足够连阳
            elif prev_up >= min_consecutive_days:
                gain_pct, current_price, target_price = window._calculate_previous_trend_gain(data, period, prev_up)
                if gain_pct != 0:
                    return f"{gain_pct:+.1f}%"
            
            return '-'
            
        except Exception as e:
            print(f"获取{period}趋势涨幅失败: {e}")
            return '-'

    def _calculate_consecutive_days_static(self, data, period):
        """静态方法：计算连阳连阴天数，不依赖Tkinter组件"""
        try:
            import pandas as pd

            # 根据周期重采样数据
            if period == 'day':
                period_data = data.copy()
            elif period == 'week':
                period_data = data.resample('W').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            elif period == 'month':
                period_data = data.resample('M').agg({
                    '开盘': 'first',
                    '最高': 'max',
                    '最低': 'min',
                    '收盘': 'last',
                    '成交量': 'sum'
                }).dropna()
            else:
                return (0, 0, 0, 0)
            
            if period_data.empty or len(period_data) < 2:
                return (0, 0, 0, 0)
            
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
            
            # 计算上一个趋势的连阳连阴天数
            prev_consecutive_up = 0
            prev_consecutive_down = 0
            
            # 从当前趋势结束位置开始向前计算
            start_pos = len(period_data) - current_consecutive_up - current_consecutive_down
            for i in range(start_pos - 1, -1, -1):
                if is_up.iloc[i]:  # 上涨
                    if prev_consecutive_down > 0:  # 如果之前是连阴，则重置
                        break
                    prev_consecutive_up += 1
                else:  # 下跌或平盘，统一算作阴线
                    if prev_consecutive_up > 0:  # 如果之前是连阳，则重置
                        break
                    prev_consecutive_down += 1
            
            return (current_consecutive_up, current_consecutive_down, prev_consecutive_up, prev_consecutive_down)
            
        except Exception as e:
            print(f"计算连阳连阴天数失败: {e}")
            return (0, 0, 0, 0)
    
    def _get_consecutive_down_days(self, data, period):
        """获取连阴天数"""
        try:
            current_up, current_down, prev_up, prev_down = self._calculate_consecutive_days_static(data, period)
            return current_down, prev_down
        except Exception as e:
            print(f"获取连阴天数失败: {e}")
            return (0, 0)
    
    def _get_trend_gain_static(self, data, period, current_up, prev_up):
        """静态方法：获取趋势涨幅字符串，不依赖Tkinter组件"""
        try:
            from src.trading_utils import calculate_consecutive_trend_gain
            # 使用统一配置获取最小连阳天数要求
            from trend_config import get_min_consecutive_days
            min_consecutive_days = get_min_consecutive_days(period)
            
            # 检查当前趋势是否有足够连阳
            if current_up >= min_consecutive_days:
                gain_pct, current_price, target_price = calculate_consecutive_trend_gain(data, period)
                if gain_pct != 0:
                    return f"{gain_pct:+.1f}%"
            # 检查上一个趋势是否有足够连阳
            elif prev_up >= min_consecutive_days:
                # 计算上一个趋势的趋势价格和涨幅
                gain_pct, current_price, target_price = self._calculate_previous_trend_gain_static(data, period, prev_up)
                if gain_pct != 0:
                    return f"{gain_pct:+.1f}%"
            
            # 改进：显示连阳或连阴天数，而不是'-'
            if current_up > 0:
                return f"{current_up}连阳"
            elif prev_up > 0:
                return f"上{prev_up}连阳"
            else:
                # 检查是否有连阴情况
                current_down, prev_down = self._get_consecutive_down_days(data, period)
                if current_down > 0:
                    return f"{current_down}连阴"
                elif prev_down > 0:
                    return f"上{prev_down}连阴"
                else:
                    return "无连阳"
            
        except Exception as e:
            print(f"获取{period}趋势涨幅失败: {e}")
            return 'error'
    
    def _calculate_previous_trend_gain_static(self, data, period, prev_consecutive_up):
        """静态方法：计算上一个趋势的趋势价格和涨幅，不依赖Tkinter组件"""
        try:
            import pandas as pd
            # 使用统一配置获取最小连阳天数要求
            from trend_config import get_min_consecutive_days
            min_consecutive_days = get_min_consecutive_days(period)
            
            if data is None or data.empty or prev_consecutive_up < min_consecutive_days:
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
                current_close = float(period_data.iloc[i]['收盘'])
                prev_close = float(period_data.iloc[i-1]['收盘'])
                
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
            
            # 计算上一个趋势的N连阳涨幅
            # 取上一个趋势中最早的N个连阳周期
            trend_data = []
            for i in range(prev_trend_start, prev_trend_end):
                if is_up.iloc[i]:
                    trend_data.append({
                        'index': i,
                        '开盘': float(period_data['开盘'].iloc[i]),
                        '收盘': float(period_data['收盘'].iloc[i]),
                        '日期': period_data.index[i]
                    })
            
            if len(trend_data) < min_consecutive_days:
                return (0.0, 0.0, 0.0)
            
            # 取最早的N个连阳周期
            consecutive_data = trend_data[-min_consecutive_days:]
            
            # 计算N连阳涨幅
            start_low = min(consecutive_data[0]['开盘'], consecutive_data[0]['收盘'])
            end_high = max(consecutive_data[-1]['开盘'], consecutive_data[-1]['收盘'])
            trend_gain = end_high - start_low
            
            # 当前周期收盘价，确保为数值类型
            current_price = float(period_data['收盘'].iloc[-1])
            
            # 趋势目标价格 = 第N个连阳周期收盘价 + N连阳涨幅
            last_consecutive_close = float(consecutive_data[-1]['收盘'])
            target_price = last_consecutive_close + trend_gain
            
            # 涨幅计算：目标价格相对于当前价格的涨幅百分比
            if current_price > 0:
                trend_gain_pct = ((target_price - current_price) / current_price) * 100
            else:
                trend_gain_pct = 0.0
            
            return (trend_gain_pct, current_price, target_price)
            
        except Exception as e:
            print(f"计算上一个{period}线连阳涨幅失败: {e}")
            return (0.0, 0.0, 0.0)

    def update_info_columns(self):
        """更新信息列和信号列（内部方法）"""
        for item in self.tree.get_children():
            values = self.tree.item(item)["values"]
            # 确保代码是6位格式，处理龙虎榜的#前缀
            raw_code = str(values[1])
            if raw_code.startswith('#'):
                # 龙虎榜股票代码，去掉#前缀
                symbol = raw_code[1:]
            elif '.' in raw_code:
                symbol = raw_code.split('.')[0]
            else:
                symbol = raw_code
            symbol = symbol.zfill(6)
            
            # 创建分析引擎实例
            analysis_engine = ETFAnalysisEngine()
            
            # 获取最新的条件触发信息
            conditions = [
                # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                CostAndConcentrationCondition(),
                CostCrossMaCondition(),
                CostPriceCompareCondition(),
                CostCrossPriceBodyCondition()
            ]
            trigger_info = analysis_engine.get_latest_condition_trigger(symbol, conditions)
            message = trigger_info['message'] if trigger_info else ''
            level = trigger_info.get('level', '') if trigger_info else ''
            
            # 更新消息列和信号等级列 (按新列顺序)
            new_values = list(values)
            while len(new_values) < 8:
                new_values.append('')
            new_values[6] = message  # 消息列
            new_values[7] = level   # 信号等级列
            self.tree.item(item, values=new_values)
            
            # 根据信号等级设置行颜色
            if level:
                if level == SignalLevel.BUY.value:
                    self.tree.item(item, tags=('buy',))
                elif level == SignalLevel.BULLISH.value:
                    self.tree.item(item, tags=('bullish',))
                elif level == SignalLevel.SELL.value:
                    self.tree.item(item, tags=('sell',))
                elif level == SignalLevel.BEARISH.value:
                    self.tree.item(item, tags=('bearish',))
    
    def create_new_list(self):
        """创建新的自选列表"""
        name = tk.simpledialog.askstring(l("new_list"), l("enter_list_name"))
        if name:
            if name in self.watchlists:
                messagebox.showerror(l("error"), l("list_already_exists"))
                return
            
            self.watchlists[name] = []
            self.current_list = name
            self.list_var.set(name)
            self.list_combo['values'] = list(self.watchlists.keys())
            self.save_watchlists()
            self.load_list_data()
    
    def delete_current_list(self):
        """删除当前自选列表"""
        if self.current_list == "默认":
            messagebox.showerror(l("error"), l("cannot_delete_default_list"))
            return
        
        if messagebox.askyesno(l("confirm"), l("confirm_delete_list")):
            del self.watchlists[self.current_list]
            self.current_list = "默认"
            self.list_var.set("默认")
            self.list_combo['values'] = list(self.watchlists.keys())
            self.save_watchlists()
            self.load_list_data()
    
    def on_list_changed(self, event):
        """列表切换处理"""
        new_list = self.list_var.get()
        if new_list == self.current_list:
            return
            
        self.current_list = new_list
        
        # 处理信号列表
        if new_list in ("买入信号", "卖出信号", "超跌", "退市", "龙虎榜"):
            if new_list == "龙虎榜":
                self.load_lhb_data()
            else:
                self.load_signal_stocks(new_list)
        elif new_list == "板块":
            # 板块列表特殊处理
            self.load_board_data()
        elif new_list == "ETF":
            # ETF列表特殊处理
            self.load_etf_data()
        else:
            # 原有列表处理逻辑
            self.save_watchlists()
            if self.current_list not in self.list_cache:
                self.load_list_data()
            else:
                self.load_from_cache()

    def load_from_cache(self):
        """从缓存加载数据到表格"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # 从缓存加载数据
        cached_items = self.list_cache.get(self.current_list, [])
        self.original_items = cached_items.copy()
        
        # 显示数据
        for item in cached_items:
            self.tree.insert("", tk.END, values=item)
            
        # 如果有排序设置，应用排序
        if self.last_sort_column:
            self.sort_treeview(self.last_sort_column)

    def show_selected_klines(self):
        """显示选中股票的K线图"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(l("info"), l("please_select_symbols"))
            return
            
        # 检查选中数量是否超过限制
        max_symbols = self.grid_rows * self.grid_cols
        if len(selected) > max_symbols:
            messagebox.showwarning(l("warning"), l("too_many_symbols_selected").format(max_symbols))
            return
            
        # 获取屏幕尺寸
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 计算每个窗口的大小
        window_width = screen_width // self.grid_cols
        window_height = screen_height // self.grid_rows
        
        # 创建并排列K线图窗口
        for i, item in enumerate(selected):
            values = self.tree.item(item)["values"]
            symbol = str(values[1]).zfill(6)  # 确保股票代码始终是6位，不足补零
            symbol_name = str(values[0])
            
            # 计算窗口位置
            row = i // self.grid_cols  # 修改为按列数计算行
            col = i % self.grid_cols   # 修改为按列数取余
            x = col * window_width
            y = row * window_height
            
            # 创建K线窗口
            kline_window = ETFKLineWindow(self.window)
            kline_window.show(symbol, symbol_name)
            
            # 设置窗口大小和位置
            kline_window.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def on_grid_size_changed(self, event):
        """处理网格大小变化"""
        self.grid_rows = int(self.grid_rows_var.get())
        self.grid_cols = int(self.grid_cols_var.get())
        
        # 更新表格选择限制
        max_symbols = self.grid_rows * self.grid_cols
        current_selected = len(self.tree.selection())
        
        if current_selected > max_symbols:
            # 取消多余的选择
            for item in self.tree.selection()[max_symbols:]:
                self.tree.selection_remove(item)
            messagebox.showinfo(l("info"), l("selection_adjusted").format(max_symbols))

    def open_kline_for_selected(self):
        selected_items = self.tree.selection()
        for item in selected_items:
            code = str(self.tree.item(item)['values'][0])
            name = self.tree.item(item)['values'][1]
            kline_window = ETFKLineWindow(self.window)  # 修正构造函数调用
            kline_window.show(code, name)

    def classify_selected(self):
        """分类选中的股票"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo(l("info"), l("please_select_symbols"))
            return
        
        # 创建分类对话框
        classify_window = tk.Toplevel(self.window)
        classify_window.title(l("classify_symbols"))
        classify_window.geometry("300x400")
        
        # 创建列表选择框
        list_frame = ttk.Frame(classify_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        ttk.Label(list_frame, text=l("select_lists")).pack(anchor=tk.W)
        
        # 创建复选框变量和控件
        checkboxes = {}
        for list_name in self.watchlists.keys():
            # 排除"板块"列表
            if list_name == "板块":
                continue
            var = tk.BooleanVar()
            checkboxes[list_name] = var
            ttk.Checkbutton(list_frame, text=list_name, variable=var).pack(anchor=tk.W)
        
        def apply_classification():
            """应用分类设置"""
            selected_lists = [name for name, var in checkboxes.items() if var.get()]
            if not selected_lists:
                messagebox.showwarning(l("warning"), l("please_select_at_least_one_list"))
                return
            
            # 更新选中股票的分类
            for item in selected:
                values = self.tree.item(item)["values"]
                # 确保代码是字符串类型并格式化为6位
                raw_code = str(values[1]).strip()
                # 处理龙虎榜的#前缀和点号
                if raw_code.startswith('#'):
                    # 龙虎榜股票代码，去掉#前缀
                    symbol = raw_code[1:]
                elif '.' in raw_code:
                    # 如果代码包含点号（如000006.SZ），取点号前的部分
                    symbol = raw_code.split('.')[0]
                else:
                    symbol = raw_code
                # 确保代码是6位格式
                symbol = symbol.zfill(6)
                # 确保名称有效
                name = values[0] if values[0] and values[0] != '--' else self.get_symbol_name(symbol)
                
                # 验证证券代码有效性
                if not self.validate_symbol_code(symbol):
                    print(f"无效的证券代码: {symbol}")
                    continue
                
                # 更新symbols数据
                if symbol not in self.symbols:
                    self.symbols[symbol] = {
                        "name": name,
                        "lists": selected_lists.copy()  # 使用副本避免引用问题
                    }
                else:
                    # 先清除原有分类
                    for old_list in self.symbols[symbol]["lists"]:
                        if old_list in self.watchlists and symbol in self.watchlists[old_list]:
                            self.watchlists[old_list].remove(symbol)
                    # 添加新分类
                    self.symbols[symbol]["lists"] = selected_lists.copy()
                
                # 更新watchlists数据
                for list_name in selected_lists:
                    # 确保列表存在
                    if list_name not in self.watchlists:
                        self.watchlists[list_name] = []
                    # 避免重复添加
                    if symbol not in self.watchlists[list_name]:
                        self.watchlists[list_name].append(symbol)
            
            # 保存更新
            self.save_watchlists()
            # 刷新显示
            self.load_list_data()
            # 关闭窗口
            classify_window.destroy()
        
        # 添加按钮
        btn_frame = ttk.Frame(classify_window)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text=l("apply"), command=apply_classification).pack(side=tk.RIGHT)

    def validate_symbol_code(self, code: str) -> bool:
        """验证证券代码格式"""
        # 基本格式检查：6位数字或BK开头的概念板块代码
        if len(code) not in (6, 7) or (not code.startswith('BK') and not code.isdigit()):
            return False
        return True

    def get_symbol_name(self, code: str) -> str:
        """根据代码获取证券名称"""
        try:
            # 优先从缓存获取
            if code in self.symbols:
                return self.symbols[code].get('name', '--')
            # 实时查询
            name, _ = get_symbol_info(code)
            return name if name else '--'
        except Exception as e:
            print(f"获取证券名称失败: {str(e)}")
            return '--'

    def load_board_data(self):
        """加载板块数据"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 清空原始数据
        self.original_items = []
     
        # 设置加载标志
        self.loading_boards = True
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在加载板块数据... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                # 检查是否需要继续更新
                if not self.loading_boards:
                    progress_label.destroy()
                    return
                percent = int((current / total) * 100)
                progress_label["text"] = f"正在加载板块数据... {percent}%"
            self.window.after(0, _update)
        
        def update_tree_item(name, code, price, change):
            """更新表格项"""
            def _update():
                # 检查是否需要继续更新
                if not self.loading_boards:
                    return
                # 板块数据需要补齐到8个字段
                item_values = (name, code, '', change, '-', '', '', '', '', '--', '--', '', '')
                self.tree.insert("", tk.END, values=item_values)
                self.original_items.append(item_values)
            self.window.after(0, _update)
        
        def fetch_data():
            """获取板块数据的线程函数"""
            try:
                # 获取所有板块
                boards = ak.stock_board_concept_name_em()
                total = len(boards)
                
                today = datetime.now().strftime("%Y%m%d")
                
                for i, (_, board) in enumerate(boards.iterrows(), 1):
                    # 检查是否需要继续加载
                    if not self.loading_boards:
                        return
                    
                    try:
                        name = board['板块名称']
                        
                        hist_data = ak.stock_board_concept_hist_em(
                            symbol=name,
                            period="daily",
                            start_date=today,
                            end_date=today,
                            adjust=""
                        )
                        
                        if not hist_data.empty:
                            price = hist_data.iloc[-1]['收盘']
                            change = hist_data.iloc[-1]['涨跌幅']
                            code = board['板块代码']
                        else:
                            price = '--'
                            change = '--'
                            code = board['板块代码']
                        
                        update_tree_item(name, code, price, change)
                        update_progress(i, total)
                        
                    except Exception as board_error:
                        print(f"Error loading data for board {name}: {board_error}")
                        update_tree_item(name, code, "加载失败", "--")
                
                def cleanup():
                    # 检查是否需要继续更新
                    if not self.loading_boards:
                        return
                    progress_label.destroy()
                    self.list_cache[self.current_list] = self.original_items.copy()
                    if self.last_sort_column:
                        self.sort_treeview(self.last_sort_column)
                    # 更新统计信息
                    self.update_statistics()
                    # 重置加载标志
                    self.loading_boards = False
                
                self.window.after(0, cleanup)
                
            except Exception as error:
                def show_error(err):
                    if self.loading_boards:  # 只在仍在加载时显示错误
                        messagebox.showerror("错误", f"加载板块数据失败: {str(err)}")
                        progress_label.destroy()
                        self.update_statistics()  # 即使出错也更新统计信息
                    self.loading_boards = False
                self.window.after(0, lambda err=error: show_error(err))
        
      
        threading.Thread(target=fetch_data, daemon=True).start()

    def load_etf_data(self):
        """加载ETF数据"""
        # 确保窗口已经创建
        if self.window is None:
            self.create_window()
            self.setup_window()
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 清空原始数据
        self.original_items = []
        
        # 设置加载标志
        self.loading_etf = True
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在加载ETF数据... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                # 检查是否需要继续更新
                if not self.loading_etf:
                    progress_label.destroy()
                    return
                percent = int((current / total) * 100)
                progress_label["text"] = f"正在加载ETF数据... {percent}%"
            
            # 使用线程安全的方式更新UI
            try:
                self.window.after(0, _update)
            except:
                # 如果after调用失败，直接更新（在调试环境中）
                _update()
        
        def update_tree_item(name, code, price, change):
            """更新表格项"""
            def _update():
                # 检查是否需要继续更新
                if not self.loading_etf:
                    return
                
                try:
                    # ETF数据需要补齐到11个字段
                    item_values = (name, code, '', change, '-', '', '', '', '', '--', '--', '', '')
                    
                    # 添加到original_items
                    self.original_items.append(item_values)
                    
                    # 插入到tree
                    self.tree.insert("", tk.END, values=item_values)
                        
                except Exception as e:
                    print(f"Error adding ETF {code}: {e}")
                    # 即使tree.insert失败，也要添加到original_items
                    try:
                        item_values = (name, code, '', change, '-', '', '', '', '', '--', '--', '', '')
                        self.original_items.append(item_values)
                    except:
                        pass
            
            # 使用线程安全的方式更新UI
            try:
                self.window.after(0, _update)
            except:
                # 如果after调用失败，直接更新（在调试环境中）
                _update()
        
        def fetch_data():
            """获取ETF数据的线程函数"""
            try:
                # 使用优化的ETF列表缓存获取数据
                from etf_list_cache import get_etf_list_cache
                etf_cache = get_etf_list_cache()
                etf_list, etf_159 = etf_cache.get_etf_list_optimized()
                
                total = len(etf_159)
                
                print(f"找到{total}个159开头的ETF")
                
                for i, (_, etf) in enumerate(etf_159.iterrows(), 1):
                    # 检查是否需要继续加载
                    if not self.loading_etf:
                        return
                    
                    try:
                        name = etf['名称']
                        code = etf['代码']
                        
                        # 从趋势缓存中获取价格数据，如果没有则显示默认值
                        cached_data = self.get_cached_trend_data(code)
                        if cached_data and cached_data[3] != '-':  # MA5偏离度列有数据
                            # 从MA5偏离度反推价格变化（这里简化处理）
                            price = '--'  # ETF价格不直接显示
                            change = '--'  # 涨跌幅由趋势列显示
                        else:
                            price = '--'
                            change = '--'
                        
                        update_tree_item(name, code, price, change)
                        update_progress(i, total)
                        
                    except Exception as etf_error:
                        print(f"Error loading data for ETF {code}: {etf_error}")
                        update_tree_item(name, code, "加载失败", "--")
                
                def cleanup():
                    # 检查是否需要继续更新
                    if not self.loading_etf:
                        return
                    progress_label.destroy()
                    self.list_cache[self.current_list] = self.original_items.copy()
                    if self.last_sort_column:
                        self.sort_treeview(self.last_sort_column)
                    # 更新统计信息
                    self.update_statistics()
                    # 重置加载标志
                    self.loading_etf = False
                
                # 使用线程安全的方式更新UI
                try:
                    self.window.after(0, cleanup)
                except:
                    # 如果after调用失败，直接执行（在调试环境中）
                    cleanup()
                
            except Exception as error:
                def show_error(err):
                    if self.loading_etf:  # 只在仍在加载时显示错误
                        messagebox.showerror("错误", f"加载ETF数据失败: {str(err)}")
                        progress_label.destroy()
                        self.update_statistics()  # 即使出错也更新统计信息
                    self.loading_etf = False
                
                # 使用线程安全的方式更新UI
                try:
                    self.window.after(0, lambda err=error: show_error(err))
                except:
                    # 如果after调用失败，直接执行（在调试环境中）
                    show_error(error)
        
        # 启动数据获取线程
        threading.Thread(target=fetch_data, daemon=True).start()

    def get_watchlist_names(self):
        """获取所有列表名称，包括信号列表"""
        # 获取基本列表
        names = list(self.watchlists.keys())
        
        # 确保必要的列表都存在
        required_lists = ["默认", "板块", "ETF", "买入信号", "卖出信号", "超跌", "龙虎榜"]
        for list_name in required_lists:
            if list_name not in names:
                names.append(list_name)
                # 同时确保watchlists中有对应的空列表
                if list_name not in self.watchlists:
                    self.watchlists[list_name] = []
        
        return names

    def sort_treeview(self, col):
        """表格排序处理"""
        # 获取所有项目
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]
        
        # 如果是同一列，反转排序方向
        if self.last_sort_column == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
            self.last_sort_column = col
        
        # 根据列类型进行排序
        if col == "industry":
            # 按行业分组并计算平均涨幅
            industry_groups = {}
            for _, item in items:
                values = self.tree.item(item)["values"]
                industry = values[2]  # 行业列
                change_str = str(values[3]).replace('%', '')  # 涨跌幅列
                
                try:
                    change = float(change_str)
                    if industry not in industry_groups:
                        industry_groups[industry] = {
                            'items': [],
                            'changes': []
                        }
                    industry_groups[industry]['items'].append(item)
                    industry_groups[industry]['changes'].append(change)
                except (ValueError, TypeError):
                    # 处理无效的涨跌幅数据
                    if industry not in industry_groups:
                        industry_groups[industry] = {
                            'items': [],
                            'changes': []
                        }
                    industry_groups[industry]['items'].append(item)
            
            # 计算每个行业的平均涨幅
            industry_avg_changes = {}
            for industry, data in industry_groups.items():
                if data['changes']:
                    avg_change = sum(data['changes']) / len(data['changes'])
                    industry_avg_changes[industry] = avg_change
                else:
                    industry_avg_changes[industry] = float('-inf')
            
            # 按平均涨幅对行业进行排序
            sorted_industries = sorted(
                industry_groups.keys(),
                key=lambda x: industry_avg_changes[x],
                reverse=self.sort_reverse
            )
            
            # 重新排列项目
            index = 0
            for industry in sorted_industries:
                for item in industry_groups[industry]['items']:
                    self.tree.move(item, '', index)
                    index += 1
                
        elif col == "change":
            # 数值排序
            def convert_to_float(x):
                try:
                    return float(x[0].replace('%', ''))
                except (ValueError, TypeError):
                    return float('-inf')  # 无效值放到最后
            items.sort(key=convert_to_float, reverse=self.sort_reverse)
            
            # 重新排列项目
            for index, (_, item) in enumerate(items):
                self.tree.move(item, '', index)
                
        elif col in ["day_trend", "week_trend", "month_trend", "ma5_deviation", "next_day_limit_up_ma5_deviation", "intraday_trend", "cost_change"]:
            # 趋势列和MA5偏离度列混合排序（数字按数值排序，字符串按字符排序）
            def convert_trend_to_sort_key(x):
                try:
                    value = x[0].strip()
                    
                    # 处理空值或无效值
                    if not value or value == '-' or value == '':
                        # 无效值始终放到最后，无论升序还是降序
                        return (2, float('-inf'), '')  # 无效值放到最后
                    
                    # 检查是否为百分比数值（如 +2.5%, -1.8%）
                    if '%' in value:
                        try:
                            num_value = float(value.replace('%', '').replace('+', ''))
                            # 数字类型：降序时给负优先级确保排在最前面
                            return (0, num_value, '')  # 数字类型，按数值排序
                        except (ValueError, TypeError):
                            return (2, float('-inf'), value)  # 转换失败，按字符串排序
                    
                    # 检查是否为纯数字（如 2.5, -1.8）
                    try:
                        num_value = float(value.replace('+', ''))
                        # 数字类型：降序时给负优先级确保排在最前面
                        return (0, num_value, '')  # 数字类型，按数值排序
                    except (ValueError, TypeError):
                        pass
                    
                    # 字符串类型（如 "3连阳", "无连阳", "上2连阳"）
                    # 字符串类型：降序时给正优先级确保排在数字后面
                    return (1, 0, value)  # 字符串类型，按字符排序
                    
                except Exception:
                    return (2, float('-inf'), str(x[0]))  # 异常情况，放到最后
            
            # 修正排序逻辑：确保降序时数字优先，升序时数字也优先
            # 排序键：(类型优先级, 数值, 字符串)
            # 类型优先级：0=数字(最高), 1=字符串(中等), 2=无效(最低)
            # 关键：使用自定义排序函数，而不是简单的reverse参数
            def custom_sort_key(item):
                key = convert_trend_to_sort_key(item)
                # 降序时：数字类型获得最高优先级，字符串次之，无效值最后
                # 升序时：同样保持数字优先
                if self.sort_reverse:
                    # 降序：数字类型优先级最高(0)，字符串次之(1)，无效最后(2)
                    return (key[0], -key[1] if key[1] != float('-inf') else float('inf'), key[2])
                else:
                    # 升序：数字类型优先级最高(0)，字符串次之(1)，无效最后(2)
                    return (key[0], key[1], key[2])
            
            items.sort(key=custom_sort_key)
            
            # 重新排列项目
            for index, (_, item) in enumerate(items):
                self.tree.move(item, '', index)
            
        elif col == "message":
            # 消息按内容排序
            def message_sort_key(x):
                return x[0]  # 只按内容排序
            items.sort(key=message_sort_key, reverse=self.sort_reverse)
            
            # 重新排列项目
            for index, (_, item) in enumerate(items):
                self.tree.move(item, '', index)
            
        else:
            # 字符串排序
            items.sort(reverse=self.sort_reverse)
            
            # 重新排列项目
            for index, (_, item) in enumerate(items):
                self.tree.move(item, '', index)
        
        # 更新表头显示排序方向
        # 定义所有表头的中文名称
        header_names = {
            "name": l("symbol_name"),
            "code": l("symbol_code"), 
            "industry": l("industry"),
            "change": l("price_change"),
            "cost_change": "股价成本涨幅",
            "ma5_deviation": "MA5偏离",
            "next_day_limit_up_ma5_deviation": "次日板MA5偏离",
            "day_trend": "日趋势",
            "week_trend": "周趋势", 
            "month_trend": "月趋势",
            "holders": l("holders_change"),
            "capita": l("capita_change"),
            "message": l("message"),
            "level": l("signal_level")
        }
        
        for header in ["name", "code", "industry", "change", "cost_change", "ma5_deviation", "day_trend", "week_trend", "month_trend", "holders", "capita", "message", "level"]:
            if header == col:
                header_text = header_names[header]
                self.tree.heading(header, text=f"{header_text} {'↓' if self.sort_reverse else '↑'}")
            else:
                header_text = header_names[header]
                self.tree.heading(header, text=header_text)
        
        # 更新统计信息
        self.update_statistics()

    def get_pinyin(self, text):
        """获取文本的拼音，支持首字母和全拼"""
        if not text:
            return [], []
            
        # 获取完整拼音
        full_pinyin = []
        for word in pypinyin.pinyin(text, style=pypinyin.NORMAL):
            full_pinyin.extend(word)
        
        # 获取拼音首字母
        first_letters = []
        for word in pypinyin.pinyin(text, style=pypinyin.FIRST_LETTER):
            first_letters.extend(word)
            
        return [''.join(full_pinyin), ''.join(first_letters)]

    def match_text(self, text, keywords):
        """检查文本是否匹配所有关键词（支持拼音和表头过滤）"""
        if not keywords:
            return True
        
        # 获取所有列名的映射
        column_map = {
            "name": 0,  # 名称列索引
            "code": 1,  # 代码列索引
            "change": 3, # 涨跌幅列索引
            "cost_change": 4, # 股价成本涨幅列索引
            "day_trend": 6, # 日趋势列索引
            "week_trend": 7, # 周趋势列索引
            "month_trend": 8, # 月趋势列索引
            "message": 11,# 消息列索引
            "level": 12, # 信号等级列索引
        }
        
        # 中文列名映射
        zh_column_map = {
            "名称": "name",
            "代码": "code",
            "涨跌幅": "change",
            "股价成本涨幅": "cost_change",
            "日趋势": "day_trend",
            "周趋势": "week_trend",
            "月趋势": "month_trend",
            "消息": "message",
            "信号": "level",
        }
        
        # 确保text是有效的数据项
        if not text or not isinstance(text, (list, tuple)):
            return False
        
        for keyword in keywords:
            matched = False
            
            # 检查是否是表头过滤格式
            if ":" in keyword:
                column, value = keyword.split(":", 1)
                column = column.lower().strip()
                value = value.lower().strip()
                
                # 处理中文列名
                if column in zh_column_map:
                    column = zh_column_map[column]
                
                # 如果指定了有效的列名
                if column in column_map:
                    col_idx = column_map[column]
                    # 确保索引有效
                    if col_idx < len(text):
                        item_value = str(text[col_idx]).lower()
                        item_pinyin = self.get_pinyin(item_value)
                        value_pinyin = self.get_pinyin(value)
                        
                        # 检查值是否匹配
                        if value in item_value:
                            matched = True
                        else:
                            for i_pinyin in item_pinyin:
                                for v_pinyin in value_pinyin:
                                    if isinstance(i_pinyin, str) and isinstance(v_pinyin, str):
                                        if v_pinyin in i_pinyin:
                                            matched = True
                                            break
                                if matched:
                                    break
                else:
                    # 如果列名无效，尝试在所有列中搜索
                    for col_idx in column_map.values():
                        if col_idx < len(text):
                            item_value = str(text[col_idx]).lower()
                            if value in item_value:
                                matched = True
                                break
            else:
                # 普通搜索模式
                keyword = keyword.lower()
                # 将item转换为字符串列表
                text_list = [str(x).lower() for x in text if x is not None]
                text_str = " ".join(text_list)
                
                if keyword in text_str:
                    matched = True
                else:
                    text_pinyin = self.get_pinyin(text_str)
                    keyword_pinyin = self.get_pinyin(keyword)
                    
                    for t_pinyin in text_pinyin:
                        for k_pinyin in keyword_pinyin:
                            if isinstance(t_pinyin, str) and isinstance(k_pinyin, str):
                                if k_pinyin in t_pinyin:
                                    matched = True
                                    break
                        if matched:
                            break
            
            if not matched:
                return False
                
        return True

    def filter_items(self, keywords):
        """根据关键词过滤列表项"""
        self.tree.delete(*self.tree.get_children())
        
        # 使用当前列表的数据进行过滤
        if self.current_list not in self.list_cache:
            # 如果缓存中没有当前列表的数据，使用原始数据
            self.list_cache[self.current_list] = self.original_items.copy()
        
        items_to_filter = self.list_cache[self.current_list]
        
        for item in items_to_filter:
            if self.match_text(item, keywords):
                values = item
                item_id = self.tree.insert("", tk.END, values=values)
                
                # 设置行颜色
                if len(values) > 4:  # 确保有足够的元素
                    level = values[4]
                    if level == SignalLevel.BUY.value:
                        self.tree.item(item_id, tags=('buy',))
                    elif level == SignalLevel.SELL.value:
                        self.tree.item(item_id, tags=('sell',))
        
        # 更新统计信息
        self.update_statistics()

    def on_search_changed(self, *args):
        """搜索框内容变化时的处理"""
        # 取消之前的延迟搜索
        if self.search_after_id:
            self.window.after_cancel(self.search_after_id)
        
        # 设置新的延迟搜索（300ms延迟）
        self.search_after_id = self.window.after(300, self.do_search)

    def do_search(self):
        """执行搜索"""
        search_text = self.search_var.get().strip()
        keywords = [k.strip() for k in search_text.split() if k.strip()]
        self.filter_items(keywords)

    def on_search_enter(self, event):
        """按下回车时的处理"""
        if self.current_list != "板块" and not self.tree.get_children():
            # 如果当前不是板块列表且过滤后没有记录，尝试添加新股票
            self.add_symbol(event)
        
    def load_list_data(self):
        """加载列表数据"""
        # 清空原始数据
        self.original_items = []
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 检查缓存是否需要更新(每60秒更新一次)
        trading_utils.update_market_data()     
                
        # 如果是板块列表，特殊处理
        if self.current_list == "板块":
            self.load_board_data()
            return
        
        # 如果是ETF列表，特殊处理
        if self.current_list == "ETF":
            self.load_etf_data()
            return
        
        # 其他列表的正常处理
        symbols = self.watchlists.get(self.current_list, [])
        
        # 创建进度显示标签
        progress_label = ttk.Label(self.window, text="正在加载数据... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                percent = int((current / total) * 100)
                progress_label["text"] = f"正在加载数据... {percent}%"
            self.window.after(0, _update)
        
        def update_tree_item(symbol, name, price, change):
            """更新表格项"""
            def _update():
                try:
                    # 获取行业信息
                    industry = self.get_stock_industry(symbol)
                    
                    # 获取股东/持股增幅
                    holders_change, capita_change = self.get_latest_holders_count(symbol)
                    
                    # 根据控制变量决定是否加载信息列内容
                    if self.show_info_columns:
                        # 创建分析引擎实例
                        analysis_engine = ETFAnalysisEngine()
                        # 获取条件触发信息
                        conditions = [
                            # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                            CostAndConcentrationCondition(),
                            CostCrossMaCondition(),
                            CostPriceCompareCondition(),
                            CostCrossPriceBodyCondition()
                        ]

                        trigger_info = analysis_engine.get_latest_condition_trigger(symbol, conditions)
                        message = trigger_info['message'] if trigger_info else ''
                        level = trigger_info.get('level', '') if trigger_info else ''
                    else:
                        # 默认情况下信息列和信号列留空
                        message = ''
                        level = ''
                    
                    # 根据控制变量决定是否加载趋势列内容
                    if self.show_trend_columns:
                        day_trend, week_trend, month_trend, ma5_deviation, cost_change = self.calculate_trend_gains(symbol)
                    else:
                        # 默认情况下趋势列留空
                        day_trend = ''
                        week_trend = ''
                        month_trend = ''
                        ma5_deviation = ''
                        cost_change = ''
                    
                    
                    item_values = (name, symbol, industry, change, cost_change, ma5_deviation, day_trend, week_trend, month_trend, holders_change, capita_change, message, level)
                    item = self.tree.insert("", tk.END, values=item_values)
                    self.original_items.append(item_values)
                    
                    # 根据信号等级设置行颜色
                    if level:
                        if level == SignalLevel.BUY.value:
                            self.tree.item(item, tags=('buy',))
                        elif level == SignalLevel.BULLISH.value:
                            self.tree.item(item, tags=('bullish',))
                        elif level == SignalLevel.SELL.value:
                            self.tree.item(item, tags=('sell',))
                        elif level == SignalLevel.BEARISH.value:
                            self.tree.item(item, tags=('bearish',))
                except Exception as e:
                    print(f"更新表格项时出错: {str(e)}")
                    # 发生错误时仍然添加项，但使用默认值
                    item_values = (name, symbol, '', '--', '-', '', '', '', '--', '--', '', '')  # 占位
                    item = self.tree.insert("", tk.END, values=item_values)
                    self.original_items.append(item_values)
                
            self.window.after(0, _update)
        
        def fetch_data():
            """获取数据的线程函数"""
            try:
                total = len(symbols)
                
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    futures = {}
                    
                    for symbol in symbols:
                        # 检查是否为板块代码
                        if str(symbol).startswith('BK'):
                            # 对于板块代码，使用不同的数据获取方法
                            futures[symbol] = (
                                executor.submit(lambda: (symbol, None)),  # 名称直接使用代码
                                executor.submit(self.get_board_quote, symbol)  # 获取板块行情
                            )
                        else:
                            # 普通股票代码使用原有方法
                            futures[symbol] = (
                                executor.submit(get_symbol_info, symbol),
                                executor.submit(get_realtime_quote, symbol)
                            )
                    
                    for i, symbol in enumerate(symbols, 1):
                        try:
                            info_future, quote_future = futures[symbol]
                            
                            if str(symbol).startswith('BK'):
                                # 处理板块数据
                                _, _ = info_future.result()  # 忽略返回值
                                quote = quote_future.result()
                                if quote is not None:
                                    name = quote.get('name', symbol)  # 使用行情中的名称
                                    change = quote.get('change', '--')
                                else:
                                    name = symbol
                                    change = '--'
                            else:
                                # 处理普通股票数据
                                name, _ = info_future.result()
                                quote = quote_future.result()
                                change = quote.get('change', '--') if quote else '--'
                            
                            update_tree_item(symbol, name, None, change)
                            update_progress(i, total)
                            
                        except Exception as e:
                            print(f"Error loading data for {symbol}: {e}")
                            update_tree_item(symbol, "加载失败", None, "--")
                
                def cleanup():
                    progress_label.destroy()
                    # 更新缓存
                    self.list_cache[self.current_list] = self.original_items.copy()
                    # 如果有排序设置，应用排序
                    if self.last_sort_column:
                        self.sort_treeview(self.last_sort_column)
                    # 更新统计信息
                    self.update_statistics()
                self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error():
                    messagebox.showerror("错误", f"加载数据失败: {str(e)}")
                    progress_label.destroy()
                    # 即使出错也更新统计
                    self.update_statistics()
                self.window.after(0, show_error)
        
        threading.Thread(target=fetch_data, daemon=True).start()

    def load_signal_stocks(self, signal_type):
        """加载信号股票列表"""
        # 检查缓存是否有效
        cache_data = self.signal_cache.get(signal_type)
        
        if cache_data and cache_data["data"]:
            if not self.should_refresh_cache(cache_data):
                # 使用缓存数据
                self.display_signal_stocks(cache_data["data"])
                return
        
        # 根据信号类型选择加载方法
        if signal_type == "超跌":
            self.load_oversold_stocks()
            return
        elif signal_type == "退市":
            self.load_delisted_stocks()
            return
            
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 创建进度显示
        progress_label = ttk.Label(self.window, text="正在扫描股票... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(count, total):
            """更新进度显示"""
            percent = int((count / total) * 100)
            self.window.after(0, lambda: progress_label.configure(
                text=f"正在扫描股票... {percent}%"))

        def process_batch(batch_stocks):
            """处理一批股票"""
            results = []
            for _, stock in batch_stocks.iterrows():
                try:
                    code = str(stock['代码']).zfill(6)
                    
                    # 过滤掉不符合条件的股票
                    if not self.is_valid_stock(code):
                        continue
                        
                    name = stock['名称']
                    change = stock['涨跌幅']
                    
                    # 获取行业信息
                    industry = self.get_stock_industry(code)
                    
                    # 根据控制变量决定是否加载信息列内容
                    if self.show_info_columns:
                        # 获取信号
                        analysis_engine = ETFAnalysisEngine()
                        conditions = [
                            InstitutionTradingCondition(),
                            # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                            CostAndConcentrationCondition(),
                            CostCrossMaCondition(),
                            CostPriceCompareCondition(),
                            CostCrossPriceBodyCondition(),
                            PriceBelowMA5Condition(),
                            PriceAboveMA5Condition()
                        ]
                        
                        trigger_info = analysis_engine.get_latest_condition_trigger(code, conditions)
                        message = trigger_info['message'] if trigger_info else ''
                        level = trigger_info.get('level', '') if trigger_info else ''
                    else:
                        # 默认情况下信息列和信号列留空
                        message = ''
                        level = ''
                    
                    # 根据信号类型筛选
                    if (signal_type == "买入信号" and level == SignalLevel.BUY.value) or \
                       (signal_type == "卖出信号" and level == SignalLevel.SELL.value):
                        # 添加行业信息到返回结果
                        results.append((name, code, industry, change, '--', '--', message, level))
                        
                except Exception as e:
                    print(f"处理股票{code}时出错: {str(e)}")
                    continue
                    
            return results

        def update_display(results):
            """更新显示结果"""
            # 更新缓存
            self.signal_cache[signal_type] = {
                "timestamp": self.get_readable_timestamp(),
                "data": results
            }
            # 保存缓存到文件
            self.save_signal_cache()
            
            for result in results:
                name, code, industry, change, message, level = result
                values = (name, code, industry, change, '-', '--', '--', '--', message, level)
                item = self.tree.insert("", tk.END, values=values)
                
                # 设置行颜色
                if level == SignalLevel.BUY.value:
                    self.tree.item(item, tags=('buy',))
                elif level == SignalLevel.SELL.value:
                    self.tree.item(item, tags=('sell',))
            
            # 更新统计信息
            self.update_statistics()

        def scan_stocks():
            try:
                # 获取A股列表
                stocks = ak.stock_zh_a_spot_em()
                total_stocks = len(stocks)
                processed_count = 0
                signal_stocks = []
                
                # 分批处理股票
                batch_size = 100  # 每批处理100只股票
                for start_idx in range(0, total_stocks, batch_size):
                    # 获取当前批次的股票
                    end_idx = min(start_idx + batch_size, total_stocks)
                    current_batch = stocks.iloc[start_idx:end_idx]
                    
                    # 创建线程池处理当前批次
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        # 将当前批次平均分配给线程
                        sub_batch_size = max(1, len(current_batch) // self.max_workers)
                        futures = []
                        
                        for i in range(0, len(current_batch), sub_batch_size):
                            sub_batch = current_batch.iloc[i:i + sub_batch_size]
                            futures.append(executor.submit(process_batch, sub_batch))
                        
                        # 收集当前批次的结果
                        batch_results = []
                        for future in as_completed(futures):
                            batch_results.extend(future.result())
                        
                        # 更新进度和显示
                        processed_count += len(current_batch)
                        update_progress(processed_count, total_stocks)
                        
                        # 如果有结果，立即更新显示
                        if batch_results:
                            self.window.after(0, lambda r=batch_results: update_display(r))
                            signal_stocks.extend(batch_results)
                    
                    # 每批处理完后主动清理内存
                    gc.collect()
                
                # 完成后更新缓存
                self.signal_cache[signal_type] = {
                    "timestamp": self.get_readable_timestamp(),
                    "data": signal_stocks
                }
                # 保存缓存到文件
                self.save_signal_cache()
                
                # 清理进度显示
                self.window.after(0, progress_label.destroy)
                
            except Exception as e:
                def show_error(err):
                    messagebox.showerror("错误", f"扫描股票失败: {str(err)}")
                    progress_label.destroy()
                    # 清除可能已经过期的缓存
                    if signal_type in self.signal_cache:
                        del self.signal_cache[signal_type]
                        # 保存更新后的缓存
                        self.save_signal_cache()
                    # 更新统计信息
                    self.update_statistics()
                self.window.after(0, lambda err=e: show_error(err))
        
        # 启动扫描线程
        threading.Thread(target=scan_stocks, daemon=True).start()

    def display_signal_stocks(self, stocks):
        """显示信号股票列表"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # 更新原始数据和缓存
        self.original_items = []
        
        # 显示股票，统一使用6个字段格式
        for stock in stocks:
            name, code, industry, change, message, level = stock
            values = (name, code, industry, change, '--', '--', '--', message, level)
            self.original_items.append(values)
            item = self.tree.insert("", tk.END, values=values)
            
            # 设置行颜色
            if level == SignalLevel.BUY.value:
                self.tree.item(item, tags=('buy',))
            elif level == SignalLevel.SELL.value:
                self.tree.item(item, tags=('sell',))
        
        # 更新list_cache
        self.list_cache[self.current_list] = self.original_items.copy()

    def copy_selected_to_clipboard(self, event=None):
        """将选中的记录以CSV格式复制到剪贴板"""
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        # 获取列标题
        headers = [self.tree.heading(col)["text"].replace(" ↓", "").replace(" ↑", "") 
                  for col in self.tree["columns"]]
        
        # 构建CSV内容
        csv_lines = [",".join(headers)]  # 添加表头
        
        for item in selected_items:
            # 获取行数据
            values = self.tree.item(item)["values"]
            # 处理每个值，确保CSV格式正确
            processed_values = []
            for value in values:
                # 如果值包含逗号，用引号包裹
                if isinstance(value, str) and ("," in value or "\n" in value):
                    processed_value = f'"{value}"'
                else:
                    processed_value = str(value)
                processed_values.append(processed_value)
            
            csv_lines.append(",".join(processed_values))
        
        # 将内容复制到剪贴板
        csv_content = "\n".join(csv_lines)
        self.window.clipboard_clear()
        self.window.clipboard_append(csv_content)
        self.window.update()  # 确保内容被复制 

    def update_statistics(self):
        """更新统计信息"""
        try:
            # 获取所有项目
            items = self.tree.get_children()
            total_count = len(items)
            
            if total_count == 0:
                self.stats_label.config(text="无数据")
                return
            
            # 收集所有项的涨跌幅数据
            changes = []
            for item in items:
                values = self.tree.item(item)["values"]
                try:
                    # 涨跌幅现在是第4列（索引3）
                    change_str = str(values[3]).replace('%', '')
                    change = float(change_str)
                    changes.append(change)
                except (ValueError, IndexError):
                    continue
            
            # 收集选中项的涨跌幅数据
            selected_items = self.tree.selection()
            selected_changes = []
            for item in selected_items:
                values = self.tree.item(item)["values"]
                try:
                    # 涨跌幅列的索引
                    change_str = str(values[3]).replace('%', '')
                    change = float(change_str)
                    selected_changes.append(change)
                except (ValueError, IndexError):
                    continue
            
            # 计算统计信息
            stats_text = f"证券数量: {total_count}"
            
            # 计算总体平均涨跌幅
            if changes:
                avg_change = sum(changes) / len(changes)
                stats_text += f" | 平均涨跌幅: {avg_change:+.2f}%"
            else:
                stats_text += " | 平均涨跌幅: --"
            
            # 添加选中项统计信息
            if selected_items:
                stats_text += f" | 选中: {len(selected_items)}"
                if selected_changes:
                    selected_avg = sum(selected_changes) / len(selected_changes)
                    stats_text += f" | 选中平均涨跌幅: {selected_avg:+.2f}%"
                else:
                    stats_text += " | 选中平均涨跌幅: --"
            
            # 添加龙虎榜日期信息（如果是龙虎榜列表）
            if self.current_list == "龙虎榜" and "龙虎榜" in self.signal_cache:
                lhb_cache = self.signal_cache["龙虎榜"]
                if "lhb_date" in lhb_cache:
                    lhb_date = lhb_cache["lhb_date"]
                    # 格式化日期显示：YYYYMMDD -> YYYY-MM-DD
                    if lhb_date and len(lhb_date) == 8:
                        formatted_date = f"{lhb_date[:4]}-{lhb_date[4:6]}-{lhb_date[6:8]}"
                        stats_text += f" | 龙虎榜日期: {formatted_date}"
            
            self.stats_label.config(text=stats_text)
            
        except Exception as e:
            print(f"更新统计信息时出错: {str(e)}")
            self.stats_label.config(text="统计信息更新失败")

    def is_valid_stock(self, code):
        """检查是否为有效的股票代码（非科创板、非ETF等）"""
        try:
            code = str(code).zfill(6)  # 确保是6位字符串
            
            # 检查是否以排除前缀开头
            for prefix in self.excluded_prefixes:
                if code.startswith(prefix):
                    return False
                
            return True
        except:
            return False

    def is_trading_time(self):
        """检查当前是否为交易时间"""
        try:
            now = datetime.now()
            
            # 检查是否为工作日
            if now.weekday() >= 5:  # 周六(5)和周日(6)不是交易日
                return False
            
            # 获取当前时间的小时和分钟
            current_time = (now.hour, now.minute)
            
            # 检查是否在交易时间范围内
            if (current_time >= self.trading_hours['start'] and 
                current_time <= self.trading_hours['end']):
                return True
            
            return False
        except:
            return True  # 如果检查出错，默认允许刷新

    def should_refresh_cache(self, cache_data):
        """检查是否需要刷新缓存"""
        if not cache_data or not cache_data.get("timestamp") or not cache_data.get("data"):
            # 如果没有缓存数据，需要刷新
            return True
        
        try:
            # 处理时间戳（可能是字符串或数字格式）
            cache_timestamp = cache_data["timestamp"]
            if isinstance(cache_timestamp, str):
                # 字符串格式的时间戳
                cache_time = datetime.strptime(cache_timestamp, '%Y-%m-%d %H:%M:%S')
            else:
                # 数字格式的时间戳（向后兼容）
                cache_time = datetime.fromtimestamp(cache_timestamp)
            
            current_time = datetime.now()
            cache_age = (current_time - cache_time).total_seconds()
            
            # 获取当前日期和缓存日期
            current_date = current_time.date()
            cache_date = cache_time.date()
            
            # 如果不在交易时间且有有效缓存数据
            if not self.is_trading_time() and cache_data.get("data"):
                # 只有当缓存是当天的数据时才使用缓存
                return current_date != cache_date
            
            return cache_age >= self.cache_timeout
            
        except Exception as e:
            print(f"解析缓存时间戳失败: {e}")
            return True  # 解析失败时刷新缓存

    def get_readable_timestamp(self):
        """获取可读的时间戳"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def load_signal_cache(self):
        """从文件加载信号缓存"""
        default_cache = {
            "买入信号": {"timestamp": None, "data": []},
            "卖出信号": {"timestamp": None, "data": []},
            "超跌": {"timestamp": None, "data": []},
            "龙虎榜": {"timestamp": None, "data": []}
        }
        
        try:
            if os.path.exists(self.signal_cache_file):
                with open(self.signal_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    return cache_data
        except Exception as e:
            print(f"加载信号缓存失败: {str(e)}")
        
        return default_cache

    def save_signal_cache(self):
        """保存信号缓存到文件"""
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.signal_cache_file), exist_ok=True)
            
            with open(self.signal_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.signal_cache, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存信号缓存失败: {str(e)}")

    def load_trend_cache(self):
        """从文件加载趋势缓存"""
        default_cache = {
            "version": self.version,
            "data": {}
        }
        
        try:
            if os.path.exists(self.trend_cache_file):
                with open(self.trend_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                    # 检查是否为旧格式（没有version字段）
                    if "version" not in cache_data:
                        print("检测到旧格式缓存，正在转换...")
                        # 转换旧格式到新格式
                        converted_data = {
                            "version": self.version,
                            "data": cache_data
                        }
                        # 保存转换后的数据
                        self.save_trend_cache_data(converted_data)
                        return converted_data
                    
                    return cache_data
        except Exception as e:
            print(f"加载趋势缓存失败: {str(e)}")
        
        return default_cache

    def save_trend_cache(self):
        """保存趋势缓存到文件"""
        self.save_trend_cache_data(self.trend_cache)
    
    def _save_trend_cache_safe(self, cache_data):
        """线程安全的趋势缓存保存方法"""
        try:
            self.save_trend_cache_data(cache_data)
        except Exception as e:
            print(f"线程安全保存趋势缓存失败: {str(e)}")
    
    def save_trend_cache_data(self, cache_data):
        """保存趋势缓存数据到文件"""
        try:
            # 确保配置目录存在
            os.makedirs(os.path.dirname(self.trend_cache_file), exist_ok=True)
            
            with open(self.trend_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存趋势缓存失败: {str(e)}")

    def is_trend_cache_valid(self, symbol: str) -> bool:
        """检查趋势缓存是否有效"""
        # 检查文件级别版本号
        if self.trend_cache.get('version') != self.version:
            print(f"算法版本不匹配，缓存无效: 缓存版本={self.trend_cache.get('version', 'v0.0.0')}, 当前版本={self.version}")
            return False
        
        # 检查符号是否存在
        if symbol not in self.trend_cache.get('data', {}):
            return False
        
        cache_data = self.trend_cache['data'][symbol]
        if not cache_data or 'timestamp' not in cache_data:
            return False
        
        # 检查缓存时间是否超时
        current_time = time.time()
        
        # 处理时间戳格式（可能是字符串或数字）
        cache_timestamp = cache_data['timestamp']
        if isinstance(cache_timestamp, str):
            # 如果是字符串格式，解析为时间戳
            try:
                from datetime import datetime
                cache_time = datetime.strptime(cache_timestamp, '%Y-%m-%d %H:%M:%S').timestamp()
            except ValueError:
                # 如果解析失败，认为缓存无效
                return False
        else:
            # 如果是数字格式，直接使用
            cache_time = cache_timestamp
        
        cache_age = current_time - cache_time
        
        # 如果缓存超时，则无效
        if cache_age > self.trend_cache_timeout:
            return False
        
        # 如果缓存数据包含error，则无效（需要重新计算）
        trend_data = cache_data.get('data', {})
        if any(trend == 'error' for trend in trend_data.values()):
            return False
        
        return True

    def get_cached_trend_data(self, symbol: str) -> tuple:
        """获取缓存的趋势数据"""
        if not self.is_trend_cache_valid(symbol):
            return None
        
        cache_data = self.trend_cache['data'][symbol]['data']
        return (
            cache_data.get('day_trend', '-'),
            cache_data.get('week_trend', '-'),
            cache_data.get('month_trend', '-'),
            cache_data.get('ma5_deviation', '-'),
            cache_data.get('next_day_limit_up_ma5_deviation', '-'),
            cache_data.get('intraday_trend', '-'),
            cache_data.get('cost_change', '-')
        )

    def save_trend_data(self, symbol: str, day_trend: str, week_trend: str, month_trend: str, ma5_deviation: str = '-', next_day_limit_up_ma5_deviation: str = '-', intraday_trend: str = '-', cost_change: str = '-'):
        """保存趋势数据到缓存"""
        try:
            # 确保缓存结构正确
            if 'data' not in self.trend_cache:
                self.trend_cache['data'] = {}
            if 'version' not in self.trend_cache:
                self.trend_cache['version'] = self.version
            
            # 创建数据副本，避免在迭代时修改字典
            trend_data = {
                'timestamp': time.time(),  # 使用数字时间戳
                'data': {
                    'day_trend': day_trend,
                    'week_trend': week_trend,
                    'month_trend': month_trend,
                    'ma5_deviation': ma5_deviation,
                    'next_day_limit_up_ma5_deviation': next_day_limit_up_ma5_deviation,
                    'intraday_trend': intraday_trend,
                    'cost_change': cost_change
                }
            }
            
            # 安全地更新缓存
            self.trend_cache['data'][symbol] = trend_data
            
            # 异步保存到文件，使用深拷贝避免线程安全问题
            import copy
            cache_copy = copy.deepcopy(self.trend_cache)
            threading.Thread(target=self._save_trend_cache_safe, args=(cache_copy,), daemon=True).start()
            
        except Exception as e:
            print(f"保存趋势数据失败 {symbol}: {str(e)}")

    def clear_old_version_cache(self):
        """清除旧版本算法的缓存数据"""
        try:
            cached_version = self.trend_cache.get('version', 'v0.0.0')
            if cached_version != self.version:
                print(f"检测到版本不匹配，正在清除缓存: 缓存版本={cached_version}, 当前版本={self.version}")
                # 清空所有数据，保留版本号
                self.trend_cache = {
                    'version': self.version,
                    'data': {}
                }
                # 保存更新后的缓存
                self.save_trend_cache()
                print("已清除所有旧版本缓存")
        except Exception as e:
            print(f"清除旧版本缓存时出错: {str(e)}")

    def on_selection_changed(self, event):
        """处理选中项变化事件"""
        self.update_statistics()

    def close(self):
        """关闭自选列表窗口"""
        try:
            # 保存自选列表数据
            self.save_watchlists()
            
            # 销毁窗口
            if self.window:
                self.window.destroy()
                self.window = None
                
        except Exception as e:
            print(f"Error closing watchlist window: {e}")

    def get_stock_industry(self, symbol):
        """获取个股行业信息"""
        # 跳过板块和ETF
        if symbol.startswith('BK') or len(symbol) == 6 and symbol.startswith(('51', '56', '15')):
            return ''
            
        try:
            # 如果已经缓存，直接返回
            if symbol in self.industry_cache:
                return self.industry_cache[symbol]
                
            # 获取行业信息
            stock_info = ak.stock_individual_info_em(symbol=symbol)
            industry = stock_info[stock_info['item'] == '行业']['value'].values[0]
            self.industry_cache[symbol] = industry
            return industry
        except:
            return ''

    def calculate_cost_change(self, symbol: str) -> str:
        """计算股价成本涨幅
        
        Args:
            symbol: 股票代码
            
        Returns:
            股价成本涨幅字符串，如"+5.2%"或"-"
        """
        try:
            import time

            import numpy as np
            import pandas as pd

            # 检查是否为指数或板块，这些没有平均成本数据
            if str(symbol) in ["1A0001", "000001"] or str(symbol).startswith('BK'):
                return '-'
            
            # 检查是否有筹码数据
            if not self.analysis_engine.has_stock_cyq_data(symbol):
                return '-'
            
            # 添加API调用延迟，避免并发冲突
            time.sleep(0.1)
            
            # 获取历史数据
            from datetime import datetime, timedelta
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)  # 获取最近30天数据
            
            # 获取K线数据
            hist_data = ak.stock_zh_a_hist(symbol=symbol, start_date=start_date.strftime('%Y%m%d'), 
                                         end_date=end_date.strftime('%Y%m%d'), adjust="qfq")
            if hist_data.empty:
                print(f"K线数据为空: {symbol}")
                return '-'
            
            # 获取筹码数据
            try:
                cyq_data = ak.stock_cyq_em(symbol=symbol, adjust="qfq")
                if cyq_data.empty or '平均成本' not in cyq_data.columns:
                    print(f"筹码数据为空或缺少平均成本列: {symbol}")
                    return '-'
            except Exception as cyq_error:
                print(f"获取筹码数据失败 {symbol}: {cyq_error}")
                return '-'
            
            # 处理数据
            hist_data['日期'] = pd.to_datetime(hist_data['日期'])
            hist_data = hist_data.set_index('日期')
            cyq_data['日期'] = pd.to_datetime(cyq_data['日期'])
            cyq_data = cyq_data.set_index('日期')
            
            # 合并数据
            merged_data = hist_data.merge(cyq_data[['平均成本']], how='left', left_index=True, right_index=True)
            
            # 获取最新数据
            latest_data = merged_data.dropna().iloc[-1]
            latest_close = latest_data['收盘']
            latest_avg_cost = latest_data['平均成本']
            
            if pd.isna(latest_avg_cost):
                print(f"平均成本数据为空: {symbol}")
                return '-'
            
            # 计算成本涨幅
            cost_change = ((latest_close - latest_avg_cost) / latest_avg_cost) * 100
            
            print(f"股价成本涨幅计算成功 {symbol}: 收盘价={latest_close:.2f}, 平均成本={latest_avg_cost:.2f}, 涨幅={cost_change:.2f}%")
            return f"{cost_change:+.1f}%"
            
        except Exception as e:
            print(f"计算股价成本涨幅失败 {symbol}: {e}")
            return '-'

    def is_oversold_stock(self, code: str) -> bool:
        """判断股票是否超跌
        @param code: 股票代码
        @return: 是否超跌
        """
        try:
            # 创建分析引擎实例
            analysis_engine = ETFAnalysisEngine()
            
            # 获取K线数据
            today = datetime.now()
            start_date = (today - timedelta(days=250 * 2)).strftime('%Y%m%d')  # 获取足够的历史数据来计算MA250
            end_date = today.strftime('%Y%m%d')
            
            # 使用load_data方法获取包含90%筹码集中度的数据
            df = analysis_engine.load_data(
                code=code,
                symbol_name='',  # 名称不重要
                period_mode='day',
                start_date=start_date,
                end_date=end_date,
                period_config={
                    'day': {
                        'ak_period': 'daily',
                        'buffer_ratio': '0.2',
                        'min_buffer': '3'
                    }
                }, 
                ma_lines=[250]  # 只需要MA250
            )
           
            # 准备数据序列
            data_sequence = {
                'kline_data': df
            }
            
            # 使用OversoldCondition进行判断
            condition = OversoldCondition()
            signal = condition.check(data_sequence)
            
            return signal.triggered
            
        except Exception as e:
            print(f"判断超跌股票时出错 {code}: {str(e)}")
            return False

    def load_oversold_stocks(self):
        """加载超跌股票列表"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 创建进度显示
        progress_label = ttk.Label(self.window, text="正在扫描超跌股票... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(count, total):
            """更新进度显示"""
            percent = int((count / total) * 100)
            self.window.after(0, lambda: progress_label.configure(
                text=f"正在扫描超跌股票... {percent}%"))

        def process_batch(batch_stocks):
            """处理一批股票"""
            results = []
            for _, stock in batch_stocks.iterrows():
                try:
                    code = str(stock['代码']).zfill(6)
                    
                    # 过滤掉不符合条件的股票
                    if not self.is_valid_stock(code):
                        continue
                        
                    # 判断是否超跌
                    if not self.is_oversold_stock(code):
                        continue
                        
                    name = stock['名称']
                    change = stock['涨跌幅']
                    
                    # 获取行业信息
                    industry = self.get_stock_industry(code)
                    
                    # 根据控制变量决定是否加载信息列内容
                    if self.show_info_columns:
                        # 获取信号
                        analysis_engine = ETFAnalysisEngine()
                        conditions = [
                            InstitutionTradingCondition(),
                            # KdjCrossCondition(),  # 已移除KDJ金叉死叉信号
                            CostAndConcentrationCondition(),
                            CostCrossMaCondition(),
                            CostPriceCompareCondition(),
                            CostCrossPriceBodyCondition(),
                            PriceBelowMA5Condition(),
                            PriceAboveMA5Condition()
                        ]
                        
                        trigger_info = analysis_engine.get_latest_condition_trigger(code, conditions)
                        message = trigger_info['message'] if trigger_info else ''
                        level = trigger_info.get('level', '') if trigger_info else ''
                    else:
                        # 默认情况下信息列和信号列留空
                        message = ''
                        level = ''
                    
                    # 添加到结果列表
                    results.append((name, code, industry, change, '--', '--', message, level))
                        
                except Exception as e:
                    print(f"处理股票{code}时出错: {str(e)}")
                    continue
                    
            return results

        def update_display(results):
            """更新显示结果"""
            # 更新缓存
            self.signal_cache["超跌"] = {
                "timestamp": self.get_readable_timestamp(),
                "data": results
            }
            # 保存缓存到文件
            self.save_signal_cache()
            
            for result in results:
                name, code, industry, change, message, level = result
                values = (name, code, industry, change, '-', '--', '--', '--', message, level)  # 加占位符保持列数一致
                item = self.tree.insert("", tk.END, values=values)
                
                # 设置行颜色
                if level == SignalLevel.BUY.value:
                    self.tree.item(item, tags=('buy',))
                elif level == SignalLevel.SELL.value:
                    self.tree.item(item, tags=('sell',))
            
            # 更新统计信息
            self.update_statistics()

        def scan_stocks():
            try:
                # 获取A股列表
                stocks = ak.stock_zh_a_spot_em()
                total_stocks = len(stocks)
                processed_count = 0
                oversold_stocks = []
                
                # 分批处理股票
                batch_size = 100  # 每批处理100只股票
                for start_idx in range(0, total_stocks, batch_size):
                    # 获取当前批次的股票
                    end_idx = min(start_idx + batch_size, total_stocks)
                    current_batch = stocks.iloc[start_idx:end_idx]
                    
                    # 创建线程池处理当前批次
                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        # 将当前批次平均分配给线程
                        sub_batch_size = max(1, len(current_batch) // self.max_workers)
                        futures = []
                        
                        for i in range(0, len(current_batch), sub_batch_size):
                            sub_batch = current_batch.iloc[i:i + sub_batch_size]
                            futures.append(executor.submit(process_batch, sub_batch))
                        
                        # 收集当前批次的结果
                        batch_results = []
                        for future in as_completed(futures):
                            batch_results.extend(future.result())
                        
                        # 更新进度和显示
                        processed_count += len(current_batch)
                        update_progress(processed_count, total_stocks)
                        
                        # 如果有结果，立即更新显示
                        if batch_results:
                            self.window.after(0, lambda r=batch_results: update_display(r))
                            oversold_stocks.extend(batch_results)
                    
                    # 每批处理完后主动清理内存
                    gc.collect()
                
                # 完成后更新缓存
                self.signal_cache["超跌"] = {
                    "timestamp": self.get_readable_timestamp(),
                    "data": oversold_stocks
                }
                # 保存缓存到文件
                self.save_signal_cache()
                
                # 清理进度显示
                self.window.after(0, progress_label.destroy)
                
            except Exception as e:
                def show_error(err):
                    messagebox.showerror("错误", f"扫描超跌股票失败: {str(err)}")
                    progress_label.destroy()
                    # 清除可能已经过期的缓存
                    if "超跌" in self.signal_cache:
                        del self.signal_cache["超跌"]
                        # 保存更新后的缓存
                        self.save_signal_cache()
                    # 更新统计信息
                    self.update_statistics()
                self.window.after(0, lambda err=e: show_error(err))
        
        # 启动扫描线程
        threading.Thread(target=scan_stocks, daemon=True).start()

    def get_latest_holders_count(self, symbol: str):
        """获取股东增幅(含日期)和人均持股增幅(不含日期)
        @param symbol: 股票代码
        @return: (股东增幅字符串, 人均增幅字符串), 无数据返回("--","--")"""
        try:
            # 跳过板块和ETF等非普通股票
            if symbol.startswith('BK') or (len(symbol) == 6 and symbol.startswith(('51','56','15'))):
                return ('--', '--')
            
            from datetime import datetime, timedelta

            import pandas as pd

            # 设置时间范围：获取最近一年的数据
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
            
            df = akshare.get_holders_historical_data(symbol, start_date, end_date)
            if df is None or df.empty:
                return ('--', '--')
            last = df.iloc[-1]
            date_val = last.name
            try:
                date_str = pd.to_datetime(date_val).strftime('%Y-%m-%d')
            except Exception:
                date_str = str(date_val)
            holders_change = last.get('股东人数增幅')
            capita_change = last.get('人均持股数量增幅')
            def fmt(v):
                try:
                    if v is None or pd.isna(v):
                        return '--'
                    return f"{v:+.1f}%"
                except Exception:
                    return '--'

            holders_str = f"{fmt(holders_change)} ({date_str})"
            capita_str = fmt(capita_change)
            return (holders_str, capita_str)
        except Exception as e:
            print(f"获取股东增幅失败 {symbol}: {e}")
            return ('--', '--')

    def load_delisted_stocks(self):
        """加载退市股票列表"""
        # 检查缓存是否有效
        cache_data = self.signal_cache.get("退市")
        
        if cache_data and cache_data["data"]:
            if not self.should_refresh_cache(cache_data):
                # 使用缓存数据
                self.display_delisted_stocks(cache_data["data"])
                return
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 创建进度显示
        progress_label = ttk.Label(self.window, text="正在加载退市股票... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(count, total):
            """更新进度显示"""
            percent = int((count / total) * 100)
            self.window.after(0, lambda: progress_label.configure(
                text=f"正在加载退市股票... {percent}%"))

        def process_delisted_stocks(delisted_df):
            """处理退市股票数据"""
            results = []
            for _, stock in delisted_df.iterrows():
                try:
                    code = str(stock['代码']).zfill(6)
                    name = stock['名称']
                    
                    # 获取行业信息
                    industry = self.get_stock_industry(code)
                    
                    # 退市股票没有实时价格，显示"--"
                    change = "--"
                    
                    # 退市股票的消息和级别
                    message = "已退市"
                    level = "退市"
                    
                    results.append((name, code, industry, change, message, level))
                        
                except Exception as e:
                    print(f"处理退市股票{code}时出错: {str(e)}")
                    continue
                    
            return results

        def update_display(results):
            """更新显示结果"""
            # 更新缓存
            self.signal_cache["退市"] = {
                "timestamp": self.get_readable_timestamp(),
                "data": results
            }
            # 保存缓存到文件
            self.save_signal_cache()
            
            for result in results:
                name, code, industry, change, message, level = result
                values = (name, code, industry, change, '-', '--', '--', '--', message, level)
                item = self.tree.insert("", tk.END, values=values)
                
            
            # 更新统计信息
            self.update_statistics()

        def fetch_delisted_data():
            """获取退市股票数据的线程函数"""
            try:
                # 获取退市股票数据
                # 可能会有连接失败的错误。
                delisted_df = ak.stock_staq_net_stop()
                
                if delisted_df.empty:
                    self.window.after(0, lambda: messagebox.showinfo("提示", "未获取到退市股票数据"))
                    self.window.after(0, progress_label.destroy)
                    return
                
                # 处理退市股票数据
                results = process_delisted_stocks(delisted_df)
                
                def cleanup():
                    progress_label.destroy()
                    update_display(results)
                
                self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error(err):
                    messagebox.showerror("错误", f"加载退市股票失败: {str(err)}")
                    progress_label.destroy()
                    # 清除可能已经过期的缓存
                    if "退市" in self.signal_cache:
                        del self.signal_cache["退市"]
                        # 保存更新后的缓存
                        self.save_signal_cache()
                    # 更新统计信息
                    self.update_statistics()
                self.window.after(0, lambda err=e: show_error(err))
        
        # 启动数据获取线程
        threading.Thread(target=fetch_delisted_data, daemon=True).start()

    def display_delisted_stocks(self, stocks):
        """显示退市股票列表"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 显示退市股票数据
        for stock in stocks:
            name, code, industry, change, message, level = stock
            values = (name, code, industry, change, '--', '--', '--', message, level)
            item = self.tree.insert("", tk.END, values=values)

        
        # 更新统计信息
        self.update_statistics()
    
    def show_cache_management(self):
        """显示缓存管理窗口"""
        # 创建缓存管理窗口
        cache_window = tk.Toplevel(self.window)
        cache_window.title("趋势缓存管理")
        cache_window.geometry("600x500")
        cache_window.resizable(False, False)
        
        # 使窗口居中
        cache_window.transient(self.window)
        cache_window.grab_set()
        
        # 主框架
        main_frame = ttk.Frame(cache_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 缓存信息显示
        info_frame = ttk.LabelFrame(main_frame, text="趋势缓存信息")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 获取趋势缓存信息
        cache_info = self.get_trend_cache_info()
        
        if cache_info["status"] == "no_cache":
            info_text = "无趋势缓存数据"
        else:
            info_text = f"""缓存版本: {cache_info['version']}
缓存时间: {cache_info['cache_time']}
缓存年龄: {cache_info['age_hours']} 小时
缓存项数: {cache_info['data_count']} 个
有效项数: {cache_info['valid_count']} 个
错误项数: {cache_info['error_count']} 个
缓存状态: {'有效' if cache_info['is_valid'] else '已过期'}"""
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(padx=10, pady=10)
        
        # 操作按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 刷新缓存按钮
        refresh_button = ttk.Button(button_frame, text="刷新趋势缓存", 
                                  command=lambda: self.refresh_trend_cache(cache_window))
        refresh_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 清除缓存按钮
        clear_button = ttk.Button(button_frame, text="清除趋势缓存", 
                                command=lambda: self.clear_trend_cache(cache_window))
        clear_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 关闭按钮
        close_button = ttk.Button(button_frame, text="关闭", 
                                command=cache_window.destroy)
        close_button.pack(side=tk.RIGHT)
        
        # 说明文本
        help_frame = ttk.LabelFrame(main_frame, text="说明")
        help_frame.pack(fill=tk.BOTH, expand=True)
        
        help_text = """趋势缓存说明：

1. 缓存内容：股票的趋势数据（日趋势、周趋势、月趋势、MA5偏离度）
2. 缓存有效期：24小时
3. 刷新缓存：重新计算所有股票的趋势数据
4. 清除缓存：删除本地缓存文件，下次计算时会重新获取
5. 缓存优势：避免重复计算，提高加载速度，减少API调用

建议：
- 正常情况下无需手动管理缓存
- 如果趋势数据异常，可以尝试刷新缓存
- 如果算法更新，建议清除缓存后重新计算
- ETF列表缓存只记录代码和名称，价格数据与趋势缓存同步更新"""
        
        help_label = ttk.Label(help_frame, text=help_text, justify=tk.LEFT)
        help_label.pack(padx=10, pady=10)
    
    def get_trend_cache_info(self):
        """获取趋势缓存信息"""
        if not self.trend_cache or not self.trend_cache.get('data'):
            return {"status": "no_cache", "message": "无趋势缓存数据"}
        
        cache_timestamp = self.trend_cache.get('timestamp', 0)
        if cache_timestamp == 0:
            return {"status": "no_cache", "message": "无趋势缓存数据"}
        
        try:
            # 处理时间戳（可能是字符串或数字格式）
            if isinstance(cache_timestamp, str):
                # 字符串格式的时间戳
                cache_time = datetime.strptime(cache_timestamp, '%Y-%m-%d %H:%M:%S')
            else:
                # 数字格式的时间戳（向后兼容）
                cache_time = datetime.fromtimestamp(cache_timestamp)
            
            current_time = datetime.now()
            age_seconds = (current_time - cache_time).total_seconds()
            age_hours = age_seconds / 3600
        except Exception as e:
            return {"status": "error", "message": f"解析缓存时间戳失败: {e}"}
        
        data_items = self.trend_cache.get('data', {})
        data_count = len(data_items)
        
        # 统计有效和错误项数
        valid_count = 0
        error_count = 0
        for symbol, item_data in data_items.items():
            trend_data = item_data.get('data', {})
            if any(trend == 'error' for trend in trend_data.values()):
                error_count += 1
            else:
                valid_count += 1
        
        return {
            "status": "cached",
            "version": self.trend_cache.get('version', 'v1.0.0'),
            "cache_time": cache_time.strftime("%Y-%m-%d %H:%M:%S"),
            "age_hours": round(age_hours, 2),
            "data_count": data_count,
            "valid_count": valid_count,
            "error_count": error_count,
            "is_valid": self._is_trend_cache_valid()
        }
    
    def _is_trend_cache_valid(self):
        """检查趋势缓存是否有效（简化版本）"""
        if not self.trend_cache or not self.trend_cache.get('data'):
            return False
        
        cache_time = self.trend_cache.get('timestamp', 0)
        if cache_time == 0:
            return False
        
        current_time = time.time()
        age_seconds = current_time - cache_time
        
        # 检查是否超过缓存有效期（24小时）
        return age_seconds <= self.trend_cache_timeout
    
    def refresh_trend_cache(self, parent_window):
        """刷新趋势缓存"""
        # 显示刷新进度
        progress_window = tk.Toplevel(parent_window)
        progress_window.title("刷新趋势缓存")
        progress_window.geometry("300x100")
        progress_window.resizable(False, False)
        progress_window.transient(parent_window)
        progress_window.grab_set()
        
        progress_label = ttk.Label(progress_window, text="正在刷新趋势缓存...")
        progress_label.pack(pady=20)
        
        def refresh_task():
            try:
                # 清除当前趋势缓存
                self.trend_cache = {
                    'version': self.version,
                    'data': {}
                }
                
                # 保存清空的缓存
                self.save_trend_cache()
                
                def success():
                    progress_window.destroy()
                    messagebox.showinfo("成功", "趋势缓存已清空，下次计算趋势时会重新获取数据")
                    parent_window.destroy()  # 关闭管理窗口
                
                self.window.after(0, success)
                
            except Exception as e:
                def error():
                    progress_window.destroy()
                    messagebox.showerror("错误", f"刷新趋势缓存失败：{str(e)}")
                
                self.window.after(0, error)
        
        # 在后台线程中执行刷新
        import threading
        threading.Thread(target=refresh_task, daemon=True).start()
    
    def clear_trend_cache(self, parent_window):
        """清除趋势缓存"""
        if messagebox.askyesno("确认", "确定要清除趋势缓存吗？\n清除后下次计算趋势时会重新获取数据。"):
            try:
                # 清除内存中的缓存
                self.trend_cache = {
                    'version': self.version,
                    'data': {}
                }
                
                # 删除缓存文件
                if os.path.exists(self.trend_cache_file):
                    os.remove(self.trend_cache_file)
                
                messagebox.showinfo("成功", "趋势缓存已清除！")
                parent_window.destroy()  # 关闭管理窗口
                
            except Exception as e:
                messagebox.showerror("错误", f"清除趋势缓存失败：{str(e)}")
    
    def refresh_etf_cache(self, parent_window):
        """刷新ETF缓存"""
        from etf_list_cache import get_etf_list_cache
        etf_cache = get_etf_list_cache()
        
        # 显示刷新进度
        progress_window = tk.Toplevel(parent_window)
        progress_window.title("刷新缓存")
        progress_window.geometry("300x100")
        progress_window.resizable(False, False)
        progress_window.transient(parent_window)
        progress_window.grab_set()
        
        progress_label = ttk.Label(progress_window, text="正在刷新ETF列表缓存...")
        progress_label.pack(pady=20)
        
        def refresh_task():
            try:
                # 强制刷新缓存
                etf_list, etf_159 = etf_cache.get_etf_list(force_refresh=True)
                
                def success():
                    progress_window.destroy()
                    messagebox.showinfo("成功", f"缓存刷新成功！\n获取到 {len(etf_list)} 个ETF，其中159开头 {len(etf_159)} 个")
                    parent_window.destroy()  # 关闭管理窗口
                
                self.window.after(0, success)
                
            except Exception as e:
                def error():
                    progress_window.destroy()
                    messagebox.showerror("错误", f"刷新缓存失败：{str(e)}")
                
                self.window.after(0, error)
        
        # 在后台线程中执行刷新
        import threading
        threading.Thread(target=refresh_task, daemon=True).start()
    
    def clear_etf_cache(self, parent_window):
        """清除ETF缓存"""
        if messagebox.askyesno("确认", "确定要清除ETF列表缓存吗？\n清除后下次加载会重新从API获取数据。"):
            from etf_list_cache import get_etf_list_cache
            etf_cache = get_etf_list_cache()
            
            etf_cache.clear_cache()
            messagebox.showinfo("成功", "ETF列表缓存已清除！")
            parent_window.destroy()  # 关闭管理窗口

    def should_refresh_lhb_cache(self, cache_data):
        """检查龙虎榜缓存是否需要刷新（考虑交易日）"""
        if not cache_data or not cache_data.get("timestamp") or not cache_data.get("data"):
            return True
        
        try:
            # 获取最新交易日日期
            latest_trading_date = self._get_last_trade_date()
            if not latest_trading_date:
                print("无法获取最新交易日，使用默认缓存检查")
                return self.should_refresh_cache(cache_data)
            
            # 解析最新交易日日期
            latest_trading_datetime = datetime.strptime(latest_trading_date, '%Y%m%d')
            latest_trading_date_only = latest_trading_datetime.date()
            
            # 处理缓存时间戳
            cache_timestamp = cache_data["timestamp"]
            if isinstance(cache_timestamp, str):
                cache_time = datetime.strptime(cache_timestamp, '%Y-%m-%d %H:%M:%S')
            else:
                cache_time = datetime.fromtimestamp(cache_timestamp)
            
            cache_date = cache_time.date()
            
            print(f"龙虎榜缓存检查: 缓存日期={cache_date}, 最新交易日={latest_trading_date_only}")
            
            # 如果缓存日期早于最新交易日，需要刷新
            if cache_date < latest_trading_date_only:
                print(f"龙虎榜缓存过期: 缓存日期({cache_date})早于最新交易日({latest_trading_date_only})")
                return True
            
            # 如果缓存日期等于最新交易日，检查是否在合理时间内（避免频繁刷新）
            if cache_date == latest_trading_date_only:
                current_time = datetime.now()
                cache_age = (current_time - cache_time).total_seconds()
                # 如果缓存时间超过1小时，允许刷新
                if cache_age > 3600:
                    print(f"龙虎榜缓存时间过长: {cache_age/3600:.1f}小时，允许刷新")
                    return True
                else:
                    print(f"龙虎榜缓存有效: 同一天且时间合理({cache_age/60:.1f}分钟)")
                    return False
            
            # 如果缓存日期晚于最新交易日（不应该发生），使用默认检查
            print(f"龙虎榜缓存日期异常: 缓存日期({cache_date})晚于最新交易日({latest_trading_date_only})")
            return self.should_refresh_cache(cache_data)
            
        except Exception as e:
            print(f"龙虎榜缓存检查失败: {e}，使用默认检查")
            return self.should_refresh_cache(cache_data)

    def load_lhb_data(self):
        """加载龙虎榜数据"""
        # 检查缓存是否有效
        cache_data = self.signal_cache.get("龙虎榜")
        
        if cache_data and cache_data["data"]:
            # 检查缓存数据格式是否兼容
            try:
                # 测试第一个数据项的解包和格式
                if cache_data["data"]:
                    test_stock = cache_data["data"][0]
                    # 检查元素数量
                    if len(test_stock) not in [12, 13]:
                        print("检测到不兼容的缓存数据格式（元素数量），清除缓存")
                        del self.signal_cache["龙虎榜"]
                        self.save_signal_cache()
                        cache_data = None
                    # 检查股票代码是否包含#符号（旧格式）
                    elif len(test_stock) >= 2 and isinstance(test_stock[1], str) and test_stock[1].startswith('#'):
                        print("检测到旧格式缓存数据（代码包含#符号），清除缓存")
                        del self.signal_cache["龙虎榜"]
                        self.save_signal_cache()
                        cache_data = None
            except Exception as e:
                print(f"缓存数据格式检查失败: {e}，清除缓存")
                if "龙虎榜" in self.signal_cache:
                    del self.signal_cache["龙虎榜"]
                    self.save_signal_cache()
                cache_data = None
        
        if cache_data and cache_data["data"]:
            if not self.should_refresh_lhb_cache(cache_data):
                # 使用缓存数据
                # 如果缓存中没有龙虎榜日期，尝试从其他地方获取
                if "lhb_date" not in cache_data:
                    # 尝试从缓存时间戳推断日期，或使用当前日期
                    try:
                        from datetime import datetime

                        # 从时间戳中提取日期
                        timestamp = cache_data.get("timestamp", "")
                        if timestamp:
                            # 假设时间戳格式为 "YYYY-MM-DD HH:MM:SS"
                            date_part = timestamp.split(" ")[0]
                            cache_data["lhb_date"] = date_part.replace("-", "")
                        else:
                            # 使用当前日期作为备选
                            cache_data["lhb_date"] = datetime.now().strftime("%Y%m%d")
                    except Exception as e:
                        print(f"无法推断龙虎榜日期: {e}")
                        cache_data["lhb_date"] = datetime.now().strftime("%Y%m%d")
                
                self.display_lhb_stocks(cache_data["data"])
                return
        
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 创建进度显示
        progress_label = ttk.Label(self.window, text="正在加载龙虎榜数据... 0%")
        progress_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        def update_progress(current, total):
            """更新进度显示"""
            percent = int((current / total) * 100)
            if hasattr(self, 'window') and self.window.winfo_exists():
                self.window.after(0, lambda: progress_label.configure(
                    text=f"正在加载龙虎榜数据... {percent}%"))
        
        def fetch_lhb_data():
            """获取龙虎榜数据的线程函数"""
            try:
                import time
                from datetime import datetime, timedelta

                import akshare as ak

                # 移除周末检查，直接获取最近交易日的龙虎榜数据
                # 这样在周末也能查看最近交易日的龙虎榜数据
                # 获取最近5个交易日的龙虎榜数据
                end_date = datetime.now()
                start_date = end_date - timedelta(days=7)  # 获取最近7天，确保包含5个交易日
                
                # 使用stock_lhb_detail_daily_sina获取最近交易日的龙虎榜数据
                lhb_df = None
                error_messages = []
                
                # 获取最近交易日日期
                last_trade_date = self._get_last_trade_date()
                if not last_trade_date:
                    error_messages.append("无法确定最近交易日日期")
                else:
                    try:
                        print(f"尝试获取{last_trade_date}的龙虎榜详情数据...")
                        lhb_df = ak.stock_lhb_detail_daily_sina(date=last_trade_date)
                        if not lhb_df.empty:
                            print(f"成功获取{last_trade_date}的龙虎榜数据，共{len(lhb_df)}条记录")
                        else:
                            print(f"{last_trade_date}数据为空")
                            error_messages.append(f"{last_trade_date}龙虎榜数据为空")
                    except Exception as e:
                        error_msg = f"获取{last_trade_date}龙虎榜数据失败: {str(e)}"
                        print(error_msg)
                        error_messages.append(error_msg)
                
                # 如果数据获取失败，显示简单错误信息
                if lhb_df is None or lhb_df.empty:
                    error_info = "无法获取龙虎榜数据。\n"
                    error_info += "可能原因: 网络连接问题或数据源暂时不可用"
                    
                    if error_messages:
                        error_info += f"\n\n技术详情:\n" + "\n".join(error_messages[:2])  # 只显示前2个错误
                    
                    def show_error_message():
                        messagebox.showinfo("龙虎榜数据获取失败", error_info)
                        progress_label.destroy()
                        # 更新统计信息
                        self.update_statistics()
                    
                    self.window.after(0, show_error_message)
                    return
                
                # 处理龙虎榜数据 - 适配stock_lhb_detail_daily_sina接口
                results = []
                seen_codes = set()  # 用于去重的股票代码集合
                total = len(lhb_df)
                
                for i, (_, row) in enumerate(lhb_df.iterrows(), 1):
                    try:
                        # 提取股票信息，确保证券代码为6位数
                        raw_code = str(row.get('股票代码', ''))
                        code = raw_code.zfill(6)  # 确保6位数格式
                        name = row.get('股票名称', '')
                        
                        # 检查是否已存在该股票代码（去重）
                        if code in seen_codes:
                            print(f"跳过重复股票: {name}({code})")
                            continue
                        seen_codes.add(code)
                        
                        # 获取行业信息 (暂时跳过，避免线程问题)
                        industry = ''
                        
                        # 从新接口获取的数据字段
                        close_price = row.get('收盘价', 0)  # 收盘价
                        volume = row.get('成交量', 0)  # 成交量
                        turnover = row.get('成交额', 0)  # 成交额
                        indicator = row.get('指标', '')  # 指标（如"涨幅偏离值达7%的证券"）
                        
                        # 确保indicator是字符串类型
                        if not isinstance(indicator, str):
                            indicator = str(indicator) if indicator is not None else ''
                        
                        # 由于没有实时价格数据，涨跌幅显示为"--"
                        change_str = "--"
                        
                        # 构建消息 - 只显示指标内容
                        message = f"{indicator}"
                        
                        # 根据指标类型判断信号等级
                        if "涨幅偏离" in indicator or "涨幅" in indicator:
                            level = "买入"
                        elif "跌幅偏离" in indicator or "跌幅" in indicator:
                            level = "卖出"
                        else:
                            level = "中性"
                        
                        # 添加到结果列表 (使用原始股票代码，不添加#符号)
                        # 注意: 确保元组元素数量与display_lhb_stocks函数中的解包数量一致
                        # 列顺序: name, code, industry, change, cost_change, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, day_trend, week_trend, month_trend, holders, capita, message, level
                        results.append((name, code, industry, change_str, '-', '--', '--', '--', '--', '--', '--', '--', '--', message, level))
                        
                        # 更新进度
                        update_progress(i, total)
                        
                    except Exception as e:
                        print(f"处理龙虎榜股票{code}时出错: {str(e)}")
                        continue
                
                print(f"龙虎榜数据处理完成，原始数据{total}条，去重后{len(results)}条")
                
                # 更新缓存
                self.signal_cache["龙虎榜"] = {
                    "timestamp": self.get_readable_timestamp(),
                    "data": results,
                    "lhb_date": last_trade_date  # 存储龙虎榜日期
                }
                # 保存缓存到文件
                self.save_signal_cache()
                
                def cleanup():
                    if hasattr(self, 'window') and self.window.winfo_exists():
                        progress_label.destroy()
                        self.display_lhb_stocks(results)
                
                if hasattr(self, 'window') and self.window.winfo_exists():
                    self.window.after(0, cleanup)
                
            except Exception as e:
                def show_error(err):
                    if hasattr(self, 'window') and self.window.winfo_exists():
                        messagebox.showerror("错误", f"加载龙虎榜数据失败: {str(err)}")
                        progress_label.destroy()
                        # 清除可能已经过期的缓存
                        if "龙虎榜" in self.signal_cache:
                            del self.signal_cache["龙虎榜"]
                            # 保存更新后的缓存
                            self.save_signal_cache()
                        # 更新统计信息
                        self.update_statistics()
                if hasattr(self, 'window') and self.window.winfo_exists():
                    self.window.after(0, lambda err=e: show_error(err))
        
        # 启动数据获取线程
        threading.Thread(target=fetch_lhb_data, daemon=True).start()

    def _get_last_trade_date(self):
        """获取最近交易日日期"""
        from datetime import datetime, timedelta

        import pandas as pd
        
        today = datetime.now()
        
        # 使用交易日历获取最近交易日
        try:
            import akshare as ak

            # 使用交易日历接口获取最近交易日
            cal_df = ak.tool_trade_date_hist_sina()
            if not cal_df.empty:
                # 获取最近的交易日
                cal_df['trade_date'] = pd.to_datetime(cal_df['trade_date'])
                # 过滤掉未来日期，只保留今天及之前的交易日
                cal_df = cal_df[cal_df['trade_date'] <= today]
                if not cal_df.empty:
                    latest_trade_date = cal_df['trade_date'].max()
                    date_str = latest_trade_date.strftime('%Y%m%d')
                    print(f"使用交易日历找到最近交易日: {date_str}")
                    return date_str
        except Exception as e:
            print(f"获取交易日历失败: {e}，使用简单方法")
        
        # 如果交易日历获取失败，使用简单方法（跳过周末）
        for days_back in range(0, 11):
            test_date = today - timedelta(days=days_back)
            
            # 跳过周末
            if test_date.weekday() >= 5:  # 周六或周日
                continue
                
            date_str = test_date.strftime('%Y%m%d')
            print(f"使用简单方法找到最近交易日: {date_str}")
            return date_str
        
        print("警告: 无法找到最近交易日")
        return None

    def _is_likely_holiday_period(self, current_time):
        """检查当前是否可能为节假日期间"""
        from datetime import datetime

        # 检查是否为周末
        if current_time.weekday() >= 5:  # 周六或周日
            return True
        
        # 检查是否为常见的节假日期间（简化版本）
        month = current_time.month
        day = current_time.day
        
        # 春节期间 (1-2月)
        if month == 1 or month == 2:
            return True
        
        # 国庆节期间 (10月1-7日)
        if month == 10 and 1 <= day <= 7:
            return True
        
        # 劳动节期间 (5月1-3日)
        if month == 5 and 1 <= day <= 3:
            return True
        
        # 清明节期间 (4月4-6日)
        if month == 4 and 4 <= day <= 6:
            return True
        
        return False

    def display_lhb_stocks(self, stocks):
        """显示龙虎榜股票列表"""
        # 清空表格
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 清空原始数据
        self.original_items = []
        
        # 显示龙虎榜股票数据
        for stock in stocks:
            try:
                # 处理可能存在的旧缓存数据格式
                if len(stock) == 15:
                    # 新格式: 15个元素
                    name, code, industry, change, cost_change, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, day_trend, week_trend, month_trend, holders, capita, message, level = stock
                elif len(stock) == 13:
                    # 旧格式: 13个元素，需要补充缺失的列
                    name, code, industry, change, ma5_deviation, day_trend, week_trend, month_trend, holders, capita, message, level = stock[:12]
                    # 补充缺失的列
                    cost_change = '-'
                    next_day_limit_up_ma5_deviation = '--'
                    intraday_trend = '--'
                elif len(stock) == 12:
                    # 更旧的格式: 12个元素，需要补充缺失的列
                    name, code, industry, change, ma5_deviation, day_trend, week_trend, month_trend, holders, capita, message, level = stock
                    # 补充缺失的列
                    cost_change = '-'
                    next_day_limit_up_ma5_deviation = '--'
                    intraday_trend = '--'
                else:
                    print(f"警告: 龙虎榜数据格式异常，元素数量: {len(stock)}")
                    continue
                
                # 确保证券代码为6位数格式
                code = str(code).zfill(6)
                
                values = (name, code, industry, change, cost_change, ma5_deviation, next_day_limit_up_ma5_deviation, intraday_trend, day_trend, week_trend, month_trend, holders, capita, message, level)
                self.original_items.append(values)
                item = self.tree.insert("", tk.END, values=values)
                
                # 设置行颜色
                if level == "买入":
                    self.tree.item(item, tags=('buy',))
                elif level == "卖出":
                    self.tree.item(item, tags=('sell',))
                    
            except Exception as e:
                print(f"处理龙虎榜股票数据时出错: {str(e)}")
                print(f"数据: {stock}")
                continue
        
        # 更新list_cache
        self.list_cache[self.current_list] = self.original_items.copy()
        
        # 更新统计信息
        self.update_statistics()
