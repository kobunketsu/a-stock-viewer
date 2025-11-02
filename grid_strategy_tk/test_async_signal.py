#!/usr/bin/env python3
"""
测试异步布林带计算后的连板信号显示
"""

import os
import sys

# 按照akshare-dev规则设置路径
sys.path.insert(0, '/opt/homebrew/lib/python3.9/site-packages')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import tkinter as tk
from datetime import date, datetime

import pandas as pd
from src.intraday_window import IntradayWindow


def test_async_signal():
    """测试异步布林带计算后的连板信号显示"""
    print("测试开始...")
    
    try:
        # 创建主窗口
        root = tk.Tk()
        root.title("异步连板信号测试 - 600996")
        root.geometry("1200x800")
        
        # 创建分时窗口（嵌入模式）
        test_date = date(2025, 9, 22)
        
        print(f"创建分时窗口，股票: 600996，日期: {test_date}")
        print("测试流程：")
        print("1. 初始加载：布林带数据不可用")
        print("2. 异步计算：等待布林带数据计算完成")
        print("3. 信号检测：布林带数据可用后检测连板信号")
        print("4. 信号显示：重新绘制图表显示信号")
        
        # 创建嵌入的分时窗口
        intraday_frame = tk.Frame(root)
        intraday_frame.pack(fill=tk.BOTH, expand=True)
        
        # 添加说明标签
        info_label = tk.Label(root, text="等待布林带数据异步计算完成...", 
                            font=('Arial', 12, 'bold'), fg='blue')
        info_label.pack(pady=5)
        
        # 添加状态标签
        status_label = tk.Label(root, text="状态：初始化中...", 
                              font=('Arial', 10), fg='orange')
        status_label.pack(pady=2)
        
        # 添加调试按钮
        debug_btn = tk.Button(root, text="检查状态", 
                            command=lambda: check_status(intraday_window, status_label))
        debug_btn.pack(pady=5)
        
        intraday_window = IntradayWindow(
            parent=intraday_frame,
            code="600996",
            name="600996连板信号测试",
            trade_date=test_date,
            embed=True,
            show_toolbar=True
        )
        
        # 定期检查状态
        def update_status():
            try:
                if intraday_window.bollinger_5min_upper is not None:
                    status_label.config(text="状态：布林带数据已计算完成，检测信号中...", fg='green')
                    if intraday_window.buy_signals and len(intraday_window.buy_signals) > 0:
                        status_label.config(text="状态：连板信号已检测到！", fg='blue')
                        info_label.config(text="✅ 连板信号已显示在图表上！", fg='green')
                else:
                    status_label.config(text="状态：等待布林带数据计算...", fg='orange')
            except Exception as e:
                status_label.config(text=f"状态：错误 - {str(e)}", fg='red')
            
            root.after(3000, update_status)  # 每3秒检查一次
        
        update_status()
        
        print("分时窗口创建成功")
        print("请观察：")
        print("1. 初始状态：布林带数据不可用")
        print("2. 异步计算：等待布林带数据计算完成")
        print("3. 信号检测：连板信号应该出现")
        print("4. 信号显示：红色实线，标签 '10.0%连板'")
        print("点击'检查状态'按钮查看详细信息")
        print("关闭窗口结束测试...")
        
        # 运行GUI
        root.mainloop()
        
    except Exception as e:
        print(f'错误: {e}')
        import traceback
        traceback.print_exc()

def check_status(intraday_window, status_label):
    """检查状态"""
    try:
        print(f"\n=== 状态检查 ===")
        print(f"布林带数据状态:")
        print(f"  上轨: {intraday_window.bollinger_5min_upper is not None}")
        print(f"  中轨: {intraday_window.bollinger_5min_middle is not None}")
        print(f"  下轨: {intraday_window.bollinger_5min_lower is not None}")
        print(f"  计算完成: {getattr(intraday_window, '_bollinger_calculated', False)}")
        
        print(f"\n信号状态:")
        print(f"  买入信号数量: {len(intraday_window.buy_signals) if intraday_window.buy_signals else 0}")
        if intraday_window.buy_signals:
            for i, signal in enumerate(intraday_window.buy_signals):
                print(f"    信号 {i+1}: {signal.get('signal_type', 'Unknown')} - 价格: {signal.get('price', 0):.3f}")
        
        print(f"  卖出信号数量: {len(intraday_window.sell_signals) if intraday_window.sell_signals else 0}")
        
        # 更新状态标签
        if intraday_window.bollinger_5min_upper is not None:
            if intraday_window.buy_signals and len(intraday_window.buy_signals) > 0:
                status_label.config(text="状态：连板信号已检测到！", fg='blue')
            else:
                status_label.config(text="状态：布林带数据已计算，但无信号", fg='orange')
        else:
            status_label.config(text="状态：等待布林带数据计算...", fg='orange')
        
        print(f"================\n")
    except Exception as e:
        print(f"检查状态失败: {e}")

if __name__ == "__main__":
    test_async_signal()
