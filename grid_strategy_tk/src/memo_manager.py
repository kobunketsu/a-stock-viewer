import os
import json
from datetime import datetime

class MemoManager:
    def __init__(self):
        # 创建memo目录用于存储备忘录文件
        self.memo_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memos")
        if not os.path.exists(self.memo_dir):
            os.makedirs(self.memo_dir)
    
    def get_memo_file_path(self, symbol):
        """获取指定股票的备忘录文件路径"""
        return os.path.join(self.memo_dir, f"{symbol}_memo.json")
    
    def save_memo(self, symbol, content):
        """保存备忘录内容"""
        memo_file = self.get_memo_file_path(symbol)
        memo_data = {
            "content": content,
            "last_modified": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            with open(memo_file, 'w', encoding='utf-8') as f:
                json.dump(memo_data, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"保存备忘录失败: {e}")
            return False
    
    def load_memo(self, symbol):
        """加载备忘录内容"""
        memo_file = self.get_memo_file_path(symbol)
        if not os.path.exists(memo_file):
            return {"content": "", "last_modified": None}
        
        try:
            with open(memo_file, 'r', encoding='utf-8') as f:
                memo_data = json.load(f)
            return memo_data
        except Exception as e:
            print(f"加载备忘录失败: {e}")
            return {"content": "", "last_modified": None} 