import json
import os
import sys
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from tkinter import messagebox, ttk

import akshare as ak
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from base_window import BaseWindow
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from stock_kline_window import ETFKLineWindow
from stock_price_query import calculate_etf_strength

# 添加StockETFQuery目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
stock_etf_path = os.path.join(os.path.dirname(current_dir), "StockETFQuery")
sys.path.append(stock_etf_path)

table_display_rows = 40

# 之后再导入stock_price_query
from stock_price_query import (analyze_monthly_performance,
                               find_similar_etf_gains,
                               get_all_etf_monthly_data)
from trading_utils import (calculate_price_range, get_symbol_info,
                           is_valid_symbol)


class ETFAnalysisWindow(BaseWindow):
    # 定义表格列及其默认值
    COLUMN_CONFIG = {
        '代码': {'default': '', 'type': str},
        '名称': {'default': '', 'type': str},
        '日均差异': {'default': 0.0, 'type': float},
        '日均最大差异': {'default': 0.0, 'type': float},
        '总涨幅': {'default': 0.0, 'type': float},
        '赚钱度': {'default': 0.0, 'type': float},
        '换手率': {'default': 0.0, 'type': float},
        '换手率增幅': {'default': 0.0, 'type': float},
        '换手率增幅2': {'default': 0.0, 'type': float},
        '换手率增幅3': {'default': 0.0, 'type': float},
        '成交额': {'default': 0.0, 'type': float},
        '周线J': {'default': np.nan, 'type': float},
        '月线J': {'default': np.nan, 'type': float}
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.monthly_data_cache = {}
        self.cache_params = {}
        self.full_etf_results = []
        self.sort_order = {}
        self.etf_window = None
        self.etf_tree = None
        self.month_tree = None
        self.current_month = None
        self.title_frame = None  # 添加标题框架引用
        self.refresh_btn = None  # 添加刷新按钮引用
        self.kline_window = ETFKLineWindow(self.parent.root)  # 添加K线图窗口实例
        self.strength_thread = None  # 添加后台线程引用
        self.code_to_item = {}  # 添加代码到tree item的映射
        self.pinned_codes = set()  # 添加置顶代码集合

    def create_window(self):
        """创建ETF分析窗口"""
        self.window = tk.Toplevel(self.parent)
        self.window.title("ETF对比分析")
        self.window.geometry("1000x600")
        
        # ... 其他窗口创建代码 ...
        
        # 在窗口创建完成后设置快捷键和关闭协议
        self.setup_window()  # 调用基类的setup_window方法

    def show_etf_comparison(self):
        """显示ETF对比窗口"""
        # 获取当前参数
        symbol = self.parent.symbol_var.get().strip()
        start_date = self.parent.start_date_var.get().replace("-", "")
        end_date = self.parent.end_date_var.get().replace("-", "")
        
        # 加载缓存数据
        self.load_monthly_data_cache()
        
        # 获取月度表现数据
        monthly_data, year_range, _ = analyze_monthly_performance(self.parent.symbol_var.get())
        
        # 创建独立窗口
        self.etf_window = tk.Toplevel()  
        self.etf_window.title("ETF对比分析")
        self.etf_window.geometry("1000x600")
        
        # 设置窗口层级
        self.etf_window.attributes('-topmost', True)
        self.etf_window.focus_force()
        
        # 设置窗口位置为屏幕居中
        screen_width = self.etf_window.winfo_screenwidth()
        screen_height = self.etf_window.winfo_screenheight()
        x = (screen_width - 1000) // 2
        y = (screen_height - 600) // 2
        self.etf_window.geometry(f"+{x}+{y}")
        
        # 创建元信息显示区域
        meta_frame = ttk.Frame(self.etf_window)
        meta_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 显示目标ETF信息
        target_info = f"目标ETF: {self.parent.symbol_var.get()} - {self.parent.symbol_name_var.get()}"
        ttk.Label(meta_frame, text=target_info, font=('Helvetica', 14, 'bold')).pack(side=tk.LEFT)
                
        # 创建月度表现图表区域
        self.chart_frame = ttk.Frame(self.etf_window)  # 保存为实例变量
        self.chart_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        
        # 创建标题栏
        chart_title_frame = ttk.Frame(self.chart_frame)
        chart_title_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 左侧标题
        year_range_text = f'月度平均涨跌幅 ({year_range})'
        ttk.Label(chart_title_frame, text=year_range_text, font=('Helvetica', 11, 'bold')).pack(side=tk.LEFT)
        
        # 创建按钮和进度标签的容器
        btn_progress_frame = ttk.Frame(chart_title_frame)
        btn_progress_frame.pack(side=tk.RIGHT)
        
        # 右侧添加"全ETF"按钮
        compare_btn = ttk.Button(
            btn_progress_frame, 
            text="全ETF对比",
            command=lambda: self.update_chart_with_market_data(
                monthly_data, 
                year_range, 
                start_date, 
                end_date
            )
        )
        compare_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 添加进度标签
        self.market_progress_label = ttk.Label(btn_progress_frame, text="")
        self.market_progress_label.pack(side=tk.LEFT)
        
        # 创建图表
        self.create_monthly_chart(monthly_data, year_range)
        
        # 创建月度分析区域
        month_frame = ttk.Frame(self.etf_window)
        month_frame.pack(fill=tk.X, padx=10, pady=(5, 0))
        
        # 创建月份按钮工具栏
        month_toolbar = ttk.Frame(month_frame)
        month_toolbar.pack(fill=tk.X, pady=(5, 0))
        
        # 创建标题标签，减小左边距
        ttk.Label(month_toolbar, text="月度分析：", font=('Helvetica', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 5))
        
        # 创建按钮容器
        btn_frame = ttk.Frame(month_toolbar)
        btn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 使用grid布局来均匀分布按钮
        btn_frame.grid_columnconfigure(tuple(range(12)), weight=1)
        
        # 创建12个月份按钮
        for month in range(1, 13):
            btn = ttk.Button(
                btn_frame,
                text=str(month),  # 只显示数字
                width=2,          # 设置最小宽度
                command=lambda m=month: self.start_monthly_analysis(m)
            )
            # 移除不必要的padding调整绑定
            btn.grid(row=0, column=month-1, padx=1, sticky='ew')  # 使用sticky='ew'使按钮水平填充
        
        # 绑定窗口大小变化事件
        self.etf_window.bind('<Configure>', lambda e: self.adjust_month_buttons(e, btn_frame))
        
        # 创建月度排名表格区域
        self.month_table_frame = ttk.Frame(month_frame)
        self.month_table_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # 创建表格框架
        self.table_frame = ttk.Frame(self.etf_window)
        self.table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))
        
        # 创建标题行
        self.create_title_frame()
        
        # 创建进度显示区域
        self.progress_frame = ttk.Frame(self.table_frame)
        self.progress_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        self.loading_label = ttk.Label(self.progress_frame, text="正在分析ETF数据...")
        self.loading_label.pack()
        
        self.etf_progress = ttk.Progressbar(self.progress_frame, orient="horizontal", length=300, mode="determinate")
        self.etf_progress.pack(pady=5)
        
        self.etf_percent_label = ttk.Label(self.progress_frame, text="0%")
        self.etf_percent_label.pack()
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                percent = int((current / total) * 100)
                self.etf_progress["value"] = percent
                self.etf_percent_label["text"] = f"{percent}%"
                self.loading_label["text"] = f"正在分析ETF数据...({current}/{total})"
            self.etf_window.after(0, _update)
        
        def fetch_data():
            try:
                # 使用多API备用机制获取ETF数据
                from .etf_data_fetcher import get_etf_spot_data
                all_etfs = get_etf_spot_data(use_cache=True)
                total_etfs = len(all_etfs)
                
                # 获取相似ETF结果
                results = find_similar_etf_gains(
                    target_code=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    top_n=None,
                    progress_callback=update_progress,
                    total_count=total_etfs
                )
                
                # 确保当前选中的股票代码在结果中
                target_in_results = False
                for etf in results:
                    if etf['代码'] == symbol:
                        target_in_results = True
                        break
                    
                if not target_in_results:
                    # 动态创建目标ETF数据
                    target_etf = {
                        col: self.COLUMN_CONFIG[col]['default']
                        for col in self.COLUMN_CONFIG
                    }
                    # 设置特殊字段
                    target_etf.update({
                        '代码': symbol,
                        '名称': self.parent.symbol_name_var.get().strip(),
                        'need_calculate_strength': True
                    })
                    results.insert(0, target_etf)
                
                # 将当前股票代码加入置顶数组
                self.pinned_codes.add(symbol)
                
                self.etf_window.after(0, lambda: self.show_etf_results(results))
            except Exception as e:
                error_msg = str(e)
                self.etf_window.after(0, lambda msg=error_msg: messagebox.showerror("错误", f"分析失败: {msg}"))
        
        # 启动数据获取线程
        threading.Thread(target=fetch_data, daemon=True).start()

    def load_monthly_data_cache(self):
        """从文件加载月度数据缓存"""
        try:
            cache_file = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                "data", 
                "cache", 
                "monthly_data_cache.json"
            )
            
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                    
                # 恢复缓存数据
                self.monthly_data_cache = cache_data['data']
                self.cache_params = cache_data['params']
                
                # 可以在这里添加缓存过期检查
                cache_time = datetime.fromisoformat(cache_data['timestamp'])
                if (datetime.now() - cache_time).days > 7:  # 缓存超过7天自动失效
                    self.monthly_data_cache.clear()
                    self.cache_params.clear()
                    
        except Exception as e:
            print(f"加载缓存失败: {str(e)}")
            self.monthly_data_cache = {}
            self.cache_params = {}

    def start_monthly_analysis(self, month: int):
        """开始月度分析"""
        try:
            # 获取当前ETF的开始年份
            _, _, start_year = analyze_monthly_performance(self.parent.symbol_var.get())
            
            # 构建缓存键和参数
            cache_key = f"{month}"
            current_params = {
                'start_year': start_year,
            }
            
            # 检查缓存是否有效
            if (cache_key in self.monthly_data_cache and 
                cache_key in self.cache_params and 
                self.cache_params[cache_key] == current_params):
                # 使用缓存数据
                self.show_monthly_top_table(month, self.monthly_data_cache[cache_key])
                return
            
            # 如果缓存无效，开始计算
            # 先初始化表格区域
            for widget in self.month_table_frame.winfo_children():
                widget.destroy()
            
            # 创建临时占位框架确保布局
            placeholder_frame = ttk.Frame(self.month_table_frame, height=300)  # 设置最小高度
            placeholder_frame.pack(fill=tk.BOTH, expand=True)
            placeholder_frame.pack_propagate(False)  # 防止框架被子组件压缩
            
            # 创建进度显示组件
            self.month_progress_frame = ttk.Frame(placeholder_frame)
            self.month_progress_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            
            self.month_loading_label = ttk.Label(self.month_progress_frame, text="正在分析月度数据...")
            self.month_loading_label.pack()
            
            self.month_progress = ttk.Progressbar(self.month_progress_frame, orient="horizontal", length=300, mode="determinate")
            self.month_progress.pack(pady=5)
            
            self.month_percent_label = ttk.Label(self.month_progress_frame, text="0%")
            self.month_percent_label.pack()
            
            # 强制更新布局
            self.month_table_frame.update_idletasks()
            self.etf_window.update_idletasks()

            def update_progress(current, total):
                def _update():
                    percent = int((current / total) * 100)
                    self.month_progress["value"] = percent
                    self.month_percent_label["text"] = f"{percent}%"
                    self.month_loading_label["text"] = f"正在分析ETF数据...({current}/{total})"
                self.etf_window.after(0, _update)

            def fetch_data():
                try:
                    # 获取所有ETF在指定月份的历史数据
                    etf_data = get_all_etf_monthly_data(
                        month, 
                        start_year,
                        progress_callback=lambda current, total: self.etf_window.after(0, update_progress, current, total)
                    )
                    
                    # 更新缓存
                    self.monthly_data_cache[cache_key] = etf_data
                    self.cache_params[cache_key] = current_params
                    
                    # 保存缓存到文件
                    self.save_monthly_data_cache()
                    
                    self.etf_window.after(0, lambda: self.show_monthly_top_table(month, etf_data))
                except Exception as e:
                    # 修复: 将e作为参数传递给lambda
                    error_msg = str(e)
                    self.etf_window.after(0, lambda msg=error_msg: messagebox.showerror("错误", f"分析失败: {msg}"))

            # 启动数据获取线程
            threading.Thread(target=fetch_data, daemon=True).start()

        except Exception as e:
            messagebox.showerror("错误", f"分析过程出错: {str(e)}")

    def adjust_month_buttons(self, event, btn_frame):
        """调整月份按钮的大小以适应窗口宽度"""
        if event.widget == self.etf_window:  # 只处理主窗口的大小变化
            # 获取按钮容器的实际宽度
            frame_width = btn_frame.winfo_width()
            # 计算每个按钮的理想宽度（考虑padding）
            button_width = (frame_width - 24) // 12  # 24是所有按钮的padding总和
            
            # 更新每个按钮的宽度
            for child in btn_frame.winfo_children():
                if isinstance(child, ttk.Button):
                    child.configure(width=max(2, button_width // 8))  # 将像素转换为字符宽度，确保最小宽度为2

    def create_title_frame(self):
        """创建标题行UI"""
        # 创建标题区域
        self.title_frame = ttk.Frame(self.table_frame)
        self.title_frame.pack(fill=tk.X, pady=(0, 5))
        
        # 显示目标ETF信息
        target_info = "涨幅相似性排名"
        ttk.Label(
            self.title_frame, 
            text=target_info, 
            font=('Helvetica', 14, 'bold')
        ).pack(side=tk.LEFT)
        
        # 创建右侧标题区域
        right_title_frame = ttk.Frame(self.title_frame)
        right_title_frame.pack(side=tk.RIGHT)
        
        # 添加刷新按钮
        self.refresh_btn = ttk.Button(
            right_title_frame,
            text="⟳",
            width=3,
            command=self.refresh_etf_results
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 显示分析标题和时间范围
        self.date_label = ttk.Label(
            right_title_frame, 
            text=f"{self.parent.start_date_var.get()} 至 {self.parent.end_date_var.get()}", 
            font=('Helvetica', 11, 'bold')
        )
        self.date_label.pack(side=tk.RIGHT)

    def show_etf_results(self, results):
        """显示ETF对比结果"""
        # 获取所有需要计算的代码
        codes = [etf['代码'] for etf in results]
        
        # 批量获取周线和月线J值
        with ThreadPoolExecutor(max_workers=2) as executor:
            weekly_future = executor.submit(self.get_j_values_batch, codes, 'week')
            monthly_future = executor.submit(self.get_j_values_batch, codes, 'month')
            weekly_j = weekly_future.result()
            monthly_j = monthly_future.result()
        
        # 更新结果
        for etf in results:
            etf['周线J'] = weekly_j.get(etf['代码'], np.nan)
            etf['月线J'] = monthly_j.get(etf['代码'], np.nan)
        
        self.full_etf_results = results
        
        # 更新日期范围显示
        self.date_label.configure(
            text=f"{self.parent.start_date_var.get()} 至 {self.parent.end_date_var.get()}"
        )
        
        # 使用配置生成列定义
        columns = ("置顶",) + tuple(self.COLUMN_CONFIG.keys())
        self.etf_tree = ttk.Treeview(self.table_frame, columns=columns, show="headings", selectmode="browse")
        
        # 添加行点击事件和键盘事件
        self.etf_tree.bind("<Double-1>", self.on_etf_row_click)
        self.etf_tree.bind("<Return>", self.on_etf_row_click)  # 添加回车键绑定
        self.etf_tree.bind("<ButtonRelease-1>", self.on_etf_row_select)  # 添加单击选择事件
        self.etf_tree.bind("<Up>", self.on_etf_key_select)  # 添加上键选择事件
        self.etf_tree.bind("<Down>", self.on_etf_key_select)  # 添加下键选择事件
        self.etf_tree.bind("<Button-1>", self.toggle_pin_status)  # 添加置顶按钮点击事件
        
        # 重置排序状态
        self.sort_order = {col: False for col in columns}
        # 设置初始排序列为"日均差异"，降序排列
        initial_sort_col = "日均差异"
        self.sort_order[initial_sort_col] = True  # True表示降序
        
        # 修改列宽设置
        col_widths = [50, 100, 200, 100, 100, 100,
                      100, 100, 100, 100, 100, 150, 100, 100]  # 成交额列宽度设为150
        for col, width in zip(columns, col_widths):
            # 修改表头点击事件处理
            if col == "置顶":
                self.etf_tree.heading(col, text=col)  # 置顶列不需要排序
            elif col == "赚钱度":
                self.etf_tree.heading(col, 
                                    text=col,
                                    command=lambda c=col: self.handle_strength_column_click(c))
            else:
                self.etf_tree.heading(col, 
                                    text=col,
                                    command=lambda c=col: self.sort_treeview_column(
                                        self.etf_tree, 
                                        c, 
                                        self.sort_order.get(c, False)
                                    ))
            # 成交额、换手率相关列右对齐，其他列居中
            anchor = tk.E if col in ["成交额", "换手率", "换手率增幅", "换手率增幅2", "换手率增幅3"] else tk.CENTER
            self.etf_tree.column(col, width=width, anchor=anchor)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.table_frame, orient=tk.VERTICAL, command=self.etf_tree.yview)
        self.etf_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.etf_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 显示数据
        self.update_table_display()
        
        # 执行初始排序
        self.sort_treeview_column(self.etf_tree, initial_sort_col, False)  # False表示降序

    def on_etf_row_click(self, event):
        """处理ETF表格行双击事件"""
        try:
            # 检查是否有选中的行
            selection = self.etf_tree.selection()
            if not selection:
                return
            
            # 获取选中的ETF代码
            item = selection[0]
            values = self.etf_tree.item(item, 'values')
            if not values:
                return
            
            # 获取选中的ETF代码
            code = values[1]
            
            # 获取当前日期范围
            start_date = self.parent.start_date_var.get().replace("-", "")
            end_date = self.parent.end_date_var.get().replace("-", "")
            
            # 验证并获取ETF信息
            if is_valid_symbol(code):
                # 获取ETF信息
                info = get_symbol_info(code)
                if info:
                    # 更新界面显示
                    self.parent.symbol_var.set(code)
                    self.parent.symbol_name_var.set(info[0])
                    
                    # 计算并更新价格区间
                    price_range = calculate_price_range(code, start_date, end_date)
                    if price_range:
                        # 修改为元组索引访问
                        self.parent.price_range_min_var.set(f"{price_range[0]:.2f}")  # 最小值
                        self.parent.price_range_max_var.set(f"{price_range[1]:.2f}")  # 最大值
                    
        except Exception as e:
            # 添加错误处理,避免程序崩溃
            print(f"选择ETF时出错: {str(e)}")
            messagebox.showerror("错误", f"选择ETF时出错: {str(e)}")

    def sort_treeview_column(self, tv, col, reverse):
        """处理列排序（基于完整数据）"""
        # 对完整数据进行排序，但保持置顶项的顺序
        pinned_results = []
        unpinned_results = []
        
        for etf in self.full_etf_results:
            if etf['代码'] in self.pinned_codes:
                pinned_results.append(etf)
            else:
                unpinned_results.append(etf)
        
        # 只对非置顶项进行排序
        unpinned_results.sort(
            key=lambda x: self.get_sort_key(x, col),
            reverse=reverse
        )
        
        # 合并结果
        self.full_etf_results = pinned_results + unpinned_results
        
        # 更新表格显示
        self.update_table_display()
        self.update_treeview_arrows(tv, col, not reverse)
        self.sort_order[col] = not reverse

    def update_table_display(self):
        """更新表格显示"""
        if not hasattr(self, 'etf_tree'):
            return
        
        self.etf_tree.delete(*self.etf_tree.get_children())
        
        # 将结果分为置顶和非置顶两组
        pinned_results = []
        unpinned_results = []
        
        # 遍历结果列表,保持原有顺序
        for etf in self.full_etf_results:
            if etf['代码'] in self.pinned_codes:
                pinned_results.append(etf)
            else:
                unpinned_results.append(etf)
        
        # 显示结果(置顶项在前,保持它们的顺序)
        display_results = pinned_results + unpinned_results[:table_display_rows - len(pinned_results)]
        
        for etf in display_results:
            # 显示...作为占位符
            strength_display = "..." if etf.get('need_calculate_strength', False) else f"{etf.get('赚钱度', 0.0):.2f}"
            
            # 设置置顶按钮显示
            pin_symbol = "-" if etf['代码'] in self.pinned_codes else "+"
            
            item = self.etf_tree.insert("", tk.END, values=(
                pin_symbol,  # 置顶按钮
                etf['代码'],
                etf['名称'],
                f"{etf['日均差异']:.2f}",
                f"{etf['日均最大差异']:.2f}",
                f"{etf['总涨幅']:.2f}%",
                strength_display,
                f"{etf['换手率']:.2f}%",
                f"{etf['换手率增幅']:.2f}",
                f"{etf['换手率增幅2']:.2f}",
                f"{etf['换手率增幅3']:.2f}",
                f"{etf['成交额']:,.0f}",
                f"{etf['周线J']:.2f}" if '周线J' in etf else '',
                f"{etf['月线J']:.2f}" if '月线J' in etf else ''
            ), tags=(etf['总涨幅'] >= 0 and 'red' or 'green',))
            
            # 更新代码到item的映射
            self.code_to_item[etf['代码']] = item
        
        # 配置颜色标签
        self.etf_tree.tag_configure('red', foreground='#FF4444')  # 更醒目的红色
        self.etf_tree.tag_configure('green', foreground='#44CC44')  # 更柔和的绿色

    def get_sort_key(self, etf, col):
        """获取排序键值"""
        if col == "日均差异":
            return etf['日均差异']
        elif col == "日均最大差异":
            return etf['日均最大差异']
        elif col == "总涨幅":
            return etf['总涨幅']
        elif col == "赚钱度":  # 添加赚钱度排序支持
            return etf.get('赚钱度', 0.0)
        elif col == "成交额":
            return etf['成交额']
        elif col == "换手率":
            return etf['换手率']
        elif col == "换手率增幅":
            return etf['换手率增幅']
        elif col == "换手率增幅2":
            return etf['换手率增幅2']
        elif col == "换手率增幅3":
            return etf['换手率增幅3']
        elif col == "周线J":
            # 处理空字符串和NaN值
            j_value = etf.get('周线J', np.nan)
            return float(j_value) if pd.notnull(j_value) and j_value != '' else -np.inf
        elif col == "月线J":
            j_value = etf.get('月线J', np.nan)
            return float(j_value) if pd.notnull(j_value) and j_value != '' else -np.inf
        else:
            return etf[col.lower()]

    def update_treeview_arrows(self, tv, sorted_col, ascending):
        """更新表头排序指示箭头"""
        for col in tv['columns']:
            current_text = tv.heading(col)['text']
            # 移除现有箭头
            current_text = current_text.replace(' ↑', '').replace(' ↓', '')
            # 添加新箭头
            if col == sorted_col:
                arrow = ' ↑' if ascending else ' ↓'
                tv.heading(col, text=current_text + arrow)
            else:
                tv.heading(col, text=current_text)

    def save_monthly_data_cache(self):
        """保存月度数据缓存到文件"""
        try:
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_file = os.path.join(cache_dir, "monthly_data_cache.json")
            
            # 准备缓存数据
            cache_data = {
                'data': self.monthly_data_cache,
                'params': self.cache_params,
                'timestamp': datetime.now().isoformat()
            }
            
            # 将数据转换为JSON格式并保存
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"保存缓存失败: {str(e)}")

    def show_monthly_top_table(self, month, etf_data):
        """显示月度排名表格"""
        # 保存当前月份
        self.current_month = month
        
        # 清除现有组件（包括占位框架）
        for widget in self.month_table_frame.winfo_children():
            widget.destroy()
        
        # 创建表格标题
        ttk.Label(
            self.month_table_frame, 
            text=f"{month}月份ETF历史表现排名", 
            font=('Helvetica', 11, 'bold')
        ).pack(anchor=tk.W, pady=(0, 5))
        
        # 创建表格
        columns = ("代码", "名称", "平均涨幅", "样本数", "成立年份", "周线J", "月线J")
        self.month_tree = ttk.Treeview(self.month_table_frame, columns=columns, show="headings", selectmode="browse")
        
        # 添加键盘和鼠标事件绑定
        self.month_tree.bind("<Return>", self.on_monthly_row_select)  # 回车键
        self.month_tree.bind("<Double-1>", self.on_monthly_row_select)  # 双击
        
        # 设置列宽和排序命令
        col_widths = [100, 200, 100, 80, 100, 100, 100]
        for col, width in zip(columns, col_widths):
            self.month_tree.heading(col, 
                                  text=col,
                                  command=lambda c=col: self.sort_monthly_table(c))
            self.month_tree.column(col, width=width, anchor=tk.CENTER)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(self.month_table_frame, orient=tk.VERTICAL, command=self.month_tree.yview)
        self.month_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.month_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 计算每个ETF的J值
        for etf in etf_data:
            try:
                # 获取周线和月线J值
                etf['周线J'] = self.get_j_value(etf['代码'], 'week')
                etf['月线J'] = self.get_j_value(etf['代码'], 'month')
            except Exception as e:
                print(f"计算{etf['代码']}的J值时出错: {str(e)}")
                etf['周线J'] = np.nan
                etf['月线J'] = np.nan
        
        # 显示数据（只显示前n条）
        for etf in etf_data[:table_display_rows]:
            gain = etf['平均涨幅']
            self.month_tree.insert("", tk.END, values=(
                etf['代码'],
                etf['名称'],
                f"{gain:.2f}%",
                etf['样本数'],
                etf['成立年份'],
                f"{etf['周线J']:.2f}" if '周线J' in etf else '',
                f"{etf['月线J']:.2f}" if '月线J' in etf else ''
            ), tags=('red' if gain >= 0 else 'green',))
        
        # 配置颜色标签
        self.month_tree.tag_configure('red', foreground='#FF4444')
        self.month_tree.tag_configure('green', foreground='#44CC44')
        
        # 保存完整数据用于排序
        self.full_monthly_data = etf_data

    def sort_monthly_table(self, col):
        """排序月度表现表格"""
        try:
            reverse = getattr(self, 'month_sort_reverse', False)
            
            # 对完整数据进行排序
            key_map = {
                "代码": "代码",
                "名称": "名称",
                "平均涨幅": "平均涨幅",
                "样本数": "样本数",
                "成立年份": "成立年份",
                "周线J": "周线J",
                "月线J": "月线J"
            }
            
            # 使用映射后的键名进行排序
            sort_key = key_map.get(col)
            if sort_key:
                self.full_monthly_data.sort(key=lambda x: x[sort_key], reverse=reverse)
            
            # 使用保存的当前月份更新显示
            self.show_monthly_top_table(self.current_month, self.full_monthly_data)
            
            # 切换排序方向
            self.month_sort_reverse = not reverse
            
        except Exception as e:
            messagebox.showerror("错误", f"排序时出错: {str(e)}")

    def on_monthly_row_select(self, event):
        """处理月度表格行选择事件"""
        try:
            # 获取选中的行
            selection = self.month_tree.selection()
            if not selection:
                return
                
            # 获取选中行的值
            item = selection[0]
            values = self.month_tree.item(item, 'values')
            
            # 获取ETF代码
            code = values[0]
            
            # 验证并获取ETF信息
            if is_valid_symbol(code):
                # 获取ETF信息
                info = get_symbol_info(code)
                if info:
                    # 更新界面显示
                    self.parent.symbol_var.set(code)
                    self.parent.symbol_name_var.set(info[0])
                    
                    # 获取当前日期范围
                    start_date = self.parent.start_date_var.get().replace("-", "")
                    end_date = self.parent.end_date_var.get().replace("-", "")
                    
                    # 计算并更新价格区间
                    price_range = calculate_price_range(code, start_date, end_date)
                    if price_range:
                        self.parent.price_range_min_var.set(f"{price_range[0]:.2f}")
                        self.parent.price_range_max_var.set(f"{price_range[1]:.2f}")
                        
        except Exception as e:
            messagebox.showerror("错误", f"选择ETF时出错: {str(e)}") 

    def create_monthly_chart(self, monthly_data, year_range, market_data=None):
        """创建月度涨幅图表"""
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False
        
        # 创建图表
        fig = Figure(figsize=(10, 2), dpi=100)
        ax = fig.add_subplot(111)
        
        # 准备数据
        months = list(range(1, 13))
        gains = [monthly_data.get(m, 0) for m in months]
        
        # 设置柱状图宽度
        bar_width = 0.35 if market_data else 0.8
        
        # 绘制目标ETF柱状图
        colors = ['#FF4444' if g >= 0 else '#44CC44' for g in gains]
        bars1 = ax.bar([m - bar_width/2 if market_data else m for m in months], 
                       gains, 
                       bar_width,
                       color=colors,
                       label=f'{self.parent.symbol_var.get()}')
        
        # 如果有市场数据，绘制市场平均柱状图
        if market_data:
            market_gains = [market_data.get(m, 0) for m in months]
            market_colors = ['#8888FF' if g >= 0 else '#88FF88' for g in market_gains]
            bars2 = ax.bar([m + bar_width/2 for m in months], 
                           market_gains, 
                           bar_width,
                           color=market_colors,
                           label='市场平均')
            
            # 添加市场数据标签
            for bar in bars2:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.1f}%',
                        ha='center', va='bottom' if height >= 0 else 'top',
                        fontsize=8)
        
        # 添加目标ETF数据标签
        for bar in bars1:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%',
                    ha='center', va='bottom' if height >= 0 else 'top',
                    fontsize=8)
        
        # 设置标题和标签
        ax.set_xlabel('月份')
        ax.set_ylabel('涨跌幅(%)')
        
        # 设置x轴刻度
        ax.set_xticks(months)
        ax.set_xticklabels([f'{m}月' for m in months])
        
        # 添加图例
        if market_data:
            ax.legend()
        
        # 添加网格线
        ax.grid(True, linestyle='--', alpha=0.7)
        
        # 调整布局
        fig.tight_layout(pad=0.5)
        
        # 更新图表显示
        if hasattr(self, 'chart_canvas'):
            self.chart_canvas.get_tk_widget().destroy()
        
        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def enable_compare_button(self):
        """重新启用对比按钮"""
        for widget in self.chart_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        child.configure(state='normal')

    def update_chart_with_market_data(self, monthly_data, year_range, start_date, end_date):
        """更新图表显示市场平均数据"""
        # 禁用按钮避免重复点击
        for widget in self.chart_frame.winfo_children():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Button):
                        child.configure(state='disabled')
        
        # 重置进度标签
        self.market_progress_label.configure(text="准备计算...")
        
        def process_etf_data(etf_code, year_range):
            """处理单个ETF数据"""
            try:
                etf_monthly_data, _, etf_start_year = analyze_monthly_performance(etf_code)
                if etf_start_year and int(etf_start_year) <= int(year_range.split('-')[0]):
                    return etf_monthly_data, True
            except Exception:
                pass
            return None, False
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                percent = int((current / total) * 100)
                self.market_progress_label.configure(text=f"计算中... {percent}%")
            self.etf_window.after(0, _update)
        
        def calculate_market_data():
            try:
                # 获取所有ETF列表
                # 使用多API备用机制获取ETF数据
                from .etf_data_fetcher import get_etf_spot_data
                all_etfs = get_etf_spot_data(use_cache=True)
                total_etfs = len(all_etfs)
                processed_count = 0
                
                # 初始化月度数据统计
                market_monthly_data = {m: {'sum': 0, 'count': 0} for m in range(1, 13)}
                
                # 创建线程池
                with ThreadPoolExecutor(max_workers=8) as executor:
                    # 提交所有ETF的处理任务
                    future_to_etf = {
                        executor.submit(process_etf_data, etf['代码'], year_range): etf['代码']
                        for _, etf in all_etfs.iterrows()
                    }
                    
                    # 处理完成的任务结果
                    for future in as_completed(future_to_etf):
                        processed_count += 1
                        update_progress(processed_count, total_etfs)
                        
                        monthly_result, is_valid = future.result()
                        if is_valid and monthly_result:
                            for month, gain in monthly_result.items():
                                market_monthly_data[month]['sum'] += gain
                                market_monthly_data[month]['count'] += 1
                
                # 计算平均值
                market_averages = {
                    month: data['sum'] / data['count'] if data['count'] > 0 else 0 
                    for month, data in market_monthly_data.items()
                }
                
                def update_ui():
                    # 更新图表
                    self.create_monthly_chart(monthly_data, year_range, market_averages)
                    # 更新进度文本
                    self.market_progress_label.configure(text=f"完成 (共{total_etfs}个ETF)")
                    # 重新启用按钮
                    self.enable_compare_button()
                
                self.etf_window.after(0, update_ui)
                
            except Exception as e:
                def show_error():
                    error_msg = str(e)
                    messagebox.showerror("错误", f"计算市场数据时出错: {error_msg}")
                    self.market_progress_label.configure(text="计算失败")
                    self.enable_compare_button()
                
                self.etf_window.after(0, show_error)
        
        # 启动计算线程
        threading.Thread(target=calculate_market_data, daemon=True).start()

    def refresh_etf_results(self):
        """刷新ETF对比结果"""
        # 获取当前参数
        symbol = self.parent.symbol_var.get().strip()
        start_date = self.parent.start_date_var.get().replace("-", "")
        end_date = self.parent.end_date_var.get().replace("-", "")
        
        # 禁用刷新按钮并显示加载状态
        refresh_btn = self.refresh_btn  # 需要在show_etf_results中保存按钮引用
        refresh_btn.configure(state='disabled', text="...")
        
        def update_progress(current, total):
            """更新进度显示"""
            def _update():
                percent = int((current / total) * 100)
                refresh_btn.configure(text=f"{percent}%")
            self.etf_window.after(0, _update)
        
        def fetch_data():
            try:
                # 使用多API备用机制获取ETF数据
                from .etf_data_fetcher import get_etf_spot_data
                all_etfs = get_etf_spot_data(use_cache=True)
                total_etfs = len(all_etfs)
                
                results = find_similar_etf_gains(
                    target_code=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    top_n=None,
                    progress_callback=update_progress,
                    total_count=total_etfs
                )
                
                # 清除现有表格内容
                if hasattr(self, 'etf_tree'):
                    self.etf_tree.destroy()
                
                def update_ui():
                    # 恢复刷新按钮状态
                    refresh_btn.configure(state='normal', text="⟳")
                    # 显示新数据
                    self.show_etf_results(results)
                
                self.etf_window.after(0, update_ui)
                
            except Exception as e:
                def show_error():
                    error_msg = str(e)
                    messagebox.showerror("错误", f"分析失败: {error_msg}")
                    refresh_btn.configure(state='normal', text="⟳")
                self.etf_window.after(0, show_error)
        
        # 启动数据获取线程
        threading.Thread(target=fetch_data, daemon=True).start()

    def on_etf_row_select(self, event):
        """处理ETF表格行选择事件"""
        selection = self.etf_tree.selection()
        if not selection:
            return
            
        # 获取选中的ETF代码和名称
        item = selection[0]
        values = self.etf_tree.item(item, 'values')
        if not values:
            return
            
        code = values[1]
        name = values[2]  # 确保这里获取的是第二列的名称
        
        # 显示K线图
        self.kline_window.show(code, name)  # 确保传递名称参数

    def on_etf_key_select(self, event):
        """处理ETF表格键盘选择事件"""
        selection = self.etf_tree.selection()
        if not selection:
            return
            
        # 获取选中的ETF代码和名称
        item = selection[0]
        values = self.etf_tree.item(item, 'values')
        if not values:
            return
            
        code = values[1]
        name = values[2]
        
        # 显示K线图
        self.kline_window.show(code, name) 

    def start_async_strength_calculation(self, results):
        """启动异步赚钱度计算"""
        if self.strength_thread and self.strength_thread.is_alive():
            return
            
        def calculate_task():
            for etf in results:
                if etf.get('need_calculate_strength', False):
                    code = etf['代码']
                    try:
                        strength = calculate_etf_strength(code)
                        self.update_strength_value(code, strength)
                    except Exception as e:
                        print(f"计算{code}赚钱度失败: {str(e)}")
        
        self.strength_thread = threading.Thread(target=calculate_task, daemon=True)
        self.strength_thread.start()

    def handle_strength_column_click(self, col):
        """处理赚钱度列点击事件"""
        # 检查是否有未计算的赚钱度
        uncalculated_etfs = [etf for etf in self.full_etf_results 
                           if etf.get('need_calculate_strength', False)]
        total = len(uncalculated_etfs)
        
        if total > 0:
            # 初始化进度跟踪
            self.calculated_count = 0
            self.total_to_calculate = total
            
            def update_progress():
                """更新进度显示"""
                percent = int((self.calculated_count / self.total_to_calculate) * 100)
                self.etf_tree.heading(col, text=f"赚钱度 {percent}%")
                
            def calculate_task():
                """带进度跟踪的计算任务"""
                with ThreadPoolExecutor(max_workers=8) as executor:  # 新增线程池
                    futures = {
                        executor.submit(
                            calculate_etf_strength, 
                            etf['代码']
                        ): etf 
                        for etf in uncalculated_etfs
                    }
                    
                    for index, future in enumerate(as_completed(futures), 1):
                        etf = futures[future]
                        try:
                            strength = future.result()
                            etf['赚钱度'] = strength
                            etf['need_calculate_strength'] = False
                            self.update_strength_value(etf['代码'], strength)
                        except Exception as e:
                            print(f"计算{etf['代码']}赚钱度失败: {str(e)}")
                        
                        # 更新进度
                        self.calculated_count = index
                        self.etf_window.after(0, update_progress)

            def on_calculation_complete():
                """计算完成后的回调"""
                # 恢复表头显示
                self.etf_tree.heading(col, text="赚钱度")
                # 执行排序
                self.sort_treeview_column(self.etf_tree, col, self.sort_order.get(col, False))
            
            # 启动计算线程
            if not (self.strength_thread and self.strength_thread.is_alive()):
                self.strength_thread = threading.Thread(target=calculate_task, daemon=True)
                self.strength_thread.start()
        else:
            # 如果已经计算完成，直接执行排序
            self.sort_treeview_column(self.etf_tree, col, self.sort_order.get(col, False))

    def update_strength_value(self, code, strength):
        """更新表格中的赚钱度值"""
        def update():
            item = self.code_to_item.get(code)
            if item:
                values = list(self.etf_tree.item(item, 'values'))
                values[5] = f"{strength:.2f}"  # 第5列是赚钱度
                self.etf_tree.item(item, values=values)
                
                # 更新full_etf_results中的数据
                for etf in self.full_etf_results:
                    if etf['代码'] == code:
                        etf['赚钱度'] = strength
                        etf['need_calculate_strength'] = False
                        break
                    
        self.etf_window.after(0, update)

    def calculate_kdj(self, df, n=9, m1=3, m2=3):
        """计算KDJ指标"""
        try:
            # 计算N日内的最高价和最低价
            df['low_n'] = df['最低'].rolling(window=n).min()
            df['high_n'] = df['最高'].rolling(window=n).max()
            
            # 计算RSV
            df['RSV'] = (df['收盘'] - df['low_n']) / (df['high_n'] - df['low_n']) * 100
            
            # 计算K、D、J值
            df['K'] = df['RSV'].ewm(alpha=1/m1, adjust=False).mean()
            df['D'] = df['K'].ewm(alpha=1/m2, adjust=False).mean()
            df['J'] = 3 * df['K'] - 2 * df['D']
            
            # 删除中间计算列
            df = df.drop(['low_n', 'high_n', 'RSV'], axis=1)
            
            return df
        except Exception as e:
            print(f"计算KDJ指标时发生错误: {str(e)}")
            return df

    def get_j_values_batch(self, codes: list, period: str) -> dict:
        """批量获取J值"""
        try:
            # 批量获取所有ETF的历史数据
            all_data = {}
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {
                    executor.submit(
                        ak.fund_etf_hist_em,
                        symbol=code,
                        period='daily' if period == 'day' else 'weekly' if period == 'week' else 'monthly',
                        adjust="qfq"
                    ): code for code in codes
                }
                for future in as_completed(futures):
                    code = futures[future]
                    try:
                        hist_data = future.result()
                        hist_data['日期'] = pd.to_datetime(hist_data['日期'])
                        all_data[code] = hist_data
                    except Exception as e:
                        print(f"获取{code}历史数据失败: {str(e)}")
                        all_data[code] = pd.DataFrame()

            # 批量计算KDJ
            j_values = {}
            for code, data in all_data.items():
                if not data.empty:
                    try:
                        data = self.calculate_kdj(data)
                        j_values[code] = data['J'].iloc[-1]
                    except Exception as e:
                        print(f"计算{code}的J值失败: {str(e)}")
                        j_values[code] = np.nan
                else:
                    j_values[code] = np.nan
            
            return j_values

        except Exception as e:
            print(f"批量获取J值失败: {str(e)}")
            return {code: np.nan for code in codes}

    def update_etf_list(self, etfs):
        """更新ETF列表"""
        # 清空现有数据
        for item in self.etf_tree.get_children():
            self.etf_tree.delete(item)
        
        # 添加新数据
        for etf in etfs:
            # 获取周线和月线J值
            weekly_j = self.get_j_values_batch([etf['代码']], 'week').get(etf['代码'], np.nan)
            monthly_j = self.get_j_values_batch([etf['代码']], 'month').get(etf['代码'], np.nan)
            
            values = (
                etf['置顶'],
                etf['代码'],
                etf['名称'],
                format(etf['价格'], '.3f'),
                format(etf['涨跌幅'], '.2f'),
                format(etf['成交量'], '.0f'),
                format(etf['成交额'], '.0f'),
                format(etf['换手率1'], '.2f'),
                format(etf['换手率2'], '.2f'),
                format(etf['换手率3'], '.2f'),
                format(weekly_j, '.2f') if pd.notnull(weekly_j) else '',  # 周线J
                format(monthly_j, '.2f') if pd.notnull(monthly_j) else '', # 月线J
                format(etf.get('赚钱度', ''), '.2f')
            )
            
            self.etf_tree.insert('', 'end', values=values) 

    def toggle_pin_status(self, event):
        """切换ETF的置顶状态"""
        region = self.etf_tree.identify("region", event.x, event.y)
        if region == "cell":
            item = self.etf_tree.identify_row(event.y)
            column = self.etf_tree.identify_column(event.x)
            if column == "#1":  # 第一列是置顶按钮列
                values = self.etf_tree.item(item, "values")
                code = values[1]  # 第二列是代码
                
                # 获取当前ETF数据
                current_etf = None
                for etf in self.full_etf_results:
                    if etf['代码'] == code:
                        current_etf = etf
                        break
                
                if code in self.pinned_codes:
                    # 取消置顶
                    self.pinned_codes.remove(code)
                    if current_etf:
                        # 先从列表中移除
                        self.full_etf_results.remove(current_etf)
                        
                        # 找到按照当前排序规则应该插入的位置
                        # 获取当前排序的列和方向
                        sorted_col = None
                        for col, arrow in self.sort_order.items():
                            if self.etf_tree.heading(col)['text'].endswith(('↑', '↓')):
                                sorted_col = col
                                reverse = not arrow  # arrow为True表示升序(↑),False表示降序(↓)
                                break
                        
                        # 如果有排序规则,按规则插入;否则插入到非置顶区域的开头
                        if sorted_col:
                            # 获取所有非置顶项
                            unpinned_results = [etf for etf in self.full_etf_results 
                                              if etf['代码'] not in self.pinned_codes]
                            
                            # 按照当前排序规则排序
                            unpinned_results.sort(
                                key=lambda x: self.get_sort_key(x, sorted_col),
                                reverse=reverse
                            )
                            
                            # 找到当前ETF应该插入的位置
                            insert_pos = 0
                            for i, etf in enumerate(unpinned_results):
                                if reverse:
                                    if self.get_sort_key(current_etf, sorted_col) >= self.get_sort_key(etf, sorted_col):
                                        insert_pos = i
                                        break
                                else:
                                    if self.get_sort_key(current_etf, sorted_col) <= self.get_sort_key(etf, sorted_col):
                                        insert_pos = i
                                        break
                                insert_pos = i + 1
                            
                            # 插入到正确位置
                            pinned_count = len([etf for etf in self.full_etf_results 
                                              if etf['代码'] in self.pinned_codes])
                            self.full_etf_results.insert(pinned_count + insert_pos, current_etf)
                        else:
                            # 没有排序规则,插入到非置顶区域的开头
                            pinned_count = len([etf for etf in self.full_etf_results 
                                              if etf['代码'] in self.pinned_codes])
                            self.full_etf_results.insert(pinned_count, current_etf)
                else:
                    # 添加置顶
                    self.pinned_codes.add(code)
                    # 将当前ETF移到结果列表最前面
                    if current_etf:
                        self.full_etf_results.remove(current_etf)
                        self.full_etf_results.insert(0, current_etf)
                
                # 更新表格显示
                self.update_table_display()
                
                # 保持当前选中状态
                self.etf_tree.selection_set(item)