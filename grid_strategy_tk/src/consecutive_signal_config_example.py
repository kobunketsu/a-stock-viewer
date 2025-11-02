"""
连续信号配置使用示例
演示如何修改连涨和连跌信号的参数
"""

from consecutive_signal_config import (get_plunge_config, get_surge_config,
                                       update_plunge_config,
                                       update_surge_config)


def example_1_default_config():
    """示例1：查看默认配置"""
    print("=== 示例1：查看默认配置 ===")
    
    surge_config = get_surge_config()
    plunge_config = get_plunge_config()
    
    print("连涨信号默认配置:")
    for key, value in surge_config.items():
        print(f"  {key}: {value}")
    
    print("\n连跌信号默认配置:")
    for key, value in plunge_config.items():
        print(f"  {key}: {value}")

def example_2_modify_consecutive_count():
    """示例2：修改连续K线数量"""
    print("\n=== 示例2：修改连续K线数量 ===")
    
    # 将连涨信号改为3连涨
    update_surge_config(consecutive_count=3)
    
    # 将连跌信号改为4连跌
    update_plunge_config(consecutive_count=4)
    
    print("修改后的配置:")
    print(f"连涨信号连续数量: {get_surge_config()['consecutive_count']}")
    print(f"连跌信号连续数量: {get_plunge_config()['consecutive_count']}")

def example_3_modify_display_style():
    """示例3：修改显示样式"""
    print("\n=== 示例3：修改显示样式 ===")
    
    # 修改连涨信号显示样式
    update_surge_config(
        display_text='▲',  # 改为向上三角形
        line_color='blue',  # 改为蓝色
        font_size=20,  # 增大字体
        line_width=3  # 加粗线条
    )
    
    # 修改连跌信号显示样式
    update_plunge_config(
        display_text='▼',  # 改为向下三角形
        line_color='orange',  # 改为橙色
        font_size=18,  # 增大字体
        line_width=3  # 加粗线条
    )
    
    print("修改后的显示样式:")
    surge_config = get_surge_config()
    print(f"连涨信号: {surge_config['display_text']}, 颜色: {surge_config['line_color']}, 字体: {surge_config['font_size']}")
    
    plunge_config = get_plunge_config()
    print(f"连跌信号: {plunge_config['display_text']}, 颜色: {plunge_config['line_color']}, 字体: {plunge_config['font_size']}")

def example_4_modify_position():
    """示例4：修改标签位置"""
    print("\n=== 示例4：修改标签位置 ===")
    
    # 调整标签偏移比例，让标签更靠近K线
    update_surge_config(label_offset_ratio=0.05)  # 从10%改为5%
    update_plunge_config(label_offset_ratio=0.05)  # 从10%改为5%
    
    print("修改后的标签位置:")
    print(f"连涨信号偏移比例: {get_surge_config()['label_offset_ratio']}")
    print(f"连跌信号偏移比例: {get_plunge_config()['label_offset_ratio']}")

def example_5_custom_style():
    """示例5：自定义样式"""
    print("\n=== 示例5：自定义样式 ===")
    
    # 创建自定义连涨样式
    update_surge_config(
        consecutive_count=6,  # 6连涨
        signal_name_prefix='强势连涨',  # 自定义名称前缀
        display_text='🚀',  # 火箭表情
        line_color='purple',  # 紫色
        label_color='purple',
        line_style='--',  # 虚线
        line_width=2,
        font_size=24,  # 超大字体
        label_offset_ratio=0.15,  # 更大的偏移
        font_weight='bold',
        bbox_style=dict(facecolor='yellow', alpha=0.3, pad=3)  # 黄色背景框
    )
    
    # 创建自定义连跌样式
    update_plunge_config(
        consecutive_count=7,  # 7连跌
        signal_name_prefix='深度连跌',  # 自定义名称前缀
        display_text='💥',  # 爆炸表情
        line_color='darkred',  # 深红色
        label_color='darkred',
        line_style=':',  # 点线
        line_width=3,
        font_size=22,  # 大字体
        label_offset_ratio=0.12,  # 较大偏移
        font_weight='bold',
        bbox_style=dict(facecolor='lightcoral', alpha=0.4, pad=2)  # 浅珊瑚色背景框
    )
    
    print("自定义样式配置:")
    surge_config = get_surge_config()
    print(f"连涨信号: {surge_config['signal_name_prefix']}{surge_config['consecutive_count']}")
    print(f"  显示: {surge_config['display_text']}, 颜色: {surge_config['line_color']}")
    print(f"  线条: {surge_config['line_style']}, 宽度: {surge_config['line_width']}")
    print(f"  字体: {surge_config['font_size']}, 偏移: {surge_config['label_offset_ratio']}")
    
    plunge_config = get_plunge_config()
    print(f"连跌信号: {plunge_config['signal_name_prefix']}{plunge_config['consecutive_count']}")
    print(f"  显示: {plunge_config['display_text']}, 颜色: {plunge_config['line_color']}")
    print(f"  线条: {plunge_config['line_style']}, 宽度: {plunge_config['line_width']}")
    print(f"  字体: {plunge_config['font_size']}, 偏移: {plunge_config['label_offset_ratio']}")

def example_6_reset_to_default():
    """示例6：重置为默认配置"""
    print("\n=== 示例6：重置为默认配置 ===")
    
    # 重置连涨信号为默认配置
    update_surge_config(
        consecutive_count=5,
        signal_name_prefix='连涨',
        display_text='↗',
        line_color='red',
        label_color='red',
        line_style='-',
        line_width=2,
        font_size=16,
        label_offset_ratio=0.1,
        font_weight='bold',
        bbox_style=None
    )
    
    # 重置连跌信号为默认配置
    update_plunge_config(
        consecutive_count=5,
        signal_name_prefix='连跌',
        display_text='↘',
        line_color='green',
        label_color='green',
        line_style='-',
        line_width=2,
        font_size=16,
        label_offset_ratio=0.1,
        font_weight='bold',
        bbox_style=None
    )
    
    print("已重置为默认配置")

if __name__ == "__main__":
    print("连续信号配置使用示例")
    print("=" * 50)
    
    example_1_default_config()
    example_2_modify_consecutive_count()
    example_3_modify_display_style()
    example_4_modify_position()
    example_5_custom_style()
    example_6_reset_to_default()
    
    print("\n" + "=" * 50)
    print("所有示例执行完成！")
    print("\n使用方法:")
    print("1. 导入配置模块: from consecutive_signal_config import *")
    print("2. 查看配置: get_surge_config(), get_plunge_config()")
    print("3. 修改配置: update_surge_config(**kwargs), update_plunge_config(**kwargs)")
    print("4. 配置会在下次创建信号实例时生效")
