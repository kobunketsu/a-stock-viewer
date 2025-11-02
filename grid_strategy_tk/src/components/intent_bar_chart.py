import tkinter as tk
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class IntentBarChart:
    """主力意图水平柱状图组件"""
    def __init__(self, parent):
        """
        初始化主力意图图表
        
        Args:
            parent: 父级容器
        """
        # 创建主frame
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建图表，设置宽高比为1:1
        self.fig = Figure(figsize=(3, 3), dpi=100)  # 调整为正方形尺寸
        self.ax = self.fig.add_subplot(111)
        
        # 创建canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # 初始化数据
        self.data = None
        
        # 设置图表样式
        self.ax.set_title('主力操盘意图', fontsize=10)
        self.fig.tight_layout()
        
        # 定义颜色映射
        self.colors = {
            '建仓': '#2ECC71',  # 绿色
            '试盘': '#F1C40F',  # 黄色
            '洗盘': '#3498DB',  # 蓝色
            '拉升': '#E74C3C',  # 红色
            '出货': '#8E44AD',  # 紫色
            '反弹': '#1ABC9C',  # 青色
            '砸盘': '#E67E22'   # 橙色
        }
    
    def update_data(self, intent_data):
        """
        更新主力意图数据显示
        
        Args:
            intent_data: 包含主力意图概率和指标的字典
        """
        # 清除旧图
        self.ax.clear()
        
        if not intent_data or 'probabilities' not in intent_data:
            return
            
        # 获取概率数据
        probs = intent_data['probabilities']
        labels = list(probs.keys())
        values = list(probs.values())
        
        # 获取对应的颜色列表
        bar_colors = [self.colors[label] for label in labels]
        
        # 绘制水平条形图
        y_pos = np.arange(len(labels))
        bars = self.ax.barh(y_pos, values, align='center', color=bar_colors)
        self.ax.set_yticks(y_pos)
        self.ax.set_yticklabels(labels)
        
        # 设置标题和样式
        self.ax.set_title('主力操盘意图', fontsize=10)
        self.ax.set_xlim(0, 1)
        
        # 添加数值标签
        for i, bar in enumerate(bars):
            width = bar.get_width()
            self.ax.text(
                width, 
                bar.get_y() + bar.get_height()/2,
                f'{width:.2f}',
                ha='left', 
                va='center',
                fontsize=8
            )
            
        # 添加指标信息
        # if 'indicators' in intent_data:
        #     indicators = intent_data['indicators']
        #     indicator_text = (
        #         f"成本压力比: {indicators['成本压力比']:.2f}\n"
        #         f"量能动量: {indicators['量能动量']:.2f}\n"
        #         f"价格加速度: {indicators['价格加速度']:.2f}"
        #     )
        #     self.ax.text(
        #         0.98, 0.02, 
        #         indicator_text,
        #         transform=self.ax.transAxes,
        #         ha='right', 
        #         va='bottom',
        #         bbox=dict(
        #             facecolor='white', 
        #             alpha=0.8, 
        #             pad=5
        #         ),
        #         fontsize=8
        #     )
        
        # 调整布局
        self.fig.tight_layout()
        self.canvas.draw()
    
    def show_loading(self, text="加载中..."):
        """显示加载提示"""
        self.ax.clear()
        self.ax.text(
            0.5, 0.5,
            text,
            ha='center',
            va='center',
            transform=self.ax.transAxes
        )
        self.canvas.draw()
    
    def show_error(self, error_msg):
        """显示错误信息"""
        self.ax.clear()
        self.ax.text(
            0.5, 0.5,
            f"错误: {error_msg}",
            ha='center',
            va='center',
            transform=self.ax.transAxes,
            color='red'
        )
        self.canvas.draw()
    
    def hide_loading(self):
        """隐藏加载提示"""
        self.ax.clear()
        self.canvas.draw() 