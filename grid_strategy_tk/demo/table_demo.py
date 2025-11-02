import tkinter as tk
from tkinter import ttk

class TableDemo(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Table Demo")
        self.geometry("1200x600")
        
        # 创建主分割容器
        self.main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)
        
        # 创建左侧Frame(用于容纳表格和滚动条)
        self.left_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.left_frame, weight=1)
        
        # 创建右侧Frame
        self.right_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.right_frame, weight=1)
        
        # 创建表格
        self._create_table()
        
        # 创建右侧标题显示
        self.title_label = ttk.Label(self.right_frame, text="", wraplength=300)
        self.title_label.pack(padx=20, pady=20)
        
    def _create_table(self):
        # 创建滚动条
        scrollbar = ttk.Scrollbar(self.left_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 创建水平滚动条
        h_scrollbar = ttk.Scrollbar(self.left_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 创建表格
        columns = [f"Column {i}" for i in range(1, 11)]
        self.tree = ttk.Treeview(self.left_frame, columns=columns, show='headings',
                                yscrollcommand=scrollbar.set,
                                xscrollcommand=h_scrollbar.set)
        
        # 设置列标题和宽度
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        
        # 添加模拟数据
        for i in range(50):
            values = [f"Item {i}-{j}" for j in range(1, 11)]
            self.tree.insert('', tk.END, values=values)
            
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        scrollbar.config(command=self.tree.yview)
        h_scrollbar.config(command=self.tree.xview)
        
        # 绑定选择事件
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        # 修改键盘事件绑定
        self.tree.bind('<Up>', self._handle_up_key)
        self.tree.bind('<Down>', self._handle_down_key)
        
    def _on_select(self, event):
        """处理选择事件"""
        selected_items = self.tree.selection()
        if selected_items:
            item = selected_items[0]
            values = self.tree.item(item)['values']
            # 更新右侧标题显示
            self.title_label.config(text=f"当前选中行的内容:\n\n{', '.join(map(str, values))}")
            
    def _handle_up_key(self, event):
        """处理向上键"""
        # 获取当前选中项
        selection = self.tree.selection()
        if not selection:
            # 如果没有选中项，选择最后一项
            last_item = self.tree.get_children()[-1]
            self.tree.selection_set(last_item)
            self.tree.see(last_item)
            return "break"
            
        current_item = selection[0]
        # 获取所有项
        all_items = self.tree.get_children()
        current_idx = all_items.index(current_item)
        
        # 如果不是第一项，选择上一项
        if current_idx > 0:
            prev_item = all_items[current_idx - 1]
            self.tree.selection_set(prev_item)
            self.tree.see(prev_item)
        
        return "break"
    
    def _handle_down_key(self, event):
        """处理向下键"""
        # 获取当前选中项
        selection = self.tree.selection()
        if not selection:
            # 如果没有选中项，选择第一项
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.see(first_item)
            return "break"
            
        current_item = selection[0]
        # 获取所有项
        all_items = self.tree.get_children()
        current_idx = all_items.index(current_item)
        
        # 如果不是最后一项，选择下一项
        if current_idx < len(all_items) - 1:
            next_item = all_items[current_idx + 1]
            self.tree.selection_set(next_item)
            self.tree.see(next_item)
        
        return "break"

if __name__ == "__main__":
    app = TableDemo()
    app.mainloop() 