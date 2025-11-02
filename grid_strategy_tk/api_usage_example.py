#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API频率限制和错误处理使用示例

这个示例展示了如何使用改进后的AKShareWrapper来处理API调用频次限制和连接错误。
"""

import logging
import os
import sys
import time

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from akshare_wrapper import AKShareWrapper


def setup_logging():
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('api_usage.log', encoding='utf-8')
        ]
    )

def demonstrate_api_usage():
    """演示API使用方法"""
    print("=== API频率限制和错误处理演示 ===\n")
    
    # 创建API包装器实例
    wrapper = AKShareWrapper()
    
    # 1. 检查API状态
    print("1. 检查API状态:")
    status = wrapper.get_api_status()
    print(f"   - 是否在冷却期: {status['is_in_cooldown']}")
    print(f"   - 剩余冷却时间: {status['remaining_cooldown']:.1f}秒")
    print(f"   - 错误计数: {status['error_count']}/{status['max_consecutive_errors']}")
    print(f"   - 最小调用间隔: {status['min_call_interval']}秒")
    
    # 2. 正常API调用
    print("\n2. 正常API调用:")
    try:
        # 获取股票列表
        stock_list = wrapper.stock_info_a_code_name()
        if not stock_list.empty:
            print(f"   ✅ 成功获取股票列表，共 {len(stock_list)} 只股票")
            print(f"   📊 前5只股票: {stock_list.head()['名称'].tolist()}")
        else:
            print("   ❌ 获取股票列表失败")
    except Exception as e:
        print(f"   ❌ 调用异常: {e}")
    
    # 3. 连续API调用（测试频率限制）
    print("\n3. 连续API调用测试:")
    symbols = ['000001', '000002', '000858', '002415', '300059']
    
    for i, symbol in enumerate(symbols):
        print(f"   获取股票 {symbol} 历史数据...")
        start_time = time.time()
        
        try:
            hist_data = wrapper.stock_zh_a_hist(symbol=symbol, period='daily', 
                                              start_date='20240101', end_date='20241231')
            elapsed = time.time() - start_time
            
            if not hist_data.empty:
                print(f"   ✅ 成功获取 {symbol} 数据，{len(hist_data)} 条记录，耗时 {elapsed:.2f}秒")
            else:
                print(f"   ⚠️  {symbol} 返回空数据，耗时 {elapsed:.2f}秒")
        except Exception as e:
            print(f"   ❌ 获取 {symbol} 失败: {e}")
        
        # 检查API状态
        status = wrapper.get_api_status()
        if status['is_in_cooldown']:
            print(f"   🕐 API进入冷却期，剩余 {status['remaining_cooldown']:.1f} 秒")
            break
    
    # 4. 处理连接错误
    print("\n4. 连接错误处理演示:")
    print("   - 当遇到连接错误时，系统会自动重试")
    print("   - 连续3次连接错误后，会进入60秒冷却期")
    print("   - 冷却期内所有API调用都会返回空数据")
    
    # 5. API状态监控
    print("\n5. API状态监控:")
    final_status = wrapper.get_api_status()
    print(f"   - 最终错误计数: {final_status['error_count']}")
    print(f"   - 是否在冷却期: {final_status['is_in_cooldown']}")
    print(f"   - 最后调用时间: {time.ctime(final_status['last_call_time'])}")
    
    # 6. 手动重置API状态（如果需要）
    if final_status['is_in_cooldown']:
        print("\n6. 手动重置API状态:")
        wrapper.reset_api_status()
        print("   ✅ API状态已重置")

def demonstrate_error_scenarios():
    """演示错误处理场景"""
    print("\n=== 错误处理场景演示 ===\n")
    
    wrapper = AKShareWrapper()
    
    # 模拟连续错误
    print("模拟连续API调用错误...")
    for i in range(5):
        print(f"   第 {i+1} 次调用...")
        # 这里可以故意传入错误的参数来触发错误
        try:
            result = wrapper.stock_zh_a_hist(symbol="INVALID", period="daily")
            if result.empty:
                print(f"   ⚠️  第 {i+1} 次调用返回空数据")
            else:
                print(f"   ✅ 第 {i+1} 次调用成功")
        except Exception as e:
            print(f"   ❌ 第 {i+1} 次调用异常: {e}")
        
        # 检查是否进入冷却期
        status = wrapper.get_api_status()
        if status['is_in_cooldown']:
            print(f"   🕐 进入冷却期，剩余 {status['remaining_cooldown']:.1f} 秒")
            break
        else:
            print(f"   📊 当前错误计数: {status['error_count']}/{status['max_consecutive_errors']}")

if __name__ == "__main__":
    # 设置日志
    setup_logging()
    
    # 演示正常使用
    demonstrate_api_usage()
    
    # 演示错误处理
    demonstrate_error_scenarios()
    
    print("\n=== 演示完成 ===")
    print("💡 提示:")
    print("   - 如果频繁遇到连接错误，系统会自动进入冷却期")
    print("   - 冷却期内请避免继续调用API")
    print("   - 可以通过 get_api_status() 监控API状态")
    print("   - 可以通过 reset_api_status() 手动重置状态")

