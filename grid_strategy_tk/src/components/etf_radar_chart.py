import tkinter as tk
import tkinter.ttk as ttk
from typing import Dict

import numpy as np
from locales.localization import l
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class ETFRadarChart:
    """ETF指标雷达图组件"""
    
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.Frame(parent)
        # 调整雷达图的大小，使其更扁平
        self.figure = Figure(figsize=(3, 3), dpi=100)  # 减小高度
        self.ax = self.figure.add_subplot(111, polar=True)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._current_data = None
        
    def update_data(self, indicators: Dict[str, float]):
        """更新雷达图数据"""
        self._current_data = indicators
        self._draw_radar()
        
    def _draw_radar(self):
        """绘制雷达图"""
        if not self._current_data:
            return
            
        # 清除旧图表
        self.ax.clear()
        
        # 准备数据
        categories = [
            l('volume_price_correlation'),
            l('holding_stability'), 
            l('arbitrage_impact'),
            l('volume_health'),
            l('momentum_trend'),
            l('volatility_quality')
        ]
        
        # 确保数据完整性
        values = []
        for cat in ['volume_price_correlation', 'holding_stability', 'arbitrage_impact',
                   'volume_health', 'momentum_trend', 'volatility_quality']:
            values.append(self._current_data.get(cat, 0.5))  # 使用0.5作为默认值
        
        # 使雷达图闭合
        values += values[:1]
        categories += categories[:1]
        
        # 设置角度
        N = len(categories) - 1  # 减1因为我们添加了重复点
        angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
        angles += angles[:1]
        
        # 绘制网格线
        self.ax.set_ylim(0, 1)
        gridlines = np.arange(0.2, 1.2, 0.2)
        for grid in gridlines:
            self.ax.plot(angles, [grid] * len(angles), 
                        color='gray', linestyle=':', alpha=0.3)
        
        # 绘制数据线
        self.ax.plot(angles, values, 'o-', linewidth=2, color='#1f77b4')
        self.ax.fill(angles, values, alpha=0.25, color='#1f77b4')
        
        # 设置标签
        self.ax.set_xticks(angles[:-1])
        self.ax.set_xticklabels(categories[:-1], fontsize=8)
        
        # 设置方向和位置
        self.ax.set_theta_offset(np.pi / 2)
        self.ax.set_theta_direction(-1)
        
        # 设置径向标签
        self.ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
        self.ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=8)
        self.ax.set_rlabel_position(0)
        
        # 添加标题
        self.ax.set_title(l('radar_chart_title'), y=1.05, fontsize=10)
        
        # 调整布局
        self.figure.tight_layout()
        
        # 重绘
        self.canvas.draw() 

    def show_loading(self, text):
        """显示加载状态"""
        if not hasattr(self, 'loading_label'):
            self.loading_label = ttk.Label(self.frame, text="")
            self.loading_label.place(relx=0.5, rely=0.5, anchor='center')
        self.loading_label.configure(text=text)
    
    def hide_loading(self):
        """隐藏加载状态"""
        if hasattr(self, 'loading_label'):
            self.loading_label.place_forget()
    
    def show_error(self, message):
        """显示错误信息"""
        self.show_loading(f"错误: {message}")
        self.frame.after(3000, self.hide_loading) 