# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from locales.localization import l  # 改为绝对导入
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

class LowPriceDigitDistributionChart:
    """
    显示最低价末位数字（分）分布的柱状图组件。
    """
    def __init__(self, parent_frame):
        """
        初始化图表。

        :param parent_frame: 父Tkinter框架。
        """
        self.frame = tk.Frame(parent_frame, bg='white')
        
        # 创建标题框架
        self.title_frame = ttk.Frame(self.frame)
        self.title_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        
        # 创建标题标签
        self.title_label = ttk.Label(
            self.title_frame,
            text=l("low_price_digit_distribution"),  # "最低价末位数字(分)分布"
            font=('SimHei', 9)
        )
        self.title_label.pack(side=tk.LEFT)
        
        # 创建日期范围标签
        self.date_label = ttk.Label(
            self.title_frame,
            text="",  # 初始为空，稍后更新
            font=('SimHei', 9),
            foreground='gray'
        )
        self.date_label.pack(side=tk.RIGHT)
        
        # 创建图表框架
        self.chart_frame = ttk.Frame(self.frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True)
        
        self.figure, self.ax = plt.subplots(figsize=(5, 2), dpi=100)
        self.figure.subplots_adjust(left=0.1, right=0.95, top=0.95, bottom=0.15)  # 调整上边距，给图表更多空间
        self.figure.patch.set_facecolor('white')
        self.ax.set_facecolor('white')

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.chart_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)

        self._initialize_chart()

    def _initialize_chart(self):
        """初始化图表外观"""
        self.ax.clear()
        # 移除标题，改用外部标签
        self.ax.set_xlabel(l("digit"), fontsize=8)
        self.ax.set_ylabel(l("probability"), fontsize=8)
        self.ax.set_xticks(range(10))
        self.ax.tick_params(axis='x', labelsize=8)
        self.ax.tick_params(axis='y', labelsize=8)
        self.ax.yaxis.set_major_formatter(plt.FuncFormatter('{:.1%}'.format))
        self.ax.grid(True, linestyle='--', alpha=0.5, axis='y')
        self.canvas.draw()

    def update_data(self, distribution: pd.Series, start_date: str = None, end_date: str = None):
        """
        更新图表数据和日期范围。
        
        :param distribution: 包含0-9数字及其概率的Pandas Series
        :param start_date: 统计开始日期，格式：YYYY-MM-DD
        :param end_date: 统计结束日期，格式：YYYY-MM-DD
        """
        self._initialize_chart()

        if distribution is None or distribution.empty:
            self.show_message(l("no_data_available"))
            self.date_label.configure(text="")  # 清空日期范围
            return

        # 更新日期范围标签
        if start_date and end_date:
            date_text = f"{start_date} ~ {end_date}"
            self.date_label.configure(text=date_text)
        else:
            self.date_label.configure(text="")

        # 绘制柱状图
        digits = distribution.index
        probabilities = distribution.values

        bars = self.ax.bar(digits, probabilities, color='skyblue')

        # 在柱状图顶部显示概率值
        for bar in bars:
            yval = bar.get_height()
            self.ax.text(bar.get_x() + bar.get_width()/2.0, yval,
                        f'{yval:.1%}',
                        va='bottom', ha='center', fontsize=7)

        # 设置Y轴范围
        max_prob = probabilities.max() if len(probabilities) > 0 else 0
        self.ax.set_ylim(0, max(max_prob * 1.2, 0.01))

        self.canvas.draw()

    def show_loading(self, message=l("loading")+"..."): # 加载中...
        """显示加载信息"""
        self._initialize_chart()
        self.ax.text(0.5, 0.5, message,
                     horizontalalignment='center',
                     verticalalignment='center',
                     transform=self.ax.transAxes,
                     fontsize=10, color='gray')
        self.canvas.draw()

    def show_error(self, message=l("error_loading_data")): # 加载数据出错
        """显示错误信息"""
        self._initialize_chart()
        self.ax.text(0.5, 0.5, message,
                     horizontalalignment='center',
                     verticalalignment='center',
                     transform=self.ax.transAxes,
                     fontsize=10, color='red')
        self.canvas.draw()

    def show_message(self, message):
        """显示通用消息"""
        self._initialize_chart()
        self.ax.text(0.5, 0.5, message,
                     horizontalalignment='center',
                     verticalalignment='center',
                     transform=self.ax.transAxes,
                     fontsize=10, color='gray')
        self.canvas.draw()

    def hide_loading(self):
        """隐藏加载/错误信息（通过重绘空图表）"""
        self._initialize_chart()

    def hide_loading(self):
        """隐藏加载/错误信息（通过重绘空图表）"""
        self._initialize_chart() 