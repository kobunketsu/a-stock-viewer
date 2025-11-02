#!/usr/bin/env python3
"""信号自定义示例 - 展示如何使用新的信号系统"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import tkinter as tk
from typing import Any, Dict

import pandas as pd
from intraday_signals import (IntradaySignalBase, MA25CrossMA50BuySignal,
                              RSISellSignal)
from intraday_window import IntradayWindow


class CustomVolumeBuySignal(IntradaySignalBase):
    """自定义成交量买入信号 - 当成交量突破前5分钟平均成交量的2倍时触发"""
    
    def __init__(self, volume_multiplier: float = 2.0, delay_minutes: int = 1):
        super().__init__(f"成交量突破({volume_multiplier}倍)", delay_minutes)
        self.volume_multiplier = volume_multiplier
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查成交量是否突破前5分钟平均成交量的指定倍数"""
        if index < 5:  # 需要至少5个数据点
            return False
        
        volumes = data.get('volumes')
        if volumes is None or index >= len(volumes):
            return False
        
        current_volume = volumes.iloc[index]
        if pd.isna(current_volume):
            return False
        
        # 计算前5分钟的平均成交量
        prev_volumes = volumes.iloc[max(0, index-5):index]
        avg_volume = prev_volumes.mean()
        
        if pd.isna(avg_volume) or avg_volume == 0:
            return False
        
        # 检查当前成交量是否突破前5分钟平均成交量的指定倍数
        return current_volume >= avg_volume * self.volume_multiplier
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证信号有效性 - 检查延迟时间内成交量是否保持在高位"""
        volumes = data.get('volumes')
        if volumes is None:
            return False
        
        # 检查延迟时间内成交量是否仍然保持在高位
        for check_i in range(signal_index + 1, min(signal_index + self.delay_minutes + 1, len(volumes))):
            if check_i < len(volumes):
                check_volume = volumes.iloc[check_i]
                if pd.isna(check_volume):
                    continue
                
                # 计算前5分钟的平均成交量
                prev_volumes = volumes.iloc[max(0, check_i-5):check_i]
                avg_volume = prev_volumes.mean()
                
                if pd.isna(avg_volume) or avg_volume == 0:
                    continue
                
                # 如果成交量回落到正常水平，则信号无效
                if check_volume < avg_volume * self.volume_multiplier * 0.8:  # 允许20%的回落
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建成交量买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        volumes = data.get('volumes')
        close_prices = data.get('close_prices')
        
        if volumes is not None and close_prices is not None:
            current_price = close_prices.iloc[index]
            current_volume = volumes.iloc[index]
            
            # 计算前5分钟的平均成交量
            prev_volumes = volumes.iloc[max(0, index-5):index]
            avg_volume = prev_volumes.mean()
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
            
            # 计算当日涨跌幅
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            base_signal.update({
                'price': current_price,
                'volume': current_volume,
                'avg_volume': avg_volume,
                'volume_ratio': volume_ratio,
                'net_gain': net_gain
            })
        
        return base_signal


class CustomPriceBreakoutBuySignal(IntradaySignalBase):
    """自定义价格突破买入信号 - 当价格突破前20分钟最高价时触发"""
    
    def __init__(self, breakout_threshold: float = 0.02, delay_minutes: int = 2):
        super().__init__(f"价格突破({breakout_threshold*100:.1f}%)", delay_minutes)
        self.breakout_threshold = breakout_threshold
    
    def check_condition(self, data: Dict[str, Any], index: int) -> bool:
        """检查价格是否突破前20分钟最高价"""
        if index < 20:  # 需要至少20个数据点
            return False
        
        close_prices = data.get('close_prices')
        if close_prices is None or index >= len(close_prices):
            return False
        
        current_price = close_prices.iloc[index]
        if pd.isna(current_price):
            return False
        
        # 计算前20分钟的最高价
        prev_prices = close_prices.iloc[max(0, index-20):index]
        max_price = prev_prices.max()
        
        if pd.isna(max_price):
            return False
        
        # 检查当前价格是否突破前20分钟最高价
        return current_price > max_price * (1 + self.breakout_threshold)
    
    def validate_signal(self, data: Dict[str, Any], signal_index: int, current_index: int) -> bool:
        """验证信号有效性 - 检查延迟时间内价格是否保持在突破位之上"""
        close_prices = data.get('close_prices')
        if close_prices is None:
            return False
        
        # 计算信号产生时的前20分钟最高价
        prev_prices = close_prices.iloc[max(0, signal_index-20):signal_index]
        max_price = prev_prices.max()
        
        if pd.isna(max_price):
            return False
        
        # 检查延迟时间内价格是否保持在突破位之上
        for check_i in range(signal_index + 1, min(signal_index + self.delay_minutes + 1, len(close_prices))):
            if check_i < len(close_prices):
                check_price = close_prices.iloc[check_i]
                if pd.isna(check_price):
                    continue
                
                # 如果价格回落到突破位之下，则信号无效
                if check_price <= max_price:
                    return False
        
        return True
    
    def create_signal_data(self, data: Dict[str, Any], index: int) -> Dict[str, Any]:
        """创建价格突破买入信号数据"""
        base_signal = super().create_signal_data(data, index)
        
        close_prices = data.get('close_prices')
        
        if close_prices is not None:
            current_price = close_prices.iloc[index]
            
            # 计算前20分钟的最高价
            prev_prices = close_prices.iloc[max(0, index-20):index]
            max_price = prev_prices.max()
            breakout_pct = ((current_price - max_price) / max_price * 100) if max_price > 0 else 0
            
            # 计算当日涨跌幅
            prev_close = data.get('prev_close')
            if prev_close is not None and prev_close > 0:
                net_gain = (current_price - prev_close) / prev_close * 100
            else:
                net_gain = 0.0
            
            base_signal.update({
                'price': current_price,
                'breakout_price': max_price,
                'breakout_pct': breakout_pct,
                'net_gain': net_gain
            })
        
        return base_signal


def demonstrate_signal_customization():
    """演示信号自定义功能"""
    print("🚀 信号自定义系统演示")
    print("=" * 50)
    
    # 创建主窗口
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    
    # 创建Frame作为父级容器
    parent_frame = tk.Frame(root)
    parent_frame.pack()
    
    # 创建分时窗口
    intraday_window = IntradayWindow(parent_frame, "000001", "平安银行")
    
    print("\n📊 当前默认信号配置:")
    intraday_window.list_signals()
    
    print("\n🔧 添加自定义买入信号...")
    
    # 添加自定义成交量买入信号
    volume_signal = CustomVolumeBuySignal(volume_multiplier=2.5, delay_minutes=1)
    intraday_window.add_buy_signal(volume_signal)
    
    # 添加自定义价格突破买入信号
    breakout_signal = CustomPriceBreakoutBuySignal(breakout_threshold=0.015, delay_minutes=2)
    intraday_window.add_buy_signal(breakout_signal)
    
    print("\n📊 添加自定义信号后的配置:")
    intraday_window.list_signals()
    
    print("\n⚙️ 自定义信号参数:")
    print(f"  成交量信号: {volume_signal.name}")
    print(f"    - 成交量倍数: {volume_signal.volume_multiplier}")
    print(f"    - 延迟时间: {volume_signal.delay_minutes}分钟")
    
    print(f"  价格突破信号: {breakout_signal.name}")
    print(f"    - 突破阈值: {breakout_signal.breakout_threshold*100:.1f}%")
    print(f"    - 延迟时间: {breakout_signal.delay_minutes}分钟")
    
    print("\n🔄 信号管理操作演示:")
    
    # 移除指定信号
    print("移除价格突破信号...")
    intraday_window.remove_buy_signal("价格突破(1.5%)")
    
    print("\n📊 移除信号后的配置:")
    intraday_window.list_signals()
    
    # 清空所有自定义信号
    print("\n清空所有自定义信号...")
    intraday_window.clear_all_signals()
    
    print("\n📊 恢复默认配置后的信号:")
    intraday_window.list_signals()
    
    print("\n✅ 信号自定义系统演示完成！")
    
    # 关闭窗口
    root.destroy()


if __name__ == "__main__":
    try:
        demonstrate_signal_customization()
    except Exception as e:
        print(f"演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
