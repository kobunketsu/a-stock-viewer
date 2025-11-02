import gettext
import json
import os


def setup_localization():
    """设置本地化"""
    # 获取当前目录的上级目录中的 locales 文件夹
    locale_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locales')
    
    # 加载 JSON 翻译文件
    json_path = os.path.join(locale_dir, 'zh_CN.json')
    translations = {}
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            translations = json.load(f)
    except Exception as e:
        print(f"Error loading translations: {e}")
    
    def translate(text):
        """翻译函数"""
        return translations.get(text, text)
    
    return translate

# 创建全局翻译函数
l = setup_localization() 

# 添加新的翻译词条
translations = {
    "month_filter": {
        "zh_CN": "过滤月份(1-12)",
        "en_US": "Filter Month (1-12)"
    },
    "month_must_be_1_to_12": {
        "zh_CN": "月份必须为1-12之间的整数",
        "en_US": "Month must be integer between 1-12"
    },
    "invalid_month_format": {
        "zh_CN": "月份格式无效，请输入1-12的数字",
        "en_US": "Invalid month format, please enter number 1-12"
    }
}

def update_translations(new_translations):
    """更新翻译词条"""
    global translations
    translations.update(new_translations)

def translate(text):
    """翻译函数"""
    return translations.get(text, text)

# 更新全局翻译函数
l = update_translations(translations)
l = translate

# 创建全局翻译函数
l = setup_localization() 