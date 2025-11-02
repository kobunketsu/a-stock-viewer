import tkinter as tk
from tkinter import ttk
import json
import os
from locales.localization import l

class ShortcutsManager:
    """快捷键管理器"""
    
    DEFAULT_SHORTCUTS = {
        'etf_compare': 'Command-E',
        'start_optimization': 'Command-Return',
        'search': 'Command-F',
        'kline': 'Command-K'
    }
    
    MODIFIER_SYMBOLS = {
        'Command': '⌘',
        'Option': '⌥',
        'Control': '⌃',
        'Shift': '⇧'
    }
    
    MODIFIERS = ['Command', 'Option', 'Control', 'Shift']
    
    def __init__(self, root):
        self.root = root
        self.shortcuts = {}
        self.config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                      "data", "shortcuts.json")
        self.load_shortcuts()
        
        # 创建设置对话框
        self.dialog = None
        
    def load_shortcuts(self):
        """加载快捷键配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.shortcuts = json.load(f)
            else:
                self.shortcuts = self.DEFAULT_SHORTCUTS.copy()
                self.save_shortcuts()
        except Exception as e:
            print(f"Error loading shortcuts: {e}")
            self.shortcuts = self.DEFAULT_SHORTCUTS.copy()
    
    def save_shortcuts(self):
        """保存快捷键配置"""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.shortcuts, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving shortcuts: {e}")
    
    def get_shortcut_key(self, action):
        """获取快捷键组合"""
        return self.shortcuts.get(action, self.DEFAULT_SHORTCUTS.get(action, ''))
    
    def get_shortcut_display(self, action):
        """获取用于显示的快捷键文本"""
        shortcut = self.get_shortcut_key(action)
        if not shortcut:
            return ''
        
        parts = shortcut.split('-')
        display_parts = []
        
        for part in parts[:-1]:  # 处理修饰键
            symbol = self.MODIFIER_SYMBOLS.get(part, part)
            display_parts.append(symbol)
            
        display_parts.append(parts[-1])  # 添加主键
        return ''.join(display_parts)
    
    def show_settings(self):
        """显示快捷键设置对话框"""
        if self.dialog is None or not self.dialog.winfo_exists():
            self.dialog = ShortcutSettingsDialog(self.root, self)
            self.dialog.grab_set()  # 设置为模态对话框
    
    def validate_and_save_shortcut(self, action, modifier, key):
        """验证并保存快捷键"""
        if not key:
            return False
            
        # 验证输入
        if not self._validate_key(key):
            messagebox.showerror(l("input_error"), l("invalid_key_format"))
            return False
            
        # 构建快捷键字符串
        new_shortcut = f"{modifier}-{key}" if modifier else key
        
        # 检查冲突
        for act, shortcut in self.shortcuts.items():
            if act != action and shortcut == new_shortcut:
                messagebox.showerror(l("shortcut_conflict"), 
                                   l("shortcut_already_in_use").format(act))
                return False
        
        # 保存新快捷键
        self.shortcuts[action] = new_shortcut
        self.save_shortcuts()
        return True
    
    def _validate_key(self, key):
        """验证键值是否合法"""
        if len(key) == 1:
            return key.isalnum()
        elif key.startswith('F'):
            try:
                num = int(key[1:])
                return 1 <= num <= 12
            except ValueError:
                return False
        return False

    def _init_default_shortcuts(self):
        self.shortcuts = {
            # ... 原有配置 ...
            'kline': {
                'key': 'K',
                'modifiers': ['command'],
                'description': '打开K线图'
            }
        }

class ShortcutSettingsDialog(tk.Toplevel):
    """快捷键设置对话框"""
    
    def __init__(self, parent, shortcuts_manager):
        super().__init__(parent)
        self.shortcuts_manager = shortcuts_manager
        
        self.title(l("shortcut_settings"))
        self.geometry("400x300")
        
        # 创建主框架
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题标签
        ttk.Label(main_frame, text=l("shortcut_settings"), 
                 font=('Arial', 14, 'bold')).pack(pady=(0, 10))
        
        # 创建快捷键设置列表
        self.create_shortcut_list(main_frame)
        
        # 绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 使窗口居中
        self.center_window()
    
    def create_shortcut_list(self, parent):
        """创建快捷键设置列表"""
        # 创建表格头部
        headers_frame = ttk.Frame(parent)
        headers_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(headers_frame, text=l("function"), width=20).pack(side=tk.LEFT)
        ttk.Label(headers_frame, text=l("modifier_key"), width=15).pack(side=tk.LEFT)
        ttk.Label(headers_frame, text=l("shortcut_key"), width=10).pack(side=tk.LEFT)
        
        # 创建分隔线
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=5)
        
        # 创建快捷键列表框架
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 添加每个快捷键设置行
        row = 0
        for action, display_name in {
            'etf_compare': l("etf_compare"),
            'start_optimization': l("start_optimization"),
            'search': l("search"),
            'kline': l("kline_chart")
        }.items():
            self.create_shortcut_row(list_frame, action, display_name, row)
            row += 1
    
    def create_shortcut_row(self, parent, action, display_name, row):
        """创建单个快捷键设置行"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=2)
        
        # 功能名称
        ttk.Label(frame, text=display_name, width=20).pack(side=tk.LEFT)
        
        # 当前快捷键
        current = self.shortcuts_manager.get_shortcut_key(action)
        current_parts = current.split('-') if current else ['', '']
        
        # 修饰键下拉框
        modifier_var = tk.StringVar(value=current_parts[0] if len(current_parts) > 1 else '')
        modifier_combo = ttk.Combobox(frame, textvariable=modifier_var, 
                                    values=self.shortcuts_manager.MODIFIERS,
                                    width=12, state='readonly')
        modifier_combo.pack(side=tk.LEFT, padx=5)
        
        # 主键输入框
        key_var = tk.StringVar(value=current_parts[-1])
        key_entry = ttk.Entry(frame, textvariable=key_var, width=8)
        key_entry.pack(side=tk.LEFT, padx=5)
        
        # 绑定验证和保存事件
        def on_key_change(*args):
            key = key_var.get().upper()
            key_var.set(key)  # 自动转换为大写
            if key:
                self.shortcuts_manager.validate_and_save_shortcut(
                    action, modifier_var.get(), key)
        
        key_var.trace_add('write', on_key_change)
        key_entry.bind('<FocusOut>', lambda e: on_key_change())
        key_entry.bind('<Return>', lambda e: on_key_change())
        modifier_combo.bind('<<ComboboxSelected>>', lambda e: on_key_change())
    
    def center_window(self):
        """使窗口居中显示"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def on_close(self):
        """关闭窗口时的处理"""
        self.shortcuts_manager.save_shortcuts()
        if hasattr(self.master, 'rebind_shortcuts'):
            self.master.rebind_shortcuts()
        self.destroy() 