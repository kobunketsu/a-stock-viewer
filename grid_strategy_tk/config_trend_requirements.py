#!/usr/bin/env python3
"""
趋势判断参数配置工具
用于修改各周期的连阳天数要求
"""

import os
import sys

# 添加src目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from trend_config import (DAILY_MIN_CONSECUTIVE_DAYS,
                          MIN5_MIN_CONSECUTIVE_DAYS,
                          MONTHLY_MIN_CONSECUTIVE_DAYS,
                          QUARTERLY_MIN_CONSECUTIVE_DAYS,
                          WEEKLY_MIN_CONSECUTIVE_DAYS,
                          YEARLY_MIN_CONSECUTIVE_DAYS, get_config_info)


def show_current_config():
    """显示当前配置"""
    print("=" * 50)
    print("当前趋势判断参数配置")
    print("=" * 50)
    config = get_config_info()
    print(f"配置版本: {config['version']}")
    print(f"配置描述: {config['description']}")
    print()
    print("各周期最小连阳天数要求:")
    print(f"  日级 (day):     {DAILY_MIN_CONSECUTIVE_DAYS} 连阳")
    print(f"  周级 (week):    {WEEKLY_MIN_CONSECUTIVE_DAYS} 连阳")
    print(f"  月级 (month):   {MONTHLY_MIN_CONSECUTIVE_DAYS} 连阳")
    print(f"  季级 (quarter): {QUARTERLY_MIN_CONSECUTIVE_DAYS} 连阳")
    print(f"  年级 (year):    {YEARLY_MIN_CONSECUTIVE_DAYS} 连阳")
    print(f"  5分钟 (5min):   {MIN5_MIN_CONSECUTIVE_DAYS} 连阳")
    print("=" * 50)

def update_config():
    """更新配置"""
    print("\n配置修改说明:")
    print("1. 修改 src/trend_config.py 文件中的对应变量")
    print("2. 重启应用程序使配置生效")
    print("3. 系统会自动清除旧版本缓存")
    print()
    print("可修改的变量:")
    print("  DAILY_MIN_CONSECUTIVE_DAYS    - 日级连阳天数")
    print("  WEEKLY_MIN_CONSECUTIVE_DAYS   - 周级连阳天数") 
    print("  MONTHLY_MIN_CONSECUTIVE_DAYS  - 月级连阳天数")
    print("  QUARTERLY_MIN_CONSECUTIVE_DAYS - 季级连阳天数")
    print("  YEARLY_MIN_CONSECUTIVE_DAYS   - 年级连阳天数")
    print("  MIN5_MIN_CONSECUTIVE_DAYS     - 5分钟级连阳天数")
    print()
    print("示例修改:")
    print("  MONTHLY_MIN_CONSECUTIVE_DAYS = 2  # 将月级改为2连阳")
    print("  DAILY_MIN_CONSECUTIVE_DAYS = 5    # 将日级改为5连阳")

def main():
    """主函数"""
    show_current_config()
    update_config()
    
    print("\n注意事项:")
    print("1. 修改参数后需要重启应用程序")
    print("2. 系统会自动检测版本变化并清除相关缓存")
    print("3. 建议在非交易时间进行参数调整")
    print("4. 修改前请备份重要数据")

if __name__ == "__main__":
    main()

